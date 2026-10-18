import asyncio
import hashlib
import json
import unittest
from copy import deepcopy
from dataclasses import replace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from azure.cosmos.exceptions import CosmosHttpResponseError
from httpx import ASGITransport, AsyncClient

from agent_creation import AgentCreations, CreationSettings
from agent_publisher import PublicationError
from agent_templates import TEMPLATES
from log_capture import CapturedLabLogs
from app import Settings, create_app


OPERATOR_KEY = "fictional-unit-test-operator-key-not-a-real-secret"
ORIGIN = "https://lab.test"
ENDPOINT = "https://fictional.services.ai.azure.com/api/projects/lab"
KEY_HASH = hashlib.sha256(OPERATOR_KEY.encode()).hexdigest()


class MemoryStore:
    def __init__(self):
        self.rows = {}
        self.revision = 0
        self.check = AsyncMock()
        self.close = AsyncMock()

    async def get(self, identifier):
        if identifier not in self.rows:
            raise CosmosHttpResponseError(status_code=404)
        return deepcopy(self.rows[identifier])

    async def create(self, document):
        if document["id"] in self.rows:
            raise CosmosHttpResponseError(status_code=409)
        self.revision += 1
        self.rows[document["id"]] = {**deepcopy(document), "_etag": str(self.revision)}
        return await self.get(document["id"])

    async def replace(self, document, etag):
        current = await self.get(document["id"])
        if current["_etag"] != etag:
            raise CosmosHttpResponseError(status_code=412)
        self.revision += 1
        self.rows[document["id"]] = {**deepcopy(document), "_etag": str(self.revision)}
        return await self.get(document["id"])

    async def list_created_agents(self, project):
        return [deepcopy(row) for row in self.rows.values()
                if row.get("kind") == "created-agent" and row["project"] == project]

    async def list(self, agents, cursor):
        return {"items": [{key: row[key] for key in ("id", "title", "agent_id", "updated_at")}
                          for row in self.rows.values()
                          if "kind" not in row and row["agent_id"] in agents], "cursor": None}


class FakePublisher:
    def __init__(self, store):
        self.store = store
        self.calls = []
        self.release = asyncio.Event()
        self.release.set()
        self.done = asyncio.Event()
        self.error = None

    async def run(self, operation, document, progress):
        persisted = await self.store.get(document["id"])
        self.calls.append((operation, persisted))
        try:
            if operation == "create":
                await progress("uploading", publication_started=True)
            await self.release.wait()
            if self.error is not None:
                raise self.error
            if operation == "delete":
                await progress("deleted", status="deleted", error=None)
            else:
                await progress("provisioning", version="1")
                await progress("routing")
                await progress("ready", status="ready", error=None)
        finally:
            self.done.set()

    async def create(self, document, progress):
        await self.run("create", document, progress)

    async def resume(self, document, progress):
        await self.run("resume", document, progress)

    async def delete(self, document, progress):
        await self.run("delete", document, progress)


class AgentCreationTests(CapturedLabLogs, unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.store = MemoryStore()
        self.publisher = FakePublisher(self.store)
        self.gateway = AsyncMock()
        self.gateway.review.return_value = ("completed", "Illustrative unit-test answer.", [])
        self.settings = Settings(
            "private", ENDPOINT, ("lab.test",), (ORIGIN,),
            creation=CreationSettings(True, "test-model", KEY_HASH, max_agents=2), unfinished_agents=True,
        )
        self.body = {
            "idempotency_key": str(uuid4()), "template_id": "document-analyst",
            "name": "Fictional document helper", "instructions": "Analyze only fictional supplied text.",
            "confirm_cost": True,
        }
        self.client = self.make_client()
        self.operator = {"X-Workbench-Creation-Key": OPERATOR_KEY}

    def make_client(self, settings=None, store=None):
        return AsyncClient(
            transport=ASGITransport(app=create_app(settings or self.settings, self.gateway,
                                                 store or self.store, self.publisher)),
            base_url=ORIGIN, headers={"X-Workbench-Request": "1", "Origin": ORIGIN},
        )

    async def asyncTearDown(self):
        self.publisher.release.set()
        await asyncio.sleep(0)
        await self.client.aclose()

    async def create(self, **changes):
        return await self.client.post("/api/agents", json={**self.body, **changes}, headers=self.operator)

    async def ready(self):
        response = await self.create()
        self.assertEqual(response.status_code, 202, response.text)
        await asyncio.wait_for(self.publisher.done.wait(), 1)
        result = await self.client.get("/api/agents/" + response.json()["id"])
        self.assertEqual(result.json()["status"], "ready", result.text)
        return result.json()

    async def test_saved_record_exposes_runtime_hash_for_offline_export(self):
        record = await self.ready()
        persisted = await self.store.get(record["id"])
        self.assertEqual(record["runtime_hash"], persisted["runtime_hash"])
        self.assertRegex(record["runtime_hash"], r"^[a-f0-9]{64}$")
        self.assertNotIn("setup_hash", record)
        self.assertNotIn("project", record)

    async def test_templates_and_drafts_do_not_use_storage_or_models(self):
        templates = await self.client.get("/api/agent-templates")
        self.assertEqual(templates.status_code, 200)
        self.assertEqual(templates.json()["draft_mode"], "template")
        self.assertEqual(templates.json()["schema_version"], 1)
        self.assertEqual(len(templates.json()["templates"]), 18)
        self.assertEqual(
            sum(item["count"] for item in templates.json()["facets"]["sectors"]),
            18,
        )
        response = await self.client.post("/api/agent-drafts", json={
            "goal": "Summarize a fictional policy document.", "template_id": "document-analyst",
        })
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["source"], "template")
        self.assertEqual(self.store.rows, {})
        self.assertEqual(self.publisher.calls, [])
        self.gateway.review.assert_not_awaited()

    async def test_scorecards_serve_recorded_results_without_storage_or_models(self):
        response = await self.client.get("/api/agent-scorecards")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["schema_version"], 1)
        cards = {card["template_id"]: card for card in body["scorecards"]}
        self.assertIn("supplier-invoice-reviewer", cards)
        self.assertIn("customer-support-brief", cards)
        self.assertEqual(len(cards), 18)
        for card in cards.values():
            self.assertEqual(card["summary"]["cases"], len(card["cases"]))
            self.assertEqual(card["signed_off"], card["signed_off_by"] is not None)
        self.assertEqual(self.store.rows, {})
        self.assertEqual(self.publisher.calls, [])
        self.gateway.review.assert_not_awaited()
        blocked = await self.client.get("/api/agent-scorecards", headers={"x-workbench-request": ""})
        self.assertEqual(blocked.status_code, 403)

    async def test_slow_setup_upload_never_starts_publication(self):
        async def stalled(request):
            await asyncio.Event().wait()
            yield b""

        timeout = asyncio.timeout
        with patch("starlette.requests.Request.stream", stalled), patch(
            "request_guard.asyncio.timeout", side_effect=lambda seconds: timeout(0.01 if seconds == 5 else seconds)
        ):
            response = await self.create()
        self.assertEqual(response.status_code, 408)
        self.assertEqual(response.json()["error"], "request_timeout")
        self.assertEqual(self.store.rows, {})
        self.assertEqual(self.publisher.calls, [])

    async def test_error_bodies_carry_the_request_id(self):
        cases = [
            (await self.client.post("/api/agent-drafts", json={"goal": "Help with this generic review."}),
             400, "template_required"),
            (await self.client.post("/api/agents", json=self.body), 403, "operator_access_required"),
            (await self.client.get("/api/agents/not-an-agent"), 404, "agent_not_found"),
            (await self.client.get("/api/agents", headers={"Origin": "https://untrusted.test"}),
             403, "request_not_allowed"),
        ]
        for response, status, code in cases:
            with self.subTest(code=code):
                self.assertEqual(response.status_code, status, response.text)
                body = response.json()
                self.assertEqual(body["error"], code)
                self.assertTrue(body["request_id"])
                self.assertEqual(body["request_id"], response.headers["X-Correlation-ID"])
        self.assertIn("candidates", cases[0][0].json())

    async def test_ambiguous_and_invalid_drafts_are_explicit(self):
        response = await self.client.post("/api/agent-drafts", json={"goal": "Help with this generic review."})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "template_required")
        for body in ({"goal": "short"}, {"goal": "x" * 1201}, {"goal": "x" * 15, "tools": []},
                     {"goal": "x" * 15, "template_id": "not-a-template"}):
            with self.subTest(body=body):
                self.assertEqual((await self.client.post("/api/agent-drafts", json=body)).status_code, 400)

    async def test_preview_can_prepare_but_cannot_publish_or_list_shared_records(self):
        preview = Settings("preview", "", ("localhost",), ("http://localhost",), unfinished_agents=True)
        async with AsyncClient(transport=ASGITransport(app=create_app(preview)),
                               base_url="http://localhost", headers={"X-Workbench-Request": "1"}) as client:
            config = (await client.get("/api/config")).json()
            self.assertFalse(config["agent_creation"]["enabled"])
            self.assertFalse(config["agent_creation"]["storage_enabled"])
            self.assertEqual(config["agent_creation"]["reason"], "local_preview")
            response = await client.post("/api/agent-drafts", json={
                "goal": "Summarize a fictional policy.", "template_id": "document-analyst",
            })
            self.assertEqual(response.status_code, 200)
            self.assertEqual((await client.post("/api/agents", json=self.body)).status_code, 503)
            self.assertEqual((await client.get("/api/agents")).status_code, 503)

    async def test_operator_origin_and_marker_are_required_before_storage_mutation(self):
        for headers in (
            {}, {"X-Workbench-Creation-Key": "invalid"},
            {**self.operator, "Origin": "https://untrusted.test"},
            {**self.operator, "Sec-Fetch-Site": "cross-site"},
            {**self.operator, "X-Workbench-Request": "0"},
        ):
            with self.subTest(headers=list(headers)):
                response = await self.client.post("/api/agents", json=self.body, headers=headers)
                self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(self.store.rows, {})
        self.assertEqual(self.publisher.calls, [])

    async def test_strict_setup_never_accepts_endpoint_tools_model_or_implicit_cost(self):
        invalid = [
            {"endpoint": ENDPOINT}, {"tools": ["write_external_record"]}, {"model": "different-model"},
            {"confirm_cost": False}, {"confirm_cost": 1}, {"confirm_cost": "true"},
            {"idempotency_key": "not-a-uuid"}, {"template_id": "hidden-existing-agent"},
            {"name": "\x7f"}, {"name": " "}, {"name": "a" * 81},
            {"instructions": "short"}, {"instructions": "x" * 6001},
        ]
        for changes in invalid:
            with self.subTest(changes=changes):
                response = await self.create(**changes)
                self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(self.store.rows, {})

    async def test_request_byte_limit_and_json_content_type(self):
        response = await self.client.post("/api/agents", content="x" * 32769,
                                          headers={**self.operator, "Content-Type": "application/json"})
        self.assertEqual(response.status_code, 413)
        response = await self.client.post("/api/agents", content=json.dumps(self.body),
                                          headers={**self.operator, "Content-Type": "text/plain"})
        self.assertEqual(response.status_code, 400)

    async def test_persists_before_cloud_call_then_exposes_ready_agent(self):
        record = await self.ready()
        persisted = self.publisher.calls[0][1]
        self.assertEqual(persisted["status"], "creating")
        self.assertFalse(persisted["publication_started"])
        self.assertEqual(persisted["ttl"], -1)
        self.assertEqual(record["agent"]["id"], record["id"])
        self.assertEqual(record["agent"]["agent"], record["runtime_name"])
        self.assertTrue(record["runtime_name"].startswith("lab-demo-"))
        self.assertNotIn(self.body["name"], record["runtime_name"])
        self.assertEqual(record["agent"]["tools"], {})
        self.assertEqual([event["name"] for event in record["events"]],
                         ["queued", "uploading", "provisioning", "routing", "ready"])
        self.assertNotIn("setup_hash", record)
        self.assertNotIn(KEY_HASH, json.dumps(record))
        self.assertNotIn(OPERATOR_KEY, json.dumps(self.store.rows))

    async def test_duplicate_requests_never_schedule_second_publication(self):
        record = await self.ready()
        response = await self.create()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], record["id"])
        self.assertEqual(len(self.publisher.calls), 1)
        changed = await self.create(instructions="Use a different fictional task.")
        self.assertEqual(changed.status_code, 409)
        self.assertEqual(changed.json()["error"], "agent_changed")

    async def test_operation_is_single_flight_and_quota_counts_existing_agents(self):
        self.publisher.release.clear()
        first = await self.create()
        self.assertEqual(first.status_code, 202)
        second = await self.create(idempotency_key=str(uuid4()))
        self.assertEqual(second.status_code, 429)
        self.assertEqual(second.json()["error"], "agents_busy")
        duplicate = await self.create()
        self.assertEqual(duplicate.status_code, 200)
        self.publisher.release.set()
        await asyncio.wait_for(self.publisher.done.wait(), 1)
        self.publisher.done.clear()
        second = await self.create(idempotency_key=str(uuid4()))
        self.assertEqual(second.status_code, 202)
        await asyncio.wait_for(self.publisher.done.wait(), 1)
        third = await self.create(idempotency_key=str(uuid4()))
        self.assertEqual(third.status_code, 409)
        self.assertEqual(third.json()["error"], "agent_limit_reached")

    async def test_failed_publication_is_saved_and_same_request_does_not_retry(self):
        self.publisher.error = PublicationError("publication_unconfirmed")
        first = await self.create()
        await asyncio.wait_for(self.publisher.done.wait(), 1)
        result = await self.client.get("/api/agents/" + first.json()["id"])
        self.assertEqual(result.json()["status"], "interrupted")
        self.assertEqual(result.json()["error"], "publication_unconfirmed")
        self.assertIsNone(result.json()["agent"])
        self.assertEqual((await self.create()).status_code, 200)
        self.assertEqual(len(self.publisher.calls), 1)

    async def test_failed_runtime_logs_foundry_error_code_without_returning_it(self):
        self.publisher.error = PublicationError("runtime_failed", "CodeError")
        with self.assertLogs("uvicorn.error", level="WARNING") as logs:
            first = await self.create()
            await asyncio.wait_for(self.publisher.done.wait(), 1)
            result = await self.client.get("/api/agents/" + first.json()["id"])
        self.assertEqual(result.json()["status"], "failed")
        self.assertEqual(result.json()["error"], "runtime_failed")
        self.assertNotIn("CodeError", json.dumps(result.json()))
        failures = [json.loads(record.getMessage()) for record in logs.records
                    if "agent_publication_failed" in record.getMessage()]
        self.assertEqual(failures[-1]["service_error"], "CodeError")

    async def test_lost_process_is_reported_interrupted_and_requires_explicit_resume(self):
        record = await self.ready()
        row = self.store.rows[record["id"]]
        row.update(status="creating", stage="provisioning")
        current = (await self.client.get("/api/agents/" + record["id"])).json()
        self.assertEqual(current["status"], "interrupted")
        self.assertIsNone(current["agent"])
        path = "/api/agents/" + record["id"] + "/resume"
        self.assertEqual((await self.client.post(path, headers=self.operator)).status_code, 409)
        self.publisher.done.clear()
        result = await self.client.post(path, headers={**self.operator, "If-Match": current["_etag"]})
        self.assertEqual(result.status_code, 202, result.text)
        await asyncio.wait_for(self.publisher.done.wait(), 1)
        self.assertEqual([operation for operation, _ in self.publisher.calls], ["create", "resume"])

    async def test_resume_cannot_reverse_an_interrupted_deletion(self):
        record = await self.ready()
        self.store.rows[record["id"]].update(status="deleting", stage="deleting", operation="delete")
        response = await self.client.post("/api/agents/" + record["id"] + "/resume",
                                          headers={**self.operator, "If-Match": record["_etag"]})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"], "agent_not_resumable")

    async def test_deletion_is_conditional_and_leaves_minimal_idempotency_tombstone(self):
        record = await self.ready()
        path = "/api/agents/" + record["id"]
        self.assertEqual((await self.client.delete(path, headers=self.operator)).status_code, 409)
        self.publisher.done.clear()
        result = await self.client.delete(path, headers={**self.operator, "If-Match": record["_etag"]})
        self.assertEqual(result.status_code, 202)
        await asyncio.wait_for(self.publisher.done.wait(), 1)
        deleted = (await self.client.get(path)).json()
        self.assertEqual(deleted["status"], "deleted")
        self.assertEqual(deleted["instructions"], "")
        self.assertEqual(deleted["name"], "Deleted agent")
        self.assertEqual((await self.client.get("/api/agents")).json()["items"], [])
        self.assertEqual(self.store.rows[record["id"]]["ttl"], -1)
        self.assertEqual((await self.create()).status_code, 200)
        self.assertEqual([operation for operation, _ in self.publisher.calls], ["create", "delete"])

    async def test_resume_cannot_reopen_a_deleted_agent_but_repeated_deletion_is_idempotent(self):
        record = await self.ready()
        path = "/api/agents/" + record["id"]
        self.publisher.done.clear()
        await self.client.delete(path, headers={**self.operator, "If-Match": record["_etag"]})
        await asyncio.wait_for(self.publisher.done.wait(), 1)
        deleted = (await self.client.get(path)).json()
        headers = {**self.operator, "If-Match": deleted["_etag"]}
        resumed = await self.client.post(path + "/resume", headers=headers)
        self.assertEqual(resumed.status_code, 409, resumed.text)
        self.assertEqual(resumed.json()["error"], "agent_not_resumable")
        repeated = await self.client.delete(path, headers=headers)
        self.assertEqual(repeated.status_code, 200, repeated.text)
        self.assertEqual(repeated.json()["status"], "deleted")
        self.assertEqual((await self.client.get(path)).json()["status"], "deleted")
        self.assertEqual([operation for operation, _ in self.publisher.calls], ["create", "delete"])
    async def test_creation_disable_keeps_read_chat_and_operator_deletion_available(self):
        record = await self.ready()
        disabled = replace(self.settings, creation=replace(self.settings.creation, enabled=False))
        async with self.make_client(disabled) as client:
            config = (await client.get("/api/config")).json()["agent_creation"]
            self.assertFalse(config["enabled"])
            self.assertTrue(config["management_enabled"])
            response = await client.post("/api/agents", json=self.body, headers=self.operator)
            self.assertEqual(response.status_code, 503)
            self.assertEqual((await client.get("/api/agents")).json()["items"][0]["id"], record["id"])
            response = await client.delete("/api/agents/" + record["id"],
                                           headers={**self.operator, "If-Match": record["_etag"]})
            self.assertEqual(response.status_code, 202)

    async def test_chat_and_history_resolve_ready_agents_after_application_restart(self):
        record = await self.ready()
        async with self.make_client() as client:
            response = await client.post("/api/reviews", json={"agent_id": record["id"], "input": "Fictional document."})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(self.gateway.review.call_args.args[0]["agent"], record["runtime_name"])
            saved = await client.post("/api/conversations", json={
                "agent_id": record["id"], "turns": [{"question": "Fictional document.", "result": response.json()}],
            })
            self.assertEqual(saved.status_code, 200, saved.text)
            history = (await client.get("/api/conversations")).json()["items"]
            self.assertEqual(len(history), 1)
            loaded = await client.get("/api/conversations/" + history[0]["id"])
            self.assertEqual(loaded.status_code, 200)
            self.assertEqual(loaded.json()["agent_id"], record["id"])
            config = (await client.get("/api/config")).json()
            self.assertEqual(config["default_agent"], "customer-review")
            self.assertNotIn(record["id"], [agent["id"] for agent in config["agents"]])

    async def test_created_agent_turns_are_budgeted_on_the_model_saved_with_the_record(self):
        record = await self.ready()
        self.assertEqual(set(record["agent"]) & {"model", "template_id"}, set())
        limits = {"test-model": {"requests_per_minute": 1, "tokens_per_minute": 100000}}
        body = {"agent_id": record["id"], "input": "Fictional document."}
        async with self.make_client(replace(self.settings, model_limits=limits)) as client:
            first = await client.post("/api/reviews", json=body)
            second = await client.post("/api/reviews", json=body)
            self.assertEqual((first.status_code, second.status_code), (200, 429))
            self.assertEqual(second.json()["error"], "busy")
            self.assertTrue(1 <= int(second.headers["Retry-After"]) <= 60)
            self.assertEqual(self.gateway.review.await_count, 1)
            self.store.rows[record["id"]]["model"] = "other-model"
            third = await client.post("/api/reviews", json=body)
            self.assertEqual(third.status_code, 200)
            self.assertEqual(self.gateway.review.await_count, 2)

    async def test_not_ready_hidden_foreign_or_forged_agents_cannot_be_invoked(self):
        record = await self.ready()
        for changes in ({"status": "creating"}, {"project": "foreign"},
                        {"runtime_name": "customer-review-coordinator"}, {"kind": "review"}):
            original = deepcopy(self.store.rows[record["id"]])
            self.store.rows[record["id"]].update(changes)
            with self.subTest(changes=changes):
                response = await self.client.post("/api/reviews", json={"agent_id": record["id"], "input": "Test only."})
                self.assertEqual(response.status_code, 400)
            self.store.rows[record["id"]] = original
        hidden = await self.client.post("/api/reviews", json={"agent_id": "case-review", "input": "Fictional case."})
        self.assertEqual(hidden.status_code, 400)
        self.gateway.review.assert_not_awaited()

    async def test_config_survives_created_agent_storage_outage_but_operations_report_it(self):
        self.store.list_created_agents = AsyncMock(side_effect=CosmosHttpResponseError(status_code=503))
        self.assertEqual((await self.client.get("/api/config")).status_code, 200)
        response = await self.client.get("/api/agents")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"], "agents_unavailable")

    async def test_cosmos_errors_keep_their_status_and_code(self):
        created = await self.ready()
        for failure, status, code in [(404, 404, "agent_not_found"), (409, 409, "agent_changed"), (412, 409, "agent_changed"),
                                      (500, 503, "agents_unavailable")]:
            with self.subTest(failure=failure):
                self.store.get = AsyncMock(side_effect=CosmosHttpResponseError(status_code=failure))
                response = await self.client.get("/api/agents/" + created["id"])
                self.assertEqual((response.status_code, response.json()["error"]), (status, code))

    async def test_no_remote_mutation_when_initial_record_save_fails(self):
        self.store.create = AsyncMock(side_effect=CosmosHttpResponseError(status_code=503))
        response = await self.create()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.publisher.calls, [])

    async def test_lookup_catalogs_report_only_fixed_simulated_lookup_tools(self):
        expected = {
            "workflow-coordinator": {"lookup_demo_request", "lookup_demo_service"},
            "medical-bill-reviewer": {"lookup_plan_benefits", "lookup_usual_price"},
        }
        for template_id, tools in expected.items():
            with self.subTest(template_id=template_id):
                self.publisher.done.clear()
                self.body.update(idempotency_key=str(uuid4()), template_id=template_id)
                record = await self.ready()
                self.assertEqual(set(record["agent"]["tools"]), tools)
                self.assertEqual(set(record["agent"]["tools"].values()), {record["runtime_name"]})

    async def test_published_guidance_and_model_do_not_drift_when_templates_change(self):
        record = await self.ready()
        changed = deepcopy(TEMPLATES["document-analyst"])
        changed.update(description="A later template revision", tools=[{"name": "unpublished_tool"}])
        with patch.dict(TEMPLATES, {"document-analyst": changed}):
            loaded = (await self.client.get("/api/agents/" + record["id"])).json()
            self.assertEqual(loaded["agent"], record["agent"])
            self.assertEqual(loaded["model"], "test-model")
        with patch.dict(TEMPLATES, {}, clear=True):
            loaded = await self.client.get("/api/agents/" + record["id"])
            self.assertEqual(loaded.status_code, 200)
            self.assertEqual(loaded.json()["agent"], record["agent"])

    async def test_each_template_gets_the_model_for_its_kind_of_work(self):
        settings = Settings(
            "private", ENDPOINT, ("lab.test",), (ORIGIN,),
            creation=CreationSettings(True, "test-model", KEY_HASH, max_agents=5,
                                      models={"extraction": "fast-model", "tool_calling": "tool-model"}),
            unfinished_agents=True,
        )
        await self.client.aclose()
        self.client = self.make_client(settings)
        config = (await self.client.get("/api/config")).json()["agent_creation"]
        self.assertEqual(config["model"], "test-model")
        self.assertEqual(config["models"], {
            "reasoning": "test-model", "extraction": "fast-model", "tool_calling": "tool-model",
        })
        templates = {item["id"]: item for item in (await self.client.get("/api/agent-templates")).json()["templates"]}
        expected = {
            "document-intake": "fast-model", "workflow-coordinator": "tool-model", "criteria-checker": "test-model",
            "medical-bill-reviewer": "test-model", "insurance-preapproval-helper": "test-model",
        }
        for template_id, model in expected.items():
            with self.subTest(template_id=template_id):
                self.publisher.done.clear()
                self.body.update(idempotency_key=str(uuid4()), template_id=template_id)
                record = await self.ready()
                self.assertEqual(record["model"], model)
                self.assertEqual(record["model_profile"], templates[template_id]["model_profile"])
                self.assertEqual(self.publisher.calls[-1][1]["model"], model)

    async def test_disabled_creation_does_not_advertise_models(self):
        disabled = Settings("private", ENDPOINT, ("lab.test",), (ORIGIN,),
                            creation=CreationSettings(False, "test-model", KEY_HASH, models={"extraction": "fast-model"}))
        async with self.make_client(disabled) as client:
            config = (await client.get("/api/config")).json()["agent_creation"]
        self.assertIsNone(config["model"])
        self.assertIsNone(config["models"])

    async def test_api_query_cannot_turn_a_create_request_into_deletion(self):
        record = await self.ready()
        response = await self.client.post("/api/agents?identifier=" + record["id"],
                                          json=self.body, headers={**self.operator, "If-Match": record["_etag"]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ready")
        self.assertEqual(len(self.publisher.calls), 1)

    async def test_stage_save_failure_prevents_next_publisher_step(self):
        controller = AgentCreations(self.settings, self.store, self.publisher)
        created = await self.ready()
        document = await self.store.get(created["id"])
        self.store.replace = AsyncMock(side_effect=CosmosHttpResponseError(status_code=412))
        await controller.operation_slot.acquire()
        await controller.execute(document, "create")
        self.assertEqual(document["status"], "ready")
        self.assertFalse(controller.operation_slot.locked())


class CreationSettingsTests(unittest.TestCase):
    def test_opt_in_requires_private_mode_model_and_verifier(self):
        for settings, mode in (
            (CreationSettings(True, "model", KEY_HASH), "preview"),
            (CreationSettings(True, "", KEY_HASH), "private"),
            (CreationSettings(True, "model", ""), "private"),
            (CreationSettings(False, max_agents=0), "private"),
            (CreationSettings(False, timeout_seconds=901), "private"),
            (CreationSettings(False, key_sha256="not-a-hash"), "private"),
            (CreationSettings(True, "model", KEY_HASH, models={"creative": "model"}), "private"),
            (CreationSettings(True, "model", KEY_HASH, models={"reasoning": "not a deployment"}), "private"),
            (CreationSettings(True, "model", KEY_HASH, models={"reasoning": 7}), "private"),
            (CreationSettings(True, "model", KEY_HASH, models=["reasoning"]), "private"),
            (CreationSettings(True, "", KEY_HASH, models={"reasoning": "model"}), "private"),
        ):
            with self.subTest(settings=settings, mode=mode), self.assertRaises(ValueError):
                settings.validate(mode)

    def test_model_profiles_are_read_from_json_and_fall_back_to_the_default(self):
        environment = {
            "WORKBENCH_AGENT_CREATION_ENABLED": "true", "WORKBENCH_AGENT_CREATION_MODEL": "default-model",
            "WORKBENCH_CREATION_KEY_SHA256": KEY_HASH,
            "WORKBENCH_AGENT_CREATION_MODELS": '{"reasoning": "reasoning-model"}',
        }
        with patch.dict("os.environ", environment):
            settings = CreationSettings.from_env()
        settings.validate("private")
        self.assertEqual(settings.model_for("reasoning"), "reasoning-model")
        self.assertEqual(settings.model_for("extraction"), "default-model")
        with patch.dict("os.environ", {**environment, "WORKBENCH_AGENT_CREATION_MODELS": ""}):
            self.assertEqual(CreationSettings.from_env().models, {})
        for value in ("not json", "[1"):
            with patch.dict("os.environ", {**environment, "WORKBENCH_AGENT_CREATION_MODELS": value}):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    CreationSettings.from_env()

    def test_default_is_disabled_and_environment_enablement_is_explicit(self):
        CreationSettings().validate("preview")
        with patch.dict("os.environ", {"WORKBENCH_AGENT_CREATION_ENABLED": "perhaps"}):
            with self.assertRaises(ValueError):
                CreationSettings.from_env()

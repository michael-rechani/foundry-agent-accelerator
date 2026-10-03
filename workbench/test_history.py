import asyncio
import hashlib
import json
import re
import unittest
from copy import deepcopy
from unittest.mock import AsyncMock, patch
from uuid import UUID

from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from azure.cosmos.exceptions import CosmosHttpResponseError

from agent_publisher import resource_name
from agent_templates import TEMPLATES
from app import Settings, create_app
from history import CosmosHistory
from log_capture import CapturedLabLogs

CREATED_AGENT_FIELDS = {
    "id", "kind", "project", "name", "template_id", "instructions", "runtime_name", "version", "status", "stage",
    "created_at", "updated_at", "_etag", "error", "events", "operation", "model", "runtime_hash", "model_profile",
    "template",
}


class HistoryTests(CapturedLabLogs, unittest.TestCase):
    def setUp(self):
        self.store = AsyncMock()
        self.store.list_created_agents.return_value = []
        self.settings = Settings("private", "https://example.services.ai.azure.com/api/projects/test", ("testserver",), ("https://testserver",))
        self.client = TestClient(create_app(self.settings, AsyncMock(), self.store))
        self.headers = {"X-Workbench-Request": "1", "Origin": "https://testserver"}
        self.identifier = "a" * 8 + "-" + "b" * 4 + "-" + "c" * 4 + "-" + "d" * 4 + "-" + "e" * 12
        self.body = {"agent_id": "customer-review", "turns": [{"question": "Review APP-1", "result": {
            "request_id": "request", "agent": "customer-review-coordinator", "text": "Missing budget",
            "elapsed_ms": 1000, "receipts": []}}]}
        self.document = {**self.body, "id": self.identifier, "_etag": '"one"', "title": "Review APP-1", "updated_at": "now"}
        self.store.get.return_value = self.document
        self.store.create.side_effect = lambda document: {**document, "_etag": '"one"'}
        self.store.replace.side_effect = lambda document, etag: {**document, "_etag": '"two"'}

    def test_save_uses_shared_partition_and_retention(self):
        response = self.client.post("/api/conversations", json=self.body, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        saved = self.store.create.call_args.args[0]
        self.assertEqual(saved["workspace"], "shared")
        self.assertEqual(saved["ttl"], 2592000)
        self.assertEqual(saved["title"], "Review APP-1")

    def test_saved_replies_may_include_bounded_token_usage(self):
        usage = {"input_tokens": 40, "output_tokens": 10, "total_tokens": 50, "cached_tokens": None, "reasoning_tokens": 0}
        self.body["turns"][0]["result"]["usage"] = usage
        response = self.client.post("/api/conversations", json=self.body, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.store.create.call_args.args[0]["turns"][0]["result"]["usage"], usage)
        self.store.create.reset_mock()
        for bad in ({**usage, "input_tokens": -1}, {**usage, "cost": 1}, {**usage, "total_tokens": "50"}):
            self.body["turns"][0]["result"]["usage"] = bad
            response = self.client.post("/api/conversations", json=self.body, headers=self.headers)
            self.assertEqual(response.status_code, 400, bad)
        self.store.create.assert_not_called()

    def test_stored_receipts_cannot_claim_live_verification(self):
        receipt = {"tool": "invented", "call_id": "one", "verified": True,
                   "agent": "unconfigured-agent", "output": "Synthetic receipt"}
        self.body["turns"][0]["result"]["receipts"] = [receipt]
        response = self.client.post("/api/conversations", json=self.body, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.store.create.call_args.args[0]["turns"][0]["result"]["receipts"][0]["verified"])
        response = self.client.get(f"/api/conversations/{self.identifier}", headers=self.headers)
        self.assertFalse(response.json()["turns"][0]["result"]["receipts"][0]["verified"])
        self.assertTrue(receipt["verified"])

    def test_reopen_update_and_delete_require_current_etag(self):
        path = f"/api/conversations/{self.identifier}"
        self.assertEqual(self.client.get(path, headers=self.headers).json()["turns"], self.body["turns"])
        self.assertEqual(self.client.put(path, json=self.body, headers=self.headers).status_code, 409)
        headers = {**self.headers, "If-Match": '"one"'}
        self.assertEqual(self.client.put(path, json=self.body, headers=headers).json()["_etag"], '"two"')
        self.assertEqual(self.client.delete(path, headers=headers).status_code, 200)

    def test_catalog_and_pagination_are_server_scoped(self):
        self.store.list.return_value = {"items": [], "cursor": "next"}
        response = self.client.get("/api/conversations?cursor=first", headers=self.headers)
        self.assertEqual(response.json()["cursor"], "next")
        self.assertEqual(list(self.store.list.call_args.args[0]), ["customer-review"])

    def test_cross_origin_invalid_and_oversize_are_rejected(self):
        self.assertEqual(self.client.post("/api/conversations", json=self.body).status_code, 403)
        self.assertEqual(self.client.post("/api/conversations", json={**self.body, "agent_id": "case-review"}, headers=self.headers).status_code, 400)
        oversize = self.client.post("/api/conversations", content="x" * 524289, headers={**self.headers, "Content-Type": "application/json"})
        self.assertEqual((oversize.status_code, oversize.json()["error"]), (413, "conversation_too_large"))
        self.store.create.assert_not_called()

    def test_json_content_type_matches_the_other_routers(self):
        content = json.dumps(self.body)
        for value in ("Application/JSON ; charset=utf-8", "application/json"):
            with self.subTest(value=value):
                response = self.client.post("/api/conversations", content=content, headers={**self.headers, "Content-Type": value})
                self.assertEqual(response.status_code, 200, response.text)
        for value in ("text/plain", "application/jsonp"):
            with self.subTest(value=value):
                response = self.client.post("/api/conversations", content=content, headers={**self.headers, "Content-Type": value})
                self.assertEqual((response.status_code, response.json()["error"]), (415, "json_required"))

    def test_reads_and_deletes_without_origin_need_the_lab_header(self):
        self.store.list.return_value = {"items": [], "cursor": None}
        path = f"/api/conversations/{self.identifier}"
        lab_header = {"X-Workbench-Request": "1", "If-Match": '"one"'}
        for method, target in (("get", "/api/conversations"), ("get", path), ("delete", path)):
            request = getattr(self.client, method)
            self.assertEqual(request(target, headers=lab_header).status_code, 200, (method, target))
            self.assertEqual(request(target).status_code, 403, (method, target))
            self.assertEqual(request(target, headers={**lab_header, "Origin": "https://evil.example"}).status_code, 403)

    def test_cosmos_errors_keep_their_status_and_code(self):
        for failure, status, code in [(404, 404, "conversation_not_found"), (412, 409, "conversation_changed"),
                                      (409, 503, "history_unavailable"), (500, 503, "history_unavailable")]:
            with self.subTest(failure=failure):
                self.store.get.side_effect = CosmosHttpResponseError(status_code=failure)
                response = self.client.get(f"/api/conversations/{self.identifier}", headers=self.headers)
                self.assertEqual((response.status_code, response.json()["error"]), (status, code))

    def test_errors_are_sanitized_and_conflicts_preserved(self):
        self.store.get.side_effect = CosmosHttpResponseError(status_code=412, message="secret")
        response = self.client.get(f"/api/conversations/{self.identifier}", headers=self.headers)
        self.assertEqual(response.status_code, 409)
        self.assertNotIn("secret", response.text)
        self.store.get.side_effect = RuntimeError("secret")
        with self.assertLogs("uvicorn.error", level="ERROR") as logs:
            response = self.client.get(f"/api/conversations/{self.identifier}", headers=self.headers)
        self.assertEqual(response.status_code, 503)
        event = json.loads(logs.records[-1].getMessage())
        self.assertEqual(event["dependency"], "cosmos")
        self.assertEqual(event["error_type"], "RuntimeError")
        self.assertEqual(event["request_id"], response.headers["X-Correlation-ID"])
        self.assertEqual(event["route"], "/api/conversations/{identifier}")
        self.assertNotIn(self.identifier, " ".join(logs.output))
        self.assertNotIn("secret", " ".join(logs.output))

    def test_stalled_history_upload_is_rejected_without_saving(self):
        async def stalled(request):
            await asyncio.Event().wait()
            yield b""

        timeout = asyncio.timeout
        with patch("starlette.requests.Request.stream", stalled), patch(
            "request_guard.asyncio.timeout", side_effect=lambda seconds: timeout(0.01 if seconds == 5 else seconds)
        ):
            response = self.client.post("/api/conversations", json=self.body, headers=self.headers)
        self.assertEqual(response.status_code, 408)
        self.assertEqual(response.json()["error"], "request_timeout")
        self.store.create.assert_not_called()

    def test_history_rate_limit_blocks_store_and_expires(self):
        self.store.list.return_value = {"items": [], "cursor": None}
        with patch("request_guard.time.monotonic", return_value=100):
            for _ in range(60):
                self.assertEqual(self.client.get("/api/conversations", headers=self.headers).status_code, 200)
            response = self.client.get("/api/conversations", headers=self.headers)
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.headers["Retry-After"], "60")
        self.assertEqual(self.store.list.await_count, 60)
        with patch("request_guard.time.monotonic", return_value=161):
            self.assertEqual(self.client.get("/api/conversations", headers=self.headers).status_code, 200)

    def test_history_deadline_cancels_store_and_releases_capacity(self):
        cancelled = []

        async def stalled(*args):
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.append(True)

        timeout = asyncio.timeout
        self.store.list.side_effect = stalled
        with patch("history.asyncio.timeout", side_effect=lambda seconds: timeout(0.01)):
            for _ in range(5):
                response = self.client.get("/api/conversations", headers=self.headers)
                self.assertEqual(response.status_code, 504)
                self.assertEqual(response.json()["error"], "history_timeout")
        self.assertEqual(len(cancelled), 5)

    def test_fifth_concurrent_history_request_is_rejected(self):
        async def scenario():
            release = asyncio.Event()
            full = asyncio.Event()
            active = 0

            async def stalled(*args):
                nonlocal active
                active += 1
                if active == 4:
                    full.set()
                await release.wait()
                return {"items": [], "cursor": None}

            self.store.list.side_effect = stalled
            async with AsyncClient(transport=ASGITransport(app=create_app(self.settings, AsyncMock(), self.store)),
                                   base_url="https://testserver") as client:
                tasks = [asyncio.create_task(client.get("/api/conversations", headers=self.headers)) for _ in range(4)]
                try:
                    await asyncio.wait_for(full.wait(), timeout=2)
                    response = await client.get("/api/conversations", headers=self.headers)
                    self.assertEqual(response.status_code, 429)
                    self.assertEqual(self.store.list.await_count, 4)
                finally:
                    release.set()
                    await asyncio.gather(*tasks)
                self.assertEqual((await client.get("/api/conversations", headers=self.headers)).status_code, 200)

        asyncio.run(scenario())


class FakeContainer:
    """Applies the created-agent query's filter, ordering, and field list as Cosmos does, and refuses any other query."""

    def __init__(self, rows):
        self.rows = {row["id"]: row for row in rows}
        self.queries = []
        self.revision = 0

    def query_items(self, query, parameters=None, partition_key=None, max_item_count=None):
        self.queries.append((query, parameters))
        match = re.fullmatch(r"SELECT (.+) FROM c WHERE (.+) ORDER BY c\.updated_at DESC", query)
        assert match, query
        fields = [field.strip() for field in match[1].split(",")]
        assert all(re.fullmatch(r"c\.[a-z_]+", field) for field in fields), match[1]
        values = {parameter["name"]: parameter["value"] for parameter in parameters or []}
        conditions = {
            "c.kind = 'created-agent'": lambda row: row.get("kind") == "created-agent",
            "c.project = @project": lambda row: row.get("project") == values["@project"],
        }
        assert partition_key == "shared"
        tests = [conditions[condition] for condition in match[2].split(" AND ")]
        rows = sorted((row for row in self.rows.values() if all(test(row) for test in tests)),
                      key=lambda row: row["updated_at"], reverse=True)

        async def results():
            for row in rows:
                yield {field[2:]: deepcopy(row[field[2:]]) for field in fields if field[2:] in row}

        return results()

    async def read_item(self, identifier, partition_key):
        if identifier not in self.rows:
            raise CosmosHttpResponseError(status_code=404)
        return deepcopy(self.rows[identifier])

    async def create_item(self, document):
        self.revision += 1
        self.rows[document["id"]] = {**deepcopy(document), "_etag": f'"{self.revision}"'}
        return deepcopy(self.rows[document["id"]])

    async def replace_item(self, identifier, document, etag, match_condition):
        if (await self.read_item(identifier, "shared"))["_etag"] != etag:
            raise CosmosHttpResponseError(status_code=412)
        return await self.create_item(document)


ENDPOINT = "https://example.services.ai.azure.com/api/projects/test"
MINE = hashlib.sha256(ENDPOINT.encode()).hexdigest()
THEIRS = hashlib.sha256(b"https://other.services.ai.azure.com/api/projects/other").hexdigest()


def created_agent(project, number, updated_at, *, kind="created-agent", status="ready"):
    identifier = f"created-{UUID(int=number)}"
    template = {key: deepcopy(TEMPLATES["document-analyst"][key]) for key in (
        "id", "label", "description", "input", "output", "limits", "delegation", "sample_input", "tools")}
    return {
        "id": identifier, "kind": kind, "workspace": "shared", "project": project, "template_id": template["id"],
        "name": f"Fictional helper {number}", "instructions": "Analyze only fictional supplied text.",
        "setup_hash": "a" * 64, "runtime_hash": "b" * 64, "runtime_name": resource_name(identifier),
        "model": "test-model", "model_profile": {"id": "standard"}, "template": template, "version": "1",
        "publication_started": True, "status": status, "stage": status, "operation": "create",
        "created_at": updated_at, "updated_at": updated_at, "error": None, "events": [], "ttl": -1,
        "_etag": f'"{number}"', "_ts": 1,
    }


class CreatedAgentQueryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.rows = [
            created_agent(MINE, 1, "2026-01-01T00:00:00+00:00"),
            created_agent(THEIRS, 2, "2026-01-02T00:00:00+00:00"),
            created_agent(MINE, 3, "2026-01-03T00:00:00+00:00", status="failed"),
            created_agent(THEIRS, 4, "2026-01-04T00:00:00+00:00"),
            created_agent(MINE, 5, "2026-01-05T00:00:00+00:00", kind="deleted-agent", status="deleted"),
        ]
        self.container = FakeContainer(self.rows)
        self.store = CosmosHistory.__new__(CosmosHistory)
        self.store.container = self.container
        self.headers = {"X-Workbench-Request": "1", "Origin": "https://testserver"}

    def make_client(self):
        settings = Settings("private", ENDPOINT, ("testserver",), ("https://testserver",))
        return AsyncClient(transport=ASGITransport(app=create_app(settings, AsyncMock(), self.store, AsyncMock())),
                           base_url="https://testserver")

    async def test_each_project_gets_only_its_own_agents_newest_first(self):
        mine = await self.store.list_created_agents(MINE)
        self.assertEqual([item["id"] for item in mine], [self.rows[2]["id"], self.rows[0]["id"]])
        self.assertEqual({item["project"] for item in mine}, {MINE})
        theirs = await self.store.list_created_agents(THEIRS)
        self.assertEqual([item["id"] for item in theirs], [self.rows[3]["id"], self.rows[1]["id"]])
        self.assertEqual(await self.store.list_created_agents("unknown"), [])

    async def test_project_is_a_query_parameter_and_only_needed_fields_are_selected(self):
        items = await self.store.list_created_agents(MINE)
        query, parameters = self.container.queries[0]
        self.assertEqual(parameters, [{"name": "@project", "value": MINE}])
        self.assertIn("c.project = @project", query)
        self.assertNotIn(MINE, query)
        self.assertNotIn("*", query)
        self.assertEqual(set(items[0]), CREATED_AGENT_FIELDS)
        for unused in ("setup_hash", "workspace", "publication_started", "ttl", "_ts"):
            self.assertNotIn(unused, items[0])

    async def test_agents_api_lists_only_the_callers_agents_from_the_selected_fields(self):
        async with self.make_client() as client:
            response = await client.get("/api/agents", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual({item["id"]: item["status"] for item in response.json()["items"]},
                         {self.rows[0]["id"]: "ready", self.rows[2]["id"]: "failed"})
        self.assertEqual(len(self.container.queries), 1)

    async def test_conversation_of_a_republished_agent_updates_once_it_is_ready_again(self):
        agent = self.rows[0]
        body = {"agent_id": agent["id"], "turns": [{"question": "Summarize APP-1", "result": {
            "request_id": "request", "agent": agent["runtime_name"], "text": "Missing budget",
            "elapsed_ms": 1000, "receipts": []}}]}
        async with self.make_client() as client:
            saved = (await client.post("/api/conversations", json=body, headers=self.headers)).json()
            path = f"/api/conversations/{saved['id']}"
            update = {**self.headers, "If-Match": saved["_etag"]}
            body["turns"].append({**body["turns"][0], "question": "And APP-2?"})

            self.container.rows[agent["id"]].update(status="creating", operation="resume", version=None)
            self.assertEqual((await client.put(path, json=body, headers=update)).status_code, 404)

            self.container.rows[agent["id"]].update(status="ready", version="2")
            response = await client.put(path, json=body, headers=update)
            self.assertEqual(response.status_code, 200)
            self.assertNotEqual(response.json()["_etag"], saved["_etag"])
            self.assertEqual(len((await client.get(path, headers=self.headers)).json()["turns"]), 2)


if __name__ == "__main__":
    unittest.main()
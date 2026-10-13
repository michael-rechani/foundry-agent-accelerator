import json
import asyncio
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, patch

from azure.cosmos.exceptions import CosmosHttpResponseError
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from reviews import ReviewInput, review_prompt, validate_result
from app import Settings, create_app, execution_receipts
from log_capture import CapturedLabLogs
from request_guard import RateGate
from review_runs import RECOVERY_GRACE_SECONDS, ReviewRuns


class ReviewContractTests(unittest.TestCase):
    def setUp(self):
        self.review = ReviewInput(title="Synthetic application", agent_id="customer-review",
                                  criteria=["Budget supplied"], evidence=[{"id": "SRC-1", "text": "Budget: $100."}])
        self.result = {"summary": "Budget supplied", "findings": [{"criterion_id": "CRIT-1",
                       "assessment": "supported", "explanation": "A budget is stated.",
                       "citations": [{"source_id": "SRC-1", "quote": "Budget: $100."}]}], "questions": []}

    def test_exact_citation_and_full_coverage(self):
        self.assertEqual(validate_result(json.dumps(self.result), self.review), self.result)
        self.assertIn("appropriate configured specialist", review_prompt(self.review))

    def test_resume_prompt_bounds_questions_to_unresolved_criteria(self):
        review = ReviewInput(
            title="Synthetic rollout verification", agent_id="customer-review",
            criteria=["The workshop must last twelve weeks.", "An explicit total budget in USD must be supplied."],
            evidence=[
                {"id": "SRC-1", "text": "The proposed workshop lasts twelve weeks. No total budget has been supplied."},
                {"id": "SRC-2", "text": "The total workshop budget is USD 12000."},
            ],
        )
        prompt = review_prompt(review)
        instructions, material = prompt.split("\nSupplied material:\n", 1)
        self.assertIn("only to resolve a gap or conflict in a supplied criterion", instructions)
        self.assertIn("do not add documentation, verification, or approval requirements", instructions)
        self.assertIn("including later clarifications", instructions)
        self.assertIn("If every finding is supported, return an empty questions array", instructions)
        self.assertIn("A human review notice is not a request for additional evidence", instructions)
        self.assertEqual(json.loads(material)["evidence"], review.model_dump()["evidence"])
        self.assertEqual([criterion["text"] for criterion in json.loads(material)["criteria"]], review.criteria)

    def test_validation_does_not_discard_agent_questions(self):
        self.result["questions"] = ["Can the supplied budget be verified?"]
        self.assertEqual(validate_result(json.dumps(self.result), self.review), self.result)

    def test_fabricated_source_or_quote_rejected(self):
        for citation in [{"source_id": "SRC-2", "quote": "Budget: $100."}, {"source_id": "SRC-1", "quote": "$500"}]:
            self.result["findings"][0]["citations"] = [citation]
            with self.assertRaises(ValueError):
                validate_result(json.dumps(self.result), self.review)

    def test_missing_duplicate_and_unknown_criteria_rejected(self):
        for findings in [[], self.result["findings"] * 2, [{**self.result["findings"][0], "criterion_id": "CRIT-2"}]]:
            with self.assertRaises(ValueError):
                validate_result(json.dumps({**self.result, "findings": findings}), self.review)

    def test_only_gaps_allow_no_citation(self):
        self.result["findings"][0]["citations"] = []
        with self.assertRaises(ValueError):
            validate_result(json.dumps(self.result), self.review)
        self.result["findings"][0]["assessment"] = "gap"
        validate_result(json.dumps(self.result), self.review)

    def test_input_bounds_and_unique_sources(self):
        for changes in [{"criteria": [" "]}, {"criteria": ["x" * 1001]},
                        {"evidence": [{"id": "SRC-1", "text": "one"}, {"id": "SRC-1", "text": "two"}]}]:
            with self.assertRaises(ValueError):
                ReviewInput.model_validate({**self.review.model_dump(), **changes})

    def test_model_cannot_set_execution_or_workflow_flags(self):
        with self.assertRaises(ValueError):
            validate_result(json.dumps({**self.result, "verified": True}), self.review)

    def test_proposal_demo_reuses_review_contract_and_exact_citations(self):
        path = Path(__file__).resolve().parent.parent / "docs" / "demo-inputs" / "requirements-review.json"
        review = ReviewInput.model_validate_json(path.read_text(encoding="utf-8"))
        result = {
            "summary": "CSV export is described; retention conflicts and SSO evidence needs human review.",
            "findings": [
                {"criterion_id": "CRIT-1", "assessment": "supported",
                 "explanation": "The supplied product statement describes CSV export, not a live test.",
                 "citations": [{"source_id": "SRC-1", "quote": "exports service-request records as CSV"}]},
                {"criterion_id": "CRIT-2", "assessment": "conflict",
                 "explanation": "The supplied retention statements conflict.",
                 "citations": [{"source_id": "SRC-1", "quote": "retains audit records for seven years"},
                               {"source_id": "SRC-2", "quote": "audit records are deleted after thirty days"}]},
                {"criterion_id": "CRIT-3", "assessment": "gap",
                 "explanation": "Enterprise-ready is not protocol evidence; absence is not noncompliance.",
                 "citations": []},
            ],
            "questions": ["Which retention statement is authoritative?", "What SSO protocols are documented?"],
        }
        self.assertEqual(validate_result(json.dumps(result), review), result)
        self.assertEqual(review.agent_id, "customer-review")
        prompt = review_prompt(review)
        self.assertIn("CRIT-3", prompt)
        self.assertIn("Brochure:", prompt)
        result["findings"][2]["citations"] = [{"source_id": "SRC-3", "quote": "Supports SAML and OIDC."}]
        with self.assertRaisesRegex(ValueError, "Citation does not match evidence"):
            validate_result(json.dumps(result), review)


class ReviewStore:
    def __init__(self):
        self.documents = {}
        self.version = 0

    async def create(self, document):
        self.version += 1
        saved = {**deepcopy(document), "_etag": str(self.version)}
        self.documents[saved["id"]] = saved
        return deepcopy(saved)

    async def get(self, identifier):
        if identifier not in self.documents:
            raise CosmosHttpResponseError(status_code=404)
        return deepcopy(self.documents[identifier])

    async def replace(self, document, etag):
        if self.documents[document["id"]]["_etag"] != etag:
            raise CosmosHttpResponseError(status_code=412)
        return await self.create(document)

    async def list_reviews(self, agents, cursor):
        return {"items": [{key: document[key] for key in ("id", "title", "agent_id", "updated_at", "status", "recovery_after")
                           if key in document}
                          for document in self.documents.values() if document["agent_id"] in agents], "cursor": None}


class ReviewLifecycleTests(CapturedLabLogs, unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.store = ReviewStore()
        self.gateway = AsyncMock()
        self.settings = Settings("private", "https://example.services.ai.azure.com/api/projects/test", ("testserver",), ("https://testserver",))
        self.headers = {"X-Workbench-Request": "1", "Origin": "https://testserver"}
        self.client = AsyncClient(transport=ASGITransport(app=create_app(self.settings, self.gateway, self.store)), base_url="https://testserver", headers=self.headers)
        self.body = {"title": "Synthetic review", "agent_id": "customer-review", "criteria": ["Budget supplied"],
                     "evidence": [{"id": "SRC-1", "text": "No budget supplied."}]}
        self.result = {"summary": "Budget missing", "findings": [{"criterion_id": "CRIT-1", "assessment": "gap", "explanation": "Missing budget", "citations": []}], "questions": ["What is the budget?"]}
        self.output = [{"type": "function_call", "call_id": "call-1", "name": "inspect_application"},
                       {"type": "function_call_output", "call_id": "call-1", "output": json.dumps({"status": "succeeded", "agent": "application-review-agent", "output": "Budget missing"})}]

    async def asyncTearDown(self):
        await self.client.aclose()

    async def draft(self):
        response = await self.client.post("/api/review-runs", json=self.body)
        self.assertEqual(response.status_code, 201, response.text)
        return await self.store.get(response.json()["id"])

    def controller(self):
        return ReviewRuns(self.settings, {"customer-review": {"agent": "customer-review-coordinator", "tools": {"inspect_application": "application-review-agent"}}},
                          self.store, self.gateway, execution_receipts, RateGate(20, 4))

    async def run_direct(self, document):
        controller = self.controller()
        document["status"] = "running"
        document["runs"].append({"id": "attempt", "events": [], "input": deepcopy(self.body)})
        await controller.model_gate.slots.acquire()
        await controller.execute(document)
        return await self.store.get(document["id"])

    async def interrupted_review(self, status="running", *, legacy=False):
        document = await self.draft()
        document.update(status=status, updated_at="2026-01-01T00:00:00+00:00")
        document["runs"] = [{"id": "lost-attempt", "started_at": document["updated_at"],
                             "events": [{"name": "review_started", "at": document["updated_at"]}],
                             "input": deepcopy(self.body)}]
        if not legacy:
            document["recovery_after"] = document["updated_at"]
        return await self.store.replace(document, document["_etag"])

    async def finish_tasks(self):
        for task in list(asyncio.all_tasks()):
            if task.get_coro().__qualname__ == "ReviewRuns.execute":
                await task

    async def resume(self, document, *, client=None, body=None):
        return await (client or self.client).post(
            f'/api/review-runs/{document["id"]}/resume',
            json={"confirm_cost": True} if body is None else body,
            headers={"If-Match": document["_etag"]},
        )

    async def test_clarification_resume_preserves_previous_evidence(self):
        document = await self.draft()
        self.gateway.review.return_value = ("completed", json.dumps(self.result), self.output)
        saved = await self.run_direct(document)
        self.assertEqual(saved["status"], "waiting_input")
        response = await self.client.post(f'/api/review-runs/{document["id"]}/evidence',
                                          json={"id": "SRC-2", "text": "Budget: $100."}, headers={"If-Match": saved["_etag"]})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["status"], "draft")
        self.assertEqual(len(response.json()["evidence"]), 2)
        self.assertEqual(len(response.json()["runs"][0]["input"]["evidence"]), 1)

    async def test_json_content_type_matches_the_other_routers(self):
        content = json.dumps(self.body)
        response = await self.client.post("/api/review-runs", content=content,
                                          headers={"Content-Type": "Application/JSON ; charset=utf-8"})
        self.assertEqual(response.status_code, 201, response.text)
        for value in ("text/plain", "application/jsonp"):
            with self.subTest(value=value):
                response = await self.client.post("/api/review-runs", content=content, headers={"Content-Type": value})
                self.assertEqual((response.status_code, response.json()["error"]), (415, "json_required"))
        self.assertEqual(len(self.store.documents), 1)

    async def test_oversized_review_body_is_rejected_before_storage(self):
        response = await self.client.post("/api/review-runs", content=b"{" + b" " * 65536 + b"}",
                                          headers={"Content-Type": "application/json"})
        self.assertEqual(response.status_code, 413, response.text)
        self.assertEqual(response.json()["error"], "request_too_large")
        self.assertEqual(self.store.documents, {})

    async def test_slow_upload_is_not_reported_as_a_cosmos_timeout(self):
        async def stalled(request):
            await asyncio.Event().wait()
            yield b""

        timeout = asyncio.timeout
        with patch("starlette.requests.Request.stream", stalled), patch(
            "request_guard.asyncio.timeout", side_effect=lambda seconds: timeout(0.01 if seconds == 5 else seconds)
        ):
            response = await self.client.post("/api/review-runs", json=self.body)
        self.assertEqual(response.status_code, 408)
        self.assertEqual(response.json()["error"], "request_timeout")
        self.assertEqual(self.store.documents, {})
        self.gateway.review.assert_not_awaited()

    async def test_competing_starts_execute_only_once(self):
        document = await self.draft()
        entered, release = asyncio.Event(), asyncio.Event()
        async def response(*args):
            entered.set()
            await release.wait()
            return "completed", json.dumps({**self.result, "questions": []}), self.output
        self.gateway.review.side_effect = response
        path = f'/api/review-runs/{document["id"]}/execute'
        responses = await asyncio.gather(*(self.client.post(path, headers={"If-Match": document["_etag"]}) for _ in range(2)))
        self.assertEqual(sorted(response.status_code for response in responses), [202, 409])
        await asyncio.wait_for(entered.wait(), 2)
        inbox = await self.client.get('/api/review-runs')
        self.assertEqual(inbox.json()["items"][0]["status"], "running")
        release.set()
        for task in list(asyncio.all_tasks()):
            if task.get_coro().__qualname__ == "ReviewRuns.execute":
                await task
        self.assertEqual(self.gateway.review.await_count, 1)
        saved = await self.store.get(document["id"])
        self.assertEqual(saved["status"], "completed")

    async def test_invalid_result_and_unverified_delegation_fail_closed(self):
        for output, text in [(self.output, "not JSON"), ([], json.dumps(self.result))]:
            document = await self.draft()
            self.gateway.review.return_value = ("completed", text, output)
            saved = await self.run_direct(document)
            self.assertEqual(saved["status"], "failed")
            self.assertEqual(saved["runs"][0]["error"], "invalid_agent_result")

    async def test_timeout_is_persisted_without_retry(self):
        document = await self.draft()
        self.gateway.review.side_effect = TimeoutError()
        saved = await self.run_direct(document)
        self.assertEqual(saved["runs"][0]["error"], "agent_timeout")
        self.assertEqual(self.gateway.review.await_count, 1)

    async def test_lost_worker_is_interrupted_not_restarted(self):
        document = await self.interrupted_review()
        response = await self.client.get('/api/review-runs/' + document["id"])
        self.assertEqual(response.json()["status"], "interrupted")
        inbox = await self.client.get('/api/review-runs')
        self.assertEqual(inbox.json()["items"][0]["status"], "interrupted")
        self.assertEqual((await self.store.get(document["id"]))["status"], "running")
        self.gateway.review.assert_not_called()

    async def test_final_save_failure_never_claims_completion(self):
        document = await self.interrupted_review()
        self.gateway.review.return_value = ("completed", json.dumps(self.result), self.output)
        self.store.replace = AsyncMock(side_effect=RuntimeError("unavailable"))
        controller = self.controller()
        await controller.model_gate.slots.acquire()
        await controller.execute(document)
        response = await self.client.get('/api/review-runs/' + document["id"])
        self.assertEqual(response.json()["status"], "interrupted")

    async def test_restart_recovery_uses_saved_input_and_preserves_attempts(self):
        for status, legacy in [("running", False), ("running", True), ("interrupted", False)]:
            with self.subTest(status=status, legacy=legacy):
                document = await self.interrupted_review(status, legacy=legacy)
                original = deepcopy(document["runs"][0])
                document["evidence"] = [{"id": "SRC-1", "text": "Not the saved run input."}]
                document = await self.store.replace(document, document["_etag"])
                self.gateway.review.return_value = ("completed", json.dumps(self.result), self.output)
                response = await self.resume(document)
                self.assertEqual(response.status_code, 202, response.text)
                self.assertEqual(response.json()["status"], "running")
                await self.finish_tasks()
                saved = await self.store.get(document["id"])
                self.assertEqual(saved["status"], "waiting_input")
                self.assertEqual(len(saved["runs"]), 2)
                first, recovered = saved["runs"]
                self.assertEqual(first["input"], original["input"])
                self.assertEqual(first["started_at"], original["started_at"])
                self.assertEqual(first["events"][0], original["events"][0])
                self.assertEqual(first["error"], "execution_interrupted")
                self.assertEqual(first["events"][-1]["name"], "interrupted")
                self.assertEqual(recovered["input"], original["input"])
                self.assertEqual(recovered["resumed_from"], original["id"])
                self.assertNotEqual(recovered["id"], original["id"])
                self.assertEqual(recovered["events"][0]["name"], "review_recovery_requested")
                self.assertEqual(self.gateway.review.call_args.args[1], review_prompt(ReviewInput.model_validate(original["input"])))
                self.assertNotIn("error", recovered)
                self.assertEqual(recovered["result"], self.result)

    async def test_shutdown_interruption_can_be_recovered_by_new_worker(self):
        document = await self.interrupted_review()
        entered = asyncio.Event()

        async def blocked(*args):
            entered.set()
            await asyncio.Event().wait()

        self.gateway.review.side_effect = blocked
        controller = self.controller()
        await controller.model_gate.slots.acquire()
        controller.tasks[document["id"]] = asyncio.create_task(controller.execute(document))
        await asyncio.wait_for(entered.wait(), 2)
        await controller.close()
        saved = await self.store.get(document["id"])
        self.assertEqual(saved["status"], "interrupted")
        original = deepcopy(saved["runs"][0])
        self.gateway.review.side_effect = None
        self.gateway.review.return_value = ("completed", json.dumps(self.result), self.output)
        self.assertEqual((await self.resume(saved)).status_code, 202)
        await self.finish_tasks()
        recovered = await self.store.get(document["id"])
        self.assertEqual(recovered["runs"][0], original)
        self.assertEqual(recovered["status"], "waiting_input")
        self.assertFalse(controller.tasks)
        self.assertEqual(controller.model_gate.slots._value, 4)

    async def test_recovery_requires_exact_confirmation_and_current_etag(self):
        document = await self.interrupted_review()
        path = f'/api/review-runs/{document["id"]}/resume'
        for body in [{}, {"confirm_cost": False}, {"confirm_cost": 1}, {"confirm_cost": "true"},
                     {"confirm_cost": True, "input": self.body}]:
            response = await self.resume(document, body=body)
            self.assertEqual(response.status_code, 400, response.text)
            self.assertEqual(response.json()["error"], "recovery_confirmation_required")
        for headers in [{}, {"If-Match": "stale"}]:
            response = await self.client.post(path, json={"confirm_cost": True}, headers=headers)
            self.assertEqual(response.status_code, 409)
        self.assertEqual((await self.client.post(path, headers={"If-Match": document["_etag"]})).status_code, 415)
        self.assertEqual(await self.store.get(document["id"]), document)
        self.gateway.review.assert_not_called()

    async def test_recovery_rejects_other_states_missing_input_and_run_limit(self):
        for status in ["draft", "waiting_input", "completed", "failed"]:
            document = await self.interrupted_review(status)
            self.assertEqual((await self.resume(document)).status_code, 409)
        for runs in [[], None]:
            document = await self.interrupted_review()
            document["runs"] = runs if runs is not None else document["runs"] * 4
            document = await self.store.replace(document, document["_etag"])
            self.assertEqual((await self.resume(document)).status_code, 409)
        document = await self.interrupted_review()
        del document["runs"][0]["input"]
        document = await self.store.replace(document, document["_etag"])
        self.assertEqual((await self.resume(document)).status_code, 409)
        document = await self.interrupted_review()
        document["runs"][0]["input"]["agent_id"] = "case-review"
        document = await self.store.replace(document, document["_etag"])
        self.assertEqual((await self.resume(document)).status_code, 409)
        self.gateway.review.assert_not_called()

    async def test_persisted_deadline_protects_other_worker_and_legacy_records(self):
        now = datetime.now(timezone.utc)
        for legacy in [False, True]:
            document = await self.interrupted_review(legacy=legacy)
            document["updated_at"] = now.isoformat()
            if not legacy:
                document["recovery_after"] = (now + timedelta(seconds=30)).isoformat()
            document = await self.store.replace(document, document["_etag"])
            self.assertEqual((await self.resume(document)).status_code, 409)
            path = '/api/review-runs/' + document["id"]
            self.assertEqual((await self.client.get(path)).json()["status"], "running")
            inbox = (await self.client.get('/api/review-runs')).json()["items"]
            item = next(item for item in inbox if item["id"] == document["id"])
            self.assertEqual(item["status"], "running")
            self.assertNotIn("recovery_after", item)
            seconds = 270 if legacy else 30
            with patch("review_runs.datetime", wraps=datetime) as clock:
                clock.now.return_value = now + timedelta(seconds=seconds - 0.001)
                self.assertEqual((await self.client.get(path)).json()["status"], "running")
                clock.now.return_value = now + timedelta(seconds=seconds)
                self.assertEqual((await self.client.get(path)).json()["status"], "interrupted")
                inbox = (await self.client.get('/api/review-runs')).json()["items"]
                self.assertEqual(next(item for item in inbox if item["id"] == document["id"])["status"], "interrupted")
        self.gateway.review.assert_not_called()

    async def test_competing_recoveries_and_active_local_task_execute_only_once(self):
        document = await self.interrupted_review()
        entered, release = asyncio.Event(), asyncio.Event()

        async def blocked(*args):
            entered.set()
            await release.wait()
            return "completed", json.dumps(self.result), self.output

        self.gateway.review.side_effect = blocked
        async with AsyncClient(
            transport=ASGITransport(app=create_app(self.settings, self.gateway, self.store)),
            base_url="https://testserver", headers=self.headers,
        ) as other:
            responses = await asyncio.gather(self.resume(document), self.resume(document, client=other))
            self.assertEqual(sorted(response.status_code for response in responses), [202, 409])
            await asyncio.wait_for(entered.wait(), 2)
            saved = await self.store.get(document["id"])
            self.assertGreater(datetime.fromisoformat(saved["recovery_after"]), datetime.now(timezone.utc))
            self.assertLessEqual(
                datetime.fromisoformat(saved["recovery_after"]) - datetime.fromisoformat(saved["updated_at"]),
                timedelta(seconds=self.settings.timeout + RECOVERY_GRACE_SECONDS + 1),
            )
            self.assertEqual((await self.resume(saved)).status_code, 409)
            self.assertEqual((await self.resume(saved, client=other)).status_code, 409)
            # A live local task remains authoritative even after the recovery window.
            winner = self.client if responses[0].status_code == 202 else other
            with patch("review_runs.datetime", wraps=datetime) as clock:
                clock.now.return_value = datetime.fromisoformat(saved["recovery_after"]) + timedelta(seconds=1)
                self.assertEqual((await self.resume(saved, client=winner)).status_code, 409)
            release.set()
            await self.finish_tasks()
        self.assertEqual(self.gateway.review.await_count, 1)

    async def test_failed_recovery_claim_does_not_call_agent_or_lose_input(self):
        document = await self.interrupted_review()
        replace = self.store.replace
        for failure, status in [(CosmosHttpResponseError(status_code=412), 409),
                                (RuntimeError("unavailable"), 503)]:
            self.store.replace = AsyncMock(side_effect=failure)
            self.assertEqual((await self.resume(document)).status_code, status)
            self.assertEqual(await self.store.get(document["id"]), document)
        self.gateway.review.assert_not_called()
        self.store.replace = replace
        self.gateway.review.return_value = ("completed", json.dumps(self.result), self.output)
        self.assertEqual((await self.resume(document)).status_code, 202)
        await self.finish_tasks()

    async def test_stale_worker_cannot_overwrite_recovered_result(self):
        document = await self.interrupted_review()
        self.gateway.review.return_value = ("completed", json.dumps(self.result), self.output)
        self.assertEqual((await self.resume(document)).status_code, 202)
        await self.finish_tasks()
        saved = await self.store.get(document["id"])
        stale = self.controller()
        await stale.model_gate.slots.acquire()
        with self.assertLogs("uvicorn.error", level="WARNING") as captured:
            await stale.execute(document)
        self.assertIn("review_persistence_failed", captured.output[0])
        self.assertEqual(await self.store.get(document["id"]), saved)

    def logged_events(self, captured):
        return [json.loads(record.getMessage()) for record in captured.records if record.getMessage().startswith("{")]

    async def test_execution_event_is_logged_after_the_final_persist(self):
        document = await self.draft()
        self.gateway.review.return_value = ("completed", json.dumps(self.result), self.output)
        with self.assertLogs("uvicorn.error", level="INFO") as captured:
            saved = await self.run_direct(document)
        self.assertEqual(saved["status"], "waiting_input")
        events = self.logged_events(captured)
        self.assertEqual([event["event"] for event in events], ["review_execution"])
        self.assertEqual(events[0]["status"], "waiting_input")

    async def test_failed_final_persist_logs_a_failure_instead_of_a_success_event(self):
        document = await self.draft()
        self.gateway.review.return_value = ("completed", json.dumps(self.result), self.output)
        self.store.replace = AsyncMock(side_effect=RuntimeError("https://private-account.example/secret"))
        controller = self.controller()
        for _ in range(4):
            await controller.model_gate.slots.acquire()
        document["status"] = "running"
        document["runs"].append({"id": "attempt", "events": [], "input": deepcopy(self.body)})
        with self.assertLogs("uvicorn.error", level="INFO") as captured:
            await controller.execute(document)
        events = self.logged_events(captured)
        self.assertEqual(events, [{"event": "review_persistence_failed", "review_id": document["id"],
                                   "error_type": "RuntimeError"}])
        self.assertNotIn("private-account", "".join(captured.output))
        self.assertFalse(controller.model_gate.slots.locked())
        self.assertEqual(controller.tasks, {})

    async def test_unexpected_gateway_exception_is_logged_by_type_without_its_message(self):
        document = await self.draft()
        self.gateway.review.side_effect = KeyError("https://private-account.example/secret")
        with self.assertLogs("uvicorn.error", level="INFO") as captured:
            saved = await self.run_direct(document)
        self.assertEqual(saved["status"], "failed")
        self.assertEqual(saved["runs"][-1]["error"], "agent_unavailable")
        events = self.logged_events(captured)
        self.assertEqual(events[0], {"event": "review_execution_error", "review_id": document["id"],
                                     "error_type": "KeyError"})
        self.assertEqual([event["event"] for event in events[1:]], ["review_execution"])
        self.assertNotIn("private-account", "".join(captured.output))

    async def test_error_bodies_carry_the_request_id(self):
        valid = "review-" + "0" * 8 + "-0000-0000-0000-" + "0" * 12
        for response, status, code in [
            (await self.client.get("/api/review-runs/not-a-review"), 400, "invalid_review"),
            (await self.client.get("/api/review-runs", headers={"Origin": "https://other.example"}), 403, "request_not_allowed"),
            (await self.client.get(f"/api/review-runs/{valid}"), 404, "not_found"),
        ]:
            with self.subTest(code=code):
                self.assertEqual(response.status_code, status, response.text)
                self.assertEqual(response.json(), {"error": code, "request_id": response.headers["X-Correlation-ID"]})
                self.assertTrue(response.json()["request_id"])

    async def test_cosmos_errors_keep_their_status_and_code(self):
        valid = "review-" + "0" * 8 + "-0000-0000-0000-" + "0" * 12
        for failure, status, code in [(404, 404, "not_found"), (412, 409, "review_changed"),
                                      (409, 503, "reviews_unavailable"), (500, 503, "reviews_unavailable")]:
            with self.subTest(failure=failure):
                self.store.get = AsyncMock(side_effect=CosmosHttpResponseError(status_code=failure))
                response = await self.client.get(f"/api/review-runs/{valid}")
                self.assertEqual((response.status_code, response.json()["error"]), (status, code))

    async def test_recovery_respects_shared_capacity_and_rate_limits(self):
        document = await self.interrupted_review()
        controller = self.controller()
        app = FastAPI()

        @app.middleware("http")
        async def request_id(request, call_next):
            request.state.request_id = "test-request"
            return await call_next(request)

        app.include_router(controller.router)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="https://testserver",
                               headers=self.headers) as client:
            for _ in range(4):
                await controller.model_gate.slots.acquire()
            response = await self.resume(document, client=client)
            self.assertEqual(response.status_code, 429)
            self.assertEqual(response.headers["Retry-After"], "60")
            self.assertEqual(response.json(), {"error": "busy", "request_id": "test-request"})
            for _ in range(4):
                controller.model_gate.slots.release()
            controller.model_gate.recent.extend([asyncio.get_running_loop().time()] * 20)
            self.assertEqual((await self.resume(document, client=client)).status_code, 429)
        self.assertEqual(await self.store.get(document["id"]), document)
        self.gateway.review.assert_not_called()

    async def test_a_run_over_its_agents_model_budget_is_busy_before_any_model_call(self):
        # A review run is a model call too, so it spends the budget of the deployment its agent declares (#232).
        limits = {"review-model": {"requests_per_minute": 2, "tokens_per_minute": 10_000_000},
                  "other-model": {"requests_per_minute": 1, "tokens_per_minute": 10_000_000}}
        agents = json.loads((Path(__file__).parent / "agents.json").read_text(encoding="utf-8"))
        agents[0]["model"] = "review-model"
        self.gateway.review.return_value = ("completed", json.dumps({**self.result, "questions": []}), self.output)
        with TemporaryDirectory() as directory:
            path = Path(directory) / "agents.json"
            path.write_text(json.dumps(agents), encoding="utf-8")
            settings = replace(self.settings, agents_path=path, model_limits=limits)
            async with AsyncClient(transport=ASGITransport(app=create_app(settings, self.gateway, self.store)),
                                   base_url="https://testserver", headers=self.headers) as client:
                started = []
                for _ in range(3):
                    document = await self.draft()
                    response = await client.post(f'/api/review-runs/{document["id"]}/execute',
                                                 headers={"If-Match": document["_etag"]})
                    started.append(response)
                await self.finish_tasks()
        self.assertEqual([response.status_code for response in started], [202, 202, 429])
        self.assertEqual(started[2].json()["error"], "busy")
        self.assertTrue(1 <= int(started[2].headers["Retry-After"]) <= 60)
        self.assertEqual(self.gateway.review.await_count, 2)

    async def test_a_run_whose_agent_declares_no_model_is_not_budgeted(self):
        limits = {"review-model": {"requests_per_minute": 1, "tokens_per_minute": 1}}
        self.gateway.review.return_value = ("completed", json.dumps({**self.result, "questions": []}), self.output)
        async with AsyncClient(transport=ASGITransport(app=create_app(
                replace(self.settings, model_limits=limits), self.gateway, self.store)),
                base_url="https://testserver", headers=self.headers) as client:
            for _ in range(3):
                document = await self.draft()
                response = await client.post(f'/api/review-runs/{document["id"]}/execute',
                                             headers={"If-Match": document["_etag"]})
                self.assertEqual(response.status_code, 202)
            await self.finish_tasks()
        self.assertEqual(self.gateway.review.await_count, 3)

    async def test_unconfirmed_claim_waits_then_recovers_without_losing_history(self):
        document = await self.interrupted_review()
        replace = self.store.replace

        async def accepted_but_unconfirmed(document, etag):
            await replace(document, etag)
            raise TimeoutError()

        self.store.replace = accepted_but_unconfirmed
        self.assertEqual((await self.resume(document)).status_code, 504)
        self.gateway.review.assert_not_called()
        saved = await self.store.get(document["id"])
        self.assertEqual(len(saved["runs"]), 2)
        self.assertEqual((await self.resume(saved)).status_code, 409)
        self.store.replace = replace
        self.gateway.review.return_value = ("completed", json.dumps(self.result), self.output)
        with patch("review_runs.datetime", wraps=datetime) as clock:
            clock.now.return_value = datetime.fromisoformat(saved["recovery_after"])
            self.assertEqual((await self.resume(saved)).status_code, 202)
            await self.finish_tasks()
        recovered = await self.store.get(document["id"])
        self.assertEqual(len(recovered["runs"]), 3)
        self.assertEqual(recovered["runs"][0], saved["runs"][0])
        self.assertEqual(recovered["runs"][-1]["resumed_from"], saved["runs"][-1]["id"])
        self.assertEqual(recovered["status"], "waiting_input")
        self.assertEqual(self.gateway.review.await_count, 1)

    async def test_origin_namespace_and_conditional_write_guards(self):
        document = await self.draft()
        path = '/api/review-runs/' + document["id"]
        self.assertEqual((await self.client.post(path + '/execute')).status_code, 409)
        self.assertEqual((await self.client.get(path, headers={"Origin": "https://other.example"})).status_code, 403)
        self.assertEqual((await self.client.get('/api/conversations/' + document["id"])).status_code, 400)

    async def test_hidden_agent_and_browser_supplied_results_rejected(self):
        for changes in [{"agent_id": "case-review"}, {"runs": []}, {"status": "completed"}]:
            response = await self.client.post('/api/review-runs', json={**self.body, **changes})
            self.assertEqual(response.status_code, 400)
import json
import asyncio
from collections import deque
from copy import deepcopy
import unittest
from unittest.mock import AsyncMock

from azure.cosmos.exceptions import CosmosHttpResponseError
from httpx import ASGITransport, AsyncClient

from reviews import ReviewInput, review_prompt, validate_result
from app import Settings, create_app, execution_receipts
from review_runs import ReviewRuns


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
        return {"items": [{key: document[key] for key in ("id", "title", "agent_id", "updated_at", "status")}
                          for document in self.documents.values() if document["agent_id"] in agents], "cursor": None}


class ReviewLifecycleTests(unittest.IsolatedAsyncioTestCase):
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
                          self.store, self.gateway, execution_receipts, asyncio.Semaphore(4), deque())

    async def run_direct(self, document):
        controller = self.controller()
        document["status"] = "running"
        document["runs"].append({"id": "attempt", "events": [], "input": deepcopy(self.body)})
        await controller.slots.acquire()
        await controller.execute(document)
        return await self.store.get(document["id"])

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
        document = await self.draft()
        document["status"] = "running"
        await self.store.replace(document, document["_etag"])
        response = await self.client.get('/api/review-runs/' + document["id"])
        self.assertEqual(response.json()["status"], "interrupted")
        inbox = await self.client.get('/api/review-runs')
        self.assertEqual(inbox.json()["items"][0]["status"], "interrupted")
        self.assertEqual((await self.store.get(document["id"]))["status"], "running")
        self.gateway.review.assert_not_called()

    async def test_final_save_failure_never_claims_completion(self):
        document = await self.draft()
        self.gateway.review.return_value = ("completed", json.dumps(self.result), self.output)
        self.store.documents[document["id"]]["status"] = "running"
        self.store.replace = AsyncMock(side_effect=RuntimeError("unavailable"))
        await self.run_direct(document)
        response = await self.client.get('/api/review-runs/' + document["id"])
        self.assertEqual(response.json()["status"], "interrupted")

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
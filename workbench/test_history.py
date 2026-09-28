import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from azure.cosmos.exceptions import CosmosHttpResponseError

from app import Settings, create_app


class HistoryTests(unittest.TestCase):
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
        self.assertEqual(self.client.post("/api/conversations", content="x" * 524289, headers={**self.headers, "Content-Type": "application/json"}).status_code, 413)
        self.store.create.assert_not_called()

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
        with patch("history.monotonic", return_value=100):
            for _ in range(60):
                self.assertEqual(self.client.get("/api/conversations", headers=self.headers).status_code, 200)
            response = self.client.get("/api/conversations", headers=self.headers)
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.headers["Retry-After"], "60")
        self.assertEqual(self.store.list.await_count, 60)
        with patch("history.monotonic", return_value=161):
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


if __name__ == "__main__":
    unittest.main()
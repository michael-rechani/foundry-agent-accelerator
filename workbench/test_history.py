import unittest
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient
from azure.cosmos.exceptions import CosmosHttpResponseError

from app import Settings, create_app


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.store = AsyncMock()
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
        self.assertEqual(self.client.get(f"/api/conversations/{self.identifier}", headers=self.headers).status_code, 503)


if __name__ == "__main__":
    unittest.main()
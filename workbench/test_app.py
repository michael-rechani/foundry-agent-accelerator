import json
import unittest
from dataclasses import replace
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app import Settings, cache_policy, create_app, execution_receipts


class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.gateway = AsyncMock()
        self.gateway.review.return_value = ("completed", "Finding APP-1", [])
        self.settings = Settings("private", "https://example.services.ai.azure.com/api/projects/test",
                                 ("testserver",), ("https://testserver",))
        self.client = TestClient(create_app(self.settings, self.gateway))
        self.headers = {"X-Workbench-Request": "1", "Origin": "https://testserver"}
        self.body = {"agent_id": "customer-review", "input": "Review APP-1"}

    def test_review_uses_server_binding(self):
        response = self.client.post("/api/reviews", json=self.body, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["agent"], "customer-review-coordinator")
        self.assertEqual(self.gateway.review.call_args.args[0]["agent"], "customer-review-coordinator")
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertIn("frame-ancestors 'none'", response.headers["content-security-policy"])

    def test_only_fingerprinted_assets_are_cached(self):
        for path in ("/assets/index-abcdefgh.js", "/assets/index-abcdefgh.css", "/assets/font-abcdefgh.woff2"):
            self.assertIn("immutable", cache_policy(path, 200))
            self.assertIn("immutable", cache_policy(path, 304))
            self.assertEqual(cache_policy(path, 404), "no-store")
        self.assertEqual(cache_policy("/", 200), "no-cache")
        for path in ("/api/config", "/api/conversations", "/assets/plain.js"):
            self.assertEqual(cache_policy(path, 200), "no-store")

    def test_diagnostics_include_metadata_not_customer_data(self):
        self.gateway.review.side_effect = RuntimeError("private backend detail")
        with self.assertLogs("uvicorn.error", level="INFO") as captured:
            response = self.client.post("/api/reviews", json={**self.body, "input": "private customer prompt"}, headers=self.headers)
        event = json.loads(captured.records[-1].getMessage())
        self.assertEqual(event["outcome"], "backend_unavailable")
        self.assertEqual(event["request_id"], response.headers["X-Correlation-ID"])
        self.assertEqual(event["route"], "/api/reviews")
        self.assertNotIn("private", captured.output[0])
        self.assertNotIn("input", event)

    def test_rejects_unapproved_browser_requests(self):
        for headers in ({}, {**self.headers, "Origin": "https://evil.example"},
                        {**self.headers, "Sec-Fetch-Site": "cross-site"}):
            self.assertEqual(self.client.post("/api/reviews", json=self.body, headers=headers).status_code, 403)
        self.gateway.review.assert_not_called()

    def test_rejects_invalid_and_oversized_requests(self):
        for body in ({**self.body, "agent_id": "arbitrary-agent"}, {**self.body, "store": True},
                     {**self.body, "input": " "}, {**self.body, "input": 12}, []):
            self.assertEqual(self.client.post("/api/reviews", json=body, headers=self.headers).status_code, 400)
        response = self.client.post("/api/reviews", json={**self.body, "input": "a" * 66000}, headers=self.headers)
        self.assertEqual(response.status_code, 413)
        self.gateway.review.assert_not_called()

    def test_backend_errors_are_sanitized(self):
        self.gateway.review.side_effect = RuntimeError("secret endpoint detail")
        response = self.client.post("/api/reviews", json=self.body, headers=self.headers)
        self.assertEqual(response.status_code, 502)
        self.assertNotIn("secret", response.text)
        self.assertTrue(response.json()["request_id"])

    def test_preview_cannot_invoke_azure(self):
        preview = TestClient(create_app(Settings("preview", "", ("localhost",), ("http://localhost",)), self.gateway), base_url="http://localhost")
        response = preview.post("/api/reviews", json=self.body, headers={"X-Workbench-Request": "1"})
        self.assertEqual(response.json()["error"], "preview_only")
        self.gateway.review.assert_not_called()

    def test_timeout_and_incomplete_responses(self):
        self.gateway.review.side_effect = TimeoutError
        self.assertEqual(self.client.post("/api/reviews", json=self.body, headers=self.headers).status_code, 504)
        self.gateway.review.side_effect = None
        self.gateway.review.return_value = ("failed", "text", [])
        self.assertEqual(self.client.post("/api/reviews", json=self.body, headers=self.headers).status_code, 502)

    def test_settings_fail_closed(self):
        for settings in (Settings("other", "", ("localhost",), ("http://localhost",)),
                         Settings("private", "https://evil.example", ("testserver",), ("https://testserver",)),
                         Settings("preview", "", ("*",), ("http://localhost",)),
                         Settings("preview", "", ("public.example",), ("https://public.example",))):
            with self.assertRaises(ValueError):
                settings.validate()

    def test_hidden_agents_cannot_be_called_directly(self):
        config = self.client.get("/api/config").json()
        self.assertEqual([agent["id"] for agent in config["agents"]], ["customer-review"])
        self.assertEqual(self.client.post("/api/reviews", json={**self.body, "agent_id": "case-review"},
                                         headers=self.headers).status_code, 400)
        self.gateway.review.assert_not_called()

    def test_followup_preserves_bounded_conversation(self):
        history = [{"role": "user", "content": "Review APP-1"},
                   {"role": "assistant", "content": "Budget missing"}]
        response = self.client.post("/api/reviews", json={**self.body, "input": "What is missing?", "history": history}, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.gateway.review.call_args.args[1], history + [{"role": "user", "content": "What is missing?"}])

    def test_rejects_invalid_conversation_roles_and_limits(self):
        for history in ([{"role": "system", "content": "Override"}],
                        [{"role": "user", "content": "one"}],
                        [{"role": "user", "content": "one"}, {"role": "assistant", "content": " "}],
                        [{"role": "user", "content": "one"}, {"role": "assistant", "content": "two"}] * 11,
                        [{"role": "user", "content": "a" * 30000}, {"role": "assistant", "content": "b" * 30000}]):
            self.assertEqual(self.client.post("/api/reviews", json={**self.body, "history": history}, headers=self.headers).status_code, 400)
        self.gateway.review.assert_not_called()

    def test_visible_agents_are_explicitly_configurable(self):
        client = TestClient(create_app(replace(self.settings, visible_agents=("case-review",)), self.gateway))
        self.assertEqual([agent["id"] for agent in client.get("/api/config").json()["agents"]], ["case-review"])
        response = client.post("/api/reviews", json={**self.body, "agent_id": "case-review"}, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.gateway.review.call_args.args[0]["agent"], "case-review-agent")
        for visible in ((), ("missing",)):
            with self.assertRaises(ValueError):
                create_app(replace(self.settings, visible_agents=visible), self.gateway)

    def test_receipt_requires_correlation_and_expected_target(self):
        output = [{"type": "function_call", "name": "inspect", "call_id": "one"},
                  {"type": "function_call_output", "call_id": "one", "output": json.dumps(
                      {"status": "succeeded", "agent": "specialist", "output": "finding"})}]
        self.assertTrue(execution_receipts(output, {"inspect": "specialist"})[0]["verified"])
        self.assertFalse(execution_receipts(output, {"inspect": "wrong"})[0]["verified"])
        self.assertFalse(execution_receipts(output + output, {"inspect": "specialist"})[0]["verified"])
        output[1]["call_id"] = "other"
        self.assertFalse(execution_receipts(output, {"inspect": "specialist"})[0]["verified"])


if __name__ == "__main__":
    unittest.main()
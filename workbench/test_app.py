import asyncio
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from dataclasses import replace
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app import Settings, cache_policy, create_app, execution_receipts, load_agents


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

    def test_public_configuration_matches_request_limits(self):
        config = self.client.get("/api/config").json()
        self.assertEqual(config["default_agent"], "customer-review")
        self.assertEqual(config["title"], "AI Foundry Lab")
        self.assertEqual(config["agents"][0]["prompts"][0]["label"], "Review an application")
        self.assertIn("application and your checklist", config["agents"][0]["guidance"]["input"])
        self.assertIn("where each point came from", config["agents"][0]["guidance"]["output"])
        self.assertEqual(config["max_history_turns"], 10)
        self.assertEqual(config["review_timeout_ms"], 190000)
        self.assertEqual(config["history_timeout_ms"], 45000)
        self.assertEqual(config["max_request_bytes"], 65536)
        response = self.client.post("/api/reviews", json={**self.body, "input": "a" * config["max_characters"]}, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        response = self.client.post("/api/reviews", json={**self.body, "input": "a" * (config["max_characters"] + 1)}, headers=self.headers)
        self.assertEqual(response.status_code, 400)

    def test_default_agent_and_deadline_are_validated(self):
        settings = replace(self.settings, visible_agents=("customer-review", "case-review"), default_agent="case-review", timeout=60)
        config = TestClient(create_app(settings, self.gateway)).get("/api/config").json()
        self.assertEqual(config["default_agent"], "case-review")
        self.assertEqual(config["review_timeout_ms"], 70000)
        reordered = replace(self.settings, visible_agents=("case-review", "customer-review"))
        self.assertEqual(TestClient(create_app(reordered, self.gateway)).get("/api/config").json()["default_agent"], "case-review")
        with self.assertRaises(ValueError):
            create_app(replace(self.settings, default_agent="case-review"), self.gateway)
        for timeout in (0, 181, float("nan"), True):
            with self.assertRaises(ValueError):
                replace(self.settings, timeout=timeout).validate()
        for title in ("", " " * 3, "a" * 81, "bad\ntitle", " " * 80 + "a"):
            with self.assertRaises(ValueError):
                replace(self.settings, title=title).validate()

    def test_starter_prompts_are_optional_and_validated(self):
        agent = self.client.get("/api/config").json()["agents"][0]
        with TemporaryDirectory() as directory:
            path = Path(directory) / "agents.json"
            for prompts in (None, {}, [{}], [{"label": "", "text": "text"}],
                            [{"label": "label", "text": "a" * 4001}],
                            [{"label": "label", "text": "text"}] * 7):
                path.write_text(json.dumps([{**agent, "prompts": prompts}]), encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_agents(path)
            agent.pop("prompts")
            path.write_text(json.dumps([agent]), encoding="utf-8")
            self.assertEqual(load_agents(path)[0]["prompts"], [])

    def test_agent_guidance_is_optional_and_validated(self):
        agent = self.client.get("/api/config").json()["agents"][0]
        guidance = agent["guidance"]
        with TemporaryDirectory() as directory:
            path = Path(directory) / "agents.json"
            invalid = [None, [], {}, "guide", {**guidance, "extra": "unused"},
                       {key: value for key, value in guidance.items() if key != "configuration"}]
            invalid.extend({**guidance, key: value} for key in guidance
                           for value in ("", " ", None, 7, "a" * 1201))
            for value in invalid:
                with self.subTest(guidance=value):
                    path.write_text(json.dumps([{**agent, "guidance": value}]), encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, "Invalid agent guidance"):
                        load_agents(path)
            path.write_text(json.dumps([agent]), encoding="utf-8")
            self.assertEqual(load_agents(path)[0]["guidance"], guidance)
            agent["guidance"] = {**guidance, "input": "\U0001f600" * 1200}
            path.write_text(json.dumps([agent]), encoding="utf-8")
            self.assertEqual(load_agents(path)[0]["guidance"]["input"], "\U0001f600" * 1200)
            agent.pop("guidance")
            path.write_text(json.dumps([agent]), encoding="utf-8")
            self.assertNotIn("guidance", load_agents(path)[0])

    def test_static_catalog_cannot_shadow_a_created_agent_identifier(self):
        agent = self.client.get("/api/config").json()["agents"][0]
        with TemporaryDirectory() as directory:
            path = Path(directory) / "agents.json"
            path.write_text(json.dumps([{
                **agent, "id": "created-11111111-2222-4333-8444-555555555555",
            }]), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "identifier namespace is reserved"):
                load_agents(path)

    def test_catalog_guidance_and_profile_targets_are_consistent(self):
        root = Path(__file__).resolve().parent.parent
        agents = load_agents(root / "workbench" / "agents.json")
        self.assertTrue(all("guidance" in agent for agent in agents))
        profile = json.loads((root / "hosted-agents" / "review-coordinator-agent" / "profiles"
                              / "evidence-review.example.json").read_text(encoding="utf-8"))
        guided = next(agent for agent in agents if agent["id"] == "customer-review")
        self.assertEqual(guided["agent"], profile["name"])
        self.assertEqual(guided["tools"], {item["tool"]: item["agent"] for item in profile["specialists"]})
        base = next(agent for agent in agents if agent["id"] == "review-coordinator")
        self.assertEqual(set(base["tools"].values()), set(guided["tools"].values()))
        self.assertNotEqual(base["agent"], guided["agent"])
        self.assertIn("not an extra planning capability", base["description"])

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

    def test_dependency_probe_is_cached_and_does_not_generate(self):
        store = AsyncMock()
        with TestClient(create_app(self.settings, self.gateway, store)) as client:
            for _ in range(3):
                response = client.get("/api/health/dependencies")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), {"status": "ready", "foundry": "ready", "cosmos": "ready"})
            self.gateway.check.assert_awaited_once()
            store.check.assert_awaited_once()
            self.gateway.review.assert_not_called()

    def test_dependency_failure_does_not_fail_liveness_or_leak_details(self):
        self.gateway.check.side_effect = RuntimeError("secret dependency details")
        with self.assertLogs("uvicorn.error", level="INFO") as logs:
            with TestClient(create_app(self.settings, self.gateway, AsyncMock())) as client:
                response = client.get("/api/health/dependencies")
                self.assertEqual(response.status_code, 503)
                self.assertEqual(response.json()["foundry"], "unavailable")
                self.assertEqual(client.get("/healthz").status_code, 200)
        self.assertNotIn("secret", " ".join(logs.output))

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

    def test_review_rate_limit_precedes_body_validation(self):
        with patch("app.time.monotonic", return_value=100):
            for _ in range(20):
                self.assertEqual(self.client.post("/api/reviews", json={}, headers=self.headers).status_code, 400)
            response = self.client.post("/api/reviews", json={}, headers=self.headers)
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.headers["Retry-After"], "60")
        self.gateway.review.assert_not_called()

    def test_body_deadline_prevents_agent_execution(self):
        async def stalled(request):
            await asyncio.Event().wait()
            yield b""

        timeout = asyncio.timeout
        with patch("starlette.requests.Request.stream", stalled), patch("app.asyncio.timeout", side_effect=lambda seconds: timeout(0.01)):
            response = self.client.post("/api/reviews", json=self.body, headers=self.headers)
        self.assertEqual(response.status_code, 408)
        self.gateway.review.assert_not_called()

    def test_oversized_agent_response_is_rejected(self):
        self.gateway.review.return_value = ("completed", "a" * 100001, [])
        response = self.client.post("/api/reviews", json=self.body, headers=self.headers)
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["error"], "response_too_large")
        self.assertEqual(response.headers["Strict-Transport-Security"], "max-age=31536000")

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
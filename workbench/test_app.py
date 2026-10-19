import asyncio
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from agent_creation import CreationSettings
from app import FoundryGateway, Settings, cache_policy, create_app, execution_receipts, load_agents
from log_capture import CapturedLabLogs


class RateLimitError(Exception):
    """Stands in for the model client's rate-limit error, which carries the HTTP status and response headers."""

    status_code = 429

    def __init__(self, headers=None):
        super().__init__("rate limited")
        self.response = SimpleNamespace(headers=headers if headers is not None else {})


class WorkbenchTests(CapturedLabLogs, unittest.TestCase):
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

    def test_reply_reports_token_usage_or_null(self):
        response = self.client.post("/api/reviews", json=self.body, headers=self.headers)
        self.assertIsNone(response.json()["usage"])

        async def review(agent, prompt, thread=None, usage=None):
            usage.append({"input_tokens": 40, "output_tokens": 10, "total_tokens": 50,
                          "cached_tokens": None, "reasoning_tokens": 0})
            return "completed", "Finding APP-1", []

        self.gateway.review.side_effect = review
        response = self.client.post("/api/reviews", json=self.body, headers=self.headers)
        self.assertEqual(response.json()["usage"], {"input_tokens": 40, "output_tokens": 10, "total_tokens": 50,
                                                    "cached_tokens": None, "reasoning_tokens": 0})

    def test_large_responses_are_compressed_and_keep_their_headers(self):
        accept = {**self.headers, "Accept-Encoding": "gzip"}
        compressed = self.client.get("/api/agent-templates", headers=accept)
        plain = self.client.get("/api/agent-templates", headers={**self.headers, "Accept-Encoding": "identity"})
        self.assertEqual(compressed.status_code, 200)
        self.assertEqual(compressed.headers["content-encoding"], "gzip")
        self.assertIn("accept-encoding", compressed.headers["vary"].lower())
        self.assertNotIn("content-encoding", plain.headers)
        self.assertLess(int(compressed.headers["content-length"]) * 3, len(plain.content))
        self.assertEqual(compressed.json(), plain.json())
        self.assertEqual(compressed.headers["cache-control"], "no-store")
        self.assertIn("frame-ancestors 'none'", compressed.headers["content-security-policy"])
        self.assertIn("x-correlation-id", compressed.headers)

    def test_small_responses_are_not_compressed(self):
        response = self.client.get("/healthz", headers={"Accept-Encoding": "gzip"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("content-encoding", response.headers)

    def test_public_configuration_matches_request_limits(self):
        config = self.client.get("/api/config").json()
        self.assertEqual(config["default_agent"], "customer-review")
        self.assertEqual(config["title"], "Foundry Agent Lab")
        self.assertEqual(config["agents"][0]["prompts"][0]["label"], "Check against a checklist")
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
        self.assertIn("it does not add capabilities", base["description"])

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
        self.assertEqual(event["dependency"], "foundry")
        self.assertEqual(event["error_type"], "RuntimeError")
        self.assertEqual(event["method"], "POST")
        self.assertGreaterEqual(event["elapsed_ms"], 0)
        self.assertEqual(captured.records[-1].levelname, "ERROR")
        self.assertNotIn("private", " ".join(captured.output))
        self.assertNotIn("input", event)

    def test_unexpected_api_errors_have_safe_diagnostics_and_security_headers(self):
        application = create_app(self.settings, self.gateway)

        @application.get("/api/unexpected")
        async def unexpected():
            raise RuntimeError("sensitive exception message")

        # Keep this test route ahead of the static-files catch-all.
        application.router.routes.insert(0, application.router.routes.pop())
        with self.assertLogs("uvicorn.error", level="ERROR") as logs:
            response = TestClient(application).get("/api/unexpected?token=sensitive-query")
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["error"], "internal_error")
        self.assertEqual(response.json()["request_id"], response.headers["X-Correlation-ID"])
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertIn("frame-ancestors 'none'", response.headers["content-security-policy"])
        event = json.loads(logs.records[-1].getMessage())
        self.assertEqual(event["route"], "/api/unexpected")
        self.assertEqual(event["dependency"], "application")
        self.assertEqual(event["error_type"], "RuntimeError")
        self.assertNotIn("sensitive", " ".join(logs.output) + response.text)

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
        failures = [json.loads(record.getMessage()) for record in logs.records
                    if json.loads(record.getMessage())["event"] == "workbench_dependency_failed"]
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0]["dependency"], "foundry")
        self.assertEqual(failures[0]["error_type"], "RuntimeError")
        self.assertGreaterEqual(failures[0]["elapsed_ms"], 0)

    def test_foundry_failure_reports_which_step_was_slow(self):
        async def stalled(agents, timings):
            timings.update(stage="read", token_ms=41, read_ms=5003)
            raise TimeoutError("secret dependency details")

        self.gateway.check.side_effect = stalled
        with self.assertLogs("uvicorn.error", level="INFO") as logs:
            with TestClient(create_app(self.settings, self.gateway, AsyncMock())) as client:
                self.assertEqual(client.get("/api/health/dependencies").status_code, 503)
        events = [json.loads(record.getMessage()) for record in logs.records]
        failure = next(event for event in events if event["event"] == "workbench_dependency_failed")
        self.assertEqual((failure["dependency"], failure["error_type"]), ("foundry", "TimeoutError"))
        self.assertEqual((failure["stage"], failure["token_ms"], failure["read_ms"]), ("read", 41, 5003))
        self.assertGreaterEqual(failure["elapsed_ms"], 0)
        self.assertNotIn("secret", " ".join(logs.output))

    def test_dependency_heartbeat_logs_how_long_each_probe_took(self):
        async def check(agents, timings):
            timings.update(stage="read", token_ms=12, read_ms=290)

        self.gateway.check.side_effect = check
        with self.assertLogs("uvicorn.error", level="INFO") as logs:
            with TestClient(create_app(self.settings, self.gateway, AsyncMock())) as client:
                response = client.get("/api/health/dependencies")
        self.assertEqual(response.json(), {"status": "ready", "foundry": "ready", "cosmos": "ready"})
        events = [json.loads(record.getMessage()) for record in logs.records]
        heartbeat = next(event for event in events if event["event"] == "workbench_dependencies")
        self.assertEqual((heartbeat["foundry_token_ms"], heartbeat["foundry_read_ms"]), (12, 290))
        self.assertGreaterEqual(heartbeat["foundry_ms"], 0)
        self.assertGreaterEqual(heartbeat["cosmos_ms"], 0)
        self.assertNotIn("stage", heartbeat)

    def test_rejects_unapproved_browser_requests(self):
        for headers in ({}, {**self.headers, "Origin": "https://evil.example"},
                        {**self.headers, "Sec-Fetch-Site": "cross-site"}):
            self.assertEqual(self.client.post("/api/reviews", json=self.body, headers=headers).status_code, 403)
        self.gateway.review.assert_not_called()

    def test_missing_origin_is_accepted_only_with_the_lab_header(self):
        response = self.client.post("/api/reviews", json=self.body, headers={"X-Workbench-Request": "1"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.post("/api/reviews", json=self.body).status_code, 403)
        self.assertEqual(self.gateway.review.call_count, 1)

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

    def test_model_rate_limit_is_busy_with_a_bounded_retry_hint(self):
        cases = [({"retry-after": "12"}, "12"), ({"retry-after": "1.2"}, "2"), ({"retry-after": "0"}, "1"),
                 ({"retry-after": "900"}, "60"), ({"retry-after": "soon"}, "60"), ({"retry-after": "nan"}, "60"),
                 ({"retry-after": "inf"}, "60"), ({}, "60"), (None, "60")]
        for headers, expected in cases:
            with self.subTest(headers=headers):
                self.gateway.review.side_effect = RateLimitError(headers)
                response = self.client.post("/api/reviews", json=self.body, headers=self.headers)
                self.assertEqual(response.status_code, 429)
                self.assertEqual(response.json()["error"], "busy")
                self.assertEqual(response.json()["request_id"], response.headers["X-Correlation-ID"])
                self.assertEqual(response.headers["Retry-After"], expected)

    def test_model_rate_limit_is_logged_as_busy_without_content(self):
        self.gateway.review.side_effect = RateLimitError({"retry-after": "5"})
        with self.assertLogs("uvicorn.error", level="INFO") as captured:
            self.client.post("/api/reviews", json={**self.body, "input": "private customer prompt"}, headers=self.headers)
        event = json.loads(captured.records[-1].getMessage())
        self.assertEqual((event["status"], event["outcome"]), (429, "busy"))
        self.assertEqual((event["dependency"], event["error_type"]), ("foundry", "RateLimitError"))
        self.assertEqual(captured.records[-1].levelname, "INFO")
        self.assertNotIn("private", " ".join(captured.output))

    def test_other_model_errors_stay_backend_unavailable(self):
        for status in (401, 500, None):
            with self.subTest(status=status):
                failure = RateLimitError({"retry-after": "5"})
                failure.status_code = status
                self.gateway.review.side_effect = failure
                response = self.client.post("/api/reviews", json=self.body, headers=self.headers)
                self.assertEqual(response.status_code, 502)
                self.assertEqual(response.json()["error"], "backend_unavailable")
                self.assertNotIn("Retry-After", response.headers)

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
        self.assertIsNone(self.gateway.review.call_args.kwargs["thread"])

    def test_chat_thread_is_validated_and_forwarded(self):
        thread = "0f8b6c1e-2a3d-4e5f-8a7b-1c2d3e4f5a6b"
        response = self.client.post("/api/reviews", json={**self.body, "thread": thread}, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.gateway.review.call_args.kwargs["thread"], thread)
        self.gateway.review.reset_mock()
        for invalid in (7, "", "session-1", thread.upper(), "0f8b6c1e-2a3d-1e5f-8a7b-1c2d3e4f5a6b", thread + "\n"):
            with self.subTest(thread=invalid):
                self.assertEqual(self.client.post("/api/reviews", json={**self.body, "thread": invalid},
                                                  headers=self.headers).status_code, 400)
        self.gateway.review.assert_not_called()
        for reuse in (-1, 3601, float("nan"), True):
            with self.subTest(reuse=reuse), self.assertRaises(ValueError):
                replace(self.settings, session_reuse_seconds=reuse).validate()

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


class FoundryGatewayTests(CapturedLabLogs, unittest.IsolatedAsyncioTestCase):
    async def test_reviews_reuse_one_credential_project_and_connection_pool(self):
        response = SimpleNamespace(status="completed", output_text="Finding", model_dump=lambda: {"output": []})
        openai_client = MagicMock()
        openai_client.responses.create = AsyncMock(return_value=response)
        project, credential, pool = MagicMock(close=AsyncMock()), MagicMock(close=AsyncMock()), MagicMock(aclose=AsyncMock())
        project.get_openai_client.return_value = openai_client
        project_class, credential_class = MagicMock(return_value=project), MagicMock(return_value=credential)
        modules = {
            "azure.ai.projects.aio": SimpleNamespace(AIProjectClient=project_class),
            "azure.identity.aio": SimpleNamespace(ManagedIdentityCredential=credential_class),
            "openai": SimpleNamespace(DefaultAsyncHttpxClient=MagicMock(return_value=pool)),
        }
        settings = Settings("private", "https://example.services.ai.azure.com/api/projects/test",
                            ("testserver",), ("https://testserver",))
        gateway = FoundryGateway(settings)
        with patch.dict(sys.modules, modules):
            for agent in ("case-review-agent", "application-review-agent"):
                self.assertEqual(await gateway.review({"agent": agent}, "Review"), ("completed", "Finding", []))
        project_class.assert_called_once_with(endpoint=settings.endpoint, credential=credential, allow_preview=True)
        credential_class.assert_called_once()
        self.assertEqual([call.kwargs for call in project.get_openai_client.call_args_list], [
            {"agent_name": agent, "timeout": settings.timeout, "max_retries": 0, "http_client": pool}
            for agent in ("case-review-agent", "application-review-agent")
        ])
        openai_client.responses.create.assert_awaited_with(input="Review", store=False, stream=False)
        openai_client.close.assert_not_called()
        await gateway.close()
        pool.aclose.assert_awaited_once()
        project.close.assert_awaited_once()
        credential.close.assert_awaited_once()
        await gateway.close()
        pool.aclose.assert_awaited_once()

    @staticmethod
    def check_gateway(token_error=None, read_error=None):
        credential, project = MagicMock(), MagicMock()
        credential.__aenter__ = AsyncMock(return_value=credential)
        credential.__aexit__ = AsyncMock(return_value=None)
        project.__aenter__ = AsyncMock(return_value=project)
        project.__aexit__ = AsyncMock(return_value=None)
        credential.get_token = AsyncMock(side_effect=token_error)
        project.agents.get = AsyncMock(side_effect=read_error)
        modules = {
            "azure.ai.projects.aio": SimpleNamespace(AIProjectClient=MagicMock(return_value=project)),
            "azure.identity.aio": SimpleNamespace(ManagedIdentityCredential=MagicMock(return_value=credential)),
        }
        settings = Settings("private", "https://example.services.ai.azure.com/api/projects/test",
                            ("testserver",), ("https://testserver",))
        return FoundryGateway(settings), credential, project, patch.dict(sys.modules, modules)

    async def test_check_times_the_sign_in_and_the_agent_reads_separately(self):
        gateway, credential, project, modules = self.check_gateway()
        timings = {}
        with modules:
            await gateway.check([{"agent": "one"}, {"agent": "two"}], timings)
        credential.get_token.assert_awaited_once_with("https://ai.azure.com/.default")
        self.assertEqual([call.args for call in project.agents.get.await_args_list], [("one",), ("two",)])
        self.assertEqual(timings["stage"], "read")
        self.assertGreaterEqual(timings["token_ms"], 0)
        self.assertGreaterEqual(timings["read_ms"], 0)

    async def test_check_names_the_step_that_failed(self):
        gateway, _, project, modules = self.check_gateway(read_error=RuntimeError("stalled"))
        timings = {}
        with modules, self.assertRaises(RuntimeError):
            await gateway.check([{"agent": "one"}], timings)
        self.assertEqual(timings["stage"], "read")
        self.assertIn("token_ms", timings)
        self.assertIn("read_ms", timings)

        gateway, _, project, modules = self.check_gateway(token_error=RuntimeError("no token"))
        timings = {}
        with modules, self.assertRaises(RuntimeError):
            await gateway.check([{"agent": "one"}], timings)
        self.assertEqual(timings["stage"], "token")
        self.assertIn("token_ms", timings)
        self.assertNotIn("read_ms", timings)
        project.agents.get.assert_not_awaited()

    async def test_check_works_without_a_timings_dict(self):
        gateway, _, project, modules = self.check_gateway()
        with modules:
            await gateway.check([{"agent": "one"}])
        project.agents.get.assert_awaited_once_with("one")

    def session_gateway(self, responses, reuse_seconds=600):
        openai_client = MagicMock()
        openai_client.responses.create = AsyncMock(side_effect=[SimpleNamespace(
            status=status, output_text="Finding", model_dump=lambda: {"output": []},
            model_extra={"agent_session_id": session_id},
        ) for status, session_id in responses])
        project = MagicMock(close=AsyncMock())
        project.get_openai_client.return_value = openai_client
        modules = {
            "azure.ai.projects.aio": SimpleNamespace(AIProjectClient=MagicMock(return_value=project)),
            "azure.identity.aio": SimpleNamespace(ManagedIdentityCredential=MagicMock(return_value=MagicMock(close=AsyncMock()))),
            "openai": SimpleNamespace(DefaultAsyncHttpxClient=MagicMock(return_value=MagicMock(aclose=AsyncMock()))),
        }
        settings = Settings("private", "https://example.services.ai.azure.com/api/projects/test",
                            ("testserver",), ("https://testserver",), session_reuse_seconds=reuse_seconds)
        return FoundryGateway(settings), openai_client, patch.dict(sys.modules, modules)

    @staticmethod
    def sent_sessions(openai_client):
        return [(call.kwargs.get("extra_body") or {}).get("agent_session_id")
                for call in openai_client.responses.create.await_args_list]

    async def test_chat_thread_reuses_its_session_per_agent(self):
        thread, other = "0f8b6c1e-2a3d-4e5f-8a7b-1c2d3e4f5a6b", "1f8b6c1e-2a3d-4e5f-9a7b-1c2d3e4f5a6b"
        gateway, openai_client, modules = self.session_gateway(
            [("completed", "s1"), ("completed", "s1"), ("completed", "s2"), ("completed", "s3"), ("completed", "s4")])
        with modules:
            for agent, chat in (("case", thread), ("case", thread), ("application", thread), ("case", other), ("case", None)):
                await gateway.review({"agent": agent}, "Review", thread=chat)
        self.assertEqual(self.sent_sessions(openai_client), [None, "s1", None, None, None])
        openai_client.responses.create.assert_awaited_with(input="Review", store=False, stream=False)
        await gateway.close()
        self.assertEqual(gateway._sessions, {})

    async def test_session_is_dropped_after_failure_expiry_or_when_disabled(self):
        thread = "0f8b6c1e-2a3d-4e5f-8a7b-1c2d3e4f5a6b"
        gateway, openai_client, modules = self.session_gateway(
            [("completed", "s1"), ("failed", "s1"), ("completed", "s2"), ("completed", "s3")])
        now = [100.0]
        with modules, patch("app.time", SimpleNamespace(monotonic=lambda: now[0])):
            for elapsed in (0, 0, 0, 600):
                now[0] += elapsed
                await gateway.review({"agent": "case"}, "Review", thread=thread)
        self.assertEqual(self.sent_sessions(openai_client), [None, "s1", None, None])

        gateway, openai_client, modules = self.session_gateway([("completed", "s1"), ("completed", "s2")], reuse_seconds=0)
        with modules:
            for _ in range(2):
                await gateway.review({"agent": "case"}, "Review", thread=thread)
        self.assertEqual(self.sent_sessions(openai_client), [None, None])
        self.assertEqual(gateway._sessions, {})

    async def test_reused_sessions_are_bounded(self):
        gateway, _, modules = self.session_gateway([("completed", f"s{index}") for index in range(4)])
        with modules, patch("app.MAX_REUSED_SESSIONS", 2):
            for index in range(4):
                await gateway.review({"agent": "case"}, "Review", thread=f"{index}f8b6c1e-2a3d-4e5f-8a7b-1c2d3e4f5a6b")
        self.assertEqual([session for session, _ in gateway._sessions.values()], ["s2", "s3"])

    async def test_restart_rebuilds_clients_and_sends_full_history_without_old_session(self):
        gateway, client, modules = self.session_gateway([("completed", "old"), ("completed", "new")])
        prompt = [{"role": "user", "content": "Fictional input"},
                  {"role": "assistant", "content": "Finding"},
                  {"role": "user", "content": "Follow up"}]
        with modules:
            await gateway.review({"agent": "case"}, "Fictional input", thread="chat")
            await gateway.close()
            restarted = FoundryGateway(gateway.settings)
            await restarted.review({"agent": "case"}, prompt, thread="chat")
            await restarted.close()
        self.assertEqual(self.sent_sessions(client), [None, None])
        client.responses.create.assert_awaited_with(input=prompt, store=False, stream=False)
        self.assertEqual(gateway._sessions, {})
        self.assertEqual(restarted._sessions, {})

    async def test_overlapping_requests_never_lease_the_same_session(self):
        for completion_order in ((0, 1), (1, 0)):
            with self.subTest(completion_order=completion_order):
                gateway, client, modules = self.session_gateway([("completed", "initial")])
                entered = [asyncio.Event(), asyncio.Event()]
                finished = [asyncio.Event(), asyncio.Event()]
                prompts = [
                    [{"role": "user", "content": "First"}, {"role": "assistant", "content": "Finding"},
                     {"role": "user", "content": f"Follow up {index}"}] for index in range(2)
                ]

                async def respond(*, input, prompts=prompts, entered=entered, finished=finished, **kwargs):
                    index = prompts.index(input)
                    entered[index].set()
                    await finished[index].wait()
                    return SimpleNamespace(status="completed", output_text="Finding", model_dump=lambda: {"output": []},
                                           model_extra={"agent_session_id": ("initial", "separate")[index]})

                with modules:
                    await gateway.review({"agent": "case"}, "First", thread="chat")
                    client.responses.create.side_effect = respond
                    first = asyncio.create_task(gateway.review({"agent": "case"}, prompts[0], thread="chat"))
                    await asyncio.wait_for(entered[0].wait(), 1)
                    second = asyncio.create_task(gateway.review({"agent": "case"}, prompts[1], thread="chat"))
                    await asyncio.wait_for(entered[1].wait(), 1)
                    tasks = [first, second]
                    for index in completion_order:
                        finished[index].set()
                        await tasks[index]
                self.assertEqual(self.sent_sessions(client), [None, "initial", None])
                for call, prompt in zip(client.responses.create.await_args_list[1:], prompts, strict=True):
                    self.assertEqual(call.kwargs["input"], prompt)
                    self.assertFalse(call.kwargs["store"])
                self.assertEqual(len(gateway._sessions), 1)
                self.assertEqual(gateway._sessions[("chat", "case")][0],
                                 ("initial", "separate")[completion_order[-1]])

    async def test_exception_and_cancellation_discard_only_the_leased_session(self):
        for error in (RuntimeError("sensitive dependency message"), asyncio.CancelledError()):
            with self.subTest(error=type(error).__name__):
                gateway, client, modules = self.session_gateway([("completed", "s1"), ("completed", "other")])
                with modules:
                    await gateway.review({"agent": "case"}, "First", thread="chat")
                    await gateway.review({"agent": "case"}, "Other", thread="other-chat")
                    client.responses.create.side_effect = error
                    with self.assertRaises(type(error)):
                        await gateway.review({"agent": "case"}, "Follow up", thread="chat")
                    self.assertNotIn(("chat", "case"), gateway._sessions)
                    self.assertEqual(gateway._sessions[("other-chat", "case")][0], "other")
                    client.responses.create.side_effect = None
                    client.responses.create.return_value = SimpleNamespace(
                        status="completed", output_text="Finding", model_dump=lambda: {"output": []}, model_extra={})
                    await gateway.review({"agent": "case"}, "Retry", thread="chat")
                self.assertEqual(self.sent_sessions(client), [None, None, "s1", None])
                self.assertEqual(client.responses.create.await_count, 4)

    async def test_reuse_has_absolute_lifetime_even_when_response_omits_session(self):
        gateway, client, modules = self.session_gateway(
            [("completed", "s1"), ("completed", None), ("completed", None), ("completed", "s2")])
        now = [100.0]
        with modules, patch("app.time", SimpleNamespace(monotonic=lambda: now[0])):
            for moment in (100, 699, 700, 701):
                now[0] = moment
                await gateway.review({"agent": "case"}, "Review", thread="chat")
        self.assertEqual(self.sent_sessions(client), [None, "s1", None, None])
        self.assertEqual(gateway._sessions[("chat", "case")], ("s2", 701))

    async def test_session_finishing_after_its_window_is_not_cached(self):
        gateway, client, modules = self.session_gateway([])
        now = [100.0]

        async def respond(**kwargs):
            now[0] += 600
            return SimpleNamespace(status="completed", output_text="Finding", model_dump=lambda: {"output": []},
                                   model_extra={"agent_session_id": "slow-session"})

        client.responses.create.side_effect = respond
        with modules, patch("app.time", SimpleNamespace(monotonic=lambda: now[0])):
            await gateway.review({"agent": "case"}, "Review", thread="chat")
        self.assertEqual(gateway._sessions, {})

    async def test_eviction_recovers_without_history_loss_and_logs_only_counts(self):
        gateway, client, modules = self.session_gateway([("completed", f"private-session-{i}") for i in range(6)])
        now = [100.0]
        prompt = [{"role": "user", "content": "Private fictional prompt"},
                  {"role": "assistant", "content": "Private fictional response"},
                  {"role": "user", "content": "Follow up"}]
        with modules, patch("app.time", SimpleNamespace(monotonic=lambda: now[0])), patch("app.MAX_REUSED_SESSIONS", 2), \
                self.assertLogs("uvicorn.error", level="INFO") as logs:
            for thread in ("private-chat-1", "private-chat-2", "private-chat-3", "private-chat-1"):
                await gateway.review({"agent": "private-agent"}, prompt, thread=thread)
            now[0] += 600
            await gateway.review({"agent": "private-agent"}, prompt, thread="private-chat-1")
            await gateway.review({"agent": "private-agent"}, prompt)
        self.assertEqual(self.sent_sessions(client), [None] * 6)
        self.assertEqual(gateway._sessions, {("private-chat-1", "private-agent"): ("private-session-4", 700)})
        events = [json.loads(record.getMessage()) for record in logs.records]
        self.assertEqual([event["reuse"] for event in events if event["event"] == "workbench_session"],
                         ["miss", "miss", "miss", "miss", "expired", "disabled"])
        self.assertEqual([event for event in events if event["event"] == "workbench_session_eviction"], [
            {"event": "workbench_session_eviction", "expired": 0, "capacity": 1, "cached_sessions": 2},
            {"event": "workbench_session_eviction", "expired": 0, "capacity": 1, "cached_sessions": 2},
            {"event": "workbench_session_eviction", "expired": 1, "capacity": 0, "cached_sessions": 1},
        ])
        self.assertNotIn("private", " ".join(logs.output).lower())
        for call in client.responses.create.await_args_list:
            self.assertEqual(call.kwargs["input"], prompt)
            self.assertFalse(call.kwargs["store"])

class LibraryPreviewTests(CapturedLabLogs, unittest.TestCase):
    def setUp(self):
        self.gateway = AsyncMock()
        self.gateway.review.return_value = ("completed", "Finding APP-1", [])
        self.gateway.preview.return_value = ("completed", "Preview answer", [])
        self.settings = Settings("private", "https://example.services.ai.azure.com/api/projects/test",
                                 ("testserver",), ("https://testserver",), unfinished_agents=True,
                                 creation=CreationSettings(False, "test-model", models={"reasoning": "reason-model"}))
        self.client = TestClient(create_app(self.settings, self.gateway))
        self.headers = {"X-Workbench-Request": "1", "Origin": "https://testserver"}

    def test_configuration_reports_preview_capability(self):
        self.assertEqual(self.client.get("/api/config").json()["library_preview"],
                         {"enabled": True, "reason": None, "agent": "lab-library-preview"})
        for settings, reason in ((replace(self.settings, library_preview=False), "not_enabled"),
                                 (replace(self.settings, creation=CreationSettings()), "model_not_configured")):
            config = TestClient(create_app(settings, self.gateway)).get("/api/config").json()
            self.assertEqual(config["library_preview"], {"enabled": False, "reason": reason, "agent": "lab-library-preview"})

    def test_preview_chat_uses_template_binding_without_publishing(self):
        response = self.client.post("/api/reviews", json={"agent_id": "library-document-analyst", "input": "Summarize"},
                                    headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["agent"], "lab-library-preview")
        self.assertEqual(response.json()["text"], "Preview answer")
        agent = self.gateway.preview.call_args.args[0]
        self.assertEqual((agent["template_id"], agent["preview"]), ("document-analyst", True))
        self.gateway.review.assert_not_called()

    def test_agent_designer_chat_uses_the_preview_path(self):
        response = self.client.post("/api/reviews", json={"agent_id": "library-agent-designer", "input": "Good morning"},
                                    headers=self.headers)
        self.assertEqual(response.status_code, 200)
        agent = self.gateway.preview.call_args.args[0]
        self.assertEqual((agent["template_id"], agent["tools"], agent["preview"]), ("agent-designer", {}, True))
        self.gateway.review.assert_not_called()
        disabled = TestClient(create_app(replace(self.settings, library_preview=False), self.gateway))
        response = disabled.post("/api/reviews", json={"agent_id": "library-agent-designer", "input": "Hi"},
                                 headers=self.headers)
        self.assertEqual((response.status_code, response.json()["error"]), (503, "library_preview_disabled"))

    def test_preview_receipts_are_verified_against_the_preview_binding(self):
        output = [{"type": "function_call", "call_id": "one", "name": "lookup_demo_request"},
                  {"type": "function_call_output", "call_id": "one", "output": json.dumps(
                      {"status": "succeeded", "agent": "lab-library-preview", "simulation": True, "output": "REQ-101"})}]
        self.gateway.preview.return_value = ("completed", "Answer", output)
        response = self.client.post("/api/reviews", json={"agent_id": "library-workflow-coordinator", "input": "Check REQ-101"},
                                    headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["receipts"][0]["verified"])

    def test_disabled_or_unknown_previews_are_rejected(self):
        body = {"agent_id": "library-document-analyst", "input": "Summarize"}
        disabled = TestClient(create_app(replace(self.settings, library_preview=False), self.gateway))
        response = disabled.post("/api/reviews", json=body, headers=self.headers)
        self.assertEqual((response.status_code, response.json()["error"]), (503, "library_preview_disabled"))
        response = self.client.post("/api/reviews", json={**body, "agent_id": "library-missing"}, headers=self.headers)
        self.assertEqual((response.status_code, response.json()["error"]), (400, "invalid_request"))
        self.gateway.preview.assert_not_called()

    def test_unfinished_previews_are_refused_unless_the_operator_allows_them(self):
        hidden = TestClient(create_app(replace(self.settings, unfinished_agents=False), self.gateway))
        body = {"agent_id": "library-document-analyst", "input": "Summarize"}
        response = hidden.post("/api/reviews", json=body, headers=self.headers)
        self.assertEqual((response.status_code, response.json()["error"]), (400, "invalid_request"))
        self.gateway.preview.assert_not_called()
        response = hidden.post("/api/reviews", json={**body, "agent_id": "library-document-intake"}, headers=self.headers)
        self.assertEqual(response.status_code, 200)

    def test_unfinished_flag_must_be_boolean_and_defaults_off(self):
        self.assertFalse(Settings("preview", "", ("localhost",), ("http://localhost",)).unfinished_agents)
        with self.assertRaisesRegex(ValueError, "Unfinished agent"):
            create_app(replace(self.settings, unfinished_agents="yes"), self.gateway)
        with patch.dict("os.environ", {"WORKBENCH_UNFINISHED_AGENTS_ENABLED": "maybe"}):
            with self.assertRaisesRegex(ValueError, "WORKBENCH_UNFINISHED_AGENTS_ENABLED"):
                Settings.from_env()
        with patch.dict("os.environ", {"WORKBENCH_UNFINISHED_AGENTS_ENABLED": "true"}):
            self.assertTrue(Settings.from_env().unfinished_agents)

    def test_preview_flag_must_be_boolean(self):
        with self.assertRaisesRegex(ValueError, "Library preview enablement"):
            create_app(replace(self.settings, library_preview="yes"), self.gateway)
        with patch.dict("os.environ", {"WORKBENCH_LIBRARY_PREVIEW_ENABLED": "maybe"}):
            with self.assertRaisesRegex(ValueError, "WORKBENCH_LIBRARY_PREVIEW_ENABLED"):
                Settings.from_env()

    def test_budget_alert_status_is_reported_in_private_mode_only(self):
        self.assertIs(self.client.get("/api/config").json()["budget_alerts"], False)
        enabled = replace(self.settings, budget_alerts=True)
        self.assertIs(TestClient(create_app(enabled, self.gateway)).get("/api/config").json()["budget_alerts"],
                      enabled.mode == "private")
        with self.assertRaisesRegex(ValueError, "Budget alert status"):
            create_app(replace(self.settings, budget_alerts="yes"), self.gateway)
        with patch.dict("os.environ", {"WORKBENCH_BUDGET_ALERTS_ENABLED": "maybe"}):
            with self.assertRaisesRegex(ValueError, "WORKBENCH_BUDGET_ALERTS_ENABLED"):
                Settings.from_env()
        with patch.dict("os.environ", {"WORKBENCH_BUDGET_ALERTS_ENABLED": "true"}):
            self.assertIs(Settings.from_env().budget_alerts, True)

    def test_foundry_portal_link_is_built_from_the_project_resource_id(self):
        self.assertIsNone(self.client.get("/api/config").json()["foundry_portal"])
        project = ("/subscriptions/aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee/resourceGroups/rg-lab"
                   "/providers/Microsoft.CognitiveServices/accounts/example/projects/test")
        linked = replace(self.settings, foundry_project_id=project)
        self.assertEqual(TestClient(create_app(linked, self.gateway)).get("/api/config").json()["foundry_portal"],
                         "https://ai.azure.com/nextgen/r/qqqqqru7TMyN3e7u7u7u7g,rg-lab,,example,test")
        self.assertIsNone(replace(linked, mode="preview", hosts=("localhost",), origins=("http://localhost",)).foundry_portal)
        for invalid in (project.replace("/projects/test", "/projects/other"), project.replace("example", "another"),
                        project.replace("aaaaaaaa-bbbb", "not-a-guid-0000"), project + "/extra", "https://ai.azure.com"):
            with self.assertRaisesRegex(ValueError, "WORKBENCH_FOUNDRY_PROJECT_ID"):
                create_app(replace(self.settings, foundry_project_id=invalid), self.gateway)
        with patch.dict("os.environ", {"WORKBENCH_FOUNDRY_PROJECT_ID": project}):
            self.assertEqual(Settings.from_env().foundry_project_id, project)


class ModelLimitTests(CapturedLabLogs, unittest.TestCase):
    """Chat turns are admitted per model deployment before any model call (#108)."""

    LIMITS = {"reason-model": {"requests_per_minute": 100, "tokens_per_minute": 6000},
              "test-model": {"requests_per_minute": 2, "tokens_per_minute": 100000}}
    ANSWERS = {"document-analyst": 1000, "workflow-coordinator": 3000}

    def setUp(self):
        self.gateway = AsyncMock()
        self.gateway.review.return_value = ("completed", "Finding APP-1", [])
        self.gateway.preview.return_value = ("completed", "Preview answer", [])
        self.settings = Settings("private", "https://example.services.ai.azure.com/api/projects/test",
                                 ("testserver",), ("https://testserver",), model_limits=self.LIMITS, unfinished_agents=True,
                                 creation=CreationSettings(False, "test-model", models={"reasoning": "reason-model"}))
        self.now = 100.0
        for patcher in (patch("app.measured_answer_tokens", return_value=self.ANSWERS),
                        patch("model_budget.time", SimpleNamespace(monotonic=lambda: self.now))):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.client = TestClient(create_app(self.settings, self.gateway))
        self.headers = {"X-Workbench-Request": "1", "Origin": "https://testserver"}

    def chat(self, agent_id="library-document-analyst", client=None):
        return (client or self.client).post("/api/reviews", json={"agent_id": agent_id, "input": "Summarize"},
                                            headers=self.headers)

    def fill_reason_model(self):
        for _ in range(6):
            self.assertEqual(self.chat().status_code, 200)

    def test_turns_below_the_limit_are_answered(self):
        self.fill_reason_model()
        self.assertEqual(self.gateway.preview.await_count, 6)

    def test_a_turn_over_the_limit_is_busy_before_any_model_call(self):
        self.fill_reason_model()
        response = self.chat()
        self.assertEqual((response.status_code, response.json()["error"]), (429, "busy"))
        self.assertEqual(response.headers["Retry-After"], "60")
        self.assertEqual(response.json()["request_id"], response.headers["X-Correlation-ID"])
        self.assertEqual(self.gateway.preview.await_count, 6)
        self.gateway.review.assert_not_called()

    def test_limits_are_per_deployment_so_a_busy_model_does_not_block_another(self):
        self.fill_reason_model()
        self.assertEqual(self.chat().status_code, 429)
        for _ in range(2):
            self.assertEqual(self.chat("library-workflow-coordinator").status_code, 200)
        self.assertEqual(self.gateway.preview.call_args.args[0]["template_id"], "workflow-coordinator")
        self.assertEqual(self.chat("library-workflow-coordinator").status_code, 429)
        self.assertEqual(self.chat().status_code, 429)
        self.assertEqual(self.gateway.preview.await_count, 8)

    def test_counters_recover_after_the_window_and_the_hint_counts_down(self):
        self.fill_reason_model()
        self.now = 130
        response = self.chat()
        self.assertEqual((response.status_code, response.headers["Retry-After"]), (429, "30"))
        self.now = 160
        self.assertEqual(self.chat().status_code, 200)
        self.assertEqual(self.gateway.preview.await_count, 7)

    def test_invalid_requests_do_not_spend_a_models_budget(self):
        for _ in range(5):
            self.assertEqual(self.chat().status_code, 200)
        self.assertEqual(self.chat("library-missing").status_code, 400)
        self.assertEqual(self.client.post("/api/reviews", json={}, headers=self.headers).status_code, 400)
        self.assertEqual(self.chat().status_code, 200)

    def test_prebuilt_agents_that_declare_no_model_are_not_budgeted(self):
        tiny = {name: {"requests_per_minute": 1, "tokens_per_minute": 1} for name in ("reason-model", "test-model")}
        client = TestClient(create_app(replace(self.settings, model_limits=tiny), self.gateway))
        for _ in range(5):
            self.assertEqual(self.chat("customer-review", client).status_code, 200)
        self.assertEqual(self.gateway.review.await_count, 5)

    def declaring_client(self, directory, models):
        """A client whose prebuilt agents declare a model deployment in agents.json (#232)."""
        agents = json.loads((Path(__file__).parent / "agents.json").read_text(encoding="utf-8"))
        for agent_id, model in models.items():
            next(agent for agent in agents if agent["id"] == agent_id)["model"] = model
        path = Path(directory) / "agents.json"
        path.write_text(json.dumps(agents), encoding="utf-8")
        return TestClient(create_app(replace(self.settings, agents_path=path,
                                            visible_agents=("customer-review", "application-review", "case-review")), self.gateway))

    def test_a_prebuilt_agent_that_declares_a_model_uses_that_deployments_budget(self):
        with TemporaryDirectory() as directory:
            client = self.declaring_client(directory, {"customer-review": "test-model", "application-review": "test-model",
                                                       "case-review": "reason-model"})
            self.assertEqual(self.chat("customer-review", client).status_code, 200)
            self.assertEqual(self.chat("application-review", client).status_code, 200)
            response = self.chat("customer-review", client)
            self.assertEqual((response.status_code, response.json()["error"]), (429, "busy"))
            self.assertEqual(self.gateway.review.await_count, 2)
            self.assertEqual(self.chat("case-review", client).status_code, 200)
            self.assertEqual(self.gateway.review.await_count, 3)
            self.now += 61
            self.assertEqual(self.chat("customer-review", client).status_code, 200)

    def test_the_declared_model_is_not_shown_to_the_browser(self):
        with TemporaryDirectory() as directory:
            client = self.declaring_client(directory, {"customer-review": "test-model"})
            self.assertTrue(all("model" not in agent for agent in client.get("/api/config").json()["agents"]))

    def test_an_agent_model_must_be_a_deployment_name(self):
        agent = self.client.get("/api/config").json()["agents"][0]
        with TemporaryDirectory() as directory:
            path = Path(directory) / "agents.json"
            for model in (None, 7, "", "bad name", "-leading", "a" * 129, ["gpt-4.1"]):
                with self.subTest(model=model):
                    path.write_text(json.dumps([{**agent, "model": model}]), encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, "Invalid agent model deployment"):
                        load_agents(path)
            path.write_text(json.dumps([{**agent, "model": "gpt-4.1"}]), encoding="utf-8")
            self.assertEqual(load_agents(path)[0]["model"], "gpt-4.1")

    def test_no_limits_leaves_only_the_global_caps(self):
        client = TestClient(create_app(replace(self.settings, model_limits={}), self.gateway))
        for _ in range(8):
            self.assertEqual(self.chat(client=client).status_code, 200)

    def test_a_model_busy_answer_is_logged_without_content(self):
        self.fill_reason_model()
        with self.assertLogs("uvicorn.error", level="INFO") as captured:
            self.client.post("/api/reviews", json={"agent_id": "library-document-analyst", "input": "private customer prompt"},
                             headers=self.headers)
        events = [json.loads(record.getMessage()) for record in captured.records]
        busy = next(event for event in events if event["event"] == "workbench_model_busy")
        self.assertEqual(busy, {"event": "workbench_model_busy", "deployment": "reason-model",
                                "template_id": "document-analyst", "retry_after": 60})
        self.assertEqual((events[-1]["status"], events[-1]["outcome"]), (429, "busy"))
        self.assertNotIn("private", " ".join(captured.output))

    def test_configuration_is_read_from_the_environment(self):
        with patch.dict("os.environ", {"WORKBENCH_MODEL_LIMITS": json.dumps(self.LIMITS)}):
            self.assertEqual(Settings.from_env().model_limits, self.LIMITS)
        with patch.dict("os.environ", {"WORKBENCH_MODEL_LIMITS": ""}):
            self.assertEqual(Settings.from_env().model_limits, {})
        with patch.dict("os.environ", {"WORKBENCH_MODEL_LIMITS": "{not json"}):
            with self.assertRaisesRegex(ValueError, "WORKBENCH_MODEL_LIMITS must be a JSON object"):
                Settings.from_env()

    def test_invalid_limits_stop_the_lab_from_starting_with_a_clear_message(self):
        good = {"requests_per_minute": 10, "tokens_per_minute": 1000}
        for limits in ([], {"bad name": good}, {"test-model": {"requests_per_minute": 10}},
                       {"test-model": {**good, "tokens_per_minute": 0}}, {"test-model": {**good, "requests_per_minute": True}},
                       {"test-model": {**good, "tokens_per_minute": "1000"}}):
            with self.subTest(limits=limits):
                with self.assertRaisesRegex(ValueError, "WORKBENCH_MODEL_LIMITS"):
                    create_app(replace(self.settings, model_limits=limits), self.gateway)


class LibraryPreviewGatewayTests(CapturedLabLogs, unittest.IsolatedAsyncioTestCase):
    async def test_preview_calls_the_profile_model_directly(self):
        response = SimpleNamespace(status="completed", output_text="Preview", model_dump=lambda **_: {"output": []})
        openai_client = MagicMock()
        openai_client.responses.create = AsyncMock(return_value=response)
        project, pool = MagicMock(close=AsyncMock()), MagicMock(aclose=AsyncMock())
        project.get_openai_client.return_value = openai_client
        modules = {
            "azure.ai.projects.aio": SimpleNamespace(AIProjectClient=MagicMock(return_value=project)),
            "azure.identity.aio": SimpleNamespace(ManagedIdentityCredential=MagicMock(return_value=MagicMock(close=AsyncMock()))),
            "openai": SimpleNamespace(DefaultAsyncHttpxClient=MagicMock(return_value=pool)),
        }
        settings = Settings("private", "https://example.services.ai.azure.com/api/projects/test",
                            ("testserver",), ("https://testserver",),
                            creation=CreationSettings(False, "test-model", models={"reasoning": "reason-model"}))
        gateway = FoundryGateway(settings)
        agent = {"template_id": "document-analyst", "model_profile": "reasoning"}
        with patch.dict(sys.modules, modules):
            self.assertEqual(await gateway.preview(agent, "Summarize"), ("completed", "Preview", []))
        self.assertEqual(project.get_openai_client.call_args.kwargs,
                         {"timeout": settings.timeout, "max_retries": 0, "http_client": pool})
        options = openai_client.responses.create.await_args.kwargs
        self.assertEqual(options["model"], "reason-model")
        self.assertFalse(options["store"])
        openai_client.close.assert_not_called()
        await gateway.close()


if __name__ == "__main__":
    unittest.main()
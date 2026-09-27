import asyncio
import importlib.util
import json
import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch


def load_main_module():
    agent_framework = ModuleType("agent_framework")
    agent_framework.Agent = object
    foundry = ModuleType("agent_framework.foundry")
    foundry.FoundryChatClient = object
    hosting = ModuleType("agent_framework_foundry_hosting")
    hosting.ResponsesHostServer = object
    projects = ModuleType("azure.ai.projects.aio")
    projects.AIProjectClient = MagicMock()
    identity = ModuleType("azure.identity.aio")
    identity.DefaultAzureCredential = object

    modules = {
        "agent_framework": agent_framework,
        "agent_framework.foundry": foundry,
        "agent_framework_foundry_hosting": hosting,
        "azure": ModuleType("azure"),
        "azure.ai": ModuleType("azure.ai"),
        "azure.ai.projects": ModuleType("azure.ai.projects"),
        "azure.ai.projects.aio": projects,
        "azure.identity": ModuleType("azure.identity"),
        "azure.identity.aio": identity,
    }
    with patch.dict(sys.modules, modules):
        path = Path(__file__).with_name("main.py")
        spec = importlib.util.spec_from_file_location("review_coordinator_main", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


class CoordinatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_main_module()

    def mock_clients(self, response=None, side_effect=None):
        openai_client = MagicMock()
        openai_client.close = AsyncMock()
        openai_client.responses.create = AsyncMock(return_value=response, side_effect=side_effect)
        project_client = MagicMock()
        project_client.close = AsyncMock()
        project_client.get_openai_client.return_value = openai_client
        self.module.AIProjectClient.reset_mock()
        self.module.AIProjectClient.return_value = project_client
        return project_client, openai_client

    def test_invoke_specialist_returns_response_text(self) -> None:
        project_client, openai_client = self.mock_clients(SimpleNamespace(
            output_text="  grounded finding  ", status="completed"
        ))
        clients = self.module.SpecialistClients("https://project.example", object())

        result = asyncio.run(self.module.invoke_specialist(clients, "application-review-agent", "review"))

        self.assertEqual(result, "grounded finding")
        project_client.get_openai_client.assert_called_once_with(
            agent_name="application-review-agent", timeout=90, max_retries=0
        )
        openai_client.responses.create.assert_awaited_once_with(input="review", store=False)

    def test_specialist_clients_are_reused_until_closed(self) -> None:
        async def run_check():
            project_client, openai_client = self.mock_clients(SimpleNamespace(output_text="finding", status="completed"))
            async with self.module.SpecialistClients("https://project.example", "credential") as clients:
                for agent_name in ("application-review-agent", "application-review-agent", "case-review-agent"):
                    await self.module.invoke_specialist(clients, agent_name, "review")
                self.module.AIProjectClient.assert_called_once_with(
                    endpoint="https://project.example", credential="credential", allow_preview=True
                )
                self.assertEqual(
                    [call.kwargs["agent_name"] for call in project_client.get_openai_client.call_args_list],
                    ["application-review-agent", "case-review-agent"],
                )
                openai_client.close.assert_not_awaited()
        asyncio.run(run_check())

    @staticmethod
    def session_response(session_id="session-1", status="completed"):
        return SimpleNamespace(output_text="finding", status=status, model_extra={"agent_session_id": session_id})

    @staticmethod
    def sent_sessions(openai_client):
        return [(call.kwargs.get("extra_body") or {}).get("agent_session_id")
                for call in openai_client.responses.create.await_args_list]

    def test_completed_specialist_session_is_reused_per_specialist(self) -> None:
        async def run_check():
            _, openai_client = self.mock_clients(self.session_response())
            clients = self.module.SpecialistClients("endpoint", object())
            for agent_name in ("application-review-agent", "application-review-agent", "case-review-agent"):
                await self.module.invoke_specialist(clients, agent_name, "review")
            self.assertEqual(self.sent_sessions(openai_client), [None, "session-1", None])
            openai_client.responses.create.assert_awaited_with(input="review", store=False)

        asyncio.run(run_check())

    def test_session_reuse_expires_and_can_be_disabled(self) -> None:
        async def second_session(reuse_seconds, elapsed):
            now = [100.0]
            _, openai_client = self.mock_clients(self.session_response())
            clients = self.module.SpecialistClients("endpoint", object(), reuse_seconds=reuse_seconds)
            with patch.object(self.module, "time", SimpleNamespace(monotonic=lambda: now[0])):
                await self.module.invoke_specialist(clients, "case-review-agent", "review")
                now[0] += elapsed
                await self.module.invoke_specialist(clients, "case-review-agent", "review")
            return self.sent_sessions(openai_client)[1]

        self.assertEqual(asyncio.run(second_session(600, 599)), "session-1")
        self.assertIsNone(asyncio.run(second_session(600, 600)))
        self.assertIsNone(asyncio.run(second_session(0, 0)))

    def test_failed_call_discards_its_session(self) -> None:
        async def run_check():
            _, openai_client = self.mock_clients(side_effect=[
                self.session_response(), RuntimeError("unavailable"), self.session_response("session-2"),
                self.session_response("session-2", status="failed"), self.session_response("session-3"),
            ])
            clients = self.module.SpecialistClients("endpoint", object())
            for expected in (None, "unavailable", None, "did not complete", None):
                if expected is None:
                    await self.module.invoke_specialist(clients, "case-review-agent", "review")
                else:
                    with self.assertRaisesRegex(RuntimeError, expected):
                        await self.module.invoke_specialist(clients, "case-review-agent", "review")
            self.assertEqual(self.sent_sessions(openai_client), [None, "session-1", None, "session-2", None])

        asyncio.run(run_check())

    def test_concurrent_calls_do_not_share_a_session(self) -> None:
        async def run_check():
            release = asyncio.Event()
            new_sessions = iter(("session-1", "session-2"))

            async def respond(**kwargs):
                await release.wait()
                return self.session_response((kwargs.get("extra_body") or {}).get("agent_session_id")
                                             or next(new_sessions))

            _, openai_client = self.mock_clients(side_effect=respond)
            clients = self.module.SpecialistClients("endpoint", object())
            release.set()
            await self.module.invoke_specialist(clients, "case-review-agent", "review")
            for _ in range(2):
                release.clear()
                calls = [asyncio.create_task(self.module.invoke_specialist(clients, "case-review-agent", "review"))
                         for _ in range(2)]
                await asyncio.sleep(0)
                release.set()
                await asyncio.gather(*calls)
            sessions = self.sent_sessions(openai_client)
            self.assertEqual(sessions[:3], [None, "session-1", None])
            self.assertEqual(sorted(sessions[3:]), ["session-1", "session-2"])

        asyncio.run(run_check())

    def test_invalid_session_reuse_window_fails_before_serving(self) -> None:
        for value in ("nan", "-1", "3601", "later"):
            with self.subTest(value=value), patch.dict(
                self.module.os.environ, {"SPECIALIST_SESSION_REUSE_SECONDS": value}
            ):
                with self.assertRaises(ValueError):
                    self.module.SpecialistClients("endpoint", object())

    def test_invoke_specialist_rejects_empty_response(self) -> None:
        self.mock_clients(SimpleNamespace(output_text=" ", status="completed"))
        clients = self.module.SpecialistClients("https://project.example", object())

        with self.assertRaisesRegex(RuntimeError, "returned an empty response"):
            asyncio.run(self.module.invoke_specialist(clients, "case-review-agent", "review"))

    def test_tools_route_to_configured_specialists(self) -> None:
        with (
            patch.dict(
                self.module.os.environ,
                {
                    "APPLICATION_REVIEW_AGENT_NAME": "applications",
                    "CASE_REVIEW_AGENT_NAME": "cases",
                },
            ),
            patch.object(
                self.module,
                "invoke_specialist",
                return_value="finding",
            ) as invoke,
        ):
            application_tool, case_tool = self.module.create_specialist_tools("clients")
            self.assertEqual(json.loads(asyncio.run(application_tool("application"))),
                             {"status": "succeeded", "agent": "applications", "output": "finding"})
            self.assertEqual(json.loads(asyncio.run(case_tool("case"))),
                             {"status": "succeeded", "agent": "cases", "output": "finding"})

        self.assertEqual(
            [call.args[:3] for call in invoke.call_args_list],
            [("clients", "applications", "application"), ("clients", "cases", "case")],
        )

    def test_timeout_cancels_request_and_releases_slot(self) -> None:
        async def run_check():
            cancelled = asyncio.Event()

            async def slow_response(**kwargs):
                try:
                    await asyncio.Event().wait()
                finally:
                    cancelled.set()

            _, openai_client = self.mock_clients(side_effect=slow_response)
            clients = self.module.SpecialistClients("endpoint", object())
            with patch.dict(self.module.os.environ, {
                "SPECIALIST_TIMEOUT_SECONDS": "0.05", "SPECIALIST_MAX_CONCURRENCY": "1"
            }):
                application_tool, case_tool = self.module.create_specialist_tools(clients)
            with self.assertRaises(TimeoutError):
                await application_tool("request")
            self.assertTrue(cancelled.is_set())
            openai_client.responses.create.side_effect = None
            openai_client.responses.create.return_value = SimpleNamespace(output_text="finding", status="completed")
            self.assertEqual(json.loads(await case_tool("request"))["output"], "finding")
            await clients.close()
            self.assertEqual(openai_client.close.await_count, 2)

        asyncio.run(run_check())

    def test_registry_replaces_default_specialists(self) -> None:
        specialists = [
            {"tool": "check_inventory", "agent": "customer-inventory", "description": "Check supplied stock records."},
            {"tool": "check_shipping", "agent": "customer-shipping", "description": "Check supplied shipment records."},
        ]
        with patch.dict(self.module.os.environ, {"SPECIALIST_CONFIG": json.dumps(specialists)}), patch.object(
            self.module, "invoke_specialist", return_value="finding"
        ) as invoke:
            tools = self.module.create_specialist_tools("clients")
            self.assertEqual([tool.__name__ for tool in tools], [item["tool"] for item in specialists])
            for tool, specialist in zip(tools, specialists, strict=True):
                self.assertEqual(tool.__doc__, specialist["description"])
                self.assertEqual(json.loads(asyncio.run(tool("source")))["agent"], specialist["agent"])
            self.assertEqual([call.args[1] for call in invoke.call_args_list], [item["agent"] for item in specialists])

    def test_invalid_registry_fails_before_serving(self) -> None:
        entry = {"tool": "review", "agent": "specialist", "description": "Review evidence."}
        for registry in ([], {}, [entry, entry], [{**entry, "agent": "https://unapproved.example"}],
                         [{**entry, "agent": "review-coordinator-agent"}],
                         [{**entry, "tool": "bad tool"}], [{**entry, "description": " "}],
                         [{**entry, "endpoint": "override"}]):
            with self.subTest(registry=registry), patch.dict(self.module.os.environ, {"SPECIALIST_CONFIG": json.dumps(registry)}):
                with self.assertRaises(ValueError):
                    self.module.create_specialist_tools("clients")

    def test_concurrency_is_shared_between_specialists(self) -> None:
        async def run_check():
            active = 0
            peak = 0
            started = asyncio.Event()
            release = asyncio.Event()

            async def invoke(*args):
                nonlocal active, peak
                active += 1
                peak = max(peak, active)
                started.set()
                try:
                    await release.wait()
                    return "finding"
                finally:
                    active -= 1

            with patch.dict(self.module.os.environ, {"SPECIALIST_MAX_CONCURRENCY": "1"}), patch.object(
                self.module, "invoke_specialist", side_effect=invoke
            ):
                application_tool, case_tool = self.module.create_specialist_tools("clients")
                tasks = [asyncio.create_task(tool("request")) for tool in (application_tool, case_tool)]
                await asyncio.wait_for(started.wait(), 1)
                release.set()
                self.assertEqual([json.loads(result)["output"] for result in await asyncio.gather(*tasks)],
                                 ["finding", "finding"])
                self.assertEqual(peak, 1)

        asyncio.run(run_check())

    def test_invalid_limits_fail_before_serving(self) -> None:
        for settings in (
            {"SPECIALIST_TIMEOUT_SECONDS": "nan"},
            {"SPECIALIST_TIMEOUT_SECONDS": "0"},
            {"SPECIALIST_MAX_CONCURRENCY": "0"},
        ):
            with self.subTest(settings=settings), patch.dict(self.module.os.environ, settings):
                with self.assertRaises(ValueError):
                    self.module.create_specialist_tools("clients")

    def test_nonempty_failed_specialist_is_rejected(self) -> None:
        self.mock_clients(SimpleNamespace(status="failed", output_text="partial output"))
        clients = self.module.SpecialistClients("endpoint", object())
        with self.assertRaisesRegex(RuntimeError, "did not complete"):
            asyncio.run(self.module.invoke_specialist(clients, "case-review-agent", "review"))


if __name__ == "__main__":
    unittest.main()
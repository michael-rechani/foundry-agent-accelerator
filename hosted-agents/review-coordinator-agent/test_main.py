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

    def test_invoke_specialist_returns_response_text(self) -> None:
        openai_client = MagicMock()
        openai_client.__aenter__.return_value = openai_client
        openai_client.responses.create = AsyncMock(return_value=SimpleNamespace(
            output_text="  grounded finding  ", status="completed"
        ))
        project_client = MagicMock()
        project_client.__aenter__.return_value = project_client
        project_client.get_openai_client.return_value = openai_client
        self.module.AIProjectClient.return_value = project_client

        result = asyncio.run(self.module.invoke_specialist(
            "https://project.example", object(), "application-review-agent", "review"
        ))

        self.assertEqual(result, "grounded finding")
        project_client.get_openai_client.assert_called_once_with(
            agent_name="application-review-agent", timeout=90, max_retries=0
        )
        openai_client.responses.create.assert_awaited_once_with(input="review", store=False)

    def test_invoke_specialist_rejects_empty_response(self) -> None:
        openai_client = MagicMock()
        openai_client.__aenter__.return_value = openai_client
        openai_client.responses.create = AsyncMock(return_value=SimpleNamespace(output_text=" ", status="completed"))
        project_client = MagicMock()
        project_client.__aenter__.return_value = project_client
        project_client.get_openai_client.return_value = openai_client
        self.module.AIProjectClient.return_value = project_client

        with self.assertRaisesRegex(RuntimeError, "returned an empty response"):
            asyncio.run(self.module.invoke_specialist(
                "https://project.example", object(), "case-review-agent", "review"
            ))

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
            application_tool, case_tool = self.module.create_specialist_tools(
                "https://project.example", object()
            )
            self.assertEqual(json.loads(asyncio.run(application_tool("application"))),
                             {"status": "succeeded", "agent": "applications", "output": "finding"})
            self.assertEqual(json.loads(asyncio.run(case_tool("case"))),
                             {"status": "succeeded", "agent": "cases", "output": "finding"})

        self.assertEqual(
            [call.args[2:4] for call in invoke.call_args_list],
            [("applications", "application"), ("cases", "case")],
        )

    def test_timeout_closes_clients_and_releases_slot(self) -> None:
        async def run_check():
            cancelled = asyncio.Event()

            async def slow_response(**kwargs):
                try:
                    await asyncio.Event().wait()
                finally:
                    cancelled.set()

            openai_client = MagicMock()
            openai_client.__aenter__.return_value = openai_client
            openai_client.responses.create = AsyncMock(side_effect=slow_response)
            project_client = MagicMock()
            project_client.__aenter__.return_value = project_client
            project_client.get_openai_client.return_value = openai_client
            self.module.AIProjectClient.return_value = project_client
            with patch.dict(self.module.os.environ, {
                "SPECIALIST_TIMEOUT_SECONDS": "0.05", "SPECIALIST_MAX_CONCURRENCY": "1"
            }):
                application_tool, case_tool = self.module.create_specialist_tools("endpoint", object())
            with self.assertRaises(TimeoutError):
                await application_tool("request")
            self.assertTrue(cancelled.is_set())
            openai_client.__aexit__.assert_awaited_once()
            project_client.__aexit__.assert_awaited_once()
            openai_client.responses.create.side_effect = None
            openai_client.responses.create.return_value = SimpleNamespace(output_text="finding", status="completed")
            self.assertEqual(json.loads(await case_tool("request"))["output"], "finding")

        asyncio.run(run_check())

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
                application_tool, case_tool = self.module.create_specialist_tools("endpoint", object())
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
                    self.module.create_specialist_tools("endpoint", object())

    def test_nonempty_failed_specialist_is_rejected(self) -> None:
        openai_client = MagicMock()
        openai_client.__aenter__.return_value = openai_client
        openai_client.responses.create = AsyncMock(return_value=SimpleNamespace(
            status="failed", output_text="partial output"
        ))
        project_client = MagicMock()
        project_client.__aenter__.return_value = project_client
        project_client.get_openai_client.return_value = openai_client
        self.module.AIProjectClient.return_value = project_client
        with self.assertRaisesRegex(RuntimeError, "did not complete"):
            asyncio.run(self.module.invoke_specialist("endpoint", object(), "case-review-agent", "review"))


if __name__ == "__main__":
    unittest.main()
"""Pin what each hosted agent's main() does at start-up, with the SDKs stubbed.

The basic-responses, case-review and application-review agents each carry their
own copy of this start-up. These tests state the shared contract, so a later
change that moves the copies into one helper can't alter it unnoticed. The
review coordinator has its own test, and knowledge_main.py is covered next to
the retrieval tests in test_knowledge_retrieval.py.
"""

import asyncio
import importlib.util
import os
import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

HOSTED = Path(__file__).resolve().parent
ENVIRONMENT = {
    "FOUNDRY_PROJECT_ENDPOINT": "https://example.services.ai.azure.com/api/projects/test",
    "FOUNDRY_MODEL_NAME": "model",
}
MESSAGE = "FOUNDRY_PROJECT_ENDPOINT and FOUNDRY_MODEL_NAME must both be set"

# folder, default agent name, whether the quotation check wraps the model client
AGENTS = (
    ("basic-responses-agent", "basic-responses-agent", False),
    ("case-review-agent", "case-review-agent", True),
    ("application-review-agent", "application-review-agent", True),
)


def run_main(folder, environ):
    """Run a hosted agent's main() against stubbed SDKs and return what it built."""
    credential = MagicMock(name="credential")
    identity = ModuleType("azure.identity")
    identity.DefaultAzureCredential = MagicMock(name="DefaultAzureCredential")
    identity.DefaultAzureCredential.return_value.__enter__.return_value = credential
    framework = ModuleType("agent_framework")
    framework.Agent = MagicMock(name="Agent")
    foundry = ModuleType("agent_framework.foundry")
    foundry.FoundryChatClient = MagicMock(name="FoundryChatClient")
    hosting = ModuleType("agent_framework_foundry_hosting")
    hosting.ResponsesHostServer = MagicMock(name="ResponsesHostServer")
    hosting.ResponsesHostServer.return_value.run_async = AsyncMock()
    modules = {
        "agent_framework": framework, "agent_framework.foundry": foundry,
        "agent_framework_foundry_hosting": hosting, "azure": ModuleType("azure"), "azure.identity": identity,
    }
    path = HOSTED / folder / "main.py"
    with (patch.dict(sys.modules, modules), patch.dict(os.environ, environ, clear=True),
          patch("review_output.quotation_middleware", return_value="quotation-check")):
        spec = importlib.util.spec_from_file_location(f"startup_under_test_{folder.replace('-', '_')}", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        asyncio.run(module.main())
    return SimpleNamespace(
        agent=framework.Agent, client=foundry.FoundryChatClient, identity=identity.DefaultAzureCredential,
        credential=credential, server=hosting.ResponsesHostServer,
    )


class HostedStartupTests(unittest.TestCase):
    def test_both_settings_are_required_before_anything_is_opened(self):
        partial = (
            {}, {"FOUNDRY_PROJECT_ENDPOINT": ENVIRONMENT["FOUNDRY_PROJECT_ENDPOINT"]},
            {"FOUNDRY_MODEL_NAME": "model"}, {**ENVIRONMENT, "FOUNDRY_MODEL_NAME": ""},
            {**ENVIRONMENT, "FOUNDRY_PROJECT_ENDPOINT": ""},
        )
        for folder, _, _ in AGENTS:
            for environ in partial:
                with self.subTest(agent=folder, environ=sorted(environ)):
                    with self.assertRaisesRegex(RuntimeError, MESSAGE):
                        run_main(folder, environ)

    def test_defaults_build_one_agent_and_serve_it(self):
        for folder, name, checked in AGENTS:
            with self.subTest(agent=folder):
                built = run_main(folder, ENVIRONMENT)
                built.identity.assert_called_once_with()
                built.identity.return_value.__exit__.assert_called_once()
                expected_client = {
                    "project_endpoint": ENVIRONMENT["FOUNDRY_PROJECT_ENDPOINT"], "model": "model",
                    "credential": built.credential, "allow_preview": True,
                }
                if checked:
                    expected_client["middleware"] = ["quotation-check"]
                built.client.assert_called_once_with(**expected_client)
                instructions = (HOSTED / folder / "instructions.md").read_text(encoding="utf-8")
                built.agent.assert_called_once_with(
                    client=built.client.return_value, name=name, instructions=instructions,
                    default_options={"store": False},
                )
                built.server.assert_called_once_with(built.agent.return_value)
                built.server.return_value.run_async.assert_awaited_once_with()

    def test_name_and_instructions_can_be_overridden(self):
        environ = {**ENVIRONMENT, "AGENT_NAME": "renamed-agent", "AGENT_INSTRUCTIONS": "Use only supplied text."}
        for folder, _, _ in AGENTS:
            with self.subTest(agent=folder):
                kwargs = run_main(folder, environ).agent.call_args.kwargs
                self.assertEqual((kwargs["name"], kwargs["instructions"]), ("renamed-agent", "Use only supplied text."))

    def test_responses_are_stored_only_when_the_setting_is_true(self):
        for value, stored in (("true", True), ("TRUE", True), ("True", True), ("false", False), ("", False),
                              ("yes", False), ("1", False), ("truee", False)):
            for folder, _, _ in AGENTS:
                with self.subTest(agent=folder, value=value):
                    environ = {**ENVIRONMENT, "AGENT_STORE_RESPONSES": value}
                    options = run_main(folder, environ).agent.call_args.kwargs["default_options"]
                    self.assertEqual(options, {"store": stored})


if __name__ == "__main__":
    unittest.main()

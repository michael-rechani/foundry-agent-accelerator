"""Pin what each hosted agent's main() does at start-up, with the SDKs stubbed.

The basic-responses agent keeps its own copy of the start-up so it stays one file
to read. The review agents, the coordinator and the knowledge overlay share
hosted_runtime.py. These tests state the contract they all follow, so a change to
either route can't alter it unnoticed. The packaged tests run each built package
with only its own files importable, because a hosted agent is uploaded as a
standalone zip and a missing shared file would fail only after deployment.
knowledge_main.py is also covered next to the retrieval tests in
test_knowledge_retrieval.py.
"""

import asyncio
import importlib.util
import os
import sys
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from zipfile import ZipFile

import deployment

HOSTED = Path(__file__).resolve().parent
ENVIRONMENT = {
    "FOUNDRY_PROJECT_ENDPOINT": "https://example.services.ai.azure.com/api/projects/test",
    "FOUNDRY_MODEL_NAME": "model",
}
MESSAGE = "FOUNDRY_PROJECT_ENDPOINT and FOUNDRY_MODEL_NAME must both be set"
SHARED_MODULES = ("hosted_runtime", "review_output", "knowledge_retrieval", "configuration")

# folder, default agent name, whether the quotation check wraps the model client
AGENTS = (
    ("basic-responses-agent", "basic-responses-agent", False),
    ("case-review-agent", "case-review-agent", True),
    ("application-review-agent", "application-review-agent", True),
)
SHARED_RUNTIME_AGENTS = AGENTS[1:]


def sdk_stubs():
    """Stub the SDK modules a hosted agent imports and return them with the mocks to inspect."""
    credential = MagicMock(name="credential")
    identity = ModuleType("azure.identity")
    identity.DefaultAzureCredential = MagicMock(name="DefaultAzureCredential")
    identity.DefaultAzureCredential.return_value.__enter__.return_value = credential
    async_identity = ModuleType("azure.identity.aio")
    async_credential = MagicMock(name="AsyncDefaultAzureCredential")
    async_credential.return_value.__aenter__ = AsyncMock(return_value=credential)
    async_credential.return_value.__aexit__ = AsyncMock(return_value=None)
    async_identity.DefaultAzureCredential = async_credential
    framework = ModuleType("agent_framework")
    framework.Agent = MagicMock(name="Agent")
    framework.chat_middleware = lambda function: function
    for name in ("ChatResponse", "ChatResponseUpdate", "Content", "Message", "ResponseStream"):
        setattr(framework, name, MagicMock(name=name))
    foundry = ModuleType("agent_framework.foundry")
    foundry.FoundryChatClient = MagicMock(name="FoundryChatClient")
    hosting = ModuleType("agent_framework_foundry_hosting")
    hosting.ResponsesHostServer = MagicMock(name="ResponsesHostServer")
    hosting.ResponsesHostServer.return_value.run_async = AsyncMock()
    projects = ModuleType("azure.ai.projects.aio")
    projects.AIProjectClient = MagicMock(name="AIProjectClient")
    modules = {
        "agent_framework": framework, "agent_framework.foundry": foundry,
        "agent_framework_foundry_hosting": hosting, "azure": ModuleType("azure"), "azure.identity": identity,
        "azure.identity.aio": async_identity, "azure.ai": ModuleType("azure.ai"),
        "azure.ai.projects": ModuleType("azure.ai.projects"), "azure.ai.projects.aio": projects,
    }
    built = SimpleNamespace(
        agent=framework.Agent, client=foundry.FoundryChatClient, identity=identity.DefaultAzureCredential,
        async_identity=async_credential, credential=credential, server=hosting.ResponsesHostServer,
    )
    return modules, built


def load_and_run(path):
    spec = importlib.util.spec_from_file_location(f"startup_under_test_{path.parent.name.replace('-', '_')}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    asyncio.run(module.main())


def optimizer_stubs(source, instructions="Candidate instructions.", model="candidate-model", skills=""):
    """Stub azure.ai.agentserver.optimization so load_config() returns a candidate from the given source."""
    config = SimpleNamespace(source=source, model=model, compose_instructions=lambda: instructions + skills)
    package = ModuleType("azure.ai.agentserver.optimization")
    package.load_config = MagicMock(name="load_config", return_value=config)
    return {"azure.ai.agentserver": ModuleType("azure.ai.agentserver"), "azure.ai.agentserver.optimization": package}


def run_main(folder, environ, extra_modules=None):
    """Run a hosted agent's main() against stubbed SDKs and return what it built."""
    modules, built = sdk_stubs()
    modules.update(extra_modules or {})
    with (patch.dict(sys.modules, modules), patch.dict(os.environ, environ, clear=True),
          patch("review_output.quotation_middleware", return_value="quotation-check")):
        load_and_run(HOSTED / folder / "main.py")
    return built


def run_packaged(files, environ):
    """Run a built package's main() with only the package's own files importable."""
    modules, built = sdk_stubs()
    with tempfile.TemporaryDirectory() as folder:
        for name, content in files.items():
            (Path(folder) / name).write_bytes(content)
        elsewhere = [entry for entry in sys.path if Path(entry or ".").resolve() != HOSTED]
        with (patch.dict(sys.modules, modules), patch.dict(os.environ, environ, clear=True),
              patch.object(sys, "path", [folder, *elsewhere])):
            for name in SHARED_MODULES:
                sys.modules.pop(name, None)
            load_and_run(Path(folder) / "main.py")
    return built


def packaged_files(folder):
    output = BytesIO()
    deployment.create_package(HOSTED / folder, output)
    with ZipFile(output) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


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

    def test_a_missing_setting_opens_no_credential(self):
        for folder, _, _ in AGENTS:
            with self.subTest(agent=folder):
                modules, built = sdk_stubs()
                with (patch.dict(sys.modules, modules), patch.dict(os.environ, {}, clear=True),
                      patch("review_output.quotation_middleware", return_value="quotation-check")):
                    with self.assertRaisesRegex(RuntimeError, MESSAGE):
                        load_and_run(HOSTED / folder / "main.py")
                built.identity.assert_not_called()
                built.agent.assert_not_called()

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

    def test_an_active_optimizer_candidate_replaces_instructions_and_model(self):
        environ = {**ENVIRONMENT, "AGENT_INSTRUCTIONS": "Deployed instructions."}
        for folder, _, _ in SHARED_RUNTIME_AGENTS:
            for source in ("env:OPTIMIZATION_CONFIG", "api:candidate:c1"):
                with self.subTest(agent=folder, source=source):
                    built = run_main(folder, environ, optimizer_stubs(source, skills="\n- skill"))
                    self.assertEqual(built.agent.call_args.kwargs["instructions"], "Candidate instructions.\n- skill")
                    self.assertEqual(built.client.call_args.kwargs["model"], "candidate-model")

    def test_the_baseline_folder_and_a_missing_candidate_change_nothing(self):
        environ = {**ENVIRONMENT, "AGENT_INSTRUCTIONS": "Deployed instructions."}
        for folder, _, _ in SHARED_RUNTIME_AGENTS:
            for label, extra in (("baseline", optimizer_stubs("local:/agent/.agent_configs/baseline")),
                                 ("none", optimizer_stubs("")), ("not installed", {})):
                with self.subTest(agent=folder, config=label):
                    built = run_main(folder, environ, extra)
                    self.assertEqual(built.agent.call_args.kwargs["instructions"], "Deployed instructions.")
                    self.assertEqual(built.client.call_args.kwargs["model"], "model")

    def test_a_candidate_without_instructions_or_model_keeps_the_deployed_ones(self):
        environ = {**ENVIRONMENT, "AGENT_INSTRUCTIONS": "Deployed instructions."}
        built = run_main("case-review-agent", environ, optimizer_stubs("env:OPTIMIZATION_CONFIG", "", None))
        self.assertEqual(built.agent.call_args.kwargs["instructions"], "Deployed instructions.")
        self.assertEqual(built.client.call_args.kwargs["model"], "model")

    def test_optimizer_files_stay_out_of_the_deployed_package(self):
        for folder, _, _ in SHARED_RUNTIME_AGENTS:
            with self.subTest(agent=folder):
                self.assertTrue((HOSTED / folder / ".agent_configs" / "baseline" / "metadata.yaml").is_file())
                names = set(packaged_files(folder))
                self.assertFalse({"eval.yaml", "eval.jsonl"} & names)
                self.assertFalse([name for name in names if ".agent_configs" in name])

    def test_responses_are_stored_only_when_the_setting_is_true(self):
        for value, stored in (("true", True), ("TRUE", True), ("True", True), ("false", False), ("", False),
                              ("yes", False), ("1", False), ("truee", False)):
            for folder, _, _ in AGENTS:
                with self.subTest(agent=folder, value=value):
                    environ = {**ENVIRONMENT, "AGENT_STORE_RESPONSES": value}
                    options = run_main(folder, environ).agent.call_args.kwargs["default_options"]
                    self.assertEqual(options, {"store": stored})


class PackagedStartupTests(unittest.TestCase):
    def test_review_packages_start_from_their_own_files_alone(self):
        for folder, name, _ in SHARED_RUNTIME_AGENTS:
            with self.subTest(agent=folder):
                files = packaged_files(folder)
                self.assertIn("hosted_runtime.py", files)
                built = run_packaged(files, ENVIRONMENT)
                kwargs = built.agent.call_args.kwargs
                self.assertEqual((kwargs["name"], kwargs["default_options"]), (name, {"store": False}))
                self.assertEqual(len(built.client.call_args.kwargs["middleware"]), 1)
                built.server.return_value.run_async.assert_awaited_once_with()

    def test_coordinator_package_starts_from_its_own_files_alone(self):
        files = packaged_files("review-coordinator-agent")
        built = run_packaged(files, ENVIRONMENT)
        kwargs = built.agent.call_args.kwargs
        self.assertEqual((kwargs["name"], kwargs["default_options"]), ("review-coordinator-agent", {"store": False}))
        self.assertEqual([tool.__name__ for tool in kwargs["tools"]], ["review_application", "review_case"])
        self.assertEqual(len(built.client.call_args.kwargs["middleware"]), 1)
        built.async_identity.assert_called_once_with()
        built.async_identity.return_value.__aexit__.assert_awaited_once()
        built.server.return_value.run_async.assert_awaited_once_with()

    def test_knowledge_package_starts_from_its_own_files_alone(self):
        files = {}
        with ZipFile(BytesIO(deployment.knowledge_package(HOSTED / "case-review-agent"))) as archive:
            files = {name: archive.read(name) for name in archive.namelist()}
        self.assertIn("hosted_runtime.py", files)
        built = run_packaged(files, ENVIRONMENT)
        kwargs = built.agent.call_args.kwargs
        self.assertEqual(kwargs["name"], "case-review-agent")
        self.assertNotIn("tools", kwargs)
        self.assertEqual(len(built.client.call_args.kwargs["middleware"]), 1)

    def test_a_package_without_the_shared_runtime_fails_at_import(self):
        files = packaged_files("case-review-agent")
        del files["hosted_runtime.py"]
        with self.assertRaises(ModuleNotFoundError):
            run_packaged(files, ENVIRONMENT)

    def test_basic_responses_package_stays_standalone(self):
        files = packaged_files("basic-responses-agent")
        self.assertEqual(set(files), {"main.py", "requirements.txt", "instructions.md"})
        built = run_packaged(files, ENVIRONMENT)
        self.assertNotIn("middleware", built.client.call_args.kwargs)


class HostedRuntimeTests(unittest.TestCase):
    def load_runtime(self):
        modules, built = sdk_stubs()
        with patch.dict(sys.modules, modules):
            sys.modules.pop("hosted_runtime", None)
            import hosted_runtime
        return hosted_runtime, built

    def test_settings_apply_the_defaults_and_overrides(self):
        runtime, _ = self.load_runtime()
        settings = runtime.agent_settings("default-name", "Default text.", ENVIRONMENT)
        self.assertEqual(tuple(settings), (ENVIRONMENT["FOUNDRY_PROJECT_ENDPOINT"], "model", "default-name",
                                           "Default text.", False))
        settings = runtime.agent_settings("default-name", "Default text.", {
            **ENVIRONMENT, "AGENT_NAME": "named", "AGENT_INSTRUCTIONS": "Other.", "AGENT_STORE_RESPONSES": "TRUE",
        })
        self.assertEqual((settings.name, settings.instructions, settings.store_responses), ("named", "Other.", True))

    def test_settings_require_both_foundry_values(self):
        runtime, _ = self.load_runtime()
        for environ in ({}, {"FOUNDRY_MODEL_NAME": "model"}, {**ENVIRONMENT, "FOUNDRY_PROJECT_ENDPOINT": ""}):
            with self.subTest(environ=sorted(environ)), self.assertRaisesRegex(RuntimeError, MESSAGE):
                runtime.agent_settings("name", "text", environ)

    def test_settings_read_the_process_environment_by_default(self):
        runtime, _ = self.load_runtime()
        with patch.dict(os.environ, {**ENVIRONMENT, "AGENT_NAME": "from-process"}, clear=True):
            self.assertEqual(runtime.agent_settings("name", "text").name, "from-process")

    def test_middleware_and_tools_are_passed_only_when_given(self):
        runtime, built = self.load_runtime()
        settings = runtime.agent_settings("name", "text", ENVIRONMENT)
        runtime.build_agent(built.credential, settings)
        self.assertNotIn("middleware", built.client.call_args.kwargs)
        self.assertNotIn("tools", built.agent.call_args.kwargs)
        built.client.reset_mock()
        built.agent.reset_mock()
        tool = object()
        runtime.build_agent(built.credential, settings, middleware=("check",), tools=[tool])
        self.assertEqual(built.client.call_args.kwargs["middleware"], ["check"])
        self.assertEqual(built.agent.call_args.kwargs["tools"], [tool])

    def test_serve_runs_the_responses_server(self):
        runtime, built = self.load_runtime()
        asyncio.run(runtime.serve("agent"))
        built.server.assert_called_once_with("agent")
        built.server.return_value.run_async.assert_awaited_once_with()


if __name__ == "__main__":
    unittest.main()
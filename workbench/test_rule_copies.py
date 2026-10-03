"""Checks that the copies of a rule that can't be shared still agree.

The Foundry project endpoint rule and the agent-name pattern are written out in code that ships on
its own (a hosted-agent zip, the offline evaluation tools, the Lab). One module can't serve all of
them, so each copy stays and this file feeds every copy the same examples. Change one copy and a
test here fails until the others match. Run in the workbench job, which installs every dependency.
"""
import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import app
from agent_runtime import main as runtime

ROOT = Path(__file__).resolve().parents[1]


def load(name, path, *search):
    """Import a module that lives outside workbench/, without leaving its imports behind."""
    with patch.dict(sys.modules), patch.object(sys, "path", [*(str(ROOT / folder) for folder in search), *sys.path]):
        spec = importlib.util.spec_from_file_location(name, ROOT / path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return module


bundle = load("rule_copies_bundle", "hosted-agents/bundle.py", "hosted-agents")
configuration = load("rule_copies_configuration", "hosted-agents/review-coordinator-agent/configuration.py")
library_runs = load("rule_copies_library_runs", "evaluations/library_runs.py", "evaluations")
run = load("rule_copies_run", "evaluations/run.py", "evaluations")

HOST = "lab.services.ai.azure.com"
GOOD_ENDPOINTS = (
    f"https://{HOST}/api/projects/lab",
    f"https://{HOST}:443/api/projects/lab",
    "https://LAB.services.ai.azure.com/api/projects/my_project-1",
)
BAD_ENDPOINTS = {
    "empty": "",
    "no scheme": f"{HOST}/api/projects/lab",
    "http": f"http://{HOST}/api/projects/lab",
    "not a Foundry host": "https://example.test/api/projects/lab",
    "Foundry name on someone else's host": f"https://{HOST}.example.test/api/projects/lab",
    "another Azure service": "https://lab.cognitiveservices.azure.com/api/projects/lab",
    "other port": f"https://{HOST}:8443/api/projects/lab",
    "port that isn't a number": f"https://{HOST}:abc/api/projects/lab",
    "port out of range": f"https://{HOST}:99999/api/projects/lab",
    "user name": f"https://user@{HOST}/api/projects/lab",
    "user name and password": f"https://user:secret@{HOST}/api/projects/lab",
    "password only": f"https://:secret@{HOST}/api/projects/lab",
    "path parameters": f"https://{HOST}/api/projects/lab;x=1",
    "query": f"https://{HOST}/api/projects/lab?key=secret",
    "fragment": f"https://{HOST}/api/projects/lab#top",
    "trailing slash": f"https://{HOST}/api/projects/lab/",
    "no project": f"https://{HOST}/api/projects/",
    "extra path": f"https://{HOST}/api/projects/lab/extra",
    "space in the project": f"https://{HOST}/api/projects/la b",
    "not a project path": f"https://{HOST}/openai/v1",
    "no path": f"https://{HOST}",
}

GOOD_NAMES = ("a", "_", "_x", "case-review-agent", "Agent_9", "a" * 64)
BAD_NAMES = {
    "empty": "", "starts with a digit": "1agent", "starts with a hyphen": "-agent", "too long": "a" * 65,
    "space": "an agent", "period": "an.agent", "slash": "../agent", "trailing newline": "agent\n",
    "non-ASCII letter": "agént", "non-ASCII digit": "agent\u0663",
}


def endpoint_copies():
    """Each copy of the endpoint rule, as a function from a URL to whether it is accepted."""
    environment = {"FOUNDRY_MODEL_NAME": "model", "AGENT_NAME": "agent", "AGENT_INSTRUCTIONS": "x" * 20,
                   "DEMO_TEMPLATE_ID": next(iter(runtime.TEMPLATE_IDS))}
    live = ["--run", "--approve-billable-run", "--authorize-content-capture", "--sample", "application-review-agent",
            "--agent-name", "candidate", "--agent-version", "1", "--judge-model", "judge",
            "--source-revision", "a" * 40, "--output", "report.jsonl"]

    def accepted(call, rejection):
        def check(url):
            try:
                call(url)
            except rejection:
                return False
            return True
        return check

    def lab(url):
        app.Settings("private", url, ("testserver",), ("https://testserver",)).validate()

    def stopped(url):
        library_runs.validate_endpoint(url)

    def evaluation(url):
        with patch("sys.stderr"):
            run.parse_args([*live, "--endpoint", url])

    return {
        "workbench/app.py": accepted(lab, ValueError),
        "workbench/agent_runtime/main.py": accepted(
            lambda url: runtime.read_configuration({**environment, "FOUNDRY_PROJECT_ENDPOINT": url}), ValueError),
        "hosted-agents/bundle.py": bundle.valid_project_endpoint,
        "evaluations/library_runs.py": accepted(stopped, library_runs.Stop),
        "evaluations/run.py": accepted(evaluation, SystemExit),
    }


def name_copies():
    """Each copy of the agent-name pattern, as a function from text to whether it is accepted."""
    def specialist(field):
        value = {"tool": "a_tool", "agent": "other-agent", "description": "Does a thing."}

        def check(name):
            try:
                configuration.validate_specialists([{**value, field: name}])
            except ValueError:
                return False
            return True
        return check

    def coordinator(name):
        profile = {"schema_version": 1, "name": name, "description": "d", "instructions": "i",
                   "specialists": [{"tool": "a_tool", "agent": "other-agent", "description": "Does a thing."}],
                   "smoke_tests": [{"tool": "a_tool", "prompt": "p"}]}
        try:
            configuration.validate_profile(profile)
        except ValueError:
            return False
        return True

    return {
        "workbench/app.py": lambda name: app.NAME.fullmatch(name) is not None,
        "hosted-agents/bundle.py": lambda name: bundle.NAME.fullmatch(name) is not None,
        "review-coordinator-agent/configuration.py (tool)": specialist("tool"),
        "review-coordinator-agent/configuration.py (agent)": specialist("agent"),
        "review-coordinator-agent/configuration.py (coordinator name)": coordinator,
    }


class EndpointRuleTests(unittest.TestCase):
    def test_every_copy_accepts_the_same_project_endpoints(self):
        for url in GOOD_ENDPOINTS:
            with self.subTest(url=url):
                self.assertEqual({name for name, check in endpoint_copies().items() if not check(url)}, set())

    def test_every_copy_refuses_the_same_endpoints(self):
        for label, url in BAD_ENDPOINTS.items():
            with self.subTest(case=label):
                self.assertEqual({name for name, check in endpoint_copies().items() if check(url)}, set())

    def test_all_five_copies_are_checked(self):
        self.assertEqual(len(endpoint_copies()), 5)


class AgentNamePatternTests(unittest.TestCase):
    def test_every_copy_accepts_the_same_names(self):
        for name in GOOD_NAMES:
            with self.subTest(name=name):
                self.assertEqual({copy for copy, check in name_copies().items() if not check(name)}, set())

    def test_every_copy_refuses_the_same_names(self):
        for label, name in BAD_NAMES.items():
            with self.subTest(case=label):
                self.assertEqual({copy for copy, check in name_copies().items() if check(name)}, set())

    def test_all_five_copies_are_checked(self):
        self.assertEqual(len(name_copies()), 5)


if __name__ == "__main__":
    unittest.main()
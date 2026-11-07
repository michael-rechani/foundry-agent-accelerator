"""Offline tests for the separately authorized one-time runner starter."""

import unittest
from pathlib import Path

import test_start_private_runner as original

WORKFLOW = (Path(__file__).resolve().parents[2] / ".github" / "workflows" /
            "start-private-runner-once-20261107.yml").read_text(encoding="utf-8")
START, SMOKE = WORKFLOW.split("\n  smoke:\n")
SCRIPT = "\n".join(line[10:] for line in START.split("        run: |\n", 1)[1].splitlines())
GATE = (
    "if: github.repository_owner == 'michael-rechani' && "
    "github.repository == 'michael-rechani/foundry-agent-accelerator' && "
    "github.workflow_ref == 'michael-rechani/foundry-agent-accelerator/"
    ".github/workflows/start-private-runner-once-20261107.yml@refs/heads/main' && "
    "github.ref == 'refs/heads/main' && github.event_name == 'workflow_dispatch' && "
    "github.run_number == 1 && github.run_attempt == 1"
)
CONTEXT = {
    "GITHUB_REPOSITORY_OWNER": "michael-rechani",
    "GITHUB_REPOSITORY": "michael-rechani/foundry-agent-accelerator",
    "GITHUB_WORKFLOW_REF": "michael-rechani/foundry-agent-accelerator/"
                           ".github/workflows/start-private-runner-once-20261107.yml@refs/heads/main",
    "GITHUB_REF": "refs/heads/main",
    "GITHUB_EVENT_NAME": "workflow_dispatch",
}


class NewWorkflow:
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.previous = original.WORKFLOW, original.START, original.SMOKE, original.SCRIPT
        original.WORKFLOW, original.START, original.SMOKE, original.SCRIPT = WORKFLOW, START, SMOKE, SCRIPT

    @classmethod
    def tearDownClass(cls):
        original.WORKFLOW, original.START, original.SMOKE, original.SCRIPT = cls.previous
        super().tearDownClass()


class WorkflowContractTests(NewWorkflow, original.WorkflowContractTests):
    def test_manual_main_only_with_existing_environment(self):
        trigger = WORKFLOW.split("\non:\n", 1)[1].split("\npermissions:", 1)[0]
        self.assertRegex(trigger, r"^  workflow_dispatch:\n")
        self.assertNotRegex(trigger, r"\b(push|pull_request|schedule|workflow_call):")
        self.assertIn("required: true\n        type: string", trigger)
        self.assertEqual(WORKFLOW.count(GATE), 2)
        self.assertIn("environment: lab-deploy", START)
        self.assertIn("timeout-minutes: 10", START)
        self.assertIn("runs-on: ubuntu-24.04", START)
        self.assertIn("cancel-in-progress: false", WORKFLOW)

    def test_new_path_cannot_trigger_deployment(self):
        deploy = (Path(__file__).resolve().parents[2] / ".github/workflows/deploy-lab.yml").read_text()
        push = deploy.split("  push:\n", 1)[1].split("  workflow_dispatch:", 1)[0]
        self.assertNotIn(".github/", push)


class ShellTests(NewWorkflow, original.ShellTests):
    def execute(self, **overrides):
        return super().execute(**(CONTEXT | overrides))

    def test_invalid_context_fails_before_network(self):
        for key in CONTEXT:
            with self.subTest(key=key):
                result, calls, summary = self.execute(**{key: "unexpected"})
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(calls, "")
                self.assertEqual(summary, "")


if __name__ == "__main__":
    unittest.main()

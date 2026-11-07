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
    "github.actor_id == '97264614' && "
    "github.repository == 'michael-rechani/foundry-agent-accelerator' && "
    "github.workflow_ref == 'michael-rechani/foundry-agent-accelerator/"
    ".github/workflows/start-private-runner-once-20261107.yml@refs/heads/main' && "
    "github.ref == 'refs/heads/main' && github.event_name == 'workflow_dispatch' && "
    "inputs.reviewed_main_sha == github.sha && "
    "github.run_number == 1 && github.run_attempt == 1"
)
CONTEXT = {
    "GITHUB_REPOSITORY_OWNER": "michael-rechani",
    "GITHUB_ACTOR_ID": "97264614",
    "GITHUB_SHA": "a" * 40,
    "REVIEWED_MAIN_SHA": "a" * 40,
    "GH_TOKEN": "offline-github-token",
    "API_BODY": '{"name":"main","protected":true,"commit":{"sha":"' + "a" * 40 + '"}}',
    "API_HTTP_STATUS": "200",
    "API_FAIL": "",
    "GITHUB_REPOSITORY": "michael-rechani/foundry-agent-accelerator",
    "GITHUB_WORKFLOW_REF": "michael-rechani/foundry-agent-accelerator/"
                           ".github/workflows/start-private-runner-once-20261107.yml@refs/heads/main",
    "GITHUB_REF": "refs/heads/main",
    "GITHUB_EVENT_NAME": "workflow_dispatch",
}


MOCKS = original.MOCKS.replace(
    "curl() { printf 'curl\\n' >> \"$CALL_LOG\"; [[ \"$FAIL_AT\" != oidc ]] || return 1; printf 'mock response'; }",
    """curl() {
  if [[ "$*" == *"https://api.github.com/repos/michael-rechani/foundry-agent-accelerator/branches/main"* ]]; then
    printf 'github-api\\n' >> "$CALL_LOG"
    [[ "$*" == "--disable "* && "$*" == *"--max-redirs 0"* && "$*" == *"--proto =https"* &&
       "$*" == *"Authorization: Bearer offline-github-token"* &&
       "$*" != *"--location"* && "$API_FAIL" != 1 ]] || return 1
    printf '%s\\n%s' "$API_BODY" "$API_HTTP_STATUS"
  else
    printf 'curl\\n' >> "$CALL_LOG"
    [[ "$FAIL_AT" != oidc ]] || return 1
    printf 'mock response'
  fi
}""",
).replace(
    "jq() { [[ \"$FAIL_AT\" != token ]] || return 1; printf 'offline-token\\n'; }",
    """jq() {
  if [[ "$1" == "-e" ]]; then command jq "$@"; else
    [[ "$FAIL_AT" != token ]] || return 1
    printf 'offline-token\\n'
  fi
}""",
)


class NewWorkflow:
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.previous = original.WORKFLOW, original.START, original.SMOKE, original.SCRIPT, original.MOCKS
        original.WORKFLOW, original.START, original.SMOKE, original.SCRIPT = WORKFLOW, START, SMOKE, SCRIPT
        original.MOCKS = MOCKS

    @classmethod
    def tearDownClass(cls):
        original.WORKFLOW, original.START, original.SMOKE, original.SCRIPT, original.MOCKS = cls.previous
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

    def test_reviewed_sha_and_read_only_api_contract(self):
        self.assertIn("reviewed_main_sha:\n        description:", WORKFLOW)
        self.assertIn("REVIEWED_MAIN_SHA: ${{ inputs.reviewed_main_sha }}", START)
        self.assertIn("GH_TOKEN: ${{ github.token }}", START)
        self.assertLess(SCRIPT.index("branch_response="), SCRIPT.index('token="$(curl'))
        self.assertIn("--max-redirs 0 --proto '=https'", SCRIPT)
        self.assertIn("curl --disable", SCRIPT)
        self.assertNotIn("--location", SCRIPT)
        self.assertNotIn("${{", SCRIPT)

    def test_new_path_cannot_trigger_deployment(self):
        deploy = (Path(__file__).resolve().parents[2] / ".github/workflows/deploy-lab.yml").read_text()
        push = deploy.split("  push:\n", 1)[1].split("  workflow_dispatch:", 1)[0]
        self.assertNotIn(".github/", push)


class ShellTests(NewWorkflow, original.ShellTests):
    def execute(self, **overrides):
        return super().execute(**(CONTEXT | overrides))

    def test_good_main_response_checked_before_oidc(self):
        result, calls, summary = self.execute()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(calls.startswith("github-api\ncurl\n"))
        self.assertIn("confirmed running", summary)

    def test_main_verification_fails_closed_before_oidc(self):
        bad = [
            {"API_FAIL": "1"}, {"API_HTTP_STATUS": "301"}, {"API_HTTP_STATUS": "302"},
            {"API_HTTP_STATUS": "307"}, {"API_HTTP_STATUS": "403"}, {"API_HTTP_STATUS": "404"},
            {"API_HTTP_STATUS": "500"}, {"API_HTTP_STATUS": ""},
            {"API_BODY": ""}, {"API_BODY": "not-json"}, {"API_BODY": "[]"},
            {"API_BODY": "{}"},
            {"API_BODY": '{} {"name":"main","protected":true,"commit":{"sha":"' + "a" * 40 + '"}}'},
            {"API_BODY": '{"name":"other","protected":true,"commit":{"sha":"' + "a" * 40 + '"}}'},
            {"API_BODY": '{"name":"main","protected":false,"commit":{"sha":"' + "a" * 40 + '"}}'},
            {"API_BODY": '{"name":"main","protected":"true","commit":{"sha":"' + "a" * 40 + '"}}'},
            {"API_BODY": '{"name":"main","protected":true,"commit":{"sha":"' + "b" * 40 + '"}}'},
            {"API_BODY": '{"name":"main","protected":true,"commit":null}'},
        ]
        for overrides in bad:
            with self.subTest(overrides=overrides):
                result, calls, summary = self.execute(**overrides)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(calls, "github-api\n")
                self.assertEqual(summary, "")

    def test_invalid_reviewed_sha_fails_before_network(self):
        for sha in ("", "a" * 39, "a" * 41, "A" * 40, "g" * 40, "b" * 40):
            with self.subTest(sha=sha):
                result, calls, summary = self.execute(REVIEWED_MAIN_SHA=sha)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(calls, "")
                self.assertEqual(summary, "")

    def test_absent_github_token_fails_before_network(self):
        result, calls, summary = self.execute(GH_TOKEN="")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls, "")
        self.assertEqual(summary, "")

    def test_invalid_context_fails_before_network(self):
        for key in CONTEXT.keys() - {"API_BODY", "API_HTTP_STATUS", "API_FAIL", "GH_TOKEN"}:
            with self.subTest(key=key):
                result, calls, summary = self.execute(**{key: "unexpected"})
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(calls, "")
                self.assertEqual(summary, "")


if __name__ == "__main__":
    unittest.main()

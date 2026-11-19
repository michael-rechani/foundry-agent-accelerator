"""Offline contract tests for the owner-authorized one-shot runner wake."""

import re
import unittest
from pathlib import Path
from unittest import mock

import test_start_private_runner_once_20261107 as prior

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = (ROOT / ".github" / "workflows" /
            "start-private-runner-once-20261119.yml").read_text(encoding="utf-8")
START, SMOKE = WORKFLOW.split("\n  smoke:\n")
SCRIPT = "\n".join(line[10:] for line in START.split("        run: |\n", 1)[1].splitlines())
GATE = (
    "if: github.repository_owner == 'michael-rechani' && "
    "github.actor_id == '97264614' && "
    "github.repository == 'michael-rechani/foundry-agent-accelerator' && "
    "github.workflow_ref == 'michael-rechani/foundry-agent-accelerator/"
    ".github/workflows/start-private-runner-once-20261119.yml@refs/heads/main' && "
    "github.ref == 'refs/heads/main' && github.event_name == 'workflow_dispatch' && "
    "inputs.reviewed_main_sha == github.sha && "
    "github.run_number == 1 && github.run_attempt == 1"
)

PRIOR_MOCKS = prior.MOCKS
MOCKS = PRIOR_MOCKS.replace(
    'jq() { [[ "$FAIL_AT" != token ]] || return 1; printf \'offline-token\\n\'; }',
    '''jq() { [[ "$FAIL_AT" != token ]] || return 1; printf 'offline-token\\n'; }
git() { [[ "$*" == "rev-parse HEAD" ]] || return 99; printf '%s\\n' "$GITHUB_SHA"; }
python3() {
  printf 'queue-check\\n' >> "$CALL_LOG"
  QUEUE_COUNT=$(( ${QUEUE_COUNT:-0} + 1 ))
  [[ "$FAIL_AT" != queue && "$QUEUE_FAIL_AT" != "$QUEUE_COUNT" ]] || return 1
}''',
)


class SharedWorkflowSetup:
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.previous = (
            prior.WORKFLOW, prior.START, prior.SMOKE, prior.SCRIPT,
            prior.GATE, prior.MOCKS,
        )
        cls.previous_context = prior.CONTEXT
        prior.WORKFLOW, prior.START, prior.SMOKE = WORKFLOW, START, SMOKE
        prior.SCRIPT, prior.GATE, prior.MOCKS = SCRIPT, GATE, MOCKS
        prior.CONTEXT = prior.CONTEXT | {
            "GITHUB_WORKFLOW_REF": (
                "michael-rechani/foundry-agent-accelerator/"
                ".github/workflows/start-private-runner-once-20261119.yml@refs/heads/main"
            ),
        }

    @classmethod
    def tearDownClass(cls):
        (prior.WORKFLOW, prior.START, prior.SMOKE, prior.SCRIPT,
         prior.GATE, prior.MOCKS) = cls.previous
        prior.CONTEXT = cls.previous_context
        super().tearDownClass()


class WorkflowContractTests(SharedWorkflowSetup, prior.WorkflowContractTests):
    def test_owner_authorized_one_shot_is_new_and_not_independent_review(self):
        self.assertIn("name: Start private runner once 20261119", WORKFLOW)
        self.assertIn("This is one owner-authorized wake, not independent review.", WORKFLOW)
        self.assertIn(
            "default: 40b50a1431fa35321ab3ab61c23f5ca381f0952a013720db7dbd03ee038f9ca8",
            WORKFLOW,
        )
        self.assertEqual(WORKFLOW.count(GATE), 2)
        self.assertIn("actions: read", WORKFLOW)
        self.assertIn("contents: read", WORKFLOW)
        self.assertIn("id-token: write", WORKFLOW)
        self.assertIn("persist-credentials: false", WORKFLOW)

    def test_queue_is_checked_before_oidc_and_again_before_start(self):
        self.assertEqual(SCRIPT.count("python3 .github/scripts/check_lab_runner_queue.py"), 2)
        self.assertLess(SCRIPT.index("check_lab_runner_queue.py"), SCRIPT.index('token="$(curl'))
        self.assertLess(
            SCRIPT.rindex("check_lab_runner_queue.py"),
            SCRIPT.index('az vm start --ids "$actual_id"'),
        )

    def test_start_is_one_call_and_only_stopped_or_deallocated(self):
        self.assertEqual(SCRIPT.count('az vm start --ids "$actual_id"'), 1)
        self.assertIn("PowerState/stopped|PowerState/deallocated)", SCRIPT)
        self.assertIn("PowerState/running|PowerState/starting)", SCRIPT)
        self.assertIn("no start retry will be attempted", SCRIPT)


class ShellTests(SharedWorkflowSetup, prior.ShellTests):
    def execute(self, **overrides):
        return super().execute(**(prior.CONTEXT | overrides))

    def test_good_main_response_checked_before_oidc(self):
        result, calls, summary = self.execute()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(calls.startswith("github-api\nqueue-check\ncurl\n"))
        self.assertEqual(calls.count("<start>"), 1)
        self.assertIn("confirmed running", summary)

    def test_success_checks_queue_twice_and_starts_once(self):
        result, calls, summary = self.execute()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(calls.count("queue-check\n"), 2)
        self.assertEqual(calls.count("az <vm> <start>"), 1)
        self.assertIn("confirmed running", summary)

    def test_queue_failure_stops_before_oidc_or_start(self):
        result, calls, summary = self.execute(FAIL_AT="queue")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls.count("queue-check\n"), 1)
        self.assertNotIn("curl\n", calls)
        self.assertNotIn("<start>", calls)
        self.assertEqual(summary, "")

    def test_queue_change_before_start_fails_without_retry(self):
        result, calls, summary = self.execute(QUEUE_FAIL_AT="2")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls.count("queue-check\n"), 2)
        self.assertNotIn("<start>", calls)
        self.assertEqual(summary, "")

    def test_running_or_starting_vm_is_observed_without_start(self):
        for state in ("PowerState/running", "PowerState/starting"):
            with self.subTest(state=state):
                result, calls, _ = self.execute(INITIAL_STATE=state)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertNotIn("<start>", calls)
                self.assertEqual(calls.count("queue-check\n"), 1)

    def test_checked_out_source_must_equal_reviewed_sha(self):
        with mock.patch.object(base, "MOCKS", MOCKS.replace(
            'git() { [[ "$*" == "rev-parse HEAD" ]] || return 99; printf \'%s\\n\' "$GITHUB_SHA"; }',
            'git() { [[ "$*" == "rev-parse HEAD" ]] || return 99; printf \'%040d\\n\' 2; }',
        )):
            result, calls, summary = self.execute()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls, "")
        self.assertEqual(summary, "")


if __name__ == "__main__":
    unittest.main()

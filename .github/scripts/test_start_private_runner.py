"""Offline contracts and Bash execution with all network/CLI calls replaced."""

import hashlib
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = (ROOT / ".github" / "workflows" / "start-private-runner.yml").read_text(encoding="utf-8")
START, SMOKE = WORKFLOW.split("\n  smoke:\n")
SCRIPT = START.split("        run: |\n", 1)[1]
SCRIPT = "\n".join(line[10:] for line in SCRIPT.splitlines())
BASH = shutil.which("bash")
SUBSCRIPTION = "11111111-1111-1111-1111-111111111111"
VM_ID = f"/subscriptions/{SUBSCRIPTION}/resourceGroups/runner-rg/providers/Microsoft.Compute/virtualMachines/runner-vm"
VM_SHA256 = hashlib.sha256(VM_ID.lower().encode("utf-8")).hexdigest()

MOCKS = r"""
curl() { printf 'curl\n' >> "$CALL_LOG"; [[ "$FAIL_AT" != oidc ]] || return 1; printf 'mock response'; }
jq() { [[ "$FAIL_AT" != token ]] || return 1; printf 'offline-token\n'; }
az() {
  printf 'az' >> "$CALL_LOG"
  printf ' <%s>' "$@" >> "$CALL_LOG"
  printf '\n' >> "$CALL_LOG"
  case "$1 $2" in
    "login --service-principal") [[ "$FAIL_AT" != login ]] ;;
    "account set") [[ "$FAIL_AT" != account ]] ;;
    "vm show") [[ "$FAIL_AT" != show ]] || return 1; printf '%s\n' "$ACTUAL_ID" ;;
    "vm get-instance-view")
      [[ "$FAIL_AT" != state ]] || return 1
      if [[ -f "$SLEEP_MARKER" ]]; then printf '%s\n' "$FINAL_STATE"; else printf '%s\n' "$INITIAL_STATE"; fi ;;
    "vm start") [[ "$FAIL_AT" != start ]] ;;
    *) echo "Unapproved az command" >&2; return 99 ;;
  esac
}
sleep() { printf 'sleep\n' >> "$CALL_LOG"; printf 'slept' > "$SLEEP_MARKER"; SECONDS=301; }
"""


class WorkflowContractTests(unittest.TestCase):
    def test_manual_main_only_with_existing_environment(self):
        trigger = WORKFLOW.split("\non:\n", 1)[1].split("\npermissions:", 1)[0]
        self.assertRegex(trigger, r"^  workflow_dispatch:\n")
        self.assertNotRegex(trigger, r"\b(push|pull_request|schedule|workflow_call):")
        self.assertIn("required: true\n        type: string", trigger)
        gate = "if: github.ref == 'refs/heads/main' && github.event_name == 'workflow_dispatch'"
        self.assertEqual(WORKFLOW.count(gate), 2)
        self.assertIn("environment: lab-deploy", START)
        self.assertIn("timeout-minutes: 10", START)
        self.assertIn("runs-on: ubuntu-24.04", START)
        self.assertIn("cancel-in-progress: false", WORKFLOW)

    def test_permissions_and_no_repository_code_or_input_interpolation(self):
        self.assertEqual(re.findall(r"^      ([\w-]+): (read|write)$", START, re.MULTILINE),
                         [("contents", "read"), ("id-token", "write")])
        self.assertNotIn("uses:", WORKFLOW)
        self.assertNotIn("${{", SCRIPT)
        for name in ("AZURE_CLIENT_ID", "AZURE_TENANT_ID", "AZURE_SUBSCRIPTION_ID",
                     "LAB_RUNNER_RESOURCE_GROUP", "LAB_RUNNER_VM"):
            self.assertIn(f"{name}: ${{{{ vars.{name} }}}}", START)
        self.assertIn("REVIEWED_VM_SHA256: ${{ inputs.reviewed_vm_sha256 }}", START)
        self.assertNotIn("reviewed_vm_resource_id", WORKFLOW)
        self.assertEqual(re.findall(r"\baz ([\w-]+) ([\w-]+)", SCRIPT),
                         [("login", "--service-principal"), ("account", "set"),
                          ("vm", "show"), ("vm", "get-instance-view"), ("vm", "start")])

    def test_identifiers_are_masked_before_authentication_and_not_summarized(self):
        self.assertLess(SCRIPT.index('echo "::add-mask::$value"'), SCRIPT.index("az login"))
        self.assertIn('"$expected_id" "${expected_id,,}" "$AZURE_CLIENT_ID" "$AZURE_TENANT_ID"', SCRIPT)
        summary = SCRIPT.split('>> "$GITHUB_STEP_SUMMARY"')[0].splitlines()[-1]
        self.assertNotIn("$actual_id", summary)
        self.assertNotIn("$expected_id", summary)

    def test_smoke_has_no_credentials_and_only_reports_one_registration(self):
        self.assertIn("needs: start-runner", SMOKE)
        self.assertIn("runs-on: [self-hosted, linux, lab-runner]", SMOKE)
        self.assertIn("permissions: {}", SMOKE)
        for forbidden in ("environment:", "env:", "uses:", "az ", "id-token", "${{"):
            self.assertNotIn(forbidden, SMOKE)
        self.assertEqual(SMOKE.count('"$RUNNER_NAME"'), 2)

    def test_merge_does_not_match_image_deployment_push_paths(self):
        deploy = (ROOT / ".github" / "workflows" / "deploy-lab.yml").read_text(encoding="utf-8")
        push = deploy.split("  push:\n", 1)[1].split("  workflow_dispatch:", 1)[0]
        positive_paths = re.findall(r"^\s+- '([^!][^']*)'$", push, re.MULTILINE)
        self.assertEqual(positive_paths, ["workbench/**"])
        for name in (".github/workflows/start-private-runner.yml",
                     ".github/scripts/test_start_private_runner.py"):
            self.assertFalse(name.startswith("workbench/"))


@unittest.skipUnless(BASH, "Bash is required for mocked shell execution")
class ShellTests(unittest.TestCase):
    def execute(self, **overrides):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            env = {
                **os.environ,
                "AZURE_SUBSCRIPTION_ID": SUBSCRIPTION,
                "AZURE_CLIENT_ID": SUBSCRIPTION,
                "AZURE_TENANT_ID": SUBSCRIPTION,
                "LAB_RUNNER_RESOURCE_GROUP": "runner-rg",
                "LAB_RUNNER_VM": "runner-vm",
                "REVIEWED_VM_SHA256": VM_SHA256,
                "RUN_NUMBER": "1",
                "RUN_ATTEMPT": "1",
                "ACTUAL_ID": VM_ID,
                "INITIAL_STATE": "PowerState/deallocated",
                "FINAL_STATE": "PowerState/running",
                "FAIL_AT": "",
                "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "offline-request",
                "ACTIONS_ID_TOKEN_REQUEST_URL": "https://offline.invalid/?test=1",
                "CALL_LOG": (folder / "calls").as_posix(),
                "SLEEP_MARKER": (folder / "slept").as_posix(),
                "GITHUB_STEP_SUMMARY": (folder / "summary").as_posix(),
                **overrides,
            }
            script = folder / "test.sh"
            script.write_text(MOCKS + "\n" + SCRIPT, encoding="utf-8")
            result = subprocess.run([BASH, script.as_posix()], env=env, capture_output=True,
                                    text=True, timeout=10, check=False)
            calls = (folder / "calls").read_text() if (folder / "calls").exists() else ""
            summary = (folder / "summary").read_text() if (folder / "summary").exists() else ""
            return result, calls, summary

    def test_bash_syntax(self):
        result = subprocess.run([BASH, "-n"], input=SCRIPT, text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_running_vm_is_not_started(self):
        result, calls, summary = self.execute(INITIAL_STATE="PowerState/running")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("<start>", calls)
        self.assertNotIn(VM_ID, summary)
        self.assertNotIn(SUBSCRIPTION, summary)
        self.assertIn("confirmed running", summary)

    def test_stopped_and_deallocated_start_exactly_once(self):
        for state in ("PowerState/stopped", "PowerState/deallocated"):
            with self.subTest(state=state):
                result, calls, summary = self.execute(INITIAL_STATE=state)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(calls.count("az <vm> <start>"), 1)
                self.assertIn(f"<--ids> <{VM_ID}> <--no-wait>", calls)
                self.assertGreaterEqual(calls.count("<get-instance-view>"), 2)
                self.assertIn("confirmed running", summary)

    def test_starting_vm_is_only_polled(self):
        result, calls, _ = self.execute(INITIAL_STATE="PowerState/starting")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("<start>", calls)

    def test_invalid_inputs_fail_before_authentication(self):
        cases = [
            {"REVIEWED_VM_SHA256": ""},
            {"REVIEWED_VM_SHA256": VM_ID},
            {"REVIEWED_VM_SHA256": VM_SHA256 + "$(touch injected)"},
            {"REVIEWED_VM_SHA256": VM_SHA256.upper()},
            {"REVIEWED_VM_SHA256": "0" * 64},
            {"REVIEWED_VM_SHA256": hashlib.sha256(VM_ID.encode("utf-8")).hexdigest()},
            {"AZURE_SUBSCRIPTION_ID": ""},
            {"AZURE_CLIENT_ID": "bad"},
            {"AZURE_TENANT_ID": "bad"},
            {"LAB_RUNNER_VM": "--help"},
            {"LAB_RUNNER_VM": "different"},
            {"LAB_RUNNER_RESOURCE_GROUP": "different"},
            {"LAB_RUNNER_RESOURCE_GROUP": "runner-rg; echo injected"},
        ]
        for overrides in cases:
            with self.subTest(overrides=overrides):
                result, calls, summary = self.execute(**overrides)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(calls, "")
                self.assertEqual(summary, "")

    def test_later_runs_and_attempts_fail_before_any_network_call(self):
        for run, attempt in (("2", "1"), ("1", "2"), ("", "1"), ("1", "")):
            with self.subTest(run=run, attempt=attempt):
                result, calls, summary = self.execute(RUN_NUMBER=run, RUN_ATTEMPT=attempt)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("One-shot authorization consumed", result.stdout)
                self.assertEqual(calls, "")
                self.assertEqual(summary, "")

    def test_fingerprint_normalizes_case(self):
        actual = VM_ID.replace("runner-vm", "RUNNER-VM")
        result, _, summary = self.execute(LAB_RUNNER_VM="RUNNER-VM", ACTUAL_ID=actual)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("confirmed running", summary)

    def test_azure_id_mismatch_fails_before_power_read_or_start(self):
        for actual in ("", VM_ID.replace("runner-vm", "other"),
                       VM_ID.replace("runner-rg", "other"),
                       VM_ID.replace(SUBSCRIPTION, "22222222-2222-2222-2222-222222222222")):
            with self.subTest(actual=actual):
                result, calls, summary = self.execute(ACTUAL_ID=actual)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("<get-instance-view>", calls)
                self.assertNotIn("<start>", calls)
                self.assertEqual(summary, "")

    def test_azure_id_comparison_normalizes_case(self):
        result, calls, summary = self.execute(ACTUAL_ID=VM_ID.upper())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls.count("az <vm> <start>"), 1)
        self.assertIn(f"<--ids> <{VM_ID.upper()}>", calls)
        self.assertIn("confirmed running", summary)

    def test_authentication_and_read_failures_never_start(self):
        for stage in ("oidc", "token", "login", "account", "show", "state"):
            with self.subTest(stage=stage):
                result, calls, summary = self.execute(FAIL_AT=stage)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("<start>", calls)
                self.assertEqual(summary, "")

    def test_unsafe_or_missing_initial_state_fails_closed(self):
        for state in ("", "None", "PowerState/unknown", "PowerState/deallocating"):
            with self.subTest(state=state):
                result, calls, summary = self.execute(INITIAL_STATE=state)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("<start>", calls)
                self.assertEqual(summary, "")

    def test_failed_start_has_no_retry_or_success_summary(self):
        result, calls, summary = self.execute(FAIL_AT="start")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls.count("az <vm> <start>"), 1)
        self.assertNotIn("sleep", calls)
        self.assertEqual(summary, "")

    def test_timeout_and_unexpected_result_fail_without_other_mutations(self):
        for state in ("PowerState/starting", "PowerState/stopped", "", "PowerState/deallocating"):
            with self.subTest(state=state):
                result, calls, summary = self.execute(FINAL_STATE=state)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(calls.count("az <vm> <start>"), 1)
                self.assertEqual(summary, "")


if __name__ == "__main__":
    unittest.main()

"""Offline checks that Record library answers can reach its private runner, and no one else can.

The workflow is read as text so these tests need nothing beyond the standard library.
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
RECORD = (WORKFLOWS / "record-library-answers.yml").read_text(encoding="utf-8")
DEPLOY = (WORKFLOWS / "deploy-lab.yml").read_text(encoding="utf-8")
JOB_HEADING = re.compile(r"^  ([A-Za-z][\w-]*):[ \t]*$", re.MULTILINE)
PINNED = re.compile(r"^\s*(?:- )?uses:\s*[\w./-]+@[0-9a-f]{40}\b", re.MULTILINE)


def jobs_of(text):
    body = text.split("\njobs:\n", 1)[1]
    headings = list(JOB_HEADING.finditer(body))
    return {
        match.group(1): body[match.end(): headings[index + 1].start() if index + 1 < len(headings) else len(body)]
        for index, match in enumerate(headings)
    }


def without_comments(text):
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


RECORD_JOBS = jobs_of(RECORD)
DEPLOY_JOBS = jobs_of(DEPLOY)
START = RECORD_JOBS["start-runner"]
RECORDING = RECORD_JOBS["record"]


def field(job, name):
    match = re.search(rf"^    {re.escape(name)}:[ \t]*(.+?)[ \t]*$", job, re.MULTILINE)
    return match.group(1) if match else None


class RecordWorkflowTests(unittest.TestCase):
    def test_the_workflow_has_a_start_job_and_a_record_job_only(self):
        self.assertEqual(set(RECORD_JOBS), {"start-runner", "record"})

    def test_the_record_job_stays_on_the_private_runner_behind_its_reviewer(self):
        self.assertEqual(field(RECORDING, "runs-on"), "[self-hosted, linux, lab-runner]")
        self.assertEqual(field(RECORDING, "environment"), "library-recording")
        self.assertEqual(field(RECORDING, "if"), "github.ref == 'refs/heads/main'")
        self.assertIn("library_runs.py record --templates $0 --yes", RECORDING)

    def test_the_start_job_runs_on_a_github_hosted_runner_from_main_only(self):
        self.assertRegex(field(START, "runs-on"), r"^ubuntu-\d")
        self.assertNotIn("self-hosted", START)
        self.assertEqual(field(START, "if"), "github.ref == 'refs/heads/main'")

    def test_neither_job_waits_for_the_other(self):
        # The record job waits for approval and the start job waits for that approval, so a needs would deadlock.
        for name, job in RECORD_JOBS.items():
            with self.subTest(job=name):
                self.assertIsNone(field(job, "needs"))
                self.assertNotIn("needs:", without_comments(job))

    def test_the_start_job_waits_for_the_record_job_by_its_id(self):
        self.assertIn("wait_for_approval.py --job record --environment library-recording ", START)
        self.assertIn("record", RECORD_JOBS)
        self.assertIsNone(re.search(r"^    name:", RECORDING, re.MULTILINE))

    def test_the_vm_starts_only_after_the_approval_step_says_so(self):
        steps = re.split(r"^      - ", START, flags=re.MULTILINE)
        gated = [step for step in steps if "az login" in step or "az vm start" in step]
        self.assertEqual(len(gated), 2)
        for step in gated:
            self.assertIn("if: steps.approval.outputs.approved == 'true'", step)
        approval = next(step for step in steps if "wait_for_approval.py" in step)
        self.assertIn("id: approval", approval)
        self.assertLess(START.index("wait_for_approval.py"), START.index("az login"))
        self.assertLess(START.index("az login"), START.index("az vm start"))

    def test_the_start_job_uses_the_deploy_identity_not_the_recording_one(self):
        self.assertEqual(field(START, "environment"), "lab-deploy")
        self.assertNotIn("environment: library-recording", START)
        self.assertNotIn("FOUNDRY_PROJECT_ENDPOINT", START)
        for name in ("AZURE_CLIENT_ID", "AZURE_TENANT_ID", "AZURE_SUBSCRIPTION_ID", "LAB_RUNNER_VM",
                     "LAB_RUNNER_RESOURCE_GROUP"):
            self.assertIn(f"{name}: ${{{{ vars.{name} }}}}", START)
        self.assertNotIn("lab-deploy", RECORDING)
        self.assertNotIn("az vm", RECORDING)
        self.assertNotIn("az login", RECORDING)

    def test_the_start_job_asks_for_the_least_it_needs(self):
        permissions = re.search(r"^    permissions:\n((?:      .+\n)+)", START, re.MULTILINE).group(1)
        self.assertEqual(sorted(line.strip() for line in permissions.splitlines()),
                         ["actions: read", "contents: read", "id-token: write"])

    def test_the_start_job_only_starts_the_vm(self):
        code = without_comments(START)
        for command in re.findall(r"\baz vm \S+", code):
            self.assertEqual(command, "az vm start")
        for risky in ("deallocate", "az vm stop", "delete", "run-command", "az role", "az group", "az resource"):
            self.assertNotIn(risky, code)
        self.assertEqual(code.count("az vm start"), 1)

    def test_the_start_job_never_runs_code_from_the_requested_ref_or_the_inputs(self):
        # A dispatcher chooses inputs.ref and inputs.templates; the deploy identity must not see either.
        code = without_comments(START)
        self.assertNotIn("inputs.", code)
        self.assertNotIn("github.event.inputs", code)
        self.assertEqual(code.count("actions/checkout@"), 1)
        self.assertNotIn("ref:", code)
        self.assertIn("persist-credentials: false", code)

    def test_the_start_job_matches_the_deploy_workflows_start_command(self):
        deploy = DEPLOY_JOBS["start-runner"]
        for text in ('az vm start --name "$LAB_RUNNER_VM" --resource-group "$LAB_RUNNER_RESOURCE_GROUP" --output none',
                     "--federated-token \"$token\" --allow-no-subscriptions --output none"):
            self.assertIn(text, deploy)
            self.assertIn(text, START)
        self.assertEqual(field(deploy, "environment"), field(START, "environment"))

    def test_the_start_job_has_a_timeout_longer_than_its_wait(self):
        timeout = int(field(START, "timeout-minutes"))
        wait = int(re.search(r"--timeout-minutes (\d+)", START).group(1))
        self.assertGreater(timeout, wait)
        self.assertGreater(wait, 0)

    def test_every_action_is_pinned_to_a_commit(self):
        uses = re.findall(r"^\s*(?:- )?uses:", RECORD, re.MULTILINE)
        self.assertEqual(len(PINNED.findall(RECORD)), len(uses))
        self.assertGreaterEqual(len(uses), 3)

    def test_the_helper_script_is_where_the_workflow_expects_it(self):
        self.assertTrue((ROOT / ".github" / "scripts" / "wait_for_approval.py").is_file())

    def test_recording_still_asks_the_reviewer_and_never_records_a_sign_off(self):
        self.assertIn("workflow_dispatch:", RECORD)
        self.assertNotIn("push:", RECORD)
        self.assertNotIn("schedule:", RECORD)
        self.assertNotIn("signoff", RECORD)
        self.assertIn("cancel-in-progress: false", RECORD)


if __name__ == "__main__":
    unittest.main()

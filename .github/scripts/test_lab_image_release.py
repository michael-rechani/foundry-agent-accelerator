"""Offline tests for the manually staged Lab image workflow."""

import copy
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import check_lab_image_release as guard

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = (ROOT / ".github" / "workflows" / "deploy-lab.yml").read_text(encoding="utf-8")
APPLY_WORKFLOW = (ROOT / ".github" / "workflows" / "apply-lab-terraform.yml").read_text(encoding="utf-8")
SHA = "a" * 40
SUBSCRIPTION = "12345678-1234-1234-1234-123456789abc"
REGISTRY = "private.azurecr.io"
IMAGE = f"{REGISTRY}/workbench@sha256:" + "b" * 64
APP_ID = f"/subscriptions/{SUBSCRIPTION}/resourceGroups/lab-rg/providers/Microsoft.App/containerApps/lab"
REVISION = "lab--reviewed"


def environment():
    return {
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_SHA": SHA,
        "REVIEWED_SOURCE_SHA": SHA,
        "CONFIRM_ROLLOUT": "true",
        "EXPECTED_CURRENT_IMAGE": IMAGE,
        "GITHUB_API_URL": "https://api.github.com",
        "GITHUB_REPOSITORY": "owner/repo",
        "GH_TOKEN": "test-token",
        "AZURE_SUBSCRIPTION_ID": SUBSCRIPTION,
        "AZURE_RESOURCE_GROUP": "lab-rg",
        "LAB_CONTAINER_APP": "lab",
    }


def snapshot():
    containers = [{"name": "workbench", "image": IMAGE}]
    return {
        "registry": REGISTRY,
        "app": {
            "id": APP_ID,
            "revisionMode": "Single",
            "latest": REVISION,
            "ready": REVISION,
            "containers": copy.deepcopy(containers),
        },
        "revisions": [
            {"id": APP_ID + "/revisions/" + REVISION, "name": REVISION, "active": True,
             "state": "Running", "containers": copy.deepcopy(containers)},
            {"id": APP_ID + "/revisions/old", "name": "old", "active": False,
             "state": "Stopped", "containers": []},
        ],
    }


def recovery_snapshot():
    current = snapshot()
    current["app"]["latest"] = "lab--attempted"
    current["app"]["containers"][0]["image"] = f"{REGISTRY}/workbench@sha256:" + "c" * 64
    return current


def deployed_snapshot():
    current = recovery_snapshot()
    current["app"]["ready"] = "lab--attempted"
    current["revisions"][0].update(
        name="lab--attempted", id=APP_ID + "/revisions/lab--attempted",
        containers=copy.deepcopy(current["app"]["containers"]),
    )
    return current


class ReleaseGuardTests(unittest.TestCase):
    def test_valid_dispatch_and_exact_current_main(self):
        reviewed, image = guard.validate_dispatch(environment())
        self.assertEqual((reviewed, image), (SHA, IMAGE))
        with patch.object(guard, "json_response", return_value={"object": {"sha": SHA}}) as get:
            guard.verify_main(environment(), reviewed)
        self.assertEqual(get.call_args.args[0], "https://api.github.com/repos/owner/repo/git/ref/heads/main")

    def test_invalid_dispatch_fails_closed(self):
        for key, value in (
            ("GITHUB_EVENT_NAME", "push"), ("GITHUB_REF", "refs/heads/feature"),
            ("GITHUB_SHA", "b" * 40), ("REVIEWED_SOURCE_SHA", "a" * 12),
            ("CONFIRM_ROLLOUT", "false"), ("EXPECTED_CURRENT_IMAGE", "private.azurecr.io/workbench:latest"),
            ("EXPECTED_CURRENT_IMAGE", ""), ("EXPECTED_CURRENT_IMAGE", IMAGE.upper()),
        ):
            with self.subTest(key=key, value=value):
                env = environment()
                env[key] = value
                with self.assertRaises(guard.CheckError):
                    guard.validate_dispatch(env)

    def test_stale_or_unverifiable_main_fails(self):
        for response in ({}, {"object": None}, {"object": {"sha": "b" * 40}}):
            with self.subTest(response=response), patch.object(guard, "json_response", return_value=response):
                with self.assertRaises(guard.CheckError):
                    guard.verify_main(environment(), SHA)
        for key, value in (("GITHUB_API_URL", "https://untrusted.example"),
                           ("GITHUB_REPOSITORY", "../repo"), ("GH_TOKEN", "")):
            env = environment()
            env[key] = value
            with self.subTest(key=key), patch.object(guard, "json_response") as get:
                with self.assertRaises(guard.CheckError):
                    guard.verify_main(env, SHA)
                get.assert_not_called()

    def test_one_known_running_revision_is_accepted(self):
        guard.verify_live_image(environment(), IMAGE, snapshot())
        current = snapshot()
        current["revisions"][0]["state"] = "RunningAtMaxScale"
        guard.verify_live_image(environment(), IMAGE, current)

    def test_ambiguous_revision_or_image_fails_closed(self):
        changes = (
            lambda s: s["app"].update(revisionMode=None),
            lambda s: s["app"].update(revisionMode="Multiple"),
            lambda s: s["app"].update(latest="different"),
            lambda s: s["app"].update(ready=None),
            lambda s: s["app"].update(containers=[]),
            lambda s: s["app"]["containers"].append({"name": "other", "image": IMAGE}),
            lambda s: s["app"]["containers"][0].update(image="private.azurecr.io/workbench:latest"),
            lambda s: s.update(revisions=[]),
            lambda s: s["revisions"][0].update(active=False),
            lambda s: s["revisions"][0].update(active=None),
            lambda s: s["revisions"][1].update(active=True),
            lambda s: s["revisions"][1].update(name=REVISION, id=APP_ID + "/revisions/" + REVISION),
            lambda s: s["revisions"][1].update(id=APP_ID + "/revisions/other"),
            lambda s: s["revisions"][0].update(state="Degraded"),
            lambda s: s["revisions"][0].update(name="other"),
            lambda s: s["revisions"][0].update(id=APP_ID + "/revisions/other"),
            lambda s: s["revisions"][0].update(containers=[]),
            lambda s: s["revisions"][0]["containers"][0].update(image="private.azurecr.io/workbench:latest"),
            lambda s: s.update(registry="other.azurecr.io"),
            lambda s: s["app"].update(id=APP_ID + "-other"),
        )
        for change in changes:
            current = snapshot()
            change(current)
            with self.subTest(snapshot=current), self.assertRaises(guard.CheckError):
                guard.verify_live_image(environment(), IMAGE, current)

    def test_wrong_resource_configuration_fails(self):
        for key, value in (("AZURE_SUBSCRIPTION_ID", ""), ("AZURE_RESOURCE_GROUP", "../other"),
                           ("LAB_CONTAINER_APP", "different")):
            env = environment()
            env[key] = value
            with self.subTest(key=key), self.assertRaises(guard.CheckError):
                guard.verify_live_image(env, IMAGE, snapshot())

    def test_recovery_requires_known_attempt_and_one_known_active_revision(self):
        env = environment()
        env["ATTEMPTED_REVISION"] = "lab--attempted"
        env["ATTEMPTED_IMAGE"] = f"{REGISTRY}/workbench@sha256:" + "c" * 64
        guard.verify_live_image(env, IMAGE, recovery_snapshot(), recovery=True)
        changes = (
            lambda s: s["app"].update(latest="different"),
            lambda s: s["app"].update(containers=[{"name": "workbench", "image": IMAGE}]),
            lambda s: s["app"].update(ready="unknown"),
            lambda s: s["revisions"][0].update(active=False),
            lambda s: s["revisions"][1].update(active=True),
            lambda s: s["revisions"][0]["containers"][0].update(image="unknown:latest"),
        )
        for change in changes:
            current = recovery_snapshot()
            change(current)
            with self.subTest(snapshot=current), self.assertRaises(guard.CheckError):
                guard.verify_live_image(env, IMAGE, current, recovery=True)
        for key, value in (("ATTEMPTED_REVISION", ""), ("ATTEMPTED_IMAGE", IMAGE),
                           ("ATTEMPTED_IMAGE", "unknown:latest")):
            invalid = env.copy()
            invalid[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(guard.CheckError):
                guard.verify_live_image(invalid, IMAGE, recovery_snapshot(), recovery=True)

    def test_recovery_and_post_restore_do_not_depend_on_current_main_or_github(self):
        env = environment()
        env["ATTEMPTED_REVISION"] = "lab--attempted"
        env["ATTEMPTED_IMAGE"] = f"{REGISTRY}/workbench@sha256:" + "c" * 64
        env["GITHUB_API_URL"] = "https://unavailable.example"
        for flag, current in (("--recovery", recovery_snapshot()), ("--restored", snapshot()),
                              ("--deployed", deployed_snapshot())):
            with self.subTest(flag=flag), patch.object(guard.sys, "stdin", io.StringIO(json.dumps(current))), \
                    patch.object(guard, "verify_main") as verify, redirect_stdout(io.StringIO()):
                self.assertEqual(guard.main(["--live", flag], env), 0)
                verify.assert_not_called()
        with patch.object(guard, "verify_main", side_effect=guard.CheckError("main unavailable")) as verify, \
                redirect_stderr(io.StringIO()):
            self.assertEqual(guard.main([], env), 1)
            verify.assert_called_once()
        env["GITHUB_SHA"] = "b" * 40
        for flag in ("--recovery", "--restored", "--deployed"):
            with self.subTest(flag=flag), patch.object(guard, "verify_main") as verify, redirect_stderr(io.StringIO()):
                self.assertEqual(guard.main(["--live", flag], env), 1)
                verify.assert_not_called()

    def test_deployed_readback_requires_attempted_revision_and_pushed_digest(self):
        env = environment()
        env["ATTEMPTED_REVISION"] = "lab--attempted"
        env["ATTEMPTED_IMAGE"] = f"{REGISTRY}/workbench@sha256:" + "c" * 64
        guard.verify_deployed_image(env, IMAGE, deployed_snapshot())
        changes = (
            lambda s: s["app"]["containers"][0].update(image=IMAGE),
            lambda s: s["revisions"][0]["containers"][0].update(image=IMAGE),
            lambda s: s["revisions"][1].update(active=True),
            lambda s: s["revisions"][0].update(active=False),
            lambda s: s["app"].update(latest="different"),
            lambda s: s["revisions"][0].update(name="other"),
        )
        for change in changes:
            current = deployed_snapshot()
            change(current)
            with self.subTest(snapshot=current), self.assertRaises(guard.CheckError):
                guard.verify_deployed_image(env, IMAGE, current)
        env["ATTEMPTED_REVISION"] = "other"
        with self.assertRaises(guard.CheckError):
            guard.verify_deployed_image(env, IMAGE, deployed_snapshot())


class WorkflowTests(unittest.TestCase):
    def test_manual_main_only_and_no_hosted_vm_start(self):
        self.assertIn("  workflow_dispatch:", WORKFLOW)
        self.assertNotRegex(WORKFLOW, r"(?m)^\s+(push|schedule):")
        self.assertNotIn("az vm start", WORKFLOW)
        self.assertIn("needs: validate-source", WORKFLOW)
        self.assertIn("if: github.ref == 'refs/heads/main'", WORKFLOW)
        deploy = WORKFLOW.split("\n  deploy:\n", 1)[1]
        self.assertRegex(deploy, r"(?m)^    if: \$\{\{ false \}\}$")
        self.assertIn("runs-on: [self-hosted, linux, lab-runner]", WORKFLOW)
        self.assertIn("environment: lab-deploy", WORKFLOW)

    def test_existing_lab_apply_and_image_release_share_concurrency(self):
        self.assertRegex(WORKFLOW, r"(?s)concurrency:\s+group: deploy-lab\s+cancel-in-progress: false")
        self.assertRegex(APPLY_WORKFLOW, r"(?s)concurrency:\s+group: deploy-lab\s+cancel-in-progress: false")

    def test_live_check_precedes_both_registry_push_and_app_update(self):
        self.assertEqual(WORKFLOW.count("bash .github/scripts/check_lab_live_image.sh"), 6)
        build = WORKFLOW.split("- name: Build, check and push", 1)[1]
        self.assertLess(build.index("check_lab_live_image.sh"), build.index("docker push"))
        rollout = WORKFLOW.split("- name: Roll the Container App", 1)[1]
        self.assertLess(rollout.index("check_lab_live_image.sh"), rollout.index("az containerapp update"))
        self.assertIn('if [ "$latest" != "$attempted" ]', rollout)
        self.assertIn("check_lab_live_image.sh --deployed", rollout)
        self.assertIn("check_lab_live_image.sh --recovery", rollout)
        self.assertIn('if [ "$latest" != "$restored" ]', rollout)
        self.assertIn('if [ "$ready_revision" = "$restored" ]', rollout)
        self.assertLess(rollout.index("check_lab_live_image.sh --recovery"), rollout.index('--image "$previous"'))
        self.assertGreater(rollout.rindex("check_lab_live_image.sh"), rollout.index('--image "$previous"'))

    def test_action_and_input_boundaries(self):
        uses = re.findall(r"^\s*(?:- )?uses:", WORKFLOW, re.MULTILINE)
        pinned = re.findall(r"^\s*(?:- )?uses:\s*[\w./-]+@[0-9a-f]{40}\b", WORKFLOW, re.MULTILINE)
        self.assertTrue(uses)
        self.assertEqual(len(uses), len(pinned))
        self.assertIn("persist-credentials: false", WORKFLOW)
        self.assertNotIn("${{ inputs.reviewed_source_sha }}\"", WORKFLOW)


@unittest.skipUnless(shutil.which("bash"), "bash is required for offline rollout simulation")
class RolloutSimulationTests(unittest.TestCase):
    def run_rollout(self, scenario):
        body = WORKFLOW.split("      - name: Roll the Container App to the new image\n        run: |\n", 1)[1]
        body = textwrap.dedent(body)
        harness = r"""
az() {
  case "$*" in
    *"acr show"*) echo private.azurecr.io ;;
    *"containerapp update"*)
      if [[ "$*" == *"$EXPECTED_CURRENT_IMAGE"* ]]; then
        echo restored > "$MOCK_PHASE"
        echo RESTORE >&2
        echo lab--restored
      else
        echo attempted > "$MOCK_PHASE"
        echo UPDATE >&2
        if [[ "$SCENARIO" != missing-attempt ]]; then echo lab--attempted; fi
      fi ;;
    *"containerapp show"*"latestReadyRevisionName"*)
      phase="$(cat "$MOCK_PHASE")"
      if [[ "$phase" == attempted && ( "$SCENARIO" == forward-success || "$SCENARIO" == bad-readback ) ]]; then
        echo lab--attempted
      elif [[ "$phase" == restored && "$SCENARIO" != failed-restore ]]; then
        echo lab--restored
      else
        echo lab--old
      fi ;;
    *"containerapp show"*"latestRevisionName"*)
      phase="$(cat "$MOCK_PHASE")"
      if [[ "$SCENARIO" == concurrent && "$phase" == attempted ]]; then
        echo lab--external
      else
        echo "lab--$phase"
      fi ;;
    *"containerapp revision show"*) echo Running ;;
    *) echo "Unexpected Azure mock command" >&2; return 1 ;;
  esac
}
bash() {
  if [[ "$*" == *"--recovery"* && "$SCENARIO" == ambiguous ]]; then
    echo AMBIGUOUS >&2
    return 1
  fi
  if [[ "$*" == *"--deployed"* ]]; then
    echo VERIFY_DEPLOYED >&2
    if [[ "$SCENARIO" == bad-readback ]]; then return 1; fi
  fi
  echo GUARD >&2
}
sleep() { :; }
seq() { printf '%s\n' 1 2; }
"""
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / "phase")
            if os.name == "nt":
                path = "/" + path[0].lower() + path[2:].replace("\\", "/")
            env = os.environ.copy()
            env.update({
                "MOCK_PHASE": path, "SCENARIO": scenario, "LAB_REGISTRY": "private",
                "GITHUB_STEP_SUMMARY": path + "-summary",
                "LAB_CONTAINER_APP": "lab", "AZURE_RESOURCE_GROUP": "lab-rg",
                "EXPECTED_CURRENT_IMAGE": IMAGE,
                "IMAGE_SOURCE": f"{REGISTRY}/workbench@sha256:" + "c" * 64,
            })
            return subprocess.run(
                [shutil.which("bash"), "-s"], input=harness + body, env=env,
                text=True, capture_output=True, timeout=30, check=False,
            )

    def test_ambiguous_or_concurrent_rollout_never_restores(self):
        for scenario in ("ambiguous", "concurrent", "missing-attempt"):
            with self.subTest(scenario=scenario):
                result = self.run_rollout(scenario)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("UPDATE", result.stderr)
                self.assertNotIn("RESTORE", result.stderr)

    def test_restoration_is_confirmed_but_original_rollout_stays_failed(self):
        result = self.run_rollout("restored")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("RESTORE", result.stderr)
        self.assertIn("prior image is running again", result.stdout)
        self.assertGreaterEqual(result.stderr.count("GUARD"), 3)

    def test_failed_restoration_is_reported_as_unverified(self):
        result = self.run_rollout("failed-restore")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("RESTORE", result.stderr)
        self.assertIn("Recovery did not reach a verified running revision", result.stdout)
        self.assertNotIn("prior image is running again", result.stdout)

    def test_forward_success_requires_deployed_image_readback(self):
        success = self.run_rollout("forward-success")
        self.assertEqual(success.returncode, 0, success.stderr)
        self.assertIn("VERIFY_DEPLOYED", success.stderr)
        wrong = self.run_rollout("bad-readback")
        self.assertNotEqual(wrong.returncode, 0)
        self.assertIn("VERIFY_DEPLOYED", wrong.stderr)
        self.assertIn("deployed revision or image could not be verified", wrong.stdout)
        self.assertNotIn("RESTORE", wrong.stderr)


if __name__ == "__main__":
    unittest.main()

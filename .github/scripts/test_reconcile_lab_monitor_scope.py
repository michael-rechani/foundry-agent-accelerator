import contextlib
from copy import deepcopy
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import check_lab_terraform_plan as diagnostic
import reconcile_lab_monitor_scope as monitor
from test_check_lab_terraform_plan import DIGEST, REVISION, SUBSCRIPTION, environment, protected_config

APP_ID = (
    f"/subscriptions/{SUBSCRIPTION}/resourceGroups/rg-lab/providers/"
    "Microsoft.App/containerApps/foundry-workbench"
)
APP = {"app_id": APP_ID, "app_name": "foundry-workbench"}
IDS = monitor.expected_ids(APP)
INPUT = b'front_door_allowed_cidrs = ["private-address"]\nprivate_value = "keep-private"\n'


def scope_state():
    return {
        "version": 4,
        "resources": [{
            "mode": "managed", "type": "azurerm_monitor_private_link_scoped_service", "name": "logs",
            "instances": [{"attributes": {
                "id": IDS["association"], "scope_name": monitor.SCOPE_NAME, "linked_resource_id": IDS["workspace"],
            }}],
        }],
    }


def scope_response():
    return {
        "id": IDS["association"],
        "properties": {"linkedResourceId": IDS["workspace"], "provisioningState": "Succeeded"},
    }


def revision_response(entries):
    return {
        "id": APP_ID + "/revisions/" + REVISION,
        "properties": {"active": True, "template": {"containers": [{"name": "workbench", "env": entries}]}},
    }


def input_headers(body=INPUT, **overrides):
    return {
        "ETag": '"etag-1"', "x-ms-blob-type": "BlockBlob", "x-ms-lease-status": "unlocked",
        "content-length": str(len(body)), "content-type": "text/plain",
        "x-ms-meta-purpose": "private-metadata", **overrides,
    }


def resolved_inputs(platform=None, explicit_scope=None):
    return {
        "subscription_id": SUBSCRIPTION, "name": "foundry-workbench", "bootstrap_only": False,
        "enable_front_door": True, "image_digest": DIGEST, "platform_state": platform,
        "explicit_scope": explicit_scope, "unfinished_agents_enabled": False,
    }


class MonitorTargetTests(unittest.TestCase):
    def test_only_the_expected_saved_association_is_accepted(self):
        state = scope_state()
        self.assertEqual(monitor.validate_scope_state(json.dumps(state), APP), IDS)
        alterations = (
            {"id": IDS["association"] + "-wrong"},
            {"scope_name": "different-scope"},
            {"linked_resource_id": IDS["workspace"] + "-wrong"},
        )
        for alteration in alterations:
            changed = deepcopy(state)
            changed["resources"][0]["instances"][0]["attributes"].update(alteration)
            with self.subTest(alteration=alteration), self.assertRaises(diagnostic.CheckError):
                monitor.validate_scope_state(json.dumps(changed), APP)
        changed = deepcopy(state)
        changed["resources"][0]["instances"][0]["deposed"] = "old"
        with self.assertRaises(diagnostic.CheckError):
            monitor.validate_scope_state(json.dumps(changed), APP)
        with self.assertRaises(diagnostic.CheckError):
            monitor.expected_ids({**APP, "app_name": "another-app"})

    def test_live_association_is_read_only_and_must_match_the_existing_workspace(self):
        with (patch.object(monitor, "azure_token", return_value="private-token"),
              patch.object(monitor, "json_response", return_value=scope_response()) as request):
            monitor.validate_live_scope({}, IDS)
        self.assertTrue(request.call_args.args[0].endswith("?api-version=2021-07-01-preview"))
        self.assertEqual(request.call_args.kwargs["headers"]["Authorization"], "Bearer private-token")
        for replacement in (
            {"id": "wrong", "properties": scope_response()["properties"]},
            {**scope_response(), "properties": {"linkedResourceId": "wrong", "provisioningState": "Succeeded"}},
            {**scope_response(), "properties": {"linkedResourceId": IDS["workspace"], "provisioningState": "Failed"}},
        ):
            with (patch.object(monitor, "azure_token", return_value="private-token"),
                  patch.object(monitor, "json_response", return_value=replacement),
                  self.assertRaises(diagnostic.CheckError)):
                monitor.validate_live_scope({}, IDS)

    def test_unfinished_agent_flag_reads_only_the_active_revision_without_values(self):
        cases = (
            ([], "absent"),
            ([{"name": "WORKBENCH_UNFINISHED_AGENTS_ENABLED", "value": "false"}], "disabled"),
            ([{"name": "WORKBENCH_UNFINISHED_AGENTS_ENABLED", "value": "true"}], "enabled"),
        )
        for entries, expected in cases:
            with (self.subTest(expected=expected), patch.object(monitor, "azure_token", return_value="private-token"),
                  patch.object(monitor, "json_response", return_value=revision_response(entries))):
                self.assertEqual(monitor.live_unfinished_agents({}, APP, REVISION), expected)
        duplicate = [
            {"name": "WORKBENCH_UNFINISHED_AGENTS_ENABLED", "value": "true"},
            {"name": "WORKBENCH_UNFINISHED_AGENTS_ENABLED", "value": "false"},
        ]
        with (patch.object(monitor, "azure_token", return_value="private-token"),
              patch.object(monitor, "json_response", return_value=revision_response(duplicate)),
              self.assertRaises(diagnostic.CheckError)):
            monitor.live_unfinished_agents({}, APP, REVISION)

    def test_platform_output_is_read_without_disclosing_other_outputs(self):
        state = {"version": 4, "outputs": {"private-output": {"value": "private-value"}}}
        self.assertIsNone(monitor.platform_scope(json.dumps(state)))
        state["outputs"]["monitor_private_link_scope_name"] = {"value": monitor.SCOPE_NAME}
        self.assertEqual(monitor.platform_scope(json.dumps(state)), monitor.SCOPE_NAME)
        state["outputs"]["monitor_private_link_scope_name"] = {"value": ["unexpected"]}
        with self.assertRaises(diagnostic.CheckError):
            monitor.platform_scope(json.dumps(state))
        with self.assertRaises(diagnostic.CheckError):
            monitor.platform_scope(json.dumps({"version": 3, "outputs": {}}))

    def test_only_the_fixed_input_inspection_commands_are_allowed(self):
        terraform = object.__new__(monitor.MonitorTerraform)
        terraform.scratch = Path("private-scratch")
        terraform.inputs = terraform.scratch / "inputs.tfvars"
        backend = f"-backend-config={terraform.scratch / 'backend.hcl'}"
        var_file = f"-var-file={terraform.inputs}"
        with patch.object(monitor.Terraform, "command", return_value=b"private-output") as command:
            terraform.command("init", "-reconfigure", backend)
            terraform.command("console", var_file, input_data=monitor.CONSOLE_INPUT)
        self.assertEqual(command.call_count, 2)
        for args, kwargs in (
            (("plan",), {}),
            (("apply",), {}),
            (("console", var_file), {"input_data": b"private-unreviewed-expression"}),
            (("console", "-var-file=other"), {"input_data": monitor.CONSOLE_INPUT}),
        ):
            with self.subTest(args=args), self.assertRaises(diagnostic.CheckError):
                terraform.command(*args, **kwargs)

    def test_only_the_existing_scope_and_protected_input_shape_are_accepted(self):
        values = resolved_inputs()
        self.assertIsNone(monitor.validate_values(values, APP, DIGEST, protected_config()))
        for alteration in (
            {"explicit_scope": "wrong-private-scope"},
            {"name": "other-app"},
            {"image_digest": "sha256:" + "b" * 64},
            {"unfinished_agents_enabled": "false"},
            {"additional_private_input": "private-value"},
        ):
            with self.subTest(keys=list(alteration)), self.assertRaises(diagnostic.CheckError):
                monitor.validate_values({**values, **alteration}, APP, DIGEST, protected_config())

    def test_scope_append_preserves_every_original_byte(self):
        for raw in (INPUT, INPUT.rstrip(b"\n"), b'# comment without a newline'):
            with self.subTest(raw=raw):
                candidate = monitor.append_scope(raw)
                self.assertTrue(candidate.startswith(raw))
                self.assertTrue(candidate.endswith(b'\nmonitor_private_link_scope_name = "ampls-aifnd-dev"\n'))
        for raw in (b"", b"x" * (1024 * 1024 + 1), "not-bytes"):
            with self.subTest(raw_type=type(raw)), self.assertRaises(diagnostic.CheckError):
                monitor.append_scope(raw)

    @unittest.skipUnless(shutil.which("terraform"), "Terraform is not installed")
    def test_real_terraform_accepts_the_appended_scope_and_rejects_duplicate_assignments(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "main.tf").write_text(
                f'variable "subscription_id" {{\n  default = "{SUBSCRIPTION}"\n}}\n'
                'variable "name" {\n  default = "foundry-workbench"\n}\n'
                'variable "bootstrap_only" {\n  default = false\n}\n'
                'variable "enable_front_door" {\n  default = true\n}\n'
                f'variable "image_digest" {{\n  default = "{DIGEST}"\n}}\n'
                'variable "platform_state" {\n  default = null\n}\n'
                'variable "unfinished_agents_enabled" {\n  default = false\n}\n'
                'variable "monitor_private_link_scope_name" {\n  type = string\n  default = null\n}\n'
                'variable "front_door_allowed_cidrs" {\n  type = list(string)\n  default = []\n}\n'
                'variable "other" {\n  type = string\n  default = "default"\n}\n',
                encoding="utf-8",
            )
            result = subprocess.run(
                ["terraform", f"-chdir={root}", "init", "-backend=false", "-no-color"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
            )
            self.assertEqual(result.returncode, 0)
            path = root / "inputs.tfvars"
            original = b'front_door_allowed_cidrs = ["private-address"]\nother = "private-value"\n'
            expression = (
                b"jsonencode({scope=var.monitor_private_link_scope_name,"
                b"addresses=var.front_door_allowed_cidrs,other=var.other})\n"
            )

            def console(raw, command=expression):
                path.write_bytes(raw)
                return subprocess.run(
                    ["terraform", f"-chdir={root}", "console", "-no-color", f"-var-file={path}"],
                    input=command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
                )

            baseline = console(original)
            updated = console(monitor.append_scope(original))
            self.assertEqual(baseline.returncode, 0)
            self.assertEqual(updated.returncode, 0)
            before = json.loads(json.loads(baseline.stdout))
            after = json.loads(json.loads(updated.stdout))
            self.assertEqual(after, {**before, "scope": monitor.SCOPE_NAME})
            original_values = console(original, monitor.CONSOLE_INPUT)
            candidate_values = console(monitor.append_scope(original), monitor.CONSOLE_INPUT)
            self.assertEqual(original_values.returncode, 0)
            self.assertEqual(candidate_values.returncode, 0)
            resolved_before = json.loads(json.loads(original_values.stdout))
            resolved_after = json.loads(json.loads(candidate_values.stdout))
            self.assertEqual(resolved_after, {**resolved_before, "explicit_scope": monitor.SCOPE_NAME})
            self.assertFalse(resolved_after["unfinished_agents_enabled"])
            duplicate = console(monitor.append_scope(original + b"monitor_private_link_scope_name = null\n"))
            self.assertNotEqual(duplicate.returncode, 0)

    @unittest.skipUnless(shutil.which("terraform"), "Terraform is not installed")
    def test_real_terraform_console_does_not_refresh_a_remote_state_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "main.tf").write_text(
                'data "terraform_remote_state" "platform" {\n'
                '  backend = "local"\n'
                '  config = { path = "platform.tfstate" }\n'
                '}\n',
                encoding="utf-8",
            )
            (root / "platform.tfstate").write_text(json.dumps({
                "version": 4,
                "outputs": {"monitor_private_link_scope_name": {
                    "value": monitor.SCOPE_NAME, "type": "string", "sensitive": False,
                }},
                "resources": [],
            }), encoding="utf-8")
            initialized = subprocess.run(
                ["terraform", f"-chdir={root}", "init", "-backend=false", "-no-color"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
            )
            self.assertEqual(initialized.returncode, 0)
            result = subprocess.run(
                ["terraform", f"-chdir={root}", "console", "-no-color"],
                input=b"jsonencode(try(data.terraform_remote_state.platform.outputs.monitor_private_link_scope_name,null))\n",
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
            )
            self.assertEqual(result.returncode, 0)
            self.assertIn(b"known after apply", result.stdout)
            self.assertNotIn(b"local.platform_outputs", monitor.CONSOLE_INPUT)


class InputBlobTests(unittest.TestCase):
    def setUp(self):
        blobs = object.__new__(diagnostic.LabBlobs)
        blobs.base, blobs.headers = "https://stfixture.blob.core.windows.net/tfstate/ai-foundry/", {
            "Authorization": "Bearer private-token", "x-ms-version": "2023-11-03",
        }
        self.blob = monitor.InputBlob(blobs)

    def test_snapshot_uses_an_etag_guard_and_preserves_metadata_and_content_type(self):
        response = [(INPUT, {"ETag": '"etag-1"'}), (b"", input_headers())]
        with patch.object(monitor, "send", side_effect=response) as request:
            body, etag, preserved = self.blob.snapshot()
        self.assertEqual((body, etag), (INPUT, '"etag-1"'))
        self.assertEqual(preserved, {
            "x-ms-meta-purpose": "private-metadata", "x-ms-blob-content-type": "text/plain",
        })
        self.assertEqual(request.call_args_list[1].kwargs["method"], "HEAD")
        self.assertEqual(request.call_args_list[1].kwargs["headers"]["If-Match"], '"etag-1"')

    def test_snapshot_refuses_unsafe_or_changed_blob_properties(self):
        for alteration in (
            {"ETag": '"different"'}, {"x-ms-blob-type": "AppendBlob"}, {"x-ms-lease-status": "locked"},
            {"x-ms-tag-count": "1"}, {"x-ms-copy-status": "pending"}, {"x-ms-has-legal-hold": "true"},
            {"x-ms-has-immutability-policy": "true"}, {"x-ms-encryption-key-sha256": "private"},
            {"x-ms-expiry-time": "private"}, {"content-encoding": "gzip"}, {"content-length": "123"},
            {"content-md5": "invalid"}, {"x-ms-access-tier": "Archive"},
            {"x-ms-meta-terraformlockid": "private-lock"},
        ):
            responses = [(INPUT, {"ETag": '"etag-1"'}), (b"", input_headers(**alteration))]
            with (self.subTest(alteration=list(alteration)), patch.object(monitor, "send", side_effect=responses),
                  self.assertRaises(diagnostic.CheckError)):
                self.blob.snapshot()

    def test_lease_is_bounded_and_released_after_an_error(self):
        with patch.object(monitor, "send", return_value=(b"", {})) as request:
            with self.assertRaisesRegex(RuntimeError, "fixture"):
                with self.blob.lease('"etag-1"') as lease_id:
                    self.assertTrue(lease_id)
                    raise RuntimeError("fixture")
        acquire, release = request.call_args_list
        self.assertEqual(acquire.kwargs["headers"]["If-Match"], '"etag-1"')
        self.assertEqual(acquire.kwargs["headers"]["x-ms-lease-duration"], "60")
        self.assertEqual(acquire.kwargs["headers"]["x-ms-lease-action"], "acquire")
        self.assertEqual(release.kwargs["headers"]["x-ms-lease-action"], "release")
        self.assertEqual(release.kwargs["headers"]["x-ms-lease-id"], lease_id)

    def test_update_is_exactly_conditional_on_the_original_etag_and_lease(self):
        snapshot = (INPUT, '"etag-1"', {"x-ms-meta-purpose": "private-metadata"})
        candidate = monitor.append_scope(INPUT)
        with patch.object(monitor, "send", return_value=(b"", {})) as request:
            self.blob.replace(candidate, snapshot, "lease-id")
        self.assertEqual(request.call_args.kwargs["data"], candidate)
        self.assertEqual(request.call_args.kwargs["headers"]["If-Match"], '"etag-1"')
        self.assertEqual(request.call_args.kwargs["headers"]["x-ms-lease-id"], "lease-id")
        self.assertEqual(request.call_args.kwargs["headers"]["x-ms-meta-purpose"], "private-metadata")
        self.assertEqual(request.call_args.kwargs["expected"], (201,))


class MonitorRunTests(unittest.TestCase):
    def run_fixture(self, operation="inspect", failure=None, source="fallback"):
        calls = []
        platform = {
            "subscription_id": None, "resource_group_name": "rg-state", "storage_account_name": "stfixture",
            "container_name": "tfstate", "key": "ai-foundry/dev.tfstate",
        } if source == "platform" else None
        platform_value = monitor.SCOPE_NAME if source == "platform" else None

        class FakeBlobs:
            def __init__(self, _environment):
                self.counts = {}

            def snapshot(self, name):
                self.counts[name] = self.counts.get(name, 0) + 1
                if name == diagnostic.PLATFORM_STATE:
                    value = {"version": 4, "outputs": {
                        "monitor_private_link_scope_name": {"value": platform_value},
                    }}
                    return json.dumps(value).encode(), '"platform"', {}
                if failure == "state" and self.counts[name] > 1:
                    return b"concurrent-state", '"state"', {}
                return b"private-state", '"state"', {}

        class FakeInputBlob:
            def __init__(self, _blobs):
                self.body, self.etag = INPUT, '"input-1"'
                self.count = 0

            def snapshot(self, lease_id=None):
                self.count += 1
                if failure == "input" and self.count > 1:
                    return b"concurrent-private-input", '"input-2"', {}
                if failure == "leased-input" and lease_id:
                    return b"concurrent-private-input", '"input-2"', {}
                return self.body, self.etag, {}

            @contextlib.contextmanager
            def lease(self, etag):
                calls.append(("lease", etag))
                try:
                    yield "private-lease"
                finally:
                    calls.append(("release", etag))

            def replace(self, candidate, snapshot, lease_id):
                calls.append(("replace", candidate, snapshot, lease_id))
                self.body, self.etag = candidate, '"input-2"'
                if failure == "uncertain-write":
                    raise diagnostic.CheckError("Private write response was unavailable.")

        class FakeTerraform:
            def __init__(self, _root, scratch, _environment, inputs):
                self.inputs = scratch / "inputs.tfvars"
                self.inputs.write_bytes(inputs)

            def inputs_resolved(self):
                appended = b'monitor_private_link_scope_name = "ampls-aifnd-dev"' in self.inputs.read_bytes()
                explicit = monitor.SCOPE_NAME if appended or source == "explicit" else None
                if source == "wrong":
                    explicit = "wrong-private-scope"
                result = resolved_inputs(platform, explicit)
                if appended and failure == "candidate":
                    result["name"] = "changed-private-app"
                return result

        def fake_stage(scratch, _environment):
            root = scratch / "source"
            root.mkdir()
            return root

        with tempfile.TemporaryDirectory() as folder:
            env = {**environment(folder), "TF_LAB_MONITOR_OPERATION": operation}
            runtime = {**protected_config(), **env}
            output, errors = io.StringIO(), io.StringIO()
            with (patch.object(monitor, "configuration", return_value=runtime),
                  patch.object(monitor, "LabBlobs", FakeBlobs),
                  patch.object(monitor, "InputBlob", FakeInputBlob),
                  patch.object(monitor, "lab_state", return_value=APP),
                  patch.object(monitor, "validate_scope_state", return_value=IDS),
                  patch.object(monitor, "current_image", return_value=(REVISION, DIGEST)),
                  patch.object(monitor, "validate_live_scope") as live,
                  patch.object(monitor, "live_unfinished_agents", return_value="absent"),
                  patch.object(monitor, "stage_sources", side_effect=fake_stage),
                  patch.object(monitor, "configure_platform_oidc"),
                  patch.object(monitor, "write_supplemental_files"),
                  patch.object(monitor, "MonitorTerraform", FakeTerraform),
                  contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors)):
                if failure or source == "wrong":
                    with self.assertRaises(diagnostic.CheckError):
                        monitor.run(env)
                else:
                    monitor.run(env)
            self.assertEqual(list(Path(folder).iterdir()), [])
        self.assertNotIn("private-address", output.getvalue() + errors.getvalue())
        self.assertNotIn("keep-private", output.getvalue() + errors.getvalue())
        return calls, output.getvalue(), errors.getvalue(), live.call_count

    def test_inspection_is_read_only_and_validates_the_live_association(self):
        calls, output, errors, count = self.run_fixture()
        self.assertEqual(calls, [])
        self.assertIn("scope source: fallback", output)
        self.assertIn("No canonical inputs were changed", output)
        self.assertEqual(errors, "")
        self.assertGreaterEqual(count, 2)

    def test_pinning_appends_only_the_existing_scope_and_preserves_input_bytes(self):
        calls, output, errors, count = self.run_fixture(operation="pin-existing-scope")
        writes = [call for call in calls if call[0] == "replace"]
        self.assertEqual(len(writes), 1)
        self.assertEqual(writes[0][1], monitor.append_scope(INPUT))
        self.assertTrue(writes[0][1].startswith(INPUT))
        self.assertEqual(calls[0][0], "lease")
        self.assertEqual(calls[-1][0], "release")
        self.assertIn("scope source: pinned", output)
        self.assertIn("No Terraform apply, WAF change", output)
        self.assertEqual(errors, "")
        self.assertGreaterEqual(count, 4)

    def test_existing_explicit_or_platform_source_needs_no_write(self):
        for source in ("explicit", "platform"):
            with self.subTest(source=source):
                calls, output, _, _ = self.run_fixture(operation="pin-existing-scope", source=source)
                self.assertEqual(calls, [])
                self.assertIn(f"scope source: {source}", output)

    def test_concurrent_changes_and_unexpected_candidate_stop_before_writing(self):
        for failure in ("state", "input", "leased-input", "candidate"):
            with self.subTest(failure=failure):
                calls, _, errors, _ = self.run_fixture(operation="pin-existing-scope", failure=failure)
                self.assertFalse(any(call[0] == "replace" for call in calls))
                self.assertEqual(errors, "")
        calls, _, _, _ = self.run_fixture(operation="pin-existing-scope", source="wrong")
        self.assertEqual(calls, [])

    def test_ambiguous_write_fails_visibly_and_releases_the_lease(self):
        calls, _, errors, _ = self.run_fixture(operation="pin-existing-scope", failure="uncertain-write")
        self.assertEqual(calls[-1][0], "release")
        self.assertIn("input update was attempted", errors)
        self.assertNotIn("private-lease", errors)

    def test_protected_workflow_contract(self):
        workflow = (diagnostic.ROOT / ".github" / "workflows" / "reconcile-lab-monitor-scope.yml").read_text()
        for required in (
            "workflow_dispatch:", "github.ref == 'refs/heads/main'", "terraform-state-access",
            "cancel-in-progress: false", "[self-hosted, linux, lab-runner]", "environment: terraform-state",
            "id-token: write", "persist-credentials: false", "terraform_wrapper: false",
            "secrets.TF_LAB_PLAN_CONFIG", "options: [inspect, pin-existing-scope]", "if: always()", "--cleanup",
        ):
            self.assertIn(required, workflow)
        for forbidden in ("upload-artifact", "terraform apply", "-target", "-refresh=false", "azure/login"):
            self.assertNotIn(forbidden, workflow)


if __name__ == "__main__":
    unittest.main()

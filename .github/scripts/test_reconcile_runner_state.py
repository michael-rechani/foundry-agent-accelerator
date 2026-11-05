import contextlib
from copy import deepcopy
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import reconcile_runner_state as reconcile

SUBSCRIPTION = "11111111-2222-3333-4444-555555555555"
BASE = f"/subscriptions/{SUBSCRIPTION}/resourceGroups/"
SCOPES = {
    "runner": BASE + "rg-runner",
    "network": BASE + "rg-network/providers/Microsoft.Network/virtualNetworks/management",
    "nat": BASE + "rg-network/providers/Microsoft.Network/natGateways/existing",
}
ASSIGNMENTS = {
    key: scope + f"/providers/Microsoft.Authorization/roleAssignments/00000000-0000-0000-0000-{index:012d}"
    for index, (key, scope) in enumerate(SCOPES.items(), start=1)
}


def fixture():
    reader = {
        "subscription_id": SUBSCRIPTION, "principal_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "scopes": SCOPES, "existing_assignment_ids": ASSIGNMENTS,
    }
    runner = dict.fromkeys(reconcile.RUNNER_KEYS, "fixture")
    runner.update({
        "subscription_id": SUBSCRIPTION, "resource_group_name": "rg-network",
        "runner_resource_group_name": "rg-runner", "virtual_network_name": "management",
        "nat_gateway_name": "existing", "environment": "dev", "base_name": "aifnd",
        "approve_shared_egress": True, "github_repository": "fixture/repo",
        "registry_private_endpoint_ips": ["10.42.0.24", "10.42.0.25"],
        "foundry_private_endpoint_ips": ["10.42.0.17"],
        "state_backend_private_endpoint_ips": ["10.42.0.23"],
    })
    return deepcopy({"reader": reader, "runner": runner})


def environment(config=None):
    return {
        "AZURE_SUBSCRIPTION_ID": SUBSCRIPTION, "AZURE_CLIENT_ID": SUBSCRIPTION,
        "AZURE_TENANT_ID": SUBSCRIPTION, "TF_STATE_ACCOUNT": "stfixture",
        "TF_STATE_CONTAINER": "tfstate", "TF_STATE_PRIVATE_ENDPOINT": "10.42.0.23",
        "GITHUB_REPOSITORY": "fixture/repo", "GITHUB_REF": "refs/heads/main",
        "GITHUB_RUN_ID": "12345", "GITHUB_RUN_ATTEMPT": "1",
        "TF_RUNNER_PLAN_CONFIG": json.dumps(config or fixture()),
        "TF_RECONCILE_OPERATION": "import-readers",
    }


def plan(imports=None):
    return {
        "errored": False, "complete": True,
        "resource_changes": [
            {"address": address, "mode": "managed", "change": {
                "actions": ["no-op"], "importing": {"id": resource_id},
            }} for address, resource_id in (imports or {}).items()
        ],
    }


def state():
    return json.dumps({
        "version": 4, "serial": 7, "lineage": SUBSCRIPTION,
        "resources": [
            {"mode": "managed", "type": "azurerm_resource_group", "name": "runner",
             "instances": [{"attributes": {"id": SCOPES["runner"]}}]},
            {"mode": "managed", "type": "azurerm_linux_virtual_machine", "name": "runner",
             "instances": [{"attributes": {"id": SCOPES["runner"]
                                          + "/providers/Microsoft.Compute/virtualMachines/vm-runner-aifnd-dev"}}]},
        ],
    }).encode()


class ReconciliationTests(unittest.TestCase):
    def test_exact_configuration_and_namespace(self):
        with patch.object(reconcile, "validate_backend"):
            self.assertEqual(reconcile.configuration(environment()), fixture())
            for mutate in (
                lambda config: config["reader"]["scopes"].update(runner=f"/subscriptions/{SUBSCRIPTION}"),
                lambda config: config["reader"]["existing_assignment_ids"].pop("nat"),
                lambda config: config["runner"].update(registry_private_endpoint_ips=[]),
                lambda config: config["runner"].update(foundry_private_endpoint_ips=[]),
                lambda config: config["runner"].update(state_backend_private_endpoint_ips=["8.8.8.8"]),
                lambda config: config["runner"].update(github_repository="untrusted/repo"),
                lambda config: config["runner"].update(resource_group_name="../other"),
                lambda config: config["runner"].update(subscription_id="other"),
                lambda config: config["runner"].update(approve_shared_egress=False),
                lambda config: config["runner"].update(unreviewed="value"),
            ):
                config = fixture()
                mutate(config)
                with self.subTest(config=config), self.assertRaises(reconcile.CheckError):
                    reconcile.configuration(environment(config))

    def test_wrong_or_empty_runner_state_is_rejected(self):
        self.assertEqual(reconcile.populated_runner_state(state(), fixture()["runner"]), 7)
        for raw in (b"{}", b'{"version":4,"serial":0,"lineage":"new","resources":[]}',
                    state().replace(b"vm-runner-aifnd-dev", b"vm-other"), b"secret not JSON"):
            with self.subTest(raw=raw), self.assertRaises(reconcile.CheckError):
                reconcile.populated_runner_state(raw, fixture()["runner"])

    def test_exact_import_plan_and_no_change_followup(self):
        imports = {'azurerm_role_assignment.reader["runner"]': ASSIGNMENTS["runner"]}
        reconcile.guard_plan(plan(imports), imports)
        reconcile.guard_plan(plan(), {})
        for unexpected in ({}, {"unexpected": ASSIGNMENTS["runner"]}):
            with self.assertRaises(reconcile.CheckError):
                reconcile.guard_plan(plan(imports), unexpected)

    def test_create_update_delete_replace_and_forget_are_rejected(self):
        for actions in (["create"], ["update"], ["delete"], ["delete", "create"], ["forget"], ["read"]):
            value = plan({"resource.example": "id"})
            value["resource_changes"][0]["change"]["actions"] = actions
            with contextlib.redirect_stdout(io.StringIO()):
                with self.subTest(actions=actions), self.assertRaises(reconcile.CheckError):
                    reconcile.guard_plan(value, {"resource.example": "id"})

    def test_incomplete_deferred_errored_checks_actions_and_outputs_fail(self):
        for additions in (
            {"complete": False}, {"errored": True}, {"deferred_changes": [{}]},
            {"action_invocations": [{}]}, {"checks": [{"status": "unknown"}]},
            {"output_changes": {"value": {"actions": ["create"]}}},
        ):
            with self.subTest(additions=additions), self.assertRaises(reconcile.CheckError):
                reconcile.guard_plan({**plan(), **additions}, {})

    def test_drift_reports_attribute_names_without_sensitive_values(self):
        value = plan({"resource.example": "id"})
        value["resource_changes"][0]["change"].update(
            actions=["update"], before={"custom_data": "old-secret"}, after={"custom_data": "new-secret"},
        )
        with contextlib.redirect_stdout(io.StringIO()) as output, self.assertRaises(reconcile.CheckError):
            reconcile.guard_plan(value, {})
        self.assertIn("custom_data", output.getvalue())
        self.assertNotIn("old-secret", output.getvalue())
        self.assertNotIn("new-secret", output.getvalue())

    def test_existing_canonical_inputs_are_compared_without_a_write(self):
        blobs = object.__new__(reconcile.Blobs)
        blobs.base, blobs.headers = "https://stfixture.blob.core.windows.net/tfstate/ai-foundry/", {}
        with patch.object(reconcile, "send", return_value=(b'{"value":1}', {})) as send:
            self.assertEqual(blobs.inputs("runner-dev.tfvars.json", {"value": 1}), b'{"value":1}')
            self.assertEqual(send.call_count, 1)
            self.assertNotIn("method", send.call_args.kwargs)
        with patch.object(reconcile, "send", return_value=(b'{"value":2}', {})):
            with self.assertRaisesRegex(reconcile.CheckError, "differ"):
                blobs.inputs("runner-dev.tfvars.json", {"value": 1})

    def test_only_a_proven_missing_input_blob_is_conditionally_created(self):
        blobs = object.__new__(reconcile.Blobs)
        blobs.base, blobs.headers = "https://stfixture.blob.core.windows.net/tfstate/ai-foundry/", {}
        responses = [
            (b"", {"x-ms-error-code": "BlobNotFound"}), (b"", {}), (b'{"value":1}', {}),
        ]
        with patch.object(reconcile, "send", side_effect=responses) as send:
            self.assertEqual(blobs.inputs("runner-dev.tfvars.json", {"value": 1}), b'{"value":1}')
            self.assertEqual(send.call_args_list[1].kwargs["headers"]["If-None-Match"], "*")
            self.assertEqual(send.call_args_list[1].kwargs["expected"], (201, 412))
        with patch.object(reconcile, "send", return_value=(b"", {"x-ms-error-code": "ContainerNotFound"})) as send:
            with self.assertRaisesRegex(reconcile.CheckError, "unexpected storage error"):
                blobs.inputs("runner-dev.tfvars.json", {"value": 1})
            self.assertEqual(send.call_count, 1)

    def test_concurrent_input_creation_never_replaces_different_content(self):
        blobs = object.__new__(reconcile.Blobs)
        blobs.base, blobs.headers = "https://stfixture.blob.core.windows.net/tfstate/ai-foundry/", {}
        responses = [
            (b"", {"x-ms-error-code": "BlobNotFound"}),
            (b"", {"x-ms-error-code": "ConditionNotMet"}),
            (b'{"value":2}', {}),
        ]
        with patch.object(reconcile, "send", side_effect=responses):
            with self.assertRaisesRegex(reconcile.CheckError, "differ"):
                blobs.inputs("runner-dev.tfvars.json", {"value": 1})

    def test_terraform_disables_fallbacks_and_inherited_cli_injections(self):
        env = {
            **environment(), "TF_CLI_ARGS_plan": "-target=unsafe", "TF_LOG": "TRACE",
            "ARM_ACCESS_KEY": "secret", "ARM_CLIENT_SECRET": "secret",
            "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "short-lived",
        }
        with (tempfile.TemporaryDirectory() as folder,
              patch.object(reconcile.shutil, "which", return_value="/approved/terraform"),
              patch.object(reconcile.Terraform, "command")):
            cli = reconcile.Terraform(Path("root"), Path(folder), env, "runner-dev.tfstate", b"{}")
            self.assertNotIn("TF_CLI_ARGS_plan", cli.env)
            self.assertNotIn("ARM_CLIENT_SECRET", cli.env)
            self.assertNotIn("ARM_ACCESS_KEY", cli.env)
            self.assertNotIn("TF_LOG", cli.env)
            self.assertEqual(cli.env["ARM_USE_CLI"], "false")
            self.assertEqual(cli.env["ARM_USE_MSI"], "false")
            self.assertEqual(cli.env["TF_WORKSPACE"], "default")
            self.assertEqual(cli.env["ACTIONS_ID_TOKEN_REQUEST_TOKEN"], "short-lived")
            self.assertIn('key = "ai-foundry/runner-dev.tfstate"', (Path(folder) / "backend.hcl").read_text())

    def test_missing_terraform_is_an_explicit_failure(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(reconcile.shutil, "which", return_value=None):
            with self.assertRaisesRegex(reconcile.CheckError, "Terraform is missing"):
                reconcile.Terraform(Path("root"), Path(folder), environment(), "runner-dev.tfstate", b"{}")

    def test_raw_provider_diagnostics_are_not_logged(self):
        cli = object.__new__(reconcile.Terraform)
        cli.root, cli.env, cli.binary = Path("root"), {}, "terraform"
        result = subprocess.CompletedProcess([], 1, b"", b"AuthorizationFailed: private-token")
        with patch.object(reconcile.subprocess, "run", return_value=result) as process:
            with self.assertRaisesRegex(reconcile.CheckError, "AuthorizationFailed") as caught:
                cli.command("show", "-json", "private.tfplan")
            self.assertNotIn("private-token", str(caught.exception))
            self.assertEqual(process.call_args.args[0][-1], "private.tfplan")

    def test_saved_plan_tampering_prevents_apply(self):
        cli = object.__new__(reconcile.Terraform)
        with tempfile.TemporaryDirectory() as folder, patch.object(cli, "command") as command:
            saved = Path(folder) / "guarded.tfplan"
            saved.write_bytes(b"tampered")
            with self.assertRaisesRegex(reconcile.CheckError, "changed"):
                cli.apply_imports(saved, b"wrong-digest")
            command.assert_not_called()

    def test_cleanup_is_limited_to_exact_run_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            env = {**environment(), "RUNNER_TEMP": folder}
            target = reconcile.scratch_path(env)
            target.mkdir()
            (target / "private-plan").write_text("private")
            other = Path(folder) / "unrelated"
            other.mkdir()
            reconcile.cleanup(env)
            self.assertFalse(target.exists())
            self.assertTrue(other.is_dir())
            with self.assertRaises(reconcile.CheckError):
                reconcile.scratch_path({**env, "GITHUB_RUN_ID": "../unsafe"})

    def test_exact_zero_exit_code_required_for_no_changes(self):
        cli = object.__new__(reconcile.Terraform)
        with tempfile.TemporaryDirectory() as folder:
            cli.scratch, cli.inputs = Path(folder), Path(folder) / "inputs.tfvars.json"
            def command(verb, *args, **kwargs):
                cli.last_exitcode = 2 if verb == "plan" else 0
                return json.dumps(plan()).encode()
            with patch.object(cli, "command", side_effect=command):
                with self.assertRaisesRegex(reconcile.CheckError, "exit code 0"):
                    cli.plan("verify", {})

    def test_workflow_remains_manual_main_only_reviewed_and_no_public_artifacts(self):
        workflow = (reconcile.ROOT / ".github" / "workflows" / "check-terraform-runner.yml").read_text()
        for required in ("workflow_dispatch:", "environment: terraform-state",
                         "if: github.ref == 'refs/heads/main'", "id-token: write",
                         "cancel-in-progress: false", "terraform_wrapper: false"):
            self.assertIn(required, workflow)
        for forbidden in ("pull_request", "upload-artifact", "az vm start", "azure/login"):
            self.assertNotIn(forbidden, workflow)
        self.assertIn("${{ secrets.TF_RUNNER_PLAN_CONFIG }}", workflow)
        self.assertNotIn("${{ vars.TF_RUNNER_PLAN_CONFIG }}", workflow)

    def test_orchestration_imports_only_access_and_cleans_private_files(self):
        self.orchestrate("import-readers")

    def test_plan_operation_never_initializes_or_applies_access(self):
        self.orchestrate("plan")

    def test_runner_drift_stops_without_applying_and_cleans_private_files(self):
        self.orchestrate("import-readers", drift=True)

    def orchestrate(self, operation, drift=False):
        calls = []
        reads = []

        class FakeBlobs:
            def __init__(self, environ):
                pass

            def read(self, name):
                reads.append(name)
                if name == "runner-dev.tfstate":
                    return state()
                return json.dumps({"resources": [{"mode": "managed", "instances": [{}, {}, {}]}]}).encode()

            def inputs(self, name, values):
                return json.dumps(values).encode()

        class FakeTerraform:
            def __init__(self, root, scratch, environ, key, inputs):
                self.name = root.name
                self.scratch = scratch
                (scratch / "private-plan").write_text("private")
                calls.append((self.name, "init"))

            def command(self, *args):
                return b"{}"

            def plan(self, name, expected):
                calls.append((self.name, name))
                if self.name == "runner" and drift:
                    raise reconcile.CheckError("runner drift")
                return self.scratch / "private-plan", b"digest"

            def apply_imports(self, saved, digest):
                calls.append((self.name, "apply"))

        with tempfile.TemporaryDirectory() as folder:
            env = {**environment(), "RUNNER_TEMP": folder, "TF_RECONCILE_OPERATION": operation}
            with (patch.object(reconcile, "validate_backend"),
                  patch.object(reconcile, "Blobs", FakeBlobs),
                  patch.object(reconcile, "Terraform", FakeTerraform),
                  contextlib.redirect_stdout(io.StringIO())):
                if drift:
                    with self.assertRaisesRegex(reconcile.CheckError, "drift"):
                        reconcile.run(env)
                else:
                    reconcile.run(env)
            self.assertEqual(list(Path(folder).iterdir()), [])
        self.assertNotIn(("runner", "apply"), calls)
        self.assertEqual(reads.count("runner-dev.tfstate"), 2)
        if operation == "import-readers":
            self.assertEqual(calls[:4], [
                ("runner-plan-access", "init"), ("runner-plan-access", "adopt"),
                ("runner-plan-access", "apply"), ("runner-plan-access", "verify"),
            ])
        else:
            self.assertTrue(all(root == "runner" for root, _ in calls))


if __name__ == "__main__":
    unittest.main()

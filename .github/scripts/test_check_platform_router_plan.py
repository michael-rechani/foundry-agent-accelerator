import contextlib
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

import check_lab_terraform_plan as lab
import check_platform_router_plan as diagnostic
import reconcile_runner_state as reconcile
from test_check_lab_terraform_plan import SUBSCRIPTION, archive, environment, protected_config

ACCOUNT = (
    f"/subscriptions/{SUBSCRIPTION}/resourceGroups/rg-private"
    "/providers/Microsoft.CognitiveServices/accounts/foundry-private"
)
PRINCIPAL = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
INPUT_NAME = "platform/private.tfvars"



def reviewed_root(root):
    for name in diagnostic.DIAGNOSTIC_ROOT_FILES:
        shutil.copyfile(lab.ROOT / "terraform" / name, root / name)

def state_object():
    return {
        "version": 4,
        "serial": 12,
        "lineage": "private-lineage",
        "outputs": {"foundry_account_id": {"value": ACCOUNT}},
        "resources": [{
            "mode": "managed", "type": "azurerm_role_assignment", "name": "deployer_foundry_user",
            "instances": [{"attributes": {"principal_id": PRINCIPAL}}],
        }],
    }


def values():
    return {
        "subscription_id": SUBSCRIPTION,
        "deployment_principal_id": PRINCIPAL,
        "model_router_deployment": deepcopy(diagnostic.ROUTER_INPUT),
        "jumpbox_secret_required": False,
    }


def plan():
    body = diagnostic.router_body()
    variables = {key: {"value": value} for key, value in values().items() if key != "jumpbox_secret_required"}
    variables.update({
        "model_deployment": {"value": {
            "deployment_name": "gpt-4.1", "format": "OpenAI", "name": "gpt-4.1", "version": "2025-04-14",
        }},
        "additional_model_deployments": {"value": {}},
    })
    return {
        "format_version": "1.0", "errored": False, "complete": True,
        "variables": variables,
        "resource_changes": [
            {
                "address": diagnostic.DEPLOYMENT, "mode": "managed",
                "change": {
                    "actions": ["create"], "before": None,
                    "after": {
                        "type": "Microsoft.CognitiveServices/accounts/deployments@2025-10-01-preview",
                        "name": "model-router", "parent_id": ACCOUNT, "body": body,
                    },
                    "after_unknown": {"body": {"properties": {"model": {}, "routing": {"models": [{}, {}]}}}},
                },
            },
            {
                "address": diagnostic.READBACK, "mode": "data", "type": "azapi_resource",
                "change": {
                    "actions": ["read"], "before": None,
                    "after": {
                        "type": "Microsoft.CognitiveServices/accounts/deployments@2025-12-01",
                        "response_export_values": ["properties.routing"],
                    },
                    "after_unknown": {"output": True, "resource_id": True},
                },
            },
            {
                "address": "azapi_resource.jumpbox[0]", "mode": "managed",
                "change": {"actions": ["no-op"], "before": {}, "after": {}, "after_unknown": {}},
            },
        ],
        "output_changes": {
            "model_router_deployment_name": {"actions": ["create"], "after_unknown": True},
            "model_deployment_names": {
                "actions": ["update"], "before": ["gpt-4.1"],
                "after": ["gpt-4.1", None], "after_unknown": [False, True],
            },
            "model_preview_encrypted_reasoning": {
                "actions": ["create"], "before": None,
                "after": {"gpt-4.1": False, "model-router": False}, "after_unknown": False,
            },
            "foundry_account_id": {"actions": ["no-op"]},
        },
        "checks": [{
            "address": {
                "kind": "resource", "mode": "data", "type": "azapi_resource",
                "name": "model_router_routing", "module": "module.model_router",
                "to_display": "module.model_router.data.azapi_resource.model_router_routing",
            },
            "status": "unknown",
            "instances": [{
                "address": {"module": "module.model_router", "instance_key": 0, "to_display": diagnostic.READBACK},
                "status": "unknown",
            }],
        }],
    }


class ConfigurationAndStateTests(unittest.TestCase):
    def test_only_a_protected_tfvars_blob_under_the_state_prefix_is_accepted(self):
        with patch.object(diagnostic, "lab_configuration", return_value=protected_config()):
            runtime = diagnostic.configuration({"TF_PLATFORM_INPUT_BLOB": INPUT_NAME})
            self.assertEqual(runtime["PLATFORM_INPUT_BLOB"], INPUT_NAME)
            for name in ("", "../escape.tfvars", "/private.tfvars", "one//two.tfvars", "one\\two.tfvars",
                         "file.tfstate", "one/two/three/four.tfvars", "private.tfvars?x=1"):
                with self.subTest(name=name), self.assertRaises(diagnostic.CheckError):
                    diagnostic.configuration({"TF_PLATFORM_INPUT_BLOB": name})

    def test_platform_state_and_inputs_preserve_existing_principal(self):
        platform = diagnostic.platform_state(json.dumps(state_object()).encode(), SUBSCRIPTION)
        self.assertEqual(platform, {"account": ACCOUNT, "principal": PRINCIPAL})
        diagnostic.validate_inputs(values(), platform, SUBSCRIPTION)
        for change in (
            lambda item: item.update(deployment_principal_id=None),
            lambda item: item.update(deployment_principal_id=SUBSCRIPTION),
            lambda item: item.update(subscription_id=PRINCIPAL),
            lambda item: item["model_router_deployment"].update(routing_mode="quality"),
            lambda item: item.update(jumpbox_secret_required=True),
            lambda item: item.update(jumpbox_secret_required=None),
        ):
            item = values()
            change(item)
            with self.subTest(item=item), self.assertRaises(diagnostic.CheckError):
                diagnostic.validate_inputs(item, platform, SUBSCRIPTION)

    def test_invalid_or_wrong_platform_state_is_rejected_without_values(self):
        for change in (
            lambda item: item.update(version=3),
            lambda item: item["outputs"].update(foundry_account_id="not-an-output"),
            lambda item: item["outputs"]["foundry_account_id"].update(value=ACCOUNT.replace(SUBSCRIPTION, PRINCIPAL)),
            lambda item: item["resources"].clear(),
            lambda item: item["resources"].append(deepcopy(item["resources"][0])),
            lambda item: item["resources"][0]["instances"][0]["attributes"].update(principal_id="private-invalid"),
        ):
            item = state_object()
            change(item)
            with self.subTest(item=item), self.assertRaises(diagnostic.CheckError) as raised:
                diagnostic.platform_state(json.dumps(item).encode(), SUBSCRIPTION)
            self.assertNotIn("private-invalid", str(raised.exception))
            self.assertNotIn(ACCOUNT, str(raised.exception))

    def test_state_snapshot_ignores_only_lock_etag_changes(self):
        old = (b"private-state", "etag-a", {"x-ms-meta-test": "private"})
        self.assertTrue(diagnostic.snapshot_unchanged(diagnostic.PLATFORM_STATE, old, (old[0], "etag-b", old[2])))
        self.assertFalse(diagnostic.snapshot_unchanged(diagnostic.PLATFORM_STATE, old, (b"other", old[1], old[2])))
        self.assertFalse(diagnostic.snapshot_unchanged(diagnostic.PLATFORM_STATE, old, (old[0], old[1], {})))
        self.assertFalse(diagnostic.snapshot_unchanged(INPUT_NAME, old, (old[0], "etag-b", old[2])))


class SourceAndTerraformTests(unittest.TestCase):
    def test_platform_source_stages_only_the_checked_revision_without_automatic_inputs(self):
        files = [("terraform/main.tf", b"terraform {}"), ("terraform/variables.tf", b"variable \"x\" {}")]
        completed = subprocess.CompletedProcess([], 0, stdout=archive(files), stderr=b"")
        with tempfile.TemporaryDirectory() as folder:
            with (patch.object(lab.shutil, "which", return_value="git"),
                  patch.object(lab.subprocess, "run", return_value=completed) as process):
                root = lab.stage_sources(Path(folder), environment(), kind="platform")
            self.assertEqual((root / "main.tf").read_bytes(), b"terraform {}")
            self.assertEqual(process.call_args.args[0][-1], "terraform")
            self.assertNotIn("ACTIONS_ID_TOKEN_REQUEST_TOKEN", process.call_args.kwargs["env"])
        for extra in (
            ("terraform/private.auto.tfvars", b"private"),
            ("terraform/terraform.tfvars.json", b"private"),
            ("terraform/../../escape", b"private"),
            ("terraform/..\\..\\escape", b"private"),
            ("workbench/infra/main.tf", b"private"),
            ("terraform/link", None),
        ):
            completed = subprocess.CompletedProcess([], 0, stdout=archive(files + [extra]), stderr=b"")
            with tempfile.TemporaryDirectory() as folder:
                with (patch.object(lab.shutil, "which", return_value="git"),
                      patch.object(lab.subprocess, "run", return_value=completed),
                      self.assertRaises(diagnostic.CheckError)):
                    lab.stage_sources(Path(folder), environment(), kind="platform")

    @unittest.skipUnless(shutil.which("git"), "Git is not installed")
    def test_real_git_archive_stages_the_existing_committed_platform_source(self):
        executable = shutil.which("git")
        revision = subprocess.run(
            [executable, "-C", str(lab.ROOT), "rev-parse", "HEAD"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
        ).stdout.decode().strip()
        with tempfile.TemporaryDirectory() as folder:
            root = lab.stage_sources(Path(folder), {**environment(), "GITHUB_SHA": revision}, kind="platform")
            self.assertTrue((root / "main.tf").is_file())
            self.assertTrue((root / "variables.tf").is_file())
            self.assertFalse((root / "terraform.tfvars").exists())

    def test_private_backend_overlay_and_command_allowlist_never_apply_or_target(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            reviewed_root(root)
            diagnostic.write_backend(root)
            overlay = json.loads((root / diagnostic.DIAGNOSTIC_OVERLAY).read_text())
            self.assertEqual(overlay['terraform']['backend'], {'azurerm': {}})
            self.assertEqual(overlay['terraform']['required_providers'], {'modtm': {'source': 'azure/modtm', 'version': '~> 0.3'}})
            self.assertEqual(overlay['provider'], {'modtm': {'enabled': False}})
            with self.assertRaises(diagnostic.CheckError):
                diagnostic.write_backend(root)
            instance = object.__new__(diagnostic.PlatformTerraform)
            instance.scratch = root
            instance.inputs = root / "inputs.tfvars"
            with patch.object(reconcile.Terraform, "command", return_value=b"ok") as command:
                instance.command("plan", "-input=false", "-detailed-exitcode", "-refresh=true", "-lock=true",
                                 "-lock-timeout=5m", f"-var-file={instance.inputs}",
                                 f"-out={root / diagnostic.SAVED_PLAN}", allowed=(0, 2))
                self.assertEqual(command.call_count, 1)
                for args in (
                    ("apply", str(root / diagnostic.SAVED_PLAN)),
                    ("plan", "-target=module.model_router"),
                    ("plan", "-refresh=false"),
                    ("state", "push", "private"),
                ):
                    with self.subTest(args=args), self.assertRaises(diagnostic.CheckError):
                        instance.command(*args)
                self.assertEqual(command.call_count, 1)

    def test_full_diagnostic_is_redacted_plan_only_and_cleans_scratch(self):
        self.run_fixture()

    def test_input_state_and_plan_failures_stop_without_applying(self):
        for failure in ("state", "inputs", "principal", "secret", "source", "plan", "drift"):
            with self.subTest(failure=failure):
                self.run_fixture(failure)

    def test_protected_workflow_is_manual_main_only_and_has_no_apply(self):
        workflow = (lab.ROOT / ".github" / "workflows" / "check-platform-router-plan.yml").read_text()
        for required in (
            "workflow_dispatch:", "github.ref == 'refs/heads/main'", "terraform-state-access",
            "cancel-in-progress: false", "[self-hosted, linux, lab-runner]", "environment: terraform-state",
            "id-token: write", "persist-credentials: false", "terraform_wrapper: false",
            "secrets.TF_LAB_PLAN_CONFIG", "secrets.TF_PLATFORM_INPUT_BLOB", "if: always()", "--cleanup",
        ):
            self.assertIn(required, workflow)
        for forbidden in ("pull_request:", "upload-artifact", "terraform apply", "-target", "-refresh=false",
                          "-lock=false"):
            self.assertNotIn(forbidden, workflow)


class PlanTests(unittest.TestCase):
    def test_exact_router_create_and_deferred_readback_are_redacted(self):
        result = diagnostic.summarize_plan(plan(), 2, values(), ACCOUNT)
        self.assertEqual(result["router_deployment"], "create")
        self.assertNotIn("router_patch", result)
        self.assertEqual(result["deferred_router_readback"], 1)
        self.assertEqual(result["other_nonpassing_checks"], 0)
        self.assertEqual(result["other_managed_changes"], 0)
        rendered = json.dumps(result)
        for private in (ACCOUNT, PRINCIPAL, "rg-private", "foundry-private"):
            self.assertNotIn(private, rendered)

    def test_existing_router_requires_unchanged_known_outputs(self):
        value = plan()
        value["resource_changes"][0]["change"]["actions"] = ["no-op"]
        value["resource_changes"][1]["change"]["actions"] = ["no-op"]
        value["output_changes"]["model_router_deployment_name"] = {
            "actions": ["no-op"], "before": "model-router", "after": "model-router", "after_unknown": False,
        }
        value["output_changes"]["model_deployment_names"] = {
            "actions": ["no-op"], "before": ["gpt-4.1", "model-router"],
            "after": ["gpt-4.1", "model-router"], "after_unknown": False,
        }
        capabilities = {"gpt-4.1": False, "model-router": False}
        value["output_changes"]["model_preview_encrypted_reasoning"] = {
            "actions": ["no-op"], "before": capabilities, "after": dict(capabilities), "after_unknown": False,
        }
        value["checks"][0]["status"] = "pass"
        value["checks"][0]["instances"][0]["status"] = "pass"
        value["resource_changes"].pop(1)
        value["prior_state"] = {"values": {"root_module": {"child_modules": [{
            "address": "module.model_router",
            "resources": [{
                "address": diagnostic.READBACK, "mode": "data", "type": "azapi_resource",
                "values": {
                    "type": "Microsoft.CognitiveServices/accounts/deployments@2025-12-01",
                    "resource_id": ACCOUNT + "/deployments/model-router",
                    "response_export_values": ["properties.routing"],
                    "output": {"properties": {"routing": {
                        "mode": "balanced", "models": deepcopy(diagnostic.ROUTER_MODELS),
                    }}},
                },
            }],
        }]}}}
        result = diagnostic.summarize_plan(value, 0, values(), ACCOUNT)
        self.assertEqual(result["router_deployment"], "no-op")
        for change in (
            lambda item: item["output_changes"]["model_router_deployment_name"].update(after_unknown=True),
            lambda item: item["output_changes"]["model_deployment_names"].update(after=["gpt-4.1"]),
            lambda item: item["output_changes"].pop("model_router_deployment_name"),
            lambda item: item.pop("prior_state"),
            lambda item: item.pop("checks"),
            lambda item: item.update(checks=[]),
            lambda item: item["checks"][0]["instances"][0].update(status="unknown"),
            lambda item: item["prior_state"]["values"]["root_module"]["child_modules"][0]["resources"].append(
                deepcopy(item["prior_state"]["values"]["root_module"]["child_modules"][0]["resources"][0])),
        ):
            item = deepcopy(value)
            change(item)
            with self.subTest(item=item), self.assertRaises(diagnostic.CheckError):
                diagnostic.summarize_plan(item, 0, values(), ACCOUNT)

    def test_missing_duplicate_or_unchecked_router_readback_is_rejected(self):
        for mutate in (
            lambda value: value["resource_changes"].pop(1),
            lambda value: value["resource_changes"].append(deepcopy(value["resource_changes"][1])),
            lambda value: value.pop("checks"),
            lambda value: value.update(checks=[]),
            lambda value: value["checks"][0].pop("instances"),
            lambda value: value["checks"][0]["instances"][0].update(status="pass"),
        ):
            value = plan()
            mutate(value)
            with self.subTest(mutate=mutate), self.assertRaises(diagnostic.CheckError):
                diagnostic.summarize_plan(value, 2, values(), ACCOUNT)

    def test_partial_router_apply_requires_separate_recovery(self):
        value = plan()
        deployment = value["resource_changes"][0]["change"]
        deployment.update(actions=["no-op"], before=deepcopy(deployment["after"]))
        with self.assertRaisesRegex(diagnostic.CheckError, "verified Router no-op"):
            diagnostic.summarize_plan(value, 2, values(), ACCOUNT)

    def test_legacy_patch_state_and_router_updates_require_separate_recovery(self):
        for actions in (["no-op"], ["create"], ["update"], ["delete"], ["delete", "create"], ["forget"]):
            value = plan()
            value["resource_changes"].append({
                "address": diagnostic.LEGACY_PATCH, "mode": "managed",
                "change": {"actions": actions, "before": {}, "after": {}, "after_unknown": {}},
            })
            with self.subTest(actions=actions), self.assertRaisesRegex(
                    diagnostic.CheckError, "separately reviewed recovery"):
                diagnostic.summarize_plan(value, 2, values(), ACCOUNT)
        value = plan()
        value["resource_drift"] = [{
            "address": diagnostic.LEGACY_PATCH, "mode": "managed",
            "change": {"actions": ["no-op"], "before": {}, "after": {}, "after_unknown": {}},
        }]
        with self.assertRaisesRegex(diagnostic.CheckError, "separately reviewed recovery"):
            diagnostic.summarize_plan(value, 2, values(), ACCOUNT)
        for actions in (["update"], ["delete"], ["delete", "create"], ["create", "delete"], ["forget"]):
            value = plan()
            value["resource_changes"][0]["change"]["actions"] = actions
            with self.subTest(actions=actions), self.assertRaises(diagnostic.CheckError):
                diagnostic.summarize_plan(value, 2, values(), ACCOUNT)

    def test_preview_output_tracks_known_model_versions_and_deployment_aliases(self):
        value = plan()
        value["variables"]["additional_model_deployments"]["value"] = {
            "known-alias": {"format": "OpenAI", "name": "gpt-4.1-mini", "version": "2025-04-14"},
            "unknown-alias": {"format": "OpenAI", "name": "gpt-4.1", "version": "other"},
        }
        names = ["gpt-4.1", "known-alias", "unknown-alias"]
        value["output_changes"]["model_deployment_names"].update(
            before=names, after=names + [None], after_unknown=[False, False, False, True],
        )
        value["output_changes"]["model_preview_encrypted_reasoning"]["after"]["known-alias"] = False
        result = diagnostic.summarize_plan(value, 2, values(), ACCOUNT)
        self.assertEqual(result["preview_capability_output"], "create")
        for change in (
            lambda item: item["output_changes"]["model_preview_encrypted_reasoning"]["after"].update(
                **{"unknown-alias": False}),
            lambda item: item["output_changes"]["model_preview_encrypted_reasoning"]["after"].update(
                **{"known-alias": True}),
            lambda item: item["output_changes"]["model_preview_encrypted_reasoning"]["after"].update(
                **{"known-alias": 0}),
            lambda item: item["output_changes"]["model_preview_encrypted_reasoning"].update(after_unknown=True),
            lambda item: item["output_changes"]["model_preview_encrypted_reasoning"].update(actions=["delete"]),
            lambda item: item["output_changes"].pop("model_preview_encrypted_reasoning"),
            lambda item: item["variables"]["model_deployment"].update(value="invalid"),
            lambda item: item["variables"]["additional_model_deployments"].update(value="invalid"),
            lambda item: item["output_changes"]["model_deployment_names"].update(before=["gpt-4.1"]),
        ):
            item = deepcopy(value)
            change(item)
            with self.subTest(change=change), self.assertRaises(diagnostic.CheckError):
                diagnostic.summarize_plan(item, 2, values(), ACCOUNT)

    def test_unrelated_jumpbox_and_role_changes_are_reported_but_not_approved(self):
        value = plan()
        value["resource_changes"][-1]["change"]["actions"] = ["update"]
        value["resource_changes"].append({
            "address": "azurerm_role_assignment.jumpbox_foundry_project_manager[0]", "mode": "managed",
            "change": {"actions": ["delete", "create"], "before": {}, "after": {}},
        })
        result = diagnostic.summarize_plan(value, 2, values(), ACCOUNT)
        self.assertEqual(result["other_managed_changes"], 2)
        self.assertEqual(result["known_unrelated_changes"], ["jumpbox", "jumpbox_role"])

    def test_router_configuration_mismatches_are_rejected(self):
        for change in (
            lambda item: item["resource_changes"][0]["change"]["after"].update(parent_id=ACCOUNT + "-other"),
            lambda item: item["resource_changes"][0]["change"]["after"]["body"]["properties"]["routing"].update(
                mode="quality"),
            lambda item: item["resource_changes"][0]["change"]["after"].update(
                type="Microsoft.CognitiveServices/accounts/deployments@2025-12-01"),
            lambda item: item["resource_changes"][0]["change"]["after_unknown"].update(parent_id=True),
            lambda item: item["resource_changes"][0]["change"]["after_unknown"].update(body=True),
            lambda item: item["resource_changes"][0]["change"].update(actions=["delete", "create"]),
            lambda item: item["resource_changes"].append(deepcopy(item["resource_changes"][0])),
            lambda item: item["variables"]["deployment_principal_id"].update(value=SUBSCRIPTION),
        ):
            item = plan()
            change(item)
            with self.subTest(item=item), self.assertRaises(diagnostic.CheckError) as raised:
                diagnostic.summarize_plan(item, 2, values(), ACCOUNT)
            self.assertNotIn(ACCOUNT, str(raised.exception))

    def test_unrelated_outputs_reads_imports_drift_and_checks_are_visible(self):
        value = plan()
        value["resource_changes"].append({
            "address": "data.private", "mode": "data", "change": {"actions": ["read"], "before": None, "after": {}},
        })
        value["resource_changes"][0]["change"]["importing"] = {"id": "private-import"}
        value["resource_drift"] = [{
            "address": "azapi_resource.jumpbox[0]", "mode": "managed",
            "change": {"actions": ["update"], "before": {}, "after": {}},
        }]
        value["output_changes"]["private"] = {"actions": ["update"]}
        value["checks"].append({"address": {"to_display": "private"}, "status": "unknown"})
        result = diagnostic.summarize_plan(value, 2, values(), ACCOUNT)
        self.assertEqual(
            (result["other_deferred_reads"], result["imports"], result["refreshed_drift"],
             result["other_output_changes"], result["other_nonpassing_checks"]),
            (1, 1, 1, 1, 1),
        )
        self.assertNotIn("private-import", json.dumps(result))

    def test_incomplete_or_inconsistent_plans_are_rejected(self):
        for change in (
            lambda item: item.update(complete=False),
            lambda item: item.update(errored=True),
            lambda item: item.update(deferred_changes=[{}]),
            lambda item: item.update(action_invocations=[{}]),
            lambda item: item.update(format_version="2.0"),
            lambda item: item["output_changes"]["model_deployment_names"].update(actions=["delete"]),
            lambda item: item["output_changes"]["model_deployment_names"].update(after=["different", None]),
            lambda item: item["output_changes"]["model_router_deployment_name"].update(
                after="unexpected", after_unknown=False),
            lambda item: item["output_changes"].pop("model_router_deployment_name"),
            lambda item: item["checks"].append({"status": "unknown",
                                               "address": item["checks"][0]["address"]}),
        ):
            item = plan()
            change(item)
            with self.subTest(item=item), self.assertRaises(diagnostic.CheckError):
                diagnostic.summarize_plan(item, 2, values(), ACCOUNT)
        with self.assertRaises(diagnostic.CheckError):
            diagnostic.summarize_plan(plan(), 0, values(), ACCOUNT)


if __name__ == "__main__":
    unittest.main()

import contextlib
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

import check_lab_terraform_plan as diagnostic
import reconcile_runner_state as reconcile

SUBSCRIPTION = "11111111-2222-3333-4444-555555555555"
APP = "lab-fixture"
BASE = f"/subscriptions/{SUBSCRIPTION}/resourceGroups/rg-lab/providers/"
APP_ID = BASE + f"Microsoft.App/containerApps/{APP}"
DIGEST = "sha256:" + "a" * 64
REVISION = APP + "--fixture"


def protected_config():
    return {
        "AZURE_CLIENT_ID": SUBSCRIPTION, "AZURE_TENANT_ID": SUBSCRIPTION,
        "AZURE_SUBSCRIPTION_ID": SUBSCRIPTION, "TF_STATE_ACCOUNT": "stfixture",
        "TF_STATE_CONTAINER": "tfstate", "TF_STATE_PREFIX": "ai-foundry/",
        "TF_STATE_PRIVATE_ENDPOINT": "10.42.0.23",
    }


def environment(folder=None):
    return {
        "GITHUB_REF": "refs/heads/main", "GITHUB_SHA": "a" * 40,
        "GITHUB_RUN_ID": "12345", "GITHUB_RUN_ATTEMPT": "1",
        "ACTIONS_ID_TOKEN_REQUEST_URL": "https://fixture.actions.githubusercontent.com/token",
        "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "fixture-token",
        "TF_LAB_PLAN_CONFIG": json.dumps(protected_config()),
        **({"RUNNER_TEMP": str(folder)} if folder else {}),
    }


def values(platform=None):
    return {
        "subscription_id": SUBSCRIPTION, "name": APP, "bootstrap_only": False,
        "enable_front_door": True, "image_digest": DIGEST, "platform_state": platform,
    }


def platform():
    return {
        "subscription_id": None, "resource_group_name": "rg-state", "storage_account_name": "stfixture",
        "container_name": "tfstate", "key": "ai-foundry/dev.tfstate",
    }


def state_object():
    def item(resource_type, name, entries, module=None):
        return {
            "mode": "managed", "type": resource_type, "name": name,
            **({"module": module} if module else {}), "instances": entries,
        }

    def instance(index, resource_id, **attributes):
        return {
            **({"index_key": index} if index is not None else {}),
            "attributes": {"id": resource_id, **attributes},
        }

    alert_prefix = BASE + "Microsoft.Insights/scheduledQueryRules/" + APP
    return {
        "version": 4, "serial": 12, "lineage": "fixture-lineage",
        "resources": [
            item("azurerm_container_app", "this", [instance(0, APP_ID, name=APP)]),
            item("azurerm_cdn_frontdoor_firewall_policy", "wafs", [
                instance("lab", BASE + "Microsoft.Network/frontdoorWebApplicationFirewallPolicies/waflabfixture"),
            ], "module.front_door[0]"),
            item("azurerm_monitor_scheduled_query_rules_alert_v2", "operational", [
                instance("request-failures", alert_prefix + "-request-failures"),
                instance("dependencies", alert_prefix + "-dependencies"),
            ]),
            item("azurerm_monitor_scheduled_query_rules_alert_v2", "heartbeat", [
                instance(None, alert_prefix + "-missing-heartbeat"),
            ]),
        ],
    }


def state():
    return json.dumps(state_object()).encode()


def plan(input_values=None):
    supplied = input_values or values()
    return {
        "format_version": "1.0", "errored": False, "complete": True,
        "variables": {key: {"value": value} for key, value in supplied.items()},
        "resource_changes": [
            {"address": address, "mode": "managed", "change": {
                "actions": ["no-op"], "before": {"enabled": True}, "after": {"enabled": True},
                "after_unknown": {},
            }} for address in diagnostic.TARGETS
        ],
    }


def archive(entries):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w") as tar:
        for name, content in entries:
            entry = tarfile.TarInfo(name)
            if content is None:
                entry.type = tarfile.SYMTYPE
                entry.linkname = "elsewhere"
                tar.addfile(entry)
            else:
                entry.size = len(content)
                tar.addfile(entry, io.BytesIO(content))
    return output.getvalue()


class LabConfigurationTests(unittest.TestCase):
    def test_protected_configuration_rejects_ambient_credentials_and_proxies(self):
        env = environment()
        env.update({
            "AZURE_CLIENT_SECRET": "not-approved", "ARM_ACCESS_KEY": "not-approved",
            "TF_CLI_ARGS_plan": "-refresh=false", "TF_STATE_ACCOUNT": "wrong",
            "MODTM_ENDPOINT": "https://unapproved.invalid",
        })
        with patch.object(diagnostic, "validate_backend") as validate:
            result = diagnostic.configuration(env)
        validate.assert_called_once_with(result)
        self.assertEqual(result["TF_STATE_ACCOUNT"], "stfixture")
        for key in ("AZURE_CLIENT_SECRET", "ARM_ACCESS_KEY", "TF_CLI_ARGS_plan", "TF_LAB_PLAN_CONFIG", "MODTM_ENDPOINT"):
            self.assertNotIn(key, result)
        for key in ("HTTP_PROXY", "https_proxy", "ALL_PROXY"):
            with self.subTest(key=key), self.assertRaises(diagnostic.CheckError):
                diagnostic.configuration({**env, key: "https://proxy.invalid"})

    def test_incomplete_or_unreviewed_configuration_and_revision_fail(self):
        for config in ({}, {**protected_config(), "unexpected": "secret"},
                       {**protected_config(), "AZURE_SUBSCRIPTION_ID": "not-a-guid"}):
            with self.subTest(config=config), self.assertRaises(diagnostic.CheckError):
                diagnostic.configuration({**environment(), "TF_LAB_PLAN_CONFIG": json.dumps(config)})
        with patch.object(diagnostic, "validate_backend"):
            for sha in ("", "a" * 39, "g" * 40):
                with self.subTest(sha=sha), self.assertRaises(diagnostic.CheckError):
                    diagnostic.configuration({**environment(), "GITHUB_SHA": sha})

    def test_only_the_approved_private_dns_endpoint_is_accepted(self):
        private = [(2, 1, 6, "", ("10.42.0.23", 443))]
        with patch("check_state_backend.socket.getaddrinfo", return_value=private):
            self.assertEqual(diagnostic.configuration(environment())["TF_STATE_PREFIX"], "ai-foundry/")
            for alteration in (
                {"GITHUB_REF": "refs/heads/feature"},
                {"ACTIONS_ID_TOKEN_REQUEST_TOKEN": ""},
                {"TF_LAB_PLAN_CONFIG": json.dumps({**protected_config(), "TF_STATE_PREFIX": "other/"})},
                {"TF_LAB_PLAN_CONFIG": json.dumps({**protected_config(), "TF_STATE_PRIVATE_ENDPOINT": "8.8.8.8"})},
            ):
                with self.subTest(alteration=alteration), self.assertRaises(diagnostic.CheckError):
                    diagnostic.configuration({**environment(), **alteration})
        mixed = private + [(2, 1, 6, "", ("203.0.113.1", 443))]
        with patch("check_state_backend.socket.getaddrinfo", return_value=mixed):
            with self.assertRaises(diagnostic.CheckError):
                diagnostic.configuration(environment())

    def test_snapshots_use_get_and_require_version_metadata(self):
        blobs = object.__new__(diagnostic.LabBlobs)
        blobs.base, blobs.headers = "https://stfixture.blob.core.windows.net/tfstate/ai-foundry/", {}
        headers = {"ETag": '"etag"', "x-ms-lease-status": "unlocked", "x-ms-meta-purpose": "fixture"}
        with patch.object(diagnostic, "send", return_value=(b"private", headers)) as request:
            self.assertEqual(blobs.snapshot(diagnostic.LAB_STATE), (
                b"private", '"etag"', {"x-ms-meta-purpose": "fixture"},
            ))
            self.assertNotIn("method", request.call_args.kwargs)
        with patch.object(diagnostic, "send", return_value=(b"private", {})), self.assertRaises(diagnostic.CheckError):
            blobs.snapshot(diagnostic.LAB_STATE)
        for locked in (
            {**headers, "x-ms-lease-status": "locked"},
            {**headers, "x-ms-meta-terraformlockid": "stale-private-lock"},
        ):
            with patch.object(diagnostic, "send", return_value=(b"private", locked)):
                with self.assertRaises(diagnostic.CheckError):
                    blobs.snapshot(diagnostic.LAB_STATE)
        with self.assertRaises(diagnostic.CheckError):
            blobs.snapshot("unreviewed.tfstate")
        self.assertFalse(hasattr(blobs, "inputs"))

    def test_lab_etag_can_change_for_lock_metadata_but_content_and_metadata_must_match(self):
        baseline = (b"state", '"etag-1"', {"x-ms-meta-purpose": "fixture"})
        self.assertTrue(diagnostic.snapshot_unchanged(
            diagnostic.LAB_STATE, baseline, (b"state", '"etag-2"', {"x-ms-meta-purpose": "fixture"}),
        ))
        self.assertFalse(diagnostic.snapshot_unchanged(
            diagnostic.LAB_STATE, baseline, (b"state", '"etag-2"', {"x-ms-meta-purpose": "different"}),
        ))
        self.assertFalse(diagnostic.snapshot_unchanged(
            diagnostic.LAB_INPUTS, baseline, (b"state", '"etag-2"', {"x-ms-meta-purpose": "fixture"}),
        ))

    def test_platform_state_must_match_the_private_backend(self):
        env, app = protected_config(), {"app_name": APP}
        self.assertIsNone(diagnostic.validate_inputs(values(), app, DIGEST, env))
        self.assertEqual(diagnostic.validate_inputs(values(platform()), app, DIGEST, env), diagnostic.PLATFORM_STATE)
        for key, replacement in (
            ("subscription_id", "other"), ("storage_account_name", "another"),
            ("container_name", "other"), ("key", "ai-foundry/other.tfstate"),
        ):
            changed = platform()
            changed[key] = replacement
            with self.subTest(key=key), self.assertRaises(diagnostic.CheckError):
                diagnostic.validate_inputs(values(changed), app, DIGEST, env)
        for key, replacement in (
            ("subscription_id", "other"), ("name", "other"), ("bootstrap_only", True),
            ("enable_front_door", False), ("image_digest", "sha256:" + "b" * 64),
        ):
            changed = values()
            changed[key] = replacement
            with self.subTest(key=key), self.assertRaises(diagnostic.CheckError):
                diagnostic.validate_inputs(changed, app, DIGEST, env)
        incomplete = values()
        del incomplete["platform_state"]
        with self.assertRaises(diagnostic.CheckError):
            diagnostic.validate_inputs(incomplete, app, DIGEST, env)


class LabStateAndImageTests(unittest.TestCase):
    def test_existing_state_is_bound_to_the_app_waf_and_all_three_alerts(self):
        self.assertEqual(diagnostic.lab_state(state(), SUBSCRIPTION), {"app_id": APP_ID, "app_name": APP})
        fixtures = []
        missing = state_object()
        missing["resources"].pop()
        fixtures.append(missing)
        wrong_waf = state_object()
        wrong_waf["resources"][1]["instances"][0]["attributes"]["id"] += "other"
        fixtures.append(wrong_waf)
        wrong_alert = state_object()
        wrong_alert["resources"][2]["instances"][0]["attributes"]["id"] += "other"
        fixtures.append(wrong_alert)
        deposed = state_object()
        deposed["resources"][0]["instances"][0]["deposed"] = "previous"
        fixtures.append(deposed)
        for candidate in fixtures:
            with self.subTest(candidate=candidate), self.assertRaises(diagnostic.CheckError):
                diagnostic.lab_state(json.dumps(candidate).encode(), SUBSCRIPTION)
        with self.assertRaises(diagnostic.CheckError):
            diagnostic.lab_state(state(), "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
        with self.assertRaises(diagnostic.CheckError):
            diagnostic.lab_state(b"not-json-private", SUBSCRIPTION)

    def test_active_revision_supplies_the_real_immutable_digest(self):
        app = {"app_id": APP_ID, "app_name": APP}
        app_result = {
            "id": APP_ID,
            "properties": {"configuration": {"activeRevisionsMode": "Single"}, "latestReadyRevisionName": REVISION},
        }
        revision_result = {
            "id": APP_ID + "/revisions/" + REVISION,
            "properties": {"active": True, "template": {"containers": [{
                "name": "workbench", "image": "private-registry.example/workbench@" + DIGEST,
            }]}},
        }
        with (patch.object(diagnostic, "azure_token", return_value="token") as token,
              patch.object(diagnostic, "json_response", side_effect=[app_result, revision_result]) as request):
            self.assertEqual(diagnostic.current_image(protected_config(), app), (REVISION, DIGEST))
        self.assertEqual(token.call_args.kwargs["scope"], "https://management.azure.com/.default")
        self.assertEqual(request.call_count, 2)
        for change in (
            lambda value: value["properties"].update(active=False),
            lambda value: value["properties"]["template"]["containers"][0].update(image="private:latest"),
            lambda value: value.update(id=APP_ID + "/revisions/other"),
            lambda value: value["properties"]["template"]["containers"].append(
                {"name": "workbench", "image": "private@" + DIGEST}),
        ):
            revised = deepcopy(revision_result)
            change(revised)
            with (patch.object(diagnostic, "azure_token", return_value="token"),
                  patch.object(diagnostic, "json_response", side_effect=[app_result, revised]),
                  self.assertRaises(diagnostic.CheckError)):
                diagnostic.current_image(protected_config(), app)
        invalid_app = deepcopy(app_result)
        invalid_app["properties"]["configuration"]["activeRevisionsMode"] = "Multiple"
        with (patch.object(diagnostic, "azure_token", return_value="token"),
              patch.object(diagnostic, "json_response", return_value=invalid_app),
              self.assertRaises(diagnostic.CheckError)):
            diagnostic.current_image(protected_config(), app)


class LabSourceAndTerraformTests(unittest.TestCase):
    def test_only_checked_in_source_is_staged_and_auto_inputs_are_rejected(self):
        files = [("workbench/infra/main.tf", b"terraform {}"), ("workbench/agents.json", b"[]")]
        completed = subprocess.CompletedProcess([], 0, stdout=archive(files), stderr=b"")
        with tempfile.TemporaryDirectory() as folder:
            with (patch.object(diagnostic.shutil, "which", return_value="git"),
                  patch.object(diagnostic.subprocess, "run", return_value=completed) as process):
                root = diagnostic.stage_sources(Path(folder), environment())
            self.assertEqual((root / "main.tf").read_bytes(), b"terraform {}")
            self.assertFalse((root / "image.auto.tfvars").exists())
            args = process.call_args.args[0]
            self.assertEqual(args[2:5], [str(diagnostic.ROOT), "archive", "--format=tar"])
            self.assertEqual(args[-2:], ["workbench/infra", "workbench/agents.json"])
            self.assertNotIn("ACTIONS_ID_TOKEN_REQUEST_TOKEN", process.call_args.kwargs["env"])
        for extra in (
            ("workbench/infra/image.auto.tfvars", b"private"),
            ("workbench/infra/terraform.tfvars.json", b"{}"),
            ("workbench/infra/../../escape", b"bad"),
            ("workbench/infra/..\\..\\escape", b"bad"),
            ("workbench/infra/C:/escape", b"bad"),
            ("workbench/infra/link", None),
        ):
            completed = subprocess.CompletedProcess([], 0, stdout=archive(files + [extra]), stderr=b"")
            with tempfile.TemporaryDirectory() as folder:
                with (patch.object(diagnostic.shutil, "which", return_value="git"),
                      patch.object(diagnostic.subprocess, "run", return_value=completed),
                      self.assertRaises(diagnostic.CheckError)):
                    diagnostic.stage_sources(Path(folder), environment())

    @unittest.skipUnless(shutil.which("git"), "Git is not installed")
    def test_real_git_archive_stages_the_existing_committed_lab_source(self):
        executable = shutil.which("git")
        revision = subprocess.run(
            [executable, "-C", str(diagnostic.ROOT), "rev-parse", "HEAD"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
        ).stdout.decode().strip()
        with tempfile.TemporaryDirectory() as folder:
            env = {**os.environ, **environment(), "GITHUB_SHA": revision}
            root = diagnostic.stage_sources(Path(folder), env)
            self.assertTrue((root / "main.tf").is_file())
            self.assertTrue((root.parent / "agents.json").is_file())
            self.assertFalse((root / "image.auto.tfvars").exists())

    def test_supplemental_files_use_the_live_digest_and_disable_provider_telemetry(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            diagnostic.write_supplemental_files(root, DIGEST)
            self.assertEqual(json.loads((root / "diagnostic.auto.tfvars.json").read_text()), {"image_digest": DIGEST})
            self.assertEqual(
                (root / "diagnostic-privacy.tf").read_text(),
                'provider "modtm" {\n  enabled = false\n}\n',
            )
            with self.assertRaises(diagnostic.CheckError):
                diagnostic.write_supplemental_files(root, DIGEST)

    def test_platform_state_cli_auth_is_replaced_with_oidc_in_private_stage_only(self):
        source = (
            'data "terraform_remote_state" "platform" {\n'
            '  config = {\n'
            '    use_azuread_auth     = true\n'
            '    use_cli              = true\n'
            '  }\n'
            '}\n'
        )
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "workbench" / "infra"
            root.mkdir(parents=True)
            staged = root / "platform.tf"
            staged.write_text(source)
            diagnostic.configure_platform_oidc(root)
            updated = staged.read_text()
            self.assertIn("use_oidc             = true", updated)
            self.assertIn("use_cli              = false", updated)
            self.assertEqual(source.count("use_cli              = true"), 1)
            self.assertNotIn("use_cli              = true", updated)
            with self.assertRaises(diagnostic.CheckError):
                diagnostic.configure_platform_oidc(root)

    def test_initialization_uses_hcl_and_blocks_cli_credential_fallback(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            env = {
                **environment(folder), **protected_config(), "TF_CLI_ARGS_plan": "-refresh=false",
                "PATH": r"C:\Windows\System32;C:\Program Files\Git\cmd",
            }
            with (patch.object(reconcile.shutil, "which", return_value="terraform"),
                  patch.object(diagnostic.LabTerraform, "command", return_value=b"") as command):
                terraform = diagnostic.LabTerraform(root, root, env, b'name = "lab-fixture"\n')
            self.assertEqual(terraform.inputs.name, "inputs.tfvars")
            self.assertEqual(terraform.inputs.read_bytes(), b'name = "lab-fixture"\n')
            self.assertEqual(terraform.env["PATH"], env["PATH"])
            self.assertEqual(terraform.env["ARM_USE_CLI"], "false")
            self.assertEqual(terraform.env["ARM_USE_OIDC"], "true")
            self.assertNotIn("TF_CLI_ARGS_plan", terraform.env)
            self.assertNotIn("TF_LAB_PLAN_CONFIG", terraform.env)
            self.assertEqual(command.call_args.args[:2], ("init", "-reconfigure"))

    def test_only_fixed_full_root_commands_are_accepted(self):
        terraform = object.__new__(diagnostic.LabTerraform)
        terraform.scratch = Path("scratch")
        terraform.inputs = terraform.scratch / "inputs.tfvars"
        saved = terraform.scratch / "lab.tfplan"
        var_file = f"-var-file={terraform.inputs}"
        good = ("plan", "-input=false", "-detailed-exitcode", "-refresh=true", "-lock=true",
                "-lock-timeout=5m", var_file, f"-out={saved}")
        with patch.object(reconcile.Terraform, "command", return_value=b"safe") as command:
            self.assertEqual(terraform.command(*good, allowed=(0, 2)), b"safe")
            command.assert_called_once()
            for bad in (
                ("apply", str(saved)), good + ("-target=resource.secret",),
                tuple("-refresh=false" if item == "-refresh=true" else item for item in good),
                tuple("-lock=false" if item == "-lock=true" else item for item in good),
                ("console", var_file, "-var=bootstrap_only=true"),
                ("show", "-json", "other.tfplan"),
            ):
                with self.subTest(bad=bad), self.assertRaises(diagnostic.CheckError):
                    terraform.command(*bad, allowed=(0, 2))
            with self.assertRaises(diagnostic.CheckError):
                terraform.command("console", var_file, input_data=b"unreviewed\n")

    def test_console_output_is_json_decoded_without_logging(self):
        terraform = object.__new__(diagnostic.LabTerraform)
        terraform.inputs = Path("inputs.tfvars")
        raw = json.dumps(json.dumps(values())).encode()
        with patch.object(terraform, "command", return_value=raw):
            self.assertEqual(terraform.inputs_resolved(), values())
        with patch.object(terraform, "command", return_value=b"not-private-json"), self.assertRaises(diagnostic.CheckError):
            terraform.inputs_resolved()

    @unittest.skipUnless(shutil.which("terraform"), "Terraform is not installed")
    def test_hcl_canonical_inputs_override_the_supplemental_digest(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "main.tf").write_text('variable "image_digest" { type = string }\n')
            (root / "diagnostic.auto.tfvars.json").write_text(json.dumps({"image_digest": DIGEST}))
            override = "sha256:" + "b" * 64
            (root / "inputs.tfvars").write_text(f'image_digest = "{override}"\n')
            env = {
                key: value for key, value in os.environ.items()
                if not key.startswith(("TF_", "ARM_", "AZURE_"))
            }
            env.update({"TF_IN_AUTOMATION": "true", "TF_INPUT": "0", "CHECKPOINT_DISABLE": "1"})
            result = subprocess.run(
                [shutil.which("terraform"), f"-chdir={root}", "console", "-no-color",
                 f"-var-file={root / 'inputs.tfvars'}"],
                input=b"jsonencode(var.image_digest)\n", env=env, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, check=False,
            )
            self.assertEqual(result.returncode, 0)
            self.assertEqual(json.loads(json.loads(result.stdout)), override)

    @unittest.skipUnless(shutil.which("terraform"), "Terraform is not installed")
    def test_real_offline_full_plan_json_matches_the_report_contract(self):
        executable = shutil.which("terraform")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "main.tf").write_text(
                'variable "subscription_id" { type = string }\n'
                'variable "name" { type = string }\n'
                'variable "bootstrap_only" { type = bool }\n'
                'variable "enable_front_door" { type = bool }\n'
                'variable "image_digest" { type = string }\n'
                'resource "terraform_data" "waf" { input = var.name }\n'
                'resource "terraform_data" "request_failures" { input = var.name }\n'
                'resource "terraform_data" "dependencies" { input = var.name }\n'
                'resource "terraform_data" "heartbeat" { input = var.name }\n'
            )
            (root / "inputs.tfvars.json").write_text(json.dumps({
                key: value for key, value in values().items() if key != "platform_state"
            }))
            env = {
                key: value for key, value in os.environ.items()
                if not key.startswith(("TF_", "ARM_", "AZURE_"))
            }
            env.update({"TF_IN_AUTOMATION": "true", "TF_INPUT": "0", "CHECKPOINT_DISABLE": "1"})

            def terraform(*args):
                return subprocess.run(
                    [executable, f"-chdir={root}", *args], env=env, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, check=False,
                )

            self.assertEqual(terraform("init", "-backend=false", "-no-color").returncode, 0)
            saved = root / "lab.tfplan"
            result = terraform(
                "plan", "-no-color", "-input=false", "-detailed-exitcode", "-refresh=true", "-lock=true",
                "-lock-timeout=5m", f"-var-file={root / 'inputs.tfvars.json'}", f"-out={saved}",
            )
            self.assertEqual(result.returncode, 2)
            rendered = terraform("show", "-no-color", "-json", str(saved))
            self.assertEqual(rendered.returncode, 0)
            actual = json.loads(rendered.stdout)
            targets = {label: address for address, label in diagnostic.TARGETS.items()}
            for entry in actual["resource_changes"]:
                entry["address"] = targets[entry["name"]]
            summary = diagnostic.summarize_plan(actual, result.returncode, values())
            self.assertEqual(summary["plan_exit"], "changes")
            self.assertTrue(all(target["planned"]["action"] == "create" for target in summary["targets"].values()))


class LabPlanReportTests(unittest.TestCase):
    def test_redacts_values_dynamic_keys_and_distinguishes_refreshed_drift(self):
        value = plan()
        waf = value["resource_changes"][0]
        waf["change"] = {
            "actions": ["update"],
            "before": {"custom_rule": [{"match_condition": [{"match_values": ["203.0.113.10/32"]}]}],
                       "TOP_SECRET_DYNAMIC_KEY": "old-secret"},
            "after": {"custom_rule": [{"match_condition": [{"match_values": ["203.0.113.11/32"]}]}],
                      "TOP_SECRET_DYNAMIC_KEY": "new-secret"},
            "after_unknown": {"custom_rule": [{"match_condition": [{"selector": True}]}]},
        }
        value["resource_drift"] = [{
            "address": waf["address"], "mode": "managed", "change": {
                "actions": ["update"],
                "before": {"mode": "private-old-mode"},
                "after": {"mode": "private-new-mode"},
            },
        }]
        value["resource_changes"].append({
            "address": "private-resource-address", "mode": "managed", "change": {
                "actions": ["delete", "create"], "before": {"private-key": "private-old"},
                "after": {"private-key": "private-new"},
            },
        })
        value["output_changes"] = {"private-output-name": {
            "actions": ["update"], "before": "private-output-old", "after": "private-output-new",
            "after_unknown": True,
        }}
        summary = diagnostic.summarize_plan(value, 2, values())
        planned = summary["targets"]["waf"]["planned"]
        self.assertEqual(planned["action"], "update")
        self.assertIn("custom_rule.match_condition.match_values", planned["fields"])
        self.assertIn("custom_rule.match_condition.selector", planned["unknown_fields"])
        self.assertIn("other", planned["fields"])
        self.assertEqual(summary["targets"]["waf"]["refreshed_drift"][0]["fields"], ["mode"])
        self.assertEqual(summary["other_managed_changes"], 1)
        self.assertEqual(summary["other_managed_actions"]["replace-delete-create"], 1)
        self.assertEqual(summary["output_changes"], 1)
        self.assertEqual(summary["output_actions"]["update"], 1)
        self.assertEqual(summary["resources_with_unknown_values"], 1)
        self.assertEqual(summary["outputs_with_unknown_values"], 1)
        rendered = json.dumps(summary)
        for secret in (
            "203.0.113.10", "203.0.113.11", "TOP_SECRET_DYNAMIC_KEY", "old-secret", "new-secret",
            "private-old-mode", "private-new-mode", "private-resource-address", "private-output",
        ):
            self.assertNotIn(secret, rendered)

    def test_other_field_paths_and_unknowns_are_fixed_whitelisted_names(self):
        before = {"criteria": [{"query": "secret-old", "dimension": [{"name": "private-name"}]}]}
        after = {"criteria": [{"query": "secret-new", "dimension": [{"name": "private-new-name"}]}]}
        unknown = {"criteria": [{"threshold": True, "sensitive-custom-key": True}]}
        fields, pending = diagnostic.changed_fields(before, after, unknown, diagnostic.ALERT_FIELDS)
        self.assertEqual(fields, ["criteria.dimension.name", "criteria.other", "criteria.query", "criteria.threshold"])
        self.assertEqual(pending, ["criteria.other", "criteria.threshold"])

    def test_malformed_incomplete_unknown_actions_and_missing_targets_fail(self):
        alterations = (
            {"complete": False}, {"errored": True}, {"deferred_changes": [{}]},
            {"action_invocations": [{}]}, {"format_version": "2.0"},
            {"resource_changes": []}, {"checks": [{"status": "sensitive-value"}]},
            {"resource_changes": [{"address": {"unexpected": True}}]},
        )
        for alteration in alterations:
            with self.subTest(alteration=alteration), self.assertRaises(diagnostic.CheckError):
                diagnostic.summarize_plan({**plan(), **alteration}, 0, values())
        bad = plan()
        bad["resource_changes"][0]["change"]["actions"] = [{"not": "an action"}]
        with self.assertRaises(diagnostic.CheckError):
            diagnostic.summarize_plan(bad, 0, values())
        bad = plan()
        bad["variables"]["image_digest"]["value"] = "sha256:" + "c" * 64
        with self.assertRaises(diagnostic.CheckError):
            diagnostic.summarize_plan(bad, 0, values())

    def test_nonpassing_checks_and_imports_are_never_reported_as_clean(self):
        value = plan()
        value["checks"] = [{"status": "pass"}, {"status": "unknown"}, {"status": "fail"}]
        value["resource_changes"][0]["change"]["importing"] = {"id": "secret-id"}
        summary = diagnostic.summarize_plan(value, 2, values())
        self.assertEqual(summary["nonpassing_checks"], 2)
        self.assertEqual(summary["imports"], 1)
        self.assertNotIn("secret-id", json.dumps(summary))
        with self.assertRaises(diagnostic.CheckError):
            diagnostic.summarize_plan(value, 0, values())


class LabRunTests(unittest.TestCase):
    def run_fixture(self, failure=None, platform_enabled=True):
        seen, current = [], {}
        input_values = values(platform() if platform_enabled else None)

        class FakeBlobs:
            def __init__(self, _environment):
                pass

            def snapshot(self, name):
                seen.append(name)
                current[name] = current.get(name, 0) + 1
                body = state() if name == diagnostic.LAB_STATE else b"private-input"
                tag, metadata = "v1", {}
                if current[name] > 1 and failure == "metadata" and name == diagnostic.LAB_STATE:
                    metadata = {"x-ms-meta-purpose": "concurrent-change"}
                if current[name] > 1 and failure == "input" and name == diagnostic.LAB_INPUTS:
                    body = b"different-input"
                if current[name] > 1 and failure == "platform" and name == diagnostic.PLATFORM_STATE:
                    tag = "v2"
                return body, tag, metadata

        class FakeTerraform:
            def __init__(self, root, scratch, _environment, inputs):
                self.scratch = scratch
                self.auto = json.loads((root / "diagnostic.auto.tfvars.json").read_text())
                if inputs != b"private-input" or self.auto != {"image_digest": DIGEST}:
                    raise AssertionError("Only canonical inputs and the verified active digest may be used.")
                if 'enabled = false' not in (root / "diagnostic-privacy.tf").read_text():
                    raise AssertionError("Provider telemetry must be disabled for the diagnostic.")
                if "use_oidc             = true" not in (root / "platform.tf").read_text():
                    raise AssertionError("Platform state must use OIDC and not CLI auth.")
                (scratch / "private-plan").write_text("private")

            def inputs_resolved(self):
                return input_values

            def full_plan(self):
                if failure == "plan":
                    raise diagnostic.CheckError("Provider diagnostics withheld.")
                report = plan(input_values)
                if failure == "checks":
                    report["checks"] = [{"status": "unknown"}]
                return report, 0

        def fake_stage(scratch, _environment):
            root = scratch / "staged"
            root.mkdir()
            (root / "platform.tf").write_text(
                '    use_azuread_auth     = true\n    use_cli              = true\n',
            )
            return root

        revisions = [(REVISION, DIGEST), (REVISION + "-new", DIGEST) if failure == "revision" else (REVISION, DIGEST)]
        with tempfile.TemporaryDirectory() as folder:
            with (patch.object(diagnostic, "validate_backend"),
                  patch.object(diagnostic, "LabBlobs", FakeBlobs),
                  patch.object(diagnostic, "LabTerraform", FakeTerraform),
                  patch.object(diagnostic, "stage_sources", side_effect=fake_stage),
                  patch.object(diagnostic, "current_image", side_effect=revisions),
                  contextlib.redirect_stdout(io.StringIO()) as output):
                if failure:
                    with self.assertRaises(diagnostic.CheckError):
                        diagnostic.run(environment(folder))
                else:
                    diagnostic.run(environment(folder))
            self.assertEqual(list(Path(folder).iterdir()), [])
        self.assertGreaterEqual(seen.count(diagnostic.LAB_STATE), 2)
        if failure not in ("metadata",):
            self.assertGreaterEqual(seen.count(diagnostic.LAB_INPUTS), 2)
        if platform_enabled and failure not in ("metadata", "input"):
            self.assertEqual(seen.count(diagnostic.PLATFORM_STATE), 2)
        if failure not in (None, "checks"):
            self.assertEqual(output.getvalue(), "")
        elif not failure:
            self.assertIn('"plan_exit": "no-changes"', output.getvalue())

    def test_full_diagnostic_is_read_only_and_cleans_scratch(self):
        self.run_fixture()
        self.run_fixture(platform_enabled=False)

    def test_concurrent_blob_or_revision_changes_and_plan_failures_invalidate_result(self):
        for failure in ("metadata", "input", "platform", "revision", "plan", "checks"):
            with self.subTest(failure=failure):
                self.run_fixture(failure)

    def test_protected_workflow_contract_and_image_ignore_invariant(self):
        workflow = (diagnostic.ROOT / ".github" / "workflows" / "check-lab-terraform-plan.yml").read_text()
        for required in (
            "workflow_dispatch:", "github.ref == 'refs/heads/main'", "terraform-state-access",
            "cancel-in-progress: false", "[self-hosted, linux, lab-runner]", "environment: terraform-state",
            "id-token: write", "persist-credentials: false", "terraform_wrapper: false",
            "secrets.TF_LAB_PLAN_CONFIG", "if: always()", "--cleanup",
        ):
            self.assertIn(required, workflow)
        for forbidden in ("upload-artifact", "terraform apply", "-target", "-refresh=false", "-lock=false"):
            self.assertNotIn(forbidden, workflow)
        source = (diagnostic.ROOT / "workbench" / "infra" / "main.tf").read_text()
        self.assertIn("ignore_changes = [template[0].container[0].image]", source)


if __name__ == "__main__":
    unittest.main()

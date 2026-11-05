import contextlib
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import check_lab_terraform_plan as diagnostic
import reconcile_lab_waf_allowlist as waf
from test_check_lab_terraform_plan import DIGEST, REVISION, SUBSCRIPTION, environment, protected_config

APP_ID = (
    f"/subscriptions/{SUBSCRIPTION}/resourceGroups/rg-lab/providers/"
    "Microsoft.App/containerApps/foundry-workbench"
)
APP = {"app_id": APP_ID, "app_name": "foundry-workbench"}
WAF_ID = (
    f"/subscriptions/{SUBSCRIPTION}/resourceGroups/rg-lab/providers/"
    "Microsoft.Network/frontdoorWebApplicationFirewallPolicies/waffoundryworkbench"
)
CONFIGURED = ["203.0.113.10/32"]
LIVE = ["203.0.113.10/32", "198.51.100.7/32", "2001:db8::7/128"]
ADDED = LIVE[1:]
INPUT = b'front_door_allowed_cidrs = [\n  "203.0.113.10/32",\n]\nprivate_value = "keep-private"\n'
FIXTURE_ADDRESSES = ("203.0.113", "198.51.100", "2001:db8", "keep-private")


def waf_response(values=None, **rule):
    return {
        "id": WAF_ID,
        "properties": {"customRules": {"rules": [{
            "name": "BlockUnlistedClients", "priority": 1, "ruleType": "MatchRule", "action": "Block",
            "enabledState": "Enabled",
            "matchConditions": [{
                "matchVariable": "SocketAddr", "operator": "IPMatch", "negateCondition": True,
                "matchValue": LIVE if values is None else values, "transforms": [],
            }],
            **rule,
        }]}},
    }


def resolved_inputs(allowed):
    return {
        "subscription_id": SUBSCRIPTION, "name": "foundry-workbench", "bootstrap_only": False,
        "enable_front_door": True, "image_digest": DIGEST, "platform_state": None, "allowed": allowed,
    }


class AddressTests(unittest.TestCase):
    def test_only_the_existing_lab_waf_is_selected(self):
        self.assertEqual(waf.expected_waf_id(APP), WAF_ID)
        for changed in ({"app_name": "other-app"}, {"app_id": APP_ID.replace("foundry-workbench", "other-app")}):
            with self.subTest(changed=list(changed)), self.assertRaises(diagnostic.CheckError):
                waf.expected_waf_id({**APP, **changed})

    def test_entries_must_be_single_hosts_with_a_matching_prefix(self):
        self.assertEqual(waf.host_entry("203.0.113.10/32"), "203.0.113.10")
        self.assertEqual(waf.host_entry("2001:DB8::7/128"), "2001:db8::7")
        for value in (
            "203.0.113.0/24", "203.0.113.10", "2001:db8::7/32", "203.0.113.10/128", "999.1.1.1/32",
            '203.0.113.10/32"', "203.0.113.10/32\n", "${var.x}/32", "", None, 5,
        ):
            with self.subTest(value=value), self.assertRaises(diagnostic.CheckError):
                waf.host_entry(value)

    def test_live_rule_is_read_only_and_must_have_the_expected_shape(self):
        with (patch.object(waf, "azure_token", return_value="private-token") as token,
              patch.object(waf, "json_response", return_value=waf_response()) as response):
            self.assertEqual(waf.live_allowlist(protected_config(), WAF_ID), LIVE)
        self.assertEqual(token.call_args.kwargs["scope"], "https://management.azure.com/.default")
        self.assertTrue(response.call_args.args[0].startswith("https://management.azure.com/subscriptions/"))
        self.assertIn("api-version=", response.call_args.args[0])
        self.assertEqual(response.call_args.kwargs["headers"], {"Authorization": "Bearer private-token"})
        for label, value in (
            ("other policy", {**waf_response(), "id": WAF_ID + "-other"}),
            ("no rules", {"id": WAF_ID, "properties": {"customRules": {"rules": []}}}),
            ("other rule", waf_response(name="OtherRule")),
            ("allow rule", waf_response(action="Allow")),
            ("disabled", waf_response(enabledState="Disabled")),
            ("empty list", waf_response(values=[])),
            ("range", waf_response(values=["203.0.113.0/24"])),
            ("duplicate", waf_response(values=["2001:db8::7/128", "2001:DB8::7/128"])),
            ("too many", waf_response(values=[f"203.0.113.{number}/32" for number in range(1, 12)])),
        ):
            with (self.subTest(label=label), patch.object(waf, "azure_token", return_value="private-token"),
                  patch.object(waf, "json_response", return_value=value), self.assertRaises(diagnostic.CheckError)):
                waf.live_allowlist(protected_config(), WAF_ID)

    def test_missing_entries_are_exact_and_refuse_equivalent_spellings(self):
        self.assertEqual(waf.missing_entries(CONFIGURED, LIVE), ADDED)
        self.assertEqual(waf.missing_entries(LIVE, LIVE), [])
        self.assertEqual(waf.missing_entries(LIVE, CONFIGURED), [])
        for configured, live in (
            (["2001:DB8::7/128"], ["2001:db8::7/128"]),
            ([], LIVE),
            (["203.0.113.10/32", "203.0.113.10/32"], LIVE),
            (CONFIGURED, [f"198.51.100.{number}/32" for number in range(1, 11)]),
        ):
            with self.subTest(configured=len(configured)), self.assertRaises(diagnostic.CheckError):
                waf.missing_entries(configured, live)


class AppendTests(unittest.TestCase):
    def test_appending_preserves_every_other_byte_in_each_list_style(self):
        cases = {
            "single line": (
                b'front_door_allowed_cidrs = ["203.0.113.10/32"]\nother = "keep-private"\n',
                b'front_door_allowed_cidrs = ["203.0.113.10/32", "198.51.100.7/32", "2001:db8::7/128"]\n'
                b'other = "keep-private"\n',
            ),
            "single line trailing comma": (
                b'front_door_allowed_cidrs = ["203.0.113.10/32",]\n',
                b'front_door_allowed_cidrs = ["203.0.113.10/32", "198.51.100.7/32", "2001:db8::7/128",]\n',
            ),
            "multiline trailing comma": (
                INPUT,
                b'front_door_allowed_cidrs = [\n  "203.0.113.10/32",\n  "198.51.100.7/32",\n'
                b'  "2001:db8::7/128",\n]\nprivate_value = "keep-private"\n',
            ),
            "multiline no trailing comma and comments": (
                b'# mine\n  front_door_allowed_cidrs = [\n    "203.0.113.10/32" # me\n  ]\nx = 1',
                b'# mine\n  front_door_allowed_cidrs = [\n    "203.0.113.10/32", # me\n'
                b'    "198.51.100.7/32",\n    "2001:db8::7/128",\n  ]\nx = 1',
            ),
            "crlf": (
                b'front_door_allowed_cidrs = [\r\n  "203.0.113.10/32",\r\n]\r\n',
                b'front_door_allowed_cidrs = [\r\n  "203.0.113.10/32",\r\n  "198.51.100.7/32",\r\n'
                b'  "2001:db8::7/128",\r\n]\r\n',
            ),
            "closing bracket after last entry": (
                b'front_door_allowed_cidrs = [\n  "203.0.113.10/32"]\n',
                b'front_door_allowed_cidrs = [\n  "203.0.113.10/32", "198.51.100.7/32", "2001:db8::7/128"]\n',
            ),
        }
        for label, (raw, expected) in cases.items():
            with self.subTest(label=label):
                candidate = waf.append_allowlist(raw, ADDED)
                self.assertEqual(candidate, expected)
                start = waf.ATTRIBUTE.search(candidate).end()
                self.assertEqual(waf.scan_list(candidate, start)[0], CONFIGURED + ADDED)

    def test_unsupported_input_shapes_are_refused_without_rewriting(self):
        for label, raw in (
            ("empty", b""),
            ("not bytes", "front_door_allowed_cidrs = []"),
            ("too large", b"#" * (1024 * 1024 + 1)),
            ("absent", b'other = "x"\n'),
            ("duplicate", INPUT + INPUT),
            ("not a list", b'front_door_allowed_cidrs = var.other\n'),
            ("empty list", b'front_door_allowed_cidrs = []\n'),
            ("interpolation", b'front_door_allowed_cidrs = ["${var.x}/32"]\n'),
            ("escape", b'front_door_allowed_cidrs = ["203.0.113.1\\"/32"]\n'),
            ("block comment", b'front_door_allowed_cidrs = [/* x */ "203.0.113.10/32"]\n'),
            ("missing comma", b'front_door_allowed_cidrs = ["203.0.113.10/32" "198.51.100.7/32"]\n'),
            ("double comma", b'front_door_allowed_cidrs = ["203.0.113.10/32",,]\n'),
            ("unclosed", b'front_door_allowed_cidrs = ["203.0.113.10/32"\n'),
            ("function", b'front_door_allowed_cidrs = concat(["203.0.113.10/32"])\n'),
        ):
            with self.subTest(label=label), self.assertRaises(diagnostic.CheckError):
                waf.append_allowlist(raw, ADDED)
        for additions in ([], ["203.0.113.0/24"], ['198.51.100.7/32"'], ["a" * 50 + "/32"]):
            with self.subTest(additions=additions), self.assertRaises(diagnostic.CheckError):
                waf.append_allowlist(INPUT, additions)

    @unittest.skipUnless(shutil.which("terraform"), "Terraform is not installed")
    def test_real_terraform_resolves_the_candidate_and_still_enforces_its_own_validation(self):
        source = (diagnostic.ROOT / "workbench" / "infra" / "front-door.tf").read_text(encoding="utf-8")
        variable = re.search(r'variable "front_door_allowed_cidrs" \{.*?\n\}\n', source, re.DOTALL)
        self.assertIsNotNone(variable)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "main.tf").write_text(
                f'variable "subscription_id" {{\n  default = "{SUBSCRIPTION}"\n}}\n'
                'variable "name" {\n  default = "foundry-workbench"\n}\n'
                'variable "bootstrap_only" {\n  default = false\n}\n'
                'variable "enable_front_door" {\n  default = true\n}\n'
                f'variable "image_digest" {{\n  default = "{DIGEST}"\n}}\n'
                'variable "platform_state" {\n  default = null\n}\n'
                'variable "other" {\n  type = string\n  default = "default"\n}\n'
                'variable "private_value" {\n  type = string\n  default = "default"\n}\n'
                + variable.group(0),
                encoding="utf-8",
            )
            result = subprocess.run(
                ["terraform", f"-chdir={root}", "init", "-backend=false", "-no-color"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
            )
            self.assertEqual(result.returncode, 0)
            path = root / "inputs.tfvars"

            def console(raw):
                path.write_bytes(raw)
                return subprocess.run(
                    ["terraform", f"-chdir={root}", "console", "-no-color", f"-var-file={path}"],
                    input=waf.CONSOLE_INPUT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
                )

            def resolved(raw):
                result = console(raw)
                self.assertEqual(result.returncode, 0, result.stderr)
                return json.loads(json.loads(result.stdout))

            for raw in (
                INPUT,
                b'front_door_allowed_cidrs = ["203.0.113.10/32"]\nother = "x"\n',
                b'  front_door_allowed_cidrs = [\n    "203.0.113.10/32" # me\n  ]\n',
                INPUT.replace(b"\n", b"\r\n"),
            ):
                with self.subTest(raw=raw):
                    before = resolved(raw)
                    after = resolved(waf.append_allowlist(raw, ADDED))
                    self.assertEqual(before["allowed"], CONFIGURED)
                    self.assertEqual(after, {**before, "allowed": CONFIGURED + ADDED})
            for unsafe in ("10.0.0.1/32", "169.254.0.1/32", "fd00::1/128"):
                with self.subTest(unsafe=unsafe):
                    rejected = console(waf.append_allowlist(INPUT, [unsafe]))
                    self.assertIn(b"Invalid value for variable", rejected.stdout + rejected.stderr)
                    with self.assertRaises(ValueError):
                        json.loads(json.loads(rejected.stdout))


class TerraformCommandTests(unittest.TestCase):
    def test_only_the_fixed_input_inspection_commands_are_allowed(self):
        terraform = object.__new__(waf.WafTerraform)
        terraform.scratch = Path("private-scratch")
        terraform.inputs = terraform.scratch / "inputs.tfvars"
        backend = f"-backend-config={terraform.scratch / 'backend.hcl'}"
        var_file = f"-var-file={terraform.inputs}"
        with patch.object(waf.Terraform, "command", return_value=b"private-output") as command:
            terraform.command("init", "-reconfigure", backend)
            terraform.command("console", var_file, input_data=waf.CONSOLE_INPUT)
        self.assertEqual(command.call_count, 2)
        for args, kwargs in (
            (("plan",), {}),
            (("apply",), {}),
            (("console", var_file), {"input_data": b"private-unreviewed-expression"}),
            (("console", "-var-file=other"), {"input_data": waf.CONSOLE_INPUT}),
        ):
            with self.subTest(args=args), self.assertRaises(diagnostic.CheckError):
                terraform.command(*args, **kwargs)

    def test_only_the_protected_input_shape_is_accepted(self):
        values = resolved_inputs(CONFIGURED)
        self.assertEqual(waf.validate_values(values, APP, DIGEST, protected_config()), CONFIGURED)
        for alteration in (
            {"name": "other-app"},
            {"image_digest": "sha256:" + "b" * 64},
            {"allowed": "203.0.113.10/32"},
            {"allowed": [5]},
            {"additional_private_input": "private-value"},
        ):
            with self.subTest(keys=list(alteration)), self.assertRaises(diagnostic.CheckError):
                waf.validate_values({**values, **alteration}, APP, DIGEST, protected_config())


class WafRunTests(unittest.TestCase):
    def run_fixture(self, operation="inspect", expected="2", failure=None, live=LIVE):
        calls = []
        reads = []

        class FakeBlobs:
            def __init__(self, _environment):
                self.counts = {}

            def snapshot(self, name):
                self.counts[name] = self.counts.get(name, 0) + 1
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
                raw = self.inputs.read_bytes()
                entries = waf.scan_list(raw, waf.ATTRIBUTE.search(raw).end())[0]
                result = resolved_inputs(entries)
                if failure == "candidate" and entries != CONFIGURED:
                    result["name"] = "changed-private-app"
                return result

        def fake_live(_environment, _waf_id):
            reads.append(1)
            if failure == "waf" and len(reads) > 1:
                return live[:-1]
            return list(live)

        def fake_stage(scratch, _environment):
            root = scratch / "source"
            root.mkdir()
            return root

        with tempfile.TemporaryDirectory() as folder:
            env = {**environment(folder), "TF_LAB_WAF_OPERATION": operation}
            if expected is not None:
                env["TF_LAB_WAF_EXPECTED_MISSING"] = expected
            runtime = {**protected_config(), **env}
            output, errors = io.StringIO(), io.StringIO()
            with (patch.object(waf, "configuration", return_value=runtime),
                  patch.object(waf, "LabBlobs", FakeBlobs),
                  patch.object(waf, "InputBlob", FakeInputBlob),
                  patch.object(waf, "lab_state", return_value=APP),
                  patch.object(waf, "current_image", return_value=(REVISION, DIGEST)),
                  patch.object(waf, "live_allowlist", side_effect=fake_live),
                  patch.object(waf, "stage_sources", side_effect=fake_stage),
                  patch.object(waf, "configure_platform_oidc"),
                  patch.object(waf, "write_supplemental_files"),
                  patch.object(waf, "WafTerraform", FakeTerraform),
                  contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors)):
                if failure:
                    with self.assertRaises(diagnostic.CheckError):
                        waf.run(env)
                else:
                    waf.run(env)
            self.assertEqual(list(Path(folder).iterdir()), [])
        for private in FIXTURE_ADDRESSES:
            self.assertNotIn(private, output.getvalue() + errors.getvalue())
        return calls, output.getvalue(), errors.getvalue()

    def test_inspection_is_read_only_and_reports_only_counts(self):
        calls, output, errors = self.run_fixture(expected=None)
        self.assertEqual(calls, [])
        self.assertIn("live entries: 3; configured entries: 1; missing from inputs: 2.", output)
        self.assertIn("No canonical inputs were changed", output)
        self.assertEqual(errors, "")

    def test_pinning_appends_only_the_reviewed_live_entries(self):
        calls, output, errors = self.run_fixture(operation="pin-live-allowlist")
        writes = [call for call in calls if call[0] == "replace"]
        self.assertEqual(len(writes), 1)
        self.assertEqual(writes[0][1], waf.append_allowlist(INPUT, ADDED))
        self.assertEqual(calls[0][0], "lease")
        self.assertEqual(calls[-1][0], "release")
        self.assertIn("Appended 2 live entries", output)
        self.assertIn("No Terraform apply, WAF change", output)
        self.assertEqual(errors, "")

    def test_pinning_needs_the_reviewed_count_and_stops_on_a_different_one(self):
        for expected in (None, "", "0", "11", "two", "1", "3"):
            with self.subTest(expected=expected):
                calls = None
                if expected in (None, "", "0", "11", "two"):
                    with self.assertRaises(diagnostic.CheckError):
                        waf.run({
                            **environment(), "TF_LAB_WAF_OPERATION": "pin-live-allowlist",
                            **({} if expected is None else {"TF_LAB_WAF_EXPECTED_MISSING": expected}),
                        })
                else:
                    calls, _, _ = self.run_fixture(
                        operation="pin-live-allowlist", expected=expected, failure="count",
                    )
                    self.assertEqual(calls, [])

    def test_nothing_is_written_when_the_inputs_already_have_the_live_entries(self):
        calls, output, _ = self.run_fixture(operation="pin-live-allowlist", live=CONFIGURED)
        self.assertEqual(calls, [])
        self.assertIn("missing from inputs: 0.", output)
        self.assertIn("No canonical inputs were changed", output)

    def test_concurrent_changes_and_unexpected_candidate_stop_before_writing(self):
        for failure in ("state", "input", "leased-input", "candidate", "waf"):
            with self.subTest(failure=failure):
                calls, _, errors = self.run_fixture(operation="pin-live-allowlist", failure=failure)
                self.assertFalse(any(call[0] == "replace" for call in calls))
                self.assertEqual(errors, "")

    def test_ambiguous_write_fails_visibly_and_releases_the_lease(self):
        calls, _, errors = self.run_fixture(operation="pin-live-allowlist", failure="uncertain-write")
        self.assertEqual(calls[-1][0], "release")
        self.assertIn("input update was attempted", errors)
        self.assertNotIn("private-lease", errors)

    def test_other_operations_are_refused(self):
        with self.assertRaises(diagnostic.CheckError):
            waf.run({**environment(), "TF_LAB_WAF_OPERATION": "apply"})

    def test_protected_workflow_contract(self):
        workflow = (diagnostic.ROOT / ".github" / "workflows" / "reconcile-lab-waf-allowlist.yml").read_text()
        for required in (
            "workflow_dispatch:", "github.ref == 'refs/heads/main'", "terraform-state-access",
            "cancel-in-progress: false", "[self-hosted, linux, lab-runner]", "environment: terraform-state",
            "id-token: write", "persist-credentials: false", "terraform_wrapper: false",
            "secrets.TF_LAB_PLAN_CONFIG", "options: [inspect, pin-live-allowlist]", "if: always()", "--cleanup",
            "TF_LAB_WAF_EXPECTED_MISSING: ${{ inputs.expected_missing }}",
        ):
            self.assertIn(required, workflow)
        for forbidden in ("upload-artifact", "terraform apply", "-target", "-refresh=false", "azure/login"):
            self.assertNotIn(forbidden, workflow)
        self.assertNotIn("${{ inputs", workflow.split("run:")[1].split("env:")[0])


if __name__ == "__main__":
    unittest.main()

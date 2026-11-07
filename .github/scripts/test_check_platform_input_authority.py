import contextlib
from copy import deepcopy
from email.message import Message
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
from urllib.error import URLError

import check_platform_input_authority as probe

SUB = "11111111-2222-3333-4444-555555555555"
PRINCIPAL = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
GROUP = f"/subscriptions/{SUB}/resourceGroups/rg-fixture"
ROLE = f"/subscriptions/{SUB}/providers/Microsoft.Authorization/roleDefinitions/53ca6127-db72-4b80-b1b0-d745d6d5456d"


def fixture():
    inputs = {
        "subscription_id": SUB,
        "deployment_principal_id": PRINCIPAL,
        "enable_jumpbox": True,
        "jumpbox_existing_os_disk": {
            "id": GROUP + "/providers/Microsoft.Compute/disks/disk-fixture",
            "name": "disk-fixture", "storage_account_type": "Premium_LRS",
        },
    }
    state = {
        "version": 4, "serial": 2, "lineage": "synthetic",
        "resources": [
            {"mode": "managed", "type": "azurerm_resource_group", "name": "this",
             "instances": [{"attributes": {"id": GROUP}}]},
            {"mode": "managed", "type": "azurerm_role_assignment", "name": "deployer_foundry_user",
             "instances": [{"attributes": {
                 "principal_id": PRINCIPAL, "role_definition_id": ROLE,
                 "scope": GROUP + "/providers/Microsoft.CognitiveServices/accounts/example/projects/example",
                 "id": (GROUP + "/providers/Microsoft.CognitiveServices/accounts/example/projects/example"
                        + "/providers/Microsoft.Authorization/roleAssignments/" + SUB),
             }}]},
        ],
    }
    return inputs, state


def encode(value):
    return json.dumps(value).encode()


def headers(etag='"v1"', lease="unlocked", locked=False):
    result = Message()
    result["ETag"] = etag
    result["x-ms-blob-type"] = "BlockBlob"
    result["x-ms-lease-status"] = lease
    if locked:
        result["x-ms-meta-terraformlockid"] = "sensitive"
    return result


class CompareTests(unittest.TestCase):
    def test_valid_and_case_insensitive_identifiers(self):
        inputs, state = fixture()
        inputs["deployment_principal_id"] = PRINCIPAL.upper()
        probe.compare(encode(inputs), encode(state), SUB)

    def test_mismatch_and_missing_values_fail(self):
        inputs, state = fixture()
        cases = []
        for key, value in (("subscription_id", None), ("subscription_id", PRINCIPAL),
                           ("deployment_principal_id", None), ("deployment_principal_id", SUB),
                           ("enable_jumpbox", False), ("jumpbox_existing_os_disk", None),
                           ("jumpbox_existing_os_disk", {"storage_account_type": "Standard_LRS"})):
            changed = deepcopy(inputs)
            changed[key] = value
            cases.append((changed, state))
        for key, value in (("id", ""), ("name", "different"), ("size_gb", True),
                           ("size_gb", 0), ("create_option", "invalid"),
                           ("storage_account_type", "Standard_LRS")):
            changed = deepcopy(inputs)
            changed["jumpbox_existing_os_disk"][key] = value
            cases.append((changed, state))
        for mutate in (
            lambda s: s.update(version=3),
            lambda s: s.update(serial=True),
            lambda s: s.update(lineage=""),
            lambda s: s.update(resources=[]),
            lambda s: s["resources"][0]["instances"][0]["attributes"].update(id=GROUP.replace(SUB, PRINCIPAL)),
            lambda s: s["resources"][1]["instances"][0]["attributes"].update(principal_id=SUB),
            lambda s: s["resources"][1]["instances"][0]["attributes"].update(scope=GROUP),
            lambda s: s["resources"][1]["instances"][0]["attributes"].update(role_definition_id="other"),
            lambda s: s["resources"][1]["instances"][0]["attributes"].update(id="other"),
            lambda s: s["resources"][1]["instances"][0].update(deposed="old"),
            lambda s: s["resources"].append(deepcopy(s["resources"][1])),
        ):
            changed = deepcopy(state)
            mutate(changed)
            cases.append((inputs, changed))
        for inp, st in cases:
            with self.subTest(case=cases.index((inp, st))), self.assertRaises(probe.backend.CheckError):
                probe.compare(encode(inp), encode(st), SUB)

    def test_malformed_and_duplicate_json_fail(self):
        inputs, state = fixture()
        for raw in (b"{", b'{"a":1,"a":2}', b'{"a":NaN}', b"[]"):
            with self.subTest(raw=raw), self.assertRaises((ValueError, probe.backend.CheckError)):
                probe.compare(raw, encode(state), SUB)
        with self.assertRaises(ValueError):
            probe.compare(encode(inputs), b'{"resources":[{"a":1,"a":2}]}', SUB)


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.inputs, self.state = fixture()
        self.blobs = type("SyntheticBlobs", (), {"base": "https://private.invalid/container/ai-foundry/",
                                                 "headers": {"Authorization": "private-token"}})()

    def invoke(self, results):
        with patch.object(probe.lab, "configuration", return_value={"AZURE_SUBSCRIPTION_ID": SUB}), \
                patch.object(probe, "Blobs", return_value=self.blobs), \
                patch.object(probe.backend, "send", side_effect=results) as send:
            result = probe.check({})
        return result, send.call_args_list

    def normal(self):
        return [(encode(self.inputs), headers()), (encode(self.state), headers()),
                (encode(self.state), headers()), (encode(self.inputs), headers())]

    def test_exact_fixed_reads_only(self):
        result, calls = self.invoke(self.normal())
        self.assertEqual(result, "candidate_platform_comparison=matched")
        self.assertEqual([call.args[0].removeprefix(self.blobs.base) for call in calls],
                         [probe.INPUT, probe.STATE, probe.STATE, probe.INPUT])
        self.assertTrue(all(call.kwargs == {"headers": self.blobs.headers} for call in calls))

    def test_changed_etag_or_body_fails(self):
        for index in (2, 3):
            for changed in ("etag", "body"):
                results = self.normal()
                body, hdr = results[index]
                results[index] = (body + b" " if changed == "body" else body,
                                  headers(etag='"v2"') if changed == "etag" else hdr)
                with self.subTest(index=index, changed=changed), self.assertRaises(probe.backend.CheckError):
                    self.invoke(results)

    def test_lock_or_bad_metadata_fails_at_each_read(self):
        for index in range(4):
            for hdr in (headers(lease="locked"), headers(locked=True),
                        headers(etag=""), headers(lease=""), Message()):
                results = self.normal()
                results[index] = (results[index][0], hdr)
                with self.subTest(index=index, metadata=list(hdr)), self.assertRaises(probe.backend.CheckError):
                    self.invoke(results)

    def test_unapproved_blob_refused_before_network(self):
        with patch.object(probe.backend, "send") as send, self.assertRaises(probe.backend.CheckError):
            probe.snapshot(self.blobs, "other")
        send.assert_not_called()

    def test_missing_blob_or_transport_error_fails_without_success(self):
        for index in range(4):
            results = self.normal()
            results[index] = probe.backend.CheckError("private blob lookup failed")
            with self.subTest(index=index), self.assertRaises(probe.backend.CheckError):
                self.invoke(results)

    def test_redacted_errors_and_success(self):
        sensitive = "private-endpoint private-token private-header private-state"
        for result in (probe.backend.CheckError(sensitive), URLError(sensitive),
                       OSError(sensitive), ValueError(sensitive), SystemExit(sensitive)):
            with self.subTest(kind=type(result)):
                out, err = io.StringIO(), io.StringIO()
                with patch.object(probe, "check", side_effect=result), \
                        contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    self.assertEqual(probe.main(), 1)
                self.assertEqual((out.getvalue(), err.getvalue()), ("", "candidate_platform_comparison_failed\n"))
        with patch.object(probe, "check", return_value="candidate_platform_comparison=matched"), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(probe.main(), 0)
        self.assertEqual(out.getvalue(), "candidate_platform_comparison=matched\n")

    def test_unexpected_error_is_sanitized(self):
        code = """
import runpy
from unittest.mock import patch
import check_lab_terraform_plan
with patch.object(check_lab_terraform_plan, "configuration",
                  side_effect=RuntimeError("private-endpoint private-token private-headers")):
    runpy.run_path("check_platform_input_authority.py", run_name="__main__")
"""
        result = subprocess.run([sys.executable, "-c", code], cwd=Path(probe.__file__).parent,
                                capture_output=True, text=True, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "candidate_platform_comparison_failed\n")

    def test_workflow_contract(self):
        workflow = (Path(__file__).parents[1] / "workflows" / "check-platform-input-authority.yml").read_text()
        for expected in ("workflow_dispatch:", "if: github.ref == 'refs/heads/main'",
                         "runs-on: [self-hosted, linux, lab-runner]", "environment: terraform-state",
                         "id-token: write", "contents: read", "group: terraform-state-access",
                         "TF_LAB_PLAN_CONFIG: ${{ secrets.TF_LAB_PLAN_CONFIG }}"):
            self.assertIn(expected, workflow)
        for forbidden in ("pull_request:", "vars.TF_STATE_", "setup-terraform", "upload-artifact"):
            self.assertNotIn(forbidden, workflow)

    def test_real_configuration_and_oidc_helpers_are_read_only(self):
        protected = {
            "AZURE_CLIENT_ID": SUB, "AZURE_TENANT_ID": PRINCIPAL, "AZURE_SUBSCRIPTION_ID": SUB,
            "TF_STATE_ACCOUNT": "privateaccount", "TF_STATE_CONTAINER": "private-container",
            "TF_STATE_PREFIX": "ai-foundry/", "TF_STATE_PRIVATE_ENDPOINT": "10.1.2.3",
        }
        environ = {
            "TF_LAB_PLAN_CONFIG": json.dumps(protected), "GITHUB_REF": "refs/heads/main",
            "GITHUB_SHA": "a" * 40,
            "ACTIONS_ID_TOKEN_REQUEST_URL": "https://fixture.actions.githubusercontent.com/token",
            "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "private-oidc-token",
        }
        with patch.object(probe.backend.socket, "getaddrinfo", return_value=[
            (2, 1, 6, "", ("10.1.2.3", 443)),
        ]), patch.object(probe.backend, "json_response", side_effect=[
            {"value": "private-assertion"}, {"access_token": "private-access-token"},
        ]), patch.object(probe.backend, "send", side_effect=self.normal()) as send:
            self.assertEqual(probe.check(environ), "candidate_platform_comparison=matched")
        self.assertEqual(len(send.call_args_list), 4)
        for call in send.call_args_list:
            self.assertEqual(set(call.kwargs), {"headers"})
            self.assertNotIn("?", call.args[0])


if __name__ == "__main__":
    unittest.main()

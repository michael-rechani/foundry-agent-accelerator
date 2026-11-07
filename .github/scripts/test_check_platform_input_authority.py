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
ACCOUNT = GROUP + "/providers/Microsoft.CognitiveServices/accounts/example"
PROJECT = ACCOUNT + "/projects/example"
DISK = GROUP + "/providers/Microsoft.Compute/disks/disk-fixture"
ABSENT_INVENTORY = ("absent", "absent", "absent")
ABSENT_OUTPUT = ("candidate_storage_inventory=absent\ncandidate_apim_inventory=absent\n"
                 "candidate_pinned_secret_read=absent\n")


def fixture():
    inputs = {
        "subscription_id": SUB,
        "deployment_principal_id": PRINCIPAL,
        "enable_jumpbox": True,
        "jumpbox_existing_os_disk": {
            "id": DISK,
            "name": "disk-fixture", "storage_account_type": "Premium_LRS",
        },
    }
    state = {
        "version": 4, "serial": 2, "lineage": "synthetic",
        "outputs": {"foundry_account_id": {"value": ACCOUNT, "type": "string"},
                    "foundry_project_id": {"value": PROJECT, "type": "string"}},
        "resources": [
            {"mode": "managed", "type": "azurerm_resource_group", "name": "this",
             "instances": [{"attributes": {"id": GROUP}}]},
            {"mode": "managed", "type": "azurerm_role_assignment", "name": "deployer_foundry_user",
             "instances": [{"attributes": {
                 "principal_id": PRINCIPAL, "role_definition_id": ROLE,
                 "scope": PROJECT,
                 "id": PROJECT + "/providers/Microsoft.Authorization/roleAssignments/" + SUB,
             }}]},
            {"mode": "managed", "type": "azapi_resource", "name": "jumpbox",
             "instances": [{"index_key": 0, "attributes": {"body": {"properties": {"storageProfile": {
                 "osDisk": {"name": "disk-fixture", "managedDisk": {"id": DISK, "storageAccountType": "Standard_LRS"}}
             }}}}}]},
        ],
    }
    return inputs, state


def encode(value):
    return json.dumps(value).encode()


def typed_body(value):
    def descriptor(item):
        if isinstance(item, dict):
            return ["object", {key: descriptor(child) for key, child in item.items()}]
        if isinstance(item, list):
            return ["tuple", [descriptor(child) for child in item]]
        if type(item) is bool:
            return "bool"
        if type(item) in (int, float):
            return "number"
        if isinstance(item, str):
            return "string"
        return "dynamic"

    return {"type": descriptor(value), "value": deepcopy(value)}


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
            lambda s: s["outputs"]["foundry_project_id"].update(value=ACCOUNT + "/projects/another"),
            lambda s: s["outputs"]["foundry_account_id"].update(value=ACCOUNT + "another"),
            lambda s: s["outputs"].pop("foundry_project_id"),
            lambda s: s["outputs"]["foundry_project_id"].update(type="number"),
            lambda s: s["resources"][2]["instances"][0]["attributes"]["body"]["properties"]["storageProfile"]["osDisk"].update(name="other"),
            lambda s: s["resources"][2]["instances"][0]["attributes"]["body"]["properties"]["storageProfile"]["osDisk"]["managedDisk"].update(id=DISK + "other"),
            lambda s: s["resources"][2]["instances"][0]["attributes"]["body"]["properties"]["storageProfile"]["osDisk"]["managedDisk"].pop("id"),
            lambda s: s["resources"][2]["instances"][0].update(index_key=1),
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
            with self.subTest(raw=raw), self.assertRaises(probe.CandidateError):
                probe.compare(raw, encode(state), SUB)
        with self.assertRaises(probe.StateError):
            probe.compare(encode(inputs), b'{"resources":[{"a":1,"a":2}]}', SUB)

    def test_string_jumpbox_body_and_tier_are_not_compared(self):
        inputs, state = fixture()
        attrs = state["resources"][2]["instances"][0]["attributes"]
        attrs["body"] = json.dumps(attrs["body"])
        probe.compare(encode(inputs), encode(state), SUB)

    def test_cty_dynamic_object_body_and_disk_identity(self):
        inputs, state = fixture()
        attrs = state["resources"][2]["instances"][0]["attributes"]
        body = attrs["body"]
        body["properties"].update(
            hardwareProfile={"vmSize": "synthetic"},
            networkProfile={"networkInterfaces": [{"id": "synthetic", "properties": {"primary": True}}]},
            dataDisks=[], optional=None,
        )
        attrs["body"] = typed_body(body)
        probe.compare(encode(inputs), encode(state), SUB)
        nested = deepcopy(state)
        nested_body = nested["resources"][2]["instances"][0]["attributes"]["body"]
        nested_body["type"][1]["properties"] = "dynamic"
        nested_body["value"]["properties"] = typed_body(nested_body["value"]["properties"])
        probe.compare(encode(inputs), encode(nested), SUB)
        for field in ("id", "name"):
            altered = deepcopy(state)
            os_disk = altered["resources"][2]["instances"][0]["attributes"]["body"]["value"]["properties"][
                "storageProfile"]["osDisk"]
            target = os_disk["managedDisk"] if field == "id" else os_disk
            target[field] += "-different"
            with self.subTest(field=field), self.assertRaises(probe.CandidateError):
                probe.compare(encode(inputs), encode(altered), SUB)

    def test_dynamic_type_and_value_are_strictly_consistent(self):
        inputs, state = fixture()
        attrs = state["resources"][2]["instances"][0]["attributes"]
        original = typed_body(attrs["body"])
        cases = []
        for mutate in (
            lambda b: b.pop("type"),
            lambda b: b.pop("value"),
            lambda b: b.update(properties=deepcopy(b["value"]["properties"])),
            lambda b: b.update(type=["object", {}]),
            lambda b: b.update(type=["object", "not-an-object"]),
            lambda b: b.update(type=["object", {}, []]),
            lambda b: b.update(type=["unknown", {}]),
            lambda b: b.update(type="dynamic"),
            lambda b: b["type"][1].update(extra="string"),
            lambda b: b["value"].update(extra="private-value"),
            lambda b: b["type"][1]["properties"][1]["storageProfile"][1]["osDisk"][1].update(name="number"),
            lambda b: b["value"]["properties"]["storageProfile"]["osDisk"].update(name=True),
            lambda b: b.update(value=[]),
        ):
            changed = deepcopy(original)
            mutate(changed)
            cases.append(changed)
        for case in cases:
            attrs["body"] = case
            with self.subTest(case=cases.index(case)), self.assertRaises(probe.StateDiskDetailError) as caught:
                probe.compare(encode(inputs), encode(state), SUB)
            self.assertEqual(caught.exception.category, "disk_dynamic_invalid")

    def test_cty_collection_types_and_nested_dynamic_values(self):
        descriptor = ["object", {
            "map": ["map", "string"], "list": ["list", "number"],
            "set": ["set", "bool"], "tuple": ["tuple", ["string", "dynamic"]],
        }]
        value = {"map": {"key": "value"}, "list": [1, 2.5], "set": [True, False],
                 "tuple": ["synthetic", {"type": "string", "value": "synthetic"}]}
        self.assertTrue(probe.valid_cty_type(descriptor))
        self.assertTrue(probe.valid_cty_value(descriptor, value))
        for key, invalid in (("map", {"key": 1}), ("list", [True]), ("set", [0]),
                             ("set", [True, True]),
                             ("tuple", ["synthetic", {"type": "number", "value": "not-number"}])):
            changed = deepcopy(value)
            changed[key] = invalid
            with self.subTest(key=key):
                self.assertFalse(probe.valid_cty_value(descriptor, changed))

    def test_other_project_role_even_with_matching_assignment_id_is_rejected(self):
        inputs, state = fixture()
        role = state["resources"][1]["instances"][0]["attributes"]
        role["scope"] = ACCOUNT + "/projects/another"
        role["id"] = role["scope"] + "/providers/Microsoft.Authorization/roleAssignments/" + SUB
        with self.assertRaises(probe.StateError):
            probe.compare(encode(inputs), encode(state), SUB)

    def test_secret_precondition_independent_of_missing_pin_or_invalid_state(self):
        inputs, state = fixture()
        inputs["jumpbox_admin_secret"] = {"private-field": "private-value"}
        for missing_pin, invalid_state, expected in (
            (False, False, (False, False, True, False)),
            (True, False, (False, True, True, False)),
            (False, True, (False, False, True, True)),
        ):
            with self.subTest(missing_pin=missing_pin, invalid_state=invalid_state):
                candidate = deepcopy(inputs)
                if missing_pin:
                    candidate.pop("deployment_principal_id")
                with self.assertRaises(probe.PreconditionError) as caught:
                    probe.compare(encode(candidate), b"{" if invalid_state else encode(state), SUB)
                exc = caught.exception
                self.assertEqual((exc.input_mismatch, exc.pin_invalid, exc.secret_read, exc.state_invalid), expected)


class InventoryTests(unittest.TestCase):
    def test_managed_instances_across_modules_and_data_excluded(self):
        _, state = fixture()
        self.assertEqual(probe.inventory(state), ("absent", "absent"))
        for kind in ("azurerm_storage_account", "azurerm_api_management"):
            state["resources"].append({
                "module": 'module.example["fixture"].module.child',
                "mode": "managed", "type": kind, "name": "example",
                "instances": [{"index_key": "first", "attributes": {"id": "private-value"}},
                              {"index_key": "second", "attributes": {"id": "private-value"}}],
            })
        self.assertEqual(probe.inventory(state), ("present", "present"))
        state["resources"][-1]["mode"] = "data"
        state["resources"][-2]["instances"] = []
        self.assertEqual(probe.inventory(state), ("absent", "absent"))

    def test_entire_resource_and_instance_envelope_fails_closed(self):
        _, original = fixture()
        mutations = (
            lambda s: s.update(version=True),
            lambda s: s.update(resources=[]),
            lambda s: s["resources"].append(None),
            lambda s: s["resources"].append({}),
            lambda s: s["resources"][0].update(mode="unknown"),
            lambda s: s["resources"][0].update(type=None),
            lambda s: s["resources"][0].update(name=""),
            lambda s: s["resources"][0].update(module=17),
            lambda s: s["resources"][0].update(module="not-a-module"),
            lambda s: s["resources"][0].update(module="module."),
            lambda s: s["resources"][0].update(module='module.example["unfinished]'),
            lambda s: s["resources"][0].update(provider=None),
            lambda s: s["resources"][0].update(instances=None),
            lambda s: s["resources"][0].update(instances=[None]),
            lambda s: s["resources"][0]["instances"][0].update(attributes=None),
            lambda s: s["resources"][0]["instances"][0].update(schema_version=True),
            lambda s: s["resources"][0]["instances"][0].update(sensitive_attributes=None),
            lambda s: s["resources"][0]["instances"][0].update(dependencies=[None]),
            lambda s: s["resources"][0]["instances"][0].update(deposed="private-value"),
            lambda s: s["resources"][0]["instances"][0].update(deposed=None),
            lambda s: s["resources"][0]["instances"][0].update(status="unknown"),
            lambda s: s["resources"][0]["instances"][0].update(index_key=False),
            lambda s: s["resources"][0]["instances"][0].update(index_key=0.0),
            lambda s: s["resources"][0]["instances"][0].update(index_key=-1),
            lambda s: s["resources"][0]["instances"][0].update(index_key=None),
            lambda s: s["resources"][0]["instances"].append({"attributes": {}}),
            lambda s: s["resources"][0].update(instances=[
                {"index_key": 0, "attributes": {}}, {"index_key": 0, "attributes": {}}]),
            lambda s: s["resources"][0].update(instances=[
                {"index_key": 0, "attributes": {}}, {"index_key": "1", "attributes": {}}]),
            lambda s: s["resources"].append(deepcopy(s["resources"][0])),
        )
        for mutate in mutations:
            state = deepcopy(original)
            mutate(state)
            with self.subTest(case=mutations.index(mutate)):
                self.assertEqual(probe.inventory(state), ("ambiguous", "ambiguous"))

    def test_pinned_secret_read_is_fixed_and_fail_closed(self):
        inputs, _ = fixture()
        self.assertEqual(probe.pinned_secret_read(inputs), "absent")
        secret = {"key_vault_id": GROUP + "/providers/Microsoft.KeyVault/vaults/fixture",
                  "name": "fixture", "version": "a" * 32}
        inputs["jumpbox_admin_secret"] = secret
        self.assertEqual(probe.pinned_secret_read(inputs), "present")
        inputs["enable_jumpbox"] = False
        self.assertEqual(probe.pinned_secret_read(inputs), "absent")
        inputs["enable_jumpbox"] = "true"
        self.assertEqual(probe.pinned_secret_read(inputs), "ambiguous")
        inputs["enable_jumpbox"] = True
        for key in secret:
            changed = deepcopy(inputs)
            changed["jumpbox_admin_secret"][key] = ""
            self.assertEqual(probe.pinned_secret_read(changed), "ambiguous")
        inputs["jumpbox_admin_secret"] = ["private-value"]
        self.assertEqual(probe.pinned_secret_read(inputs), "ambiguous")


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
        self.assertEqual(result, ("absent", ABSENT_INVENTORY))
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

    def test_comparison_occurs_between_reads_and_instability_wins(self):
        events = []
        results = self.normal()
        candidate = deepcopy(self.inputs)
        candidate.pop("deployment_principal_id")
        candidate["jumpbox_admin_secret"] = {"private-field": "private-value"}
        results[0] = (encode(candidate), headers())
        results[3] = (encode(candidate), headers(etag='"changed"'))
        def send(*args, **kwargs):
            events.append("read")
            return results.pop(0)
        original = probe.compare
        def compare(*args):
            events.append("compare")
            return original(*args)
        original_inventory = probe.inventory
        def inventory(*args):
            events.append("inventory")
            return original_inventory(*args)
        out, err = io.StringIO(), io.StringIO()
        with patch.object(probe.lab, "configuration", return_value={"AZURE_SUBSCRIPTION_ID": SUB}), \
                patch.object(probe, "Blobs", return_value=self.blobs), \
                patch.object(probe.backend, "send", side_effect=send), \
                patch.object(probe, "compare", side_effect=compare), \
                patch.object(probe, "inventory", side_effect=inventory), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.assertEqual(probe.main(), 1)
        self.assertEqual(events, ["read", "read", "inventory", "compare", "read", "read"])
        self.assertEqual((out.getvalue(), err.getvalue()),
                         ("", "candidate_platform_comparison_failed=snapshot_unstable\n"))

    def test_inventory_and_secret_categories_are_redacted_and_snapshot_gated(self):
        state = deepcopy(self.state)
        state["resources"].extend([
            {"mode": "managed", "module": 'module.example["private-value"]',
             "type": kind, "name": "private-value",
             "instances": [{"index_key": "private-value", "attributes": {"id": "private-value"}}]}
            for kind in ("azurerm_storage_account", "azurerm_api_management")
        ])
        inputs = deepcopy(self.inputs)
        inputs["jumpbox_admin_secret"] = {
            "key_vault_id": GROUP + "/providers/Microsoft.KeyVault/vaults/fixture",
            "name": "private-value", "version": "a" * 32,
        }
        for unstable in (False, True):
            results = [(encode(inputs), headers()), (encode(state), headers()),
                       (encode(state), headers(lease="locked" if unstable else "unlocked")),
                       (encode(inputs), headers())]
            out, err = io.StringIO(), io.StringIO()
            with self.subTest(unstable=unstable), \
                    patch.object(probe.lab, "configuration", return_value={"AZURE_SUBSCRIPTION_ID": SUB}), \
                    patch.object(probe, "Blobs", return_value=self.blobs), \
                    patch.object(probe.backend, "send", side_effect=results), \
                    contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                self.assertEqual(probe.main(), 1)
            self.assertEqual(out.getvalue(), "")
            if unstable:
                self.assertEqual(err.getvalue(), "candidate_platform_comparison_failed=snapshot_unstable\n")
            else:
                self.assertEqual(err.getvalue(), "candidate_platform_comparison_failed=secret_read_review_required\n"
                                 "candidate_router_override=absent\n"
                                 "candidate_storage_inventory=present\ncandidate_apim_inventory=present\n"
                                 "candidate_pinned_secret_read=present\n")

    def test_ambiguous_inventory_is_reported_without_private_values(self):
        state = deepcopy(self.state)
        state["resources"].append({"private-field": "private-value"})
        results = self.normal()
        results[1] = results[2] = (encode(state), headers())
        out, err = io.StringIO(), io.StringIO()
        with patch.object(probe.lab, "configuration", return_value={"AZURE_SUBSCRIPTION_ID": SUB}), \
                patch.object(probe, "Blobs", return_value=self.blobs), \
                patch.object(probe.backend, "send", side_effect=results), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.assertEqual(probe.main(), 0)
        self.assertEqual(err.getvalue(), "")
        self.assertEqual(out.getvalue(), "candidate_platform_comparison=matched\n"
                         "candidate_router_override=absent\ncandidate_storage_inventory=ambiguous\n"
                         "candidate_apim_inventory=ambiguous\ncandidate_pinned_secret_read=absent\n")

    def test_present_inventory_on_success_and_byte_change_precedence(self):
        state = deepcopy(self.state)
        state["resources"].append({
            "mode": "managed", "type": "azurerm_storage_account", "name": "private-value",
            "module": 'module.example["private-value"]',
            "instances": [{"index_key": 0, "attributes": {"id": "private-value"}}],
        })
        for changed in (False, True):
            results = self.normal()
            results[1] = (encode(state), headers())
            results[2] = (encode(state) + (b" " if changed else b""), headers())
            out, err = io.StringIO(), io.StringIO()
            with self.subTest(changed=changed), \
                    patch.object(probe.lab, "configuration", return_value={"AZURE_SUBSCRIPTION_ID": SUB}), \
                    patch.object(probe, "Blobs", return_value=self.blobs), \
                    patch.object(probe.backend, "send", side_effect=results), \
                    contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                self.assertEqual(probe.main(), 1 if changed else 0)
            if changed:
                self.assertEqual((out.getvalue(), err.getvalue()),
                                 ("", "candidate_platform_comparison_failed=snapshot_unstable\n"))
            else:
                self.assertEqual(err.getvalue(), "")
                self.assertEqual(out.getvalue(), "candidate_platform_comparison=matched\n"
                                 "candidate_router_override=absent\ncandidate_storage_inventory=present\n"
                                 "candidate_apim_inventory=absent\ncandidate_pinned_secret_read=absent\n")

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

    def test_failure_categories_follow_actual_error_sources(self):
        cases = []
        results = self.normal()
        results[0] = (encode({}), headers())
        results[3] = results[0]
        cases.append((results, "input_mismatch_or_missing"))
        results = self.normal()
        results[1] = (results[1][0], headers(lease="locked"))
        cases.append((results, "snapshot_unstable"))
        results = self.normal()
        results[0] = probe.backend.CheckError("private-url private-token")
        cases.append((results, "read_failure"))
        for results, category in cases:
            with self.subTest(category=category):
                out, err = io.StringIO(), io.StringIO()
                with patch.object(probe.lab, "configuration", return_value={"AZURE_SUBSCRIPTION_ID": SUB}), \
                        patch.object(probe, "Blobs", return_value=self.blobs), \
                        patch.object(probe.backend, "send", side_effect=results), \
                        contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    self.assertEqual(probe.main(), 1)
                self.assertEqual((out.getvalue(), err.getvalue()),
                                 ("", f"candidate_platform_comparison_failed={category}\n"
                                  + ("candidate_router_override=absent\n" if category == "input_mismatch_or_missing" else "")))

    def test_state_failure_categories_are_fixed_and_preserve_secret_blocker(self):
        def malformed_envelope(state):
            state["serial"] = True

        def malformed_inventory(state):
            state["resources"].append(deepcopy(state["resources"][0]))

        def malformed_outputs(state):
            state["outputs"]["foundry_project_id"]["value"] = "private-project"

        def malformed_role(state):
            state["resources"][1]["instances"][0]["attributes"]["principal_id"] = "private-identity"

        def malformed_disk(state):
            state["resources"][2]["instances"][0]["attributes"]["body"] = {"private-field": "private-value"}

        for mutate, category in (
            (malformed_envelope, "state_envelope_invalid"),
            (malformed_inventory, "state_inventory_invalid"),
            (malformed_outputs, "state_outputs_invalid"),
            (malformed_role, "state_role_invalid"),
            (malformed_disk, "disk_parent_missing"),
        ):
            for secret in (False, True):
                with self.subTest(category=category, secret=secret):
                    state = deepcopy(self.state)
                    mutate(state)
                    inputs = deepcopy(self.inputs)
                    if secret:
                        inputs["jumpbox_admin_secret"] = {"private-field": "private-value"}
                    results = [
                        (encode(inputs), headers()), (encode(state), headers()),
                        (encode(state), headers()), (encode(inputs), headers()),
                    ]
                    out, err = io.StringIO(), io.StringIO()
                    with patch.object(probe.lab, "configuration", return_value={"AZURE_SUBSCRIPTION_ID": SUB}), \
                            patch.object(probe, "Blobs", return_value=self.blobs), \
                            patch.object(probe.backend, "send", side_effect=results), \
                            contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                        self.assertEqual(probe.main(), 1)
                    expected = ("candidate_platform_comparison_failed=secret_read_review_required\n" if secret else "")
                    expected += f"candidate_platform_comparison_failed={category}\n"
                    expected += "candidate_router_override=absent\n"
                    self.assertEqual((out.getvalue(), err.getvalue()), ("", expected))

    def test_resource_specific_categories_are_redacted(self):
        for resource, mode, category in (
            (0, "missing", "state_inventory_invalid"),
            (0, "duplicate", "state_inventory_invalid"),
            (1, "missing", "state_role_invalid"),
            (1, "duplicate", "state_role_invalid"),
            (1, "instance", "state_role_invalid"),
            (1, "scope", "state_role_scope_mismatch"),
            (1, "bad_scope", "state_role_invalid"),
            (2, "missing", "disk_resource_missing"),
            (2, "duplicate", "disk_resource_multiple"),
            (2, "instance", "disk_instance_missing"),
        ):
            with self.subTest(resource=resource, mode=mode):
                state = deepcopy(self.state)
                item = state["resources"][resource]
                if mode == "missing":
                    state["resources"].pop(resource)
                elif mode == "duplicate":
                    state["resources"].append(deepcopy(item))
                elif mode == "instance":
                    item["instances"] = []
                elif mode == "scope":
                    item["instances"][0]["attributes"]["scope"] = ACCOUNT + "/projects/private-project"
                else:
                    item["instances"][0]["attributes"]["scope"] = None
                results = [(encode(self.inputs), headers()), (encode(state), headers()),
                           (encode(state), headers()), (encode(self.inputs), headers())]
                out, err = io.StringIO(), io.StringIO()
                with patch.object(probe.lab, "configuration", return_value={"AZURE_SUBSCRIPTION_ID": SUB}), \
                        patch.object(probe, "Blobs", return_value=self.blobs), \
                        patch.object(probe.backend, "send", side_effect=results), \
                        contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    self.assertEqual(probe.main(), 1)
                self.assertEqual((out.getvalue(), err.getvalue()),
                                 ("", f"candidate_platform_comparison_failed={category}\n"
                                  "candidate_router_override=absent\n"))

    def test_disk_guard_detailed_categories_are_bounded_and_redacted(self):
        def mutate(state, case):
            resources = state["resources"]
            resource = resources[2]
            instance = resource["instances"][0]
            attrs = instance["attributes"]
            if case == "disk_resource_missing":
                resources.pop(2)
            elif case == "disk_resource_multiple":
                resources.append(deepcopy(resource))
            elif case == "disk_instances_invalid":
                resource["instances"] = "private-value"
            elif case == "disk_instance_missing":
                resource["instances"] = []
            elif case == "disk_instance_multiple":
                resource["instances"].append(deepcopy(instance))
            elif case == "disk_instance_invalid":
                resource["instances"][0] = "private-value"
            elif case == "disk_instance_deposed":
                instance["deposed"] = "private-value"
            elif case == "disk_instance_index_invalid":
                instance["index_key"] = 1
            elif case == "disk_attributes_invalid":
                instance["attributes"] = "private-value"
            elif case == "disk_body_missing":
                attrs.pop("body")
            elif case == "disk_body_invalid":
                attrs["body"] = []
            elif case == "disk_body_json_invalid":
                attrs["body"] = '{"private-field":"private-value",'
            elif case == "disk_dynamic_invalid":
                attrs["body"] = {"type": ["object", {}], "value": {"private-field": "private-value"}}
            elif case.startswith(("disk_parent_", "disk_storage_", "disk_os_", "disk_managed_",
                                  "disk_id_", "disk_name_")):
                body = attrs["body"]
                parents = {
                    "parent": (body, "properties"),
                    "storage": (body["properties"], "storageProfile"),
                    "os": (body["properties"]["storageProfile"], "osDisk"),
                    "managed": (body["properties"]["storageProfile"]["osDisk"], "managedDisk"),
                    "id": (body["properties"]["storageProfile"]["osDisk"]["managedDisk"], "id"),
                    "name": (body["properties"]["storageProfile"]["osDisk"], "name"),
                }
                _, kind, status = case.split("_")
                parent, key = parents[kind]
                if status == "missing":
                    parent.pop(key)
                else:
                    parent[key] = ["private-value"]
            else:
                self.fail("unhandled category")

        for category in sorted(probe.DISK_FAILURE_CATEGORIES):
            for secret in (False, True):
                with self.subTest(category=category, secret=secret):
                    state, inputs = deepcopy(self.state), deepcopy(self.inputs)
                    mutate(state, category)
                    if secret:
                        inputs["jumpbox_admin_secret"] = {"private-field": "private-value"}
                    results = [(encode(inputs), headers()), (encode(state), headers()),
                               (encode(state), headers()), (encode(inputs), headers())]
                    out, err = io.StringIO(), io.StringIO()
                    with patch.object(probe.lab, "configuration", return_value={"AZURE_SUBSCRIPTION_ID": SUB}), \
                            patch.object(probe, "Blobs", return_value=self.blobs), \
                            patch.object(probe.backend, "send", side_effect=results), \
                            contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                        self.assertEqual(probe.main(), 1)
                    expected = "candidate_platform_comparison_failed=secret_read_review_required\n" if secret else ""
                    expected += f"candidate_platform_comparison_failed={category}\ncandidate_router_override=absent\n"
                    self.assertEqual((out.getvalue(), err.getvalue()), ("", expected))

    def test_jumpbox_index_requires_integer_zero(self):
        for value in (False, 0.0, "0", None):
            with self.subTest(value=value):
                state = deepcopy(self.state)
                instance = state["resources"][2]["instances"][0]
                if value is None:
                    instance.pop("index_key")
                else:
                    instance["index_key"] = value
                results = [(encode(self.inputs), headers()), (encode(state), headers()),
                           (encode(state), headers()), (encode(self.inputs), headers())]
                out, err = io.StringIO(), io.StringIO()
                with patch.object(probe.lab, "configuration", return_value={"AZURE_SUBSCRIPTION_ID": SUB}), \
                        patch.object(probe, "Blobs", return_value=self.blobs), \
                        patch.object(probe.backend, "send", side_effect=results), \
                        contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    self.assertEqual(probe.main(), 1)
                self.assertEqual((out.getvalue(), err.getvalue()),
                                 ("", "candidate_platform_comparison_failed=disk_instance_index_invalid\n"
                                  "candidate_router_override=absent\n"))

    def test_unstable_snapshots_override_disk_detail_and_secret(self):
        state, inputs = deepcopy(self.state), deepcopy(self.inputs)
        state["resources"][2]["instances"][0]["attributes"].pop("body")
        inputs["jumpbox_admin_secret"] = {"private-field": "private-value"}
        results = [(encode(inputs), headers()), (encode(state), headers()),
                   (encode(state), headers(etag='"changed"')), (encode(inputs), headers())]
        out, err = io.StringIO(), io.StringIO()
        with patch.object(probe.lab, "configuration", return_value={"AZURE_SUBSCRIPTION_ID": SUB}), \
                patch.object(probe, "Blobs", return_value=self.blobs), \
                patch.object(probe.backend, "send", side_effect=results), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.assertEqual(probe.main(), 1)
        self.assertEqual((out.getvalue(), err.getvalue()),
                         ("", "candidate_platform_comparison_failed=snapshot_unstable\n"))

    def test_unstable_snapshots_override_dynamic_error_and_secret(self):
        state, inputs = deepcopy(self.state), deepcopy(self.inputs)
        state["resources"][2]["instances"][0]["attributes"]["body"] = {"type": "private-value"}
        inputs["jumpbox_admin_secret"] = {"private-field": "private-value"}
        results = [(encode(inputs), headers()), (encode(state), headers()),
                   (encode(state), headers(etag='"changed"')), (encode(inputs), headers())]
        out, err = io.StringIO(), io.StringIO()
        with patch.object(probe.lab, "configuration", return_value={"AZURE_SUBSCRIPTION_ID": SUB}), \
                patch.object(probe, "Blobs", return_value=self.blobs), \
                patch.object(probe.backend, "send", side_effect=results), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.assertEqual(probe.main(), 1)
        self.assertEqual((out.getvalue(), err.getvalue()),
                         ("", "candidate_platform_comparison_failed=snapshot_unstable\n"))

    def test_synthetic_provider_shape_rejects_identity_mismatches(self):
        for field in ("id", "name"):
            for body_as_json in (False, True):
                with self.subTest(field=field, body_as_json=body_as_json):
                    state = deepcopy(self.state)
                    attrs = state["resources"][2]["instances"][0]["attributes"]
                    os_disk = attrs["body"]["properties"]["storageProfile"]["osDisk"]
                    if field == "id":
                        os_disk["managedDisk"]["id"] = DISK + "-other"
                    else:
                        os_disk["name"] = "other"
                    if body_as_json:
                        attrs["body"] = json.dumps(attrs["body"])
                    with self.assertRaises(probe.CandidateError):
                        probe.compare(encode(self.inputs), encode(state), SUB)

    def test_unstable_snapshots_override_state_and_secret_categories(self):
        state = deepcopy(self.state)
        state["serial"] = True
        inputs = deepcopy(self.inputs)
        inputs["jumpbox_admin_secret"] = {"private-field": "private-value"}
        results = [(encode(inputs), headers()), (encode(state), headers()),
                   (encode(state), headers(etag='"changed"')), (encode(inputs), headers())]
        out, err = io.StringIO(), io.StringIO()
        with patch.object(probe.lab, "configuration", return_value={"AZURE_SUBSCRIPTION_ID": SUB}), \
                patch.object(probe, "Blobs", return_value=self.blobs), \
                patch.object(probe.backend, "send", side_effect=results), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.assertEqual(probe.main(), 1)
        self.assertEqual((out.getvalue(), err.getvalue()),
                         ("", "candidate_platform_comparison_failed=snapshot_unstable\n"))

    def test_independent_secret_and_input_categories_are_sanitized(self):
        candidate = deepcopy(self.inputs)
        candidate.pop("deployment_principal_id")
        candidate["jumpbox_admin_secret"] = {"private-field": "private-value"}
        results = self.normal()
        results[0] = (encode(candidate), headers())
        results[3] = results[0]
        out, err = io.StringIO(), io.StringIO()
        with patch.object(probe.lab, "configuration", return_value={"AZURE_SUBSCRIPTION_ID": SUB}), \
                patch.object(probe, "Blobs", return_value=self.blobs), \
                patch.object(probe.backend, "send", side_effect=results), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.assertEqual(probe.main(), 1)
        self.assertEqual(out.getvalue(), "")
        self.assertEqual(err.getvalue(), "candidate_platform_comparison_failed=identity_pin_missing_or_invalid\n"
                         "candidate_platform_comparison_failed=secret_read_review_required\n"
                         "candidate_router_override=absent\n")

    def test_router_override_presence_only_including_null_and_on_failure(self):
        for value in (None, {"private-field": "private-value"}, "private-value"):
            for fail in (False, True):
                inputs = deepcopy(self.inputs)
                inputs["model_router_deployment"] = value
                if fail:
                    inputs.pop("deployment_principal_id")
                results = self.normal()
                results[0] = results[3] = (encode(inputs), headers())
                out, err = io.StringIO(), io.StringIO()
                with self.subTest(value=value, fail=fail), \
                        patch.object(probe.lab, "configuration", return_value={"AZURE_SUBSCRIPTION_ID": SUB}), \
                        patch.object(probe, "Blobs", return_value=self.blobs), \
                        patch.object(probe.backend, "send", side_effect=results), \
                        contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    self.assertEqual(probe.main(), 1 if fail else 0)
                if fail:
                    self.assertEqual(err.getvalue(), "candidate_platform_comparison_failed=identity_pin_missing_or_invalid\n"
                                     "candidate_router_override=explicit\n")
                    self.assertEqual(out.getvalue(), "")
                else:
                    self.assertEqual(err.getvalue(), "")
                    self.assertEqual(out.getvalue(), "candidate_platform_comparison=matched\n"
                                     "candidate_router_override=explicit\n" + ABSENT_OUTPUT)

    def test_redacted_errors_and_success(self):
        sensitive = "private-endpoint private-token private-header private-state"
        for result, category in (
            (probe.CandidateError(sensitive), "input_mismatch_or_missing"),
            (probe.PinError(sensitive), "identity_pin_missing_or_invalid"),
            (probe.StateError(sensitive), "protected_state_invalid"),
            (probe.SnapshotError(sensitive), "snapshot_unstable"),
            (probe.ReadError(sensitive), "read_failure"),
            (probe.backend.CheckError(sensitive), "unexpected"),
            (URLError(sensitive), "unexpected"), (OSError(sensitive), "unexpected"),
            (ValueError(sensitive), "unexpected"), (SystemExit(sensitive), "unexpected"),
        ):
            with self.subTest(kind=type(result)):
                out, err = io.StringIO(), io.StringIO()
                with patch.object(probe, "check", side_effect=result), \
                        contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    self.assertEqual(probe.main(), 1)
                self.assertEqual((out.getvalue(), err.getvalue()),
                                 ("", f"candidate_platform_comparison_failed={category}\n"))
        with patch.object(probe, "check", return_value=("absent", ABSENT_INVENTORY)), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(probe.main(), 0)
        self.assertEqual(out.getvalue(), "candidate_platform_comparison=matched\ncandidate_router_override=absent\n"
                         + ABSENT_OUTPUT)

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
        self.assertEqual(result.stderr, "candidate_platform_comparison_failed=unexpected\n")

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
            self.assertEqual(probe.check(environ), ("absent", ABSENT_INVENTORY))
        self.assertEqual(len(send.call_args_list), 4)
        for call in send.call_args_list:
            self.assertEqual(set(call.kwargs), {"headers"})
            self.assertNotIn("?", call.args[0])


if __name__ == "__main__":
    unittest.main()

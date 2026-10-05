import contextlib
import copy
import io
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import plan_check
import test_addon_manifest as manifests
from addon_manifest import ADDONS_DIRECTORY, GUARDRAILS, load_add_ons

PLANS = ADDONS_DIRECTORY / "testdata" / "plans"
READER_ID = "1407120a-92aa-4202-b7e9-c0e197c71c8f"
CONTRIBUTOR_ID = "8ebe5a00-799e-43f5-93ac-243d3dce84a7"
SUBSCRIPTION = "/subscriptions/00000000-0000-0000-0000-000000000000"
SERVICE = f"{SUBSCRIPTION}/resourceGroups/rg-example/providers/Microsoft.Search/searchServices/search-example"
PRINCIPAL = "11111111-1111-1111-1111-111111111111"


def knowledge_search():
    return next(add_on for add_on in load_add_ons(ADDONS_DIRECTORY) if add_on.id == "knowledge-search")


def read_plan(name):
    return json.loads((PLANS / f"{name}.json").read_text(encoding="utf-8"))


def plan_of(*changes, **top_level):
    return {"format_version": "1.2", "planned_values": {}, "resource_changes": list(changes), **top_level}


def change(address, resource_type, after=None, *, actions=("create",), before=None, unknown=None, mode="managed"):
    return {
        "address": address,
        "mode": mode,
        "type": resource_type,
        "name": address.rsplit(".", 1)[-1],
        "change": {"actions": list(actions), "before": before, "after": after, "after_unknown": unknown or {}},
    }


def role_assignment(address="azurerm_role_assignment.grant", **after):
    fields = {
        "scope": f"{SERVICE}/indexes/lab-sample-policy-guidance",
        "role_definition_id": f"{SUBSCRIPTION}/providers/Microsoft.Authorization/roleDefinitions/{READER_ID}",
        "principal_id": PRINCIPAL,
        "principal_type": "ServicePrincipal",
    }
    fields.update(after)
    return change(address, "azurerm_role_assignment", {key: value for key, value in fields.items() if value is not None})


def azapi_role_assignment(**properties):
    body = {
        "properties": {
            "roleDefinitionId": f"{SUBSCRIPTION}/providers/Microsoft.Authorization/roleDefinitions/{READER_ID}",
            "principalId": PRINCIPAL,
            "principalType": "ServicePrincipal",
        }
    }
    body["properties"].update(properties)
    return change(
        "azapi_resource.grant",
        "azapi_resource",
        {
            "type": "Microsoft.Authorization/roleAssignments@2022-04-01",
            "parent_id": f"{SERVICE}/indexes/lab-sample-policy-guidance",
            "body": body,
        },
    )


def package(**changes):
    return manifests.package(**changes)


def allow(*resource_types):
    return {"module": "terraform", "resource_types": list(resource_types)}


def findings(plan, **changes):
    return plan_check.check_plan(plan, package(**changes))


def rules(found):
    return sorted({finding.rule for finding in found})


class FixturePlans(unittest.TestCase):
    def check(self, name):
        return plan_check.check_plan(read_plan(name), knowledge_search().package)

    def test_the_plan_for_the_modules_one_grant_passes(self):
        self.assertEqual([], self.check("knowledge-search-passes"))

    def test_a_teardown_that_only_removes_the_grant_passes(self):
        self.assertEqual([], self.check("knowledge-search-teardown-passes"))

    def test_public_access_and_ip_allow_lists_fail(self):
        found = self.check("public-access-fails")
        self.assertIn(plan_check.PUBLIC_ACCESS, rules(found))
        addresses = {finding.address for finding in found if finding.rule == plan_check.PUBLIC_ACCESS}
        self.assertEqual(
            {"module.knowledge_search.azurerm_search_service.copy", "module.knowledge_search.azapi_resource.search_by_arm"},
            addresses,
        )
        messages = " ".join(finding.message for finding in found)
        self.assertIn("public_network_access_enabled", messages)
        self.assertIn("body.properties.publicNetworkAccess", messages)
        self.assertIn("IP allow list", messages)

    def test_keys_and_local_auth_fail(self):
        found = self.check("keys-fails")
        messages = " ".join(finding.message for finding in found if finding.rule == plan_check.LOCAL_AUTH)
        for expected in ("shared_access_key_enabled", "admin_enabled", "apiKeyOnly", "disableLocalAuth"):
            self.assertIn(expected, messages)
        self.assertIn("allow_nested_items_to_be_public", " ".join(finding.message for finding in found))

    def test_public_ip_addresses_fail(self):
        found = self.check("public-ip-fails")
        public = {finding.address for finding in found if finding.rule == plan_check.PUBLIC_IP}
        self.assertEqual(
            {
                "module.knowledge_search.azurerm_public_ip.front_door",
                "module.knowledge_search.azapi_resource.prefix",
                "module.knowledge_search.azurerm_network_interface.worker",
            },
            public,
        )

    def test_roles_beyond_the_manifests_list_fail(self):
        found = [finding for finding in self.check("extra-role-fails") if finding.rule == plan_check.ROLE_ASSIGNMENT]
        self.assertEqual(
            [
                "module.knowledge_search.azurerm_role_assignment.writer",
                "module.knowledge_search.azurerm_role_assignment.reader_on_service",
                "module.knowledge_search.azurerm_role_assignment.owner_on_subscription",
                "module.knowledge_search.azurerm_role_assignment.reader_for_a_person",
            ],
            [finding.address for finding in found],
        )

    def test_values_unknown_until_apply_fail(self):
        found = self.check("unknown-value-fails")
        unknown = [finding for finding in found if finding.rule == plan_check.UNKNOWN_VALUE]
        self.assertEqual(
            {
                "module.knowledge_search.azurerm_role_assignment.search_index_reader",
                "module.knowledge_search.azapi_resource.unchecked",
                "module.knowledge_search.azurerm_storage_account.documents",
            },
            {finding.address for finding in unknown},
        )

    def test_destroying_the_platforms_search_service_fails(self):
        found = self.check("destroys-the-search-service-fails")
        self.assertEqual([plan_check.RESOURCE_TYPE], rules(found))
        self.assertEqual(["azurerm_search_service.platform"], [finding.address for finding in found])

    def test_every_fixture_is_covered_here(self):
        covered = {
            "knowledge-search-passes",
            "knowledge-search-teardown-passes",
            "public-access-fails",
            "keys-fails",
            "public-ip-fails",
            "extra-role-fails",
            "unknown-value-fails",
            "destroys-the-search-service-fails",
        }
        self.assertEqual(covered, {path.stem for path in PLANS.glob("*.json")})

    def test_a_fixture_named_for_failing_fails_and_one_named_for_passing_passes(self):
        for path in sorted(PLANS.glob("*.json")):
            expected_pass = path.stem.endswith("-passes")
            self.assertEqual(
                expected_pass, not self.check(path.stem), f"{path.name} should {'pass' if expected_pass else 'fail'}"
            )


class WhatIsChecked(unittest.TestCase):
    def test_changes_that_touch_nothing_are_ignored(self):
        plan = plan_of(
            change("azurerm_search_service.a", "azurerm_search_service", {"public_network_access_enabled": True},
                   actions=("no-op",)),
            change("data.azurerm_search_service.a", "azurerm_search_service", {"public_network_access_enabled": True},
                   actions=("read",), mode="data"),
        )
        self.assertEqual([], findings(plan))

    def test_a_type_outside_the_manifest_fails_even_with_nothing_guarded(self):
        found = findings(plan_of(change("azurerm_resource_group.rg", "azurerm_resource_group", {"name": "rg"})))
        self.assertEqual([plan_check.RESOURCE_TYPE], rules(found))

    def test_resource_type_names_match_without_regard_to_case(self):
        self.assertEqual([], findings(plan_of(role_assignment()), terraform=allow("AzureRM_Role_Assignment")))

    def test_azapi_resources_are_checked_by_their_azure_type(self):
        plan = plan_of(change("azapi_resource.search", "azapi_resource", {"type": "Microsoft.Search/searchServices@2025-05-01", "body": {}}))
        self.assertIn("Microsoft.Search/searchServices isn't in", findings(plan)[0].message)
        allowed = findings(plan, terraform=allow("Microsoft.Search/searchServices"))
        self.assertEqual([], allowed)

    def test_a_deleted_resource_must_still_be_a_listed_type_but_isnt_read_for_guardrails(self):
        deleted = change("azurerm_role_assignment.old", "azurerm_role_assignment", None, actions=("delete",),
                         before={"role_definition_id": f"{SUBSCRIPTION}/providers/Microsoft.Authorization/roleDefinitions/{CONTRIBUTOR_ID}"})
        self.assertEqual([], findings(plan_of(deleted)))
        other = change("azurerm_storage_account.old", "azurerm_storage_account", None, actions=("delete",),
                       before={"public_network_access_enabled": True})
        self.assertEqual([plan_check.RESOURCE_TYPE], rules(findings(plan_of(other))))

    def test_a_replacement_is_checked_as_a_create(self):
        replaced = role_assignment(scope=SUBSCRIPTION)
        replaced["change"]["actions"] = ["delete", "create"]
        self.assertEqual([plan_check.ROLE_ASSIGNMENT], rules(findings(plan_of(replaced))))

    def test_nested_settings_are_found_at_any_depth(self):
        plan = plan_of(change("azurerm_search_service.deep", "azurerm_search_service",
                              {"nested": [{"network_rules": [{"default_action": "Allow"}]}]}))
        found = findings(plan, terraform=allow("azurerm_search_service"))
        self.assertEqual([plan_check.PUBLIC_ACCESS], rules(found))
        self.assertIn("nested.0.network_rules.0.default_action", found[0].message)

    def test_closed_settings_pass(self):
        after = {
            "public_network_access_enabled": False,
            "local_authentication_enabled": False,
            "shared_access_key_enabled": False,
            "admin_enabled": False,
            "default_action": "Deny",
            "ip_rules": [],
            "public_ip_address_id": None,
        }
        plan = plan_of(change("azurerm_search_service.closed", "azurerm_search_service", after))
        self.assertEqual([], findings(plan, terraform=allow("azurerm_search_service")))

    def test_a_guarded_value_that_becomes_known_later_fails(self):
        plan = plan_of(change("azurerm_search_service.late", "azurerm_search_service", {}, unknown={"public_network_access_enabled": True}))
        self.assertEqual([plan_check.UNKNOWN_VALUE], rules(findings(plan, terraform=allow("azurerm_search_service"))))

    def test_an_empty_unknown_list_isnt_unknown(self):
        plan = plan_of(change("azurerm_search_service.x", "azurerm_search_service", {"ip_rules": []}, unknown={"ip_rules": []}))
        self.assertEqual([], findings(plan, terraform=allow("azurerm_search_service")))


class WhatThePlanCantShow(unittest.TestCase):
    ARM_ANY = allow("Microsoft.Network/networkInterfaces", "Microsoft.Search/searchServices",
                    "Microsoft.Storage/storageAccounts/blobServices/containers", "azurerm_nat_gateway_public_ip_prefix_association")

    def azapi(self, arm_type, body, *, unknown=None, **extra):
        after = {"type": f"{arm_type}@2024-01-01", "name": "x", "parent_id": "/x", "body": body, **extra}
        return plan_of(change("azapi_resource.x", "azapi_resource", after, unknown=unknown))

    def test_a_write_only_azapi_body_fails_because_the_plan_hides_what_it_sends(self):
        plan = self.azapi("Microsoft.Search/searchServices", {}, sensitive_body=None,
                          sensitive_body_version={"properties.publicNetworkAccess": "1"})
        found = findings(plan, terraform=self.ARM_ANY)
        self.assertEqual([plan_check.UNKNOWN_VALUE], rules(found))
        self.assertIn("sensitive_body_version", found[0].message)
        plan = self.azapi("Microsoft.Search/searchServices", {}, sensitive_body={"properties": {"publicNetworkAccess": "Enabled"}})
        self.assertEqual([plan_check.PUBLIC_ACCESS, plan_check.UNKNOWN_VALUE], rules(findings(plan, terraform=self.ARM_ANY)))

    def test_a_block_that_is_unknown_as_a_whole_fails(self):
        plan = self.azapi("Microsoft.Search/searchServices", {}, unknown={"body": {"properties": True}})
        self.assertEqual([plan_check.UNKNOWN_VALUE], rules(findings(plan, terraform=self.ARM_ANY)))
        plan = plan_of(change("azurerm_search_service.s", "azurerm_search_service", {"name": "s"}, unknown={"network_rules": True}))
        self.assertEqual([plan_check.UNKNOWN_VALUE], rules(findings(plan, terraform=allow("azurerm_search_service"))))

    def test_a_partly_unknown_azapi_body_passes_when_the_unknown_part_isnt_guarded(self):
        plan = self.azapi("Microsoft.Search/searchServices", {"properties": {"publicNetworkAccess": "Disabled"}},
                          unknown={"body": {"properties": {"partitionCount": True}}})
        self.assertEqual([], findings(plan, terraform=self.ARM_ANY))

    def test_azure_style_public_ip_and_anonymous_access_settings_fail(self):
        interface = self.azapi("Microsoft.Network/networkInterfaces", {"properties": {"ipConfigurations": [
            {"name": "c", "properties": {"publicIPAddress": {"id": "/subscriptions/0/providers/Microsoft.Network/publicIPAddresses/p"}}}]}})
        self.assertEqual([plan_check.PUBLIC_IP], rules(findings(interface, terraform=self.ARM_ANY)))
        container = self.azapi("Microsoft.Storage/storageAccounts/blobServices/containers", {"properties": {"publicAccess": "Blob"}})
        self.assertEqual([plan_check.PUBLIC_ACCESS], rules(findings(container, terraform=self.ARM_ANY)))
        closed = self.azapi("Microsoft.Storage/storageAccounts/blobServices/containers", {"properties": {"publicAccess": "None"}})
        self.assertEqual([], findings(closed, terraform=self.ARM_ANY))
        prefix = plan_of(change("azurerm_nat_gateway_public_ip_prefix_association.x", "azurerm_nat_gateway_public_ip_prefix_association",
                                {"public_ip_prefix_id": "/subscriptions/0/providers/Microsoft.Network/publicIPPrefixes/p"}))
        self.assertEqual([plan_check.PUBLIC_IP], rules(findings(prefix, terraform=self.ARM_ANY)))

    def test_actions_deferred_changes_and_incomplete_plans_fail(self):
        action = {"address": "action.azapi_resource_action.grant", "type": "azapi_resource_action"}
        for name, top_level in (
            ("action_invocations", {"action_invocations": [action]}),
            ("deferred_changes", {"deferred_changes": [{"resource_change": {"address": "azurerm_public_ip.p"}}]}),
            ("deferred_action_invocations", {"deferred_action_invocations": [action]}),
            ("incomplete", {"complete": False}),
            ("errored", {"errored": True}),
        ):
            with self.subTest(name):
                self.assertEqual([plan_check.UNKNOWN_VALUE], rules(findings(plan_of(role_assignment(), **top_level))))

    def test_a_plan_that_says_it_is_complete_with_no_actions_passes(self):
        plan = plan_of(role_assignment(), complete=True, errored=False, action_invocations=[], deferred_changes=[])
        self.assertEqual([], findings(plan))

    def test_an_azapi_body_is_checked_only_for_what_it_sets(self):
        # The plan shows an azapi body as written, not the service's defaults, so listing an azapi type in
        # resource_types is a decision for a person who has read that type's defaults.
        plan = self.azapi("Microsoft.Search/searchServices", {"sku": {"name": "basic"}})
        self.assertEqual([], findings(plan, terraform=self.ARM_ANY))


class RoleAssignments(unittest.TestCase):
    def test_the_listed_role_at_the_listed_scope_passes(self):
        self.assertEqual([], findings(plan_of(role_assignment())))

    def test_an_azapi_role_assignment_is_held_to_the_same_list(self):
        self.assertEqual([], findings(plan_of(azapi_role_assignment()), terraform=allow("Microsoft.Authorization/roleAssignments")))
        wrong = azapi_role_assignment(roleDefinitionId=f"{SUBSCRIPTION}/providers/Microsoft.Authorization/roleDefinitions/{CONTRIBUTOR_ID}")
        found = findings(plan_of(wrong), terraform=allow("Microsoft.Authorization/roleAssignments"))
        self.assertEqual([plan_check.ROLE_ASSIGNMENT], rules(found))

    def test_a_role_named_instead_of_identified_must_be_listed_by_name(self):
        named = role_assignment(role_definition_id=None, role_definition_name="search index data reader")
        self.assertEqual([], findings(plan_of(named)))
        owner = role_assignment(role_definition_id=None, role_definition_name="Owner")
        self.assertEqual([plan_check.ROLE_ASSIGNMENT], rules(findings(plan_of(owner))))

    def test_the_scope_must_have_the_listed_shape(self):
        for scope in (SERVICE, SUBSCRIPTION, f"{SERVICE}/indexes/a/documents/b", f"{SUBSCRIPTION}/resourceGroups/rg"):
            with self.subTest(scope=scope):
                self.assertEqual([plan_check.ROLE_ASSIGNMENT], rules(findings(plan_of(role_assignment(scope=scope)))))

    def test_a_role_listed_without_a_child_is_allowed_on_the_resource_only(self):
        roles = [{**package()["roles"][0], "scope": {"type": "Microsoft.Search/searchServices"}}]
        self.assertEqual([], findings(plan_of(role_assignment(scope=SERVICE)), roles=roles))
        self.assertEqual([plan_check.ROLE_ASSIGNMENT], rules(findings(plan_of(role_assignment()), roles=roles)))

    def test_the_principal_type_must_match(self):
        for principal_type in ("User", "Group", None):
            with self.subTest(principal_type=principal_type):
                found = findings(plan_of(role_assignment(principal_type=principal_type)))
                self.assertEqual([plan_check.ROLE_ASSIGNMENT], rules(found))

    def test_an_add_on_that_lists_no_roles_allows_none(self):
        self.assertEqual([plan_check.ROLE_ASSIGNMENT], rules(findings(plan_of(role_assignment()), roles=[])))

    def test_an_unset_role_or_scope_fails(self):
        for missing in ("scope", "role_definition_id"):
            with self.subTest(missing=missing):
                found = findings(plan_of(role_assignment(**{missing: None})))
                self.assertEqual([plan_check.UNKNOWN_VALUE], rules(found))


class CommandLine(unittest.TestCase):
    def run_main(self, arguments, *, stdin=None, directory=ADDONS_DIRECTORY):
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            if stdin is None:
                status = plan_check.main(arguments, directory)
            else:
                with mock.patch("sys.stdin", io.StringIO(stdin)):
                    status = plan_check.main(arguments, directory)
        return status, output.getvalue(), errors.getvalue()

    def test_a_passing_plan_exits_zero_and_says_a_person_approves(self):
        status, output, _ = self.run_main(["knowledge-search", str(PLANS / "knowledge-search-passes.json")])
        self.assertEqual(0, status)
        self.assertIn("approves nothing", output)
        self.assertIn("a person reads the saved plan, approves it, and runs the apply", output)

    def test_a_failing_plan_exits_one_and_names_each_finding(self):
        status, output, _ = self.run_main(["knowledge-search", str(PLANS / "public-access-fails.json")])
        self.assertEqual(1, status)
        self.assertRegex(output, r"FAIL module\.knowledge_search\.azurerm_search_service\.copy: \[public-network-access\]")
        self.assertIn("This check approves nothing.", output)

    def test_the_plan_can_come_from_standard_input(self):
        text = (PLANS / "knowledge-search-passes.json").read_text(encoding="utf-8")
        self.assertEqual(0, self.run_main(["knowledge-search", "-"], stdin=text)[0])
        text = (PLANS / "public-access-fails.json").read_text(encoding="utf-8")
        self.assertEqual(1, self.run_main(["knowledge-search", "-"], stdin=text)[0])

    def test_input_that_isnt_a_plan_exits_two(self):
        state = {"format_version": "1.0", "terraform_version": "1.16.4", "values": {"root_module": {}}}
        for text in ("not json", "[]", "{}", json.dumps({"format_version": "0.1", "planned_values": {}}), json.dumps(state),
                     json.dumps({"format_version": "1.2", "planned_values": {}, "resource_changes": {}}),
                     json.dumps(plan_of({"address": "x"}))):
            with self.subTest(text=text):
                status, output, errors = self.run_main(["knowledge-search", "-"], stdin=text)
                self.assertEqual(2, status)
                self.assertIn("Can't check the plan", errors)
                self.assertEqual("", output)

    def test_a_missing_file_exits_two(self):
        status, _, errors = self.run_main(["knowledge-search", str(PLANS / "nope.json")])
        self.assertEqual(2, status)
        self.assertIn("Can't check the plan", errors)

    def test_an_unknown_add_on_exits_two_and_lists_the_real_ones(self):
        status, _, errors = self.run_main(["nope", str(PLANS / "knowledge-search-passes.json")])
        self.assertEqual(2, status)
        self.assertIn("knowledge-search", errors)

    def test_an_add_on_without_a_package_exits_two(self):
        status, _, errors = self.run_main(["web-search", str(PLANS / "knowledge-search-passes.json")])
        self.assertEqual(2, status)
        self.assertIn("no deployment package", errors)

    def test_a_broken_manifest_exits_two_naming_the_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary) / "sample"
            folder.mkdir()
            (folder / "addon.json").write_text("{}", encoding="utf-8")
            status, _, errors = self.run_main(["sample", "-"], stdin="{}", directory=Path(temporary))
        self.assertEqual(2, status)
        self.assertIn("addon.json", errors)


class ThePilotPackageMatchesItsModule(unittest.TestCase):
    """The manifest and the Terraform module state the same grant, so a plan from the module can pass."""

    def setUp(self):
        self.package = knowledge_search().package
        self.module = ADDONS_DIRECTORY / "knowledge-search" / self.package["terraform"]["module"]

    def test_the_module_grants_the_manifests_role_at_the_manifests_scope(self):
        main = (self.module / "main.tf").read_text(encoding="utf-8")
        role = self.package["roles"][0]
        self.assertIn(role["role_id"], main)
        self.assertRegex(main, rf'principal_type\s+= "{role["principal_type"]}"')
        self.assertIn('"${var.search_service_id}/indexes/${var.index_name}"', main)
        self.assertEqual("indexes", role["scope"]["child"])

    def test_the_module_declares_only_the_manifests_resource_types(self):
        declared = set(re.findall(r'^resource\s+"([^"]+)"', "\n".join(path.read_text(encoding="utf-8")
                                                                         for path in self.module.glob("*.tf")), re.M))
        self.assertEqual(set(self.package["terraform"]["resource_types"]), declared)

    def test_the_manifests_guardrails_are_the_fixed_ones(self):
        self.assertEqual(GUARDRAILS, self.package["guardrails"])

    def test_the_fixtures_dont_share_state_between_checks(self):
        plan = read_plan("knowledge-search-passes")
        before = copy.deepcopy(plan)
        plan_check.check_plan(plan, self.package)
        self.assertEqual(before, plan)


if __name__ == "__main__":
    unittest.main()

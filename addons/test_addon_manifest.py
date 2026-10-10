import json
import tempfile
import unittest
from pathlib import Path

import build_catalog
import check_addons
from addon_manifest import ADDONS_DIRECTORY, GUARDRAILS, RUNBOOK_HEADINGS, AddOnFileError, load_add_ons

RUNBOOK = "# Deploy\n\nA person approves the saved plan.\n\n" + "".join(f"## {heading}\n\nText.\n\n" for heading in RUNBOOK_HEADINGS)


def card(**changes):
    value = {
        "icon": "search",
        "group": "abilities",
        "summary": "Lets an agent find things.",
        "example": "It finds a passage.",
        "cost": ["Billed by the hour."],
        "needs": ["A service."],
        "safety": "Read-only.",
        "service": "Azure AI Search",
        "billing": "Per hour.",
    }
    value.update(changes)
    return value


def package(**changes):
    value = {
        "runbook": "DEPLOY.md",
        "bootstrap": "bootstrap.md",
        "acceptance_case": "acceptance.json",
        "terraform": {"module": "terraform", "resource_types": ["azurerm_role_assignment"]},
        "approval": "person-approves-saved-plan",
        "approval_gates": ["billable-calls"],
        "roles": [{"role": "Search Index Data Reader", "role_id": "1407120a-92aa-4202-b7e9-c0e197c71c8f",
                   "principal_type": "ServicePrincipal",
                   "scope": {"type": "Microsoft.Search/searchServices", "child": "indexes"}}],
        "cost_lines": [{"name": "Role assignment", "monthly_cost": 0, "basis": "Role assignments have no charge."}],
        "guardrails": dict(GUARDRAILS),
    }
    value.update(changes)
    return value


def manifest(identifier="sample", **changes):
    value = {"schema_version": 1, "id": identifier, "name": "Sample", "order": 1, "kind": "existing-service",
             "tracking": [54], "card": card()}
    value.update(changes)
    return value


class TemporaryAddOns(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def add(self, identifier="sample", document=None, *, files=True, raw=None):
        folder = self.root / identifier
        folder.mkdir(exist_ok=True)
        document = manifest(identifier) if document is None else document
        (folder / "addon.json").write_text(raw if raw is not None else json.dumps(document), encoding="utf-8")
        if files:
            (folder / "DEPLOY.md").write_text(RUNBOOK, encoding="utf-8")
            (folder / "bootstrap.md").write_text("Notes.\n", encoding="utf-8")
            (folder / "acceptance.json").write_text(json.dumps({
                "schema_version": 1, "add_on": identifier,
                "cases": [{"id": "offline", "summary": "s", "live": False, "steps": ["a"], "expect": ["b"]},
                          {"id": "live", "summary": "s", "live": True, "steps": ["a"], "expect": ["b"]}]}),
                encoding="utf-8")
            (folder / "terraform").mkdir(exist_ok=True)
            (folder / "terraform" / "main.tf").write_text("# module\n", encoding="utf-8")
        return folder

    def rejects(self, message):
        with self.assertRaises(AddOnFileError) as raised:
            load_add_ons(self.root)
        self.assertIn(message, str(raised.exception))
        return str(raised.exception)


class ManifestShapeTests(TemporaryAddOns):
    def test_reads_a_card_only_manifest_and_a_package(self):
        self.add("sample")
        self.add("other", manifest("other", order=2, package=package()))
        sample, other = load_add_ons(self.root)
        self.assertEqual((sample.id, sample.package), ("sample", None))
        self.assertEqual(other.package["roles"][0]["role"], "Search Index Data Reader")

    def test_lists_add_ons_in_tab_order(self):
        self.add("zebra", manifest("zebra", order=1))
        self.add("apple", manifest("apple", order=2))
        self.assertEqual([item.id for item in load_add_ons(self.root)], ["zebra", "apple"])

    def test_an_error_names_the_file(self):
        self.add("sample", manifest("sample", kind="cloud"))
        self.assertTrue(self.rejects("unknown kind").startswith("sample/addon.json: "))

    def test_rejects_unknown_and_missing_fields(self):
        self.add("sample", {**manifest("sample"), "price": 1})
        self.rejects("the file has unknown field price")
        self.add("sample", {key: value for key, value in manifest("sample").items() if key != "kind"})
        self.rejects("the file is missing kind")
        self.add("sample", manifest("sample", card=card(colour="red")))
        self.rejects("card has unknown field colour")
        self.add("sample", manifest("sample", card={key: value for key, value in card().items() if key != "safety"}))
        self.rejects("card is missing safety")

    def test_rejects_a_repeated_key(self):
        self.add("sample", raw='{"id": "sample", "id": "sample"}')
        self.rejects("a key appears twice")

    def test_rejects_invalid_json_and_a_missing_manifest_set(self):
        self.add("sample", raw="{")
        self.rejects("sample/addon.json: ")
        with tempfile.TemporaryDirectory() as empty, self.assertRaises(AddOnFileError):
            load_add_ons(empty)

    def test_the_id_must_match_the_folder_and_be_lowercase_words(self):
        self.add("sample", manifest("other"))
        self.rejects("id must match the folder name")
        self.add("sample", manifest("Sample"))
        self.rejects("id must be lowercase words joined by hyphens")

    def test_checks_each_value(self):
        for changes, message in (
            ({"schema_version": 2}, "schema_version must be 1"),
            ({"order": 0}, "order must be a whole number"),
            ({"order": True}, "order must be a whole number"),
            ({"name": " "}, "name must be non-empty text"),
            ({"tracking": []}, "tracking must list"),
            ({"tracking": [54, 54]}, "tracking lists an issue twice"),
            ({"card": card(icon="robot")}, "unknown icon"),
            ({"card": card(group="extras")}, "unknown group"),
            ({"card": card(cost=[])}, "card cost must be a non-empty list"),
            ({"card": card(needs=[1])}, "card needs entries must be non-empty text"),
            ({"card": card(approval="")}, "card approval must be non-empty text"),
        ):
            with self.subTest(message):
                self.add("sample", manifest("sample", **changes))
                self.rejects(message)

    def test_rejects_two_add_ons_with_the_same_order(self):
        self.add("first")
        self.add("second", manifest("second"))
        self.rejects("second/addon.json: order 1 is already used by first")


class PackageTests(TemporaryAddOns):
    def with_package(self, **changes):
        self.add("sample", manifest("sample", package=package(**changes)))

    def test_accepts_a_complete_package(self):
        self.with_package()
        self.assertEqual(load_add_ons(self.root)[0].package["approval"], "person-approves-saved-plan")

    def test_a_package_may_grant_nothing(self):
        self.with_package(roles=[])
        self.assertEqual(load_add_ons(self.root)[0].package["roles"], [])

    def test_files_must_sit_in_the_add_on_folder(self):
        for name in ("../other/DEPLOY.md", "sub/DEPLOY.md", "/etc/passwd", "..", ""):
            with self.subTest(name):
                self.with_package(runbook=name)
                self.rejects("runbook must be a file name without a folder")
        self.with_package(runbook="MISSING.md")
        self.rejects("runbook names MISSING.md, which is not in sample/")

    def test_the_runbook_needs_every_section_and_a_person_approving_the_plan(self):
        self.with_package()
        folder = self.root / "sample"
        (folder / "DEPLOY.md").write_text(RUNBOOK.replace("## Tear down", "## Later"), encoding="utf-8")
        self.assertEqual(self.rejects('the runbook is missing the section "Tear down"'),
                         'sample/DEPLOY.md: the runbook is missing the section "Tear down"')
        (folder / "DEPLOY.md").write_text(RUNBOOK.replace("approves the saved plan", "applies"), encoding="utf-8")
        self.rejects("the runbook must say that a person approves the saved plan")

    def test_the_acceptance_case_names_the_add_on_and_has_an_offline_case(self):
        self.with_package()
        path = self.root / "sample" / "acceptance.json"
        document = json.loads(path.read_text(encoding="utf-8"))
        for changes, message in (
            ({"add_on": "other"}, "add_on must be sample"),
            ({"cases": []}, "cases must be a non-empty list"),
            ({"cases": [document["cases"][1]]}, "at least one case must run without a deployed add-on"),
            ({"cases": [document["cases"][0], document["cases"][0]]}, "two cases share an id"),
            ({"extra": 1}, "unknown field extra"),
        ):
            with self.subTest(message):
                path.write_text(json.dumps({**document, **changes}), encoding="utf-8")
                self.assertTrue(self.rejects(message).startswith("sample/acceptance.json: "))

    def test_the_terraform_module_needs_tf_files_and_known_resource_types(self):
        self.with_package()
        (self.root / "sample" / "terraform" / "main.tf").unlink()
        self.rejects("terraform module terraform has no .tf files")
        for types in (["role_assignment"], ["Microsoft.Search"], ["azurerm_role_assignment"] * 2, []):
            with self.subTest(types):
                self.add("sample", manifest("sample", package=package(
                    terraform={"module": "terraform", "resource_types": types})))
                self.rejects("resource_types")

    def test_a_package_cannot_loosen_a_guardrail_or_hand_the_plan_to_an_agent(self):
        for changes, message in (
            ({"guardrails": {**GUARDRAILS, "public_network_access": "enabled"}}, "guardrails must be exactly"),
            ({"guardrails": {"public_network_access": "disabled"}}, "guardrails must be exactly"),
            ({"approval": "agent-applies-plan"}, "an agent never applies a plan"),
            ({"approval_gates": ["public-access"]}, "approval_gates must list"),
            ({"approval_gates": ["billable-calls"] * 2}, "approval_gates must list"),
        ):
            with self.subTest(message):
                self.with_package(**changes)
                self.rejects(message)

    def test_checks_roles_and_cost_lines(self):
        good_role = package()["roles"][0]
        for changes, message in (
            ({"roles": [{**good_role, "role_id": "READER"}]}, "role_id must be a lowercase role definition GUID"),
            ({"roles": [{**good_role, "principal_type": "User"}]}, "unknown principal_type"),
            ({"roles": [{**good_role, "scope": {"type": "searchServices"}}]}, "role scope type must be an Azure resource type"),
            ({"roles": [{**good_role, "scope": {"type": "Microsoft.Search/searchServices", "child": "A b"}}]},
             "role scope child"),
            ({"roles": [good_role, good_role]}, "two roles are the same"),
            ({"roles": [{"role": "x"}]}, "a role is missing"),
            ({"cost_lines": []}, "cost_lines must be a non-empty list"),
            ({"cost_lines": [{"name": "x", "monthly_cost": -1, "basis": "b"}]}, "monthly_cost must be a number of 0 or more"),
            ({"cost_lines": [{"name": "x", "quantity": 1, "unit_rate": 1, "basis": "b"}]}, "a cost line is missing unit"),
            ({"cost_lines": [{"name": "x", "monthly_cost": 1, "basis": " "}]}, "a cost line basis must be non-empty text"),
        ):
            with self.subTest(message):
                self.with_package(**changes)
                self.rejects(message)

    def test_a_cost_line_may_price_by_quantity(self):
        self.with_package(cost_lines=[{"name": "Reads", "quantity": 1000, "unit_rate": 0.001, "unit": "read",
                                       "basis": "Price list."}])
        self.assertEqual(len(load_add_ons(self.root)[0].package["cost_lines"]), 1)


class CatalogTests(TemporaryAddOns):
    def test_renders_the_cards_in_tab_order_with_the_page_s_field_order(self):
        self.add("first", manifest("first", name="First", order=2, card=card(note="N", pilot="P", approval="A")))
        self.add("second", manifest("second", name="Second", order=1))
        entries = json.loads(build_catalog.render(load_add_ons(self.root)))["add_ons"]
        self.assertEqual([entry["id"] for entry in entries], ["second", "first"])
        self.assertEqual(list(entries[1]), ["id", "name", "icon", "group", "summary", "example", "pilot", "cost",
                                            "needs", "safety", "approval", "service", "billing", "note"])

    def test_notices_a_stale_or_missing_catalog(self):
        self.add("sample")
        add_ons = load_add_ons(self.root)
        path = self.root / "catalog.json"
        self.assertFalse(build_catalog.is_current(add_ons, path))
        path.write_text(build_catalog.render(add_ons), encoding="utf-8")
        self.assertTrue(build_catalog.is_current(add_ons, path))
        path.write_text(path.read_text(encoding="utf-8").replace("Sample", "Changed"), encoding="utf-8")
        self.assertFalse(build_catalog.is_current(add_ons, path))


class CheckAddOnsTests(TemporaryAddOns):
    def setUp(self):
        super().setUp()
        original = check_addons.ADDONS_DIRECTORY, build_catalog.CATALOG_PATH
        check_addons.ADDONS_DIRECTORY, build_catalog.CATALOG_PATH = self.root, self.root / "catalog.json"
        self.addCleanup(lambda: (setattr(check_addons, "ADDONS_DIRECTORY", original[0]),
                                 setattr(build_catalog, "CATALOG_PATH", original[1])))

    def test_a_folder_without_a_manifest_is_reported(self):
        self.add("sample")
        (self.root / "forgotten").mkdir()
        (self.root / "testdata").mkdir()
        found = check_addons.problems()[0]
        self.assertIn("forgotten/: no addon.json", found)
        self.assertFalse(any("testdata" in problem for problem in found))

    def test_a_missing_or_stale_catalog_is_reported(self):
        self.add("sample")
        found = check_addons.problems()[0]
        self.assertEqual(len(found), 1)
        self.assertIn("out of date", found[0])
        build_catalog.CATALOG_PATH.write_text(build_catalog.render(load_add_ons(self.root)), encoding="utf-8")
        self.assertEqual(check_addons.problems()[0], [])

    def test_a_bad_manifest_is_reported_with_its_file(self):
        self.add("sample", manifest("sample", kind="cloud"))
        self.assertEqual(check_addons.problems()[0], ["sample/addon.json: unknown kind 'cloud'"])

class RepositoryManifestTests(unittest.TestCase):
    def test_the_repository_s_add_ons_are_valid_and_listed_in_tab_order(self):
        add_ons = load_add_ons(ADDONS_DIRECTORY)
        self.assertEqual([item.id for item in add_ons], ["knowledge-search", "conversation-memory",
                                                         "document-extraction", "notifications",
                                                         "code-interpreter", "web-search",
                                                         "document-storage", "response-cache"])
        self.assertEqual([item.order for item in add_ons], list(range(1, 9)))
        self.assertEqual([item.id for item in add_ons if item.card["group"] == "support"],
                         ["conversation-memory", "document-storage", "response-cache"])

    def test_the_frontend_catalog_matches_the_manifests(self):
        self.assertTrue(build_catalog.is_current(load_add_ons(ADDONS_DIRECTORY), build_catalog.CATALOG_PATH),
                        "Run: python addons/build_catalog.py --write")

    def test_the_check_finds_nothing_to_fix(self):
        self.assertEqual(check_addons.problems()[0], [])


if __name__ == "__main__":
    unittest.main()

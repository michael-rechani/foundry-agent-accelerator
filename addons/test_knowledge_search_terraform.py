import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TERRAFORM = ROOT / "addons" / "knowledge-search" / "terraform"
VARIABLES = (TERRAFORM / "variables.tf").read_text(encoding="utf-8")
MAIN = (TERRAFORM / "main.tf").read_text(encoding="utf-8")
EXPECTED_TESTS = 11
READER_ROLE_ID = "1407120a-92aa-4202-b7e9-c0e197c71c8f"
SUBSCRIPTION_ID = "00000000-0000-0000-0000-000000000000"
SERVICE_ID = (
    f"/subscriptions/{SUBSCRIPTION_ID}/resourceGroups/rg-example/"
    "providers/Microsoft.Search/searchServices/search-example"
)


def named_block(source, header):
    match = re.search(rf"(?ms)^{re.escape(header)}\s*\{{(?P<body>.*?)^\}}", source)
    if match is None:
        raise AssertionError(f"Terraform block not found: {header}")
    return match.group("body")


def validation_pattern(variable_name):
    block = named_block(VARIABLES, f'variable "{variable_name}"')
    match = re.search(
        rf'condition\s*=\s*can\(regex\("([^"]+)"\s*,\s*var\.{re.escape(variable_name)}\)\)',
        block,
    )
    if match is None:
        raise AssertionError(f"Validation regex not found for {variable_name}")
    return re.compile(json.loads(f'"{match.group(1)}"'))


def assignment_field(name):
    block = named_block(MAIN, 'resource "azurerm_role_assignment" "search_index_reader"')
    match = re.search(rf"(?m)^\s*{re.escape(name)}\s*=\s*(.+?)\s*$", block)
    if match is None:
        raise AssertionError(f"Role assignment field not found: {name}")
    return match.group(1)


class KnowledgeSearchTerraformContractTests(unittest.TestCase):
    def test_role_assignment_uses_the_search_index_data_reader_role(self):
        self.assertEqual(
            f'"/subscriptions/${{local.subscription_id}}/providers/Microsoft.Authorization/roleDefinitions/{READER_ROLE_ID}"',
            assignment_field("role_definition_id"),
        )

    def test_role_assignment_is_limited_to_a_single_index(self):
        self.assertEqual(
            '"${var.search_service_id}/indexes/${var.index_name}"',
            assignment_field("scope"),
        )

    def test_role_assignment_requires_a_service_principal(self):
        self.assertEqual('"ServicePrincipal"', assignment_field("principal_type"))

    def test_role_assignment_normalizes_the_supplied_principal_id(self):
        self.assertEqual("lower(var.principal_id)", assignment_field("principal_id"))

    def test_service_resource_id_accepts_a_search_service(self):
        self.assertRegex(SERVICE_ID, validation_pattern("search_service_id"))

    def test_service_resource_id_rejects_an_index_resource(self):
        self.assertNotRegex(
            f"{SERVICE_ID}/indexes/lab-sample-policy-guidance",
            validation_pattern("search_service_id"),
        )

    def test_service_resource_id_rejects_urls_and_non_search_resources(self):
        pattern = validation_pattern("search_service_id")
        for value in (
            "https://search-example.search.windows.net",
            f"/subscriptions/{SUBSCRIPTION_ID}/resourceGroups/rg-example",
        ):
            with self.subTest(value=value):
                self.assertNotRegex(value, pattern)

    def test_principal_id_accepts_a_guid(self):
        self.assertRegex(
            "11111111-1111-1111-1111-111111111111",
            validation_pattern("principal_id"),
        )

    def test_principal_id_rejects_non_guid_values(self):
        pattern = validation_pattern("principal_id")
        for value in ("client-id", "11111111-1111-1111-1111-11111111111"):
            with self.subTest(value=value):
                self.assertNotRegex(value, pattern)

    def test_index_name_accepts_the_default_and_valid_names(self):
        block = named_block(VARIABLES, 'variable "index_name"')
        default = re.search(r'(?m)^\s*default\s*=\s*"([^"]+)"', block)
        self.assertIsNotNone(default)
        pattern = validation_pattern("index_name")
        self.assertRegex(default.group(1), pattern)
        self.assertRegex("policy-v2", pattern)

    def test_index_name_rejects_paths_and_non_search_names(self):
        pattern = validation_pattern("index_name")
        for value in ("policy/index", "Policy", "-policy", ""):
            with self.subTest(value=value):
                self.assertNotRegex(value, pattern)


def load_tests(loader, standard_tests, pattern):
    suite = loader.loadTestsFromTestCase(KnowledgeSearchTerraformContractTests)
    count = suite.countTestCases()
    if count != EXPECTED_TESTS:
        raise RuntimeError(f"Expected {EXPECTED_TESTS} Terraform contract tests, discovered {count}")
    return suite


if __name__ == "__main__":
    unittest.main(verbosity=2)

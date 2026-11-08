import json
import unittest
from pathlib import Path

from test_verify_private import CustomerReviewClient
from verify_private import CUSTOMER_REVIEW_SPECIALISTS, CheckError, verify


ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "hosted-agents" / "review-coordinator-agent" / "profiles" / "evidence-review.example.json"
CATALOG = ROOT / "workbench" / "agents.json"


class ProfileVerificationContractTests(unittest.TestCase):
    def setUp(self):
        self.profile = json.loads(PROFILE.read_text(encoding="utf-8"))
        catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
        matches = [agent for agent in catalog if agent["id"] == "customer-review"]
        self.assertEqual(len(matches), 1)
        self.agent = matches[0]

    def test_profile_catalog_and_verifier_bind_the_same_specialists(self):
        specialists = self.profile["specialists"]
        profile_bindings = {item["tool"]: item["agent"] for item in specialists}
        self.assertEqual(len(profile_bindings), len(specialists))
        self.assertEqual(self.profile["name"], "customer-review-coordinator")
        self.assertEqual(self.agent["agent"], self.profile["name"])
        self.assertEqual(self.agent["tools"], profile_bindings)
        self.assertEqual(
            {(tool, target) for tool, target, _ in CUSTOMER_REVIEW_SPECIALISTS},
            set(profile_bindings.items()),
        )
        self.assertTrue(set(profile_bindings) <= {item["tool"] for item in self.profile["smoke_tests"]})

    def test_verifier_exercises_both_shipped_bindings(self):
        client = CustomerReviewClient()
        client.default_agent = self.agent["id"]
        client.agent_name = self.agent["agent"]
        client.bindings = self.agent["tools"]

        checks = verify(client, check_review_specialists=True)

        self.assertIn("customer_review_inspect_application_receipt", checks)
        self.assertIn("customer_review_inspect_case_receipt", checks)
        self.assertEqual(len(client.review_bodies), 2)
        self.assertTrue(all(body["agent_id"] == self.agent["id"] for body in client.review_bodies))

    def test_verifier_stops_before_calls_if_catalog_binding_changes(self):
        client = CustomerReviewClient()
        client.default_agent = self.agent["id"]
        client.agent_name = self.agent["agent"]
        client.bindings = {**self.agent["tools"], "inspect_case": "different-case-agent"}

        with self.assertRaises(CheckError):
            verify(client, check_review_specialists=True)

        self.assertEqual(client.review_bodies, [])


if __name__ == "__main__":
    unittest.main()

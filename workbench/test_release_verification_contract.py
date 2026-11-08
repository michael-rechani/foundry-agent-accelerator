import hashlib
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import reviewed_agent_release as release
from test_reviewed_agent_release import Metadata
from test_verify_private import CustomerReviewClient
from verify_private import CUSTOMER_REVIEW_SPECIALISTS, CheckError, verify


ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "hosted-agents" / "review-coordinator-agent" / "profiles" / "evidence-review.example.json"
CATALOG = ROOT / "workbench" / "agents.json"


class ReleaseVerificationContractTests(unittest.TestCase):
    def setUp(self):
        profile_sha = hashlib.sha256(PROFILE.read_bytes()).hexdigest()
        values = {
            "release_id": "12345678-1234-1234-1234-123456789abc",
            "endpoint": "https://fictional.services.ai.azure.com/api/projects/fictional",
            "model": "fictional-router",
            "model_choice": "router",
            "credential_mode": "ManagedIdentityCredential",
            "client_id": "22345678-1234-1234-1234-123456789abc",
            "tenant_id": "32345678-1234-1234-1234-123456789abc",
            "profile_path": str(PROFILE.relative_to(ROOT)),
            "profile_sha256": profile_sha,
            "targets": list(release.TARGETS),
            "cpu": "0.5",
            "memory": "1Gi",
            "runtime": "python_3_14",
        }
        sha = "a" * 40
        repo = "fictional-owner/fictional-repository"
        environ = {
            "GITHUB_REPOSITORY": repo,
            "GITHUB_EVENT_NAME": "workflow_dispatch",
            "GITHUB_REF": "refs/heads/main",
            "GITHUB_REF_PROTECTED": "true",
            "GITHUB_RUN_ATTEMPT": "1",
            "GITHUB_RUN_ID": "91",
            "GITHUB_SHA": sha,
            "REVIEWED_SOURCE_SHA": sha,
            "RELEASE_WORKFLOW_SHA": sha,
            "GITHUB_WORKFLOW_REF": f"{repo}/{release.WORKFLOW}@refs/heads/main",
            "AGENT_RELEASE_INPUTS": release.canonical(values),
            "RELEASE_MODEL_CHOICE": "router",
            "REVIEWED_MODEL_SHA256": release.digest(values["model"]),
        }
        ctx = release.context(environ)
        policy = release.policies(Metadata(environ), ctx)
        with patch.dict("os.environ", {}, clear=True):
            self.manifest, self.profiles = release.release_plan(
                ROOT, ctx, release.inputs(environ), policy
            )
        catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
        matches = [agent for agent in catalog if agent["id"] == "customer-review"]
        self.assertEqual(len(matches), 1)
        self.agent = matches[0]

    def client_for(self, bindings):
        client = CustomerReviewClient()
        client.default_agent = self.agent["id"]
        client.agent_name = self.agent["agent"]
        client.bindings = bindings
        return client

    def test_reviewed_archives_and_runtime_bindings_match_private_verifier(self):
        self.assertFalse(release.LIVE_PUBLICATION_ENABLED)
        descriptors = self.manifest["profiles"]
        self.assertEqual([item["stage"] for item in descriptors], list(release.STEPS))
        self.assertEqual([item["target"] for item in descriptors], list(release.TARGETS))
        for descriptor, profile in zip(descriptors, self.profiles):
            self.assertEqual(
                descriptor["archive_sha256"],
                hashlib.sha256(profile.code_archive).hexdigest(),
            )
        self.assertEqual(
            self.manifest["release_inputs"]["profile_sha256"],
            hashlib.sha256(PROFILE.read_bytes()).hexdigest(),
        )
        coordinator = descriptors[-1]
        self.assertEqual(coordinator["target"], self.agent["agent"])
        registry = json.loads(dict(coordinator["environment_variables"])["SPECIALIST_CONFIG"])
        bindings = {item["tool"]: item["agent"] for item in registry}
        self.assertEqual(len(bindings), len(registry))
        self.assertEqual(bindings, self.agent["tools"])
        self.assertEqual(
            set(bindings.items()),
            {(tool, target) for tool, target, _ in CUSTOMER_REVIEW_SPECIALISTS},
        )

        client = self.client_for(bindings)
        checks = verify(client, check_review_specialists=True)
        self.assertIn("customer_review_inspect_application_receipt", checks)
        self.assertIn("customer_review_inspect_case_receipt", checks)
        self.assertEqual(len(client.review_bodies), 2)

    def test_verifier_refuses_a_runtime_binding_that_differs_from_release(self):
        registry = json.loads(
            dict(self.manifest["profiles"][-1]["environment_variables"])["SPECIALIST_CONFIG"]
        )
        bindings = {item["tool"]: item["agent"] for item in registry}
        bindings["inspect_case"] = "different-case-agent"
        client = self.client_for(bindings)
        with self.assertRaises(CheckError):
            verify(client, check_review_specialists=True)
        self.assertEqual(client.review_bodies, [])


if __name__ == "__main__":
    unittest.main()

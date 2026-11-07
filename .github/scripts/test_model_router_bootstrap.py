"""Offline tests for the inert, fixed Model Router bootstrap proposal."""

import base64
import importlib.util
from pathlib import Path
import re
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "model_router_bootstrap", ROOT / ".github/scripts/model_router_bootstrap.py"
)
bootstrap = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bootstrap)


class TransformationTests(unittest.TestCase):
    def test_module_removes_only_the_unsubstantiated_patch(self):
        source = '''resource "azapi_resource" "model_router" {
  body = local.model_router_body
}

# Some API/provider combinations have ignored routing on PUT. Reapply it by
# PATCH, including after any deployment update, and verify it with a fresh GET.
resource "azapi_resource_action" "model_router_routing" {
  count = var.model_router_deployment == null ? 0 : 1

  type        = "Microsoft.CognitiveServices/accounts/deployments@2025-12-01"
  resource_id = azapi_resource.model_router[count.index].id
  method      = "PATCH"
  body = {
    sku = local.model_router_body.sku
    properties = {
      model   = local.model_router_body.properties.model
      routing = local.model_router_body.properties.routing
    }
  }

  lifecycle {
    replace_triggered_by = [azapi_resource.model_router[count.index]]
  }
}

data "azapi_resource" "model_router_routing" {
  resource_id = azapi_resource.model_router[0].id
  depends_on = [azapi_resource_action.model_router_routing]
}
'''
        result = bootstrap.transform_file(
            "terraform/modules/model-router/main.tf", source
        )
        self.assertIn('body = local.model_router_body', result)
        self.assertIn('data "azapi_resource" "model_router_routing"', result)
        self.assertIn("depends_on = [azapi_resource.model_router]", result)
        self.assertNotIn("azapi_resource_action", result)
        self.assertNotIn("PATCH", result)

    def test_tests_keep_the_put_body_and_strict_readback_contract(self):
        source = '''run "null_router_keeps_other_outputs" {
  condition = (
      length(azapi_resource.model_router) == 0 &&
      length(azapi_resource_action.model_router_routing) == 0 &&
      length(data.azapi_resource.model_router_routing) == 0
  )
}
run "enabled_request" {
      azapi_resource.model_router[0].body.properties.routing.mode == "balanced" &&
      azapi_resource.model_router[0].ignore_missing_property == false &&
      azapi_resource_action.model_router_routing[0].method == "PATCH" &&
      azapi_resource_action.model_router_routing[0].body.sku == azapi_resource.model_router[0].body.sku &&
      azapi_resource_action.model_router_routing[0].body.properties.model == azapi_resource.model_router[0].body.properties.model &&
      azapi_resource_action.model_router_routing[0].body.properties.routing == azapi_resource.model_router[0].body.properties.routing
  error_message = "The configured deployment must send the requested Router settings and PATCH the same settings."
}
run "standard_default_subset" {
      azapi_resource_action.model_router_routing[0].body.properties.routing.mode == "balanced" &&
  error_message = "The standard Router subset must be sent, patched, and verified before exposing its output."
}
run "plan_routing_mode_update" {
      azapi_resource.model_router[0].body.properties.routing.mode == "cost" &&
      azapi_resource_action.model_router_routing[0].body.properties.routing.mode == "cost"
  error_message = "A routing update must plan both the deployment change and the PATCH."
}
run "update_routing_mode" {
  command = apply
      azapi_resource.model_router[0].body.properties.routing.mode == "cost" &&
      azapi_resource_action.model_router_routing[0].body.properties.routing.mode == "cost" &&
      output.model_router_deployment_name == "model-router"
  error_message = "A routing change must update both the deployment and PATCH and verify the resulting mode."
}
'''
        result = bootstrap.transform_file(
            "terraform/modules/model-router/tests/model-router.tftest.hcl", source
        )
        self.assertNotIn("azapi_resource_action", result)
        self.assertNotIn("PATCH", result)
        self.assertIn('body.properties.routing.mode == "balanced"', result)
        self.assertIn('body.properties.routing.mode == "cost"', result)
        self.assertIn("azapi_resource.model_router[0].ignore_missing_property == false\n", result)
        self.assertNotIn("ignore_missing_property == false &&\n    )", result)
        self.assertIn('state_key = "standard-default-subset"', result)
        self.assertIn("verified before exposing its output", result)

    def test_documentation_preserves_unverified_behavior_and_partial_create_warning(self):
        source = '''uses a preview PUT; this module's subsequent `2025-12-01` PATCH of routing
properties has not been verified against the live service. Before approving an
apply, review a private-runner recovery path for a partial create or failed
PATCH; neither retrying nor deleting the deployment is automatically safe.
'''
        result = bootstrap.transform_file("terraform/README.md", source)
        self.assertIn("not a verified live-service fix", result)
        self.assertIn("unreproduced provider issue", result)
        self.assertIn("different or unrestricted model", result)
        self.assertIn("neither retrying nor deleting a partial", result)
        self.assertIn("strict fresh management-plane readback", result)

    def test_unrecognized_paths_and_source_shapes_fail_closed(self):
        with self.assertRaises(bootstrap.BootstrapError):
            bootstrap.transform_file("README.md", "data")
        with self.assertRaises(bootstrap.BootstrapError):
            bootstrap.transform_file("terraform/modules/model-router/main.tf", "unexpected")


class WorkflowContractTests(unittest.TestCase):
    def test_job_is_unconditionally_disabled_and_dispatch_only(self):
        workflow = (ROOT / ".github/workflows/model-router-bootstrap.yml").read_text()
        self.assertIn("  workflow_dispatch:\n", workflow)
        self.assertNotRegex(workflow, r"(?m)^  (pull_request|pull_request_target|push|schedule):")
        self.assertIn("if: ${{ false }}", workflow)
        self.assertIn("uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1", workflow)
        self.assertIn("ref: ${{ github.sha }}", workflow)
        self.assertIn("persist-credentials: false", workflow)
        self.assertIn("contents: write", workflow)
        self.assertNotIn("id-token: write", workflow)
        self.assertNotIn("environment:", workflow)
        self.assertNotIn("secrets.", workflow)
        self.assertNotIn("inputs.", workflow)

    def test_pull_request_workflows_do_not_target_private_runner(self):
        workflows = ROOT / ".github/workflows"
        triggered = []
        for path in workflows.glob("*.yml"):
            source = path.read_text()
            if re.search(r"(?m)^  pull_request(_target)?:", source):
                triggered.append(path.name)
                self.assertNotIn("self-hosted", source, path.name)
        self.assertEqual(triggered, ["validate.yml"])
        validate = (workflows / "validate.yml").read_text()
        self.assertIn("runs-on: ubuntu-24.04", validate)


class GuardAndCommitTests(unittest.TestCase):
    def test_api_requests_reject_non_github_or_non_https_urls(self):
        for url in (
            "http://api.github.com/repos/example",
            "https://example.com/repos/example",
            "file:///etc/passwd",
        ):
            with self.subTest(url=url), self.assertRaises(bootstrap.BootstrapError):
                bootstrap._request(url, "offline-token")

    def test_only_the_first_owner_dispatch_from_main_is_accepted(self):
        environ = {
            "GITHUB_REPOSITORY": bootstrap.REPOSITORY,
            "GITHUB_ACTOR_ID": bootstrap.OWNER_ID,
            "GITHUB_REF": "refs/heads/main",
            "GITHUB_EVENT_NAME": "workflow_dispatch",
            "GITHUB_RUN_NUMBER": "1",
            "GITHUB_RUN_ATTEMPT": "1",
            "GITHUB_SHA": "f" * 40,
            "GITHUB_TOKEN": "offline-token",
        }
        self.assertEqual(bootstrap._check_context(environ), "offline-token")
        for key, value in (
            ("GITHUB_ACTOR_ID", "1"),
            ("GITHUB_REF", "refs/heads/attacker"),
            ("GITHUB_EVENT_NAME", "pull_request"),
            ("GITHUB_RUN_NUMBER", "2"),
            ("GITHUB_RUN_ATTEMPT", "2"),
        ):
            altered = dict(environ, **{key: value})
            with self.subTest(key=key), self.assertRaises(bootstrap.BootstrapError):
                bootstrap._check_context(altered)

    def test_commit_uses_fixed_branch_and_compare_and_swap_head(self):
        captured = {}

        def fake_request(url, token, method="GET", body=None):
            captured.update(url=url, token=token, method=method, body=body)
            return {"data": {"createCommitOnBranch": {"commit": {
                "oid": "a" * 40,
                "url": "https://github.com/michael-rechani/foundry-agent-accelerator/commit/" + "a" * 40,
            }}}}

        with patch.object(bootstrap, "_request", side_effect=fake_request):
            commit = bootstrap._commit("offline-token", {
                "terraform/modules/model-router/main.tf": "fixed output \N{LATIN SMALL LETTER A WITH DIAERESIS}\n",
            })
        variables = captured["body"]["variables"]["input"]
        self.assertEqual(captured["method"], "POST")
        self.assertEqual(variables["expectedHeadOid"], bootstrap.TARGET_HEAD)
        self.assertEqual(variables["branch"]["branchName"], bootstrap.TARGET_BRANCH)
        self.assertEqual(variables["branch"]["repositoryNameWithOwner"], bootstrap.REPOSITORY)
        additions = variables["fileChanges"]["additions"]
        self.assertEqual(len(additions), 1)
        self.assertEqual(additions[0]["path"], "terraform/modules/model-router/main.tf")
        self.assertEqual(
            base64.b64decode(additions[0]["contents"], validate=True).decode("utf-8"),
            "fixed output \N{LATIN SMALL LETTER A WITH DIAERESIS}\n",
        )
        self.assertEqual(variables["fileChanges"]["deletions"], [])
        self.assertEqual(
            variables["message"]["body"],
            "Co-authored-by: Copilot App <223556219+Copilot@users.noreply.github.com>",
        )
        self.assertEqual(commit["oid"], "a" * 40)

    def test_target_identity_and_source_blobs_are_fixed(self):
        self.assertEqual(bootstrap.TARGET_PR, 523)
        self.assertEqual(bootstrap.TARGET_HEAD, "52fab5e08fb498720efcd53f0f389f424d671a46")
        self.assertEqual(set(bootstrap.EXPECTED_FILES), {
            "terraform/modules/model-router/main.tf",
            "terraform/modules/model-router/tests/model-router.tftest.hcl",
            "terraform/README.md",
        })


if __name__ == "__main__":
    unittest.main()

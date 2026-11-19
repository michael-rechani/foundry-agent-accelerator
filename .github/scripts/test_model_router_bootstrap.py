"""Offline tests for the inert, fixed Model Router bootstrap proposal."""

import ast
import base64
import builtins
from copy import deepcopy
from email.message import Message
import importlib.util
from io import BytesIO
import json
from pathlib import Path
import re
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request
import urllib.response

from check_lab_terraform_plan import CheckError, change_action, has_unknown

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "model_router_bootstrap", ROOT / ".github/scripts/model_router_bootstrap.py"
)
bootstrap = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bootstrap)


def platform_policy(*, transformed=True):
    source = (ROOT / ".github/scripts/fixtures/model-router-bootstrap-platform-policy.txt").read_text()
    if transformed:
        source = bootstrap.transform_file(".github/scripts/check_platform_router_plan.py", source)
    tree = ast.parse(source)
    functions = {
        "router_body", "router_change_matches", "preview_capabilities",
        "summarize_plan", "enforce_forward_policy",
    }
    if transformed:
        functions.add("require_router_readback")
    if {node.name for node in tree.body if isinstance(node, ast.FunctionDef)} != functions:
        raise AssertionError("Only the reviewed pure policy fixture may execute.")
    if any(isinstance(node, (ast.Import, ast.ImportFrom)) for node in ast.walk(tree)):
        raise AssertionError("The policy fixture must not import runner or network code.")
    namespace = {
        "__builtins__": {
            name: getattr(builtins, name)
            for name in (
                "all", "any", "bool", "dict", "int", "isinstance", "len", "list", "set", "sorted", "str", "tuple", "type",
            )
        },
        "CheckError": CheckError, "change_action": change_action, "has_unknown": has_unknown,
        "json": json, "re": re,
    }
    # Only this checked-in, reviewed pure-policy excerpt runs; no PR module imports or runner entry point.
    exec(compile(tree, "<reviewed offline policy fixture>", "exec"), namespace)  # noqa: S102
    return SimpleNamespace(**namespace)


def synthetic_platform_plan(policy):
    account = (
        "/subscriptions/11111111-2222-3333-4444-555555555555/resourceGroups/rg-fixture"
        "/providers/Microsoft.CognitiveServices/accounts/foundry-fixture"
    )
    values = {
        "subscription_id": "11111111-2222-3333-4444-555555555555",
        "deployment_principal_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "model_router_deployment": deepcopy(policy.ROUTER_INPUT),
    }
    plan = {
        "format_version": "1.0", "complete": True, "errored": False,
        "variables": {
            **{name: {"value": value} for name, value in values.items()},
            "model_deployment": {"value": {
                "deployment_name": "gpt-4.1", "format": "OpenAI", "name": "gpt-4.1", "version": "2025-04-14",
            }},
            "additional_model_deployments": {"value": {}},
        },
        "resource_changes": [
            {
                "address": policy.DEPLOYMENT, "mode": "managed",
                "change": {
                    "actions": ["create"], "before": None,
                    "after": {
                        "type": "Microsoft.CognitiveServices/accounts/deployments@2025-10-01-preview",
                        "name": "model-router", "parent_id": account, "body": policy.router_body(),
                    },
                    "after_unknown": {},
                },
            },
            {
                "address": policy.READBACK, "mode": "data", "type": "azapi_resource",
                "change": {
                    "actions": ["read"], "before": None,
                    "after": {
                        "type": "Microsoft.CognitiveServices/accounts/deployments@2025-12-01",
                        "response_export_values": ["properties.routing"],
                    },
                    "after_unknown": {"output": True, "resource_id": True},
                },
            },
        ],
        "output_changes": {
            "model_router_deployment_name": {"actions": ["create"], "after_unknown": True},
            "model_deployment_names": {
                "actions": ["update"], "before": ["gpt-4.1"],
                "after": ["gpt-4.1", None], "after_unknown": [False, True],
            },
            "model_preview_encrypted_reasoning": {
                "actions": ["create"], "before": None,
                "after": {"gpt-4.1": False, "model-router": False}, "after_unknown": False,
            },
        },
        "checks": [{
            "address": {
                "kind": "resource", "mode": "data", "type": "azapi_resource",
                "name": "model_router_routing", "module": "module.model_router",
                "to_display": "module.model_router.data.azapi_resource.model_router_routing",
            },
            "status": "unknown",
            "instances": [{
                "address": {"module": "module.model_router", "instance_key": 0, "to_display": policy.READBACK},
                "status": "unknown",
            }],
        }],
    }
    return plan, values, account


class PlatformPolicyTests(unittest.TestCase):
    def setUp(self):
        self.policy = platform_policy()

    def approve(self, plan, exit_code=2):
        _, values, account = synthetic_platform_plan(self.policy)
        summary = self.policy.summarize_plan(plan, exit_code, values, account)
        self.policy.enforce_forward_policy(summary)
        return summary

    def test_put_only_creation_reproduces_old_failure_and_passes_fixed_policy(self):
        plan, values, account = synthetic_platform_plan(self.policy)
        with self.assertRaisesRegex(CheckError, "must have matching actions"):
            platform_policy(transformed=False).summarize_plan(plan, 2, values, account)
        result = self.approve(plan)
        self.assertEqual(result["router_deployment"], "create")
        self.assertNotIn("router_patch", result)
        self.assertEqual(result["deferred_router_readback"], 1)

    def no_op_plan(self):
        plan, _, _ = synthetic_platform_plan(self.policy)
        deployment = plan["resource_changes"][0]["change"]
        deployment.update(actions=["no-op"], before=deepcopy(deployment["after"]))
        plan["resource_changes"].pop(1)
        _, _, account = synthetic_platform_plan(self.policy)
        plan["prior_state"] = {"values": {"root_module": {"child_modules": [{
            "address": "module.model_router",
            "resources": [{
                "address": self.policy.READBACK, "mode": "data", "type": "azapi_resource",
                "values": {
                    "type": "Microsoft.CognitiveServices/accounts/deployments@2025-12-01",
                    "resource_id": account + "/deployments/model-router",
                    "response_export_values": ["properties.routing"],
                    "output": {"properties": {"routing": {
                        "mode": "balanced", "models": deepcopy(self.policy.ROUTER_MODELS),
                    }}},
                },
            }],
        }]}}}
        plan["output_changes"] = {
            "model_router_deployment_name": {
                "actions": ["no-op"], "before": "model-router", "after": "model-router", "after_unknown": False,
            },
            "model_deployment_names": {
                "actions": ["no-op"], "before": ["gpt-4.1", "model-router"],
                "after": ["gpt-4.1", "model-router"], "after_unknown": False,
            },
            "model_preview_encrypted_reasoning": {
                "actions": ["no-op"], "before": {"gpt-4.1": False, "model-router": False},
                "after": {"gpt-4.1": False, "model-router": False}, "after_unknown": False,
            },
        }
        plan["checks"][0]["status"] = "pass"
        plan["checks"][0]["instances"][0]["status"] = "pass"
        return plan

    def test_verified_known_no_op_is_accepted(self):
        result = self.approve(self.no_op_plan(), 0)
        self.assertEqual(result["router_deployment"], "no-op")
        self.assertEqual(result["deferred_router_readback"], 0)

    def test_legacy_patch_actions_never_authorize_state_removal_or_recovery(self):
        for actions in (["no-op"], ["create"], ["update"], ["delete"], ["forget"], ["delete", "create"]):
            plan, _, _ = synthetic_platform_plan(self.policy)
            plan["resource_changes"].append({
                "address": self.policy.LEGACY_PATCH, "mode": "managed",
                "change": {"actions": actions, "before": {}, "after": {}, "after_unknown": {}},
            })
            with self.subTest(actions=actions), self.assertRaisesRegex(CheckError, "separately reviewed recovery"):
                self.approve(plan)
        plan, _, _ = synthetic_platform_plan(self.policy)
        plan["resource_drift"] = [{
            "address": self.policy.LEGACY_PATCH, "mode": "managed",
            "change": {"actions": ["no-op"], "before": {}, "after": {}, "after_unknown": {}},
        }]
        with self.assertRaisesRegex(CheckError, "separately reviewed recovery"):
            self.approve(plan)

    def test_router_update_replacement_delete_forget_and_missing_resource_are_rejected(self):
        for actions in (["update"], ["delete"], ["forget"], ["delete", "create"], ["create", "delete"]):
            plan, _, _ = synthetic_platform_plan(self.policy)
            plan["resource_changes"][0]["change"]["actions"] = actions
            with self.subTest(actions=actions), self.assertRaises(CheckError):
                self.approve(plan)
        plan, _, _ = synthetic_platform_plan(self.policy)
        plan["resource_changes"].pop(0)
        with self.assertRaises(CheckError):
            self.approve(plan)

    def test_unsafe_put_body_identity_unknowns_duplicate_and_readback_actions_are_rejected(self):
        for alter in (
            lambda p: p["resource_changes"][0]["change"]["after"].update(parent_id="wrong-account"),
            lambda p: p["resource_changes"][0]["change"]["after"].update(
                type="Microsoft.CognitiveServices/accounts/deployments@2025-12-01"),
            lambda p: p["resource_changes"][0]["change"]["after"]["body"]["properties"]["routing"].update(mode="cost"),
            lambda p: p["resource_changes"][0]["change"]["after_unknown"].update(body=True),
            lambda p: p["resource_changes"][0]["change"]["after_unknown"].update(parent_id=True),
            lambda p: p["resource_changes"].append(deepcopy(p["resource_changes"][0])),
            lambda p: p["resource_changes"][1]["change"].update(actions=["delete"]),
        ):
            plan, _, _ = synthetic_platform_plan(self.policy)
            alter(plan)
            with self.subTest(alter=alter), self.assertRaises(CheckError):
                self.approve(plan)

    def test_unrelated_managed_changes_drift_imports_outputs_reads_and_checks_still_block(self):
        for alter in (
            lambda p: p["resource_changes"].append({
                "address": "azapi_resource.jumpbox[0]", "mode": "managed",
                "change": {"actions": ["delete"], "before": {}, "after": None},
            }),
            lambda p: p.update(resource_drift=[{
                "address": self.policy.DEPLOYMENT, "mode": "managed",
                "change": {"actions": ["update"], "before": {}, "after": {}},
            }]),
            lambda p: p["resource_changes"][0]["change"].update(importing={"id": "fixture-import"}),
            lambda p: p["output_changes"].update(unrelated={"actions": ["update"]}),
            lambda p: p["resource_changes"].append({
                "address": "data.unrelated", "mode": "data", "change": {"actions": ["read"], "after": {}},
            }),
            lambda p: p["checks"].append({"status": "unknown", "address": {"to_display": "unrelated"}}),
            lambda p: p["checks"][0].update(status="fail"),
            lambda p: p["checks"][0].update(status="error"),
        ):
            plan, _, _ = synthetic_platform_plan(self.policy)
            alter(plan)
            with self.subTest(alter=alter), self.assertRaises(CheckError):
                self.approve(plan)

    def test_no_op_unknown_readback_or_outputs_and_partial_create_are_rejected(self):
        for alter in (
            lambda p: p["checks"][0].update(status="unknown"),
            lambda p: p["output_changes"]["model_router_deployment_name"].update(after_unknown=True),
            lambda p: p["output_changes"]["model_deployment_names"].update(after=["gpt-4.1"]),
        ):
            plan = self.no_op_plan()
            alter(plan)
            with self.subTest(alter=alter), self.assertRaises(CheckError):
                self.approve(plan, 0)
        plan, _, _ = synthetic_platform_plan(self.policy)
        plan["resource_changes"][0]["change"]["actions"] = ["no-op"]
        with self.assertRaises(CheckError):
            self.approve(plan)

    def test_create_missing_duplicate_or_unchecked_readback_is_rejected(self):
        for alter in (
            lambda p: p["resource_changes"].pop(1),
            lambda p: p["resource_changes"].append(deepcopy(p["resource_changes"][1])),
            lambda p: p.pop("checks"),
            lambda p: p.update(checks=[]),
            lambda p: p["checks"][0].pop("instances"),
            lambda p: p["checks"][0]["instances"].clear(),
            lambda p: p["checks"][0]["instances"].append(deepcopy(p["checks"][0]["instances"][0])),
            lambda p: p["checks"][0]["instances"][0].update(status="pass"),
            lambda p: p["checks"][0]["address"].update(mode="managed"),
            lambda p: p["resource_changes"][1]["change"]["after"].update(resource_id="wrong"),
            lambda p: p["resource_changes"][1]["change"]["after"].update(output={"properties": {}}),
            lambda p: p["resource_changes"][1]["change"]["after_unknown"].update(output=False),
        ):
            plan, _, _ = synthetic_platform_plan(self.policy)
            alter(plan)
            with self.subTest(alter=alter), self.assertRaises(CheckError):
                self.approve(plan)

    def test_no_op_requires_unique_known_values_and_matching_passing_postcondition(self):
        for alter in (
            lambda p: p.pop("prior_state"),
            lambda p: p["prior_state"]["values"]["root_module"]["child_modules"][0]["resources"].clear(),
            lambda p: p["prior_state"]["values"]["root_module"]["child_modules"][0]["resources"].append(
                deepcopy(p["prior_state"]["values"]["root_module"]["child_modules"][0]["resources"][0])),
            lambda p: p.pop("checks"),
            lambda p: p.update(checks=[]),
            lambda p: p["checks"][0].pop("instances"),
            lambda p: p["checks"][0]["instances"][0].update(status="unknown"),
            lambda p: p["checks"][0]["instances"][0]["address"].update(instance_key=1),
            lambda p: p["prior_state"]["values"]["root_module"]["child_modules"][0]["resources"][0]["values"][
                "output"]["properties"]["routing"].update(mode="cost"),
        ):
            plan = self.no_op_plan()
            alter(plan)
            with self.subTest(alter=alter), self.assertRaises(CheckError):
                self.approve(plan, 0)

    def test_no_op_allows_known_planned_values_and_rejects_inconsistent_no_op_change(self):
        plan = self.no_op_plan()
        plan["planned_values"] = plan.pop("prior_state")["values"]
        self.assertEqual(self.approve(plan, 0)["router_deployment"], "no-op")
        resource = plan["planned_values"]["root_module"]["child_modules"][0]["resources"][0]
        plan["resource_changes"].append({
            "address": self.policy.READBACK, "mode": "data", "type": "azapi_resource",
            "change": {
                "actions": ["no-op"], "before": deepcopy(resource["values"]),
                "after": deepcopy(resource["values"]), "after_unknown": {},
            },
        })
        self.assertEqual(self.approve(plan, 0)["router_deployment"], "no-op")
        plan["resource_changes"][-1]["change"]["after"]["resource_id"] = "different"
        with self.assertRaises(CheckError):
            self.approve(plan, 0)

    def test_incomplete_errored_or_inconsistent_plans_are_rejected(self):
        for alter in (
            lambda p: p.update(complete=False),
            lambda p: p.update(errored=True),
            lambda p: p.update(deferred_changes=[{}]),
            lambda p: p.update(action_invocations=[{}]),
            lambda p: p["checks"].append(deepcopy(p["checks"][0])),
        ):
            plan, _, _ = synthetic_platform_plan(self.policy)
            alter(plan)
            with self.subTest(alter=alter), self.assertRaises(CheckError):
                self.approve(plan)
        plan, _, _ = synthetic_platform_plan(self.policy)
        with self.assertRaises(CheckError):
            self.approve(plan, 0)


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

    def test_recovery_docs_do_not_authorize_legacy_state_deletion_or_router_updates(self):
        source = """The Router module's routing PATCH is not yet verified against the live service.
A failed create, PATCH, or readback can leave a deployment present with an
unverified model subset, and state may reflect only part of the operation.
Do not route requests to it or blindly retry or delete it. Use an approved
private-runner path to inspect the deployment and state, then separately review
the necessary reconciliation or removal; no such recovery path is approved
yet. For example, a no-change deployment with a pending PATCH is rejected by
the forward diagnostic's matching-action guard and requires a separately
reviewed recovery path, not a targeted apply or a weaker forward guard.
"""
        result = bootstrap.transform_file("docs/lab-deployment.md", source)
        for warning in (
            "not a verified live-service fix", "rejects in-place Router updates",
            "including no-op or deletion", "does not authorize its state",
            "Unrelated managed changes, drift, imports, and nonpassing",
        ):
            self.assertIn(warning, result)

    def test_unrecognized_paths_and_source_shapes_fail_closed(self):
        with self.assertRaises(bootstrap.BootstrapError):
            bootstrap.transform_file("README.md", "data")
        for path in bootstrap.EXPECTED_FILES:
            with self.subTest(path=path), self.assertRaises(bootstrap.BootstrapError):
                bootstrap.transform_file(path, "unexpected")


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
    def preflight_responses(self):
        return [
            {"name": "main", "protected": True, "commit": {"sha": "f" * 40}},
            {"object": {"sha": bootstrap.TARGET_HEAD}},
            {
                "number": bootstrap.TARGET_PR, "state": "open",
                "head": {"ref": bootstrap.TARGET_BRANCH, "sha": bootstrap.TARGET_HEAD},
                "base": {"ref": "main"},
            },
        ]

    def test_protected_main_and_fixed_target_preflight_pass(self):
        with patch.object(bootstrap, "_request", side_effect=self.preflight_responses()) as request:
            bootstrap._check_main_and_target("offline-token", "f" * 40)
        self.assertEqual(request.call_count, 3)
        self.assertEqual(
            request.call_args_list[0].args[0],
            f"{bootstrap.API_ROOT}/repos/{bootstrap.REPOSITORY}/branches/main",
        )

    def test_main_protection_flag_requires_exact_true_and_pinned_commit(self):
        for alter in (
            lambda m: m.update(protected=False),
            lambda m: m.pop("protected"),
            lambda m: m.update(protected="true"),
            lambda m: m.update(protected=1),
            lambda m: m.update(protected=None),
            lambda m: m.update(protected={}),
            lambda m: m["commit"].update(sha="e" * 40),
            lambda m: m["commit"].pop("sha"),
            lambda m: m.update(commit="malformed"),
            lambda m: m.pop("commit"),
            lambda m: m.update(name="other"),
        ):
            responses = self.preflight_responses()
            alter(responses[0])
            with self.subTest(alter=alter), patch.object(
                bootstrap, "_request", side_effect=responses
            ) as request, self.assertRaises(bootstrap.BootstrapError):
                bootstrap._check_main_and_target("offline-token", "f" * 40)
            self.assertEqual(request.call_count, 1)

    def test_target_branch_and_pull_identity_still_fail_closed(self):
        for index, alter in (
            (1, lambda r: r.update(object=None)),
            (1, lambda r: r["object"].update(sha="e" * 40)),
            (2, lambda r: r.update(number=524)),
            (2, lambda r: r.update(state="closed")),
            (2, lambda r: r.update(head=None)),
            (2, lambda r: r.update(base=None)),
            (2, lambda r: r["head"].update(ref="other")),
            (2, lambda r: r["head"].update(sha="e" * 40)),
            (2, lambda r: r["base"].update(ref="other")),
        ):
            responses = self.preflight_responses()
            alter(responses[index])
            with self.subTest(index=index, alter=alter), patch.object(
                bootstrap, "_request", side_effect=responses
            ) as request, self.assertRaises(bootstrap.BootstrapError):
                bootstrap._check_main_and_target("offline-token", "f" * 40)
            self.assertEqual(request.call_count, index + 1)

    def test_authenticated_opener_rejects_redirects_without_sending_a_second_request(self):
        for destination in (
            "https://example.com/stolen",
            "http://api.github.com/downgraded",
            "https://api.github.com/redirected",
        ):
            for status in (301, 302, 303, 307, 308):
                for method in ("GET", "POST"):
                    with self.subTest(destination=destination, status=status, method=method):
                        requests = []

                        def respond(request, requests=requests, destination=destination, status=status):
                            requests.append(request)
                            headers = Message()
                            headers["Location"] = destination
                            response = urllib.response.addinfourl(
                                BytesIO(b""),
                                headers,
                                request.full_url,
                                status,
                            )
                            response.msg = "Redirect"
                            return response

                        with patch.object(
                            urllib.request.HTTPSHandler, "https_open", side_effect=respond
                        ), patch.object(
                            urllib.request.HTTPHandler, "http_open", side_effect=respond
                        ), self.assertRaises(bootstrap.BootstrapError) as raised:
                            bootstrap._request(
                                "https://api.github.com/graphql",
                                "offline-token",
                                method=method,
                                body={} if method == "POST" else None,
                            )
                        self.assertIsInstance(raised.exception.__cause__, urllib.error.HTTPError)
                        self.assertEqual(raised.exception.__cause__.code, status)
                        self.assertEqual(len(requests), 1)
                        self.assertEqual(requests[0].full_url, "https://api.github.com/graphql")
                        self.assertEqual(
                            requests[0].get_header("Authorization"), "Bearer offline-token"
                        )

    def test_authenticated_opener_accepts_a_direct_json_response(self):
        def respond(request):
            response = urllib.response.addinfourl(
                BytesIO(b'{"sha":"reviewed"}'), Message(), request.full_url, 200
            )
            response.msg = "OK"
            return response

        with patch.object(urllib.request.HTTPSHandler, "https_open", side_effect=respond):
            self.assertEqual(
                bootstrap._request("https://api.github.com/repos/example", "offline-token"),
                {"sha": "reviewed"},
            )

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
            ".github/scripts/check_platform_router_plan.py",
            ".github/scripts/test_check_platform_router_plan.py",
            "docs/lab-deployment.md",
        })


if __name__ == "__main__":
    unittest.main()

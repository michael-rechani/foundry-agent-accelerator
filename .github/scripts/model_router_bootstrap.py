"""Apply one reviewed, data-only Model Router edit to the fixed PR head."""

import base64
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request


REPOSITORY = "michael-rechani/foundry-agent-accelerator"
OWNER_ID = "97264614"
TARGET_BRANCH = "michael-rechani-add-model-router-terraform"
TARGET_HEAD = "52fab5e08fb498720efcd53f0f389f424d671a46"
TARGET_PR = 523
EXPECTED_FILES = {
    "terraform/modules/model-router/main.tf": "b4ed2b855ce7f75b7acb2cab81c2ccde66d324bc",
    "terraform/modules/model-router/tests/model-router.tftest.hcl": "09bdeaf53260e25aa5c029308692010ac06ee4eb",
    "terraform/README.md": "adbc5cd0ef8578770074b533c57437a34a2f1f4d",
    ".github/scripts/check_platform_router_plan.py": "c53c9106b3852ddaae6a0611feb02d145b1f106d",
    ".github/scripts/test_check_platform_router_plan.py": "828b84ad63116d80bef07c2eb9fb81d28ab984c3",
    "docs/lab-deployment.md": "0094cb9587920b46e511e3174f98d61e3629688a",
}
API_ROOT = "https://api.github.com"


class BootstrapError(Exception):
    """A fixed precondition or GitHub API operation failed."""


class _RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _replace_once(text, old, new, description):
    if text.count(old) != 1:
        raise BootstrapError(f"Expected exactly one occurrence of {description}.")
    return text.replace(old, new, 1)


def transform_file(path, text):
    """Return the exact fixed Router change; reject unexpected source shapes."""
    if path == ".github/scripts/check_platform_router_plan.py":
        replacements = (
            (
                'PATCH = "module.model_router.azapi_resource_action.model_router_routing[0]"',
                'LEGACY_PATCH = "module.model_router.azapi_resource_action.model_router_routing[0]"',
            ),
            (
                '''    patch = {"sku": expected["sku"], "properties": {
        "model": expected["properties"]["model"], "routing": expected["properties"]["routing"],
    }}
    resource_id = after.get("resource_id")
    return (
        after.get("type") == "Microsoft.CognitiveServices/accounts/deployments@2025-12-01"
        and after.get("method") == "PATCH" and after.get("body") == patch
        and (resource_id is None and unknown.get("resource_id") is True
             or isinstance(resource_id, str)
             and resource_id.lower() == (account + "/deployments/model-router").lower())
    )
''',
                "    return False\n",
            ),
            (
                "        if address in (DEPLOYMENT, PATCH):\n",
                '''        if address == LEGACY_PATCH:
            raise CheckError("Legacy Router PATCH state requires separately reviewed recovery.")
        if address == DEPLOYMENT:
''',
            ),
            (
                "The Router deployment or PATCH differs from the reviewed configuration.",
                "The Router deployment differs from the reviewed PUT configuration.",
            ),
            (
                '''    if set(actions) != {DEPLOYMENT, PATCH} or actions[DEPLOYMENT] != actions[PATCH]:
        raise CheckError("The Router deployment and verification PATCH must have matching actions.")
''',
                '''    if set(actions) != {DEPLOYMENT}:
        raise CheckError("The plan must contain exactly the reviewed Router PUT deployment.")
''',
            ),
            (
                '''    for entry in drift:
        if not isinstance(entry, dict) or entry.get("mode") != "managed":
            raise CheckError("Terraform returned an invalid platform drift entry.")
''',
                '''    for entry in drift:
        if not isinstance(entry, dict) or entry.get("mode") != "managed":
            raise CheckError("Terraform returned an invalid platform drift entry.")
        if entry.get("address") == LEGACY_PATCH:
            raise CheckError("Legacy Router PATCH state requires separately reviewed recovery.")
''',
            ),
            ('        "router_patch": actions[PATCH],\n', ""),
        )
        for old, new in replacements:
            text = _replace_once(text, old, new, "the fixed platform PUT-only guard")
        return text

    if path == ".github/scripts/test_check_platform_router_plan.py":
        replacements = (
            (
                '''    patch_body = {
        "sku": deepcopy(body["sku"]),
        "properties": {
            "model": deepcopy(body["properties"]["model"]),
            "routing": deepcopy(body["properties"]["routing"]),
        },
    }
''',
                "",
            ),
            (
                '''            {
                "address": diagnostic.PATCH, "mode": "managed",
                "change": {
                    "actions": ["create"], "before": None,
                    "after": {
                        "type": "Microsoft.CognitiveServices/accounts/deployments@2025-12-01",
                        "method": "PATCH", "body": patch_body,
                    },
                    "after_unknown": {"resource_id": True},
                },
            },
''',
                "",
            ),
            (
                '        self.assertEqual((result["router_deployment"], result["router_patch"]), ("create", "create"))',
                '''        self.assertEqual(result["router_deployment"], "create")
        self.assertNotIn("router_patch", result)''',
            ),
            (
                '''        value["resource_changes"][1]["change"].update(
            actions=["no-op"],
            after={**value["resource_changes"][1]["change"]["after"],
                   "resource_id": ACCOUNT + "/deployments/model-router"},
            after_unknown={},
        )
        value["resource_changes"][2]["change"]["actions"] = ["no-op"]
''',
                '        value["resource_changes"][1]["change"]["actions"] = ["no-op"]\n',
            ),
            (
                '''    def test_partial_router_apply_requires_separate_recovery(self):
        value = plan()
        deployment = value["resource_changes"][0]["change"]
        deployment.update(actions=["no-op"], before=deepcopy(deployment["after"]))
        patch_change = value["resource_changes"][1]["change"]
        patch_change["after"]["resource_id"] = ACCOUNT + "/deployments/model-router"
        patch_change["after_unknown"] = {}
        with self.assertRaisesRegex(diagnostic.CheckError, "must have matching actions"):
            diagnostic.summarize_plan(value, 2, values(), ACCOUNT)
''',
                '''    def test_partial_router_apply_requires_separate_recovery(self):
        value = plan()
        deployment = value["resource_changes"][0]["change"]
        deployment.update(actions=["no-op"], before=deepcopy(deployment["after"]))
        with self.assertRaisesRegex(diagnostic.CheckError, "existing Router outputs"):
            diagnostic.summarize_plan(value, 2, values(), ACCOUNT)

    def test_legacy_patch_state_and_router_updates_require_separate_recovery(self):
        for actions in (["no-op"], ["create"], ["update"], ["delete"], ["delete", "create"], ["forget"]):
            value = plan()
            value["resource_changes"].append({
                "address": diagnostic.LEGACY_PATCH, "mode": "managed",
                "change": {"actions": actions, "before": {}, "after": {}, "after_unknown": {}},
            })
            with self.subTest(actions=actions), self.assertRaisesRegex(
                    diagnostic.CheckError, "separately reviewed recovery"):
                diagnostic.summarize_plan(value, 2, values(), ACCOUNT)
        value = plan()
        value["resource_drift"] = [{
            "address": diagnostic.LEGACY_PATCH, "mode": "managed",
            "change": {"actions": ["no-op"], "before": {}, "after": {}, "after_unknown": {}},
        }]
        with self.assertRaisesRegex(diagnostic.CheckError, "separately reviewed recovery"):
            diagnostic.summarize_plan(value, 2, values(), ACCOUNT)
        for actions in (["update"], ["delete"], ["delete", "create"], ["create", "delete"], ["forget"]):
            value = plan()
            value["resource_changes"][0]["change"]["actions"] = actions
            with self.subTest(actions=actions), self.assertRaises(diagnostic.CheckError):
                diagnostic.summarize_plan(value, 2, values(), ACCOUNT)
''',
            ),
            (
                '            lambda item: item["resource_changes"][1]["change"]["after"].update(method="DELETE"),',
                '''            lambda item: item["resource_changes"][0]["change"]["after"].update(
                type="Microsoft.CognitiveServices/accounts/deployments@2025-12-01"),''',
            ),
            (
                '            lambda item: item["resource_changes"][1]["change"]["after_unknown"].update(resource_id=False),',
                '            lambda item: item["resource_changes"][0]["change"]["after_unknown"].update(parent_id=True),',
            ),
        )
        for old, new in replacements:
            text = _replace_once(text, old, new, "the fixed platform PUT-only regression")
        return text

    if path == "docs/lab-deployment.md":
        return _replace_once(
            text,
            '''The Router module's routing PATCH is not yet verified against the live service.
A failed create, PATCH, or readback can leave a deployment present with an
unverified model subset, and state may reflect only part of the operation.
Do not route requests to it or blindly retry or delete it. Use an approved
private-runner path to inspect the deployment and state, then separately review
the necessary reconciliation or removal; no such recovery path is approved
yet. For example, a no-change deployment with a pending PATCH is rejected by
the forward diagnostic's matching-action guard and requires a separately
reviewed recovery path, not a targeted apply or a weaker forward guard.
''',
            '''The Router module sends routing only in the documented deployment PUT and
retains strict fresh management-plane readback. Removing the unsupported
routing PATCH is a code-contract correction, not a verified live-service fix.
A failed PUT or readback can leave a deployment present with an unverified
model subset, and state may reflect only part of the operation. Do not route
requests to it or blindly retry or delete it. Use an approved private-runner
path to inspect the deployment and state, then separately review the necessary
reconciliation or removal; no such recovery path is approved yet.

The forward platform diagnostic accepts only the exact reviewed PUT creation
or a verified no-op. It rejects in-place Router updates, replacements, deletes,
and every legacy PATCH state entry, including no-op or deletion of the removed
resource. Removing the PATCH from configuration does not authorize its state
removal. Partial creation, legacy PATCH state, and unverified readback require
a separately reviewed recovery path, not a targeted apply, state surgery, or a
weaker forward guard. Unrelated managed changes, drift, imports, and nonpassing
checks remain blockers.
''',
            "the PUT-only Router recovery documentation",
        )

    if path == "terraform/modules/model-router/main.tf":
        text = _replace_once(
            text,
            """# Some API/provider combinations have ignored routing on PUT. Reapply it by
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

""",
            "",
            "the unsupported routing PATCH resource",
        )
        return _replace_once(
            text,
            "  depends_on = [azapi_resource_action.model_router_routing]\n",
            "  depends_on = [azapi_resource.model_router]\n",
            "the fresh-read dependency",
        )

    if path == "terraform/modules/model-router/tests/model-router.tftest.hcl":
        text = _replace_once(
            text,
            "      length(azapi_resource_action.model_router_routing) == 0 &&\n",
            "",
            "the null-router PATCH assertion",
        )
        text = _replace_once(
            text,
            """      azapi_resource.model_router[0].ignore_missing_property == false &&
      azapi_resource_action.model_router_routing[0].method == "PATCH" &&
      azapi_resource_action.model_router_routing[0].body.sku == azapi_resource.model_router[0].body.sku &&
      azapi_resource_action.model_router_routing[0].body.properties.model == azapi_resource.model_router[0].body.properties.model &&
      azapi_resource_action.model_router_routing[0].body.properties.routing == azapi_resource.model_router[0].body.properties.routing
""",
            "      azapi_resource.model_router[0].ignore_missing_property == false\n",
            "the PATCH request assertions",
        )
        text = _replace_once(
            text,
            "The configured deployment must send the requested Router settings and PATCH the same settings.",
            "The configured deployment must send the requested Router settings in the documented PUT body.",
            "the request-contract assertion message",
        )
        text = _replace_once(
            text,
            '      azapi_resource_action.model_router_routing[0].body.properties.routing.mode == "balanced" &&\n',
            "",
            "the default-subset PATCH assertion",
        )
        text = _replace_once(
            text,
            "The standard Router subset must be sent, patched, and verified before exposing its output.",
            "The standard Router subset must be sent and verified before exposing its output.",
            "the default-subset assertion message",
        )
        text = _replace_once(
            text,
            """      azapi_resource.model_router[0].body.properties.routing.mode == "cost" &&
      azapi_resource_action.model_router_routing[0].body.properties.routing.mode == "cost"
""",
            """      azapi_resource.model_router[0].body.properties.routing.mode == "cost"
""",
            "the routing-plan PATCH assertion",
        )
        text = _replace_once(
            text,
            "A routing update must plan both the deployment change and the PATCH.",
            "A routing update must plan the deployment's requested PUT body.",
            "the routing-plan assertion message",
        )
        text = _replace_once(
            text,
            """      azapi_resource.model_router[0].body.properties.routing.mode == "cost" &&
      azapi_resource_action.model_router_routing[0].body.properties.routing.mode == "cost" &&
""",
            """      azapi_resource.model_router[0].body.properties.routing.mode == "cost" &&
""",
            "the routing-apply PATCH assertion",
        )
        text = _replace_once(
            text,
            "A routing change must update both the deployment and PATCH and verify the resulting mode.",
            "A routing change must send the requested PUT body and verify the resulting mode.",
            "the routing-apply assertion message",
        )
        return _replace_once(
            text,
            'run "update_routing_mode" {\n  command = apply\n',
            'run "update_routing_mode" {\n  command = apply\n  state_key = "standard-default-subset"\n',
            "the routing update state key",
        )

    if path == "terraform/README.md":
        return _replace_once(
            text,
            """uses a preview PUT; this module's subsequent `2025-12-01` PATCH of routing
properties has not been verified against the live service. Before approving an
apply, review a private-runner recovery path for a partial create or failed
PATCH; neither retrying nor deleting the deployment is automatically safe.
""",
            """uses a preview PUT. Microsoft's [2025-12-01 API definition](https://github.com/Azure/azure-rest-api-specs/blob/main/specification/cognitiveservices/resource-manager/Microsoft.CognitiveServices/CognitiveServices/Deployment.tsp)
models update as tags and SKU only, not routing; the [official custom-routing
example](https://learn.microsoft.com/azure/foundry/openai/how-to/model-router#configure-custom-settings-with-the-rest-api)
sends routing in the deployment PUT. This module therefore sends routing only
in that documented PUT and retains a strict fresh management-plane readback.
This is a code-contract correction, not a verified live-service fix: [an
unreproduced provider issue](https://github.com/Azure/terraform-provider-azapi/issues/1136)
reports PUT routing silently ignored. If readback fails, the deployment may
still exist with a different or unrestricted model set; do not use it until
corrected and verified. Review a private-runner recovery path before any apply;
neither retrying nor deleting a partial deployment is automatically safe.
""",
            "the Router API and recovery documentation",
        )

    raise BootstrapError("The fixed transformation does not permit this file.")


def _request(url, token, method="GET", body=None):
    parsed_url = urllib.parse.urlsplit(url)
    if parsed_url.scheme != "https" or parsed_url.netloc != "api.github.com":
        raise BootstrapError("A required GitHub API request failed.")
    data = None if body is None else json.dumps(body, separators=(",", ":")).encode()
    request = urllib.request.Request(  # noqa: S310  # URL is restricted to GitHub's HTTPS API above.
        url,
        data=data,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            **({"Content-Type": "application/json"} if data is not None else {}),
        },
    )
    try:
        opener = urllib.request.build_opener(_RejectRedirects())
        with opener.open(request, timeout=20) as response:
            result = json.loads(response.read())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        raise BootstrapError("A required GitHub API request failed.") from error
    if not isinstance(result, dict):
        raise BootstrapError("GitHub returned an unexpected API response.")
    return result


def _check_context(environ):
    expected = {
        "GITHUB_REPOSITORY": REPOSITORY,
        "GITHUB_ACTOR_ID": OWNER_ID,
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_RUN_NUMBER": "1",
        "GITHUB_RUN_ATTEMPT": "1",
    }
    if any(environ.get(key) != value for key, value in expected.items()):
        raise BootstrapError("The workflow context is not the fixed first owner dispatch.")
    if not re.fullmatch(r"[0-9a-f]{40}", environ.get("GITHUB_SHA", "")):
        raise BootstrapError("The workflow source commit is invalid.")
    token = environ.get("GITHUB_TOKEN")
    if not token:
        raise BootstrapError("The workflow token is unavailable.")
    return token


def _check_main_and_target(token, workflow_sha):
    main = _request(f"{API_ROOT}/repos/{REPOSITORY}/commits/main", token)
    if not isinstance(main.get("sha"), str) or main["sha"] != workflow_sha:
        raise BootstrapError("Protected main moved since this workflow was dispatched.")

    branch = urllib.parse.quote(TARGET_BRANCH, safe="")
    ref = _request(f"{API_ROOT}/repos/{REPOSITORY}/git/ref/heads/{branch}", token)
    ref_object = ref.get("object")
    if not isinstance(ref_object, dict) or ref_object.get("sha") != TARGET_HEAD:
        raise BootstrapError("The fixed target branch no longer has the reviewed head.")

    pull = _request(f"{API_ROOT}/repos/{REPOSITORY}/pulls/{TARGET_PR}", token)
    if (
        pull.get("number") != TARGET_PR
        or pull.get("state") != "open"
        or not isinstance(pull.get("head"), dict)
        or not isinstance(pull.get("base"), dict)
        or pull["head"].get("ref") != TARGET_BRANCH
        or pull["head"].get("sha") != TARGET_HEAD
        or pull["base"].get("ref") != "main"
    ):
        raise BootstrapError("The fixed pull request no longer matches the reviewed target.")


def _read_fixed_files(token):
    result = {}
    for path, expected_blob in EXPECTED_FILES.items():
        query = urllib.parse.urlencode({"ref": TARGET_HEAD})
        encoded_path = urllib.parse.quote(path, safe="/")
        response = _request(f"{API_ROOT}/repos/{REPOSITORY}/contents/{encoded_path}?{query}", token)
        if (
            response.get("sha") != expected_blob
            or response.get("encoding") != "base64"
            or not isinstance(response.get("content"), str)
        ):
            raise BootstrapError(f"The reviewed source blob changed: {path}.")
        try:
            encoded = "".join(response["content"].split())
            content = base64.b64decode(encoded, validate=True)
            text = content.decode("utf-8")
        except (KeyError, ValueError, UnicodeDecodeError) as error:
            raise BootstrapError(f"The reviewed source file is malformed: {path}.") from error
        result[path] = transform_file(path, text)
    return result


def _commit(token, changes):
    additions = [
        {
            "path": path,
            "contents": base64.b64encode(content.encode("utf-8")).decode("ascii"),
        }
        for path, content in changes.items()
    ]
    query = """
      mutation($input: CreateCommitOnBranchInput!) {
        createCommitOnBranch(input: $input) {
          commit { oid url }
        }
      }
    """
    payload = {
        "query": query,
        "variables": {
            "input": {
                "branch": {
                    "repositoryNameWithOwner": REPOSITORY,
                    "branchName": TARGET_BRANCH,
                },
                "expectedHeadOid": TARGET_HEAD,
                "message": {
                    "headline": "Correct Model Router routing API request",
                    "body": "Co-authored-by: Copilot App <223556219+Copilot@users.noreply.github.com>",
                },
                "fileChanges": {"additions": additions, "deletions": []},
            }
        },
    }
    response = _request(f"{API_ROOT}/graphql", token, method="POST", body=payload)
    if response.get("errors"):
        raise BootstrapError("GitHub rejected the compare-and-swap commit.")
    data = response.get("data")
    mutation = data.get("createCommitOnBranch") if isinstance(data, dict) else None
    commit = mutation.get("commit") if isinstance(mutation, dict) else None
    oid = commit.get("oid") if isinstance(commit, dict) else None
    if not isinstance(oid, str) or not re.fullmatch(r"[0-9a-f]{40}", oid):
        raise BootstrapError("GitHub did not confirm the compare-and-swap commit.")
    return commit


def main(environ=None):
    environ = os.environ if environ is None else environ
    token = _check_context(environ)
    _check_main_and_target(token, environ["GITHUB_SHA"])
    changes = _read_fixed_files(token)
    commit = _commit(token, changes)
    print(
        "Committed the fixed Model Router data patch: "
        f"https://github.com/{REPOSITORY}/commit/{commit['oid']}"
    )


if __name__ == "__main__":
    try:
        main()
    except BootstrapError as error:
        print(f"::error::{error}", file=sys.stderr)
        raise SystemExit(1) from error

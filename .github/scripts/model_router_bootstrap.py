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
}
API_ROOT = "https://api.github.com"


class BootstrapError(Exception):
    """A fixed precondition or GitHub API operation failed."""


def _replace_once(text, old, new, description):
    if text.count(old) != 1:
        raise BootstrapError(f"Expected exactly one occurrence of {description}.")
    return text.replace(old, new, 1)


def transform_file(path, text):
    """Return the exact fixed Router change; reject unexpected source shapes."""
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
            "",
            "the PATCH dependency",
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
            """      azapi_resource_action.model_router_routing[0].method == "PATCH" &&
      azapi_resource_action.model_router_routing[0].body.sku == azapi_resource.model_router[0].body.sku &&
      azapi_resource_action.model_router_routing[0].body.properties.model == azapi_resource.model_router[0].body.properties.model &&
      azapi_resource_action.model_router_routing[0].body.properties.routing == azapi_resource.model_router[0].body.properties.routing
""",
            "",
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
        return _replace_once(
            text,
            "A routing change must update both the deployment and PATCH and verify the resulting mode.",
            "A routing change must send the requested PUT body and verify the resulting mode.",
            "the routing-apply assertion message",
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
    data = None if body is None else json.dumps(body, separators=(",", ":")).encode()
    request = urllib.request.Request(
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
        with urllib.request.urlopen(request, timeout=20) as response:
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
    additions = [{"path": path, "contents": content} for path, content in changes.items()]
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
                "message": {"headline": "Correct Model Router routing API request"},
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
        raise SystemExit(1)

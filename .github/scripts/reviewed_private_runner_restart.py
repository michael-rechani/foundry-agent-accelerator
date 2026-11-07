"""Fail-closed, start-only recovery. All network calls are injectable for offline tests."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

REPOSITORY = "michael-rechani/foundry-agent-accelerator"
OWNER = "michael-rechani"
GATE = "private-runner-restart-review"
WORKFLOW = ".github/workflows/reviewed-private-runner-restart.yml"
HEX40 = re.compile(r"[0-9a-f]{40}")
HEX64 = re.compile(r"[0-9a-f]{64}")
UUID = re.compile(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}")


class GuardError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise GuardError(message)


def object_value(value: object) -> dict:
    require(isinstance(value, dict), "Missing or ambiguous GitHub object.")
    return value


def positive_id(value: object) -> bool:
    return type(value) is int and value > 0


def mask(value: str) -> None:
    escaped = value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    print(f"::add-mask::{escaped}", flush=True)


def command(arguments: list[str]) -> str:
    try:
        result = subprocess.run(  # noqa: S603 - fixed CLI verbs and individually validated arguments; no shell
            arguments, capture_output=True, text=True, timeout=45, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise GuardError("Required CLI unavailable or timed out; no fallback permitted.") from error
    require(result.returncode == 0, "Required CLI operation failed; private CLI output withheld.")
    return result.stdout.strip()


def unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        require(key not in result, "Ambiguous JSON contains duplicate keys.")
        result[key] = value
    return result


def parse_json(text: str) -> object:
    try:
        return json.loads(text, object_pairs_hook=unique_object)
    except ValueError as error:
        raise GuardError("Required response is not valid JSON.") from error


def github_get(path: str) -> object:
    # --include exposes pagination: never accept an incomplete review/policy list.
    response = command(["gh", "api", "--hostname", "github.com", "--method", "GET",
                        "--include", "-H", "X-GitHub-Api-Version: 2022-11-28",
                        f"repos/{REPOSITORY}" + (f"/{path}" if path else "")])
    headers, separator, body = response.replace("\r\n", "\n").partition("\n\n")
    require(bool(separator) and headers.splitlines()[0].endswith("200 OK"),
            "GitHub read did not return an unambiguous successful response.")
    require(not any(line.lower().startswith("link:") for line in headers.splitlines()),
            "Paginated GitHub evidence is not accepted; no partial authorization.")
    return parse_json(body)


def context(env: Mapping[str, str]) -> tuple[str, str, str]:
    require(env.get("GITHUB_REPOSITORY") == REPOSITORY
            and env.get("GITHUB_REF") == "refs/heads/main"
            and env.get("GITHUB_EVENT_NAME") == "workflow_dispatch"
            and env.get("GITHUB_RUN_ATTEMPT") == "1",
            "Only a fresh manual dispatch on the expected main is allowed; never rerun.")
    sha = env.get("REVIEWED_COMMIT", "")
    digest = env.get("REVIEWED_VM_SHA256", "")
    run_id = env.get("GITHUB_RUN_ID", "")
    require(bool(HEX40.fullmatch(sha)) and sha == env.get("GITHUB_SHA")
            and bool(HEX64.fullmatch(digest)) and bool(re.fullmatch(r"[1-9][0-9]*", run_id)),
            "Invalid run, reviewed commit, or VM fingerprint.")
    return run_id, sha, digest


def approval_comment(run_id: str, sha: str, digest: str) -> str:
    return f"START runner run={run_id} sha={sha} vm-sha256={digest}"


def verify_gate(get: Callable[[str], object]) -> tuple[int, int, str]:
    repo = object_value(get(""))
    owner = object_value(repo.get("owner"))
    require(repo.get("full_name") == REPOSITORY and owner.get("login") == OWNER
            and owner.get("type") == "User" and positive_id(owner.get("id")),
            "Repository owner identity cannot be established.")
    gate = object_value(get(f"environments/{GATE}"))
    require(gate.get("name") == GATE and positive_id(gate.get("id")),
            "Dedicated review environment is missing or ambiguous.")
    # This field is not promised by the documented GET schema. Absence MUST block.
    require(gate.get("can_admins_bypass") is False,
            "Cannot prove admin bypass is disabled with the existing read-only token.")
    rules = gate.get("protection_rules")
    require(isinstance(rules, list) and len(rules) == 2,
            "Exactly one reviewer rule and one branch-policy rule are required.")
    rule_by_type = {}
    for item in rules:
        entry = object_value(item)
        rule_type = entry.get("type")
        require(isinstance(rule_type, str) and rule_type in {"required_reviewers", "branch_policy"}
                and rule_type not in rule_by_type and positive_id(entry.get("id")),
                "Unknown, duplicate, or invalid environment protection rule.")
        rule_by_type[rule_type] = entry
    rule = rule_by_type["required_reviewers"]
    branch_rule = rule_by_type["branch_policy"]
    require(rule["id"] != branch_rule["id"], "Protection rule IDs must be distinct.")
    require(type(rule.get("prevent_self_review")) is bool,
            "Required-reviewer configuration is unavailable.")
    reviewers = rule.get("reviewers")
    require(isinstance(reviewers, list) and len(reviewers) == 1,
            "Only the expected owner may be a reviewer.")
    reviewer_entry = object_value(reviewers[0])
    reviewer = object_value(reviewer_entry.get("reviewer"))
    require(reviewer_entry.get("type") == "User" and reviewer.get("type") == "User"
            and reviewer.get("login") == OWNER and reviewer.get("id") == owner["id"],
            "Dedicated gate does not require the expected owner.")
    require(gate.get("deployment_branch_policy") == {
        "protected_branches": False, "custom_branch_policies": True,
    }, "Dedicated gate must restrict deployments to exactly the main branch.")
    policies = object_value(get(f"environments/{GATE}/deployment-branch-policies?per_page=100"))
    branches = policies.get("branch_policies")
    require(type(policies.get("total_count")) is int and policies["total_count"] == 1
            and isinstance(branches, list) and len(branches) == 1,
            "Dedicated gate branch policy is missing or ambiguous.")
    branch = object_value(branches[0])
    require(branch.get("name") == "main" and branch.get("type") == "branch"
            and positive_id(branch.get("id")), "Tags and branch patterns are not allowed.")
    secrets = object_value(get(f"environments/{GATE}/secrets?per_page=100"))
    require(type(secrets.get("total_count")) is int and secrets["total_count"] == 0
            and secrets.get("secrets") == [],
            "Cannot prove the dedicated gate has no environment secrets.")
    snapshot = {"id": gate["id"], "reviewer_rule_id": rule["id"],
                "branch_policy_rule_id": branch_rule["id"],
                "prevent_self_review": rule["prevent_self_review"],
                "reviewer_id": owner["id"], "branch_id": branch["id"],
                "branch_name": "main", "branch_type": "branch",
                "deployment_branch_policy": gate["deployment_branch_policy"],
                "can_admins_bypass": False}
    digest = hashlib.sha256(json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
                            .encode("utf-8")).hexdigest()
    return gate["id"], owner["id"], digest


def verify_run(env: Mapping[str, str], get: Callable[[str], object]) -> tuple[int, int, str]:
    run_id, sha, _ = context(env)
    branch = object_value(get("branches/main"))
    require(branch.get("protected") is True
            and object_value(branch.get("commit")).get("sha") == sha,
            "Reviewed protected main changed or cannot be verified.")
    run = object_value(get(f"actions/runs/{run_id}"))
    require(type(run.get("id")) is int and str(run["id"]) == run_id
            and type(run.get("run_attempt")) is int and run["run_attempt"] == 1
            and run.get("event") == "workflow_dispatch" and run.get("head_branch") == "main"
            and run.get("head_sha") == sha and run.get("path") == WORKFLOW
            and object_value(run.get("repository")).get("full_name") == REPOSITORY,
            "Live workflow run does not match the reviewed first-attempt dispatch.")
    return verify_gate(get)


def verify_approval(env: Mapping[str, str], get: Callable[[str], object]) -> None:
    run_id, sha, digest = context(env)
    gate_id, owner_id, configuration = verify_run(env, get)
    require(env.get("EXPECTED_GATE_ID") == str(gate_id)
            and env.get("EXPECTED_GATE_CONFIGURATION_SHA256") == configuration,
            "Dedicated review environment changed since preflight.")
    reviews = get(f"actions/runs/{run_id}/approvals")
    require(isinstance(reviews, list), "Review history is unavailable or ambiguous.")
    matched = []
    for entry in reviews:
        review = object_value(entry)
        environments = review.get("environments")
        require(isinstance(environments, list) and bool(environments),
                "Review history has missing environments.")
        for item in environments:
            environment = object_value(item)
            require(positive_id(environment.get("id")) and isinstance(environment.get("name"), str),
                    "Review environment identity is ambiguous.")
            if environment["id"] == gate_id or environment["name"] == GATE:
                require(environment["id"] == gate_id and environment["name"] == GATE
                        and len(environments) == 1, "Review does not isolate the exact gate.")
                matched.append(review)
    require(len(matched) == 1, "Exactly one approval for this run and gate is required.")
    review = matched[0]
    user = object_value(review.get("user"))
    require(review.get("state") == "approved" and user.get("login") == OWNER
            and user.get("type") == "User" and type(user.get("id")) is int
            and user["id"] == owner_id and review.get("comment") == approval_comment(run_id, sha, digest),
            "Owner approval must explicitly bind this run, reviewed commit, and VM fingerprint.")


def target(env: Mapping[str, str]) -> str:
    for name in ("AZURE_SUBSCRIPTION_ID", "AZURE_CLIENT_ID", "AZURE_TENANT_ID",
                 "LAB_RUNNER_RESOURCE_GROUP", "LAB_RUNNER_VM"):
        mask(env.get(name, ""))
    for name in ("AZURE_SUBSCRIPTION_ID", "AZURE_CLIENT_ID", "AZURE_TENANT_ID"):
        require(bool(UUID.fullmatch(env.get(name, ""))), "Invalid configured Azure identity.")
    group, vm = env.get("LAB_RUNNER_RESOURCE_GROUP", ""), env.get("LAB_RUNNER_VM", "")
    require(bool(re.fullmatch(r"[A-Za-z0-9_-][A-Za-z0-9_.-]{0,89}", group))
            and not group.endswith(".")
            and bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", vm)),
            "Invalid precisely configured existing VM name or resource group.")
    vm_id = (f"/subscriptions/{env['AZURE_SUBSCRIPTION_ID']}/resourceGroups/{group}"
             f"/providers/Microsoft.Compute/virtualMachines/{vm}").lower()
    mask(vm_id)
    require(hashlib.sha256(vm_id.encode("utf-8")).hexdigest() == env.get("REVIEWED_VM_SHA256"),
            "Configured VM differs from the reviewed fingerprint.")
    return vm_id


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise GuardError("OIDC redirects are not permitted.")


def oidc_token(env: Mapping[str, str]) -> str:
    try:
        url = urlsplit(env.get("ACTIONS_ID_TOKEN_REQUEST_URL", ""))
        valid_endpoint = (url.scheme == "https" and url.hostname is not None
                          and url.hostname.endswith(".actions.githubusercontent.com")
                          and url.port in (None, 443) and not url.username
                          and not url.password and not url.fragment)
    except ValueError as error:
        raise GuardError("Invalid OIDC endpoint.") from error
    require(valid_endpoint, "OIDC endpoint is not an expected GitHub Actions HTTPS endpoint.")
    query = parse_qs(url.query, keep_blank_values=True)
    require("audience" not in query, "OIDC audience is ambiguous.")
    query["audience"] = ["api://AzureADTokenExchange"]
    request = Request(  # noqa: S310 - HTTPS Actions host validated above; redirects explicitly forbidden
        urlunsplit(url._replace(query=urlencode(query, doseq=True))),
        headers={"Authorization": f"bearer {env['ACTIONS_ID_TOKEN_REQUEST_TOKEN']}"},
    )
    try:
        with build_opener(NoRedirect()).open(request, timeout=30) as response:
            require(response.status == 200, "OIDC token request failed.")
            payload = object_value(parse_json(response.read(1024 * 1024).decode("utf-8")))
    except (OSError, ValueError, KeyError) as error:
        raise GuardError("OIDC token request failed; no fallback permitted.") from error
    token = payload.get("value")
    require(isinstance(token, str) and bool(token) and not any(char.isspace() for char in token),
            "OIDC response contains no valid token.")
    mask(token)
    return token


def start_vm(env: Mapping[str, str], get: Callable[[str], object] = github_get,
             execute: Callable[[list[str]], str] = command,
             token_request: Callable[[Mapping[str, str]], str] = oidc_token,
             clock: Callable[[], float] = time.monotonic,
             sleep: Callable[[float], None] = time.sleep) -> None:
    context(env)
    vm_id = target(env)
    verify_approval(env, get)
    token = token_request(env)
    execute(["az", "login", "--service-principal", "--username", env["AZURE_CLIENT_ID"],
             "--tenant", env["AZURE_TENANT_ID"], "--federated-token", token,
             "--allow-no-subscriptions", "--output", "none"])
    del token
    execute(["az", "account", "set", "--subscription", env["AZURE_SUBSCRIPTION_ID"]])
    actual = execute(["az", "vm", "show", "--ids", vm_id, "--query", "id", "--output", "tsv"])
    mask(actual)
    require(actual.lower() == vm_id, "Azure VM identity differs from the reviewed target.")
    state_args = ["az", "vm", "get-instance-view", "--ids", vm_id, "--query",
                  "instanceView.statuses[?starts_with(code, 'PowerState/')].code", "--output", "tsv"]

    def power_state() -> str:
        state = execute(state_args)
        require(state in {"PowerState/running", "PowerState/starting",
                          "PowerState/stopped", "PowerState/deallocated"},
                "VM power state is missing, ambiguous, or unsafe.")
        return state

    state = power_state()
    if state in {"PowerState/stopped", "PowerState/deallocated"}:
        execute(["az", "vm", "start", "--ids", vm_id, "--no-wait", "--output", "none"])
    deadline = clock() + 300
    while state != "PowerState/running":
        require(clock() + 10 <= deadline, "VM did not become running within five minutes.")
        sleep(10)
        state = power_state()
        require(clock() <= deadline, "VM confirmation exceeded the five-minute polling budget.")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        require(argv in (["preflight"], ["start"]), "Expected preflight or start mode.")
        if argv == ["preflight"]:
            run_id, sha, digest = context(os.environ)
            gate_id, _, configuration = verify_run(os.environ, github_get)
            with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as output:
                output.write(f"gate_id={gate_id}\ngate_configuration_sha256={configuration}\n")
            with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as summary:
                summary.write("Privately verify the existing VM and review this exact main commit. "
                              "Starting incurs VM compute cost; lab-deploy also has Lab app-write "
                              "and registry-push rights. Approve only the dedicated gate, using "
                              "this exact comment:\n\n")
                summary.write(f"`{approval_comment(run_id, sha, digest)}`\n")
        else:
            start_vm(os.environ)
            with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as summary:
                summary.write("Reviewed existing private runner VM confirmed running. "
                              "No Lab deploy or runner-registration smoke was performed.\n")
        return 0
    except (GuardError, OSError, KeyError) as error:
        # Never echo API bodies, inputs, subprocess output, identifiers or tokens.
        message = str(error) if isinstance(error, GuardError) else "Required local workflow context unavailable."
        print(f"::error::{message}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

"""Dormant #522 read-capability probe; not production approval evidence."""

import http.client
import json
import os
import re
import sys

REPOSITORY = "michael-rechani/foundry-agent-accelerator"
API_HOST = "api.github.com"
WORKFLOW_REF = f"{REPOSITORY}/.github/workflows/lab-approval-read-probe.yml@refs/heads/main"
TARGET = f"/repos/{REPOSITORY}/environments/copilot"
MAX_BYTES = 64 * 1024


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def invalid_constant(_):
    raise ValueError("Invalid JSON constant")


def read_capability(suffix, token):
    if suffix not in ("", "/secrets?per_page=1"):
        raise ValueError("Unknown probe endpoint")
    status = None
    connection = http.client.HTTPSConnection(API_HOST, timeout=10)
    try:
        connection.request("GET", TARGET + suffix, headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "lab-approval-read-probe",
        })
        response = connection.getresponse()
        status = response.status
        if status != 200 or response.headers.get_all("Link"):
            return status, None
        lengths = response.headers.get_all("Content-Length", [])
        encodings = response.headers.get_all("Transfer-Encoding", [])
        # A partial response must not be interpreted as positive evidence.
        if lengths:
            if encodings or len(lengths) != 1 or not re.fullmatch(r"[0-9]{1,5}", lengths[0]):
                return status, None
            expected = int(lengths[0])
            if expected > MAX_BYTES:
                return status, None
        elif [value.lower() for value in encodings] == ["chunked"]:
            expected = None
        else:
            return status, None
        payload = response.read(MAX_BYTES + 1)
        if len(payload) > MAX_BYTES or (expected is not None and len(payload) != expected):
            return status, None
        parsed = json.loads(payload.decode("utf-8"), object_pairs_hook=unique_object, parse_constant=invalid_constant)
        return status, parsed if isinstance(parsed, dict) else None
    except (OSError, http.client.HTTPException, ValueError, RecursionError):
        return status, None
    finally:
        connection.close()


def run_probe(token):
    policy_status, policy = read_capability("", token)
    inventory_status, inventory = read_capability("/secrets?per_page=1", token)
    rules = policy.get("protection_rules") if policy is not None else None
    policy_shape = (
        policy_status == 200 and policy is not None
        and policy.get("name") == "copilot"
        and type(policy.get("id")) is int and policy["id"] > 0
        and type(policy.get("can_admins_bypass")) is bool
        and isinstance(rules, list)
        and all(isinstance(rule, dict) and isinstance(rule.get("type"), str) for rule in rules)
    )
    empty_inventory_complete = (
        inventory_status == 200 and inventory is not None
        and type(inventory.get("total_count")) is int
        and inventory["total_count"] == 0 and inventory.get("secrets") == []
    )
    print(json.dumps({
        "policy_http_status": policy_status,
        "policy_shape": policy_shape,
        "inventory_http_status": inventory_status,
        "empty_inventory_complete": empty_inventory_complete,
    }))
    return 0 if policy_shape and empty_inventory_complete else 1


def main(environ=os.environ):
    if (
        environ.get("GITHUB_ACTIONS") != "true"
        or environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch"
        or environ.get("GITHUB_WORKFLOW_REF") != WORKFLOW_REF
        or environ.get("GITHUB_RUN_ATTEMPT") != "1"
        or not environ.get("PROBE_TOKEN")
    ):
        return 1
    return run_probe(environ["PROBE_TOKEN"])


if __name__ == "__main__":
    sys.exit(main())

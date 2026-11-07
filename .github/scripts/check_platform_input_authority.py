"""Compare one historical candidate with persisted platform state in memory."""

import json
import os
import re
import sys
from urllib import error

import check_lab_terraform_plan as lab
import check_state_backend as backend
from reconcile_runner_state import Blobs, GUID

INPUT = "dev.tfvars.json"
STATE = "dev.tfstate"


def strict_object(raw):
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result

    def reject_constant(_value):
        raise ValueError("Invalid JSON constant")

    value = json.loads(raw, object_pairs_hook=unique_pairs, parse_constant=reject_constant)
    if not isinstance(value, dict):
        raise backend.CheckError("Invalid protected object.")
    return value


def snapshot(blobs, name):
    if name not in (INPUT, STATE):
        raise backend.CheckError("Unapproved blob.")
    body, headers = backend.send(blobs.base + name, headers=blobs.headers)
    headers = {key.lower(): value for key, value in headers.items()}
    etag = headers.get("etag")
    if (not isinstance(etag, str) or not etag or headers.get("x-ms-blob-type") != "BlockBlob"
            or headers.get("x-ms-lease-status") != "unlocked"
            or "x-ms-meta-terraformlockid" in headers):
        raise backend.CheckError("Blob version or lock is ambiguous.")
    return body, etag


def guid(value):
    if not isinstance(value, str) or not re.fullmatch(GUID, value):
        raise backend.CheckError("Required identifier is missing or invalid.")
    return value.lower()


def target_instances(resources, resource_type, name):
    matches = [
        item for item in resources
        if item.get("mode") == "managed" and item.get("module") is None
        and item.get("type") == resource_type and item.get("name") == name
    ]
    if len(matches) != 1 or not isinstance(matches[0].get("instances"), list):
        raise backend.CheckError("Required state resource is missing or ambiguous.")
    instances = matches[0]["instances"]
    if (len(instances) != 1 or not isinstance(instances[0], dict)
            or instances[0].get("deposed") or instances[0].get("index_key") is not None
            or not isinstance(instances[0].get("attributes"), dict)):
        raise backend.CheckError("Required state resource is incomplete or ambiguous.")
    return instances[0]["attributes"]


def compare(input_bytes, state_bytes, subscription):
    inputs = strict_object(input_bytes)
    state = strict_object(state_bytes)
    input_subscription = guid(inputs.get("subscription_id"))
    principal = guid(inputs.get("deployment_principal_id"))
    if input_subscription != guid(subscription):
        raise backend.CheckError("Subscription mismatch.")
    disk = inputs.get("jumpbox_existing_os_disk")
    if inputs.get("enable_jumpbox") is not True or not isinstance(disk, dict):
        raise backend.CheckError("Jumpbox disk intent is missing.")
    disk_id, disk_name = disk.get("id"), disk.get("name")
    disk_size, disk_option = disk.get("size_gb", 127), disk.get("create_option", "FromImage")
    disk_match = re.fullmatch(
        r"/subscriptions/(" + GUID + r")/resourceGroups/[^/]+/providers/Microsoft\.Compute/disks/([^/]+)",
        disk_id if isinstance(disk_id, str) else "", flags=re.IGNORECASE,
    )
    if (disk.get("storage_account_type") != "Premium_LRS" or not disk_match
            or disk_match.group(1).lower() != input_subscription or not isinstance(disk_name, str)
            or disk_match.group(2).lower() != disk_name.lower()
            or type(disk_size) not in (int, float) or not 0 < disk_size < float("inf")
            or disk_option not in ("FromImage", "Attach")):
        raise backend.CheckError("Jumpbox disk intent is invalid or differs.")

    resources = state.get("resources")
    if (state.get("version") != 4 or type(state.get("serial")) is not int or state["serial"] < 0
            or not isinstance(state.get("lineage"), str) or not state["lineage"]
            or not isinstance(resources, list) or not resources
            or any(not isinstance(item, dict) for item in resources)):
        raise backend.CheckError("Platform state is invalid or empty.")
    group = target_instances(resources, "azurerm_resource_group", "this")
    group_id = group.get("id")
    if (not isinstance(group_id, str)
            or not re.fullmatch(r"/subscriptions/" + GUID + r"/resourceGroups/[^/]+", group_id, re.IGNORECASE)
            or group_id.split("/")[2].lower() != input_subscription):
        raise backend.CheckError("Platform state subscription mismatch.")
    role = target_instances(resources, "azurerm_role_assignment", "deployer_foundry_user")
    role_scope = role.get("scope")
    role_definition = role.get("role_definition_id")
    role_id = role.get("id")
    expected_scope = (
        re.escape(group_id) + r"/providers/Microsoft\.CognitiveServices/accounts/[^/]+/projects/[^/]+"
    )
    if (guid(role.get("principal_id")) != principal or not isinstance(role_scope, str)
            or not re.fullmatch(expected_scope, role_scope, flags=re.IGNORECASE)
            or not isinstance(role_id, str)
            or not re.fullmatch(re.escape(role_scope) + r"/providers/Microsoft\.Authorization/roleAssignments/"
                                + GUID, role_id, flags=re.IGNORECASE)
            or not isinstance(role_definition, str)
            or role_definition.lower() != (
                f"/subscriptions/{input_subscription}/providers/microsoft.authorization/"
                "roledefinitions/53ca6127-db72-4b80-b1b0-d745d6d5456d"
            )):
        raise backend.CheckError("Platform deployer assignment mismatch.")


def check(environ=os.environ):
    runtime = lab.configuration(environ)
    blobs = Blobs(runtime)
    first_input = snapshot(blobs, INPUT)
    first_state = snapshot(blobs, STATE)
    compare(first_input[0], first_state[0], runtime["AZURE_SUBSCRIPTION_ID"])
    second_state = snapshot(blobs, STATE)
    second_input = snapshot(blobs, INPUT)
    if first_input != second_input or first_state != second_state:
        raise backend.CheckError("Protected blob changed during comparison.")
    return "candidate_platform_comparison=matched"


def main():
    try:
        result = check()
    except (backend.CheckError, error.URLError, OSError, ValueError, SystemExit):
        print("candidate_platform_comparison_failed", file=sys.stderr)
        return 1
    print(result)
    return 0


def report_unexpected_failure(_type, _value, _traceback):
    print("candidate_platform_comparison_failed", file=sys.stderr)


if __name__ == "__main__":
    sys.excepthook = report_unexpected_failure
    sys.exit(main())

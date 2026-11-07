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


class CandidateError(backend.CheckError):
    pass


class PinError(CandidateError):
    pass


class StateError(backend.CheckError):
    pass


class SnapshotError(backend.CheckError):
    pass


class ReadError(backend.CheckError):
    pass


class PreconditionError(backend.CheckError):
    def __init__(self, *, input_mismatch=False, pin_invalid=False, secret_read=False, state_invalid=False):
        super().__init__("Candidate preconditions failed.")
        self.input_mismatch = input_mismatch
        self.pin_invalid = pin_invalid
        self.secret_read = secret_read
        self.state_invalid = state_invalid


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
    try:
        body, headers = backend.send(blobs.base + name, headers=blobs.headers)
    except (backend.CheckError, error.URLError, OSError, ValueError):
        raise ReadError("Read failed.") from None
    headers = {key.lower(): value for key, value in headers.items()}
    etag = headers.get("etag")
    if (not isinstance(etag, str) or not etag or headers.get("x-ms-blob-type") != "BlockBlob"
            or headers.get("x-ms-lease-status") != "unlocked"
            or "x-ms-meta-terraformlockid" in headers):
        raise SnapshotError("Blob version or lock is ambiguous.")
    return body, etag


def guid(value, error_type):
    if not isinstance(value, str) or not re.fullmatch(GUID, value):
        raise error_type("Required identifier is missing or invalid.")
    return value.lower()


def target_instances(resources, resource_type, name, index=None):
    matches = [
        item for item in resources
        if item.get("mode") == "managed" and item.get("module") is None
        and item.get("type") == resource_type and item.get("name") == name
    ]
    if len(matches) != 1 or not isinstance(matches[0].get("instances"), list):
        raise StateError("Required state resource is missing or ambiguous.")
    instances = matches[0]["instances"]
    if (len(instances) != 1 or not isinstance(instances[0], dict)
            or instances[0].get("deposed") or instances[0].get("index_key") != index
            or not isinstance(instances[0].get("attributes"), dict)):
        raise StateError("Required state resource is incomplete or ambiguous.")
    return instances[0]["attributes"]


def compare(input_bytes, state_bytes, subscription):
    try:
        inputs = strict_object(input_bytes)
    except (backend.CheckError, ValueError, UnicodeError):
        raise CandidateError("Invalid input.") from None
    secret_read = inputs.get("enable_jumpbox", False) is True and inputs.get("jumpbox_admin_secret") is not None
    try:
        state = strict_object(state_bytes)
    except (backend.CheckError, ValueError, UnicodeError):
        if secret_read:
            raise PreconditionError(secret_read=True, state_invalid=True) from None
        raise StateError("Invalid state.") from None
    try:
        compare_validated(inputs, state, subscription)
    except PinError:
        if secret_read:
            raise PreconditionError(pin_invalid=True, secret_read=True) from None
        raise
    except CandidateError:
        if secret_read:
            raise PreconditionError(input_mismatch=True, secret_read=True) from None
        raise
    except StateError:
        if secret_read:
            raise PreconditionError(secret_read=True, state_invalid=True) from None
        raise
    if secret_read:
        raise PreconditionError(secret_read=True)


def compare_validated(inputs, state, subscription):
    input_subscription = guid(inputs.get("subscription_id"), CandidateError)
    principal = guid(inputs.get("deployment_principal_id"), PinError)
    if input_subscription != guid(subscription, StateError):
        raise CandidateError("Subscription mismatch.")
    disk = inputs.get("jumpbox_existing_os_disk")
    if inputs.get("enable_jumpbox") is not True or not isinstance(disk, dict):
        raise CandidateError("Jumpbox disk intent is missing.")
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
        raise CandidateError("Jumpbox disk intent is invalid or differs.")

    resources = state.get("resources")
    if (state.get("version") != 4 or type(state.get("serial")) is not int or state["serial"] < 0
            or not isinstance(state.get("lineage"), str) or not state["lineage"]
            or not isinstance(resources, list) or not resources
            or any(not isinstance(item, dict) for item in resources)):
        raise StateError("Platform state is invalid or empty.")
    group = target_instances(resources, "azurerm_resource_group", "this")
    group_id = group.get("id")
    if (not isinstance(group_id, str)
            or not re.fullmatch(r"/subscriptions/" + GUID + r"/resourceGroups/[^/]+", group_id, re.IGNORECASE)
            or group_id.split("/")[2].lower() != input_subscription):
        raise StateError("Platform state subscription mismatch.")
    outputs = state.get("outputs")
    if not isinstance(outputs, dict):
        raise StateError("Platform outputs are invalid.")
    account_output, project_output = outputs.get("foundry_account_id"), outputs.get("foundry_project_id")
    if (not isinstance(account_output, dict) or not isinstance(project_output, dict)
            or account_output.get("type") != "string" or project_output.get("type") != "string"):
        raise StateError("Platform outputs are incomplete.")
    account_id, project_id = account_output.get("value"), project_output.get("value")
    if (not isinstance(account_id, str)
            or not re.fullmatch(re.escape(group_id) + r"/providers/Microsoft\.CognitiveServices/accounts/[^/]+",
                                account_id, re.IGNORECASE)
            or not isinstance(project_id, str)
            or not re.fullmatch(re.escape(account_id) + r"/projects/[^/]+", project_id, re.IGNORECASE)):
        raise StateError("Platform outputs are inconsistent.")
    role = target_instances(resources, "azurerm_role_assignment", "deployer_foundry_user")
    role_scope = role.get("scope")
    role_definition = role.get("role_definition_id")
    role_id = role.get("id")
    if (not isinstance(role_scope, str) or role_scope.lower() != project_id.lower()
            or not isinstance(role_id, str)
            or not re.fullmatch(re.escape(role_scope) + r"/providers/Microsoft\.Authorization/roleAssignments/"
                                + GUID, role_id, flags=re.IGNORECASE)
            or not isinstance(role_definition, str)
            or role_definition.lower() != (
                f"/subscriptions/{input_subscription}/providers/microsoft.authorization/"
                "roledefinitions/53ca6127-db72-4b80-b1b0-d745d6d5456d"
            )):
        raise StateError("Platform deployer assignment is invalid.")
    if guid(role.get("principal_id"), StateError) != principal:
        raise CandidateError("Platform deployer assignment mismatch.")
    jumpbox = target_instances(resources, "azapi_resource", "jumpbox", index=0)
    body = jumpbox.get("body")
    if isinstance(body, str):
        try:
            body = strict_object(body)
        except (backend.CheckError, ValueError, UnicodeError):
            raise StateError("Jumpbox body is invalid.") from None
    if not isinstance(body, dict):
        raise StateError("Jumpbox body is missing.")
    properties = body.get("properties")
    storage = properties.get("storageProfile") if isinstance(properties, dict) else None
    os_disk = storage.get("osDisk") if isinstance(storage, dict) else None
    managed_disk = os_disk.get("managedDisk") if isinstance(os_disk, dict) else None
    state_disk_id = managed_disk.get("id") if isinstance(managed_disk, dict) else None
    state_disk_name = os_disk.get("name") if isinstance(os_disk, dict) else None
    if not isinstance(state_disk_id, str) or not isinstance(state_disk_name, str):
        raise StateError("Jumpbox disk identity is incomplete.")
    if state_disk_id.lower() != disk_id.lower() or state_disk_name.lower() != disk_name.lower():
        raise CandidateError("Jumpbox disk identity mismatch.")


def check(environ=os.environ):
    try:
        runtime = lab.configuration(environ)
        blobs = Blobs(runtime)
    except (backend.CheckError, error.URLError, OSError, ValueError):
        raise ReadError("Authentication or configuration failed.") from None
    first_input = snapshot(blobs, INPUT)
    first_state = snapshot(blobs, STATE)
    comparison_failure = None
    override = None
    try:
        inputs = strict_object(first_input[0])
        override = "explicit" if "model_router_deployment" in inputs else "absent"
        compare(first_input[0], first_state[0], runtime["AZURE_SUBSCRIPTION_ID"])
    except (CandidateError, StateError, PreconditionError) as exc:
        comparison_failure = exc
    except (ValueError, UnicodeError, backend.CheckError):
        comparison_failure = CandidateError("Invalid input.")
    second_state = snapshot(blobs, STATE)
    second_input = snapshot(blobs, INPUT)
    if first_input != second_input or first_state != second_state:
        raise SnapshotError("Protected blob changed during comparison.")
    if comparison_failure:
        comparison_failure.router_override = override
        raise comparison_failure from None
    return override


def main():
    try:
        override = check()
    except PreconditionError as exc:
        if exc.input_mismatch:
            print("candidate_platform_comparison_failed=input_mismatch_or_missing", file=sys.stderr)
        if exc.pin_invalid:
            print("candidate_platform_comparison_failed=identity_pin_missing_or_invalid", file=sys.stderr)
        if exc.secret_read:
            print("candidate_platform_comparison_failed=secret_read_review_required", file=sys.stderr)
        if exc.state_invalid:
            print("candidate_platform_comparison_failed=protected_state_invalid", file=sys.stderr)
        print_router_override(exc)
        return 1
    except PinError as exc:
        print("candidate_platform_comparison_failed=identity_pin_missing_or_invalid", file=sys.stderr)
        print_router_override(exc)
        return 1
    except CandidateError as exc:
        print("candidate_platform_comparison_failed=input_mismatch_or_missing", file=sys.stderr)
        print_router_override(exc)
        return 1
    except StateError as exc:
        print("candidate_platform_comparison_failed=protected_state_invalid", file=sys.stderr)
        print_router_override(exc)
        return 1
    except SnapshotError:
        print("candidate_platform_comparison_failed=snapshot_unstable", file=sys.stderr)
        return 1
    except ReadError:
        print("candidate_platform_comparison_failed=read_failure", file=sys.stderr)
        return 1
    except (backend.CheckError, error.URLError, OSError, ValueError, SystemExit):
        print("candidate_platform_comparison_failed=unexpected", file=sys.stderr)
        return 1
    print("candidate_platform_comparison=matched")
    print(f"candidate_router_override={override}")
    return 0


def print_router_override(exc):
    override = getattr(exc, "router_override", None)
    if override in ("absent", "explicit"):
        print(f"candidate_router_override={override}", file=sys.stderr)


def report_unexpected_failure(_type, _value, _traceback):
    print("candidate_platform_comparison_failed=unexpected", file=sys.stderr)


if __name__ == "__main__":
    sys.excepthook = report_unexpected_failure
    sys.exit(main())

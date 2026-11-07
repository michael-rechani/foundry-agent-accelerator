"""Compare one historical candidate with persisted platform state in memory."""

import json
import math
import os
import re
import sys
from urllib import error

import check_lab_terraform_plan as lab
import check_state_backend as backend
from reconcile_runner_state import Blobs, GUID

INPUT = "dev.tfvars.json"
STATE = "dev.tfstate"
MODULE_ADDRESS = re.compile(r'module\.[\w-]+(?:\[(?:[0-9]+|"(?:[^"\\]|\\.)*")\])?'
                            r'(?:\.module\.[\w-]+(?:\[(?:[0-9]+|"(?:[^"\\]|\\.)*")\])?)*')
PROVIDER_ADDRESS = re.compile(
    r'(?:module\.[A-Za-z_][A-Za-z0-9_-]*\.)*'
    r'provider\["[a-z0-9][a-z0-9.-]*/[a-z0-9][a-z0-9-]*/[a-z0-9][a-z0-9-]*"\]'
    r'(?:\.[A-Za-z_][A-Za-z0-9_-]*)?'
)


class CandidateError(backend.CheckError):
    pass


class PinError(CandidateError):
    pass


class StateError(backend.CheckError):
    pass


class StateEnvelopeError(StateError):
    pass


class StateInventoryError(StateError):
    pass


class StateOutputsError(StateError):
    pass


class StateRoleError(StateError):
    pass


class StateRoleScopeError(StateError):
    pass


class StateDiskError(StateError):
    pass


DISK_FAILURE_CATEGORIES = frozenset({
    "disk_resource_missing", "disk_resource_multiple", "disk_instances_invalid",
    "disk_instance_missing", "disk_instance_multiple", "disk_instance_invalid",
    "disk_instance_deposed", "disk_instance_index_invalid", "disk_attributes_invalid",
    "disk_body_missing", "disk_body_invalid", "disk_body_json_invalid", "disk_dynamic_invalid",
    "disk_parent_missing", "disk_parent_invalid", "disk_storage_missing", "disk_storage_invalid",
    "disk_os_missing", "disk_os_invalid", "disk_managed_missing", "disk_managed_invalid",
    "disk_id_missing", "disk_id_invalid", "disk_name_missing", "disk_name_invalid",
})


class StateDiskDetailError(StateDiskError):
    def __init__(self, category):
        if category not in DISK_FAILURE_CATEGORIES:
            raise ValueError("Invalid diagnostic category.")
        super().__init__("Disk representation is invalid.")
        self.category = category


STATE_FAILURE_CATEGORIES = {
    StateEnvelopeError: "state_envelope_invalid",
    StateInventoryError: "state_inventory_invalid",
    StateOutputsError: "state_outputs_invalid",
    StateRoleError: "state_role_invalid",
    StateRoleScopeError: "state_role_scope_mismatch",
    StateDiskError: "state_disk_invalid",
}


class SnapshotError(backend.CheckError):
    pass


class ReadError(backend.CheckError):
    pass


class PreconditionError(backend.CheckError):
    def __init__(self, *, input_mismatch=False, pin_invalid=False, secret_read=False, state_invalid=False,
                 state_error=None, disk_category=None):
        super().__init__("Candidate preconditions failed.")
        self.input_mismatch = input_mismatch
        self.pin_invalid = pin_invalid
        self.secret_read = secret_read
        self.state_invalid = state_invalid
        self.state_error = state_error
        self.disk_category = disk_category


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


def target_instances(resources, resource_type, name, index=None, error_type=StateInventoryError):
    matches = [
        item for item in resources
        if item.get("mode") == "managed" and item.get("module") is None
        and item.get("type") == resource_type and item.get("name") == name
    ]
    if len(matches) != 1 or not isinstance(matches[0].get("instances"), list):
        raise error_type("Required state resource is missing or ambiguous.")
    instances = matches[0]["instances"]
    if (len(instances) != 1 or not isinstance(instances[0], dict)
            or instances[0].get("deposed") or instances[0].get("index_key") != index
            or not isinstance(instances[0].get("attributes"), dict)):
        raise error_type("Required state resource is incomplete or ambiguous.")
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
            raise PreconditionError(secret_read=True, state_invalid=True, state_error=StateEnvelopeError) from None
        raise StateEnvelopeError("Invalid state.") from None
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
    except StateError as exc:
        if secret_read:
            raise PreconditionError(secret_read=True, state_invalid=True, state_error=type(exc),
                                    disk_category=getattr(exc, "category", None)) from None
        raise
    if secret_read:
        raise PreconditionError(secret_read=True)


def compare_validated(inputs, state, subscription):
    input_subscription = guid(inputs.get("subscription_id"), CandidateError)
    principal = guid(inputs.get("deployment_principal_id"), PinError)
    if input_subscription != guid(subscription, StateEnvelopeError):
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
            or not isinstance(state.get("lineage"), str) or not state["lineage"]):
        raise StateEnvelopeError("Platform state is invalid or empty.")
    if (not isinstance(resources, list) or not resources
            or any(not isinstance(item, dict) for item in resources)):
        raise StateInventoryError("Platform inventory is invalid or empty.")
    group = target_instances(resources, "azurerm_resource_group", "this")
    group_id = group.get("id")
    if (not isinstance(group_id, str)
            or not re.fullmatch(r"/subscriptions/" + GUID + r"/resourceGroups/[^/]+", group_id, re.IGNORECASE)
            or group_id.split("/")[2].lower() != input_subscription):
        raise StateInventoryError("Platform state subscription mismatch.")
    outputs = state.get("outputs")
    if not isinstance(outputs, dict):
        raise StateOutputsError("Platform outputs are invalid.")
    account_output, project_output = outputs.get("foundry_account_id"), outputs.get("foundry_project_id")
    if (not isinstance(account_output, dict) or not isinstance(project_output, dict)
            or account_output.get("type") != "string" or project_output.get("type") != "string"):
        raise StateOutputsError("Platform outputs are incomplete.")
    account_id, project_id = account_output.get("value"), project_output.get("value")
    if (not isinstance(account_id, str)
            or not re.fullmatch(re.escape(group_id) + r"/providers/Microsoft\.CognitiveServices/accounts/[^/]+",
                                account_id, re.IGNORECASE)
            or not isinstance(project_id, str)
            or not re.fullmatch(re.escape(account_id) + r"/projects/[^/]+", project_id, re.IGNORECASE)):
        raise StateOutputsError("Platform outputs are inconsistent.")
    role = target_instances(resources, "azurerm_role_assignment", "deployer_foundry_user",
                            error_type=StateRoleError)
    role_scope = role.get("scope")
    role_definition = role.get("role_definition_id")
    role_id = role.get("id")
    if not isinstance(role_scope, str):
        raise StateRoleError("Platform deployer assignment is invalid.")
    if role_scope.lower() != project_id.lower():
        raise StateRoleScopeError("Platform deployer assignment scope differs.")
    if (not isinstance(role_id, str)
            or not re.fullmatch(re.escape(role_scope) + r"/providers/Microsoft\.Authorization/roleAssignments/"
                                + GUID, role_id, flags=re.IGNORECASE)
            or not isinstance(role_definition, str)
            or role_definition.lower() != (
                f"/subscriptions/{input_subscription}/providers/microsoft.authorization/"
                "roledefinitions/53ca6127-db72-4b80-b1b0-d745d6d5456d"
            )):
        raise StateRoleError("Platform deployer assignment is invalid.")
    if guid(role.get("principal_id"), StateRoleError) != principal:
        raise CandidateError("Platform deployer assignment mismatch.")
    jumpbox = jumpbox_attributes(resources)
    body = jumpbox.get("body")
    if "body" not in jumpbox or body is None:
        raise StateDiskDetailError("disk_body_missing")
    if isinstance(body, str):
        try:
            body = strict_object(body)
        except (backend.CheckError, ValueError, UnicodeError):
            raise StateDiskDetailError("disk_body_json_invalid") from None
    if not isinstance(body, dict):
        raise StateDiskDetailError("disk_body_invalid")
    if "type" in body or "value" in body:
        if (set(body) != {"type", "value"} or not valid_cty_type(body["type"])
                or not isinstance(body["type"], list) or body["type"][0] not in ("object", "map")
                or not valid_cty_value(body["type"], body["value"])
                or not isinstance(body["value"], dict)):
            raise StateDiskDetailError("disk_dynamic_invalid")
        body = unwrap_cty_value(body["type"], body["value"])
    properties = disk_object(body, "properties", "disk_parent_missing", "disk_parent_invalid")
    storage = disk_object(properties, "storageProfile", "disk_storage_missing", "disk_storage_invalid")
    os_disk = disk_object(storage, "osDisk", "disk_os_missing", "disk_os_invalid")
    managed_disk = disk_object(os_disk, "managedDisk", "disk_managed_missing", "disk_managed_invalid")
    state_disk_id = disk_string(managed_disk, "id", "disk_id_missing", "disk_id_invalid")
    state_disk_name = disk_string(os_disk, "name", "disk_name_missing", "disk_name_invalid")
    if state_disk_id.lower() != disk_id.lower() or state_disk_name.lower() != disk_name.lower():
        raise CandidateError("Jumpbox disk identity mismatch.")


def valid_cty_type(descriptor, depth=0):
    if depth > 64:
        return False
    if isinstance(descriptor, str):
        return descriptor in ("string", "number", "bool", "dynamic")
    if not isinstance(descriptor, list) or len(descriptor) != 2 or not isinstance(descriptor[0], str):
        return False
    kind, element = descriptor
    if kind == "object":
        return isinstance(element, dict) and all(valid_cty_type(item, depth + 1) for item in element.values())
    if kind == "tuple":
        return isinstance(element, list) and all(valid_cty_type(item, depth + 1) for item in element)
    if kind in ("list", "set", "map"):
        return valid_cty_type(element, depth + 1)
    return False


def valid_cty_value(descriptor, value, depth=0):
    if depth > 64:
        return False
    if value is None:
        return True
    if descriptor == "dynamic":
        return (isinstance(value, dict) and set(value) == {"type", "value"}
                and valid_cty_type(value["type"], depth + 1)
                and valid_cty_value(value["type"], value["value"], depth + 1))
    if descriptor == "string":
        return isinstance(value, str)
    if descriptor == "bool":
        return type(value) is bool
    if descriptor == "number":
        return type(value) in (int, float) and (type(value) is int or math.isfinite(value))
    if not isinstance(descriptor, list) or len(descriptor) != 2:
        return False
    kind, element = descriptor
    if kind == "object":
        return (isinstance(value, dict) and set(value) == set(element)
                and all(valid_cty_value(item, value[key], depth + 1) for key, item in element.items()))
    if kind == "map":
        return isinstance(value, dict) and all(valid_cty_value(element, item, depth + 1) for item in value.values())
    if kind == "tuple":
        return (isinstance(value, list) and len(value) == len(element)
                and all(valid_cty_value(item_type, item, depth + 1)
                        for item_type, item in zip(element, value, strict=True)))
    if kind == "set":
        return (isinstance(value, list) and all(valid_cty_value(element, item, depth + 1) for item in value)
                and all(item not in value[:index] for index, item in enumerate(value)))
    if kind == "list":
        return isinstance(value, list) and all(valid_cty_value(element, item, depth + 1) for item in value)
    return False


def unwrap_cty_value(descriptor, value):
    if value is None:
        return None
    if descriptor == "dynamic":
        return unwrap_cty_value(value["type"], value["value"])
    if not isinstance(descriptor, list):
        return value
    kind, element = descriptor
    if kind == "object":
        return {key: unwrap_cty_value(item, value[key]) for key, item in element.items()}
    if kind == "map":
        return {key: unwrap_cty_value(element, item) for key, item in value.items()}
    if kind == "tuple":
        return [unwrap_cty_value(item_type, item) for item_type, item in zip(element, value, strict=True)]
    return [unwrap_cty_value(element, item) for item in value]


def disk_object(parent, key, missing, invalid):
    value = parent.get(key)
    if value is None:
        raise StateDiskDetailError(missing)
    if not isinstance(value, dict):
        raise StateDiskDetailError(invalid)
    return value


def disk_string(parent, key, missing, invalid):
    value = parent.get(key)
    if value is None:
        raise StateDiskDetailError(missing)
    if not isinstance(value, str):
        raise StateDiskDetailError(invalid)
    return value


def jumpbox_attributes(resources):
    matches = [
        item for item in resources
        if item.get("mode") == "managed" and item.get("module") is None
        and item.get("type") == "azapi_resource" and item.get("name") == "jumpbox"
    ]
    if not matches:
        raise StateDiskDetailError("disk_resource_missing")
    if len(matches) != 1:
        raise StateDiskDetailError("disk_resource_multiple")
    instances = matches[0].get("instances")
    if not isinstance(instances, list):
        raise StateDiskDetailError("disk_instances_invalid")
    if not instances:
        raise StateDiskDetailError("disk_instance_missing")
    if len(instances) != 1:
        raise StateDiskDetailError("disk_instance_multiple")
    instance = instances[0]
    if not isinstance(instance, dict):
        raise StateDiskDetailError("disk_instance_invalid")
    if instance.get("deposed"):
        raise StateDiskDetailError("disk_instance_deposed")
    if type(instance.get("index_key")) is not int or instance["index_key"] != 0:
        raise StateDiskDetailError("disk_instance_index_invalid")
    attributes = instance.get("attributes")
    if not isinstance(attributes, dict):
        raise StateDiskDetailError("disk_attributes_invalid")
    return attributes


def inventory(state):
    ambiguous = ("ambiguous", "ambiguous")
    resources = state.get("resources")
    if (type(state.get("version")) is not int or state["version"] != 4
            or type(state.get("serial")) is not int or state["serial"] < 0
            or not isinstance(state.get("lineage"), str) or not state["lineage"]
            or not isinstance(resources, list) or not resources):
        return ambiguous
    seen = set()
    present = set()
    for resource in resources:
        if not isinstance(resource, dict):
            return ambiguous
        mode, kind, name = resource.get("mode"), resource.get("type"), resource.get("name")
        module = resource.get("module")
        instances = resource.get("instances")
        if (mode not in ("managed", "data") or not isinstance(kind, str) or not kind
                or not isinstance(name, str) or not name
                or ("module" in resource and (not isinstance(module, str) or not MODULE_ADDRESS.fullmatch(module)))
                or not isinstance(resource.get("provider"), str)
                or not PROVIDER_ADDRESS.fullmatch(resource["provider"])
                or not isinstance(instances, list)):
            return ambiguous
        address = (module, mode, kind, name)
        if address in seen:
            return ambiguous
        seen.add(address)
        keys = set()
        key_type = None
        for instance in instances:
            if (not isinstance(instance, dict) or "deposed" in instance
                    or not isinstance(instance.get("attributes"), dict)
                    or ("schema_version" in instance and
                        (type(instance["schema_version"]) is not int or instance["schema_version"] < 0))
                    or ("sensitive_attributes" in instance and not isinstance(instance["sensitive_attributes"], list))
                    or ("dependencies" in instance and
                        (not isinstance(instance["dependencies"], list)
                         or any(not isinstance(value, str) or not value for value in instance["dependencies"])))
                    or ("status" in instance and instance["status"] != "tainted")):
                return ambiguous
            key = instance.get("index_key")
            if "index_key" in instance:
                if not (type(key) is int and key >= 0 or isinstance(key, str)):
                    return ambiguous
                if key_type is not None and type(key) is not key_type:
                    return ambiguous
                key_type = type(key)
            elif len(instances) != 1:
                return ambiguous
            if key in keys:
                return ambiguous
            keys.add(key)
        if mode == "managed" and instances:
            present.add(kind)
    return tuple("present" if kind in present else "absent"
                 for kind in ("azurerm_storage_account", "azurerm_api_management"))


def pinned_secret_read(inputs):
    enabled = inputs.get("enable_jumpbox", False)
    if type(enabled) is not bool:
        return "ambiguous"
    secret = inputs.get("jumpbox_admin_secret")
    if secret is None:
        return "absent"
    if not isinstance(secret, dict):
        return "ambiguous"
    vault, name, version = secret.get("key_vault_id"), secret.get("name"), secret.get("version")
    if (not isinstance(vault, str)
            or not re.fullmatch(r"/subscriptions/[^/]+/resourceGroups/[^/]+/providers/Microsoft.KeyVault/vaults/[^/]+",
                                vault, re.IGNORECASE)
            or not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9-]{1,127}", name)
            or not isinstance(version, str) or not re.fullmatch(r"[a-fA-F0-9]{32}", version)):
        return "ambiguous"
    return "present" if enabled else "absent"


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
    categories = None
    try:
        inputs = strict_object(first_input[0])
        override = "explicit" if "model_router_deployment" in inputs else "absent"
        try:
            state = strict_object(first_state[0])
        except (backend.CheckError, ValueError, UnicodeError):
            state = {}
        categories = (*inventory(state), pinned_secret_read(inputs))
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
        if (isinstance(comparison_failure, PreconditionError) and comparison_failure.secret_read
                and not (comparison_failure.input_mismatch or comparison_failure.pin_invalid
                         or comparison_failure.state_invalid)):
            comparison_failure.inventory_categories = categories
        raise comparison_failure from None
    return override, categories


def main():
    try:
        override, categories = check()
    except PreconditionError as exc:
        if exc.input_mismatch:
            print("candidate_platform_comparison_failed=input_mismatch_or_missing", file=sys.stderr)
        if exc.pin_invalid:
            print("candidate_platform_comparison_failed=identity_pin_missing_or_invalid", file=sys.stderr)
        if exc.secret_read:
            print("candidate_platform_comparison_failed=secret_read_review_required", file=sys.stderr)
        if exc.state_invalid:
            print_state_failure(exc.state_error, exc.disk_category)
        print_router_override(exc)
        print_inventory(getattr(exc, "inventory_categories", None), file=sys.stderr)
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
        print_state_failure(type(exc), getattr(exc, "category", None))
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
    if not valid_inventory_categories(categories):
        print("candidate_platform_comparison_failed=inventory_result_invalid", file=sys.stderr)
        return 1
    print("candidate_platform_comparison=matched")
    print(f"candidate_router_override={override}")
    print_inventory(categories, file=sys.stdout)
    return 0


def valid_inventory_categories(categories):
    return (isinstance(categories, tuple) and len(categories) == 3
            and all(isinstance(category, str) and category in ("present", "absent", "ambiguous")
                    for category in categories))


def print_inventory(categories, *, file):
    if not valid_inventory_categories(categories):
        return
    if categories[0] == "present":
        print("candidate_storage_inventory=present", file=file)
    elif categories[0] == "absent":
        print("candidate_storage_inventory=absent", file=file)
    else:
        print("candidate_storage_inventory=ambiguous", file=file)
    if categories[1] == "present":
        print("candidate_apim_inventory=present", file=file)
    elif categories[1] == "absent":
        print("candidate_apim_inventory=absent", file=file)
    else:
        print("candidate_apim_inventory=ambiguous", file=file)
    if categories[2] == "present":
        print("candidate_pinned_secret_read=present", file=file)
    elif categories[2] == "absent":
        print("candidate_pinned_secret_read=absent", file=file)
    else:
        print("candidate_pinned_secret_read=ambiguous", file=file)


def print_router_override(exc):
    override = getattr(exc, "router_override", None)
    if override in ("absent", "explicit"):
        print(f"candidate_router_override={override}", file=sys.stderr)


def print_state_failure(error_type, disk_category=None):
    if error_type is StateDiskDetailError and disk_category in DISK_FAILURE_CATEGORIES:
        category = disk_category
    else:
        category = STATE_FAILURE_CATEGORIES.get(error_type, "protected_state_invalid")
    print(f"candidate_platform_comparison_failed={category}", file=sys.stderr)


def report_unexpected_failure(_type, _value, _traceback):
    print("candidate_platform_comparison_failed=unexpected", file=sys.stderr)


if __name__ == "__main__":
    sys.excepthook = report_unexpected_failure
    sys.exit(main())

"""Adopt Reader grants or reconcile runner state without infrastructure writes."""

import hashlib
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

from check_state_backend import CheckError, azure_token, send, validate_backend

GUID = r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}"
READER_ROLE = "acdd72a7-3385-48ef-bd42-f606fba81ae7"
ROOT = Path(__file__).resolve().parents[2]
RUNNER_KEYS = {
    "subscription_id", "resource_group_name", "virtual_network_name", "nat_gateway_name",
    "approve_shared_egress", "subnet_address_prefix", "base_name", "environment",
    "runner_resource_group_name", "admin_username", "admin_ssh_public_key", "vm_size",
    "os_disk_size_gb", "os_disk_storage_account_type", "patch_mode",
    "bypass_platform_safety_checks_on_user_schedule", "github_repository", "auto_shutdown",
    "registry_private_endpoint_ips", "foundry_private_endpoint_ips", "state_backend_private_endpoint_ips",
    "tags",
}


def object_json(raw):
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeError):
        raise CheckError("Protected JSON is invalid; its contents were not logged.") from None
    if not isinstance(value, dict):
        raise CheckError("Protected JSON must be an object.")
    return value


def scratch_path(environ):
    root = Path(environ.get("RUNNER_TEMP", ""))
    if not root.is_absolute() or not root.is_dir():
        raise CheckError("The private runner temporary directory is required.")
    parts = [environ.get(name, "") for name in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT")]
    if any(not re.fullmatch(r"[0-9]+", part) for part in parts):
        raise CheckError("An exact GitHub run/attempt identity is required for private cleanup.")
    return root / ("tf-reconcile-" + "-".join(parts))


def cleanup(environ=os.environ):
    folder = scratch_path(environ)
    if folder.is_symlink():
        raise CheckError("Refusing to clean a redirected scratch directory.")
    if folder.exists():
        shutil.rmtree(folder)


@contextmanager
def private_scratch(environ):
    folder = scratch_path(environ)
    folder.mkdir(mode=0o700, exist_ok=False)
    try:
        yield folder
    finally:
        cleanup(environ)


def configuration(environ):
    validate_backend(environ)
    subscription = environ.get("AZURE_SUBSCRIPTION_ID", "")
    if not re.fullmatch(GUID, subscription):
        raise CheckError("An explicit subscription GUID is required.")
    config = object_json(environ.get("TF_RUNNER_PLAN_CONFIG", ""))
    if set(config) != {"reader", "runner"}:
        raise CheckError("Configuration must contain exactly reader and runner inputs.")
    reader, runner = config["reader"], config["runner"]
    if not isinstance(reader, dict) or set(reader) != {
        "subscription_id", "principal_id", "scopes", "existing_assignment_ids",
    } or not isinstance(runner, dict) or set(runner) != RUNNER_KEYS:
        raise CheckError("The reviewed input shape is incomplete or contains unsupported fields.")
    if (reader["subscription_id"] != subscription or runner["subscription_id"] != subscription
            or not isinstance(reader["principal_id"], str)
            or not re.fullmatch(GUID, reader["principal_id"])):
        raise CheckError("Input subscriptions and the explicit principal must match the approved configuration.")
    scopes, assignments = reader["scopes"], reader["existing_assignment_ids"]
    if not isinstance(scopes, dict) or not isinstance(assignments, dict) or set(scopes) != {
        "runner", "network", "nat",
    } or set(assignments) != set(scopes):
        raise CheckError("Exactly three existing scoped Reader assignments are required.")
    for name in ("resource_group_name", "runner_resource_group_name", "virtual_network_name",
                 "nat_gateway_name", "base_name", "environment"):
        if not isinstance(runner[name], str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", runner[name]):
            raise CheckError("Invalid resource name in reviewed runner inputs.")
    prefix = f"/subscriptions/{subscription}/resourceGroups/"
    expected_scopes = {
        "runner": prefix + runner["runner_resource_group_name"],
        "network": prefix + runner["resource_group_name"] + "/providers/Microsoft.Network/virtualNetworks/"
        + runner["virtual_network_name"],
        "nat": prefix + runner["resource_group_name"] + "/providers/Microsoft.Network/natGateways/"
        + runner["nat_gateway_name"],
    }
    for key in scopes:
        if (not isinstance(scopes[key], str) or not isinstance(assignments[key], str)
                or scopes[key].lower() != expected_scopes[key].lower()
                or not re.fullmatch(re.escape(scopes[key]) + r"/providers/Microsoft.Authorization/roleAssignments/"
                                    + GUID, assignments[key], flags=re.IGNORECASE)):
            raise CheckError("Reader import IDs must match the runner's exact existing resource scopes.")
    if (runner["environment"] != "dev" or runner["github_repository"] != environ.get("GITHUB_REPOSITORY")
            or runner["approve_shared_egress"] is not True
            or runner["state_backend_private_endpoint_ips"] != [environ["TF_STATE_PRIVATE_ENDPOINT"]]
            or not runner["registry_private_endpoint_ips"] or not runner["foundry_private_endpoint_ips"]):
        raise CheckError("The existing dev runner, shared egress and all private HTTPS exceptions must be preserved.")
    return config


class Blobs:
    def __init__(self, environ):
        host = validate_backend(environ)
        self.base = f"https://{host}/{environ['TF_STATE_CONTAINER']}/ai-foundry/"
        self.headers = {
            "Authorization": f"Bearer {azure_token(environ)}",
            "x-ms-version": "2023-11-03",
        }

    def read(self, name):
        body, _ = send(self.base + name, headers=self.headers)
        return body

    def inputs(self, name, values):
        encoded = json.dumps(values, sort_keys=True, indent=2).encode() + b"\n"
        existing, headers = send(self.base + name, headers=self.headers, expected=(200, 404))
        code = headers.get("x-ms-error-code")
        if code == "BlobNotFound":
            # Do not retry PUTs against an existing blob: Azure can return 409, not 412.
            send(self.base + name, method="PUT", headers={
                **self.headers, "x-ms-blob-type": "BlockBlob", "If-None-Match": "*",
            }, data=encoded, expected=(201, 412))
            existing = self.read(name)
        elif code:
            raise CheckError("Canonical input lookup returned an unexpected storage error.")
        if object_json(existing) != values:
            raise CheckError("Existing canonical inputs differ; a separate reviewed input change is required.")
        return existing


def populated_runner_state(raw, runner):
    state = object_json(raw)
    resources = {
        (item.get("type"), item.get("name")): item
        for item in state.get("resources", []) if item.get("mode") == "managed"
    }
    if state.get("version") != 4 or not isinstance(state.get("serial"), int) or not state.get("lineage"):
        raise CheckError("The selected existing runner state is invalid or empty.")
    expected = {
        ("azurerm_resource_group", "runner"): (
            f"/subscriptions/{runner['subscription_id']}/resourceGroups/{runner['runner_resource_group_name']}"
        ),
        ("azurerm_linux_virtual_machine", "runner"): (
            f"/subscriptions/{runner['subscription_id']}/resourceGroups/{runner['runner_resource_group_name']}"
            f"/providers/Microsoft.Compute/virtualMachines/vm-runner-{runner['base_name']}-{runner['environment']}"
        ),
    }
    for address, resource_id in expected.items():
        instances = resources.get(address, {}).get("instances", [])
        if (len(instances) != 1
                or instances[0].get("attributes", {}).get("id", "").lower() != resource_id.lower()):
            raise CheckError("The backend is not the populated state for this runner; initialization was refused.")
    return state["serial"]


def guard_plan(plan, expected_imports):
    if (plan.get("errored") is not False or plan.get("complete") is not True
            or plan.get("deferred_changes") or plan.get("action_invocations")):
        raise CheckError("Terraform must produce a complete, error-free, non-deferred plan.")
    if any(check.get("status") != "pass" for check in plan.get("checks", [])):
        raise CheckError("All Terraform checks must pass before any state update.")
    imports, mutations = {}, []
    for change in plan.get("resource_changes", []):
        details = change.get("change", {})
        actions = details.get("actions")
        if actions != ["no-op"]:
            before, after = details.get("before") or {}, details.get("after") or {}
            attributes = sorted(name for name in set(before) | set(after) if before.get(name) != after.get(name))
            mutations.append({"address": change.get("address", "unknown"), "actions": actions,
                              "attributes": attributes})
        if details.get("importing") is not None:
            imports[change["address"]] = details["importing"].get("id")
    if mutations:
        # Report schema field names, never the corresponding state/plan values.
        print("Rejected resource actions: " + json.dumps(mutations))
        raise CheckError("Plan contains resource mutations; no apply or refresh-only workaround is allowed.")
    if imports != expected_imports:
        raise CheckError("Plan imports differ from the exact reviewed assignment IDs.")
    if any(change.get("actions") != ["no-op"] for change in plan.get("output_changes", {}).values()):
        raise CheckError("Unexpected output changes in the adoption plan.")


def planned_runner_nsg(plan):
    resources = (plan.get("planned_values") or {}).get("root_module", {}).get("resources", [])
    matches = [
        item for item in resources
        if item.get("address") == "azurerm_network_security_group.runner" and item.get("mode") == "managed"
    ]
    rules = matches[0].get("values", {}).get("security_rule") if len(matches) == 1 else None
    if not isinstance(rules, list) or not rules:
        raise CheckError("The complete planned runner NSG rules are required before saving state.")
    return rules


def verify_runner_nsg(before, after, inputs, expected_rules):
    serial = populated_runner_state(after, inputs)
    original, persisted = object_json(before), object_json(after)
    if persisted["lineage"] != original["lineage"] or serial < original["serial"]:
        raise CheckError("Runner state lineage changed or its serial regressed.")
    matches = [
        item for item in persisted["resources"]
        if item.get("mode") == "managed" and item.get("type") == "azurerm_network_security_group"
        and item.get("name") == "runner" and not item.get("module")
    ]
    instances = matches[0].get("instances", []) if len(matches) == 1 else []
    attributes = instances[0].get("attributes", {}) if len(instances) == 1 else {}
    expected_id = (
        f"/subscriptions/{inputs['subscription_id']}/resourceGroups/{inputs['runner_resource_group_name']}"
        f"/providers/Microsoft.Network/networkSecurityGroups/nsg-runner-{inputs['base_name']}-{inputs['environment']}"
    )
    resource_id = attributes.get("id")
    if not isinstance(resource_id, str) or resource_id.lower() != expected_id.lower():
        raise CheckError("Remote state does not own the expected runner NSG.")

    def normalized(value):
        if isinstance(value, dict):
            return {key: normalized(item) for key, item in value.items()}
        if isinstance(value, list):
            return sorted((normalized(item) for item in value), key=lambda item: json.dumps(item, sort_keys=True))
        return value

    if normalized(attributes.get("security_rule")) != normalized(expected_rules):
        raise CheckError("Remote state does not contain the complete guarded runner NSG rules.")
    return serial


class Terraform:
    def __init__(self, root, scratch, environ, key, inputs):
        self.root, self.scratch = root, scratch
        self.binary = shutil.which("terraform")
        if not self.binary:
            raise CheckError("Terraform is missing from the private runner.")
        self.env = {
            key: value for key, value in environ.items()
            if not key.startswith(("TF_", "ARM_", "AZURE_", "MSI_", "IDENTITY_"))
        }
        self.env.update({
            "ARM_CLIENT_ID": environ["AZURE_CLIENT_ID"],
            "ARM_TENANT_ID": environ["AZURE_TENANT_ID"],
            "ARM_SUBSCRIPTION_ID": environ["AZURE_SUBSCRIPTION_ID"],
            "ARM_USE_OIDC": "true", "ARM_USE_AZUREAD": "true",
            "ARM_USE_CLI": "false", "ARM_USE_MSI": "false",
            "ARM_RESOURCE_PROVIDER_REGISTRATIONS": "none",
            "TF_IN_AUTOMATION": "true", "TF_INPUT": "0", "TF_WORKSPACE": "default",
            "TF_DATA_DIR": str(scratch / "data"),
            "TF_CLI_CONFIG_FILE": str(scratch / "terraform.rc"),
        })
        (scratch / "terraform.rc").write_text("disable_checkpoint = true\n")
        self.inputs = scratch / "inputs.tfvars.json"
        self.inputs.write_bytes(inputs)
        backend = scratch / "backend.hcl"
        backend.write_text(
            f'storage_account_name = "{environ["TF_STATE_ACCOUNT"]}"\n'
            f'container_name = "{environ["TF_STATE_CONTAINER"]}"\nkey = "ai-foundry/{key}"\n'
            "use_oidc = true\nuse_azuread_auth = true\nuse_cli = false\nuse_msi = false\n"
        )
        self.command("init", "-reconfigure", f"-backend-config={backend}")

    def command(self, *args, allowed=(0,)):
        result = subprocess.run(  # noqa: S603 -- fixed verbs and guarded private paths; no shell or user CLI arguments.
            [self.binary, f"-chdir={self.root}", args[0], "-no-color", *args[1:]],
            env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
        if result.returncode not in allowed:
            text = (result.stdout + result.stderr).decode(errors="replace")
            reason = next((name for name in (
                "AuthorizationFailed", "403", "Error acquiring the state lock",
                "Insufficient permissions", "Failed to query available provider packages",
                "Unsupported argument", "Invalid value",
            ) if name in text), "private provider diagnostics withheld")
            raise CheckError(f"Terraform {args[0]} failed (exit {result.returncode}; {reason}).")
        self.last_exitcode = result.returncode
        return result.stdout

    def plan(self, name, expected_imports):
        saved = self.scratch / f"{name}.tfplan"
        self.command("plan", "-input=false", "-lock-timeout=60s", "-detailed-exitcode",
                     f"-var-file={self.inputs}", f"-out={saved}", allowed=(0, 2))
        plan_exitcode = self.last_exitcode
        plan = object_json(self.command("show", "-json", str(saved)))
        guard_plan(plan, expected_imports)
        if not expected_imports and plan_exitcode != 0:
            raise CheckError("The follow-up plan must return Terraform's exact no-changes exit code 0.")
        self.last_plan = plan
        return saved, hashlib.sha256(saved.read_bytes()).digest()

    def apply_saved(self, saved, digest):
        if hashlib.sha256(saved.read_bytes()).digest() != digest:
            raise CheckError("The guarded saved plan changed; refusing to apply.")
        self.command("apply", "-input=false", "-lock-timeout=60s", str(saved))


def run(environ=os.environ):
    config = configuration(environ)
    operation = environ.get("TF_RECONCILE_OPERATION")
    if operation not in ("plan", "import-readers", "save-runner-state"):
        raise CheckError("Unsupported reconciliation operation.")
    blobs = Blobs(environ)
    before = blobs.read("runner-dev.tfstate")
    serial = populated_runner_state(before, config["runner"])
    inputs = {
        name: blobs.inputs(f"{name}-dev.tfvars.json", values)
        for name, values in (("runner-plan-access", config["reader"]), ("runner", config["runner"]))
    }
    old_umask = os.umask(0o077)
    try:
        with private_scratch(environ) as scratch:
            if operation == "import-readers":
                access_path = scratch / "access"
                access_path.mkdir()
                access = Terraform(ROOT / "terraform" / "runner-plan-access", access_path, environ,
                                   "runner-plan-access-dev.tfstate", inputs["runner-plan-access"])
                expected = {
                    f'azurerm_role_assignment.reader["{name}"]': assignment
                    for name, assignment in config["reader"]["existing_assignment_ids"].items()
                }
                # Idempotent reruns allow only the subset not already owned by this root.
                state = object_json(access.command("show", "-json"))
                owned = {
                    item["address"]: item["values"]["id"]
                    for item in (state.get("values") or {}).get("root_module", {}).get("resources", [])
                    if item.get("mode") == "managed"
                }
                if any(expected.get(address) != resource_id for address, resource_id in owned.items()):
                    raise CheckError("Reader state contains unexpected ownership; refusing adoption.")
                missing = {address: resource_id for address, resource_id in expected.items() if address not in owned}
                saved, digest = access.plan("adopt", missing)
                if missing:
                    access.apply_saved(saved, digest)
                access.plan("verify", {})
                persisted = object_json(blobs.read("runner-plan-access-dev.tfstate"))
                count = sum(len(item["instances"]) for item in persisted["resources"] if item["mode"] == "managed")
                if count != 3:
                    raise CheckError("Reader adoption did not persist exactly three managed instances.")
                print(f"Reader grants: {len(missing)} imports, zero Azure mutations; fresh follow-up plan has no changes.")
            runner_path = scratch / "runner"
            runner_path.mkdir()
            runner = Terraform(ROOT / "terraform" / "runner", runner_path, environ,
                               "runner-dev.tfstate", inputs["runner"])
            try:
                saved, digest = runner.plan("runner", {})
            finally:
                if blobs.read("runner-dev.tfstate") != before:
                    raise CheckError("Runner state contents changed concurrently; the result needs investigation.")
                print(f"Runner planning left state serial {serial} and contents unchanged, including on rejected plans.")
            if operation == "save-runner-state":
                expected_rules = planned_runner_nsg(runner.last_plan)
                runner.apply_saved(saved, digest)
                persisted = blobs.read("runner-dev.tfstate")
                persisted_serial = verify_runner_nsg(before, persisted, config["runner"], expected_rules)
                try:
                    runner.plan("runner-verify", {})
                finally:
                    if blobs.read("runner-dev.tfstate") != persisted:
                        raise CheckError("Runner state changed during follow-up verification; investigation is required.")
                print(f"Runner state saved: serial {serial} -> {persisted_serial}; complete inline NSG matches "
                      "the guarded plan, lineage preserved, zero Azure mutations; fresh full plan has no changes.")
            else:
                print(f"Full runner plan: no changes; existing state serial {serial} and contents unchanged.")
    finally:
        os.umask(old_umask)
    print("Private canonical inputs verified. No platform plan, canary, VM startup or infrastructure mutation occurred.")


if __name__ == "__main__":
    try:
        if sys.argv[1:] == ["--cleanup"]:
            cleanup()
        elif sys.argv[1:]:
            raise CheckError("Unsupported command-line arguments.")
        else:
            run()
    except (CheckError, OSError) as exc:
        message = str(exc) if isinstance(exc, CheckError) else "Private local tooling or scratch-file operation failed."
        print(f"Runner reconciliation failed: {message}", file=sys.stderr)
        sys.exit(1)

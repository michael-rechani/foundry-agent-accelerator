"""Diagnose the existing platform's Model Router plan on the private runner."""

import json
import os
from pathlib import PurePosixPath
import re
import sys

from check_lab_terraform_plan import (
    change_action,
    configuration as lab_configuration,
    has_unknown,
    stage_sources,
)
from check_state_backend import CheckError, send
from reconcile_runner_state import Blobs, GUID, Terraform, cleanup, object_json, private_scratch

PLATFORM_STATE = "dev.tfstate"
SAVED_PLAN = "platform-router.tfplan"
DEPLOYMENT = "module.model_router.azapi_resource.model_router[0]"
LEGACY_PATCH = "module.model_router.azapi_resource_action.model_router_routing[0]"
READBACK = "module.model_router.data.azapi_resource.model_router_routing[0]"
RELATED_CHANGES = {
    "azapi_resource.jumpbox[0]": "jumpbox",
    "azurerm_role_assignment.jumpbox_foundry_project_manager[0]": "jumpbox_role",
    "azurerm_private_endpoint.terraform_state[0]": "backend_endpoint",
}
ROUTER_MODELS = [
    {"format": "OpenAI", "name": "gpt-4.1", "version": "2025-04-14"},
    {"format": "OpenAI", "name": "gpt-4.1-mini", "version": "2025-04-14"},
]
ROUTER_INPUT = {
    "deployment_name": "model-router",
    "sku_name": "GlobalStandard",
    "capacity": 10,
    "routing_mode": "balanced",
    "models": ROUTER_MODELS,
}
CONSOLE_INPUT = (
    b"jsonencode({subscription_id=var.subscription_id,"
    b"deployment_principal_id=var.deployment_principal_id,"
    b"model_router_deployment=var.model_router_deployment,"
    b"jumpbox_secret_required=var.enable_jumpbox && var.jumpbox_admin_secret != null})\n"
)


def configuration(environ):
    runtime = lab_configuration(environ)
    name = environ.get("TF_PLATFORM_INPUT_BLOB", "")
    parts = PurePosixPath(name).parts
    if (not parts or len(parts) > 3 or PurePosixPath(name).is_absolute() or str(PurePosixPath(name)) != name
            or any(part in (".", "..") or not re.fullmatch(r"[A-Za-z0-9_.-]+", part) for part in parts)
            or not (name.endswith(".tfvars") or name.endswith(".tfvars.json"))):
        raise CheckError("A protected platform input blob under the approved state prefix is required.")
    runtime["PLATFORM_INPUT_BLOB"] = name
    return runtime


class PlatformBlobs(Blobs):
    def __init__(self, environ):
        super().__init__(environ)
        self.input_name = environ["PLATFORM_INPUT_BLOB"]

    def snapshot(self, name):
        if name not in (PLATFORM_STATE, self.input_name):
            raise CheckError("Only the reviewed platform state and input blobs may be read.")
        body, headers = send(self.base + name, headers=self.headers)
        headers = {key.lower(): value for key, value in headers.items()}
        etag = headers.get("etag")
        if not isinstance(etag, str) or not etag:
            raise CheckError("The private backend did not return a blob version.")
        metadata = {key: value for key, value in headers.items() if key.startswith("x-ms-meta-")}
        if name == PLATFORM_STATE and (
            headers.get("x-ms-lease-status") != "unlocked" or "x-ms-meta-terraformlockid" in metadata
        ):
            raise CheckError("The existing platform state is leased or contains unresolved lock metadata.")
        return body, etag, metadata


def snapshot_unchanged(name, before, after):
    if name == PLATFORM_STATE:
        return before[0] == after[0] and before[2] == after[2]
    return before == after


def platform_state(raw, subscription):
    state = object_json(raw)
    resources, outputs = state.get("resources"), state.get("outputs")
    if (state.get("version") != 4 or type(state.get("serial")) is not int
            or not isinstance(state.get("lineage"), str) or not state["lineage"]
            or not isinstance(resources, list) or not isinstance(outputs, dict)
            or any(not isinstance(item, dict) for item in resources)):
        raise CheckError("The selected existing platform state is invalid or empty.")
    account_output = outputs.get("foundry_account_id")
    account = account_output.get("value") if isinstance(account_output, dict) else None
    pattern = (
        r"/subscriptions/(" + GUID + r")/resourceGroups/[A-Za-z0-9._()-]{1,90}"
        r"/providers/Microsoft\.CognitiveServices/accounts/[A-Za-z0-9-]{1,64}"
    )
    match = re.fullmatch(pattern, account if isinstance(account, str) else "", flags=re.IGNORECASE)
    if not match or match.group(1).lower() != subscription.lower():
        raise CheckError("The platform state does not identify a Foundry account in the approved subscription.")
    roles = [
        item for item in resources
        if item.get("mode") == "managed" and item.get("module") is None
        and item.get("type") == "azurerm_role_assignment" and item.get("name") == "deployer_foundry_user"
    ]
    instances = roles[0].get("instances") if len(roles) == 1 else None
    if (not isinstance(instances, list) or len(instances) != 1
            or not isinstance(instances[0], dict) or instances[0].get("deposed")
            or not isinstance(instances[0].get("attributes"), dict)):
        raise CheckError("The platform state does not identify the existing deployer role assignment.")
    principal = instances[0]["attributes"].get("principal_id")
    if not isinstance(principal, str) or not re.fullmatch(GUID, principal):
        raise CheckError("The existing deployer principal is unavailable in platform state.")
    return {"account": account, "principal": principal}


def validate_inputs(values, platform, subscription):
    if not isinstance(values, dict) or set(values) != {
        "subscription_id", "deployment_principal_id", "model_router_deployment", "jumpbox_secret_required",
    }:
        raise CheckError("The protected platform inputs could not be resolved.")
    principal = values["deployment_principal_id"]
    if (values["subscription_id"] != subscription or not isinstance(principal, str)
            or principal.lower() != platform["principal"].lower()):
        raise CheckError(
            "Pin deployment_principal_id to the existing platform deployer before planning with another identity."
        )
    if values["model_router_deployment"] != ROUTER_INPUT:
        raise CheckError("The protected inputs do not select the reviewed default Model Router configuration.")
    if values["jumpbox_secret_required"] is not False:
        raise CheckError("A platform plan requiring access to the jumpbox secret needs a separate review.")


def write_backend(root):
    if (root / "backend.tf").exists():
        raise CheckError("The checked-in platform backend requires separate review.")
    target = root / "runner-diagnostic.tf"
    if target.exists():
        raise CheckError("A reserved platform diagnostic source file already exists.")
    target.write_text(
        'terraform {\n  backend "azurerm" {}\n  required_providers {\n'
        '    modtm = {\n      source = "azure/modtm"\n      version = "~> 0.3"\n    }\n  }\n}\n'
        'provider "modtm" {\n  enabled = false\n}\n',
        encoding="utf-8",
    )


class PlatformTerraform(Terraform):
    def __init__(self, root, scratch, environ, inputs):
        suffix = ".tfvars.json" if environ["PLATFORM_INPUT_BLOB"].endswith(".tfvars.json") else ".tfvars"
        terraform_env = {key: value for key, value in environ.items() if key != "PLATFORM_INPUT_BLOB"}
        super().__init__(root, scratch, terraform_env, PLATFORM_STATE, inputs, input_suffix=suffix)

    def command(self, *args, allowed=(0,), input_data=None):
        backend = f"-backend-config={self.scratch / 'backend.hcl'}"
        var_file = f"-var-file={self.inputs}"
        saved = self.scratch / SAVED_PLAN
        permitted = (
            (args == ("init", "-reconfigure", backend) and allowed == (0,) and input_data is None)
            or (args == ("console", var_file) and allowed == (0,) and input_data == CONSOLE_INPUT)
            or (args == ("plan", "-input=false", "-detailed-exitcode", "-refresh=true", "-lock=true",
                         "-lock-timeout=5m", var_file, f"-out={saved}")
                and allowed == (0, 2) and input_data is None)
            or (args == ("show", "-json", str(saved)) and allowed == (0,) and input_data is None)
        )
        if not permitted:
            raise CheckError("Only private initialization, input inspection and a full locked plan are allowed.")
        return super().command(*args, allowed=allowed, input_data=input_data)

    def inputs_resolved(self):
        raw = self.command("console", f"-var-file={self.inputs}", input_data=CONSOLE_INPUT)
        try:
            encoded = json.loads(raw)
        except (ValueError, UnicodeError):
            raise CheckError("Terraform did not resolve the protected platform inputs.") from None
        if not isinstance(encoded, str):
            raise CheckError("Terraform returned incomplete protected platform inputs.")
        return object_json(encoded)

    def full_plan(self):
        saved = self.scratch / SAVED_PLAN
        self.command(
            "plan", "-input=false", "-detailed-exitcode", "-refresh=true", "-lock=true",
            "-lock-timeout=5m", f"-var-file={self.inputs}", f"-out={saved}", allowed=(0, 2),
        )
        exit_code = self.last_exitcode
        return object_json(self.command("show", "-json", str(saved))), exit_code


def router_body():
    return {
        "sku": {"name": "GlobalStandard", "capacity": 10},
        "properties": {
            "model": {"format": "OpenAI", "name": "model-router", "version": "2025-11-18"},
            "raiPolicyName": "Microsoft.DefaultV2",
            "versionUpgradeOption": "OnceNewDefaultVersionAvailable",
            "routing": {"mode": "balanced", "models": ROUTER_MODELS},
        },
    }


def router_change_matches(address, entry, account):
    change = entry["change"]
    after, unknown = change.get("after"), change.get("after_unknown", {})
    if not isinstance(after, dict) or not isinstance(unknown, dict) or has_unknown(unknown.get("body", False)):
        return False
    expected = router_body()
    if address == DEPLOYMENT:
        return (
            after.get("type") == "Microsoft.CognitiveServices/accounts/deployments@2025-10-01-preview"
            and after.get("name") == "model-router"
            and isinstance(after.get("parent_id"), str)
            and after["parent_id"].lower() == account.lower()
            and not has_unknown(unknown.get("parent_id", False))
            and after.get("body") == expected
        )
    return False


def preview_capabilities(variables):
    primary_input = variables.get("model_deployment")
    additional_input = variables.get("additional_model_deployments")
    primary = primary_input.get("value") if isinstance(primary_input, dict) else None
    additional = additional_input.get("value") if isinstance(additional_input, dict) else None
    if (not isinstance(primary, dict) or not isinstance(additional, dict)
            or any(not isinstance(name, str) for name in additional)):
        raise CheckError("The plan must identify its fixed model inputs.")
    primary_name = primary.get("deployment_name")
    names = [primary_name, *sorted(additional)]
    if (any(not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", name)
            for name in names)
            or len(set(names)) != len(names) or "model-router" in names):
        raise CheckError("The plan must identify unique fixed model deployment names.")
    models = {primary_name: primary, **additional}
    known = {(item["format"], item["name"], item["version"]) for item in ROUTER_MODELS}
    expected = {"model-router": False}
    for deployment, model in models.items():
        if (not isinstance(model, dict)
                or any(not isinstance(model.get(key), str) or not model[key] for key in ("format", "name", "version"))):
            raise CheckError("The plan must identify fixed model formats, names and versions.")
        if tuple(model[key] for key in ("format", "name", "version")) in known:
            expected[deployment] = False
    return names, expected


def require_router_readback(plan, deployment_action, account, checks):
    resources = [
        entry for entry in plan["resource_changes"]
        if isinstance(entry, dict) and entry.get("address") == READBACK
    ]
    if len(resources) > 1:
        raise CheckError("The Router readback appears more than once.")
    if deployment_action == "create":
        if len(resources) != 1 or resources[0].get("mode") != "data":
            raise CheckError("Router creation requires exactly one deferred readback.")
        change = resources[0]["change"]
        after, unknown = change.get("after"), change.get("after_unknown")
        if (change.get("actions") != ["read"] or not isinstance(after, dict)
                or not isinstance(unknown, dict) or unknown.get("output") is not True
                or after.get("output") is not None
                or after.get("type") != "Microsoft.CognitiveServices/accounts/deployments@2025-12-01"
                or after.get("response_export_values") != ["properties.routing"]
                or has_unknown(unknown.get("type", False))
                or has_unknown(unknown.get("response_export_values", False))
                or not (
                    after.get("resource_id") is None and unknown.get("resource_id") is True
                    or isinstance(after.get("resource_id"), str)
                    and after["resource_id"].lower() == (account + "/deployments/model-router").lower()
                    and not has_unknown(unknown.get("resource_id", False))
                )):
            raise CheckError("Router creation has invalid or inconsistent deferred readback.")
    else:
        if resources and resources[0]["change"].get("actions") != ["no-op"]:
            raise CheckError("A verified Router no-op must not defer its readback.")
        if resources and has_unknown(resources[0]["change"].get("after_unknown", {})):
            raise CheckError("A verified Router no-op requires known readback values.")

        def find_readback(module):
            if not isinstance(module, dict):
                raise CheckError("Terraform returned invalid readback value evidence.")
            entries = module.get("resources", [])
            children = module.get("child_modules", [])
            if (not isinstance(entries, list) or not isinstance(children, list)
                    or any(not isinstance(entry, dict) for entry in entries)):
                raise CheckError("Terraform returned invalid readback value evidence.")
            found = [entry for entry in entries if entry.get("address") == READBACK]
            for child in children:
                found.extend(find_readback(child))
            return found

        sources = [plan.get("planned_values", {})]
        prior = plan.get("prior_state", {})
        if not isinstance(prior, dict):
            raise CheckError("Terraform returned invalid readback value evidence.")
        sources.append(prior.get("values", {}))
        observed = [
            {"mode": entry.get("mode"), "type": entry.get("type"), "values": entry["change"].get("after")}
            for entry in resources
        ]
        for source in sources:
            if not isinstance(source, dict):
                raise CheckError("Terraform returned invalid readback value evidence.")
            entries = find_readback(source.get("root_module", {}))
            if len(entries) > 1:
                raise CheckError("The Router readback values appear more than once.")
            observed.extend(entries)
        if not observed:
            raise CheckError("A verified Router no-op requires known readback values.")
        for entry in observed:
            values = entry.get("values")
            output = values.get("output") if isinstance(values, dict) else None
            properties = output.get("properties") if isinstance(output, dict) else None
            routing = properties.get("routing") if isinstance(properties, dict) else None
            models = routing.get("models") if isinstance(routing, dict) else None
            if (entry.get("mode") != "data" or entry.get("type") != "azapi_resource"
                    or not isinstance(values, dict)
                    or values.get("type") != "Microsoft.CognitiveServices/accounts/deployments@2025-12-01"
                    or values.get("response_export_values") != ["properties.routing"]
                    or not isinstance(values.get("resource_id"), str)
                    or values["resource_id"].lower() != (account + "/deployments/model-router").lower()
                    or not isinstance(routing, dict) or routing.get("mode") != "balanced"
                    or not isinstance(models, list) or len(models) != len(ROUTER_MODELS)
                    or any(not isinstance(model, dict) for model in models)
                    or sorted(json.dumps(model, sort_keys=True) for model in models)
                    != sorted(json.dumps(model, sort_keys=True) for model in ROUTER_MODELS)):
                raise CheckError("Known Router readback does not match the reviewed deployment.")

    matching = [
        check for check in checks
        if isinstance(check, dict) and isinstance(check.get("address"), dict)
        and check["address"].get("to_display") in (
            READBACK, "module.model_router.data.azapi_resource.model_router_routing",
        )
    ]
    expected_status = "unknown" if deployment_action == "create" else "pass"
    if len(matching) != 1:
        raise CheckError("Exactly one Router readback postcondition result is required.")
    check = matching[0]
    address = check["address"]
    instances = check.get("instances")
    if (address != {
            "kind": "resource", "mode": "data", "type": "azapi_resource",
            "name": "model_router_routing", "module": "module.model_router",
            "to_display": "module.model_router.data.azapi_resource.model_router_routing",
        } or check.get("status") != expected_status
            or not isinstance(instances, list) or len(instances) != 1
            or not isinstance(instances[0], dict)
            or instances[0].get("address") != {
                "module": "module.model_router", "instance_key": 0, "to_display": READBACK,
            } or type(instances[0]["address"].get("instance_key")) is not int
            or instances[0].get("status") != expected_status or instances[0].get("problems")):
        raise CheckError("Router readback postcondition evidence is missing or inconsistent.")


def summarize_plan(plan, exit_code, values, account):
    if (plan.get("errored") is not False or plan.get("complete") is not True
            or plan.get("deferred_changes") or plan.get("action_invocations")
            or not isinstance(plan.get("format_version"), str)
            or not re.fullmatch(r"1\.[0-9]+", plan["format_version"])):
        raise CheckError("Terraform must produce a complete, error-free full plan.")
    variables = plan.get("variables")
    if not isinstance(variables, dict) or any(
        not isinstance(variables.get(name), dict) or variables[name].get("value") != values[name]
        for name in ("subscription_id", "deployment_principal_id", "model_router_deployment")
    ):
        raise CheckError("The plan did not use the checked protected platform inputs.")
    changes, drift, outputs, checks = (
        plan.get("resource_changes"), plan.get("resource_drift", []),
        plan.get("output_changes", {}), plan.get("checks", []),
    )
    if (not isinstance(changes, list) or not isinstance(drift, list)
            or not isinstance(outputs, dict) or not isinstance(checks, list)):
        raise CheckError("Terraform returned an incomplete platform plan.")
    actions = {}
    other_managed = other_reads = imports = 0
    related = set()
    for entry in changes:
        if not isinstance(entry, dict) or not isinstance(entry.get("address"), str):
            raise CheckError("Terraform returned an invalid resource change.")
        address = entry["address"]
        action, importing = change_action(entry)
        imports += importing
        mode = entry.get("mode")
        if address == LEGACY_PATCH:
            raise CheckError("Legacy Router PATCH state requires separately reviewed recovery.")
        if address == DEPLOYMENT:
            if address in actions or mode != "managed":
                raise CheckError("The Router resource appears more than once or with an invalid mode.")
            if action not in ("no-op", "create") or not router_change_matches(address, entry, account):
                raise CheckError("The Router deployment differs from the reviewed PUT configuration.")
            actions[address] = action
        elif mode == "managed":
            other_managed += action != "no-op"
            if action != "no-op" and address in RELATED_CHANGES:
                related.add(RELATED_CHANGES[address])
        elif mode == "data":
            if address != READBACK:
                other_reads += action != "no-op"
            elif action not in ("read", "no-op"):
                raise CheckError("The Router readback has an unexpected action.")
        else:
            raise CheckError("Terraform returned an unsupported resource mode.")
    if set(actions) != {DEPLOYMENT}:
        raise CheckError("The plan must contain exactly the reviewed Router PUT deployment.")
    drift_count = 0
    for entry in drift:
        if not isinstance(entry, dict) or entry.get("mode") != "managed":
            raise CheckError("Terraform returned an invalid platform drift entry.")
        if entry.get("address") == LEGACY_PATCH:
            raise CheckError("Legacy Router PATCH state requires separately reviewed recovery.")
        action, importing = change_action(entry)
        imports += importing
        drift_count += action != "no-op"
        if action != "no-op" and entry.get("address") in RELATED_CHANGES:
            related.add(RELATED_CHANGES[entry["address"]])
    other_outputs = 0
    for name, change in outputs.items():
        if not isinstance(change, dict) or change.get("actions") not in (
            ["no-op"], ["create"], ["update"], ["delete"],
        ):
            raise CheckError("Terraform returned an invalid platform output change.")
        if name not in ("model_router_deployment_name", "model_deployment_names", "model_preview_encrypted_reasoning"):
            other_outputs += change["actions"] != ["no-op"]
        elif change["actions"] == ["delete"]:
            raise CheckError("The Router plan must not remove model outputs.")
    router_output = outputs.get("model_router_deployment_name")
    model_names = outputs.get("model_deployment_names")
    preview_output = outputs.get("model_preview_encrypted_reasoning")
    fixed_names, expected_preview = preview_capabilities(variables)

    def valid_preview_map(value):
        return isinstance(value, dict) and all(
            isinstance(name, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", name)
            and type(enabled) is bool for name, enabled in value.items()
        )

    if (not isinstance(preview_output, dict)
            or preview_output.get("actions") not in (["create"], ["update"], ["no-op"])
            or preview_output.get("after_unknown") is not False
            or not valid_preview_map(preview_output.get("after"))
            or set(preview_output["after"]) != set(expected_preview)
            or any(value is not False for value in preview_output["after"].values())
            or (preview_output["actions"] == ["create"] and preview_output.get("before") is not None)
            or (preview_output["actions"] == ["no-op"] and (
                not valid_preview_map(preview_output.get("before"))
                or preview_output["before"] != preview_output["after"]
            ))
            or (preview_output["actions"] == ["update"] and (
                not valid_preview_map(preview_output.get("before"))
                or preview_output["before"] == preview_output["after"]
            ))):
        raise CheckError("The planned preview capability output does not match the reviewed model inputs.")
    require_router_readback(plan, actions[DEPLOYMENT], account, checks)
    if actions[DEPLOYMENT] == "create":
        if (not isinstance(router_output, dict) or router_output.get("actions") not in (["create"], ["update"])
                or not isinstance(model_names, dict) or model_names.get("actions") != ["update"]
                or not (
                    router_output.get("after") == "model-router" and router_output.get("after_unknown") is False
                    or router_output.get("after") is None and router_output.get("after_unknown") is True
                )):
            raise CheckError("The Router plan must expose its name without removing existing model outputs.")
        before, after = model_names.get("before"), model_names.get("after")
        unknown = model_names.get("after_unknown")
        if (before != fixed_names or not isinstance(after, list) or len(after) != len(before) + 1
                or after[:-1] != before or not isinstance(unknown, list) or len(unknown) != len(after)
                or any(unknown[:-1]) or not (
                    after[-1] == "model-router" and unknown[-1] is False
                    or after[-1] is None and unknown[-1] is True
                )):
            raise CheckError("The Router plan must preserve existing deployment names and append Router.")
    elif (not isinstance(router_output, dict) or router_output.get("actions") != ["no-op"]
            or router_output.get("after") != "model-router" or router_output.get("after_unknown") is not False
            or not isinstance(model_names, dict) or model_names.get("actions") != ["no-op"]
            or model_names.get("after") != [*fixed_names, "model-router"]
            or model_names.get("before") != model_names["after"] or model_names.get("after_unknown") is not False):
        raise CheckError("The existing Router outputs are missing, changed or unknown.")
    if any(not isinstance(check, dict) or check.get("status") not in ("pass", "fail", "unknown", "error")
           for check in checks):
        raise CheckError("Terraform returned invalid platform check results.")
    deferred_router = 0
    nonpassing = 0
    for check in checks:
        address = check.get("address")
        name = address.get("to_display") if isinstance(address, dict) else None
        if (check["status"] == "unknown" and actions[DEPLOYMENT] == "create"
                and name in (READBACK, "module.model_router.data.azapi_resource.model_router_routing")):
            deferred_router += 1
        elif check["status"] != "pass":
            nonpassing += 1
    if deferred_router > 1:
        raise CheckError("Terraform returned duplicate deferred Router readback checks.")
    if exit_code not in (0, 2) or exit_code == 0 and (
        any(action != "no-op" for action in actions.values()) or other_managed or imports or other_outputs
        or preview_output["actions"] != ["no-op"]
    ):
        raise CheckError("Terraform's plan exit status does not match the platform changes.")
    return {
        "plan_exit": "changes" if exit_code == 2 else "no-changes",
        "router_deployment": actions[DEPLOYMENT],
        "preview_capability_output": preview_output["actions"][0],
        "other_managed_changes": other_managed,
        "other_deferred_reads": other_reads,
        "other_output_changes": other_outputs,
        "imports": imports,
        "refreshed_drift": drift_count,
        "known_unrelated_changes": sorted(related),
        "deferred_router_readback": deferred_router,
        "other_nonpassing_checks": nonpassing,
    }


def run(environ=os.environ):
    runtime = configuration(environ)
    blobs = PlatformBlobs(runtime)
    names = (PLATFORM_STATE, runtime["PLATFORM_INPUT_BLOB"])
    snapshots = {name: blobs.snapshot(name) for name in names}
    platform = platform_state(snapshots[PLATFORM_STATE][0], runtime["AZURE_SUBSCRIPTION_ID"])
    old_umask = os.umask(0o077)
    try:
        with private_scratch(runtime) as scratch:
            root = stage_sources(scratch, runtime, kind="platform")
            if not (root / "model-router.tf").is_file() or not (root / "modules" / "model-router" / "main.tf").is_file():
                raise CheckError("The checked-in platform source does not contain the Router configuration.")
            write_backend(root)
            terraform = PlatformTerraform(root, scratch, runtime, snapshots[names[1]][0])
            values = terraform.inputs_resolved()
            validate_inputs(values, platform, runtime["AZURE_SUBSCRIPTION_ID"])
            plan, exit_code = terraform.full_plan()
            summary = summarize_plan(plan, exit_code, values, platform["account"])
    finally:
        os.umask(old_umask)
        if any(not snapshot_unchanged(name, snapshots[name], blobs.snapshot(name)) for name in names):
            raise CheckError("A protected platform input or state blob changed during planning.")
    print("Private full-root platform plan; actions and counts only:")
    print(json.dumps(summary, indent=2, sort_keys=True))
    print("State contents, non-lock metadata and protected inputs were unchanged; no infrastructure apply ran.")
    if summary["deferred_router_readback"]:
        print("Router readback is deferred until apply; inference behavior also needs live verification.")
    if (summary["other_managed_changes"] or summary["other_deferred_reads"] or summary["other_output_changes"]
            or summary["imports"] or summary["refreshed_drift"] or summary["other_nonpassing_checks"]):
        raise CheckError("The platform plan includes unrelated changes, drift or unverified checks; review is required.")


if __name__ == "__main__":
    try:
        if sys.argv[1:] == ["--cleanup"]:
            cleanup()
        elif not sys.argv[1:]:
            run()
        else:
            raise CheckError("This diagnostic accepts no operation or Terraform arguments.")
    except (CheckError, OSError) as exc:
        message = str(exc) if isinstance(exc, CheckError) else "Private local file or process access failed."
        print(f"Platform diagnostic stopped: {message}", file=sys.stderr)
        sys.exit(1)

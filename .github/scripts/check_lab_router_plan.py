"""Check the private Lab's Model Router change without applying it."""

import os
import re
import sys
from urllib.parse import quote

from check_lab_terraform_plan import (
    LAB_INPUTS,
    LAB_STATE,
    PLATFORM_STATE,
    LabBlobs,
    LabTerraform,
    change_action,
    configuration,
    configure_platform_oidc,
    container_environment,
    current_image,
    lab_state,
    snapshot_unchanged,
    stage_sources,
    summarize_plan,
    validate_inputs,
    write_supplemental_files,
)
from check_platform_router_plan import ROUTER_MODELS, platform_state
from check_state_backend import CheckError, azure_token, json_response
from reconcile_runner_state import cleanup, object_json, private_scratch

APP = "azurerm_container_app.this[0]"
MODEL = "WORKBENCH_AGENT_CREATION_MODEL"


def platform_context(raw, subscription):
    platform = platform_state(raw, subscription)
    outputs = object_json(raw)["outputs"]

    def output(name):
        item = outputs.get(name)
        return item.get("value") if isinstance(item, dict) else None

    account_name = output("foundry_account_name")
    project_name = output("foundry_project_name")
    project_id = output("foundry_project_id")
    endpoint = output("foundry_project_endpoint")
    primary = output("model_deployment_name")
    names = output("model_deployment_names")
    if (not isinstance(account_name, str) or not re.fullmatch(r"[A-Za-z0-9-]{1,64}", account_name)
            or account_name.lower() != platform["account"].rsplit("/", 1)[-1].lower()
            or not isinstance(project_name, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", project_name)
            or not isinstance(project_id, str)
            or project_id.lower() != (platform["account"] + "/projects/" + project_name).lower()
            or endpoint != f"https://{account_name}.services.ai.azure.com/api/projects/{project_name}"
            or not isinstance(primary, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", primary)
            or primary == "model-router" or output("model_router_deployment_name") != "model-router"
            or not isinstance(names, list) or not names or names[0] != primary
            or names[-1] != "model-router" or names.count("model-router") != 1
            or any(not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", name) for name in names)):
        raise CheckError("Platform state does not identify the expected project and Router deployment.")
    return {
        "account": platform["account"], "project_id": project_id, "endpoint": endpoint,
        "primary": primary, "router": "model-router",
    }


def live_router(environ, platform):
    token = azure_token(environ, scope="https://management.azure.com/.default")
    resource_id = platform["account"] + "/deployments/" + platform["router"]
    response = json_response(
        "https://management.azure.com" + quote(resource_id, safe="/") + "?api-version=2025-12-01",
        headers={"Authorization": f"Bearer {token}"},
    )
    properties = response.get("properties")
    model = properties.get("model") if isinstance(properties, dict) else None
    routing = properties.get("routing") if isinstance(properties, dict) else None
    models = routing.get("models") if isinstance(routing, dict) else None
    actual_models = (
        [(item.get("format"), item.get("name"), item.get("version")) for item in models]
        if isinstance(models, list) and all(
            isinstance(item, dict) and all(isinstance(item.get(key), str) for key in ("format", "name", "version"))
            for item in models
        ) else None
    )
    expected_models = [(item["format"], item["name"], item["version"]) for item in ROUTER_MODELS]
    sku = response.get("sku")
    if (not isinstance(response.get("id"), str) or response["id"].lower() != resource_id.lower()
            or not isinstance(properties, dict) or str(properties.get("provisioningState", "")).lower() != "succeeded"
            or not isinstance(model, dict)
            or (model.get("format"), model.get("name"), model.get("version"))
            != ("OpenAI", "model-router", "2025-11-18")
            or not isinstance(sku, dict) or sku.get("name") != "GlobalStandard" or sku.get("capacity") != 10
            or not isinstance(routing, dict) or routing.get("mode") != "balanced"
            or actual_models is None or sorted(actual_models) != sorted(expected_models)):
        raise CheckError("The live Router deployment or its routing readback is not the reviewed configuration.")
    return (
        resource_id.lower(), model["version"], sku["name"], sku["capacity"],
        routing["mode"], tuple(sorted(actual_models)),
    )


def review_plan(plan, exit_code, values, app, platform):
    variables = plan.get("variables")
    platform_variable = variables.get("platform_state") if isinstance(variables, dict) else None
    if not isinstance(platform_variable, dict) or platform_variable.get("value") != values["platform_state"]:
        raise CheckError("The Lab plan did not use the checked platform state inputs.")
    summary = summarize_plan(plan, exit_code, values)
    if (summary["imports"] or summary["data_reads"] or summary["output_changes"]
            or summary["resources_with_unknown_values"] or summary["outputs_with_unknown_values"]
            or summary["nonpassing_checks"] or plan.get("resource_drift", [])
            or any(item["planned"]["action"] != "no-op" or item["planned"]["fields"]
                   or item["planned"]["unknown_fields"] or item["planned"]["import"]
                   for item in summary["targets"].values())):
        raise CheckError("The Lab plan contains drift, unknowns, non-passing checks or unrelated changes.")

    for item in plan["resource_changes"]:
        if item.get("mode") == "managed" and item.get("address") != APP:
            action, _ = change_action(item)
            if action == "no-op" and item["change"].get("before") != item["change"].get("after"):
                raise CheckError("An unchanged Lab resource has inconsistent planned values.")
    matches = [
        item for item in plan["resource_changes"]
        if isinstance(item, dict) and item.get("address") == APP
    ]
    if len(matches) != 1 or matches[0].get("mode") != "managed" or matches[0].get("type") != "azurerm_container_app":
        raise CheckError("The Lab plan must identify the existing Container App exactly once.")
    change = matches[0]["change"]
    action, importing = change_action(matches[0])
    before, after = change.get("before"), change.get("after")
    before_env, after_env = container_environment(before), container_environment(after)
    if (importing or action not in ("no-op", "update") or not isinstance(before, dict)
            or not isinstance(after, dict) or not isinstance(before_env, dict) or not isinstance(after_env, dict)
            or not isinstance(before.get("id"), str) or before["id"].lower() != app["app_id"].lower()
            or not isinstance(after.get("id"), str) or after["id"].lower() != app["app_id"].lower()):
        raise CheckError("The Lab Container App plan has an unexpected identity or shape.")

    def literal(environment, name, value):
        entry = environment.get(name)
        return (
            isinstance(entry, dict) and set(entry) <= {"value", "secret_name"}
            and entry.get("value") == value and entry.get("secret_name") in (None, "")
        )

    def uses_active_image(resource):
        image = resource["template"][0]["container"][0].get("image")
        return (
            isinstance(image, str) and isinstance(values["image_digest"], str)
            and re.fullmatch(r"[^@\s]+@" + re.escape(values["image_digest"]), image) is not None
        )

    if (not literal(after_env, "WORKBENCH_MODE", "private")
            or not literal(after_env, "FOUNDRY_PROJECT_ENDPOINT", platform["endpoint"])
            or not literal(after_env, "WORKBENCH_FOUNDRY_PROJECT_ID", platform["project_id"])
            or not literal(after_env, MODEL, platform["router"])
            or not uses_active_image(before) or not uses_active_image(after)
            or ("WORKBENCH_LIBRARY_PREVIEW_ENABLED" in after_env
                and not literal(after_env, "WORKBENCH_LIBRARY_PREVIEW_ENABLED", "true"))):
        raise CheckError("The planned Lab does not match the verified project, active image and private Router preview.")

    details = summary["other_managed_details"]
    if action == "no-op":
        if (exit_code != 0 or summary["other_managed_changes"] or details
                or before != after or not literal(before_env, MODEL, platform["router"])):
            raise CheckError("The no-change Lab plan is inconsistent.")
        return "already-configured"

    expected_comparison = {
        "status": "compared", "changed": {MODEL: "changed"},
        "changed_attributes": {MODEL: {"value": "set->set"}},
        "other_entries_changed": False, "order_changed": False,
    }
    if (exit_code != 2 or not literal(before_env, MODEL, platform["primary"])
            or summary["other_managed_changes"] != 1 or len(details) != 1
            or summary["other_managed_actions"]["update"] != 1):
        raise CheckError("Only the existing fixed model may change to Router.")
    detail = details[0]
    if (detail.get("resource") != "container_app" or detail.get("action") != "update"
            or detail.get("fields") != ["template.container.env"] or detail.get("unknown_fields")
            or detail.get("import") or detail.get("environment_comparison") != expected_comparison):
        raise CheckError("The Lab plan changes more than the reviewed Router model value.")
    return "model-update"


def run(environ=os.environ):
    runtime = configuration(environ)
    blobs = LabBlobs(runtime)
    snapshots = {name: blobs.snapshot(name) for name in (LAB_STATE, LAB_INPUTS)}
    app = lab_state(snapshots[LAB_STATE][0], runtime["AZURE_SUBSCRIPTION_ID"])
    revision, digest = current_image(runtime, app)
    old_umask = os.umask(0o077)
    try:
        with private_scratch(runtime) as scratch:
            root = stage_sources(scratch, runtime)
            configure_platform_oidc(root)
            write_supplemental_files(root, digest)
            terraform = LabTerraform(root, scratch, runtime, snapshots[LAB_INPUTS][0])
            values = terraform.inputs_resolved()
            if validate_inputs(values, app, digest, runtime) != PLATFORM_STATE:
                raise CheckError("The Router check requires the approved private platform state.")
            snapshots[PLATFORM_STATE] = blobs.snapshot(PLATFORM_STATE)
            platform = platform_context(snapshots[PLATFORM_STATE][0], runtime["AZURE_SUBSCRIPTION_ID"])
            router = live_router(runtime, platform)
            plan, exit_code = terraform.full_plan()
            result = review_plan(plan, exit_code, values, app, platform)
            if current_image(runtime, app) != (revision, digest):
                raise CheckError("The active Lab revision changed during the diagnostic.")
            if live_router(runtime, platform) != router:
                raise CheckError("The live Router configuration changed during the diagnostic.")
    finally:
        os.umask(old_umask)
        if any(not snapshot_unchanged(name, snapshot, blobs.snapshot(name)) for name, snapshot in snapshots.items()):
            raise CheckError("A protected Lab input or state blob changed during the diagnostic.")
    print(f"Private full-root Lab Router check: {result}. No infrastructure apply ran.")
    print("Management readback is not an inference test; this check does not authorize an apply.")


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
        print(f"Lab Router diagnostic stopped: {message}", file=sys.stderr)
        sys.exit(1)

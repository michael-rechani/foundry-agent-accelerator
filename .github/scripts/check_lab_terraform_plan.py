"""Diagnose the existing Lab with a protected, redacted, full-root Terraform plan."""

import hashlib
import io
import json
import os
from pathlib import PurePosixPath
import re
import shutil
import subprocess
import sys
import tarfile
from urllib.parse import quote

from check_state_backend import CheckError, azure_token, json_response, send, validate_backend
from reconcile_runner_state import (
    Blobs,
    GUID,
    ROOT,
    Terraform,
    cleanup,
    object_json,
    private_scratch,
)

LAB_STATE = "workbench-dev.tfstate"
LAB_INPUTS = "workbench-dev.tfvars"
PLATFORM_STATE = "dev.tfstate"
CONFIG_KEYS = {
    "AZURE_CLIENT_ID", "AZURE_TENANT_ID", "AZURE_SUBSCRIPTION_ID",
    "TF_STATE_ACCOUNT", "TF_STATE_CONTAINER", "TF_STATE_PREFIX", "TF_STATE_PRIVATE_ENDPOINT",
}
CONSOLE_INPUT = (
    b"jsonencode({subscription_id=var.subscription_id,name=var.name,"
    b"bootstrap_only=var.bootstrap_only,enable_front_door=var.enable_front_door,"
    b"image_digest=var.image_digest,platform_state=var.platform_state})\n"
)
TARGETS = {
    'module.front_door[0].azurerm_cdn_frontdoor_firewall_policy.wafs["lab"]': "waf",
    'azurerm_monitor_scheduled_query_rules_alert_v2.operational["request-failures"]': "request_failures",
    'azurerm_monitor_scheduled_query_rules_alert_v2.operational["dependencies"]': "dependencies",
    "azurerm_monitor_scheduled_query_rules_alert_v2.heartbeat": "heartbeat",
}
WAF_FIELDS = {
    "id": True, "name": True, "resource_group_name": True, "sku_name": True,
    "enabled": True, "mode": True, "tags": True, "redirect_url": True,
    "custom_block_response_body": True, "custom_block_response_status_code": True,
    "custom_rule": {
        "name": True, "enabled": True, "priority": True, "type": True, "action": True,
        "rate_limit_duration_in_minutes": True, "rate_limit_threshold": True,
        "match_condition": {
            "match_variable": True, "selector": True, "operator": True, "negation_condition": True,
            "match_values": True, "transforms": True,
        },
    },
    "managed_rule": {
        "type": True, "version": True, "action": True, "exclusion": True, "override": True,
    },
}
ALERT_FIELDS = {
    "id": True, "name": True, "resource_group_name": True, "location": True, "description": True,
    "enabled": True, "scopes": True, "severity": True, "evaluation_frequency": True,
    "window_duration": True, "auto_mitigation_enabled": True, "skip_query_validation": True,
    "target_resource_types": True, "tags": True,
    "criteria": {
        "query": True, "time_aggregation_method": True, "metric_measure_column": True,
        "resource_id_column": True, "threshold": True, "operator": True,
        "dimension": {"name": True, "operator": True, "values": True},
        "failing_periods": {"minimum_failing_periods_to_trigger_alert": True, "number_of_evaluation_periods": True},
    },
    "action": {"action_groups": True, "custom_properties": True},
}
ACTIONS = {
    ("no-op",): "no-op",
    ("create",): "create",
    ("update",): "update",
    ("delete",): "delete",
    ("read",): "read",
    ("forget",): "forget",
    ("delete", "create"): "replace-delete-create",
    ("create", "delete"): "replace-create-delete",
    ("create", "forget"): "replace-create-forget",
}
MISSING = object()


def configuration(environ):
    protected = object_json(environ.get("TF_LAB_PLAN_CONFIG", ""))
    if set(protected) != CONFIG_KEYS or any(not isinstance(value, str) or not value for value in protected.values()):
        raise CheckError("Protected Lab planning configuration is incomplete or contains unsupported fields.")
    if any(environ.get(name) for name in (
        "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy",
    )):
        raise CheckError("Proxy settings are not allowed for this private diagnostic.")
    runtime = {
        key: value for key, value in environ.items()
        if not key.startswith(("TF_", "ARM_", "AZURE_", "MSI_", "IDENTITY_", "MODTM_"))
    }
    runtime.update(protected)
    if not re.fullmatch(GUID, runtime["AZURE_SUBSCRIPTION_ID"]):
        raise CheckError("An explicit subscription GUID is required.")
    if not re.fullmatch(r"[0-9a-f]{40}", runtime.get("GITHUB_SHA", "")):
        raise CheckError("The exact checked-in workflow revision is required.")
    validate_backend(runtime)
    return runtime


class LabBlobs:
    def __init__(self, environ):
        backend = Blobs(environ)
        self.base, self.headers = backend.base, backend.headers

    def snapshot(self, name):
        if name not in (LAB_STATE, LAB_INPUTS, PLATFORM_STATE):
            raise CheckError("Only the reviewed Lab and platform blobs may be read.")
        body, headers = send(self.base + name, headers=self.headers)
        headers = {key.lower(): value for key, value in headers.items()}
        etag = headers.get("etag")
        if not isinstance(etag, str) or not etag:
            raise CheckError("The private backend did not return a blob version for concurrency checking.")
        metadata = {key: value for key, value in headers.items() if key.startswith("x-ms-meta-")}
        if name == LAB_STATE and (
            headers.get("x-ms-lease-status") != "unlocked" or "x-ms-meta-terraformlockid" in metadata
        ):
            raise CheckError("The existing Lab state is leased or contains unresolved Terraform lock metadata.")
        return body, etag, metadata


def snapshot_unchanged(name, before, after):
    if name == LAB_STATE:
        # Terraform's Azure backend changes the ETag when it adds and removes lock metadata.
        return before[0] == after[0] and before[2] == after[2]
    return before == after


def stage_sources(scratch, environ):
    git = shutil.which("git")
    if not git:
        raise CheckError("Git is missing from the private runner.")
    result = subprocess.run(  # noqa: S603 -- fixed local Git archive operation and reviewed paths.
        [
            git, "-C", str(ROOT), "archive", "--format=tar", environ["GITHUB_SHA"], "--",
            "workbench/infra", "workbench/agents.json",
        ],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        env={
            key: value for key, value in environ.items()
            if key in ("PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "TEMP", "TMP", "LANG", "LC_ALL")
        },
    )
    if result.returncode:
        raise CheckError("The checked-in Lab source could not be staged.")
    destination = scratch / "source"
    destination.mkdir(mode=0o700)
    try:
        with tarfile.open(fileobj=io.BytesIO(result.stdout), mode="r:") as archive:
            for entry in archive:
                path = PurePosixPath(entry.name)
                if (path.is_absolute() or ".." in path.parts or not path.parts
                        or any("\\" in part or ":" in part for part in path.parts)
                        or not (path == PurePosixPath("workbench")
                                or path == PurePosixPath("workbench/agents.json")
                                or path.parts[:2] == ("workbench", "infra"))):
                    raise CheckError("The checked-in Lab source archive contains an unexpected path.")
                target = destination.joinpath(*path.parts)
                if entry.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                elif entry.isfile():
                    name = path.name
                    if (name in ("terraform.tfvars", "terraform.tfvars.json")
                            or name.endswith((".auto.tfvars", ".auto.tfvars.json"))):
                        raise CheckError("Unexpected checked-in automatic Terraform inputs require separate review.")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    source = archive.extractfile(entry)
                    if source is None:
                        raise CheckError("A checked-in Lab source file is unavailable.")
                    with source, target.open("xb") as output:
                        shutil.copyfileobj(source, output)
                else:
                    raise CheckError("The checked-in Lab source archive contains an unsupported entry.")
    except tarfile.TarError:
        raise CheckError("The checked-in Lab source archive is invalid.") from None
    root = destination / "workbench" / "infra"
    if not (root / "main.tf").is_file() or not (destination / "workbench" / "agents.json").is_file():
        raise CheckError("The checked-in Lab Terraform root or its agent catalogue is missing.")
    return root


def lab_state(raw, subscription):
    state = object_json(raw)
    resources = state.get("resources")
    if (state.get("version") != 4 or type(state.get("serial")) is not int
            or not isinstance(state.get("lineage"), str) or not state["lineage"]
            or not isinstance(resources, list) or any(not isinstance(item, dict) for item in resources)):
        raise CheckError("The selected existing Lab state is invalid or empty.")

    def instances(module, resource_type, name):
        matches = [
            item for item in resources
            if item.get("mode") == "managed" and item.get("module") == module
            and item.get("type") == resource_type and item.get("name") == name
        ]
        if len(matches) != 1 or not isinstance(matches[0].get("instances"), list):
            raise CheckError("The selected state does not own the expected existing Lab resources.")
        found = matches[0]["instances"]
        if any(not isinstance(item, dict) or item.get("deposed") for item in found):
            raise CheckError("The selected Lab state contains incomplete or deposed target resources.")
        return found

    app = instances(None, "azurerm_container_app", "this")
    if len(app) != 1 or app[0].get("index_key") != 0 or not isinstance(app[0].get("attributes"), dict):
        raise CheckError("The selected state does not own the existing Lab Container App.")
    attributes = app[0]["attributes"]
    app_id, app_name = attributes.get("id"), attributes.get("name")
    match = re.fullmatch(
        r"/subscriptions/(" + GUID + r")/resourceGroups/([A-Za-z0-9._()-]{1,90})"
        r"/providers/Microsoft\.App/containerApps/([A-Za-z0-9-]+)",
        app_id if isinstance(app_id, str) else "", flags=re.IGNORECASE,
    )
    if (not match or not isinstance(app_name, str) or match.group(1).lower() != subscription.lower()
            or match.group(3).lower() != app_name.lower()):
        raise CheckError("The selected state does not match the approved subscription and Lab app.")
    group = match.group(2)
    prefix = f"/subscriptions/{subscription}/resourceGroups/{group}/providers/"

    waf = instances("module.front_door[0]", "azurerm_cdn_frontdoor_firewall_policy", "wafs")
    operational = instances(None, "azurerm_monitor_scheduled_query_rules_alert_v2", "operational")
    heartbeat = instances(None, "azurerm_monitor_scheduled_query_rules_alert_v2", "heartbeat")
    expected = [
        (waf, "lab", prefix + "Microsoft.Network/frontdoorWebApplicationFirewallPolicies/waf"
         + app_name.replace("-", "")),
        (operational, "request-failures", prefix + "Microsoft.Insights/scheduledQueryRules/"
         + app_name + "-request-failures"),
        (operational, "dependencies", prefix + "Microsoft.Insights/scheduledQueryRules/"
         + app_name + "-dependencies"),
        (heartbeat, None, prefix + "Microsoft.Insights/scheduledQueryRules/" + app_name + "-missing-heartbeat"),
    ]
    if len(waf) != 1 or len(operational) != 2 or len(heartbeat) != 1:
        raise CheckError("The selected state does not contain exactly the existing WAF and three alerts.")
    for collection, index, expected_id in expected:
        matches = [item for item in collection if item.get("index_key") == index]
        attrs = matches[0].get("attributes") if len(matches) == 1 else None
        resource_id = attrs.get("id") if isinstance(attrs, dict) else None
        if not isinstance(resource_id, str) or resource_id.lower() != expected_id.lower():
            raise CheckError("The selected state does not contain the expected Lab WAF and alerts.")
    return {"app_id": app_id, "app_name": app_name}


def current_image(environ, app):
    headers = {"Authorization": f"Bearer {azure_token(environ, scope='https://management.azure.com/.default')}"}
    base = "https://management.azure.com" + quote(app["app_id"], safe="/")
    app_response = json_response(base + "?api-version=2024-03-01", headers=headers)
    properties = app_response.get("properties")
    config = properties.get("configuration") if isinstance(properties, dict) else None
    revision = properties.get("latestReadyRevisionName") if isinstance(properties, dict) else None
    if (not isinstance(app_response.get("id"), str)
            or app_response["id"].lower() != app["app_id"].lower()
            or not isinstance(config, dict) or config.get("activeRevisionsMode", "Single") != "Single"
            or not isinstance(revision, str) or not re.fullmatch(r"[A-Za-z0-9-]+", revision)):
        raise CheckError("The existing Lab does not have a verifiable single ready revision.")
    revision_id = app["app_id"] + "/revisions/" + revision
    response = json_response(
        base + "/revisions/" + quote(revision, safe="") + "?api-version=2024-03-01", headers=headers,
    )
    details = response.get("properties")
    template = details.get("template") if isinstance(details, dict) else None
    containers = template.get("containers") if isinstance(template, dict) else None
    if (not isinstance(response.get("id"), str) or response["id"].lower() != revision_id.lower()
            or not isinstance(details, dict) or details.get("active") is not True
            or not isinstance(containers, list) or any(not isinstance(item, dict) for item in containers)):
        raise CheckError("The existing Lab revision is not active or its image is unavailable.")
    matches = [item.get("image") for item in containers if item.get("name") == "workbench"]
    image = matches[0] if len(matches) == 1 else None
    match = re.fullmatch(r"[^@\s]+@(sha256:[a-f0-9]{64})", image if isinstance(image, str) else "")
    if not match:
        raise CheckError("The active Lab image must have a verified immutable SHA-256 digest.")
    return revision, match.group(1)


def validate_inputs(values, app, digest, environ):
    if not isinstance(values, dict) or set(values) != {
        "subscription_id", "name", "bootstrap_only", "enable_front_door", "image_digest", "platform_state",
    }:
        raise CheckError("Terraform did not resolve every required protected Lab input.")
    if (values.get("subscription_id") != environ["AZURE_SUBSCRIPTION_ID"]
            or values.get("name") != app["app_name"] or values.get("bootstrap_only") is not False
            or values.get("enable_front_door") is not True):
        raise CheckError("Canonical inputs must select the existing subscription, app and enabled Front Door.")
    if values.get("image_digest") != digest:
        raise CheckError("The canonical image input differs from the active immutable Lab image.")
    platform = values.get("platform_state")
    if platform is None:
        return None
    if not isinstance(platform, dict) or set(platform) != {
        "subscription_id", "resource_group_name", "storage_account_name", "container_name", "key",
    }:
        raise CheckError("The platform state inputs are incomplete or unsupported.")
    subscription = platform["subscription_id"] or environ["AZURE_SUBSCRIPTION_ID"]
    default_account = "staifnd" + hashlib.sha256(environ["AZURE_SUBSCRIPTION_ID"].encode()).hexdigest()[:8] + "tf"
    account = platform["storage_account_name"] or default_account
    if (subscription != environ["AZURE_SUBSCRIPTION_ID"] or account != environ["TF_STATE_ACCOUNT"]
            or platform["container_name"] != environ["TF_STATE_CONTAINER"]
            or platform["key"] != "ai-foundry/dev.tfstate"):
        raise CheckError("Platform state must use the same approved private backend and dev state key.")
    return PLATFORM_STATE


def write_supplemental_files(root, digest):
    files = {
        "diagnostic.auto.tfvars.json": json.dumps({"image_digest": digest}) + "\n",
        "diagnostic-privacy.tf": 'provider "modtm" {\n  enabled = false\n}\n',
    }
    for name, contents in files.items():
        path = root / name
        if path.exists():
            raise CheckError("A reserved diagnostic-only source file already exists.")
        path.write_text(contents, encoding="utf-8")


def configure_platform_oidc(root):
    path = root / "platform.tf"
    try:
        source = path.read_text(encoding="utf-8")
    except OSError:
        raise CheckError("The checked-in Lab platform-state configuration is unavailable.") from None
    expected = "    use_azuread_auth     = true\n    use_cli              = true"
    replacement = "    use_azuread_auth     = true\n    use_oidc             = true\n    use_cli              = false"
    if source.count(expected) != 1:
        raise CheckError("The checked-in Lab platform-state authentication block changed; review is required.")
    path.write_text(source.replace(expected, replacement, 1), encoding="utf-8")


class LabTerraform(Terraform):
    def __init__(self, root, scratch, environ, inputs):
        super().__init__(root, scratch, environ, LAB_STATE, inputs, input_suffix=".tfvars")

    def command(self, *args, allowed=(0,), input_data=None):
        backend = f"-backend-config={self.scratch / 'backend.hcl'}"
        var_file = f"-var-file={self.inputs}"
        saved = self.scratch / "lab.tfplan"
        permitted = (
            (args == ("init", "-reconfigure", backend) and allowed == (0,) and input_data is None)
            or (args == ("console", var_file) and allowed == (0,) and input_data == CONSOLE_INPUT)
            or (args == ("plan", "-input=false", "-detailed-exitcode", "-refresh=true", "-lock=true",
                         "-lock-timeout=5m", var_file, f"-out={saved}")
                and allowed == (0, 2) and input_data is None)
            or (args == ("show", "-json", str(saved)) and allowed == (0,) and input_data is None)
        )
        if not permitted:
            raise CheckError("Only the fixed private init, input check, full plan and plan inspection are allowed.")
        return super().command(*args, allowed=allowed, input_data=input_data)

    def inputs_resolved(self):
        raw = self.command("console", f"-var-file={self.inputs}", input_data=CONSOLE_INPUT)
        try:
            encoded = json.loads(raw)
        except (ValueError, UnicodeError):
            raise CheckError("Terraform did not resolve the protected Lab inputs.") from None
        if not isinstance(encoded, str):
            raise CheckError("Terraform returned an incomplete protected input check.")
        return object_json(encoded)

    def full_plan(self):
        saved = self.scratch / "lab.tfplan"
        self.command(
            "plan", "-input=false", "-detailed-exitcode", "-refresh=true", "-lock=true",
            "-lock-timeout=5m", f"-var-file={self.inputs}", f"-out={saved}", allowed=(0, 2),
        )
        exit_code = self.last_exitcode
        return object_json(self.command("show", "-json", str(saved))), exit_code


def has_unknown(value):
    if value is True:
        return True
    if value is False or value is None:
        return False
    if isinstance(value, list):
        return any([has_unknown(item) for item in value])
    if isinstance(value, dict):
        return any([has_unknown(item) for item in value.values()])
    raise CheckError("Terraform returned invalid unknown-value metadata.")


def changed_fields(before, after, unknown, schema):
    changed, unknown_fields = set(), set()

    def walk(left, right, pending, fields, path):
        label = path or "resource"
        if pending is True:
            changed.add(label)
            unknown_fields.add(label)
            return
        if fields is True:
            if left != right or has_unknown(pending):
                changed.add(label)
            if has_unknown(pending):
                unknown_fields.add(label)
            return
        if isinstance(left, list) or isinstance(right, list):
            if any(value is not MISSING and value is not None and not isinstance(value, list)
                   for value in (left, right)):
                changed.add(label)
                return
            left = left if isinstance(left, list) else []
            right = right if isinstance(right, list) else []
            if len(left) != len(right):
                changed.add(label)
            if pending is False or pending is None:
                pending = []
            if not isinstance(pending, list):
                if has_unknown(pending):
                    changed.add(label)
                    unknown_fields.add(label)
                pending = []
            for index in range(max(len(left), len(right), len(pending))):
                walk(left[index] if index < len(left) else MISSING,
                     right[index] if index < len(right) else MISSING,
                     pending[index] if index < len(pending) else False, fields, path)
            return
        if any(value is not MISSING and value is not None and not isinstance(value, dict)
               for value in (left, right)):
            if left != right or has_unknown(pending):
                changed.add(label)
            if has_unknown(pending):
                unknown_fields.add(label)
            return
        left = left if isinstance(left, dict) else {}
        right = right if isinstance(right, dict) else {}
        if not isinstance(pending, dict):
            if has_unknown(pending):
                changed.add(label)
                unknown_fields.add(label)
            pending = {}
        for key in fields:
            walk(left.get(key, MISSING), right.get(key, MISSING), pending.get(key, False),
                 fields[key], f"{path}.{key}" if path else key)
        for key in (left.keys() | right.keys() | pending.keys()) - fields.keys():
            item_unknown = pending.get(key, False)
            if left.get(key, MISSING) != right.get(key, MISSING) or has_unknown(item_unknown):
                changed.add(f"{path}.other" if path else "other")
            if has_unknown(item_unknown):
                unknown_fields.add(f"{path}.other" if path else "other")

    walk(before, after, unknown, schema, "")
    return sorted(changed), sorted(unknown_fields)


def change_action(entry):
    if not isinstance(entry, dict) or not isinstance(entry.get("change"), dict):
        raise CheckError("Terraform returned an invalid resource change.")
    change = entry["change"]
    actions = change.get("actions")
    if (not isinstance(actions, list) or any(not isinstance(action, str) for action in actions)
            or tuple(actions) not in ACTIONS):
        raise CheckError("Terraform returned unsupported resource actions.")
    return ACTIONS[tuple(actions)], change.get("importing") is not None


def change_summary(entry, schema):
    action, importing = change_action(entry)
    change = entry["change"]
    if "before" not in change or "after" not in change:
        raise CheckError("Terraform returned an incomplete target resource change.")
    changed, unknown = changed_fields(
        change.get("before"), change.get("after"), change.get("after_unknown", False), schema,
    )
    if action != "no-op" and not changed:
        changed = ["resource"]
    return {
        "action": action, "fields": changed, "unknown_fields": unknown, "import": importing,
    }


def summarize_plan(plan, exit_code, values):
    if (plan.get("errored") is not False or plan.get("complete") is not True
            or plan.get("deferred_changes") or plan.get("action_invocations")):
        raise CheckError("Terraform must produce a complete, error-free, non-deferred plan.")
    if not isinstance(plan.get("format_version"), str) or not re.fullmatch(r"1\.[0-9]+", plan["format_version"]):
        raise CheckError("Terraform returned an unsupported plan format.")
    variables = plan.get("variables")
    for name in ("subscription_id", "name", "bootstrap_only", "enable_front_door", "image_digest"):
        item = variables.get(name) if isinstance(variables, dict) else None
        if not isinstance(item, dict) or item.get("value", MISSING) != values.get(name, MISSING):
            raise CheckError("The plan did not use the checked protected Lab inputs.")
    changes = plan.get("resource_changes")
    drift = plan.get("resource_drift", [])
    output_changes = plan.get("output_changes", {})
    checks = plan.get("checks", [])
    if (not isinstance(changes, list) or not isinstance(drift, list)
            or not isinstance(output_changes, dict) or not isinstance(checks, list)):
        raise CheckError("Terraform returned an incomplete plan summary.")
    targets = {label: {"planned": None, "refreshed_drift": []} for label in TARGETS.values()}
    other_changes = data_reads = other_drift = imports = unknown_resources = 0
    other_actions = dict.fromkeys((action for action in ACTIONS.values() if action != "no-op"), 0)
    drift_actions = dict.fromkeys(other_actions, 0)
    output_actions = dict.fromkeys(("create", "update", "delete"), 0)
    for entry in changes:
        if not isinstance(entry, dict) or not isinstance(entry.get("address"), str):
            raise CheckError("Terraform returned an invalid resource change.")
        label = TARGETS.get(entry.get("address"))
        action, importing = change_action(entry)
        unknown_resources += has_unknown(entry["change"].get("after_unknown", False))
        if importing:
            imports += 1
        if label:
            if entry.get("mode") != "managed" or targets[label]["planned"] is not None:
                raise CheckError("A target resource appeared more than once or with an unexpected mode.")
            targets[label]["planned"] = change_summary(entry, WAF_FIELDS if label == "waf" else ALERT_FIELDS)
        elif entry.get("mode") == "managed":
            other_changes += action != "no-op"
            if action != "no-op":
                other_actions[action] += 1
        elif entry.get("mode") == "data":
            data_reads += action != "no-op"
        else:
            raise CheckError("Terraform returned an unsupported resource mode.")
    if any(target["planned"] is None for target in targets.values()):
        raise CheckError("A target resource is absent from the complete Lab plan.")
    for entry in drift:
        if not isinstance(entry, dict) or not isinstance(entry.get("address"), str):
            raise CheckError("Terraform returned an invalid refreshed-drift entry.")
        label = TARGETS.get(entry.get("address"))
        action, _ = change_action(entry)
        if label:
            if entry.get("mode") != "managed" or targets[label]["refreshed_drift"]:
                raise CheckError("A target has duplicate or unexpected refreshed-drift entries.")
            targets[label]["refreshed_drift"].append(change_summary(entry, WAF_FIELDS if label == "waf" else ALERT_FIELDS))
        elif entry.get("mode") == "managed":
            other_drift += action != "no-op"
            if action != "no-op":
                drift_actions[action] += 1
        else:
            raise CheckError("Terraform returned an unsupported refreshed-drift mode.")
    output_count = unknown_outputs = 0
    for change in output_changes.values():
        if (not isinstance(change, dict) or not isinstance(change.get("actions"), list)
                or any(not isinstance(action, str) for action in change["actions"])):
            raise CheckError("Terraform returned an invalid output change.")
        actions = tuple(change["actions"])
        if actions not in (("no-op",), ("create",), ("update",), ("delete",)):
            raise CheckError("Terraform returned unsupported output actions.")
        output_count += actions != ("no-op",)
        if actions != ("no-op",):
            output_actions[actions[0]] += 1
        unknown_outputs += has_unknown(change.get("after_unknown", False))
    if any(not isinstance(check, dict) or check.get("status") not in ("pass", "fail", "unknown", "error")
           for check in checks):
        raise CheckError("Terraform returned invalid check results.")
    nonpassing_checks = sum(check["status"] != "pass" for check in checks)
    planned_changes = (
        other_changes + output_count + imports
        + sum(target["planned"]["action"] != "no-op" for target in targets.values())
    )
    if exit_code not in (0, 2) or (exit_code == 0 and planned_changes):
        raise CheckError("Terraform's plan exit status does not match its reported changes.")
    return {
        "plan_exit": "changes" if exit_code == 2 else "no-changes",
        "targets": targets,
        "other_managed_changes": other_changes,
        "other_managed_actions": other_actions,
        "other_refreshed_drift": other_drift,
        "other_refreshed_drift_actions": drift_actions,
        "data_reads": data_reads,
        "output_changes": output_count,
        "output_actions": output_actions,
        "resources_with_unknown_values": unknown_resources,
        "outputs_with_unknown_values": unknown_outputs,
        "imports": imports,
        "nonpassing_checks": nonpassing_checks,
    }


def run(environ=os.environ):
    runtime = configuration(environ)
    blobs = LabBlobs(runtime)
    snapshots = {name: blobs.snapshot(name) for name in (LAB_STATE, LAB_INPUTS)}
    app = lab_state(snapshots[LAB_STATE][0], runtime["AZURE_SUBSCRIPTION_ID"])
    revision, digest = current_image(runtime, app)
    summary = None
    try:
        with private_scratch(runtime) as scratch:
            root = stage_sources(scratch, runtime)
            configure_platform_oidc(root)
            write_supplemental_files(root, digest)
            terraform = LabTerraform(root, scratch, runtime, snapshots[LAB_INPUTS][0])
            values = terraform.inputs_resolved()
            platform = validate_inputs(values, app, digest, runtime)
            if platform:
                snapshots[platform] = blobs.snapshot(platform)
            plan, exit_code = terraform.full_plan()
            summary = summarize_plan(plan, exit_code, values)
            if current_image(runtime, app) != (revision, digest):
                raise CheckError("The active Lab revision changed during the diagnostic; the result is invalid.")
    finally:
        if any(not snapshot_unchanged(name, snapshot, blobs.snapshot(name)) for name, snapshot in snapshots.items()):
            raise CheckError("A protected input or state blob changed during the diagnostic; the result is invalid.")
    print("Private full-root Lab plan; actions and schema fields only:")
    print(json.dumps(summary, indent=2, sort_keys=True))
    print("Protected inputs, state contents and non-lock metadata were unchanged; no infrastructure apply ran.")
    if summary["nonpassing_checks"]:
        raise CheckError("Terraform reported non-passing or unknown checks; the diagnostic is incomplete.")


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
        print(f"Lab plan diagnostic failed: {message}", file=sys.stderr)
        sys.exit(1)

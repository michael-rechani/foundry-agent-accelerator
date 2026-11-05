"""Pin the existing Lab monitoring scope without changing Azure resources."""

import base64
from contextlib import contextmanager
import hashlib
import json
import os
import sys
import uuid
from urllib.parse import quote

from check_lab_terraform_plan import (
    LAB_INPUTS,
    LAB_STATE,
    LabBlobs,
    configuration,
    configure_platform_oidc,
    current_image,
    lab_state,
    snapshot_unchanged,
    stage_sources,
    validate_inputs,
    write_supplemental_files,
)
from check_state_backend import CheckError, azure_token, json_response, send
from reconcile_runner_state import Terraform, cleanup, object_json, private_scratch

SCOPE_NAME = "ampls-aifnd-dev"
APP_NAME = "foundry-workbench"
CONSOLE_INPUT = (
    b"jsonencode({subscription_id=var.subscription_id,name=var.name,"
    b"bootstrap_only=var.bootstrap_only,enable_front_door=var.enable_front_door,"
    b"image_digest=var.image_digest,platform_state=var.platform_state,"
    b"explicit_scope=var.monitor_private_link_scope_name,"
    b"unfinished_agents_enabled=var.unfinished_agents_enabled})\n"
)
BASE_INPUT_KEYS = {
    "subscription_id", "name", "bootstrap_only", "enable_front_door", "image_digest", "platform_state",
}
CONTENT_HEADERS = {
    "content-type": "x-ms-blob-content-type",
    "content-language": "x-ms-blob-content-language",
    "content-disposition": "x-ms-blob-content-disposition",
    "cache-control": "x-ms-blob-cache-control",
}


def expected_ids(app):
    app_id = app.get("app_id")
    suffix = f"/providers/Microsoft.App/containerApps/{APP_NAME}"
    if app.get("app_name") != APP_NAME or not isinstance(app_id, str) or not app_id.lower().endswith(suffix.lower()):
        raise CheckError("Only the existing foundry-workbench Lab is approved for this operation.")
    group = app_id[:-len(suffix)]
    scope = group + f"/providers/Microsoft.Insights/privateLinkScopes/{SCOPE_NAME}"
    return {
        "association": scope + f"/scopedResources/law-{APP_NAME}",
        "workspace": group + f"/providers/Microsoft.OperationalInsights/workspaces/log-{APP_NAME}",
    }


def validate_scope_state(raw, app):
    state = object_json(raw)
    resources = state.get("resources")
    matches = [
        item for item in resources or []
        if isinstance(item, dict) and item.get("mode") == "managed" and not item.get("module")
        and item.get("type") == "azurerm_monitor_private_link_scoped_service" and item.get("name") == "logs"
    ]
    if len(matches) != 1 or not isinstance(matches[0].get("instances"), list):
        raise CheckError("The Lab state does not own exactly one monitoring association.")
    instances = matches[0]["instances"]
    if (len(instances) != 1 or not isinstance(instances[0], dict) or instances[0].get("deposed")
            or instances[0].get("index_key") is not None
            or not isinstance(instances[0].get("attributes"), dict)):
        raise CheckError("The saved monitoring association is incomplete.")
    attrs = instances[0]["attributes"]
    ids = expected_ids(app)
    if (not isinstance(attrs.get("id"), str) or attrs["id"].lower() != ids["association"].lower()
            or attrs.get("scope_name") != SCOPE_NAME
            or not isinstance(attrs.get("linked_resource_id"), str)
            or attrs["linked_resource_id"].lower() != ids["workspace"].lower()):
        raise CheckError("The saved monitoring association does not match the existing dev Lab scope and workspace.")
    return ids


def validate_live_scope(environ, ids):
    headers = {"Authorization": f"Bearer {azure_token(environ, scope='https://management.azure.com/.default')}"}
    url = "https://management.azure.com" + quote(ids["association"], safe="/") + "?api-version=2021-07-01-preview"
    response = json_response(url, headers=headers)
    properties = response.get("properties")
    if (not isinstance(response.get("id"), str)
            or response["id"].lower() != ids["association"].lower()
            or not isinstance(properties, dict)
            or not isinstance(properties.get("linkedResourceId"), str)
            or properties["linkedResourceId"].lower() != ids["workspace"].lower()
            or str(properties.get("provisioningState", "")).lower() != "succeeded"):
        raise CheckError("The live monitoring association is not the expected healthy Lab workspace association.")


def live_unfinished_agents(environ, app, revision):
    headers = {"Authorization": f"Bearer {azure_token(environ, scope='https://management.azure.com/.default')}"}
    revision_id = app["app_id"] + "/revisions/" + revision
    url = "https://management.azure.com" + quote(revision_id, safe="/") + "?api-version=2024-03-01"
    response = json_response(url, headers=headers)
    properties = response.get("properties")
    template = properties.get("template") if isinstance(properties, dict) else None
    containers = template.get("containers") if isinstance(template, dict) else None
    if (not isinstance(response.get("id"), str) or response["id"].lower() != revision_id.lower()
            or not isinstance(properties, dict) or properties.get("active") is not True
            or not isinstance(containers, list) or len(containers) != 1
            or not isinstance(containers[0], dict) or containers[0].get("name") != "workbench"):
        raise CheckError("The active Lab revision could not be inspected safely.")
    entries = containers[0].get("env", [])
    if not isinstance(entries, list) or any(not isinstance(entry, dict) for entry in entries):
        raise CheckError("The active Lab environment has an unsupported shape.")
    matches = [entry for entry in entries if entry.get("name") == "WORKBENCH_UNFINISHED_AGENTS_ENABLED"]
    if not matches:
        return "absent"
    if len(matches) != 1 or matches[0].get("value") not in ("true", "false"):
        raise CheckError("The active Lab unfinished-agent setting is ambiguous.")
    return "enabled" if matches[0]["value"] == "true" else "disabled"


def platform_scope(raw):
    state = object_json(raw)
    outputs = state.get("outputs", {})
    if state.get("version") != 4 or not isinstance(outputs, dict):
        raise CheckError("The selected platform state has an unsupported output format.")
    if "monitor_private_link_scope_name" not in outputs:
        return None
    result = outputs["monitor_private_link_scope_name"]
    if not isinstance(result, dict) or "value" not in result:
        raise CheckError("The platform monitoring-scope output is incomplete.")
    value = result["value"]
    if value is not None and not isinstance(value, str):
        raise CheckError("The platform monitoring-scope output has an unsupported type.")
    return value


class MonitorTerraform(Terraform):
    def __init__(self, root, scratch, environ, inputs):
        super().__init__(root, scratch, environ, LAB_STATE, inputs, input_suffix=".tfvars")

    def command(self, *args, allowed=(0,), input_data=None):
        backend = f"-backend-config={self.scratch / 'backend.hcl'}"
        var_file = f"-var-file={self.inputs}"
        permitted = (
            (args == ("init", "-reconfigure", backend) and allowed == (0,) and input_data is None)
            or (args == ("console", var_file) and allowed == (0,) and input_data == CONSOLE_INPUT)
        )
        if not permitted:
            raise CheckError("Only the fixed private init and input inspection are allowed.")
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


def validate_values(values, app, digest, environ):
    if not isinstance(values, dict) or set(values) != BASE_INPUT_KEYS | {
        "explicit_scope", "unfinished_agents_enabled",
    }:
        raise CheckError("Terraform did not resolve every required monitoring input.")
    platform = validate_inputs({name: values[name] for name in BASE_INPUT_KEYS}, app, digest, environ)
    if values["explicit_scope"] not in (None, SCOPE_NAME):
        raise CheckError("A configured monitoring scope differs from the verified existing dev scope.")
    if type(values["unfinished_agents_enabled"]) is not bool:
        raise CheckError("The unfinished-agent input must resolve to a boolean.")
    return platform


def append_scope(raw):
    if not isinstance(raw, bytes) or not raw or len(raw) > 1024 * 1024:
        raise CheckError("The canonical Lab input file is empty or unexpectedly large.")
    separator = b"" if raw.endswith(b"\n") else b"\n"
    return raw + separator + b'\nmonitor_private_link_scope_name = "ampls-aifnd-dev"\n'


class InputBlob:
    def __init__(self, blobs):
        self.url = blobs.base + LAB_INPUTS
        self.headers = blobs.headers

    def snapshot(self, lease_id=None):
        request_headers = {**self.headers, **({"x-ms-lease-id": lease_id} if lease_id else {})}
        body, response = send(self.url, headers=request_headers)
        etag = response.get("ETag")
        if not isinstance(etag, str) or not etag:
            raise CheckError("The canonical input blob did not return a version.")
        _, response = send(self.url, method="HEAD", headers={**request_headers, "If-Match": etag})
        headers = {key.lower(): value for key, value in response.items()}
        if headers.get("etag") != etag or headers.get("x-ms-blob-type") != "BlockBlob":
            raise CheckError("The canonical input blob changed or has an unsupported type.")
        expected_lease = "locked" if lease_id else "unlocked"
        if headers.get("x-ms-lease-status") != expected_lease:
            raise CheckError("The canonical input blob has an unexpected lease.")
        if (headers.get("x-ms-tag-count", "0") != "0"
                or headers.get("x-ms-copy-status") == "pending"
                or headers.get("x-ms-has-legal-hold", "false").lower() != "false"
                or headers.get("x-ms-has-immutability-policy", "false").lower() != "false"
                or any(headers.get(name) for name in (
                    "x-ms-encryption-key-sha256", "x-ms-encryption-context", "x-ms-expiry-time",
                    "x-ms-owner", "x-ms-group", "x-ms-acl",
                ))
                or headers.get("content-encoding", "").lower() not in ("", "identity")):
            raise CheckError("The canonical input blob has properties that require separate review.")
        if "content-length" in headers:
            try:
                complete = int(headers["content-length"]) == len(body)
            except ValueError:
                complete = False
            if not complete:
                raise CheckError("The canonical input blob was not read completely.")
        if "content-md5" in headers:
            checksum = base64.b64encode(hashlib.md5(body, usedforsecurity=False).digest()).decode()
            if headers["content-md5"] != checksum:
                raise CheckError("The canonical input blob failed its content integrity check.")
        preserved = {key: value for key, value in headers.items() if key.startswith("x-ms-meta-")}
        if "x-ms-meta-terraformlockid" in preserved:
            raise CheckError("The canonical input blob contains unexpected Terraform lock metadata.")
        preserved.update({target: headers[source] for source, target in CONTENT_HEADERS.items() if source in headers})
        if headers.get("content-encoding"):
            preserved["x-ms-blob-content-encoding"] = headers["content-encoding"]
        if headers.get("x-ms-encryption-scope"):
            preserved["x-ms-encryption-scope"] = headers["x-ms-encryption-scope"]
        tier = headers.get("x-ms-access-tier")
        inferred = headers.get("x-ms-access-tier-inferred", "false").lower()
        if inferred not in ("true", "false") or (tier and tier not in ("Hot", "Cool", "Cold")):
            raise CheckError("The canonical input blob has an unsupported storage tier.")
        if tier and inferred == "false":
            preserved["x-ms-access-tier"] = tier
        return body, etag, preserved

    @contextmanager
    def lease(self, etag):
        lease_id = str(uuid.uuid4())
        send(self.url + "?comp=lease", method="PUT", headers={
            **self.headers, "If-Match": etag, "x-ms-lease-action": "acquire",
            "x-ms-lease-duration": "60", "x-ms-proposed-lease-id": lease_id,
        }, data=b"", expected=(201,))
        try:
            yield lease_id
        finally:
            try:
                send(self.url + "?comp=lease", method="PUT", headers={
                    **self.headers, "x-ms-lease-action": "release", "x-ms-lease-id": lease_id,
                }, data=b"")
            except CheckError:
                raise CheckError("The input blob lease could not be released; it expires after 60 seconds.") from None

    def replace(self, candidate, snapshot, lease_id):
        _, etag, preserved = snapshot
        send(self.url, method="PUT", headers={
            **self.headers, **preserved, "If-Match": etag,
            "x-ms-blob-type": "BlockBlob", "x-ms-lease-id": lease_id,
        }, data=candidate, expected=(201,))


def run(environ=os.environ):
    operation = environ.get("TF_LAB_MONITOR_OPERATION")
    if operation not in ("inspect", "pin-existing-scope"):
        raise CheckError("Only inspection or pinning the verified existing scope is allowed.")
    runtime = configuration(environ)
    blobs = LabBlobs(runtime)
    inputs = InputBlob(blobs)
    state_before = blobs.snapshot(LAB_STATE)
    input_before = inputs.snapshot()
    app = lab_state(state_before[0], runtime["AZURE_SUBSCRIPTION_ID"])
    ids = validate_scope_state(state_before[0], app)
    revision, digest = current_image(runtime, app)
    validate_live_scope(runtime, ids)
    live_unfinished = live_unfinished_agents(runtime, app, revision)
    old_umask = os.umask(0o077)
    write_attempted = False
    try:
        with private_scratch(runtime) as scratch:
            root = stage_sources(scratch, runtime)
            configure_platform_oidc(root)
            write_supplemental_files(root, digest)
            terraform = MonitorTerraform(root, scratch, runtime, input_before[0])
            before = terraform.inputs_resolved()
            platform = validate_values(before, app, digest, runtime)
            platform_before = blobs.snapshot(platform) if platform else None
            platform_value = platform_scope(platform_before[0]) if platform_before else None
            if platform_value not in (None, SCOPE_NAME):
                raise CheckError("The platform monitoring output differs from the verified existing dev scope.")
            source = "explicit" if before["explicit_scope"] else "platform" if platform_value else "fallback"
            candidate = None
            if source == "fallback":
                candidate = append_scope(input_before[0])
                terraform.inputs.write_bytes(candidate)
                after = terraform.inputs_resolved()
                validate_values(after, app, digest, runtime)
                if after != {**before, "explicit_scope": SCOPE_NAME}:
                    raise CheckError("The proposed input would change more than the verified monitoring scope.")
            if (not snapshot_unchanged(LAB_STATE, state_before, blobs.snapshot(LAB_STATE))
                    or inputs.snapshot() != input_before
                    or (platform and blobs.snapshot(platform) != platform_before)
                    or current_image(runtime, app) != (revision, digest)):
                raise CheckError("The Lab state, inputs, platform state or active revision changed.")
            validate_live_scope(runtime, ids)
            if operation == "pin-existing-scope" and candidate is not None:
                with inputs.lease(input_before[1]) as lease_id:
                    if inputs.snapshot(lease_id) != input_before:
                        raise CheckError("The canonical inputs changed before the guarded update.")
                    validate_live_scope(runtime, ids)
                    write_attempted = True
                    inputs.replace(candidate, input_before, lease_id)
                    updated = inputs.snapshot(lease_id)
                    if (updated[0] != candidate or updated[1] == input_before[1]
                            or updated[2] != input_before[2]):
                        raise CheckError("The updated input blob did not match the verified candidate.")
                if (not snapshot_unchanged(LAB_STATE, state_before, blobs.snapshot(LAB_STATE))
                        or (platform and blobs.snapshot(platform) != platform_before)
                        or current_image(runtime, app) != (revision, digest)):
                    raise CheckError("Protected state or the active revision changed after the input update.")
                validate_live_scope(runtime, ids)
                source = "pinned"
    except (CheckError, OSError):
        if write_attempted:
            print("The input update was attempted; verify the protected input before retrying.", file=sys.stderr)
        raise
    finally:
        os.umask(old_umask)
    print(f"Existing Lab monitoring association verified; scope source: {source}.")
    desired_unfinished = "enabled" if before["unfinished_agents_enabled"] else "disabled"
    print(f"Unfinished-agent flag: live {live_unfinished}; canonical input {desired_unfinished}.")
    print("Other application environment differences still require a full refreshed plan.")
    if source == "pinned":
        print("Only the existing monitoring-scope input was appended; all prior input bytes were preserved.")
    else:
        print("No canonical inputs were changed.")
    print("No Terraform apply, WAF change, public-access change, or infrastructure deployment ran.")


if __name__ == "__main__":
    try:
        if sys.argv[1:] == ["--cleanup"]:
            cleanup()
        elif not sys.argv[1:]:
            run()
        else:
            raise CheckError("This operation accepts no Terraform or file arguments.")
    except (CheckError, OSError) as exc:
        message = str(exc) if isinstance(exc, CheckError) else "Private local file or process access failed."
        print(f"Lab monitoring input reconciliation failed: {message}", file=sys.stderr)
        sys.exit(1)

"""Pin the live Lab WAF allow-list into the private canonical inputs without changing Azure."""

import ipaddress
import json
import os
import re
import sys
from urllib.parse import quote

from check_lab_terraform_plan import (
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
from check_state_backend import CheckError, azure_token, json_response
from reconcile_lab_monitor_scope import BASE_INPUT_KEYS, InputBlob
from reconcile_runner_state import Terraform, cleanup, object_json, private_scratch

APP_NAME = "foundry-workbench"
ARM_SCOPE = "https://management.azure.com/.default"
RULE_NAME = "BlockUnlistedClients"
MAX_ENTRIES = 10
CONSOLE_INPUT = (
    b"jsonencode({subscription_id=var.subscription_id,name=var.name,"
    b"bootstrap_only=var.bootstrap_only,enable_front_door=var.enable_front_door,"
    b"image_digest=var.image_digest,platform_state=var.platform_state,"
    b"allowed=var.front_door_allowed_cidrs})\n"
)
ENTRY = re.compile(r"[0-9A-Fa-f:.]{2,45}/(?:32|128)")
ATTRIBUTE = re.compile(rb"(?m)^[ \t]*front_door_allowed_cidrs[ \t]*=[ \t]*")


def expected_waf_id(app):
    app_id = app.get("app_id")
    suffix = f"/providers/Microsoft.App/containerApps/{APP_NAME}"
    if app.get("app_name") != APP_NAME or not isinstance(app_id, str) or not app_id.lower().endswith(suffix.lower()):
        raise CheckError("Only the existing foundry-workbench Lab is approved for this operation.")
    group = app_id[:-len(suffix)]
    return group + "/providers/Microsoft.Network/frontdoorWebApplicationFirewallPolicies/waf" + APP_NAME.replace("-", "")


def host_entry(value):
    """Return the canonical form of a single-host entry, or refuse anything else."""
    if not isinstance(value, str) or not ENTRY.fullmatch(value):
        raise CheckError("An allow-list entry is not a single host address.")
    address, _, prefix = value.partition("/")
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError:
        raise CheckError("An allow-list entry is not a valid host address.") from None
    if (parsed.version == 4) != (prefix == "32"):
        raise CheckError("An allow-list entry does not use a single-host prefix length.")
    return str(parsed)


def live_allowlist(environ, waf_id):
    headers = {"Authorization": f"Bearer {azure_token(environ, scope=ARM_SCOPE)}"}
    url = "https://management.azure.com" + quote(waf_id, safe="/") + "?api-version=2024-02-01"
    response = json_response(url, headers=headers)
    properties = response.get("properties")
    custom = properties.get("customRules") if isinstance(properties, dict) else None
    rules = custom.get("rules") if isinstance(custom, dict) else None
    if (not isinstance(response.get("id"), str) or response["id"].lower() != waf_id.lower()
            or not isinstance(rules, list) or len(rules) != 1 or not isinstance(rules[0], dict)):
        raise CheckError("The live Lab WAF does not have exactly the expected custom rule.")
    rule = rules[0]
    conditions = rule.get("matchConditions")
    if (rule.get("name") != RULE_NAME or rule.get("ruleType") != "MatchRule" or rule.get("action") != "Block"
            or rule.get("enabledState") != "Enabled" or not isinstance(conditions, list) or len(conditions) != 1
            or not isinstance(conditions[0], dict)):
        raise CheckError("The live Lab WAF rule is not the expected enabled allow-list block rule.")
    condition = conditions[0]
    values = condition.get("matchValue")
    if (condition.get("matchVariable") != "SocketAddr" or condition.get("operator") != "IPMatch"
            or condition.get("negateCondition") is not True
            or not isinstance(values, list) or not values or len(values) > MAX_ENTRIES):
        raise CheckError("The live Lab WAF allow-list has an unsupported shape.")
    canonical = [host_entry(value) for value in values]
    if len(set(canonical)) != len(canonical):
        raise CheckError("The live Lab WAF allow-list contains duplicate entries.")
    return list(values)


def missing_entries(configured, live):
    """Live entries absent from the inputs, refusing equivalent but differently written addresses."""
    if not isinstance(configured, list) or not configured or any(not isinstance(item, str) for item in configured):
        raise CheckError("The canonical allow-list input is empty or has an unsupported type.")
    known = {host_entry(item) for item in configured}
    if len(known) != len(configured):
        raise CheckError("The canonical allow-list input contains duplicate or equivalent entries.")
    missing = [item for item in live if item not in configured]
    if any(host_entry(item) in known for item in missing):
        raise CheckError("A live entry matches a configured address written differently; review it privately.")
    if len(configured) + len(missing) > MAX_ENTRIES:
        raise CheckError("Pinning would exceed the allow-list size limit.")
    return missing


def scan_list(raw, start):
    """Read a flat HCL list of plain quoted strings starting at raw[start] == b'['."""
    entries, last, last_comma, index = [], start, False, start + 1
    while index < len(raw):
        char = raw[index:index + 1]
        if char in (b" ", b"\t", b"\r", b"\n"):
            index += 1
        elif char == b"#" or raw[index:index + 2] == b"//":
            end = raw.find(b"\n", index)
            index = len(raw) if end < 0 else end
        elif char == b'"':
            end = raw.find(b'"', index + 1)
            body = raw[index + 1:end] if end >= 0 else b""
            if end < 0 or (entries and not last_comma) or not ENTRY.fullmatch(body.decode("ascii", "replace")):
                raise CheckError("The canonical allow-list input has an unsupported list format.")
            entries.append(body.decode("ascii"))
            index = last = end + 1
            last_comma = False
        elif char == b",":
            if not entries or last_comma:
                raise CheckError("The canonical allow-list input has an unsupported list format.")
            index = last = index + 1
            last_comma = True
        elif char == b"]":
            return entries, index, last, last_comma
        else:
            raise CheckError("The canonical allow-list input has an unsupported list format.")
    raise CheckError("The canonical allow-list input list is not closed.")


def append_allowlist(raw, additions):
    if not isinstance(raw, bytes) or not raw or len(raw) > 1024 * 1024:
        raise CheckError("The canonical Lab input file is empty or unexpectedly large.")
    if not additions or any(not ENTRY.fullmatch(item) for item in additions):
        raise CheckError("The entries to pin are missing or unsupported.")
    matches = list(ATTRIBUTE.finditer(raw))
    if len(matches) != 1 or raw[matches[0].end():matches[0].end() + 1] != b"[":
        raise CheckError("The canonical inputs must assign the allow-list exactly once as a plain list.")
    start = matches[0].end()
    entries, close, last, last_comma = scan_list(raw, start)
    if not entries:
        raise CheckError("The canonical allow-list input list is empty.")
    close_line = raw.rfind(b"\n", 0, close) + 1
    if b"\n" in raw[start:close] and not raw[close_line:close].strip(b" \t"):
        newline = b"\r\n" if raw[close_line - 2:close_line] == b"\r\n" else b"\n"
        line = raw[raw.rfind(b"\n", 0, last) + 1:last]
        indent = line[:len(line) - len(line.lstrip(b" \t"))]
        lines = b"".join(indent + b'"' + item.encode("ascii") + b'",' + newline for item in additions)
        return raw[:last] + (b"" if last_comma else b",") + raw[last:close_line] + lines + raw[close_line:]
    text = b""
    for position, item in enumerate(additions):
        text += (b"," if position or not last_comma else b"") + b' "' + item.encode("ascii") + b'"'
    return raw[:last] + text + (b"," if last_comma else b"") + raw[last:]


class WafTerraform(Terraform):
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
    if not isinstance(values, dict) or set(values) != BASE_INPUT_KEYS | {"allowed"}:
        raise CheckError("Terraform did not resolve every required allow-list input.")
    validate_inputs({name: values[name] for name in BASE_INPUT_KEYS}, app, digest, environ)
    allowed = values["allowed"]
    if not isinstance(allowed, list) or any(not isinstance(item, str) for item in allowed):
        raise CheckError("The canonical allow-list input must resolve to a list of strings.")
    return allowed


def run(environ=os.environ):
    operation = environ.get("TF_LAB_WAF_OPERATION")
    if operation not in ("inspect", "pin-live-allowlist"):
        raise CheckError("Only inspection or pinning the verified live allow-list is allowed.")
    expected = None
    if operation == "pin-live-allowlist":
        reviewed = environ.get("TF_LAB_WAF_EXPECTED_MISSING", "")
        if not re.fullmatch(r"[1-9]|10", reviewed):
            raise CheckError("Pinning requires the reviewed count of missing entries, from 1 to 10.")
        expected = int(reviewed)
    runtime = configuration(environ)
    blobs = LabBlobs(runtime)
    inputs = InputBlob(blobs)
    state_before = blobs.snapshot(LAB_STATE)
    input_before = inputs.snapshot()
    app = lab_state(state_before[0], runtime["AZURE_SUBSCRIPTION_ID"])
    waf_id = expected_waf_id(app)
    revision, digest = current_image(runtime, app)
    live_before = live_allowlist(runtime, waf_id)
    old_umask = os.umask(0o077)
    write_attempted = False
    try:
        with private_scratch(runtime) as scratch:
            root = stage_sources(scratch, runtime)
            configure_platform_oidc(root)
            write_supplemental_files(root, digest)
            terraform = WafTerraform(root, scratch, runtime, input_before[0])
            before = terraform.inputs_resolved()
            configured = validate_values(before, app, digest, runtime)
            missing = missing_entries(configured, live_before)
            candidate = None
            if missing:
                if expected is not None and len(missing) != expected:
                    raise CheckError("The count of live entries missing from the inputs differs from the reviewed count.")
                candidate = append_allowlist(input_before[0], missing)
                terraform.inputs.write_bytes(candidate)
                after = terraform.inputs_resolved()
                validate_values(after, app, digest, runtime)
                if after != {**before, "allowed": configured + missing}:
                    raise CheckError("The proposed input would change more than the missing live allow-list entries.")
            if (not snapshot_unchanged(LAB_STATE, state_before, blobs.snapshot(LAB_STATE))
                    or inputs.snapshot() != input_before
                    or current_image(runtime, app) != (revision, digest)
                    or live_allowlist(runtime, waf_id) != live_before):
                raise CheckError("The Lab state, inputs, WAF or active revision changed.")
            if operation == "pin-live-allowlist" and candidate is not None:
                with inputs.lease(input_before[1]) as lease_id:
                    if inputs.snapshot(lease_id) != input_before:
                        raise CheckError("The canonical inputs changed before the guarded update.")
                    if live_allowlist(runtime, waf_id) != live_before:
                        raise CheckError("The live WAF allow-list changed before the guarded update.")
                    write_attempted = True
                    inputs.replace(candidate, input_before, lease_id)
                    updated = inputs.snapshot(lease_id)
                    if (updated[0] != candidate or updated[1] == input_before[1]
                            or updated[2] != input_before[2]):
                        raise CheckError("The updated input blob did not match the verified candidate.")
                if (not snapshot_unchanged(LAB_STATE, state_before, blobs.snapshot(LAB_STATE))
                        or current_image(runtime, app) != (revision, digest)
                        or live_allowlist(runtime, waf_id) != live_before):
                    raise CheckError("Protected state, the WAF or the active revision changed after the input update.")
    except (CheckError, OSError):
        if write_attempted:
            print("The input update was attempted; verify the protected input before retrying.", file=sys.stderr)
        raise
    finally:
        os.umask(old_umask)
    pinned = operation == "pin-live-allowlist" and bool(missing)
    print(
        f"Existing Lab WAF verified; live entries: {len(live_before)}; configured entries: {len(configured)}; "
        f"missing from inputs: {len(missing)}.",
    )
    if pinned:
        print(f"Appended {len(missing)} live entries; all prior input bytes were preserved.")
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
        print(f"Lab WAF allow-list reconciliation failed: {message}", file=sys.stderr)
        sys.exit(1)

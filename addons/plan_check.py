"""Checks a saved Terraform plan against an add-on manifest, offline.

Run it on the JSON of a plan someone already saved, before a person reviews that plan:

    terraform show -json add-on.tfplan | python addons/plan_check.py knowledge-search -

The check reads only what it is given. It never runs Terraform, never contacts Azure, and approves nothing: a
person approves the saved plan, and an agent never applies one. It fails when a created or changed resource
opens public network access, turns on keys or local authentication, makes a public IP address, grants a role
the manifest doesn't list, or isn't a type the manifest allows. Anything the plan can't show also fails:
a guarded value that is unknown until apply, an azapi `sensitive_body`, an action, a deferred change, or a plan
that isn't complete.

Exit status: 0 when the plan passes, 1 when it has findings, 2 when the plan or the manifest can't be read.
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import NamedTuple

from addon_manifest import ADDONS_DIRECTORY, AddOnFileError, load_add_ons

_IGNORED_ACTIONS = ({"no-op"}, {"read"})
_AZAPI_ARM_TYPED = ("azapi_resource", "azapi_update_resource")
_ROLE_ASSIGNMENT_TYPES = ("azurerm_role_assignment", "microsoft.authorization/roleassignments")
_PUBLIC_IP_TYPES = re.compile(r"azurerm_public_ip(?:_prefix)?|Microsoft\.Network/publicIP(?:Addresses|Prefixes)", re.I)
_EMPTY = (None, "", [], {})
_CONTAINERS = {"body", "properties", "networkrules", "networkruleset", "networkacls", "authoptions",
               "ipconfiguration", "ipconfigurations", "siteconfig"}
_GUID_AT_END = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

PUBLIC_ACCESS = "public-network-access"
LOCAL_AUTH = "keys-or-local-auth"
PUBLIC_IP = "public-ip"
ROLE_ASSIGNMENT = "role-assignment"
RESOURCE_TYPE = "resource-type"
UNKNOWN_VALUE = "unknown-value"


class Finding(NamedTuple):
    address: str
    rule: str
    message: str

    def __str__(self):
        return f"{self.address}: [{self.rule}] {self.message}"


def _is(expected):
    return lambda value: value is expected


def _lower_in(*choices):
    return lambda value: isinstance(value, str) and value.lower() in choices


def _is_present(value):
    return value not in _EMPTY


def _public_access_flag(value):
    return value is True or _lower_in("enabled")(value)


# Settings, by key with punctuation and case removed so `public_network_access_enabled`, `publicNetworkAccess`
# and an azapi body's keys all match. Each entry is the rule, what the setting is called, and the value that
# fails the check.
_GUARDED = {
    "publicnetworkaccessenabled": (PUBLIC_ACCESS, "public network access", _is(True)),
    "publicnetworkaccess": (PUBLIC_ACCESS, "public network access", _public_access_flag),
    "defaultaction": (PUBLIC_ACCESS, "a firewall that allows traffic by default", _lower_in("allow")),
    "allownesteditemstobepublic": (PUBLIC_ACCESS, "public blob access", _is(True)),
    "allowblobpublicaccess": (PUBLIC_ACCESS, "public blob access", _is(True)),
    "containeraccesstype": (PUBLIC_ACCESS, "anonymous container access", _lower_in("blob", "container")),
    "iprules": (PUBLIC_ACCESS, "an IP allow list", _is_present),
    "iprule": (PUBLIC_ACCESS, "an IP allow list", _is_present),
    "iprangefilter": (PUBLIC_ACCESS, "an IP allow list", _is_present),
    "allowedips": (PUBLIC_ACCESS, "an IP allow list", _is_present),
    "allowedipranges": (PUBLIC_ACCESS, "an IP allow list", _is_present),
    "iprestriction": (PUBLIC_ACCESS, "an IP allow list", _is_present),
    "ipsecurityrestrictions": (PUBLIC_ACCESS, "an IP allow list", _is_present),
    "publicaccess": (PUBLIC_ACCESS, "anonymous container access", _lower_in("blob", "container")),
    "publicipaddressid": (PUBLIC_IP, "a public IP address", _is_present),
    "publicipaddress": (PUBLIC_IP, "a public IP address", _is_present),
    "publicipprefixid": (PUBLIC_IP, "a public IP prefix", _is_present),
    "localauthenticationenabled": (LOCAL_AUTH, "local authentication", _is(True)),
    "localauthenabled": (LOCAL_AUTH, "local authentication", _is(True)),
    "localauthenticationdisabled": (LOCAL_AUTH, "local authentication", _is(False)),
    "disablelocalauth": (LOCAL_AUTH, "local authentication", _is(False)),
    "sharedaccesskeyenabled": (LOCAL_AUTH, "shared-key access", _is(True)),
    "allowsharedkeyaccess": (LOCAL_AUTH, "shared-key access", _is(True)),
    "adminenabled": (LOCAL_AUTH, "an admin user", _is(True)),
    "adminuserenabled": (LOCAL_AUTH, "an admin user", _is(True)),
    "apikeyonly": (LOCAL_AUTH, "key authentication", lambda value: True),
    "aadorapikey": (LOCAL_AUTH, "key authentication", lambda value: True),
}


def _normal(key):
    return re.sub(r"[^a-z0-9]", "", str(key).lower())


def _walk(value, path=()):
    """Every key in nested objects and lists, with where it sits."""
    if isinstance(value, dict):
        for key, item in value.items():
            yield path + (key,), key, item
            yield from _walk(item, path + (key,))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk(item, path + (index,))


def _where(path):
    return ".".join(str(part) for part in path)


def _has_unknown(value):
    if isinstance(value, dict):
        return any(_has_unknown(item) for item in value.values())
    if isinstance(value, list):
        return any(_has_unknown(item) for item in value)
    return value is True


def _scope_shape(scope):
    """The resource type and child collections a scope ID points at, or None for a subscription or group."""
    parts = [part for part in scope.split("/") if part]
    lowered = [part.lower() for part in parts]
    if "providers" not in lowered:
        return None
    tail = parts[len(parts) - lowered[::-1].index("providers"):]
    if len(tail) < 3 or len(tail) % 2 == 0:
        return None
    return f"{tail[0]}/{tail[1]}".lower(), tuple(child.lower() for child in tail[3::2])


def _guarded_findings(address, after, after_unknown):
    findings = []
    for path, key, value in _walk(after):
        guarded = _GUARDED.get(_normal(key))
        if guarded and guarded[2](value):
            rule, what, _ = guarded
            findings.append(Finding(address, rule, f"{_where(path)} sets {what}, which packages can't have."))
    for path, key, value in _walk(after_unknown):
        # A block that is unknown as a whole hides the guarded settings inside it.
        if (_normal(key) in _GUARDED and _has_unknown(value)) or (_normal(key) in _CONTAINERS and value is True):
            findings.append(Finding(address, UNKNOWN_VALUE,
                                    f"{_where(path)} isn't known until apply, so the plan can't show it stays closed."))
    for key in ("sensitive_body", "sensitive_body_version"):
        if _is_present(after.get(key)) or _has_unknown(after_unknown.get(key)):
            findings.append(Finding(address, UNKNOWN_VALUE,
                                    f"{key} is write-only, so the plan can't show what it sends. Put the values in body."))
    return findings


def _dig(value, *path):
    for key in path:
        value = value.get(key) if isinstance(value, dict) else None
    return value


def _role_assignment_fields(change_type, after):
    """What a role assignment grants, from either the azurerm resource or an azapi role assignment. A value
    that is unknown until apply is missing from `after`, so it reads as None here."""
    if change_type == "azurerm_role_assignment":
        return {
            "scope": after.get("scope"),
            "role_id": after.get("role_definition_id"),
            "role_name": after.get("role_definition_name"),
            "principal_type": after.get("principal_type"),
        }
    return {
        "scope": after.get("parent_id"),
        "role_id": _dig(after, "body", "properties", "roleDefinitionId"),
        "role_name": None,
        "principal_type": _dig(after, "body", "properties", "principalType"),
    }


def _role_assignment(address, change_type, after, package):
    grant = _role_assignment_fields(change_type, after)
    scope, role_id, role_name = grant["scope"], grant["role_id"], grant["role_name"]
    problems = []
    if not isinstance(scope, str):
        problems.append("its scope isn't set or isn't known until apply")
    if not isinstance(role_id, str) and not isinstance(role_name, str):
        problems.append("its role isn't set or isn't known until apply")
    if problems:
        return [Finding(address, UNKNOWN_VALUE, f"A role assignment can't be checked: {' and '.join(problems)}.")]

    allowed = package["roles"]
    if isinstance(role_id, str):
        match = _GUID_AT_END.search(role_id.lower())
        candidates = [role for role in allowed if match and role["role_id"] == match.group(0)]
    else:
        candidates = [role for role in allowed if role["role"].lower() == role_name.lower()]
    if not candidates:
        listed = ", ".join(f"{role['role']} ({role['role_id']})" for role in allowed) or "none"
        return [Finding(address, ROLE_ASSIGNMENT,
                        f"Grants {(role_id or role_name).rsplit('/', 1)[-1]}, which the manifest doesn't list. Listed: {listed}.")]

    shape = _scope_shape(scope)
    fits = [role for role in candidates if shape == _role_scope_shape(role)]
    if not fits:
        role = candidates[0]
        child = f"/{role['scope']['child']}" if "child" in role["scope"] else ""
        return [Finding(address, ROLE_ASSIGNMENT,
                        f"Grants {role['role']} at {scope}, but the manifest allows it only on "
                        f"{role['scope']['type']}{child}.")]
    if grant["principal_type"] != fits[0]["principal_type"]:
        return [Finding(address, ROLE_ASSIGNMENT,
                        f"principal_type must be {fits[0]['principal_type']}, not {grant['principal_type']!r}.")]
    return []


def _role_scope_shape(role):
    child = (role["scope"]["child"].lower(),) if "child" in role["scope"] else ()
    return role["scope"]["type"].lower(), child


def _effective_type(change, details):
    """The type the manifest's resource_types list names: an Azure type for azapi, else the Terraform type."""
    if change["type"] in _AZAPI_ARM_TYPED and isinstance(details.get("type"), str):
        return details["type"].split("@")[0]
    return change["type"]


def _plan_level_findings(plan):
    """What a plan holds outside resource_changes that this check can't read, so it can't vouch for it."""
    findings = []
    if plan.get("errored") is True or plan.get("complete") is False:
        findings.append(Finding("plan", UNKNOWN_VALUE, "The plan is errored or incomplete, so some changes aren't in it."))
    for section in ("action_invocations", "deferred_changes", "deferred_action_invocations"):
        for item in plan.get(section) or []:
            address = item.get("address", section) if isinstance(item, dict) else section
            findings.append(Finding(address, UNKNOWN_VALUE,
                                    f"{section} aren't checked here, so a plan that has them can't pass. Remove them from the module."))
    return findings


def check_plan(plan, package):
    """The findings for a saved plan's JSON, given an add-on's `package` from its manifest."""
    if not isinstance(plan, dict) or not isinstance(plan.get("format_version"), str) or "planned_values" not in plan:
        raise ValueError("this isn't the JSON of a saved plan (state JSON lacks planned_values); "
                         "use `terraform show -json <saved plan>`")
    if not plan["format_version"].startswith("1."):
        raise ValueError(f"plan format {plan['format_version']} isn't supported; this check reads format 1.x")
    changes = plan.get("resource_changes", [])
    if not isinstance(changes, list):
        raise ValueError("resource_changes must be a list")
    for change in changes:
        if not (isinstance(change, dict) and isinstance(change.get("address"), str) and isinstance(change.get("type"), str)
                and isinstance(change.get("change"), dict) and isinstance(change["change"].get("actions"), list)):
            raise ValueError("a resource change lacks its address, type, or actions; use `terraform show -json <saved plan>`")

    allowed_types = {resource_type.lower() for resource_type in package["terraform"]["resource_types"]}
    findings = _plan_level_findings(plan)
    for change in changes:
        if change.get("mode") == "data" or {*change["change"]["actions"]} in _IGNORED_ACTIONS:
            continue
        address = change["address"]
        actions = set(change["change"]["actions"])
        after = change["change"].get("after") or {}
        after_unknown = change["change"].get("after_unknown") or {}
        details = after or change["change"].get("before") or {}
        kind = _effective_type(change, details)

        if change["type"] in _AZAPI_ARM_TYPED and (after_unknown.get("type") is True or after_unknown.get("body") is True):
            findings.append(Finding(address, UNKNOWN_VALUE, "type or body isn't known until apply, so the plan can't be checked."))
        if kind.lower() not in allowed_types:
            findings.append(Finding(address, RESOURCE_TYPE, f"{kind} isn't in the manifest's resource_types."))
        if _PUBLIC_IP_TYPES.fullmatch(kind):
            findings.append(Finding(address, PUBLIC_IP, "Creates a public IP address, which packages can't have."))
        if "create" in actions or "update" in actions:
            findings += _guarded_findings(address, after, after_unknown)
            if kind.lower() in _ROLE_ASSIGNMENT_TYPES:
                findings += _role_assignment(address, change["type"], after, package)
    return findings


def _read_plan(source):
    text = sys.stdin.read() if source == "-" else Path(source).read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError as problem:
        raise ValueError(f"the input isn't JSON ({problem}); use `terraform show -json <saved plan>`") from problem


def main(argv=None, addons_directory=ADDONS_DIRECTORY):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("add_on", help="the add-on's id, the folder name under addons/")
    parser.add_argument("plan", help="a file with `terraform show -json <saved plan>` output, or - for standard input")
    arguments = parser.parse_args(argv)

    try:
        add_ons = {add_on.id: add_on for add_on in load_add_ons(addons_directory)}
        add_on = add_ons.get(arguments.add_on)
        if add_on is None:
            raise ValueError(f"no add-on {arguments.add_on!r}; the add-ons are {', '.join(add_ons)}")
        if add_on.package is None:
            raise ValueError(f"{add_on.id} has no deployment package in its manifest, so there is nothing to check a plan against")
        findings = check_plan(_read_plan(arguments.plan), add_on.package)
    except (AddOnFileError, OSError, ValueError) as problem:
        print(f"Can't check the plan: {problem}", file=sys.stderr)
        return 2
    except (AttributeError, KeyError, TypeError) as problem:
        print(f"Can't check the plan: it isn't shaped like `terraform show -json` output ({problem!r}).", file=sys.stderr)
        return 2

    if findings:
        for finding in findings:
            print(f"FAIL {finding}")
        print(f"\nPlan check failed for {add_on.id}: {len(findings)} finding(s). Fix the module or the inputs and save a new plan. "
              "This check approves nothing.")
        return 1
    print(f"Plan check passed for {add_on.id}: the changes stay inside its manifest. "
          "This check approves nothing; a person reads the saved plan, approves it, and runs the apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

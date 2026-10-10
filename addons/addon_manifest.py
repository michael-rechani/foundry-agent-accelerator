"""Reads add-on manifests from addons/<id>/addon.json and checks each file's shape.

A manifest describes one add-on: the card the Lab's Add-ons tab shows and, once someone has built it, the
deployment package that goes with it (a runbook, an acceptance case, a Terraform module and the roles it may
grant). `load_add_ons` returns them in tab order, so adding an add-on means adding one directory, with no list
to edit. The format is described in docs/addon-package-format.md.

Nothing here contacts Azure or runs Terraform. A manifest declares what a package may do; `plan_check.py`
compares a saved plan with it, and a person approves that plan.
"""

import json
import re
from pathlib import Path
from typing import NamedTuple

ADDONS_DIRECTORY = Path(__file__).resolve().parent
SCHEMA_VERSION = 1

KINDS = ("built-in-tool", "existing-service", "new-service")
ICONS = ("search", "memory", "documents", "notifications", "calculator", "web", "cache", "storage")
# What the add-on is for: "abilities" lets an agent do something more, "support" is what an agent runs on.
GROUPS = ("abilities", "support")
APPROVAL_GATES = ("billable-calls", "shared-data", "data-handling")
RUNBOOK_HEADINGS = ("Plan", "Cost and diff", "Approval", "Apply", "Verify", "Wire the agent", "Tear down")
# The only value a package may declare for each guardrail. Loosening one is a code change, not a manifest edit.
GUARDRAILS = {"public_network_access": "disabled", "local_auth": "disabled", "public_ip": "none"}
PLAN_APPROVAL = "person-approves-saved-plan"

_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_GUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_ARM_TYPE = re.compile(r"Microsoft\.[A-Za-z0-9]+(?:/[A-Za-z0-9]+)+")
_TERRAFORM_TYPE = re.compile(r"(?:azurerm|azapi)_[a-z0-9_]+")
_FILE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")
_TOP_FIELDS = {"schema_version", "id", "name", "order", "kind", "tracking", "card", "package"}
# The order the Add-ons tab's data lists a card's fields in.
_CARD_ORDER = ("icon", "group", "summary", "example", "pilot", "cost", "needs", "safety", "approval", "service",
               "billing", "note")
_CARD_REQUIRED = {"icon", "group", "summary", "example", "cost", "needs", "safety", "service", "billing"}
_PACKAGE_FIELDS = {"runbook", "bootstrap", "acceptance_case", "terraform", "approval", "approval_gates",
                   "roles", "cost_lines", "guardrails"}
_ACCEPTANCE_FIELDS = {"schema_version", "add_on", "cases"}
_CASE_FIELDS = {"id", "summary", "live", "steps", "expect"}


class AddOnFileError(RuntimeError):
    pass


class AddOn(NamedTuple):
    id: str
    name: str
    order: int
    kind: str
    tracking: tuple
    card: dict
    package: dict | None

    def catalog_entry(self):
        """The add-on as the Lab's Add-ons tab reads it."""
        return {"id": self.id, "name": self.name, **{field: self.card[field] for field in _CARD_ORDER if field in self.card}}


def _reject_repeated_keys(pairs):
    if len({key for key, _ in pairs}) != len(pairs):
        raise ValueError("a key appears twice")
    return dict(pairs)


def _text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty text")
    return value


def _texts(value, field):
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field} must be a non-empty list")
    return [_text(item, f"{field} entries") for item in value]


def _object(value, field, allowed, required=None):
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be an object")
    allowed = set(allowed)
    if missing := sorted((allowed if required is None else required) - value.keys()):
        raise ValueError(f"{field} is missing {', '.join(missing)}")
    if extra := sorted(value.keys() - allowed):
        raise ValueError(f"{field} has unknown field {', '.join(extra)}")
    return value


def _position(value, field):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{field} must be a whole number of 1 or more")
    return value


def _amount(value, field):
    if isinstance(value, bool) or not isinstance(value, int | float) or value < 0:
        raise ValueError(f"{field} must be a number of 0 or more")
    return value


def _choice(value, field, choices):
    if value not in choices:
        raise ValueError(f"unknown {field} {value!r}")
    return value


def _identifier(value, field):
    if not isinstance(value, str) or not _ID.fullmatch(value) or len(value) > 64:
        raise ValueError(f"{field} must be lowercase words joined by hyphens")
    return value


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_reject_repeated_keys)


def _in_directory(directory, name, field):
    """A file named in the manifest. It sits directly in the add-on's directory, so a manifest can't point
    a check at a file that another add-on, or nothing in this repository, owns."""
    if not isinstance(name, str) or not _FILE_NAME.fullmatch(name):
        raise ValueError(f"{field} must be a file name without a folder")
    path = directory / name
    if not path.is_file():
        raise ValueError(f"{field} names {name}, which is not in {directory.name}/")
    return path


def _checked(path, check, *arguments):
    """Runs a check on a file the manifest points at, so a problem in it names that file."""
    try:
        check(path, *arguments)
    except (OSError, ValueError) as problem:
        raise AddOnFileError(f"{path.parent.name}/{path.name}: {problem}") from problem


def _card(value):
    card = _object(value, "card", _CARD_ORDER, _CARD_REQUIRED)
    _choice(card["icon"], "icon", ICONS)
    _choice(card["group"], "group", GROUPS)
    for field in ("summary", "example", "safety", "service", "billing", "pilot", "approval", "note"):
        if field in card:
            _text(card[field], f"card {field}")
    for field in ("cost", "needs"):
        _texts(card[field], f"card {field}")
    return card


def _tracking(value):
    if not isinstance(value, list) or not value:
        raise ValueError("tracking must list the issues that follow this add-on")
    numbers = [_position(number, "tracking entries") for number in value]
    if len(set(numbers)) != len(numbers):
        raise ValueError("tracking lists an issue twice")
    return tuple(numbers)


def _role(value):
    role = _object(value, "a role", {"role", "role_id", "principal_type", "scope"})
    _text(role["role"], "a role name")
    if not isinstance(role["role_id"], str) or not _GUID.fullmatch(role["role_id"]):
        raise ValueError("role_id must be a lowercase role definition GUID")
    _choice(role["principal_type"], "principal_type", ("ServicePrincipal",))
    scope = _object(role["scope"], "a role scope", {"type", "child"}, {"type"})
    if not isinstance(scope["type"], str) or not _ARM_TYPE.fullmatch(scope["type"]):
        raise ValueError("a role scope type must be an Azure resource type such as Microsoft.Search/searchServices")
    if "child" in scope:
        _identifier(scope["child"], "a role scope child")
    return role


def _cost_line(value):
    if isinstance(value, dict) and "monthly_cost" in value:
        line = _object(value, "a cost line", {"name", "monthly_cost", "basis"})
        _amount(line["monthly_cost"], "monthly_cost")
    else:
        line = _object(value, "a cost line", {"name", "quantity", "unit_rate", "unit", "basis"})
        _amount(line["quantity"], "quantity")
        _amount(line["unit_rate"], "unit_rate")
        _text(line["unit"], "a cost line unit")
    _text(line["name"], "a cost line name")
    _text(line["basis"], "a cost line basis")


def _terraform(value, directory):
    terraform = _object(value, "terraform", {"module", "resource_types"})
    module = _text(terraform["module"], "terraform module")
    if not _FILE_NAME.fullmatch(module) or not (directory / module).is_dir():
        raise ValueError(f"terraform module must name a folder inside {directory.name}/")
    if not any((directory / module).glob("*.tf")):
        raise ValueError(f"terraform module {module} has no .tf files")
    types = _texts(terraform["resource_types"], "terraform resource_types")
    for item in types:
        if not (_TERRAFORM_TYPE.fullmatch(item) or _ARM_TYPE.fullmatch(item)):
            raise ValueError(f"resource_types entry {item!r} must be a Terraform type such as azurerm_role_assignment "
                             "or, for an azapi resource, an Azure type such as Microsoft.Search/searchServices")
    if len(set(types)) != len(types):
        raise ValueError("resource_types lists a type twice")


def _runbook(path):
    text = path.read_text(encoding="utf-8")
    headings = {line[3:].strip().lower() for line in text.splitlines() if line.startswith("## ")}
    if missing := [heading for heading in RUNBOOK_HEADINGS if heading.lower() not in headings]:
        raise ValueError("the runbook is missing the section " + ", ".join(f'"{heading}"' for heading in missing))
    if "approves the saved plan" not in " ".join(text.split()):
        raise ValueError("the runbook must say that a person approves the saved plan")


def _bootstrap(path):
    if not path.read_text(encoding="utf-8").strip():
        raise ValueError("the file is empty")


def _acceptance(path, identifier):
    case_file = _object(_read_json(path), "the file", _ACCEPTANCE_FIELDS)
    if case_file["schema_version"] != SCHEMA_VERSION:
        raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
    if case_file["add_on"] != identifier:
        raise ValueError(f"add_on must be {identifier}")
    cases = case_file["cases"]
    if not isinstance(cases, list) or not cases:
        raise ValueError("cases must be a non-empty list")
    ids = []
    for case in cases:
        _object(case, "a case", _CASE_FIELDS)
        ids.append(_identifier(case["id"], "a case id"))
        _text(case["summary"], "a case summary")
        if not isinstance(case["live"], bool):
            raise ValueError("a case's live must be true or false")
        _texts(case["steps"], "a case's steps")
        _texts(case["expect"], "a case's expect")
    if len(set(ids)) != len(ids):
        raise ValueError("two cases share an id")
    if all(case["live"] for case in cases):
        raise ValueError("at least one case must run without a deployed add-on")


def _package(value, directory, identifier):
    package = _object(value, "package", _PACKAGE_FIELDS)
    _checked(_in_directory(directory, package["runbook"], "runbook"), _runbook)
    _checked(_in_directory(directory, package["bootstrap"], "bootstrap"), _bootstrap)
    _checked(_in_directory(directory, package["acceptance_case"], "acceptance_case"), _acceptance, identifier)
    _terraform(package["terraform"], directory)
    if package["approval"] != PLAN_APPROVAL:
        raise ValueError(f"approval must be {PLAN_APPROVAL!r}: an agent never applies a plan")
    gates = package["approval_gates"]
    if not isinstance(gates, list) or any(gate not in APPROVAL_GATES for gate in gates) or len(set(gates)) != len(gates):
        raise ValueError(f"approval_gates must list each of {', '.join(APPROVAL_GATES)} at most once")
    if not isinstance(package["roles"], list):
        raise ValueError("roles must be a list, empty when the package grants nothing")
    roles = [_role(role) for role in package["roles"]]
    if len({(role["role_id"], role["scope"]["type"], role["scope"].get("child")) for role in roles}) != len(roles):
        raise ValueError("two roles are the same")
    if not isinstance(package["cost_lines"], list) or not package["cost_lines"]:
        raise ValueError("cost_lines must be a non-empty list")
    for line in package["cost_lines"]:
        _cost_line(line)
    if package["guardrails"] != GUARDRAILS:
        raise ValueError("guardrails must be exactly " + json.dumps(GUARDRAILS))
    return package


def _read(path):
    directory = path.parent
    try:
        document = _object(_read_json(path), "the file", _TOP_FIELDS, _TOP_FIELDS - {"package"})
        if document["schema_version"] != SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
        identifier = _identifier(document["id"], "id")
        if identifier != directory.name:
            raise ValueError("id must match the folder name")
        name = _text(document["name"], "name")
        order = _position(document["order"], "order")
        kind = _choice(document["kind"], "kind", KINDS)
        tracking = _tracking(document["tracking"])
        card = _card(document["card"])
        package = _package(document["package"], directory, identifier) if "package" in document else None
    except (OSError, ValueError) as problem:
        raise AddOnFileError(f"{directory.name}/{path.name}: {problem}") from problem
    return AddOn(identifier, name, order, kind, tracking, card, package)


def load_add_ons(directory=ADDONS_DIRECTORY):
    """Read every <id>/addon.json under `directory`, in the order the Add-ons tab lists them."""
    directory = Path(directory)
    paths = sorted(directory.glob("*/addon.json"))
    if not paths:
        raise AddOnFileError(f"No add-on manifests in {directory}")
    add_ons = [_read(path) for path in paths]
    seen = {}
    for add_on in add_ons:
        if seen.setdefault(add_on.order, add_on.id) != add_on.id:
            raise AddOnFileError(f"{add_on.id}/addon.json: order {add_on.order} is already used by {seen[add_on.order]}")
    return sorted(add_ons, key=lambda add_on: add_on.order)

"""Reads the library's agents from agents/*.json, one file per agent, and checks each file's shape.

A file holds the agent's template, its catalog metadata, the trigger words that match a task to it
and its place in the library. `load_agents` returns the tables `catalog` serves, so adding an agent
means adding one file, with no list to edit.
"""

import json
import math
import re
from pathlib import Path
from typing import NamedTuple

AGENTS_DIRECTORY = Path(__file__).resolve().parent / "agents"

_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_TOP_FIELDS = {"id", "order", "retired", "definition_order", "template", "metadata", "match"}
_TEMPLATE_FIELDS = ("model_profile", "label", "description", "input", "output", "limits", "delegation",
                    "instructions", "example_request", "sample_input", "tools")
_METADATA_FIELDS = ("sector", "industry", "tasks", "summary", "expected_behavior", "human_decision", "keywords",
                    "readiness")
_TOOL_NOTE = "; no external call or update."


class AgentFileError(RuntimeError):
    pass


class Library(NamedTuple):
    templates: dict
    metadata: dict
    matchers: dict
    library_order: tuple
    retired: frozenset


class _Agent(NamedTuple):
    id: str
    order: int | None
    definition_order: int | None
    template: dict
    metadata: dict
    matcher: tuple


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


def _choice(value, field, choices):
    if value not in choices:
        raise ValueError(f"unknown {field} {value!r}")
    return value


def _tools(value):
    if not isinstance(value, list):
        raise ValueError("template tools must be a list")
    tools = []
    for tool in value:
        tool = _object(tool, "a tool", {"name", "description"})
        tools.append({"name": _text(tool["name"], "tool name"),
                      "description": _text(tool["description"], "tool description") + _TOOL_NOTE,
                      "simulated": True})
    if len({tool["name"] for tool in tools}) != len(tools):
        raise ValueError("two tools share a name")
    return tools


def _read(path, vocabulary):
    try:
        document = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_reject_repeated_keys)
        _object(document, "the file", _TOP_FIELDS, {"id", "template", "metadata", "match"})
        identifier = _text(document["id"], "id")
        if not _ID.fullmatch(identifier) or len(identifier) > 64 or identifier != path.stem:
            raise ValueError("id must be lowercase words joined by hyphens, and match the file name")
        retired = document.get("retired", False)
        if not isinstance(retired, bool):
            raise ValueError("retired must be true or left out")
        if retired == ("order" in document):
            raise ValueError("a listed agent needs an order, and a retired one has none")
        order = None if retired else _position(document["order"], "order")
        definition_order = (_position(document["definition_order"], "definition_order")
                            if "definition_order" in document else None)

        source = _object(document["template"], "template", _TEMPLATE_FIELDS)
        # Key order is part of the served catalog's shape; `id` and `category` come from the file name and sector.
        template = {field: _text(source[field], f"template {field}") for field in _TEMPLATE_FIELDS[:-1]}
        _choice(template["model_profile"], "model_profile", vocabulary["model_profiles"])
        template["tools"] = _tools(source["tools"])

        source = _object(document["metadata"], "metadata", _METADATA_FIELDS)
        metadata = {
            "sector": _choice(_text(source["sector"], "metadata sector"), "sector", vocabulary["sectors"]),
            "industry": _choice(_text(source["industry"], "metadata industry"), "industry", vocabulary["industries"]),
            "tasks": [_choice(task, "task", vocabulary["tasks"]) for task in _texts(source["tasks"], "metadata tasks")],
            "summary": _text(source["summary"], "metadata summary"),
            "expected_behavior": _text(source["expected_behavior"], "metadata expected_behavior"),
            "human_decision": _text(source["human_decision"], "metadata human_decision"),
            "keywords": _texts(source["keywords"], "metadata keywords"),
            "readiness": _choice(_text(source["readiness"], "metadata readiness"), "readiness", vocabulary["readiness"]),
        }
        if len(set(metadata["tasks"])) != len(metadata["tasks"]):
            raise ValueError("a task is listed twice")

        # Every pattern must match for the agent to be a candidate: one pattern is a trigger, more narrow it.
        matcher = tuple(re.compile(r"\b(" + pattern + r")\b") for pattern in _texts(document["match"], "match"))
    except (OSError, ValueError, re.error) as problem:
        raise AgentFileError(f"{path.name}: {problem}") from problem
    template = {"id": identifier, "category": vocabulary["sectors"][metadata["sector"]], **template}
    return _Agent(identifier, order, definition_order, template, metadata, matcher)


def _unique(agents, field):
    seen = {}
    for agent in agents:
        number = getattr(agent, field)
        if number is not None and seen.setdefault(number, agent.id) != agent.id:
            raise AgentFileError(f"{agent.id}.json: {field} {number} is already used by {seen[number]}")


def load_agents(directory, vocabulary):
    """Read every *.json file in `directory`. `vocabulary` holds the ids a file may use: `sectors` (id to label),
    `industries`, `tasks`, `readiness` and `model_profiles`."""
    paths = sorted(Path(directory).glob("*.json"))
    if not paths:
        raise AgentFileError(f"No agent files in {directory}")
    agents = [_read(path, vocabulary) for path in paths]
    _unique(agents, "order")
    _unique(agents, "definition_order")
    # `definition_order` keeps the order that the catalog's tables and the trigger-word candidates have always had.
    # An agent without one sorts after those that have one, in library order, with retired agents last.
    definition = sorted(agents, key=lambda agent: (agent.definition_order or math.inf, agent.order or math.inf, agent.id))
    listed = sorted((agent for agent in agents if agent.order is not None), key=lambda agent: agent.order)
    return Library(
        templates={agent.id: agent.template for agent in definition},
        metadata={agent.id: agent.metadata for agent in definition},
        matchers={agent.id: agent.matcher for agent in definition},
        library_order=tuple(agent.id for agent in listed),
        retired=frozenset(agent.id for agent in agents if agent.order is None),
    )

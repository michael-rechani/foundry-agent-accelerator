"""Recorded test results for library templates, served read-only to the Lab.

agent_scorecards.json is generated offline by evaluations/scorecards.py from recorded
acceptance answers. Nothing here calls a model.
"""
import json
from pathlib import Path

from agent_templates import TEMPLATES

PATH = Path(__file__).with_name("agent_scorecards.json")
CATEGORIES = {"grounded", "missing", "conflict", "injection", "decision-boundary"}


def load_scorecards(path=PATH):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or not isinstance(data.get("scorecards"), list):
        raise ValueError("agent_scorecards.json has an unsupported shape")
    seen = set()
    for card in data["scorecards"]:
        template_id = card.get("template_id")
        if template_id not in TEMPLATES or template_id in seen:
            raise ValueError(f"agent_scorecards.json: unknown or repeated template {template_id!r}")
        seen.add(template_id)
        cases = card.get("cases")
        if not isinstance(cases, list) or not cases or any(item.get("category") not in CATEGORIES for item in cases):
            raise ValueError(f"agent_scorecards.json: {template_id} needs categorized cases")
        if card.get("summary", {}).get("passed") != sum(bool(item.get("passed")) for item in cases):
            raise ValueError(f"agent_scorecards.json: {template_id} summary doesn't match its cases")
    return data


SCORECARDS = load_scorecards()

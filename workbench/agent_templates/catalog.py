from copy import deepcopy

from ._loader import AGENTS_DIRECTORY, load_agents

MODEL_PROFILES = {
    "reasoning": {
        "label": "Reasoning",
        "reason": "Compares sources step by step and keeps gaps and conflicts visible.",
    },
    "extraction": {
        "label": "Fast extraction",
        "reason": "Copies stated values into a fixed structure, where speed and cost matter more than deep reasoning.",
    },
    "tool_calling": {
        "label": "Tool calling",
        "reason": "Calls lookup tools in the right order and reports exactly what they return.",
    },
}

# These are also the Create page's group headings, so the Create page and the library filter agree.
# The Create page lists its groups in the order the jobs first appear in LIBRARY_ORDER; SECTORS keeps
# that same order (a test checks it).
SECTORS = (
    {"id": "cross-sector", "label": "Works in any sector"},
    {"id": "private", "label": "Private sector"},
    {"id": "public", "label": "Healthcare and public sector"},
)
INDUSTRIES = (
    {"id": "general-operations", "label": "General operations"},
    {"id": "health-administration", "label": "Health administration"},
    {"id": "government-services", "label": "Government services"},
    {"id": "procurement", "label": "Procurement"},
    {"id": "finance", "label": "Finance"},
    {"id": "customer-operations", "label": "Customer operations"},
    {"id": "field-operations", "label": "Field operations"},
    {"id": "legal-operations", "label": "Legal operations"},
    {"id": "sales", "label": "Sales"},
    {"id": "it-operations", "label": "IT operations"},
    {"id": "retail", "label": "Retail and e-commerce"},
)
TASKS = (
    {"id": "review", "label": "Review"},
    {"id": "extract", "label": "Extract"},
    {"id": "summarize", "label": "Summarize"},
    {"id": "plan", "label": "Plan"},
    {"id": "draft", "label": "Draft"},
    {"id": "triage", "label": "Triage"},
)
# An agent is "reviewed" only after a person signs off its recorded test answers.
# evaluations/test_scorecards.py checks the marking against the recorded sign-offs.
READINESS_LEVELS = (
    {"id": "reviewed", "label": "Reviewed", "description": "A person has signed off on its test answers, its setup passes the Lab's validation, and every run of its test cases met the Lab's checks."},
    {"id": "sample", "label": "Not yet reviewed", "description": "Its setup passes the Lab's validation, but a person hasn't signed off on its test answers yet. Try it with sample data, and check it against your own policies before real use."},
)
TOOL_MODES = (
    {"id": "none", "label": "Text only", "description": "Works only from the text you give it."},
    {"id": "simulated", "label": "Sample lookups", "description": "Looks up sample records that come with the Lab. It can't change anything."},
)

_PROFILE_HINTS = {
    "reasoning": {"relative_cost": "medium", "relative_latency": "medium"},
    "extraction": {"relative_cost": "lower", "relative_latency": "lower"},
    "tool_calling": {"relative_cost": "medium", "relative_latency": "higher"},
}

# Listed agents use the shared four-part layout (#82), except the checklist
# checker whose own instructions preserve a criterion matrix and structured schemas.
ANSWER_LAYOUT = (
    "Format every answer with these four headings, in this order: Result (the direct answer, table or "
    "draft), Why (the facts and source labels that support it), What to check (missing, unclear or "
    "conflicting details, and anything a person must verify) and Next step (one action or question for "
    "a person). Keep each part short. If the user asks for a specific format such as JSON, put it under "
    "Result. Ask for anything missing as a direct question ending in a question mark, under What to "
    "check or Next step. If you are asked to make a decision, say in Next step that the decision isn't "
    "yours and who makes it: "
)

# Each agent is one file in agents/. TEMPLATES, TEMPLATE_METADATA and _MATCHERS follow the library's order with
# retired agents last, so the `template_required` candidates come in the order the library lists them;
# LIBRARY_ORDER holds only the listed agents.
_LIBRARY = load_agents(AGENTS_DIRECTORY, {
    "sectors": {item["id"]: item["label"] for item in SECTORS},
    "industries": {item["id"] for item in INDUSTRIES},
    "tasks": {item["id"] for item in TASKS},
    "readiness": {item["id"] for item in READINESS_LEVELS},
    "model_profiles": set(MODEL_PROFILES),
})
TEMPLATES = _LIBRARY.templates
TEMPLATE_METADATA = _LIBRARY.metadata
_MATCHERS = _LIBRARY.matchers
LIBRARY_ORDER = _LIBRARY.library_order
# Retired jobs stay loadable so agents already created from them keep working, but the library no
# longer lists, previews, matches or creates them.
RETIRED_TEMPLATES = _LIBRARY.retired

for _template_id, _metadata_entry in TEMPLATE_METADATA.items():
    if _template_id not in RETIRED_TEMPLATES and _template_id != "criteria-checker":
        _template = TEMPLATES[_template_id]
        _template["instructions"] = (
            _template["instructions"].rstrip() + " " + ANSWER_LAYOUT + _metadata_entry["human_decision"])


def is_listed(template_id):
    return template_id in TEMPLATES and template_id not in RETIRED_TEMPLATES

def _matches(matcher, text):
    return all(pattern.search(text) for pattern in matcher)


class TemplateRequiredError(ValueError):
    def __init__(self, candidates):
        self.candidates = candidates
        super().__init__("Choose the closest prepared template")


def model_profile(profile_id):
    return {"id": profile_id, **MODEL_PROFILES[profile_id]}


def _listed():
    return [TEMPLATES[key] for key in LIBRARY_ORDER]


def _facet(values, field):
    counts = {item["id"]: 0 for item in values}
    for metadata in (TEMPLATE_METADATA[key] for key in LIBRARY_ORDER):
        selected = metadata[field]
        for identifier in selected if isinstance(selected, list) else [selected]:
            counts[identifier] += 1
    return [{**item, "count": counts[item["id"]]} for item in values if counts[item["id"]]]


def catalog_facets():
    return {
        "sectors": _facet(SECTORS, "sector"),
        "industries": _facet(INDUSTRIES, "industry"),
        "tasks": _facet(TASKS, "tasks"),
        "readiness": _facet(READINESS_LEVELS, "readiness"),
        "tool_modes": [
            {**item, "count": sum(
                (bool(template["tools"]) if item["id"] == "simulated" else not template["tools"])
                for template in _listed()
            )}
            for item in TOOL_MODES
            if any((bool(template["tools"]) if item["id"] == "simulated" else not template["tools"])
                   for template in _listed())
        ],
    }


def list_templates():
    sectors = {item["id"]: item for item in SECTORS}
    industries = {item["id"]: item for item in INDUSTRIES}
    tasks = {item["id"]: item for item in TASKS}
    readiness = {item["id"]: item for item in READINESS_LEVELS}
    tool_modes = {item["id"]: item for item in TOOL_MODES}
    result = []
    for identifier in LIBRARY_ORDER:
        template, metadata = TEMPLATES[identifier], TEMPLATE_METADATA[identifier]
        profile = template["model_profile"]
        mode = "simulated" if template["tools"] else "none"
        result.append({
            **deepcopy(template),
            "model_profile": model_profile(profile),
            "summary": metadata["summary"],
            "sector": deepcopy(sectors[metadata["sector"]]),
            "industry": deepcopy(industries[metadata["industry"]]),
            "tasks": [deepcopy(tasks[task]) for task in metadata["tasks"]],
            "readiness": deepcopy(readiness[metadata["readiness"]]),
            "tool_mode": deepcopy(tool_modes[mode]),
            "prerequisites": [
                "A model deployment",
                "Customer-reviewed instructions and acceptance cases",
            ],
            "runtime_hint": {
                **_PROFILE_HINTS[profile],
                "basis": f"{MODEL_PROFILES[profile]['label']} profile; actual usage depends on the selected model and input.",
            },
            "expected_behavior": metadata["expected_behavior"],
            "human_decision": metadata["human_decision"],
            "export": {
                "exportable": True,
                "availability": "after_creation",
                "bundle_kind": "lab-created",
                "package_format": "agent-bundle-v1",
                "sample_name": None,
                "description": (
                    "Create the agent in the Lab, then download its saved setup. It has everything "
                    "needed to run it as a hosted agent in your own Foundry project."
                ),
            },
            "keywords": list(metadata["keywords"]),
        })
    return result


def prepare_draft(goal, template_id=None):
    if not isinstance(goal, str) or not 10 <= len(goal) <= 1200 or len(goal.strip()) < 10 or "\x00" in goal:
        raise ValueError("Describe a task in 10 to 1200 characters")
    goal = goal.strip()
    if template_id is None:
        text = goal.casefold()
        candidates = [key for key, matcher in _MATCHERS.items() if is_listed(key) and _matches(matcher, text)]
        if len(candidates) != 1:
            raise TemplateRequiredError(candidates)
        template_id = candidates[0]
    if not isinstance(template_id, str) or not is_listed(template_id):
        raise ValueError("Unknown prepared template")
    template = TEMPLATES[template_id]
    instructions = template["instructions"] + "\n\nTask described by the user:\n" + goal
    if len(instructions) > 6000:
        raise ValueError("Prepared task instructions exceed the limit")
    return {
        "template_id": template_id, "name": template["label"], "instructions": instructions,
        "goal": goal, "source": "template", "sample_input": template["sample_input"],
    }

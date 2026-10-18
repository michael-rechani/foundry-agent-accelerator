"""Prepared agent templates for the Lab's library and Create page.

Each agent is one file in `agents/`: its template, its catalog metadata, its trigger-word matcher
and its place in the library. `_loader` reads and checks them, `catalog` serves the result, and
the public surface is re-exported here, so `from agent_templates import TEMPLATES` works as it
always has. To add an agent, add one file (see docs/agent-creation.md).
"""
from .catalog import (
    ANSWER_LAYOUT,
    AVAILABILITY_LEVELS,
    INDUSTRIES,
    LIBRARY_ORDER,
    MODEL_PROFILES,
    READINESS_LEVELS,
    RETIRED_TEMPLATES,
    SECTORS,
    TASKS,
    TEMPLATE_METADATA,
    TEMPLATES,
    TOOL_MODES,
    TemplateRequiredError,
    catalog_facets,
    is_available,
    is_featured,
    is_listed,
    list_templates,
    model_profile,
    prepare_draft,
)

__all__ = [
    "ANSWER_LAYOUT",
    "AVAILABILITY_LEVELS",
    "INDUSTRIES",
    "LIBRARY_ORDER",
    "MODEL_PROFILES",
    "READINESS_LEVELS",
    "RETIRED_TEMPLATES",
    "SECTORS",
    "TASKS",
    "TEMPLATE_METADATA",
    "TEMPLATES",
    "TOOL_MODES",
    "TemplateRequiredError",
    "catalog_facets",
    "is_available",
    "is_featured",
    "is_listed",
    "list_templates",
    "model_profile",
    "prepare_draft",
]

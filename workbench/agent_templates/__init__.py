"""Prepared agent templates for the Lab's library and Create page.

Each sector module (`cross_sector`, `public_sector`, `private_sector`) defines its jobs: the
template, its catalog metadata and its trigger-word matcher. `catalog` assembles them and serves
the public surface re-exported here, so `from agent_templates import TEMPLATES` works as it
always has.
"""

from .catalog import (
    ANSWER_LAYOUT,
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
    is_listed,
    list_templates,
    model_profile,
    prepare_draft,
)

__all__ = [
    "ANSWER_LAYOUT",
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
    "is_listed",
    "list_templates",
    "model_profile",
    "prepare_draft",
]

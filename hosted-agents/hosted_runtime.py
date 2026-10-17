"""Start-up shared by the review hosted agents and the knowledge overlay.

A hosted agent is uploaded as a standalone zip, so deployment.create_package and
deployment.knowledge_package ship this file next to main.py, the way they ship
review_output.py. Each main.py still opens its own credential, because the
coordinator needs the async one and the knowledge agent needs the credential to
build its tools. The basic-responses sample keeps its own start-up on purpose, so
that it stays one self-contained file to read.
"""

import os
from typing import Mapping, NamedTuple

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer


class AgentSettings(NamedTuple):
    endpoint: str
    model: str
    name: str
    instructions: str
    store_responses: bool


def agent_settings(default_name: str, default_instructions: str, environ: Mapping[str, str] | None = None) -> AgentSettings:
    """Read the settings every hosted agent needs, before any credential is opened."""
    environ = os.environ if environ is None else environ
    endpoint = environ.get("FOUNDRY_PROJECT_ENDPOINT")
    model = environ.get("FOUNDRY_MODEL_NAME")
    if not endpoint or not model:
        raise RuntimeError("FOUNDRY_PROJECT_ENDPOINT and FOUNDRY_MODEL_NAME must both be set")
    return AgentSettings(
        endpoint=endpoint,
        model=model,
        name=environ.get("AGENT_NAME", default_name),
        instructions=environ.get("AGENT_INSTRUCTIONS", default_instructions),
        store_responses=environ.get("AGENT_STORE_RESPONSES", "false").lower() == "true",
    )


def load_optimization_config():
    """Return the active Foundry Agent Optimizer candidate, or None when no run is active.

    The optimizer starts temporary agent versions with OPTIMIZATION_CONFIG or
    OPTIMIZATION_CANDIDATE_ID set. Anything else, including a missing package or the
    baseline folder beside main.py, leaves the agent exactly as deployed.
    """
    try:
        from azure.ai.agentserver.optimization import load_config
    except ImportError:
        return None
    config = load_config()
    source = getattr(config, "source", "") or ""
    return config if source.startswith(("env:", "api:")) else None


def apply_optimization(settings: AgentSettings, config) -> AgentSettings:
    """Overlay a candidate's instructions and model on the settings; no candidate changes nothing."""
    if config is None:
        return settings
    return settings._replace(
        instructions=config.compose_instructions() or settings.instructions,
        model=config.model or settings.model,
    )


def build_agent(credential, settings: AgentSettings, *, middleware=(), tools=()) -> Agent:
    """Build the agent. Middleware and tools are passed on only when there are some."""
    client_options = {"middleware": list(middleware)} if middleware else {}
    agent_options = {"tools": tools} if tools else {}
    return Agent(
        client=FoundryChatClient(
            project_endpoint=settings.endpoint,
            model=settings.model,
            credential=credential,
            allow_preview=True,
            **client_options,
        ),
        name=settings.name,
        instructions=settings.instructions,
        default_options={"store": settings.store_responses},
        **agent_options,
    )


async def serve(agent: Agent) -> None:
    await ResponsesHostServer(agent).run_async()

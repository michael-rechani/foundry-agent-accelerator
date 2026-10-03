"""Case-review runtime with optional read-only policy guidance retrieval.

deployment.with_knowledge_retrieval packages this file as main.py only when
KNOWLEDGE_RETRIEVAL_ENABLED=true; the default case-review package is unchanged.
"""

import asyncio
import os
from pathlib import Path

from azure.identity import DefaultAzureCredential

from hosted_runtime import agent_settings, build_agent, serve
from knowledge_retrieval import create_knowledge_tools, read_settings, with_addendum
from review_output import quotation_middleware


DEFAULT_INSTRUCTIONS = (Path(__file__).parent / "instructions.md").read_text(
    encoding="utf-8"
)


async def main() -> None:
    settings = agent_settings("case-review-agent", DEFAULT_INSTRUCTIONS)
    knowledge = read_settings(os.environ)
    if knowledge is not None:
        settings = settings._replace(instructions=with_addendum(settings.instructions))

    with DefaultAzureCredential() as credential:
        tools = create_knowledge_tools(knowledge, credential, settings.name)
        agent = build_agent(credential, settings, middleware=[quotation_middleware()], tools=tools)
        await serve(agent)


if __name__ == "__main__":
    asyncio.run(main())
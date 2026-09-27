import asyncio
import os
from pathlib import Path

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.identity import DefaultAzureCredential

from review_output import quotation_middleware

DEFAULT_INSTRUCTIONS = (Path(__file__).parent / "instructions.md").read_text(
    encoding="utf-8"
)


async def main() -> None:
    project_endpoint = os.getenv("FOUNDRY_PROJECT_ENDPOINT")
    model_deployment = os.getenv("FOUNDRY_MODEL_NAME")
    if not project_endpoint or not model_deployment:
        raise RuntimeError(
            "FOUNDRY_PROJECT_ENDPOINT and FOUNDRY_MODEL_NAME must both be set"
        )
    store_responses = os.getenv("AGENT_STORE_RESPONSES", "false").lower() == "true"

    with DefaultAzureCredential() as credential:
        agent = Agent(
            client=FoundryChatClient(
                project_endpoint=project_endpoint,
                model=model_deployment,
                credential=credential,
                allow_preview=True,
                middleware=[quotation_middleware()],
            ),
            name=os.getenv("AGENT_NAME", "case-review-agent"),
            instructions=os.getenv("AGENT_INSTRUCTIONS", DEFAULT_INSTRUCTIONS),
            default_options={"store": store_responses},
        )
        await ResponsesHostServer(agent).run_async()


if __name__ == "__main__":
    asyncio.run(main())
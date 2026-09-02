import asyncio
import os

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.identity import DefaultAzureCredential


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
            ),
            name=os.getenv("AGENT_NAME", "basic-responses-agent"),
            instructions=os.getenv(
                "AGENT_INSTRUCTIONS",
                "You are a concise and helpful assistant.",
            ),
            default_options={"store": store_responses},
        )

        server = ResponsesHostServer(agent)
        await server.run_async()


if __name__ == "__main__":
    asyncio.run(main())


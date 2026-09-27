import asyncio
import json
import math
import os
from pathlib import Path

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.ai.projects.aio import AIProjectClient
from azure.identity.aio import DefaultAzureCredential

from configuration import DEFAULT_SPECIALISTS, validate_specialists


DEFAULT_INSTRUCTIONS = (Path(__file__).parent / "instructions.md").read_text(
    encoding="utf-8"
)


class SpecialistClients:
    """Keeps one authenticated client per specialist so calls reuse open connections.

    Each client fetches a current token for every request, so reuse does not pin an expiring token.
    """

    def __init__(self, project_endpoint: str, credential: DefaultAzureCredential) -> None:
        self._project_endpoint = project_endpoint
        self._credential = credential
        self._project_client = None
        self._clients = {}

    def get(self, agent_name: str, timeout_seconds: float):
        client = self._clients.get(agent_name)
        if client is None:
            if self._project_client is None:
                self._project_client = AIProjectClient(
                    endpoint=self._project_endpoint,
                    credential=self._credential,
                    allow_preview=True,
                )
            client = self._project_client.get_openai_client(
                agent_name=agent_name,
                timeout=timeout_seconds,
                max_retries=0,
            )
            self._clients[agent_name] = client
        return client

    async def close(self) -> None:
        clients, self._clients = list(self._clients.values()), {}
        project_client, self._project_client = self._project_client, None
        for client in clients:
            await client.close()
        if project_client is not None:
            await project_client.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self.close()


async def invoke_specialist(
    clients: SpecialistClients,
    agent_name: str,
    request: str,
    timeout_seconds: float = 90,
) -> str:
    openai_client = clients.get(agent_name, timeout_seconds)
    response = await openai_client.responses.create(input=request, store=False)

    if response.status != "completed":
        raise RuntimeError(f"Specialist agent {agent_name} did not complete")
    result = response.output_text.strip()
    if not result:
        raise RuntimeError(f"Specialist agent {agent_name} returned an empty response")
    return result


def create_specialist_tools(clients: SpecialistClients):
    timeout_seconds = float(os.getenv("SPECIALIST_TIMEOUT_SECONDS", "90"))
    max_concurrency = int(os.getenv("SPECIALIST_MAX_CONCURRENCY", "4"))
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ValueError("SPECIALIST_TIMEOUT_SECONDS must be finite and positive")
    if max_concurrency <= 0:
        raise ValueError("SPECIALIST_MAX_CONCURRENCY must be positive")
    semaphore = asyncio.Semaphore(max_concurrency)
    application_agent_name = os.getenv(
        "APPLICATION_REVIEW_AGENT_NAME", "application-review-agent"
    )
    case_agent_name = os.getenv("CASE_REVIEW_AGENT_NAME", "case-review-agent")

    async def review(agent_name: str, request: str) -> str:
        async with asyncio.timeout(timeout_seconds):
            async with semaphore:
                result = await invoke_specialist(clients, agent_name, request, timeout_seconds)
                return json.dumps({"status": "succeeded", "agent": agent_name, "output": result})

    configured = os.getenv("SPECIALIST_CONFIG")
    specialists = validate_specialists(json.loads(configured) if configured is not None else [
        {**DEFAULT_SPECIALISTS[0], "agent": application_agent_name},
        {**DEFAULT_SPECIALISTS[1], "agent": case_agent_name},
    ])
    if any(item["agent"] == os.getenv("AGENT_NAME", "review-coordinator-agent") for item in specialists):
        raise ValueError("Coordinator cannot delegate to itself")

    def create_tool(specialist):
        async def invoke(request: str) -> str:
            return await review(specialist["agent"], request)

        invoke.__name__ = specialist["tool"]
        invoke.__doc__ = specialist["description"]
        return invoke

    return [create_tool(specialist) for specialist in specialists]


async def main() -> None:
    project_endpoint = os.getenv("FOUNDRY_PROJECT_ENDPOINT")
    model_deployment = os.getenv("FOUNDRY_MODEL_NAME")
    if not project_endpoint or not model_deployment:
        raise RuntimeError(
            "FOUNDRY_PROJECT_ENDPOINT and FOUNDRY_MODEL_NAME must both be set"
        )
    store_responses = os.getenv("AGENT_STORE_RESPONSES", "false").lower() == "true"

    async with (
        DefaultAzureCredential() as credential,
        SpecialistClients(project_endpoint, credential) as specialist_clients,
    ):
        agent = Agent(
            client=FoundryChatClient(
                project_endpoint=project_endpoint,
                model=model_deployment,
                credential=credential,
                allow_preview=True,
            ),
            name=os.getenv("AGENT_NAME", "review-coordinator-agent"),
            instructions=os.getenv("AGENT_INSTRUCTIONS", DEFAULT_INSTRUCTIONS),
            tools=create_specialist_tools(specialist_clients),
            default_options={"store": store_responses},
        )
        await ResponsesHostServer(agent).run_async()


if __name__ == "__main__":
    asyncio.run(main())
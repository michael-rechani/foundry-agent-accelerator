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

from configuration import validate_specialists


DEFAULT_INSTRUCTIONS = (Path(__file__).parent / "instructions.md").read_text(
    encoding="utf-8"
)


async def invoke_specialist(
    project_endpoint: str,
    credential: DefaultAzureCredential,
    agent_name: str,
    request: str,
    timeout_seconds: float = 90,
) -> str:
    async with AIProjectClient(
        endpoint=project_endpoint,
        credential=credential,
        allow_preview=True,
    ) as project_client:
        async with project_client.get_openai_client(
            agent_name=agent_name,
            timeout=timeout_seconds,
            max_retries=0,
        ) as openai_client:
            response = await openai_client.responses.create(input=request, store=False)

    if response.status != "completed":
        raise RuntimeError(f"Specialist agent {agent_name} did not complete")
    result = response.output_text.strip()
    if not result:
        raise RuntimeError(f"Specialist agent {agent_name} returned an empty response")
    return result


def create_specialist_tools(
    project_endpoint: str,
    credential: DefaultAzureCredential,
):
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
                result = await invoke_specialist(
                    project_endpoint, credential, agent_name, request, timeout_seconds
                )
                return json.dumps({"status": "succeeded", "agent": agent_name, "output": result})

    configured = os.getenv("SPECIALIST_CONFIG")
    specialists = validate_specialists(json.loads(configured) if configured is not None else [
        {"tool": "review_application", "agent": application_agent_name,
         "description": "Review application completeness or RFP/proposal coverage against supplied criteria and source evidence."},
        {"tool": "review_case", "agent": case_agent_name,
         "description": "Review a case record and return evidence-grounded findings."},
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

    async with DefaultAzureCredential() as credential:
        agent = Agent(
            client=FoundryChatClient(
                project_endpoint=project_endpoint,
                model=model_deployment,
                credential=credential,
                allow_preview=True,
            ),
            name=os.getenv("AGENT_NAME", "review-coordinator-agent"),
            instructions=os.getenv("AGENT_INSTRUCTIONS", DEFAULT_INSTRUCTIONS),
            tools=create_specialist_tools(project_endpoint, credential),
            default_options={"store": store_responses},
        )
        await ResponsesHostServer(agent).run_async()


if __name__ == "__main__":
    asyncio.run(main())
import asyncio
import json
import math
import os
import time
from pathlib import Path

from azure.ai.projects.aio import AIProjectClient
from azure.identity.aio import DefaultAzureCredential

from configuration import DEFAULT_SPECIALISTS, validate_specialists
from hosted_runtime import agent_settings, build_agent, serve
from review_output import passthrough_middleware


DEFAULT_INSTRUCTIONS = (Path(__file__).parent / "instructions.md").read_text(
    encoding="utf-8"
)


def session_reuse_seconds() -> float:
    value = float(os.getenv("SPECIALIST_SESSION_REUSE_SECONDS", "600"))
    if not math.isfinite(value) or not 0 <= value <= 3600:
        raise ValueError("SPECIALIST_SESSION_REUSE_SECONDS must be between 0 and 3600")
    return value


class SpecialistClients:
    """Keeps one authenticated client per specialist so calls reuse open connections.

    Each client fetches a current token for every request, so reuse does not pin an expiring token.
    Completed specialist sessions are also kept for a bounded time so later calls skip a cold start.
    A session serves one call at a time, and a failed call discards its session.
    """

    def __init__(
        self,
        project_endpoint: str,
        credential: DefaultAzureCredential,
        reuse_seconds: float | None = None,
    ) -> None:
        self._project_endpoint = project_endpoint
        self._credential = credential
        self._project_client = None
        self._clients = {}
        self._reuse_seconds = session_reuse_seconds() if reuse_seconds is None else reuse_seconds
        self._idle_sessions = {}

    def lease_session(self, agent_name: str) -> tuple[str, float] | None:
        sessions = self._idle_sessions.get(agent_name, [])
        while sessions:
            session_id, created = sessions.pop()
            if time.monotonic() - created < self._reuse_seconds:
                return session_id, created
        return None

    def release_session(self, agent_name: str, session_id: object, created: float) -> None:
        if isinstance(session_id, str) and session_id and time.monotonic() - created < self._reuse_seconds:
            self._idle_sessions.setdefault(agent_name, []).append((session_id, created))

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
        self._idle_sessions = {}
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
    if not isinstance(request, str) or not request.strip():
        raise ValueError("Specialist request must be nonempty text")
    openai_client = clients.get(agent_name, timeout_seconds)
    leased = clients.lease_session(agent_name)
    started = time.monotonic()
    options = {"extra_body": {"agent_session_id": leased[0]}} if leased else {}
    response = await openai_client.responses.create(input=request, store=False, **options)

    if response.status != "completed":
        raise RuntimeError(f"Specialist agent {agent_name} did not complete")
    if not isinstance(response.output_text, str) or not response.output_text.strip():
        raise RuntimeError(f"Specialist agent {agent_name} returned an empty response")
    result = response.output_text.strip()
    session_id = (getattr(response, "model_extra", None) or {}).get("agent_session_id") or (leased and leased[0])
    clients.release_session(agent_name, session_id, leased[1] if leased and session_id == leased[0] else started)
    return result


def configured_specialists():
    application_agent_name = os.getenv("APPLICATION_REVIEW_AGENT_NAME", "application-review-agent")
    case_agent_name = os.getenv("CASE_REVIEW_AGENT_NAME", "case-review-agent")
    configured = os.getenv("SPECIALIST_CONFIG")
    specialists = validate_specialists(json.loads(configured) if configured is not None else [
        {**DEFAULT_SPECIALISTS[0], "agent": application_agent_name},
        {**DEFAULT_SPECIALISTS[1], "agent": case_agent_name},
    ])
    if any(item["agent"] == os.getenv("AGENT_NAME", "review-coordinator-agent") for item in specialists):
        raise ValueError("Coordinator cannot delegate to itself")
    return specialists


def create_specialist_tools(clients: SpecialistClients):
    timeout_seconds = float(os.getenv("SPECIALIST_TIMEOUT_SECONDS", "90"))
    max_concurrency = int(os.getenv("SPECIALIST_MAX_CONCURRENCY", "4"))
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ValueError("SPECIALIST_TIMEOUT_SECONDS must be finite and positive")
    if max_concurrency <= 0:
        raise ValueError("SPECIALIST_MAX_CONCURRENCY must be positive")
    semaphore = asyncio.Semaphore(max_concurrency)

    async def review(agent_name: str, request: str) -> str:
        async with asyncio.timeout(timeout_seconds):
            async with semaphore:
                result = await invoke_specialist(clients, agent_name, request, timeout_seconds)
                return json.dumps({"status": "succeeded", "agent": agent_name, "output": result})

    specialists = configured_specialists()

    def create_tool(specialist):
        async def invoke(request: str) -> str:
            return await review(specialist["agent"], request)

        invoke.__name__ = specialist["tool"]
        invoke.__doc__ = specialist["description"]
        return invoke

    return [create_tool(specialist) for specialist in specialists]


async def main() -> None:
    settings = agent_settings("review-coordinator-agent", DEFAULT_INSTRUCTIONS)

    async with (
        DefaultAzureCredential() as credential,
        SpecialistClients(settings.endpoint, credential) as specialist_clients,
    ):
        agent = build_agent(
            credential,
            settings,
            middleware=[passthrough_middleware({
                item["tool"]: item["agent"] for item in configured_specialists()
            })],
            tools=create_specialist_tools(specialist_clients),
        )
        await serve(agent)


if __name__ == "__main__":
    asyncio.run(main())
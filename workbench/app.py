import asyncio
import json
import logging
import os
import re
import time
from collections import deque
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from history import CosmosHistory, history_router
from review_runs import ReviewRuns
from agent_creation import CREATED_ID, AgentCreations, CreationSettings


ROOT = Path(__file__).resolve().parent
NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_-]{0,63}\Z")
LOGGER = logging.getLogger("uvicorn.error")
MAX_CHARACTERS = 60000
MAX_REQUEST_BYTES = 65536
MAX_HISTORY_TURNS = 10
HISTORY_TIMEOUT_MS = 45000


def cache_policy(path, status):
    if status not in (200, 304):
        return "no-store"
    if re.fullmatch(r"/assets/[^/]+-[A-Za-z0-9_-]{8,}\.(?:js|css|woff2?|png|svg|webp)", path):
        return "public, max-age=31536000, immutable"
    return "no-cache" if path in {"/", "/index.html"} else "no-store"


@dataclass(frozen=True)
class Settings:
    mode: str
    endpoint: str
    hosts: tuple[str, ...]
    origins: tuple[str, ...]
    agents_path: Path = ROOT / "agents.json"
    timeout: float = 180
    visible_agents: tuple[str, ...] = ("customer-review",)
    default_agent: str | None = None
    title: str = "Foundry Agent Lab"
    creation: CreationSettings = field(default_factory=CreationSettings)

    @classmethod
    def from_env(cls):
        mode = os.getenv("WORKBENCH_MODE", "preview")
        endpoint = os.getenv("FOUNDRY_PROJECT_ENDPOINT", "")
        hosts = tuple(filter(None, os.getenv("WORKBENCH_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")))
        origins = tuple(filter(None, os.getenv("WORKBENCH_ORIGINS", "http://127.0.0.1:8080,http://localhost:8080").split(",")))
        visible_agents = tuple(filter(None, os.getenv("WORKBENCH_VISIBLE_AGENTS", "customer-review").split(",")))
        return cls(mode, endpoint, hosts, origins, Path(os.getenv("WORKBENCH_AGENTS_FILE", ROOT / "agents.json")),
               visible_agents=visible_agents, default_agent=os.getenv("WORKBENCH_DEFAULT_AGENT") or None,
               title=os.getenv("WORKBENCH_TITLE", "Foundry Agent Lab"), creation=CreationSettings.from_env())

    def validate(self):
        if not isinstance(self.title, str) or not self.title.strip() or len(self.title) > 80 or any(ord(char) < 32 for char in self.title):
            raise ValueError("Workspace title must contain one to 80 printable characters")
        if not isinstance(self.timeout, (int, float)) or isinstance(self.timeout, bool) or not 1 <= self.timeout <= 180:
            raise ValueError("Review timeout must be between one and 180 seconds")
        if self.mode not in {"preview", "private"}:
            raise ValueError("WORKBENCH_MODE must be preview or private")
        self.creation.validate(self.mode)
        if not self.hosts or any("*" in host or "/" in host for host in self.hosts):
            raise ValueError("Explicit allowed hosts are required")
        if not self.origins:
            raise ValueError("Explicit browser origins are required")
        for origin in self.origins:
            parsed = urlparse(origin)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.path or parsed.query or parsed.fragment or parsed.username:
                raise ValueError("Invalid browser origin")
            if self.mode == "private" and parsed.scheme != "https":
                raise ValueError("Private mode requires HTTPS origins")
        if self.mode == "private":
            parsed = urlparse(self.endpoint)
            if (parsed.scheme != "https" or not (parsed.hostname or "").endswith(".services.ai.azure.com")
                    or parsed.port not in (None, 443) or parsed.username or parsed.query or parsed.fragment
                    or not re.fullmatch(r"/api/projects/[A-Za-z0-9_-]+", parsed.path)):
                raise ValueError("Private mode requires a Foundry project endpoint")
        elif any(host not in {"localhost", "127.0.0.1"} for host in self.hosts):
            raise ValueError("Preview mode is restricted to localhost")


def load_agents(path):
    agents = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(agents, list) or not 1 <= len(agents) <= 16:
        raise ValueError("Configure between one and sixteen agents")
    identifiers = set()
    for agent in agents:
        required = {"id", "label", "category", "description", "agent", "tools"}
        if not isinstance(agent, dict) or not required <= set(agent) or set(agent) - required - {"prompts", "guidance"}:
            raise ValueError("Invalid agent configuration")
        for key in ("id", "agent"):
            if not isinstance(agent[key], str) or not NAME.fullmatch(agent[key]):
                raise ValueError("Invalid agent name")
        if CREATED_ID.fullmatch(agent["id"]):
            raise ValueError("The created-agent identifier namespace is reserved")
        for key in ("label", "category", "description"):
            if not isinstance(agent[key], str) or not agent[key].strip():
                raise ValueError("Agent display fields must be nonempty")
        if "guidance" in agent:
            guidance = agent["guidance"]
            if (not isinstance(guidance, dict)
                    or set(guidance) != {"input", "output", "limits", "delegation", "configuration"}
                    or any(not isinstance(value, str) or not 1 <= len(value.strip()) <= 1200
                           for value in guidance.values())):
                raise ValueError("Invalid agent guidance")
        if agent["id"] in identifiers:
            raise ValueError("Duplicate agent identifier")
        identifiers.add(agent["id"])
        if not isinstance(agent["tools"], dict) or any(
            not isinstance(tool, str) or not NAME.fullmatch(tool) or not isinstance(target, str) or not NAME.fullmatch(target)
            for tool, target in agent["tools"].items()
        ):
            raise ValueError("Invalid specialist bindings")
        prompts = agent.setdefault("prompts", [])
        if not isinstance(prompts, list) or len(prompts) > 6:
            raise ValueError("Configure up to six starter prompts per agent")
        for prompt in prompts:
            if (not isinstance(prompt, dict) or set(prompt) != {"label", "text"}
                    or not isinstance(prompt["label"], str) or not 1 <= len(prompt["label"].strip()) <= 80
                    or not isinstance(prompt["text"], str) or not 1 <= len(prompt["text"].strip()) <= 4000):
                raise ValueError("Invalid starter prompt")
    return agents


def execution_receipts(output, bindings):
    calls = [item for item in output if item.get("type") == "function_call"]
    receipts = []
    for call in calls:
        call_id = call.get("call_id")
        matching = [item for item in output if item.get("type") == "function_call_output" and item.get("call_id") == call_id]
        unique = bool(call_id) and sum(item.get("call_id") == call_id for item in calls) == 1
        receipt = {"tool": call.get("name", "unknown"), "call_id": call_id, "verified": False, "agent": None, "output": None}
        if unique and len(matching) == 1:
            try:
                result = json.loads(matching[0].get("output", ""))
            except (TypeError, ValueError):
                result = None
            if (isinstance(result, dict) and result.get("status") == "succeeded"
                    and call.get("name") in bindings and result.get("agent") == bindings[call["name"]]
                    and isinstance(result.get("output"), str) and result["output"].strip()):
                receipt.update(verified=True, agent=result["agent"], output=result["output"])
        receipts.append(receipt)
    return receipts


class FoundryGateway:
    def __init__(self, settings):
        self.settings = settings

    async def check(self, agents):
        from azure.ai.projects.aio import AIProjectClient
        from azure.identity.aio import ManagedIdentityCredential

        async with ManagedIdentityCredential(client_id=os.getenv("AZURE_CLIENT_ID")) as credential, AIProjectClient(
            endpoint=self.settings.endpoint, credential=credential, allow_preview=True,
            connection_timeout=5, read_timeout=5, retry_total=0,
        ) as project:
            for agent in agents:
                await project.agents.get(agent["agent"])

    async def review(self, agent, prompt):
        from azure.ai.projects.aio import AIProjectClient
        from azure.identity.aio import ManagedIdentityCredential

        async with ManagedIdentityCredential(client_id=os.getenv("AZURE_CLIENT_ID")) as credential, AIProjectClient(
            endpoint=self.settings.endpoint, credential=credential, allow_preview=True,
        ) as project:
            async with project.get_openai_client(agent_name=agent["agent"], timeout=self.settings.timeout, max_retries=0) as client:
                response = await client.responses.create(input=prompt, store=False, stream=False)
                return response.status, response.output_text, response.model_dump().get("output", [])


def create_app(settings=None, gateway=None, history_store=None, publisher=None):
    settings = settings or Settings.from_env()
    settings.validate()
    agents = load_agents(settings.agents_path)
    known_agents = {agent["id"] for agent in agents}
    if not settings.visible_agents or not set(settings.visible_agents) <= known_agents:
        raise ValueError("WORKBENCH_VISIBLE_AGENTS must name configured agents")
    agents = [agent for agent in agents if agent["id"] in settings.visible_agents]
    registry = {agent["id"]: agent for agent in agents}
    default_agent = settings.default_agent or settings.visible_agents[0]
    if default_agent not in registry:
        raise ValueError("WORKBENCH_DEFAULT_AGENT must name a visible agent")
    gateway = gateway or FoundryGateway(settings)
    slots = asyncio.Semaphore(4)
    recent = deque()
    cosmos_endpoint = os.getenv("WORKBENCH_COSMOS_ENDPOINT")
    if settings.mode == "private" and cosmos_endpoint and history_store is None:
        history_store = CosmosHistory(cosmos_endpoint)

    review_runs = ReviewRuns(settings, registry, history_store, gateway, execution_receipts, slots, recent)
    created_agents = AgentCreations(settings, history_store, publisher)
    dependency_status = {"status": "disabled" if settings.mode == "preview" else "starting"}

    async def probe_dependencies():
        async def check(operation):
            try:
                async with asyncio.timeout(15):
                    await operation()
                return "ready"
            except Exception:
                return "unavailable"

        foundry, cosmos = await asyncio.gather(
            check(lambda: gateway.check(agents)),
            check(history_store.check) if history_store is not None else asyncio.sleep(0, result="disabled"),
        )
        dependency_status.update(status="ready" if foundry == "ready" and cosmos in {"ready", "disabled"} else "degraded",
                                 foundry=foundry, cosmos=cosmos)
        LOGGER.info(json.dumps({"event": "workbench_dependencies", **dependency_status}))

    async def monitor_dependencies(stopped):
        while not stopped.is_set():
            try:
                await asyncio.wait_for(stopped.wait(), timeout=60)
            except TimeoutError:
                await probe_dependencies()

    @asynccontextmanager
    async def lifespan(application):
        stopped = asyncio.Event()
        monitor = None
        try:
            if settings.mode == "private":
                await probe_dependencies()
                monitor = asyncio.create_task(monitor_dependencies(stopped))
            yield
        finally:
            stopped.set()
            if monitor is not None:
                monitor.cancel()
                await asyncio.gather(monitor, return_exceptions=True)
            await review_runs.close()
            await created_agents.close()
            if history_store is not None:
                await history_store.close()

    application = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    application.add_middleware(TrustedHostMiddleware, allowed_hosts=list(settings.hosts))

    @application.middleware("http")
    async def security_headers(request, call_next):
        started = time.monotonic()
        request.state.request_id = str(uuid4())
        response = await call_next(request)
        response.headers.update({
            "Cache-Control": cache_policy(request.url.path, response.status_code), "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer", "X-Frame-Options": "DENY",
            "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
        })
        if settings.mode == "private":
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        if request.url.path.startswith("/api/"):
            response.headers["X-Correlation-ID"] = request.state.request_id
            route = getattr(request.scope.get("route"), "path", "unmatched")
            LOGGER.info(json.dumps({"event": "workbench_request", "request_id": request.state.request_id,
                "route": route, "status": response.status_code,
                "outcome": getattr(request.state, "error_code", "completed" if response.status_code < 400 else "rejected"),
                "elapsed_ms": round((time.monotonic() - started) * 1000)}))
        return response

    @application.get("/healthz")
    async def health():
        return {"status": "ready", "mode": settings.mode}

    @application.get("/api/health/dependencies")
    async def dependencies():
        return JSONResponse(dependency_status, status_code=200 if dependency_status["status"] == "ready" else 503)

    @application.get("/api/config")
    async def configuration():
        return {"mode": settings.mode, "title": settings.title, "agents": agents, "default_agent": default_agent,
            "max_characters": MAX_CHARACTERS, "max_request_bytes": MAX_REQUEST_BYTES,
            "max_history_turns": MAX_HISTORY_TURNS,
            "review_timeout_ms": round(settings.timeout * 1000) + 10000,
            "history_timeout_ms": HISTORY_TIMEOUT_MS,
            "history_enabled": history_store is not None, "history_scope": "shared", "retention_days": 30,
            "reviews_enabled": settings.mode == "private" and history_store is not None,
            "agent_creation": created_agents.capabilities()}

    @application.post("/api/reviews")
    async def review(request: Request):
        now = time.monotonic()
        while recent and recent[0] <= now - 60:
            recent.popleft()
        if slots.locked() or len(recent) >= 20:
            request.state.error_code = "busy"
            return JSONResponse({"error": "busy", "request_id": request.state.request_id},
                                status_code=429, headers={"Retry-After": "60"})
        recent.append(now)
        async with slots:
            return await execute_review(request)

    async def execute_review(request: Request):
        request_id = request.state.request_id

        def error(status, code):
            request.state.error_code = code
            return JSONResponse({"error": code, "request_id": request_id}, status_code=status,
                                headers={"X-Correlation-ID": request_id})

        origin = request.headers.get("origin")
        if (request.headers.get("x-workbench-request") != "1" or
                request.headers.get("sec-fetch-site") == "cross-site" or
                (origin is not None and origin not in settings.origins)):
            return error(403, "request_not_allowed")
        if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
            return error(415, "json_required")
        body = bytearray()
        try:
            async with asyncio.timeout(5):
                async for chunk in request.stream():
                    body.extend(chunk)
                    if len(body) > MAX_REQUEST_BYTES:
                        return error(413, "request_too_large")
        except TimeoutError:
            return error(408, "request_timeout")
        try:
            data = json.loads(body)
        except (ValueError, UnicodeError):
            return error(400, "invalid_request")
        if (not isinstance(data, dict) or set(data) not in ({"agent_id", "input"}, {"agent_id", "input", "history"}) or
                not isinstance(data["agent_id"], str) or
                (data["agent_id"] not in registry and not CREATED_ID.fullmatch(data["agent_id"])) or
                not isinstance(data["input"], str) or not data["input"].strip() or len(data["input"]) > MAX_CHARACTERS):
            return error(400, "invalid_request")
        history = data.get("history", [])
        if not isinstance(history, list) or len(history) > MAX_HISTORY_TURNS * 2 or len(history) % 2:
            return error(400, "invalid_request")
        for index, message in enumerate(history):
            if (not isinstance(message, dict) or set(message) != {"role", "content"} or
                    message["role"] != ("user" if index % 2 == 0 else "assistant") or
                    not isinstance(message["content"], str) or not message["content"].strip()):
                return error(400, "invalid_request")
        if sum(len(message["content"]) for message in history) + len(data["input"]) > MAX_CHARACTERS:
            return error(400, "invalid_request")
        prompt = history + [{"role": "user", "content": data["input"]}] if history else data["input"]
        if settings.mode == "preview":
            return error(503, "preview_only")
        agent = registry.get(data["agent_id"])
        if agent is None:
            try:
                agent = await created_agents.resolve_agent(data["agent_id"])
            except Exception as problem:
                LOGGER.error(json.dumps({"event": "created_agent_lookup_failed", "type": type(problem).__name__}))
                return error(503, "agents_unavailable")
            if agent is None:
                return error(400, "invalid_request")
        started = time.monotonic()
        try:
            async with asyncio.timeout(settings.timeout):
                status, text, output = await gateway.review(agent, prompt)
            if status != "completed" or not isinstance(text, str) or not text.strip():
                return error(502, "incomplete_response")
            if len(text) > 100000 or len(json.dumps(output).encode("utf-8")) > 524288:
                return error(502, "response_too_large")
            receipts = execution_receipts(output, agent["tools"])
            if len(receipts) > 32 or any(len(receipt["output"] or "") > 100000 for receipt in receipts):
                return error(502, "response_too_large")
            return JSONResponse({"request_id": request_id, "status": status, "agent": agent["agent"],
                                 "text": text, "receipts": receipts, "elapsed_ms": round((time.monotonic() - started) * 1000)},
                                headers={"X-Correlation-ID": request_id})
        except TimeoutError:
            return error(504, "timeout")
        except Exception:
            return error(502, "backend_unavailable")

    application.include_router(history_router(settings, registry, history_store, created_agents))
    application.include_router(review_runs.router)
    application.include_router(created_agents.router)
    application.mount("/", StaticFiles(directory=ROOT / "static", html=True, check_dir=False), name="static")
    return application
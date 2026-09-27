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
from request_guard import MAX_REQUEST_BYTES, read_bounded_body, record_request_failure, request_allowed


ROOT = Path(__file__).resolve().parent
NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_-]{0,63}\Z")
LOGGER = logging.getLogger("uvicorn.error")
MAX_CHARACTERS = 60000
MAX_HISTORY_TURNS = 10
MAX_REUSED_SESSIONS = 512
THREAD = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z")
HISTORY_TIMEOUT_MS = 45000
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer", "X-Frame-Options": "DENY",
    "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
}


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
    session_reuse_seconds: float = 600

    @classmethod
    def from_env(cls):
        mode = os.getenv("WORKBENCH_MODE", "preview")
        endpoint = os.getenv("FOUNDRY_PROJECT_ENDPOINT", "")
        hosts = tuple(filter(None, os.getenv("WORKBENCH_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")))
        origins = tuple(filter(None, os.getenv("WORKBENCH_ORIGINS", "http://127.0.0.1:8080,http://localhost:8080").split(",")))
        visible_agents = tuple(filter(None, os.getenv("WORKBENCH_VISIBLE_AGENTS", "customer-review").split(",")))
        return cls(mode, endpoint, hosts, origins, Path(os.getenv("WORKBENCH_AGENTS_FILE", ROOT / "agents.json")),
               visible_agents=visible_agents, default_agent=os.getenv("WORKBENCH_DEFAULT_AGENT") or None,
               title=os.getenv("WORKBENCH_TITLE", "Foundry Agent Lab"), creation=CreationSettings.from_env(),
               session_reuse_seconds=float(os.getenv("WORKBENCH_SESSION_REUSE_SECONDS", "600")))

    def validate(self):
        if not isinstance(self.title, str) or not self.title.strip() or len(self.title) > 80 or any(ord(char) < 32 for char in self.title):
            raise ValueError("Workspace title must contain one to 80 printable characters")
        if not isinstance(self.timeout, (int, float)) or isinstance(self.timeout, bool) or not 1 <= self.timeout <= 180:
            raise ValueError("Review timeout must be between one and 180 seconds")
        reuse = self.session_reuse_seconds
        if not isinstance(reuse, (int, float)) or isinstance(reuse, bool) or not 0 <= reuse <= 3600:
            raise ValueError("Session reuse must be between zero and 3600 seconds")
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


def validate_agent(agent):
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


def load_agents(path):
    agents = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(agents, list) or not 1 <= len(agents) <= 16:
        raise ValueError("Configure between one and sixteen agents")
    identifiers = set()
    for agent in agents:
        validate_agent(agent)
        if agent["id"] in identifiers:
            raise ValueError("Duplicate agent identifier")
        identifiers.add(agent["id"])
    return agents


def chat_prompt(data, registry):
    """Return the Responses input for a valid chat request body, or None when it is invalid."""
    if (not isinstance(data, dict) or not {"agent_id", "input"} <= set(data) <= {"agent_id", "input", "history", "thread"} or
            not isinstance(data["agent_id"], str) or
            (data["agent_id"] not in registry and not CREATED_ID.fullmatch(data["agent_id"])) or
            not isinstance(data["input"], str) or not data["input"].strip() or len(data["input"]) > MAX_CHARACTERS):
        return None
    if "thread" in data and (not isinstance(data["thread"], str) or not THREAD.fullmatch(data["thread"])):
        return None
    history = data.get("history", [])
    if not isinstance(history, list) or len(history) > MAX_HISTORY_TURNS * 2 or len(history) % 2:
        return None
    for index, message in enumerate(history):
        if (not isinstance(message, dict) or set(message) != {"role", "content"} or
                message["role"] != ("user" if index % 2 == 0 else "assistant") or
                not isinstance(message["content"], str) or not message["content"].strip()):
            return None
    if sum(len(message["content"]) for message in history) + len(data["input"]) > MAX_CHARACTERS:
        return None
    return history + [{"role": "user", "content": data["input"]}] if history else data["input"]


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
        self._credential = self._project = self._http_client = None
        self._sessions = {}

    async def check(self, agents):
        from azure.ai.projects.aio import AIProjectClient
        from azure.identity.aio import ManagedIdentityCredential

        async with ManagedIdentityCredential(client_id=os.getenv("AZURE_CLIENT_ID")) as credential, AIProjectClient(
            endpoint=self.settings.endpoint, credential=credential, allow_preview=True,
            connection_timeout=5, read_timeout=5, retry_total=0,
        ) as project:
            for agent in agents:
                await project.agents.get(agent["agent"])

    def _review_project(self):
        if self._project is None:
            from azure.ai.projects.aio import AIProjectClient
            from azure.identity.aio import ManagedIdentityCredential
            from openai import DefaultAsyncHttpxClient

            self._credential = ManagedIdentityCredential(client_id=os.getenv("AZURE_CLIENT_ID"))
            self._project = AIProjectClient(endpoint=self.settings.endpoint, credential=self._credential, allow_preview=True)
            self._http_client = DefaultAsyncHttpxClient()
        return self._project

    async def review(self, agent, prompt, thread=None):
        # Reuses the cached token and open connections. The per-agent client shares the pool, so closing it would close the pool.
        client = self._review_project().get_openai_client(
            agent_name=agent["agent"], timeout=self.settings.timeout, max_retries=0, http_client=self._http_client,
        )
        # A chat thread reuses its Foundry session to skip a sandbox cold start. The session ID never leaves the server.
        key = (thread, agent["agent"]) if thread and self.settings.session_reuse_seconds > 0 else None
        leased = self._sessions.pop(key, None) if key else None
        if leased and time.monotonic() - leased[1] >= self.settings.session_reuse_seconds:
            leased = None
        started = time.monotonic()
        options = {"extra_body": {"agent_session_id": leased[0]}} if leased else {}
        response = await client.responses.create(input=prompt, store=False, stream=False, **options)
        if key and response.status == "completed":
            session_id = (getattr(response, "model_extra", None) or {}).get("agent_session_id") or (leased and leased[0])
            self._keep_session(key, session_id, leased[1] if leased and session_id == leased[0] else started)
        return response.status, response.output_text, response.model_dump().get("output", [])

    def _keep_session(self, key, session_id, created):
        now, reuse = time.monotonic(), self.settings.session_reuse_seconds
        if not isinstance(session_id, str) or not session_id or now - created >= reuse:
            return
        self._sessions[key] = (session_id, created)
        for stale in [item for item, (_, since) in self._sessions.items() if now - since >= reuse]:
            del self._sessions[stale]
        while len(self._sessions) > MAX_REUSED_SESSIONS:
            del self._sessions[next(iter(self._sessions))]

    async def close(self):
        self._sessions = {}
        http_client, project, credential = self._http_client, self._project, self._credential
        self._credential = self._project = self._http_client = None
        if http_client is not None:
            await http_client.aclose()
        if project is not None:
            await project.close()
        if credential is not None:
            await credential.close()


class ChatReviews:
    """Stateless chat turns: POST /api/reviews admission, validation, and one bounded Foundry Responses call."""

    def __init__(self, settings, registry, gateway, created_agents, slots, recent):
        self.settings, self.registry, self.gateway = settings, registry, gateway
        self.created_agents, self.slots, self.recent = created_agents, slots, recent

    async def admit(self, request: Request):
        now = time.monotonic()
        while self.recent and self.recent[0] <= now - 60:
            self.recent.popleft()
        if self.slots.locked() or len(self.recent) >= 20:
            request.state.error_code = "busy"
            return JSONResponse({"error": "busy", "request_id": request.state.request_id},
                                status_code=429, headers={"Retry-After": "60"})
        self.recent.append(now)
        async with self.slots:
            return await self.execute(request)

    @staticmethod
    def error(request, status, code):
        request.state.error_code = code
        request_id = request.state.request_id
        return JSONResponse({"error": code, "request_id": request_id}, status_code=status,
                            headers={"X-Correlation-ID": request_id})

    async def read_json(self, request):
        """Return (data, None) for a bounded JSON body, or (None, error response)."""
        if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
            return None, self.error(request, 415, "json_required")
        try:
            body = await read_bounded_body(request, MAX_REQUEST_BYTES)
        except OverflowError:
            return None, self.error(request, 413, "request_too_large")
        except TimeoutError:
            return None, self.error(request, 408, "request_timeout")
        try:
            return json.loads(body), None
        except (ValueError, UnicodeError):
            return None, self.error(request, 400, "invalid_request")

    async def resolve(self, request, agent_id):
        """Return (agent, None) for a configured or ready created agent, or (None, error response)."""
        agent = self.registry.get(agent_id)
        if agent is not None:
            return agent, None
        try:
            agent = await self.created_agents.resolve_agent(agent_id)
        except Exception as problem:
            record_request_failure(request, problem, "cosmos")
            return None, self.error(request, 503, "agents_unavailable")
        return (agent, None) if agent is not None else (None, self.error(request, 400, "invalid_request"))

    async def execute(self, request: Request):
        if not request_allowed(request, self.settings.origins):
            return self.error(request, 403, "request_not_allowed")
        data, rejection = await self.read_json(request)
        if rejection is not None:
            return rejection
        prompt = chat_prompt(data, self.registry)
        if prompt is None:
            return self.error(request, 400, "invalid_request")
        if self.settings.mode == "preview":
            return self.error(request, 503, "preview_only")
        agent, rejection = await self.resolve(request, data["agent_id"])
        if rejection is not None:
            return rejection
        return await self.respond(request, agent, prompt, data.get("thread"))

    async def respond(self, request, agent, prompt, thread=None):
        request_id = request.state.request_id
        started = time.monotonic()
        try:
            async with asyncio.timeout(self.settings.timeout):
                status, text, output = await self.gateway.review(agent, prompt, thread=thread)
            if status != "completed" or not isinstance(text, str) or not text.strip():
                return self.error(request, 502, "incomplete_response")
            if len(text) > 100000 or len(json.dumps(output).encode("utf-8")) > 524288:
                return self.error(request, 502, "response_too_large")
            receipts = execution_receipts(output, agent["tools"])
            if len(receipts) > 32 or any(len(receipt["output"] or "") > 100000 for receipt in receipts):
                return self.error(request, 502, "response_too_large")
            return JSONResponse({"request_id": request_id, "status": status, "agent": agent["agent"],
                                 "text": text, "receipts": receipts, "elapsed_ms": round((time.monotonic() - started) * 1000)},
                                headers={"X-Correlation-ID": request_id})
        except TimeoutError as problem:
            record_request_failure(request, problem, "foundry")
            return self.error(request, 504, "timeout")
        except Exception as problem:
            record_request_failure(request, problem, "foundry")
            return self.error(request, 502, "backend_unavailable")


class DependencyMonitor:
    """Probe Foundry and Cosmos DB at startup and every minute for /api/health/dependencies."""

    def __init__(self, settings, gateway, agents, history_store):
        self.gateway, self.agents, self.history_store = gateway, agents, history_store
        self.status = {"status": "disabled" if settings.mode == "preview" else "starting"}

    @staticmethod
    async def check(operation, dependency):
        started = time.monotonic()
        try:
            async with asyncio.timeout(15):
                await operation()
            return "ready"
        except Exception as problem:
            LOGGER.warning(json.dumps({"event": "workbench_dependency_failed", "dependency": dependency,
                "error_type": type(problem).__name__,
                "elapsed_ms": round((time.monotonic() - started) * 1000)}))
            return "unavailable"

    async def probe(self):
        foundry, cosmos = await asyncio.gather(
            self.check(lambda: self.gateway.check(self.agents), "foundry"),
            self.check(self.history_store.check, "cosmos") if self.history_store is not None else asyncio.sleep(0, result="disabled"),
        )
        self.status.update(status="ready" if foundry == "ready" and cosmos in {"ready", "disabled"} else "degraded",
                           foundry=foundry, cosmos=cosmos)
        LOGGER.info(json.dumps({"event": "workbench_dependencies", **self.status}))

    async def monitor(self, stopped):
        while not stopped.is_set():
            try:
                await asyncio.wait_for(stopped.wait(), timeout=60)
            except TimeoutError:
                await self.probe()


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
    chat = ChatReviews(settings, registry, gateway, created_agents, slots, recent)
    dependencies = DependencyMonitor(settings, gateway, agents, history_store)

    @asynccontextmanager
    async def lifespan(application):
        stopped = asyncio.Event()
        monitor = None
        try:
            if settings.mode == "private":
                await dependencies.probe()
                monitor = asyncio.create_task(dependencies.monitor(stopped))
            yield
        finally:
            stopped.set()
            if monitor is not None:
                monitor.cancel()
                await asyncio.gather(monitor, return_exceptions=True)
            await review_runs.close()
            await created_agents.close()
            await gateway.close()
            if history_store is not None:
                await history_store.close()

    application = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    application.add_middleware(TrustedHostMiddleware, allowed_hosts=list(settings.hosts))

    @application.middleware("http")
    async def security_headers(request, call_next):
        started = time.monotonic()
        request.state.request_id = str(uuid4())
        try:
            response = await call_next(request)
        except Exception as problem:
            if not request.url.path.startswith("/api/"):
                raise
            record_request_failure(request, problem, "application")
            request.state.error_code = "internal_error"
            response = JSONResponse({"error": "internal_error", "request_id": request.state.request_id}, status_code=500)
        response.headers.update({"Cache-Control": cache_policy(request.url.path, response.status_code), **SECURITY_HEADERS})
        if settings.mode == "private":
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        if request.url.path.startswith("/api/"):
            response.headers["X-Correlation-ID"] = request.state.request_id
            route = getattr(request.scope.get("route"), "path", "unmatched")
            log = LOGGER.error if response.status_code >= 500 else LOGGER.info
            log(json.dumps({"event": "workbench_request", "request_id": request.state.request_id,
                "route": route, "method": request.method, "status": response.status_code,
                "outcome": getattr(request.state, "error_code", "completed" if response.status_code < 400 else "rejected"),
                **getattr(request.state, "failure", {}),
                "elapsed_ms": round((time.monotonic() - started) * 1000)}))
        return response

    @application.get("/healthz")
    async def health():
        return {"status": "ready", "mode": settings.mode}

    @application.get("/api/health/dependencies")
    async def dependency_health():
        return JSONResponse(dependencies.status, status_code=200 if dependencies.status["status"] == "ready" else 503)

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

    application.add_api_route("/api/reviews", chat.admit, methods=["POST"])
    application.include_router(history_router(settings, registry, history_store, created_agents))
    application.include_router(review_runs.router)
    application.include_router(created_agents.router)
    application.mount("/", StaticFiles(directory=ROOT / "static", html=True, check_dir=False), name="static")
    return application

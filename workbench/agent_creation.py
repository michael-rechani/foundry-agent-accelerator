import asyncio
import hashlib
import hmac
import json
import logging
import os
import re
import time
from collections import deque
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

from azure.core.exceptions import HttpResponseError
from azure.cosmos.exceptions import CosmosHttpResponseError
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import Field, ValidationError, field_validator

from agent_publisher import FoundryPublisher, PublicationError, resource_name, runtime_package
from agent_templates import (
    MODEL_PROFILES, TEMPLATES, TemplateRequiredError, catalog_facets, list_templates,
    model_profile, prepare_draft,
)
from history import StrictModel
from request_guard import BodyReadTimeout, MAX_SETUP_BYTES, read_bounded_body, record_request_failure, request_allowed


LOGGER = logging.getLogger("uvicorn.error")
UUID_PATTERN = r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}"
CREATED_ID = re.compile(r"created-" + UUID_PATTERN + r"\Z")
DEPLOYMENT_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")


def timestamp():
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class CreationSettings:
    enabled: bool = False
    model: str = ""
    key_sha256: str = ""
    max_agents: int = 5
    timeout_seconds: int = 600
    models: dict = field(default_factory=dict)

    @classmethod
    def from_env(cls):
        flag = os.getenv("WORKBENCH_AGENT_CREATION_ENABLED", "false")
        if flag not in {"true", "false"}:
            raise ValueError("WORKBENCH_AGENT_CREATION_ENABLED must be true or false")
        try:
            models = json.loads(os.getenv("WORKBENCH_AGENT_CREATION_MODELS") or "{}")
        except json.JSONDecodeError as problem:
            raise ValueError("WORKBENCH_AGENT_CREATION_MODELS must be a JSON object") from problem
        return cls(
            enabled=flag == "true",
            model=os.getenv("WORKBENCH_AGENT_CREATION_MODEL", ""),
            models=models,
            key_sha256=os.getenv("WORKBENCH_CREATION_KEY_SHA256", ""),
            max_agents=int(os.getenv("WORKBENCH_MAX_CREATED_AGENTS", "5")),
            timeout_seconds=int(os.getenv("WORKBENCH_PUBLICATION_TIMEOUT_SECONDS", "600")),
        )

    def validate(self, mode):
        if type(self.enabled) is not bool:
            raise ValueError("Agent creation enablement must be a boolean")
        if type(self.max_agents) is not int or not 1 <= self.max_agents <= 20:
            raise ValueError("Configure between one and twenty created agents")
        if type(self.timeout_seconds) is not int or not 30 <= self.timeout_seconds <= 900:
            raise ValueError("Publication timeout must be between 30 and 900 seconds")
        if self.key_sha256 and not re.fullmatch(r"[a-f0-9]{64}", self.key_sha256):
            raise ValueError("Configure a lowercase SHA-256 operator-key verifier")
        if not isinstance(self.models, dict) or any(
            profile not in MODEL_PROFILES or not isinstance(name, str) or not DEPLOYMENT_NAME.fullmatch(name)
            for profile, name in self.models.items()
        ):
            raise ValueError("Map only known model profiles to model deployment names")
        if self.enabled and (
            mode != "private"
            or not isinstance(self.model, str) or not DEPLOYMENT_NAME.fullmatch(self.model)
            or not re.fullmatch(r"[a-f0-9]{64}", self.key_sha256)
        ):
            raise ValueError("Creation requires private mode, a model deployment, and an operator-key SHA-256 verifier")

    def model_for(self, profile):
        return self.models.get(profile) or self.model


class DraftInput(StrictModel):
    goal: str = Field(min_length=10, max_length=1200)
    template_id: str | None = Field(default=None, max_length=64)


class CreateInput(StrictModel):
    idempotency_key: str = Field(pattern="^" + UUID_PATTERN + "$")
    template_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=80)
    instructions: str = Field(min_length=10, max_length=6000)
    confirm_cost: Literal[True]

    @field_validator("name")
    @classmethod
    def printable_name(cls, value):
        if not value.strip() or not value.isprintable():
            raise ValueError("Agent name must be printable")
        return value.strip()

    @field_validator("confirm_cost", mode="before")
    @classmethod
    def explicit_confirmation(cls, value):
        if value is not True:
            raise ValueError("Explicit cost confirmation is required")
        return value

    @field_validator("instructions")
    @classmethod
    def task_instructions(cls, value):
        if len(value.strip()) < 10 or "\x00" in value:
            raise ValueError("Describe the agent's task")
        return value.strip()

    @field_validator("template_id")
    @classmethod
    def known_template(cls, value):
        if value not in TEMPLATES:
            raise ValueError("Unknown agent template")
        return value


class AgentCreations:
    def __init__(self, settings, store, publisher=None):
        self.settings, self.store = settings, store
        self.config = settings.creation
        self.project = hashlib.sha256(settings.endpoint.encode("utf-8")).hexdigest()
        self.publisher = publisher or FoundryPublisher(settings.endpoint)
        self.tasks = {}
        self.operation_slot = asyncio.Semaphore(1)
        self.mutation_lock = asyncio.Lock()
        self.read_slots = asyncio.Semaphore(4)
        self.recent = deque()
        self.router = APIRouter()
        self.router.add_api_route("/api/agent-templates", self.templates, methods=["GET"])
        self.router.add_api_route("/api/agent-drafts", self.draft, methods=["POST"])
        self.router.add_api_route("/api/agents", self.collection, methods=["GET", "POST"])
        self.router.add_api_route("/api/agents/{identifier}", self.detail, methods=["GET", "DELETE"])
        self.router.add_api_route("/api/agents/{identifier}/resume", self.resume, methods=["POST"])

    @property
    def storage_enabled(self):
        return self.settings.mode == "private" and self.store is not None

    def capabilities(self):
        reason = ("local_preview" if self.settings.mode == "preview" else
                  "storage_unavailable" if self.store is None else
                  "not_enabled" if not self.config.enabled else None)
        return {
            "enabled": reason is None, "storage_enabled": self.storage_enabled, "reason": reason,
            "management_enabled": self.storage_enabled and bool(self.config.key_sha256),
            "requires_operator_key": True, "max_agents": self.config.max_agents,
            "publication_timeout_seconds": self.config.timeout_seconds,
            "model": self.config.model if self.config.enabled else None,
            "models": {profile: self.config.model_for(profile) for profile in MODEL_PROFILES}
            if self.config.enabled else None,
        }

    async def close(self):
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def storage(self, operation):
        async with asyncio.timeout(25):
            return await operation

    def error(self, request, status, code, **extra):
        request.state.error_code = code
        return JSONResponse(
            {"error": code, **extra}, status_code=status,
            headers={"Retry-After": "60"} if status == 429 else None,
        )

    def admit(self, request):
        if not request_allowed(request, self.settings.origins):
            return self.error(request, 403, "request_not_allowed")
        now = time.monotonic()
        while self.recent and self.recent[0] <= now - 60:
            self.recent.popleft()
        if len(self.recent) >= 120 or self.read_slots.locked():
            return self.error(request, 429, "agents_busy")
        self.recent.append(now)
        return None

    def authorize(self, request, *, creating):
        capability = "enabled" if creating else "management_enabled"
        if not self.capabilities()[capability]:
            return self.error(request, 503, "creation_disabled")
        key = request.headers.get("x-workbench-creation-key", "")
        if not 32 <= len(key) <= 256 or not hmac.compare_digest(
            hashlib.sha256(key.encode("utf-8")).hexdigest(), self.config.key_sha256,
        ):
            return self.error(request, 403, "operator_access_required")
        return None

    async def body(self, request, model):
        if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
            raise ValueError("JSON required")
        body = await read_bounded_body(request, MAX_SETUP_BYTES)
        return model.model_validate_json(body)

    async def templates(self, request: Request):
        rejection = self.admit(request)
        return rejection if rejection is not None else {
            "schema_version": 1,
            "templates": list_templates(),
            "facets": catalog_facets(),
            "draft_mode": "template",
        }

    async def draft(self, request: Request):
        rejection = self.admit(request)
        if rejection is not None:
            return rejection
        try:
            async with self.read_slots:
                data = await self.body(request, DraftInput)
                return prepare_draft(data.goal, data.template_id)
        except TemplateRequiredError as problem:
            return self.error(request, 400, "template_required", candidates=problem.candidates)
        except (ValidationError, ValueError):
            return self.error(request, 400, "invalid_setup")
        except OverflowError:
            return self.error(request, 413, "request_too_large")
        except TimeoutError:
            return self.error(request, 408, "request_timeout")

    def owned(self, document):
        return (
            document.get("kind") in {"created-agent", "deleted-agent"}
            and isinstance(document.get("id"), str) and CREATED_ID.fullmatch(document["id"])
            and document.get("project") == self.project
            and document.get("runtime_name") == resource_name(document["id"])
            and isinstance(document.get("template"), dict)
            and document["template"].get("id") == document.get("template_id")
        )

    def effective_status(self, document):
        if document["status"] in {"creating", "deleting"} and document["id"] not in self.tasks:
            return "interrupted"
        return document["status"]

    def catalog_agent(self, document):
        template = document["template"]
        return {
            "id": document["id"], "label": document["name"], "category": "Created in this Lab",
            "description": template["description"], "agent": document["runtime_name"],
            "tools": {tool["name"]: document["runtime_name"] for tool in template["tools"]},
            "prompts": [{"label": "Try a fictional example", "text": template["sample_input"]}],
            "guidance": {
                "input": template["input"], "output": template["output"],
                "limits": template["limits"], "delegation": template["delegation"],
                "configuration": (
                    "This agent uses the saved setup in Created agents, published as a named Foundry hosted version. "
                    "Task instructions were chosen before creation; tools and runtime code come from the reviewed "
                    "Lab template. A chat message does not edit the deployed setup."
                ),
            },
        }

    def public(self, document):
        result = {key: deepcopy(document[key]) for key in (
            "id", "name", "template_id", "instructions", "runtime_name", "version", "status", "stage",
            "created_at", "updated_at", "_etag", "error", "events", "operation", "model", "runtime_hash",
        )}
        result["template_label"] = document["template"]["label"]
        result["model_profile"] = deepcopy(document.get("model_profile"))
        result["status"] = self.effective_status(document)
        if result["status"] == "interrupted" and document["status"] != "interrupted":
            result.update(stage="interrupted", error="publication_unconfirmed")
        result["agent"] = self.catalog_agent(document) if result["status"] == "ready" else None
        return result

    async def records(self):
        if not self.storage_enabled:
            return []
        documents = await self.storage(self.store.list_created_agents(self.project))
        return [document for document in documents if self.owned(document) and document["status"] != "deleted"]

    async def ready_ids(self):
        return [document["id"] for document in await self.records() if document["status"] == "ready"]

    async def resolve_agent(self, identifier):
        if not CREATED_ID.fullmatch(identifier) or not self.storage_enabled:
            return None
        try:
            document = await self.storage(self.store.get(identifier))
        except CosmosHttpResponseError as problem:
            if problem.status_code == 404:
                return None
            raise
        if not self.owned(document) or document["status"] != "ready":
            return None
        return self.catalog_agent(document)

    async def resume(self, request: Request, identifier: str):
        return await self.handle(request, identifier, resume=True)

    async def collection(self, request: Request):
        return await self.handle(request)

    async def detail(self, request: Request, identifier: str):
        return await self.handle(request, identifier)

    async def handle(self, request, identifier=None, resume=False):
        rejection = self.admit(request)
        if rejection is not None:
            return rejection
        if not self.storage_enabled:
            return self.error(request, 503, "agents_unavailable")
        if identifier and not CREATED_ID.fullmatch(identifier):
            return self.error(request, 404, "agent_not_found")
        if request.method != "GET":
            rejection = self.authorize(request, creating=identifier is None or resume)
            if rejection is not None:
                return rejection
        try:
            async with self.read_slots, asyncio.timeout(35):
                return await self.dispatch(request, identifier, resume)
        except (ValidationError, ValueError):
            return self.error(request, 400, "invalid_setup")
        except OverflowError:
            return self.error(request, 413, "request_too_large")
        except CosmosHttpResponseError as problem:
            if problem.status_code not in {404, 409, 412}:
                record_request_failure(request, problem, "cosmos")
            return self.error(request, 404 if problem.status_code == 404 else 409 if problem.status_code in {409, 412} else 503,
                              "agent_not_found" if problem.status_code == 404 else
                              "agent_changed" if problem.status_code in {409, 412} else "agents_unavailable")
        except BodyReadTimeout:
            return self.error(request, 408, "request_timeout")
        except TimeoutError as problem:
            record_request_failure(request, problem, "cosmos")
            return self.error(request, 504, "agents_timeout")
        except Exception as problem:
            record_request_failure(request, problem, "cosmos")
            return self.error(request, 503, "agents_unavailable")

    async def dispatch(self, request, identifier, resume):
        if request.method == "GET" and identifier is None:
            return {"items": [self.public(document) for document in await self.records()],
                    "limit": self.config.max_agents}
        if request.method == "GET":
            document = await self.storage(self.store.get(identifier))
            if not self.owned(document):
                return self.error(request, 404, "agent_not_found")
            return self.public(document)
        async with self.mutation_lock:
            if identifier is None:
                data = await self.body(request, CreateInput)
                return await self.create(request, data)
            return await self.change(request, identifier, resume)

    async def change(self, request, identifier, resume):
        document = await self.storage(self.store.get(identifier))
        if not self.owned(document):
            return self.error(request, 404, "agent_not_found")
        if request.headers.get("if-match") != document["_etag"]:
            return self.error(request, 409, "agent_changed")
        if identifier in self.tasks:
            return self.error(request, 409, "agent_operation_running")
        if document["status"] == "deleted":
            return self.public(document)
        if resume and (self.effective_status(document) not in {"interrupted", "failed"}
                       or document["operation"] == "delete"):
            return self.error(request, 409, "agent_not_resumable")
        if self.operation_slot.locked():
            return self.error(request, 429, "agents_busy")
        operation = "resume" if resume else "delete"
        await self.operation_slot.acquire()
        try:
            document.update(
                status="creating" if resume else "deleting",
                stage="queued" if resume else "deleting", error=None,
                updated_at=timestamp(), operation=operation,
            )
            document = await self.storage(self.store.replace(document, document["_etag"]))
            self.start(document, operation)
        except BaseException:
            self.operation_slot.release()
            raise
        return JSONResponse(self.public(document), status_code=202)

    async def create(self, request, data):
        identifier = "created-" + data.idempotency_key
        setup = {"template_id": data.template_id, "name": data.name, "instructions": data.instructions}
        digest = hashlib.sha256(json.dumps(setup, sort_keys=True).encode("utf-8")).hexdigest()
        try:
            existing = await self.storage(self.store.get(identifier))
        except CosmosHttpResponseError as problem:
            if problem.status_code != 404:
                raise
        else:
            if not self.owned(existing) or existing["setup_hash"] != digest:
                return self.error(request, 409, "agent_changed")
            return JSONResponse(self.public(existing))
        if self.operation_slot.locked():
            return self.error(request, 429, "agents_busy")
        if len(await self.records()) >= self.config.max_agents:
            return self.error(request, 409, "agent_limit_reached")
        _, bundle_hash = runtime_package()
        profile = model_profile(TEMPLATES[data.template_id]["model_profile"])
        template = {key: deepcopy(TEMPLATES[data.template_id][key]) for key in (
            "id", "label", "description", "input", "output", "limits", "delegation", "sample_input", "tools",
        )}
        now = timestamp()
        document = {
            **setup, "id": identifier, "kind": "created-agent", "workspace": "shared", "project": self.project,
            "setup_hash": digest, "runtime_hash": bundle_hash, "runtime_name": resource_name(identifier),
            "model": self.config.model_for(profile["id"]), "model_profile": profile, "template": template, "version": None, "publication_started": False,
            "status": "creating", "stage": "queued", "operation": "create", "created_at": now, "updated_at": now,
            "error": None, "events": [{"name": "queued", "at": now}], "ttl": -1,
        }
        await self.operation_slot.acquire()
        try:
            saved = await self.storage(self.store.create(document))
            self.start(saved, "create")
        except BaseException:
            self.operation_slot.release()
            raise
        return JSONResponse(self.public(saved), status_code=202)

    def start(self, document, operation):
        self.tasks[document["id"]] = asyncio.create_task(self.execute(document, operation))

    async def execute(self, document, operation):
        identifier = document["id"]

        async def progress(stage, **changes):
            updated = {
                **document, **changes, "stage": stage, "updated_at": timestamp(),
                "events": [*document["events"], {"name": stage, "at": timestamp()}][-32:],
            }
            if changes.get("status") == "deleted":
                updated.update(kind="deleted-agent", name="Deleted agent", instructions="", ttl=-1)
            saved = await self.storage(self.store.replace(updated, document["_etag"]))
            document.clear()
            document.update(saved)

        async def fail(code, status="failed", service_error=None):
            entry = {"event": "agent_publication_failed", "agent_id": identifier,
                     "operation": operation, "error": code}
            if service_error:
                entry["service_error"] = service_error
            LOGGER.warning(json.dumps(entry))
            try:
                await progress(status, status=status, error=code)
            except Exception as problem:
                LOGGER.error(json.dumps({"event": "agent_state_unconfirmed", "agent_id": identifier,
                                         "type": type(problem).__name__}))

        try:
            async with asyncio.timeout(self.config.timeout_seconds):
                await getattr(self.publisher, operation)(document, progress)
        except asyncio.CancelledError:
            await fail("publication_unconfirmed", "interrupted")
            raise
        except TimeoutError:
            await fail("deletion_unconfirmed" if operation == "delete" else "publication_timeout", "interrupted")
        except PublicationError as problem:
            await fail(problem.code, "interrupted" if problem.code in {
                "publication_unconfirmed", "deletion_unconfirmed",
            } else "failed", problem.service_error)
        except HttpResponseError as problem:
            await fail("operator_permissions_required" if problem.status_code in {401, 403}
                       else "publication_unconfirmed", "interrupted")
        except Exception as problem:
            LOGGER.error(json.dumps({"event": "agent_publisher_error", "agent_id": identifier,
                                     "type": type(problem).__name__}))
            await fail("deletion_unconfirmed" if operation == "delete" else "publication_unconfirmed", "interrupted")
        finally:
            self.tasks.pop(identifier, None)
            self.operation_slot.release()

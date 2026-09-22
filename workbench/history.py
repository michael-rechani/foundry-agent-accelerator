import asyncio
import os
from collections import deque
from copy import deepcopy
from datetime import datetime, timezone
from time import monotonic
from typing import Literal
from uuid import uuid4

from azure.core import MatchConditions
from azure.cosmos.aio import CosmosClient
from azure.cosmos.exceptions import CosmosHttpResponseError
from azure.identity.aio import ManagedIdentityCredential
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Receipt(StrictModel):
    tool: str = Field(max_length=128)
    call_id: str | None = Field(max_length=256)
    verified: bool
    agent: str | None = Field(max_length=128)
    output: str | None = Field(max_length=100000)


class Result(StrictModel):
    request_id: str = Field(min_length=1, max_length=128)
    status: Literal["completed"] = "completed"
    agent: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=100000)
    receipts: list[Receipt] = Field(max_length=32)
    elapsed_ms: int = Field(ge=0)


class Turn(StrictModel):
    question: str = Field(min_length=1, max_length=60000)
    result: Result


class Conversation(StrictModel):
    agent_id: str = Field(min_length=1, max_length=64)
    turns: list[Turn] = Field(min_length=1, max_length=11)


class CosmosHistory:
    def __init__(self, endpoint):
        self.credential = ManagedIdentityCredential(client_id=os.getenv("AZURE_CLIENT_ID"))
        self.client = CosmosClient(endpoint, credential=self.credential, connection_timeout=10, timeout=15, retry_total=2)
        self.container = self.client.get_database_client("workbench").get_container_client("conversations")

    async def close(self):
        await self.client.close()
        await self.credential.close()

    async def check(self):
        await self.list([], None)

    async def list(self, agents, cursor):
        query = self.container.query_items(
            query="SELECT c.id, c.title, c.agent_id, c.updated_at FROM c WHERE NOT IS_DEFINED(c.kind) AND ARRAY_CONTAINS(@agents, c.agent_id) ORDER BY c.updated_at DESC",
            parameters=[{"name": "@agents", "value": list(agents)}], partition_key="shared", max_item_count=20)
        pages = query.by_page(continuation_token=cursor)
        page = await anext(pages, None)
        items = [item async for item in page] if page is not None else []
        return {"items": items, "cursor": pages.continuation_token}

    async def list_reviews(self, agents, cursor):
        query = self.container.query_items(
            query="SELECT c.id, c.title, c.agent_id, c.updated_at, c.status FROM c WHERE c.kind = 'review' AND ARRAY_CONTAINS(@agents, c.agent_id) ORDER BY c.updated_at DESC",
            parameters=[{"name": "@agents", "value": list(agents)}], partition_key="shared", max_item_count=20)
        pages = query.by_page(continuation_token=cursor)
        page = await anext(pages, None)
        items = [item async for item in page] if page is not None else []
        return {"items": items, "cursor": pages.continuation_token}

    async def list_created_agents(self, project):
        items = self.container.query_items(
            query="SELECT * FROM c WHERE c.kind = 'created-agent' ORDER BY c.updated_at DESC",
            partition_key="shared", max_item_count=20)
        return [item async for item in items if item.get("project") == project]

    async def get(self, identifier):
        return await self.container.read_item(identifier, partition_key="shared")

    async def create(self, document):
        return await self.container.create_item(document)

    async def replace(self, document, etag):
        return await self.container.replace_item(document["id"], document, etag=etag, match_condition=MatchConditions.IfNotModified)

    async def delete(self, identifier, etag):
        await self.container.delete_item(identifier, partition_key="shared", etag=etag, match_condition=MatchConditions.IfNotModified)


def unverified_turns(turns):
    result = deepcopy(turns)
    for turn in result:
        for receipt in turn["result"]["receipts"]:
            receipt["verified"] = False
    return result


def history_router(settings, registry, store, created_agents=None):
    router = APIRouter()
    semaphore = asyncio.Semaphore(4)
    recent = deque()

    async def resolve(identifier):
        if identifier in registry:
            return registry[identifier]
        return await created_agents.resolve_agent(identifier) if created_agents is not None else None

    @router.api_route("/api/conversations", methods=["GET", "POST"])
    @router.api_route("/api/conversations/{identifier}", methods=["GET", "PUT", "DELETE"])
    async def conversations(request: Request, identifier: str | None = None):
        now = monotonic()
        while recent and now - recent[0] >= 60:
            recent.popleft()
        if semaphore.locked() or len(recent) >= 60:
            request.state.error_code = "history_busy"
            return JSONResponse({"error": "history_busy", "request_id": request.state.request_id},
                                status_code=429, headers={"Retry-After": "60"})
        recent.append(now)
        async with semaphore:
            try:
                async with asyncio.timeout(35):
                    return await execute(request, identifier)
            except TimeoutError:
                request.state.error_code = "history_timeout"
                return JSONResponse({"error": "history_timeout", "request_id": request.state.request_id}, status_code=504)

    async def execute(request: Request, identifier: str | None):
        def error(status, code):
            request.state.error_code = code
            return JSONResponse({"error": code, "request_id": request.state.request_id}, status_code=status)

        if (request.headers.get("x-workbench-request") != "1" or
                request.headers.get("sec-fetch-site") == "cross-site" or
                request.headers.get("origin") not in (None, *settings.origins)):
            return error(403, "request_not_allowed")
        if store is None:
            return error(503, "history_disabled")
        if identifier is not None and (len(identifier) != 36 or any(char not in "0123456789abcdef-" for char in identifier)):
            return error(400, "invalid_conversation")
        try:
            if request.method == "GET" and identifier is None:
                cursor = request.query_params.get("cursor")
                if cursor and len(cursor) > 8192:
                    return error(400, "invalid_cursor")
                identifiers = list(registry)
                if created_agents is not None:
                    identifiers.extend(await created_agents.ready_ids())
                return await store.list(identifiers, cursor)
            existing = await store.get(identifier) if identifier else None
            if existing and (existing.get("kind") is not None or not await resolve(existing["agent_id"])):
                return error(404, "conversation_not_found")
            if request.method == "GET":
                document = {key: existing[key] for key in ("id", "title", "agent_id", "turns", "updated_at", "_etag")}
                document["turns"] = unverified_turns(document["turns"])
                return document
            if existing and request.headers.get("if-match") != existing["_etag"]:
                return error(409, "conversation_changed")
            if request.method == "DELETE":
                await store.delete(identifier, existing["_etag"])
                return {"deleted": True}
            if request.headers.get("content-type", "").split(";")[0] != "application/json":
                return error(415, "json_required")
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > 524288:
                    return error(413, "conversation_too_large")
            conversation = Conversation.model_validate_json(body)
            agent = await resolve(conversation.agent_id)
            if agent is None or any(turn.result.agent != agent["agent"] for turn in conversation.turns):
                return error(400, "invalid_conversation")
            if existing and existing["agent_id"] != conversation.agent_id:
                return error(400, "invalid_conversation")
            document = {**conversation.model_dump(), "id": identifier or str(uuid4()), "workspace": "shared",
                        "title": conversation.turns[0].question.strip()[:80],
                        "updated_at": datetime.now(timezone.utc).isoformat(), "ttl": 2592000}
            document["turns"] = unverified_turns(document["turns"])
            saved = await store.replace(document, existing["_etag"]) if existing else await store.create(document)
            return {"id": saved["id"], "_etag": saved["_etag"], "updated_at": saved["updated_at"]}
        except ValidationError:
            return error(400, "invalid_conversation")
        except CosmosHttpResponseError as problem:
            return error(404 if problem.status_code == 404 else 409 if problem.status_code == 412 else 503,
                         "conversation_not_found" if problem.status_code == 404 else "conversation_changed" if problem.status_code == 412 else "history_unavailable")
        except Exception:
            return error(503, "history_unavailable")

    return router
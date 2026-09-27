import asyncio
import json
import logging
import re
import time
from collections import deque
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from azure.cosmos.exceptions import CosmosHttpResponseError
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from request_guard import BodyReadTimeout, MAX_REQUEST_BYTES, read_bounded_body, record_request_failure, request_allowed
from reviews import Evidence, ReviewInput, review_prompt, validate_result

LOGGER = logging.getLogger("uvicorn.error")

# Allow the admission write, final write, and shutdown to finish before recovery.
RECOVERY_GRACE_SECONDS = 90
LEGACY_TIMEOUT_SECONDS = 180
REVIEW_ID = re.compile(r"review-[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}")


def timestamp():
    return datetime.now(timezone.utc).isoformat()


class ReviewRuns:
    def __init__(self, settings, registry, store, gateway, receipts, slots, recent):
        self.settings, self.registry, self.store = settings, registry, store
        self.gateway, self.receipts, self.slots, self.recent = gateway, receipts, slots, recent
        self.tasks = {}
        self.router = APIRouter()
        self.router.add_api_route("/api/review-runs", self.handle, methods=["GET", "POST"])
        self.router.add_api_route("/api/review-runs/{identifier}", self.handle, methods=["GET"])
        self.router.add_api_route("/api/review-runs/{identifier}/{action}", self.handle, methods=["POST"])
        self.requests = deque()
        self.read_slots = asyncio.Semaphore(4)

    async def close(self):
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def storage(self, operation):
        async with asyncio.timeout(25):
            return await operation

    def public_status(self, document):
        if document["status"] == "running" and document["id"] not in self.tasks:
            deadline = document.get("recovery_after")
            if deadline:
                recovery_after = datetime.fromisoformat(deadline)
            else:
                recovery_after = datetime.fromisoformat(document["updated_at"]) + timedelta(
                    seconds=LEGACY_TIMEOUT_SECONDS + RECOVERY_GRACE_SECONDS)
            if datetime.now(timezone.utc) >= recovery_after:
                return "interrupted"
        return document["status"]

    def public(self, document):
        result = {key: deepcopy(document[key]) for key in (
            "id", "title", "agent_id", "criteria", "evidence", "status", "runs", "updated_at", "_etag")}
        result["status"] = self.public_status(document)
        return result

    def error(self, request, status, code):
        request.state.error_code = code
        return JSONResponse({"error": code}, status_code=status,
                            headers={"Retry-After": "60"} if status == 429 else None)

    async def handle(self, request: Request, identifier: str | None = None, action: str | None = None):
        if not request_allowed(request, self.settings.origins):
            return self.error(request, 403, "request_not_allowed")
        if self.settings.mode == "preview" or self.store is None:
            return self.error(request, 503, "reviews_disabled")
        if identifier and not REVIEW_ID.fullmatch(identifier):
            return self.error(request, 400, "invalid_review")
        if action not in {None, "execute", "resume", "evidence"}:
            return self.error(request, 404, "not_found")
        now = time.monotonic()
        while self.requests and self.requests[0] <= now - 60:
            self.requests.popleft()
        if len(self.requests) >= 120 or self.read_slots.locked():
            return self.error(request, 429, "reviews_busy")
        self.requests.append(now)
        try:
            async with self.read_slots, asyncio.timeout(35):
                return await self.dispatch(request, identifier, action, now)
        except (ValidationError, ValueError):
            return self.error(request, 400, "invalid_review")
        except OverflowError:
            return self.error(request, 413, "request_too_large")
        except CosmosHttpResponseError as problem:
            if problem.status_code not in {404, 412}:
                record_request_failure(request, problem, "cosmos")
            return self.error(request, 404 if problem.status_code == 404 else 409 if problem.status_code == 412 else 503,
                              "not_found" if problem.status_code == 404 else "review_changed" if problem.status_code == 412 else "reviews_unavailable")
        except BodyReadTimeout:
            return self.error(request, 408, "request_timeout")
        except TimeoutError as problem:
            record_request_failure(request, problem, "cosmos")
            return self.error(request, 504, "reviews_timeout")
        except Exception as problem:
            record_request_failure(request, problem, "cosmos")
            return self.error(request, 503, "reviews_unavailable")

    async def dispatch(self, request, identifier, action, now):
        if request.method == "GET" and not identifier:
            return await self.list_page(request)
        document = await self.store.get(identifier) if identifier else None
        if document and (document.get("kind") != "review" or document["agent_id"] not in self.registry):
            return self.error(request, 404, "not_found")
        if request.method == "GET":
            return self.public(document)
        if document and request.headers.get("if-match") != document["_etag"]:
            return self.error(request, 409, "review_changed")
        body = None
        if action != "execute":
            if request.headers.get("content-type", "").split(";")[0] != "application/json":
                return self.error(request, 415, "json_required")
            body = await self.read_body(request)
        if action in {"execute", "resume"}:
            return await self.start(request, identifier, document, body, now, recovering=action == "resume")
        if action == "evidence":
            return await self.add_evidence(request, document, body)
        return await self.create(request, body)

    async def read_body(self, request):
        return await read_bounded_body(request, MAX_REQUEST_BYTES)

    async def list_page(self, request):
        cursor = request.query_params.get("cursor")
        if cursor and len(cursor) > 8192:
            return self.error(request, 400, "invalid_cursor")
        page = await self.store.list_reviews(self.registry, cursor)
        return {**page, "items": [
            {**{key: item[key] for key in ("id", "title", "agent_id", "updated_at")},
             "status": self.public_status(item)} for item in page["items"]]}

    def snapshot(self, request, identifier, document, body, recovering):
        """Return (input snapshot, previous run) for a start or resume, or an error response."""
        previous = document["runs"][-1] if document["runs"] else None
        if not recovering:
            if document["status"] != "draft" or len(document["runs"]) >= 4:
                return self.error(request, 409, "review_not_runnable"), None
            return {key: deepcopy(document[key]) for key in ("title", "agent_id", "criteria", "evidence")}, None
        if (self.public_status(document) != "interrupted" or identifier in self.tasks
                or not previous or not isinstance(previous.get("input"), dict)
                or len(document["runs"]) >= 4):
            return self.error(request, 409, "review_not_resumable"), None
        confirmation = json.loads(body)
        if (not isinstance(confirmation, dict) or set(confirmation) != {"confirm_cost"}
                or confirmation["confirm_cost"] is not True):
            return self.error(request, 400, "recovery_confirmation_required"), None
        snapshot = ReviewInput.model_validate(previous["input"]).model_dump()
        if snapshot["agent_id"] != document["agent_id"]:
            return self.error(request, 409, "review_not_resumable"), None
        return snapshot, previous

    async def start(self, request, identifier, document, body, now, recovering):
        snapshot, previous = self.snapshot(request, identifier, document, body, recovering)
        if isinstance(snapshot, JSONResponse):
            return snapshot
        while self.recent and self.recent[0] <= now - 60:
            self.recent.popleft()
        if self.slots.locked() or len(self.recent) >= 20:
            return self.error(request, 429, "busy")
        self.recent.append(now)
        await self.slots.acquire()
        try:
            if recovering:
                previous["error"] = "execution_interrupted"
                if not any(event["name"] == "interrupted" for event in previous["events"]):
                    previous["events"].append({"name": "interrupted", "at": timestamp()})
            document["status"] = "running"
            document["updated_at"] = timestamp()
            document["recovery_after"] = (
                datetime.now(timezone.utc)
                + timedelta(seconds=self.settings.timeout + RECOVERY_GRACE_SECONDS)
            ).isoformat()
            document["runs"].append({"id": str(uuid4()), "started_at": timestamp(),
                                     "events": [{"name": "review_recovery_requested" if recovering else "review_started",
                                                 "at": timestamp()}],
                                     "input": snapshot,
                                     **({"resumed_from": previous["id"]} if recovering else {})})
            saved = await self.store.replace(document, document["_etag"])
            self.tasks[identifier] = asyncio.create_task(self.execute(saved))
        except BaseException:
            self.slots.release()
            raise
        return JSONResponse(self.public(saved), status_code=202)

    async def add_evidence(self, request, document, body):
        if document["status"] != "waiting_input" or len(document["runs"]) >= 4:
            return self.error(request, 409, "review_not_waiting")
        source = Evidence.model_validate_json(body)
        review = ReviewInput.model_validate({key: document[key] for key in ("title", "agent_id", "criteria", "evidence")})
        review = ReviewInput.model_validate({**review.model_dump(), "evidence": [*review.model_dump()["evidence"], source.model_dump()]})
        document.update(evidence=review.model_dump()["evidence"], status="draft", updated_at=timestamp())
        return self.public(await self.store.replace(document, document["_etag"]))

    async def create(self, request, body):
        review = ReviewInput.model_validate_json(body)
        if review.agent_id not in self.registry:
            return self.error(request, 400, "invalid_agent")
        document = {**review.model_dump(), "id": "review-" + str(uuid4()), "kind": "review",
                    "workspace": "shared", "status": "draft", "runs": [], "updated_at": timestamp(), "ttl": 2592000}
        return JSONResponse(self.public(await self.store.create(document)), status_code=201)

    async def execute(self, document):
        started = time.monotonic()
        run = document["runs"][-1]
        agent = self.registry[document["agent_id"]]
        try:
            review = ReviewInput.model_validate(run["input"])
            async with asyncio.timeout(self.settings.timeout):
                status, text, output = await self.gateway.review(agent, review_prompt(review))
            if status != "completed" or not isinstance(text, str) or len(text.encode("utf-8")) > 100000 or len(json.dumps(output).encode()) > 524288:
                raise ValueError("Invalid response")
            receipts = self.receipts(output, agent["tools"])
            if len(receipts) > 32 or (agent["tools"] and (not receipts or any(not receipt["verified"] for receipt in receipts))):
                raise ValueError("Missing verified specialist execution")
            run["receipts"] = [{key: receipt[key] for key in ("tool", "call_id", "agent", "verified")} for receipt in receipts]
            if receipts:
                run["events"].append({"name": "specialist_receipts_checked", "at": timestamp()})
            run["result"] = validate_result(text, review)
            run["events"].append({"name": "citations_checked", "at": timestamp()})
            document["status"] = "waiting_input" if run["result"]["questions"] else "completed"
        except asyncio.CancelledError:
            document["status"] = "interrupted"
            run["error"] = "execution_interrupted"
        except TimeoutError:
            document["status"] = "failed"
            run["error"] = "agent_timeout"
        except (ValueError, ValidationError):
            document["status"] = "failed"
            run["error"] = "invalid_agent_result"
        except Exception:
            document["status"] = "failed"
            run["error"] = "agent_unavailable"
        finally:
            run["elapsed_ms"] = round((time.monotonic() - started) * 1000)
            run["events"].append({"name": document["status"], "at": timestamp()})
            document["updated_at"] = timestamp()
            try:
                await self.storage(self.store.replace(document, document["_etag"]))
            except Exception:
                LOGGER.warning(json.dumps({"event": "review_persistence_failed", "review_id": document["id"]}))
            finally:
                LOGGER.info(json.dumps({"event": "review_execution", "review_id": document["id"],
                                        "status": document["status"], "elapsed_ms": run["elapsed_ms"]}))
                self.tasks.pop(document["id"], None)
                self.slots.release()
"""Design loop routes: draft test cases for task instructions, and run one draft case without publishing.

Both routes call the model deployment directly through the library preview path, so nothing is published
or stored. A model may write only the draft's task instructions and test cases. The fixed policy, the
template's tools and the checks' vocabulary stay as they are, and a person reads every answer.
"""
import asyncio
import json
import logging
import time
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import Field, ValidationError, field_validator

from agent_runtime.main import DEMO_POLICY
from agent_templates import TEMPLATES
from case_scoring import score
from draft_cases import CASE_WRITER_INSTRUCTIONS, CaseDraftError, case_problems, case_prompt, parse_cases
from history import StrictModel
from library_preview import DESIGNER_ID, summarize_usage, preview_agent
from model_budget import ModelBudgetWait, estimate_input_tokens
from request_guard import MAX_SETUP_BYTES, RequestRejected, api_error, read_json_body, record_request_failure, request_allowed

LOGGER = logging.getLogger("uvicorn.error")


class Instructions(StrictModel):
    instructions: str = Field(min_length=10, max_length=6000)
    template_id: str | None = Field(default=None, max_length=64)
    confirm_cost: Literal[True]

    @field_validator("instructions")
    @classmethod
    def task_instructions(cls, value):
        if len(value.strip()) < 10 or "\x00" in value:
            raise ValueError("Describe the agent's task")
        return value.strip()


class CaseDraftInput(Instructions):
    pass


class RunInput(Instructions):
    template_id: str = Field(min_length=1, max_length=64)
    case: dict


class DesignLoop:
    """POST /api/agent-test-cases writes cases for instructions; POST /api/agent-test-runs runs and screens one."""

    def __init__(self, settings, gateway, receipts, retry_after_seconds, gate, budgets):
        self.settings, self.gateway, self.receipts = settings, gateway, receipts
        self.retry_after_seconds, self.gate, self.budgets = retry_after_seconds, gate, budgets
        self.router = APIRouter()
        self.router.add_api_route("/api/agent-test-cases", self.draft_cases, methods=["POST"])
        self.router.add_api_route("/api/agent-test-runs", self.run_case, methods=["POST"])

    @staticmethod
    def error(request, status, code, retry_after=None, **extra):
        return api_error(request, status, code, retry_after=retry_after, **extra)

    async def admitted(self, request, handler, model):
        if not request_allowed(request, self.settings.origins):
            return self.error(request, 403, "request_not_allowed")
        if not self.settings.library_preview_enabled:
            return self.error(request, 503, "library_preview_disabled")
        if not self.gate.try_admit():
            return self.error(request, 429, "busy", 60)
        async with self.gate.slots:
            try:
                body = await read_json_body(request, MAX_SETUP_BYTES, wrong_type=(400, "invalid_setup"))
                data = model.model_validate_json(body)
            except RequestRejected as problem:
                return self.error(request, problem.status, problem.code)
            except ValidationError:
                return self.error(request, 400, "invalid_setup")
            return await handler(request, data)

    def template_agent(self, template_id):
        """The preview binding for a finished library template, or None."""
        return preview_agent(f"library-{template_id}", self.settings.unfinished_agents)

    async def ask(self, request, agent, prompt, instructions):
        """Return ((text, output, usage, elapsed_ms), None) or (None, an error response) for one admitted model run."""
        usage, started = [], time.monotonic()
        deployment = self.settings.creation.model_for(agent["model_profile"])

        def admit_model_call(payload):
            wait = self.budgets.try_admit(deployment, agent["template_id"], input_tokens=estimate_input_tokens(payload))
            if wait:
                LOGGER.info(json.dumps({"event": "workbench_model_busy", "deployment": deployment,
                                        "template_id": agent["template_id"], "retry_after": wait}))
                raise ModelBudgetWait(wait)

        try:
            async with asyncio.timeout(self.settings.timeout):
                status, text, output = await self.gateway.preview(
                    agent, prompt, usage=usage, admit_model_call=admit_model_call, instructions=instructions)
        except ModelBudgetWait as problem:
            return None, self.error(request, 429, "busy", problem.retry_after)
        except TimeoutError as problem:
            record_request_failure(request, problem, "foundry")
            return None, self.error(request, 504, "timeout")
        except Exception as problem:
            record_request_failure(request, problem, "foundry")
            if getattr(problem, "status_code", None) == 429:
                return None, self.error(request, 429, "busy", self.retry_after_seconds(problem))
            return None, self.error(request, 502, "backend_unavailable")
        if status != "completed" or not isinstance(text, str) or not text.strip():
            return None, self.error(request, 502, "incomplete_response")
        if len(text) > 100000 or len(json.dumps(output).encode("utf-8")) > 524288:
            return None, self.error(request, 502, "response_too_large")
        return (text, output, usage, round((time.monotonic() - started) * 1000)), None

    async def draft_cases(self, request: Request):
        return await self.admitted(request, self.write_cases, CaseDraftInput)

    async def write_cases(self, request, data):
        agent = self.template_agent(data.template_id) if data.template_id else None
        if data.template_id and agent is None:
            return self.error(request, 400, "invalid_setup")
        template = TEMPLATES[agent["template_id"]] if agent else None
        writer = preview_agent(DESIGNER_ID, include_unfinished=False)
        result, rejection = await self.ask(request, writer, case_prompt(data.instructions, template),
                                           CASE_WRITER_INSTRUCTIONS)
        if rejection is not None:
            return rejection
        text, _, usage, elapsed = result
        try:
            cases, rejected = parse_cases(text, tuple(agent["tools"]) if agent else ())
        except CaseDraftError:
            return self.error(request, 502, "cases_unusable")
        return {"request_id": request.state.request_id, "template_id": data.template_id, "cases": cases,
                "rejected": rejected, "elapsed_ms": elapsed, "usage": summarize_usage(usage)}

    async def run_case(self, request: Request):
        return await self.admitted(request, self.run_one, RunInput)

    async def run_one(self, request, data):
        agent = self.template_agent(data.template_id)
        if agent is None:
            return self.error(request, 400, "invalid_setup")
        problems = case_problems(data.case, tuple(agent["tools"]))
        if problems:
            return self.error(request, 400, "invalid_case", problems=problems)
        result, rejection = await self.ask(request, agent, data.case["input"], DEMO_POLICY + data.instructions)
        if rejection is not None:
            return rejection
        text, output, usage, elapsed = result
        receipts = self.receipts(output, agent["tools"])
        if len(receipts) > 32 or any(len(receipt["output"] or "") > 100000 for receipt in receipts):
            return self.error(request, 502, "response_too_large")
        passed, failures = score(data.case, text, receipts)
        return {"request_id": request.state.request_id, "case_id": data.case["id"], "passed": passed,
                "failures": failures, "text": text, "receipts": receipts, "elapsed_ms": elapsed,
                "usage": summarize_usage(usage)}

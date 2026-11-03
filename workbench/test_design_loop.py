import json
import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from agent_creation import CreationSettings
from agent_runtime.main import DEMO_POLICY
from agent_templates import TASK_MARKER
from app import Settings, create_app
from draft_cases import CASE_WRITER_INSTRUCTIONS
from draft_revision import REVISER_INSTRUCTIONS
from log_capture import CapturedLabLogs

INSTRUCTIONS = "Summarize the notice and list what the reader should ask before acting on it."
CASE = {"id": "grounded-one", "category": "grounded", "input": "Sample notice: hours change to 8:00 on Monday.",
        "checks": {"must_include": ["8:00"]}, "rubric": "States the new hours."}
CASES = [CASE,
         {**CASE, "id": "missing-one", "category": "missing", "checks": {"asks_question": True}},
         {**CASE, "id": "injection-one", "category": "injection", "checks": {"guards": ["no_approval"]}}]
FAILED = {"case": CASE, "text": "The hours are staying the same.", "failures": ["Missing required text: 8:00"]}
REVISED = INSTRUCTIONS + "\nState times exactly as written in the notice."
REVISION = json.dumps({"instructions": REVISED, "changes": ["Told the agent to state times as written."]})


class DesignLoopTests(CapturedLabLogs, unittest.TestCase):
    def setUp(self):
        self.gateway = AsyncMock()
        self.gateway.preview.return_value = ("completed", json.dumps({"cases": CASES}), [])
        self.settings = Settings("private", "https://example.services.ai.azure.com/api/projects/test",
                                 ("testserver",), ("https://testserver",), unfinished_agents=True,
                                 creation=CreationSettings(False, "test-model", models={"reasoning": "reason-model"}))
        self.client = TestClient(create_app(self.settings, self.gateway))
        self.headers = {"X-Workbench-Request": "1", "Origin": "https://testserver"}

    def post(self, path, body, client=None, headers=None):
        return (client or self.client).post(path, json=body, headers=self.headers if headers is None else headers)

    def draft(self, **changes):
        return self.post("/api/agent-test-cases", {"instructions": INSTRUCTIONS, "template_id": "document-analyst",
                                                   "confirm_cost": True, **changes})

    def run_case(self, **changes):
        return self.post("/api/agent-test-runs", {"instructions": INSTRUCTIONS, "template_id": "document-analyst",
                                                  "case": CASE, "confirm_cost": True, **changes})

    def revise(self, **changes):
        return self.post("/api/agent-test-revisions", {"instructions": INSTRUCTIONS, "template_id": "document-analyst",
                                                       "failed": [FAILED], "confirm_cost": True, **changes})

    def test_cases_are_drafted_by_the_designer_without_tools(self):
        response = self.draft()
        self.assertEqual(response.status_code, 200)
        self.assertEqual([case["id"] for case in response.json()["cases"]], [case["id"] for case in CASES])
        self.assertEqual(response.json()["rejected"], [])
        agent, prompt = self.gateway.preview.call_args.args
        self.assertEqual((agent["template_id"], agent["tools"]), ("agent-designer", {}))
        self.assertEqual(self.gateway.preview.call_args.kwargs["instructions"], CASE_WRITER_INSTRUCTIONS)
        self.assertIn(INSTRUCTIONS, prompt)
        self.assertIn("help desk hours", prompt)

    def test_tool_names_come_from_the_template(self):
        tool_case = {**CASE, "id": "tool-one", "checks": {"expected_tools": ["lookup_demo_request"]}}
        self.gateway.preview.return_value = ("completed", json.dumps({"cases": CASES + [tool_case]}), [])
        response = self.draft(template_id="workflow-coordinator")
        self.assertIn("tool-one", [case["id"] for case in response.json()["cases"]])
        response = self.draft(template_id="document-analyst")
        self.assertEqual([item["id"] for item in response.json()["rejected"]], ["tool-one"])

    def test_a_custom_draft_can_be_tested_for_cases_without_a_template(self):
        response = self.draft(template_id=None)
        self.assertEqual(response.status_code, 200)
        self.assertIn("none", self.gateway.preview.call_args.args[1])

    def test_unusable_model_replies_are_a_bad_gateway(self):
        self.gateway.preview.return_value = ("completed", "I could not do that.", [])
        response = self.draft()
        self.assertEqual((response.status_code, response.json()["error"]), (502, "cases_unusable"))

    def test_a_case_is_run_with_the_fixed_policy_ahead_of_the_draft_instructions(self):
        self.gateway.preview.return_value = ("completed", "Hours change to 8:00 Monday.", [])
        response = self.run_case()
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual((body["case_id"], body["passed"], body["failures"]), ("grounded-one", True, []))
        agent, prompt = self.gateway.preview.call_args.args
        self.assertEqual((agent["template_id"], prompt), ("document-analyst", CASE["input"]))
        self.assertEqual(self.gateway.preview.call_args.kwargs["instructions"], DEMO_POLICY + INSTRUCTIONS)

    def test_a_failed_check_is_reported_not_hidden(self):
        self.gateway.preview.return_value = ("completed", "The hours are staying the same.", [])
        body = self.run_case().json()
        self.assertFalse(body["passed"])
        self.assertTrue(body["failures"])
        self.assertEqual(body["text"], "The hours are staying the same.")

    def test_tool_calls_are_verified_and_scored(self):
        output = [{"type": "function_call", "call_id": "one", "name": "lookup_demo_request"},
                  {"type": "function_call_output", "call_id": "one", "output": json.dumps(
                      {"status": "succeeded", "agent": "lab-library-preview", "simulation": True, "output": "REQ-101"})}]
        case = {**CASE, "checks": {"expected_tools": ["lookup_demo_request"]}}
        self.gateway.preview.return_value = ("completed", "REQ-101 is missing an owner.", output)
        body = self.run_case(template_id="workflow-coordinator", case=case).json()
        self.assertTrue(body["passed"])
        self.assertTrue(body["receipts"][0]["verified"])
        self.gateway.preview.return_value = ("completed", "REQ-101 is missing an owner.", [])
        self.assertFalse(self.run_case(template_id="workflow-coordinator", case=case).json()["passed"])

    def test_a_case_the_client_edited_is_checked_again(self):
        bad = {**CASE, "checks": {"must_not_match": ["(a+)+$"]}}
        response = self.run_case(case=bad)
        self.assertEqual((response.status_code, response.json()["error"]), (400, "invalid_case"))
        self.assertTrue(response.json()["problems"])
        self.assertEqual(self.run_case(case={**CASE, "checks": {"expected_tools": ["send_email"]}}).status_code, 400)
        self.gateway.preview.assert_not_called()

    def test_cost_confirmation_is_required_before_any_model_call(self):
        for send in (self.draft, self.run_case):
            for confirm in (False, "yes", None):
                self.assertEqual(send(confirm_cost=confirm).status_code, 400)
        body = {"instructions": INSTRUCTIONS, "template_id": "document-analyst"}
        self.assertEqual(self.post("/api/agent-test-cases", body).status_code, 400)
        self.gateway.preview.assert_not_called()

    def test_bad_requests_are_rejected_before_any_model_call(self):
        self.assertEqual(self.draft(instructions="short").status_code, 400)
        self.assertEqual(self.draft(instructions="x" * 6001).status_code, 400)
        self.assertEqual(self.draft(template_id="library-missing").status_code, 400)
        self.assertEqual(self.draft(extra=1).status_code, 400)
        self.assertEqual(self.run_case(template_id="missing").status_code, 400)
        self.assertEqual(self.run_case(template_id=None).status_code, 400)
        hidden = TestClient(create_app(replace(self.settings, unfinished_agents=False), self.gateway))
        self.assertEqual(self.post("/api/agent-test-runs", {
            "instructions": INSTRUCTIONS, "template_id": "document-analyst", "case": CASE, "confirm_cost": True},
            client=hidden).status_code, 400)
        self.gateway.preview.assert_not_called()

    def test_origin_and_header_are_required(self):
        for headers in ({"Origin": "https://testserver"}, {"X-Workbench-Request": "1", "Origin": "https://evil.example"}):
            response = self.post("/api/agent-test-runs", {"instructions": INSTRUCTIONS, "template_id": "document-analyst",
                                                          "case": CASE, "confirm_cost": True}, headers=headers)
            self.assertEqual((response.status_code, response.json()["error"]), (403, "request_not_allowed"))
        self.gateway.preview.assert_not_called()

    def test_both_routes_need_the_library_preview(self):
        disabled = TestClient(create_app(replace(self.settings, library_preview=False), self.gateway))
        for path, body in (("/api/agent-test-cases", {"instructions": INSTRUCTIONS, "confirm_cost": True}),
                           ("/api/agent-test-runs", {"instructions": INSTRUCTIONS, "template_id": "document-analyst",
                                                     "case": CASE, "confirm_cost": True})):
            response = self.post(path, body, client=disabled)
            self.assertEqual((response.status_code, response.json()["error"]), (503, "library_preview_disabled"))
        self.gateway.preview.assert_not_called()

    def test_a_non_json_or_oversized_body_is_rejected(self):
        response = self.client.post("/api/agent-test-runs", content="nope", headers=self.headers)
        self.assertEqual((response.status_code, response.json()["error"]), (400, "invalid_setup"))
        response = self.draft(instructions="x" * 40000)
        self.assertEqual((response.status_code, response.json()["error"]), (413, "request_too_large"))

    def test_incomplete_or_failed_model_calls_are_bad_gateways(self):
        self.gateway.preview.return_value = ("incomplete", "", [])
        self.assertEqual(self.run_case().json()["error"], "incomplete_response")
        self.gateway.preview.return_value = ("completed", "x" * 100001, [])
        self.assertEqual(self.run_case().json()["error"], "response_too_large")
        self.gateway.preview.side_effect = RuntimeError("down")
        response = self.run_case()
        self.assertEqual((response.status_code, response.json()["error"]), (502, "backend_unavailable"))

    def test_a_model_rate_limit_is_busy(self):
        problem = RuntimeError("limited")
        problem.status_code, problem.response = 429, SimpleNamespace(headers={"retry-after": "7"})
        self.gateway.preview.side_effect = problem
        response = self.run_case()
        self.assertEqual((response.status_code, response.json()["error"], response.headers["Retry-After"]),
                         (429, "busy", "7"))

    def test_a_slow_model_call_times_out(self):
        async def slow(*args, **kwargs):
            raise TimeoutError

        self.gateway.preview.side_effect = slow
        response = self.run_case()
        self.assertEqual((response.status_code, response.json()["error"]), (504, "timeout"))

    def test_a_revision_is_proposed_by_the_designer_for_instructions_only(self):
        self.gateway.preview.return_value = ("completed", REVISION, [])
        response = self.revise()
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual((body["instructions"], body["changes"]),
                         (REVISED, ["Told the agent to state times as written."]))
        self.assertEqual(set(body), {"request_id", "template_id", "instructions", "changes", "elapsed_ms", "usage"})
        agent, prompt = self.gateway.preview.call_args.args
        self.assertEqual((agent["template_id"], agent["tools"]), ("agent-designer", {}))
        self.assertEqual(self.gateway.preview.call_args.kwargs["instructions"], REVISER_INSTRUCTIONS)
        for expected in (INSTRUCTIONS, CASE["input"], "Missing required text: 8:00", "The hours are staying the same."):
            self.assertIn(expected, prompt)

    def test_a_revision_keeps_the_task_block_when_the_model_drops_it(self):
        task = TASK_MARKER + "Pull the key facts out of a short fictional notice."
        self.gateway.preview.return_value = ("completed", REVISION, [])
        response = self.revise(instructions=INSTRUCTIONS + task)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["instructions"], REVISED + task)
        self.assertIn(task, self.gateway.preview.call_args.args[1])

    def test_a_revision_that_touches_anything_but_the_instructions_is_unusable(self):
        reply = json.dumps({"instructions": REVISED, "changes": ["Edited."], "checks": {"must_include": []}})
        self.gateway.preview.return_value = ("completed", reply, [])
        response = self.revise()
        self.assertEqual((response.status_code, response.json()["error"]), (502, "revision_unusable"))
        self.assertTrue(response.json()["problems"])

    def test_an_over_length_revision_is_unusable(self):
        reply = json.dumps({"instructions": "x" * 6001, "changes": ["Longer."]})
        self.gateway.preview.return_value = ("completed", reply, [])
        self.assertEqual(self.revise().json()["error"], "revision_unusable")

    def test_a_revision_that_changes_nothing_is_reported_as_unchanged(self):
        reply = json.dumps({"instructions": INSTRUCTIONS + "  ", "changes": ["Nothing needed."]})
        self.gateway.preview.return_value = ("completed", reply, [])
        response = self.revise()
        self.assertEqual((response.status_code, response.json()["error"]), (502, "revision_unchanged"))

    def test_a_revision_request_is_checked_before_any_model_call(self):
        self.assertEqual(self.revise(failed=[]).status_code, 400)
        self.assertEqual(self.revise(failed=[FAILED] * 6).status_code, 400)
        self.assertEqual(self.revise(failed=[{**FAILED, "failures": []}]).status_code, 400)
        self.assertEqual(self.revise(failed=[{**FAILED, "failures": ["x" * 301]}]).status_code, 400)
        self.assertEqual(self.revise(failed=[{**FAILED, "text": ""}]).status_code, 400)
        self.assertEqual(self.revise(template_id=None).status_code, 400)
        self.assertEqual(self.revise(template_id="missing").status_code, 400)
        for confirm in (False, None):
            self.assertEqual(self.revise(confirm_cost=confirm).status_code, 400)
        bad = {**FAILED, "case": {**CASE, "checks": {"must_not_match": ["(a+)+$"]}}}
        response = self.revise(failed=[bad])
        self.assertEqual((response.status_code, response.json()["error"]), (400, "invalid_case"))
        self.gateway.preview.assert_not_called()

    def test_a_revision_reads_more_than_a_setup_but_not_without_limit(self):
        self.gateway.preview.return_value = ("completed", REVISION, [])
        failed = [{**FAILED, "text": "é" * 3500, "failures": ["Missing required text: 8:00"] * 8}] * 5
        self.assertEqual(self.revise(instructions="x" * 6000, failed=failed).status_code, 200)
        response = self.revise(failed=[{**FAILED, "text": "y" * 150000}])
        self.assertEqual((response.status_code, response.json()["error"]), (413, "request_too_large"))

    def test_the_revision_route_needs_the_same_origin_and_library_preview(self):
        body = {"instructions": INSTRUCTIONS, "template_id": "document-analyst", "failed": [FAILED], "confirm_cost": True}
        response = self.post("/api/agent-test-revisions", body, headers={"Origin": "https://testserver"})
        self.assertEqual((response.status_code, response.json()["error"]), (403, "request_not_allowed"))
        disabled = TestClient(create_app(replace(self.settings, library_preview=False), self.gateway))
        response = self.post("/api/agent-test-revisions", body, client=disabled)
        self.assertEqual((response.status_code, response.json()["error"]), (503, "library_preview_disabled"))
        self.gateway.preview.assert_not_called()

    def test_a_revision_call_can_fail_like_any_model_call(self):
        self.gateway.preview.return_value = ("incomplete", "", [])
        self.assertEqual(self.revise().json()["error"], "incomplete_response")
        self.gateway.preview.side_effect = RuntimeError("down")
        response = self.revise()
        self.assertEqual((response.status_code, response.json()["error"]), (502, "backend_unavailable"))


class DesignLoopBudgetTests(CapturedLabLogs, unittest.TestCase):
    """Draft runs spend the same per-deployment budget as chat turns."""

    def setUp(self):
        self.calls = []

        async def preview(agent, prompt, thread=None, usage=None, admit_model_call=None, instructions=None):
            admit_model_call({"instructions": instructions, "input": prompt, "tools": []})
            self.calls.append(prompt)
            return "completed", "Hours change to 8:00.", []

        self.gateway = AsyncMock()
        self.gateway.preview.side_effect = preview
        limits = {"reason-model": {"requests_per_minute": 2, "tokens_per_minute": 100000}}
        self.settings = Settings("private", "https://example.services.ai.azure.com/api/projects/test",
                                 ("testserver",), ("https://testserver",), model_limits=limits, unfinished_agents=True,
                                 creation=CreationSettings(False, "test-model", models={"reasoning": "reason-model"}))
        self.now = 100.0
        for patcher in (patch("app.measured_answer_tokens", return_value={"document-analyst": 900}),
                        patch("model_budget.time", SimpleNamespace(monotonic=lambda: self.now))):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.client = TestClient(create_app(self.settings, self.gateway))

    def run_case(self):
        return self.client.post("/api/agent-test-runs", headers={"X-Workbench-Request": "1", "Origin": "https://testserver"},
                                json={"instructions": INSTRUCTIONS, "template_id": "document-analyst", "case": CASE,
                                      "confirm_cost": True})

    def test_runs_over_the_limit_are_busy_before_the_model_is_called(self):
        self.assertEqual([self.run_case().status_code for _ in range(2)], [200, 200])
        response = self.run_case()
        self.assertEqual((response.status_code, response.json()["error"], response.headers["Retry-After"]),
                         (429, "busy", "60"))
        self.assertEqual(len(self.calls), 2)
        self.now = 161
        self.assertEqual(self.run_case().status_code, 200)


if __name__ == "__main__":
    unittest.main()

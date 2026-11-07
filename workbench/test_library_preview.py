import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from agent_runtime.demo_tools import create_demo_tools
from agent_runtime.main import demo_policy
from agent_templates import RETIRED_TEMPLATES, TEMPLATES, is_available
from app import execution_receipts
from library_preview import (DESIGNER_ID, DESIGNER_INSTRUCTIONS, DESIGNER_TEMPLATE, MAX_TOOL_ROUNDS, PREVIEW_AGENT,
                             model_observation, preview_agent, run_preview, run_tool, summarize_usage, tool_specs,
                             usage_record)
from model_budget import ModelBudgetWait, estimate_input_tokens


class Response:
    def __init__(self, output, status="completed", text="", usage=None, model=None):
        self.output, self.status, self.output_text, self.usage, self.model = output, status, text, usage, model

    def model_dump(self, exclude_none=False):
        return {"output": [dict(item) for item in self.output]}


class FakeClient:
    def __init__(self, responses):
        self.calls, self._queue = [], list(responses)
        self.responses = SimpleNamespace(create=self.create)

    async def create(self, **options):
        self.calls.append({**options, "input": [dict(item) for item in options["input"]]})
        return self._queue.pop(0)


def tool_template():
    return next(template_id for template_id, template in TEMPLATES.items() if template["tools"])


def text_template():
    return next(template_id for template_id, template in TEMPLATES.items() if not template["tools"])


class LibraryPreviewTests(unittest.TestCase):
    def test_every_template_has_a_preview_binding(self):
        for template_id, template in TEMPLATES.items():
            agent = preview_agent(f"library-{template_id}")
            if template_id in RETIRED_TEMPLATES:
                self.assertIsNone(agent)
                continue
            self.assertEqual(agent["template_id"], template_id)
            self.assertEqual(agent["agent"], PREVIEW_AGENT)
            self.assertTrue(agent["preview"])
            self.assertEqual(agent["model_profile"], template["model_profile"])
            self.assertEqual(agent["tools"], {tool["name"]: PREVIEW_AGENT for tool in template["tools"]})

    def test_agent_designer_is_a_toolless_conversation(self):
        agent = preview_agent(DESIGNER_ID, include_unfinished=False)
        self.assertEqual((agent["template_id"], agent["tools"], agent["preview"]), (DESIGNER_TEMPLATE, {}, True))
        self.assertNotIn(DESIGNER_TEMPLATE, TEMPLATES)
        client = FakeClient([Response([{"type": "message"}], text="Hi! What would you like to build?")])
        status, text, _ = asyncio.run(run_preview(client, template_id=DESIGNER_TEMPLATE, model="gpt-test",
                                                  prompt="Good morning", reasoning=True))
        self.assertEqual((status, text), ("completed", "Hi! What would you like to build?"))
        options = client.calls[0]
        self.assertEqual(options["instructions"], DESIGNER_INSTRUCTIONS)
        self.assertNotIn("tools", options)
        self.assertNotIn("include", options)
        self.assertFalse(options["store"])

    def test_instructions_replace_the_computed_ones_without_changing_the_tools(self):
        custom = demo_policy(text_template()) + "Summarize the notice."
        for template_id, expect_tools in ((text_template(), False), (tool_template(), True), (DESIGNER_TEMPLATE, False)):
            client = FakeClient([Response([{"type": "message"}], text="Done")])
            asyncio.run(run_preview(client, template_id=template_id, model="gpt-test", prompt="Go", reasoning=True,
                                    instructions=custom))
            self.assertEqual(client.calls[0]["instructions"], custom)
            self.assertEqual("tools" in client.calls[0], expect_tools)

    def test_agent_designer_knows_the_real_export_path(self):
        for phrase in ("Take it to Foundry", "The Lab has no import", "hosted-agent package"):
            self.assertIn(phrase, DESIGNER_INSTRUCTIONS)

    def test_agent_designer_knows_how_to_preserve_the_conversation(self):
        for phrase in ("Export conversation", "Save to shared history", "this designer conversation",
                       "Chats are not saved automatically", "save again after adding replies",
                       "Never tell them to paste into Shared history", "not the conversation",
                       "does not create an agent or configure retrieval or tools"):
            self.assertIn(phrase, DESIGNER_INSTRUCTIONS)

    def test_agent_designer_writes_a_spec_naming_only_real_agents(self):
        self.assertIn("agent-spec", DESIGNER_INSTRUCTIONS)
        for key in ("instructions", "human_decision", "closest_template", "tools_needed"):
            self.assertIn(key, DESIGNER_INSTRUCTIONS)
        finished = [identifier for identifier in TEMPLATES if is_available(identifier, False)]
        self.assertTrue(finished)
        for identifier in finished:
            self.assertIn(identifier, DESIGNER_INSTRUCTIONS)
        for identifier in TEMPLATES:
            if identifier not in finished:
                self.assertNotIn(identifier, DESIGNER_INSTRUCTIONS)

    def test_unknown_or_malformed_ids_are_rejected(self):
        for identifier in ("library-", "library-missing-template", "Library-x", f"library-{text_template()}\n",
                           "customer-review", None, 3):
            self.assertIsNone(preview_agent(identifier))

    def test_tool_specs_are_strict_string_schemas(self):
        functions = create_demo_tools(tool_template(), PREVIEW_AGENT)
        for spec, function in zip(tool_specs(functions), functions, strict=True):
            self.assertEqual(spec["name"], function.__name__)
            self.assertTrue(spec["strict"])
            self.assertTrue(spec["description"])
            self.assertFalse(spec["parameters"]["additionalProperties"])
            self.assertEqual(spec["parameters"]["required"], list(spec["parameters"]["properties"]))
            self.assertTrue(all(value == {"type": "string"} for value in spec["parameters"]["properties"].values()))

    def test_bad_tool_calls_fail_closed(self):
        functions = {function.__name__: function for function in create_demo_tools("workflow-coordinator", PREVIEW_AGENT)}
        name = next(iter(functions))
        for call in ({"name": "missing", "arguments": "{}"}, {"name": name, "arguments": "not json"},
                     {"name": name, "arguments": "[]"}, {"name": name, "arguments": json.dumps({"extra": "x"})},
                     {"name": "lookup_demo_request", "arguments": json.dumps({"request_id": "REQ-999"})}):
            self.assertEqual(json.loads(run_tool(functions, call))["status"], "failed")

    def test_text_template_makes_one_call_without_tools(self):
        template_id = text_template()
        client = FakeClient([Response([{"type": "message"}], text="Draft notes")])
        status, text, output = asyncio.run(run_preview(client, template_id=template_id, model="gpt-test", prompt="Hello"))
        self.assertEqual((status, text, output), ("completed", "Draft notes", [{"type": "message"}]))
        options = client.calls[0]
        self.assertEqual(options["instructions"], demo_policy(template_id) + TEMPLATES[template_id]["instructions"])
        self.assertFalse(options["store"])
        self.assertEqual(options["model"], "gpt-test")
        self.assertNotIn("tools", options)
        self.assertNotIn("include", options)
        self.assertEqual(options["input"], [{"role": "user", "content": "Hello"}])

    def test_tool_calls_return_verifiable_simulated_receipts(self):
        template_id = "workflow-coordinator"
        functions = create_demo_tools(template_id, PREVIEW_AGENT)
        function = next(item for item in functions if item.__name__ == "lookup_demo_request")
        arguments = {"request_id": "REQ-101"}
        call = {"type": "function_call", "call_id": "call-1", "name": function.__name__, "arguments": json.dumps(arguments)}
        client = FakeClient([Response([{"type": "reasoning", "encrypted_content": "x"}, call]),
                             Response([{"type": "message"}], text="Answer")])
        history = [{"role": "user", "content": "Earlier"}, {"role": "assistant", "content": "Reply"},
                   {"role": "user", "content": "Look it up"}]
        status, text, output = asyncio.run(run_preview(client, template_id=template_id, model="gpt-test",
                                                       prompt=history, reasoning=True))
        self.assertEqual((status, text), ("completed", "Answer"))
        self.assertEqual(client.calls[0]["include"], ["reasoning.encrypted_content"])
        self.assertEqual(len(client.calls[0]["tools"]), len(functions))
        second = client.calls[1]["input"]
        self.assertEqual(second[:3], history)
        self.assertEqual(second[4], call)
        receipt = next(item for item in output if item["type"] == "function_call_output")
        self.assertEqual(receipt["call_id"], "call-1")
        parsed = json.loads(receipt["output"])
        self.assertEqual(parsed["status"], "succeeded")
        self.assertEqual(parsed["agent"], PREVIEW_AGENT)
        self.assertTrue(parsed["simulation"])
        self.assertEqual(history[2], {"role": "user", "content": "Look it up"})

    def test_medical_preview_runs_and_verifies_the_same_local_calculator(self):
        data = {
            "lines": [{"label": "One", "quantity": "1", "unit_price": "900.00", "amount": "900.00"},
                      {"label": "Two", "quantity": "1", "unit_price": "250.00", "amount": "250.00"},
                      {"label": "Three", "quantity": "1", "unit_price": "250.00", "amount": "250.00"},
                      {"label": "Four", "quantity": "3", "unit_price": "60.00", "amount": "180.00"},
                      {"label": "Five", "quantity": "1", "unit_price": "120.00", "amount": "120.00"}],
            "bill_total": "1800.00", "bill_adjustments": ["-696.00"], "bill_balance": "1104.00",
            "patient_shares": ["120.00", "30.00", "0.00", "8.00", "16.00"], "statement_share": "174.00",
        }
        calls = [{"type": "function_call", "call_id": "math", "name": "calculate_bill_math",
                  "arguments": json.dumps({"bill_data_json": json.dumps(data)})}]
        client = FakeClient([Response(calls), Response([{"type": "message"}], text="Answer")])
        status, _, transcript = asyncio.run(run_preview(
            client, template_id="medical-bill-reviewer", model="gpt-test", prompt="Review sample bill"))
        self.assertEqual(status, "completed")
        spec = next(tool for tool in client.calls[0]["tools"] if tool["name"] == "calculate_bill_math")
        self.assertEqual(spec["parameters"]["required"], ["bill_data_json"])
        receipts = execution_receipts(transcript, preview_agent("library-medical-bill-reviewer")["tools"])
        self.assertEqual(len(receipts), 1)
        self.assertTrue(receipts[0]["verified"])
        result = json.loads(receipts[0]["output"].split("\n", 1)[1])
        self.assertEqual(result["line_amount_sum"], "$1,700.00")
        self.assertEqual(result["bill_total_minus_line_sum"], "$100.00")
        self.assertEqual(result["bill_balance_minus_statement_share"], "$930.00")

    def test_benefits_preview_executes_exact_dates_and_reports_invalid_dates_explicitly(self):
        for start, succeeded in (("2027-02-12", True), ("2027-02-29", False)):
            with self.subTest(start=start):
                call = {"type": "function_call", "call_id": "dates", "name": "calculate_date_difference",
                        "arguments": json.dumps({"start_date": start, "end_date": "2027-03-20"})}
                client = FakeClient([Response([call]), Response([{"type": "message"}], text="Answer")])
                status, _, transcript = asyncio.run(run_preview(
                    client, template_id="benefits-renewal-helper", model="gpt-test", prompt="Check sample dates"))
                self.assertEqual(status, "completed")
                spec = next(tool for tool in client.calls[0]["tools"] if tool["name"] == "calculate_date_difference")
                self.assertEqual(spec["parameters"]["required"], ["start_date", "end_date"])
                receipts = execution_receipts(transcript, preview_agent("library-benefits-renewal-helper")["tools"])
                self.assertEqual(receipts[0]["verified"], succeeded)
                if succeeded:
                    result = json.loads(receipts[0]["output"].split("\n", 1)[1])
                    self.assertEqual(result["days"], 36)
                else:
                    failed = next(item for item in transcript if item["type"] == "function_call_output")
                    self.assertEqual(json.loads(failed["output"])["status"], "failed")
                    self.assertIn("valid calendar date", json.loads(failed["output"])["error"])
                    self.assertIsNone(receipts[0]["output"])

    def test_medical_missing_shares_fail_explicitly_and_can_be_corrected_in_the_next_round(self):
        data = {"lines": [{"label": "One", "amount": "10"}], "statement_share": "1"}
        calls = [{"type": "function_call", "call_id": name, "name": "calculate_bill_math",
                  "arguments": json.dumps({"bill_data_json": json.dumps(value)})}
                 for name, value in (("missing", data), ("copied", {**data, "patient_shares": ["1"]}))]
        client = FakeClient([Response([calls[0]]), Response([calls[1]]),
                             Response([{"type": "message"}], text="Answer")])
        status, _, transcript = asyncio.run(run_preview(
            client, template_id="medical-bill-reviewer", model="gpt-test", prompt="Check sample bill"))
        self.assertEqual(status, "completed")
        outputs = [json.loads(item["output"]) for item in transcript if item["type"] == "function_call_output"]
        self.assertEqual(outputs[0]["status"], "failed")
        self.assertIn("patient_shares", outputs[0]["error"])
        receipts = execution_receipts(transcript, preview_agent("library-medical-bill-reviewer")["tools"])
        self.assertEqual([receipt["verified"] for receipt in receipts], [False, True])
        self.assertEqual(json.loads(receipts[1]["output"].split("\n", 1)[1])["provided_patient_shares_sum"], "$1.00")

    def test_usage_is_summed_across_tool_rounds(self):
        call = {"type": "function_call", "call_id": "call-1", "name": "lookup_demo_request",
                "arguments": json.dumps({"request_id": "REQ-101"})}
        first = {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120,
                 "input_tokens_details": {"cached_tokens": 0}, "output_tokens_details": {"reasoning_tokens": 8}}
        second = {"input_tokens": 150, "output_tokens": 40, "total_tokens": 190,
                  "input_tokens_details": {"cached_tokens": 64}, "output_tokens_details": {"reasoning_tokens": 12}}
        client = FakeClient([Response([call], usage=first, model="gpt-4.1-2025-04-14"),
                             Response([{"type": "message"}], text="Answer", usage=second,
                                      model="gpt-4.1-mini-2025-04-14")])
        usage = []
        asyncio.run(run_preview(client, template_id="workflow-coordinator", model="model-router", prompt="Check", usage=usage))
        self.assertEqual(summarize_usage(usage), {"input_tokens": 250, "output_tokens": 60, "total_tokens": 310,
                                                  "cached_tokens": 64, "reasoning_tokens": 20})
        self.assertEqual(model_observation("model-router", usage), {
            "deployment": "model-router",
            "calls": [
                {"reported_model": "gpt-4.1-2025-04-14", "model_status": "reported",
                 "usage": {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120,
                           "cached_tokens": 0, "reasoning_tokens": 8}},
                {"reported_model": "gpt-4.1-mini-2025-04-14", "model_status": "reported",
                 "usage": {"input_tokens": 150, "output_tokens": 40, "total_tokens": 190,
                           "cached_tokens": 64, "reasoning_tokens": 12}},
            ],
        })
        self.assertEqual([call["model"] for call in client.calls], ["model-router", "model-router"])

    def test_model_observations_distinguish_missing_and_invalid_metadata(self):
        self.assertIsNone(model_observation("model-router", []))
        for model, expected in ((None, "not_reported"), ("", "invalid"), (True, "invalid"),
                                ("bad\nprivate", "invalid"), ("gpt-4.1\n", "invalid"), ("a" * 129, "invalid"),
                                ("org/model:v1", "reported")):
            with self.subTest(model=model):
                record = usage_record(Response([], model=model, usage={"input_tokens": 10, "output_tokens": False}))
                observed = model_observation("fixed-model", [record])
                self.assertEqual(observed["deployment"], "fixed-model")
                call = observed["calls"][0]
                self.assertEqual(call["model_status"], expected)
                self.assertEqual(call["reported_model"], model if expected == "reported" else None)
                self.assertEqual(call["usage"], {"input_tokens": 10, "output_tokens": None, "total_tokens": None,
                                                 "cached_tokens": None, "reasoning_tokens": None})
                if expected == "invalid" and isinstance(model, str) and model:
                    self.assertNotIn(model, json.dumps(observed))
        missing = model_observation("model-router", [usage_record(Response([]))])["calls"][0]
        self.assertEqual(missing, {"reported_model": None, "model_status": "not_reported", "usage": None})

    def test_each_preview_model_call_is_admitted_with_its_current_input_history(self):
        template_id = "workflow-coordinator"
        function = create_demo_tools(template_id, PREVIEW_AGENT)[0]
        call = {"type": "function_call", "call_id": "call-1", "name": function.__name__, "arguments": "{}"}
        client = FakeClient([Response([call]), Response([{"type": "message"}], text="Answer")])
        payloads = []

        def admit(payload):
            payloads.append(payload)
            if len(payloads) == 2:
                raise ModelBudgetWait(59)

        with patch("library_preview.run_tool", return_value="sample lookup result " * 100):
            with self.assertRaisesRegex(ModelBudgetWait, "configured limit"):
                asyncio.run(run_preview(client, template_id=template_id, model="gpt-test", prompt="Check",
                                        admit_model_call=admit))
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(len(payloads), 2)
        self.assertLess(estimate_input_tokens(payloads[0]), estimate_input_tokens(payloads[1]))

    def test_missing_usage_is_not_reported_as_zero(self):
        self.assertIsNone(summarize_usage([]))
        self.assertIsNone(summarize_usage([usage_record(Response([]))]))
        partial = [usage_record(Response([], usage={"input_tokens": 10, "output_tokens": 2, "total_tokens": 12})),
                   usage_record(Response([], usage={"input_tokens": 5, "output_tokens": True, "total_tokens": -1}))]
        self.assertEqual(summarize_usage(partial), {"input_tokens": 15, "output_tokens": None, "total_tokens": None,
                                                    "cached_tokens": None, "reasoning_tokens": None})
        self.assertIsNone(summarize_usage([partial[0], usage_record(Response([]))]))
        dumped = SimpleNamespace(usage=SimpleNamespace(model_dump=lambda: {"input_tokens": 3, "output_tokens": 4,
                                                                            "total_tokens": 7}),
                                 model="gpt-4.1")
        sdk_record = usage_record(dumped)
        self.assertEqual(sdk_record["total_tokens"], 7)
        self.assertEqual((sdk_record["model_status"], sdk_record["reported_model"]), ("reported", "gpt-4.1"))

    def test_tool_calling_profile_omits_reasoning_include(self):
        template_id = tool_template()
        client = FakeClient([Response([{"type": "message"}], text="Answer")])
        asyncio.run(run_preview(client, template_id=template_id, model="gpt-test", prompt="Hi", reasoning=False))
        self.assertIn("tools", client.calls[0])
        self.assertNotIn("include", client.calls[0])

    def test_tool_loop_is_bounded(self):
        template_id = tool_template()
        function = create_demo_tools(template_id, PREVIEW_AGENT)[0]
        call = {"type": "function_call", "call_id": "loop", "name": function.__name__, "arguments": "{}"}
        client = FakeClient([Response([call]) for _ in range(MAX_TOOL_ROUNDS + 1)])
        status, text, _ = asyncio.run(run_preview(client, template_id=template_id, model="gpt-test", prompt="Hi"))
        self.assertEqual((status, text), ("incomplete", ""))
        self.assertEqual(len(client.calls), MAX_TOOL_ROUNDS + 1)

    def test_too_many_parallel_calls_stop(self):
        template_id = tool_template()
        function = create_demo_tools(template_id, PREVIEW_AGENT)[0]
        calls = [{"type": "function_call", "call_id": f"c{index}", "name": function.__name__, "arguments": "{}"}
                 for index in range(9)]
        client = FakeClient([Response(calls)])
        status, _, _ = asyncio.run(run_preview(client, template_id=template_id, model="gpt-test", prompt="Hi"))
        self.assertEqual(status, "incomplete")
        self.assertEqual(len(client.calls), 1)

    def test_non_completed_status_is_returned(self):
        client = FakeClient([Response([], status="incomplete", text="")])
        status, _, _ = asyncio.run(run_preview(client, template_id=text_template(), model="gpt-test", prompt="Hi"))
        self.assertEqual(status, "incomplete")


if __name__ == "__main__":
    unittest.main()

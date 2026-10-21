import asyncio
import json
import unittest
from types import SimpleNamespace

from agent_runtime.demo_tools import create_demo_tools
from agent_runtime.main import DEMO_POLICY
from agent_templates import RETIRED_TEMPLATES, TEMPLATES, is_available
from library_preview import (DESIGNER_ID, DESIGNER_INSTRUCTIONS, DESIGNER_TEMPLATE, MAX_TOOL_ROUNDS, PREVIEW_AGENT,
                             preview_agent, run_preview, run_tool, summarize_usage, tool_specs, usage_record)


class Response:
    def __init__(self, output, status="completed", text="", usage=None):
        self.output, self.status, self.output_text, self.usage = output, status, text, usage

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

    def test_agent_designer_knows_the_real_export_path(self):
        for phrase in ("Take it to Foundry", "The Lab has no import", "hosted-agent package"):
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
        self.assertEqual(options["instructions"], DEMO_POLICY + TEMPLATES[template_id]["instructions"])
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

    def test_usage_is_summed_across_tool_rounds(self):
        call = {"type": "function_call", "call_id": "call-1", "name": "lookup_demo_request",
                "arguments": json.dumps({"request_id": "REQ-101"})}
        first = {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120,
                 "input_tokens_details": {"cached_tokens": 0}, "output_tokens_details": {"reasoning_tokens": 8}}
        second = {"input_tokens": 150, "output_tokens": 40, "total_tokens": 190,
                  "input_tokens_details": {"cached_tokens": 64}, "output_tokens_details": {"reasoning_tokens": 12}}
        client = FakeClient([Response([call], usage=first), Response([{"type": "message"}], text="Answer", usage=second)])
        usage = []
        asyncio.run(run_preview(client, template_id="workflow-coordinator", model="gpt-test", prompt="Check", usage=usage))
        self.assertEqual(summarize_usage(usage), {"input_tokens": 250, "output_tokens": 60, "total_tokens": 310,
                                                  "cached_tokens": 64, "reasoning_tokens": 20})

    def test_missing_usage_is_not_reported_as_zero(self):
        self.assertIsNone(summarize_usage([]))
        self.assertIsNone(summarize_usage([usage_record(Response([]))]))
        partial = [usage_record(Response([], usage={"input_tokens": 10, "output_tokens": 2, "total_tokens": 12})),
                   usage_record(Response([], usage={"input_tokens": 5, "output_tokens": True, "total_tokens": -1}))]
        self.assertEqual(summarize_usage(partial), {"input_tokens": 15, "output_tokens": None, "total_tokens": None,
                                                    "cached_tokens": None, "reasoning_tokens": None})
        dumped = SimpleNamespace(usage=SimpleNamespace(model_dump=lambda: {"input_tokens": 3, "output_tokens": 4,
                                                                            "total_tokens": 7}))
        self.assertEqual(usage_record(dumped)["total_tokens"], 7)

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

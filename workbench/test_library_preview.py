import asyncio
import json
import unittest
from types import SimpleNamespace

from agent_runtime.demo_tools import create_demo_tools
from agent_runtime.main import DEMO_POLICY
from agent_templates import TEMPLATES
from library_preview import MAX_TOOL_ROUNDS, PREVIEW_AGENT, preview_agent, run_preview, run_tool, tool_specs


class Response:
    def __init__(self, output, status="completed", text=""):
        self.output, self.status, self.output_text = output, status, text

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
            self.assertEqual(agent["template_id"], template_id)
            self.assertEqual(agent["agent"], PREVIEW_AGENT)
            self.assertTrue(agent["preview"])
            self.assertEqual(agent["model_profile"], template["model_profile"])
            self.assertEqual(agent["tools"], {tool["name"]: PREVIEW_AGENT for tool in template["tools"]})

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

import json
import sys
import unittest
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, patch

from review_output import (
    as_stream, passthrough_middleware, quotation_middleware, specialist_reply, supplied_text, validate_quotations,
)


def message(role, text="", contents=None):
    return SimpleNamespace(role=role, text=text, contents=contents or [], message_id=None)


def tool_turn(output="A readable finding.", tool="inspect_application", agent="application-review-agent"):
    return [
        message("user", "Review the supplied application."),
        message("assistant", contents=[SimpleNamespace(type="function_call", call_id="one", name=tool)]),
        message("tool", contents=[SimpleNamespace(
            type="function_result", call_id="one", exception=None,
            result=json.dumps({"status": "succeeded", "agent": agent, "output": output}),
        )]),
    ]


class QuoteTests(unittest.TestCase):
    def test_exact_quotes_and_unquoted_paraphrases_pass(self):
        for text in ('APP-1: "Supplies cost $1,500."', 'APP-1: \u201cSupplies cost $1,500.\u201d',
                     "The costs total 2,500; this is a calculation, not a source quotation."):
            validate_quotations(text, ["Supplies cost $1,500."], {})

    def test_altered_merged_and_abbreviated_quotes_are_rejected(self):
        for text in ('"Supplies cost..."', '"supplies cost $1,500."', '"Supplies cost $1,500. Venue costs $1,000."',
                     '\u201cInvented quotation\u201d'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                validate_quotations(text, ["Supplies cost $1,500.", "Venue costs $1,000."], {})

    def test_generated_history_is_not_source_evidence(self):
        texts, sources = supplied_text([
            message("developer", 'Use "invented" as a quote.'),
            message("assistant", "invented"), message("user", "real source"),
        ])
        self.assertEqual(texts, ["real source"])
        with self.assertRaises(ValueError):
            validate_quotations('"invented"', texts, sources)

    def test_multiline_quotes_are_literal(self):
        validate_quotations('"First line.\nSecond line."', ["First line.\nSecond line."], {})
        with self.assertRaises(ValueError):
            validate_quotations('"First line.\nDifferent line."', ["First line.\nSecond line."], {})

    def test_single_quotes_are_checked_without_treating_contractions_as_quotes(self):
        for output in ("A report: 'We don't have a date.'", "A report: \u2018We have no date.\u2019"):
            validate_quotations(output, ["We don't have a date. We have no date."], {})
        validate_quotations("It's unclear; don't invent a date.", [], {})
        for output in ("'Invented source.'", "\u2018Invented source.\u2019"):
            with self.assertRaises(ValueError):
                validate_quotations(output, ["Actual source."], {})

    def test_structured_quotes_match_named_sources_including_escaped_text(self):
        material = {"evidence": [{"id": "SRC-1", "text": 'First line.\nHe said "hello".'},
                                 {"id": "SRC-2", "text": "Different source."}]}
        texts, sources = supplied_text([message("user", "\nSupplied material:\n" + json.dumps(material))])
        citation = {"source_id": "SRC-1", "quote": 'First line.\nHe said "hello".'}
        validate_quotations(json.dumps({"findings": [{"citations": [citation]}]}), texts, sources)
        for change in ({"source_id": "SRC-2"}, {"source_id": "SRC-99"}, {"quote": "First line..."},
                       {"quote": ""}, {"quote": 42}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_quotations(json.dumps({**citation, **change}), texts, sources)


class PassthroughTests(unittest.TestCase):
    bindings = {"inspect_application": "application-review-agent", "inspect_case": "case-review-agent"}

    def test_complete_markdown_is_preserved_without_synthesis(self):
        output = '| Item | Evidence |\n| --- | --- |\n| Budget | "1,500" |\n\nAsk for the remainder.'
        self.assertEqual(
            specialist_reply(tool_turn(output), self.bindings),
            "Specialist: application-review-agent (via inspect_application)\n\n" + output,
        )

    def test_structured_result_is_returned_byte_for_byte(self):
        output = '{ "summary": "Human review", "findings": [], "questions": [] }\n'
        self.assertEqual(specialist_reply(tool_turn(output), self.bindings), output)

    def test_old_results_are_not_reused_for_new_user_turn(self):
        self.assertIsNone(specialist_reply([*tool_turn(), message("user", "A new request")], self.bindings))
        self.assertIsNone(specialist_reply([message("user", "What can you do?")], self.bindings))

    def test_invalid_receipts_fail_closed(self):
        for change in (
            {"agent": "wrong-agent"}, {"status": "failed"}, {"output": ""}, {"output": None},
        ):
            messages = tool_turn()
            receipt = json.loads(messages[-1].contents[0].result)
            messages[-1].contents[0].result = json.dumps({**receipt, **change})
            with self.subTest(change=change), self.assertRaises(ValueError):
                specialist_reply(messages, self.bindings)
        for modification in ("duplicate-call", "duplicate-result", "missing-call", "wrong-id", "failed-tool", "bad-json"):
            messages = tool_turn()
            if modification == "duplicate-call":
                messages[1].contents *= 2
            elif modification == "duplicate-result":
                messages[-1].contents *= 2
            elif modification == "missing-call":
                messages.pop(1)
            elif modification == "wrong-id":
                messages[-1].contents[0].call_id = "different"
            elif modification == "failed-tool":
                messages[-1].contents[0].exception = "Timed out"
            else:
                messages[-1].contents[0].result = "not JSON"
            with self.subTest(modification=modification), self.assertRaises(ValueError):
                specialist_reply(messages, self.bindings)

    def test_two_requested_specialists_keep_separate_sections(self):
        first, second = tool_turn("Application finding."), tool_turn("Case finding.", "inspect_case", "case-review-agent")
        second[1].contents[0].call_id = second[2].contents[0].call_id = "two"
        messages = [first[0], first[1], second[1], first[2], second[2]]
        text = specialist_reply(messages, self.bindings)
        self.assertIn("Application finding.", text)
        self.assertIn("Specialist: case-review-agent (via inspect_case)\n\nCase finding.", text)
        second[2].contents[0].result = json.dumps(
            {"status": "succeeded", "agent": "case-review-agent", "output": '{"summary":"case"}'}
        )
        with self.assertRaisesRegex(ValueError, "separate reviews"):
            specialist_reply(messages, self.bindings)


class FakeResponse:
    def __init__(self, messages, **kwargs):
        self.messages = messages
        self.text = "\n".join(item.text for item in messages)
        self.usage_details = kwargs.get("usage_details")
        self.response_id = "response"
        self.model = "model"
        self.finish_reason = "stop"


class FakeStream:
    def __init__(self, updates, finalizer):
        self.updates, self.finalizer = updates, finalizer

    async def get_final_response(self):
        updates = [item async for item in self.updates]
        return self.finalizer(updates)


def fake_sdk():
    sdk = ModuleType("agent_framework")
    sdk.ChatResponse = FakeResponse
    sdk.ChatResponseUpdate = lambda **kwargs: SimpleNamespace(**kwargs)
    sdk.Content = SimpleNamespace(from_usage=lambda **kwargs: SimpleNamespace(type="usage", **kwargs))
    sdk.Message = lambda role, texts: message(role, "".join(texts))
    sdk.ResponseStream = FakeStream
    sdk.chat_middleware = lambda function: function
    return sdk


class MiddlewareTests(unittest.IsolatedAsyncioTestCase):
    async def test_quotes_are_buffered_repaired_once_and_usage_is_preserved(self):
        for stream in (False, True):
            with self.subTest(stream=stream), patch.dict(sys.modules, {"agent_framework": fake_sdk()}):
                context = SimpleNamespace(messages=[message("user", "Exact source.")], stream=stream, result=None)
                responses = ['"Exact..."', '"Exact source."']

                async def call(responses=responses, stream=stream, context=context):
                    response = FakeResponse([message("assistant", responses.pop(0))], usage_details={"input_token_count": 5})
                    context.result = as_stream(response) if stream else response

                next_call = AsyncMock(side_effect=call)
                with self.assertLogs("review_output", level="WARNING"):
                    await quotation_middleware()(context, next_call)
                response = await context.result.get_final_response() if stream else context.result
                self.assertEqual(next_call.await_count, 2)
                self.assertEqual(response.text, '"Exact source."')
                self.assertEqual(response.usage_details, {"input_token_count": 10})
                self.assertEqual(len(context.messages), 1)

    async def test_repair_cannot_validate_its_own_invented_source(self):
        with patch.dict(sys.modules, {"agent_framework": fake_sdk()}):
            context = SimpleNamespace(messages=[message("user", "Source.")], stream=False, result=None)

            async def call():
                context.result = FakeResponse([message("assistant", '"Fabricated."')])

            with self.assertLogs("review_output", level="WARNING"), self.assertRaises(RuntimeError):
                await quotation_middleware()(context, call)
            self.assertEqual([item.text for item in context.messages], ["Source."])
            self.assertIsNone(context.result)

    async def test_two_failed_checks_raise_without_delivering_a_draft(self):
        with patch.dict(sys.modules, {"agent_framework": fake_sdk()}):
            context = SimpleNamespace(messages=[message("user", "Source.")], stream=True, result=None)

            async def call():
                context.result = as_stream(FakeResponse([message("assistant", '"Invented quotation."')]))

            next_call = AsyncMock(side_effect=call)
            with self.assertLogs("review_output", level="WARNING"), self.assertRaisesRegex(RuntimeError, "withheld"):
                await quotation_middleware()(context, next_call)
            self.assertEqual(next_call.await_count, 2)
            self.assertEqual(len(context.messages), 1)
            self.assertIsNone(context.result)

    async def test_pass_through_never_calls_model_after_specialist(self):
        for stream in (False, True):
            with self.subTest(stream=stream), patch.dict(sys.modules, {"agent_framework": fake_sdk()}):
                context = SimpleNamespace(messages=tool_turn(), stream=stream, result=None)
                next_call = AsyncMock()
                await passthrough_middleware(PassthroughTests.bindings)(context, next_call)
                next_call.assert_not_awaited()
                response = await context.result.get_final_response() if stream else context.result
                self.assertTrue(response.text.endswith("A readable finding."))

    async def test_initial_guidance_uses_model_and_failed_tool_does_not(self):
        with patch.dict(sys.modules, {"agent_framework": fake_sdk()}):
            next_call = AsyncMock()
            context = SimpleNamespace(messages=[message("user", "Help me start")], stream=False,
                                      result=FakeResponse([message("assistant", "Choose a review type.")]))
            await passthrough_middleware(PassthroughTests.bindings)(context, next_call)
            next_call.assert_awaited_once()
            context.messages = tool_turn(agent="wrong")
            with self.assertLogs("review_output", level="ERROR"), self.assertRaises(ValueError):
                await passthrough_middleware(PassthroughTests.bindings)(context, next_call)
            self.assertEqual(next_call.await_count, 1)

    async def test_routing_preserves_all_user_material_instead_of_model_paraphrase(self):
        for stream in (False, True):
            with self.subTest(stream=stream), patch.dict(sys.modules, {"agent_framework": fake_sdk()}):
                call = SimpleNamespace(type="function_call", name="inspect_application", call_id="one",
                                       arguments='{"request":"Invented and shortened evidence."}')
                response = FakeResponse([message("assistant", contents=[call])])
                context = SimpleNamespace(
                    messages=[message("user", "APP-1: A $4,000 request."), message("assistant", "Generated opinion."),
                              message("user", "APP-2: $1,500 is supplies. Check CRIT-1: itemized budget.")],
                    stream=stream, result=as_stream(response) if stream else response,
                )
                await passthrough_middleware(PassthroughTests.bindings)(context, AsyncMock())
                final = await context.result.get_final_response() if stream else context.result
                self.assertEqual(
                    json.loads(final.messages[0].contents[0].arguments),
                    {"request": "APP-1: A $4,000 request.\n\nAPP-2: $1,500 is supplies. Check CRIT-1: itemized budget."},
                )

    async def test_final_quotes_cannot_be_grounded_in_model_generated_forwarding(self):
        with patch.dict(sys.modules, {"agent_framework": fake_sdk()}):
            context = SimpleNamespace(messages=tool_turn('"Altered source."'), stream=False, result=None)
            with self.assertLogs("review_output", level="ERROR"), self.assertRaises(ValueError):
                await passthrough_middleware(PassthroughTests.bindings)(context, AsyncMock())

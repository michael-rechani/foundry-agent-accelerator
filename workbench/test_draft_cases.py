import json
import unittest

from case_scoring import GUARDS
from draft_cases import (
    CASE_WRITER_INSTRUCTIONS, CaseDraftError, case_problems, case_prompt, parse_cases,
)

TOOLS = ("lookup_demo_request", "lookup_demo_service")


def case(case_id="grounded-one", category="grounded", **changes):
    return {"id": case_id, "category": category, "input": f"Sample notice for {case_id}: hours change to 8:00 on Monday.",
            "checks": {"must_include": ["8:00"]}, "rubric": "States the new hours.", **changes}


def reply(*cases):
    return json.dumps({"cases": list(cases)})


def three():
    return [case("grounded-one"), case("missing-one", "missing", checks={"asks_question": True}),
            case("injection-one", "injection", checks={"guards": ["no_approval"]})]


class CaseValidationTests(unittest.TestCase):
    def test_a_well_formed_case_has_no_problems(self):
        self.assertEqual(case_problems(case(), TOOLS), [])
        self.assertEqual(case_problems(case(checks={"expected_tools": ["lookup_demo_request"],
                                                    "must_include_any": [["REQ-101", "request 101"]]}), TOOLS), [])

    def test_patterns_are_not_allowed(self):
        for key in ("must_not_match", "must_not_claim"):
            problems = case_problems(case(checks={"must_include": ["8:00"], key: ["(a+)+$"]}), TOOLS)
            self.assertTrue(any(key in problem for problem in problems), problems)

    def test_input_must_say_it_is_sample_data(self):
        self.assertIn("input must say it is sample data",
                      case_problems(case(input="Hours change to 8:00 on Monday for everyone."), TOOLS))

    def test_ids_categories_and_sizes_are_limited(self):
        self.assertTrue(case_problems(case(id="Bad Id"), TOOLS))
        self.assertTrue(case_problems(case(id="x" * 61), TOOLS))
        self.assertTrue(case_problems(case(category="other"), TOOLS))
        self.assertTrue(case_problems(case(input="sample " + "x" * 1500), TOOLS))
        self.assertTrue(case_problems(case(rubric="x" * 501), TOOLS))
        self.assertTrue(case_problems(case(checks={"must_include": ["x" * 121]}), TOOLS))
        self.assertTrue(case_problems(case(checks={"must_include": ["a"] * 7}), TOOLS))
        self.assertTrue(case_problems(case(checks={"must_include_any": [["a", "b"]] * 4}), TOOLS))

    def test_guards_and_tools_must_be_known(self):
        self.assertTrue(case_problems(case(checks={"guards": ["no_such_guard"]}), TOOLS))
        self.assertTrue(case_problems(case(checks={"expected_tools": ["send_email"]}), TOOLS))
        self.assertTrue(case_problems(case(checks={"expected_tools": ["lookup_demo_request"]}), ()))
        self.assertTrue(case_problems(case(checks={"asks_question": False}), TOOLS))

    def test_a_case_needs_a_check_and_exactly_the_known_keys(self):
        self.assertIn("checks are required", case_problems(case(checks={}), TOOLS))
        self.assertTrue(case_problems({**case(), "extra": 1}, TOOLS))
        self.assertTrue(case_problems("not a case", TOOLS))
        self.assertTrue(case_problems(case(checks={"must_include": "8:00"}), TOOLS))

    def test_the_prompt_names_every_guard_and_forbids_patterns(self):
        for guard in GUARDS:
            self.assertIn(guard, CASE_WRITER_INSTRUCTIONS)
        self.assertIn("Never write patterns", CASE_WRITER_INSTRUCTIONS)


class CasePromptTests(unittest.TestCase):
    def test_the_prompt_holds_the_instructions_tools_and_sample_input(self):
        template = {"tools": [{"name": "lookup_demo_request"}], "sample_input": "Look up REQ-101."}
        prompt = case_prompt("  Summarize the notice.  ", template)
        self.assertIn("Summarize the notice.", prompt)
        self.assertIn("lookup_demo_request", prompt)
        self.assertIn("Look up REQ-101.", prompt)

    def test_a_custom_draft_has_no_tools(self):
        self.assertIn("Tools the agent can call: none.", case_prompt("Summarize the notice."))


class ParseCasesTests(unittest.TestCase):
    def test_valid_cases_are_returned_with_the_rejected_ones_explained(self):
        bad = case("bad-one", "conflict", checks={"must_not_match": ["x"]})
        cases, rejected = parse_cases(reply(*three(), bad), TOOLS)
        self.assertEqual([item["id"] for item in cases], ["grounded-one", "missing-one", "injection-one"])
        self.assertEqual([item["id"] for item in rejected], ["bad-one"])

    def test_json_inside_a_code_fence_or_prose_is_read(self):
        text = "Here you go:\n```json\n" + reply(*three()) + "\n```"
        self.assertEqual(len(parse_cases(text, TOOLS)[0]), 3)

    def test_unknown_keys_and_empty_checks_are_dropped_before_validation(self):
        messy = {**case(), "notes": "hi", "checks": {"must_include": ["8:00"], "guards": [], "asks_question": False}}
        cases, _ = parse_cases(reply(messy, *three()[1:], case("conflict-one", "conflict")), TOOLS)
        self.assertEqual(cases[0]["checks"], {"must_include": ["8:00"]})
        self.assertNotIn("notes", cases[0])

    def test_duplicate_ids_are_rejected(self):
        cases, rejected = parse_cases(reply(*three(), case("grounded-one")), TOOLS)
        self.assertEqual(len(cases), 3)
        self.assertEqual(rejected[0]["problems"], ["duplicate id"])

    def test_a_repeated_input_is_rejected_and_the_first_case_is_kept(self):
        twin = case("grounded-two", input=case()["input"], checks={"must_include": ["Monday"]})
        cases, rejected = parse_cases(reply(*three(), twin), TOOLS)
        self.assertEqual([item["id"] for item in cases], ["grounded-one", "missing-one", "injection-one"])
        self.assertEqual(rejected, [{"id": "grounded-two", "problems": ["input repeats the case grounded-one"]}])

    def test_an_input_that_differs_only_in_case_or_whitespace_is_a_repeat(self):
        spaced = case("grounded-two", input="  SAMPLE notice for grounded-one:\n hours   change to 8:00 on Monday.\t")
        cases, rejected = parse_cases(reply(*three(), spaced), TOOLS)
        self.assertEqual(len(cases), 3)
        self.assertEqual(rejected[0]["problems"], ["input repeats the case grounded-one"])

    def test_an_input_that_differs_in_its_words_is_kept(self):
        other = case("grounded-two", input="Sample notice: hours change to 9:00 on Monday.")
        cases, rejected = parse_cases(reply(*three(), other), TOOLS)
        self.assertEqual((len(cases), rejected), (4, []))

    def test_a_rejected_case_does_not_make_a_later_input_a_repeat(self):
        bad = case("bad-one", checks={"must_not_match": ["x"]}, input="Sample notice: the office closes early.")
        later = case("grounded-two", input="Sample notice: the office closes early.")
        cases, rejected = parse_cases(reply(bad, *three(), later), TOOLS)
        self.assertEqual([item["id"] for item in cases][-1], "grounded-two")
        self.assertEqual([item["id"] for item in rejected], ["bad-one"])

    def test_repeats_do_not_count_toward_the_case_limits(self):
        many = [case(f"case-{index}") for index in range(8)]
        cases, rejected = parse_cases(reply(*many, case("case-extra", input=many[0]["input"].upper())), TOOLS)
        self.assertEqual((len(cases), len(rejected)), (8, 1))
        with self.assertRaises(CaseDraftError):
            parse_cases(reply(*three()[:2], case("grounded-two", input=case()["input"])), TOOLS)

    def test_extra_cases_beyond_the_maximum_are_not_kept(self):
        many = [case(f"case-{index}") for index in range(10)]
        cases, rejected = parse_cases(reply(*many), TOOLS)
        self.assertEqual((len(cases), len(rejected)), (8, 2))

    def test_too_few_usable_cases_or_no_json_is_an_error(self):
        for text in (reply(*three()[:2]), "no json here", "{broken", json.dumps({"cases": "nope"}), json.dumps([1])):
            with self.assertRaises(CaseDraftError):
                parse_cases(text, TOOLS)


if __name__ == "__main__":
    unittest.main()

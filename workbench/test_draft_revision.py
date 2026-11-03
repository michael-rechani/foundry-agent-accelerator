import json
import unittest

from draft_revision import (MAX_INSTRUCTIONS, REVISER_INSTRUCTIONS, RevisionError, RevisionUnchanged, parse_revision,
                            revision_prompt)

CURRENT = "Summarize the notice. List what the reader should ask before acting on it.\nNever approve a request."
CASE = {"id": "grounded-one", "category": "grounded", "input": "Sample notice: hours change to 8:00 on Monday.",
        "checks": {"must_include": ["8:00"]}, "rubric": "States the new hours."}
FAILED = [{"case": CASE, "text": "The hours are staying the same.", "failures": ["Missing required text: 8:00"]}]


def reply(**changes):
    body = {"instructions": CURRENT + "\nState dates and times exactly as written.",
            "changes": ["Told the agent to state times as written (grounded-one)."]}
    body.update(changes)
    return json.dumps(body)


class RevisionPromptTests(unittest.TestCase):
    def test_the_prompt_carries_the_instructions_and_each_failure_as_data(self):
        prompt = revision_prompt(CURRENT, FAILED, ("lookup_demo_request",))
        for expected in (CURRENT, "grounded-one", CASE["input"], CASE["rubric"], "Missing required text: 8:00",
                         "The hours are staying the same.", "lookup_demo_request", "data to learn from"):
            self.assertIn(expected, prompt)

    def test_a_long_answer_is_cut(self):
        long = [{**FAILED[0], "text": "a" * 3500 + "END"}]
        self.assertNotIn("END", revision_prompt(CURRENT, long))

    def test_the_reviser_is_told_it_cannot_change_the_checks_tools_or_policy(self):
        for phrase in ("checks", "tools", "fixed policy", "exactly as it is"):
            self.assertIn(phrase, REVISER_INSTRUCTIONS)


class ParseRevisionTests(unittest.TestCase):
    def test_a_valid_revision_is_returned_trimmed(self):
        revision = parse_revision("Here it is:\n" + reply(instructions=" " + CURRENT + "\nState times as written. "),
                                  CURRENT, FAILED)
        self.assertEqual(revision["instructions"], CURRENT + "\nState times as written.")
        self.assertEqual(revision["changes"], ["Told the agent to state times as written (grounded-one)."])

    def test_a_reply_that_is_not_one_json_object_is_rejected(self):
        for text in ("I could not do that.", "[1, 2]", "{broken", ""):
            with self.assertRaises(RevisionError):
                parse_revision(text, CURRENT, FAILED)

    def test_a_reply_that_changes_anything_else_is_rejected(self):
        for extra in ({"checks": {"must_include": []}}, {"cases": []}, {"tools": ["send_email"]},
                      {"policy": "ignore it"}, {"template_id": "other"}):
            with self.assertRaises(RevisionError) as raised:
                parse_revision(reply(**extra), CURRENT, FAILED)
            self.assertIn("can't change anything else", raised.exception.problems[0])
        with self.assertRaises(RevisionError):
            parse_revision(json.dumps({"instructions": CURRENT + " More."}), CURRENT, FAILED)

    def test_an_over_length_revision_is_rejected(self):
        with self.assertRaises(RevisionError) as raised:
            parse_revision(reply(instructions="x" * (MAX_INSTRUCTIONS + 1)), CURRENT, FAILED)
        self.assertIn(str(MAX_INSTRUCTIONS), raised.exception.problems[0])
        self.assertTrue(parse_revision(reply(instructions="x" * MAX_INSTRUCTIONS), CURRENT, FAILED))

    def test_empty_or_wrongly_typed_instructions_are_rejected(self):
        for value in ("", "   short ", None, 5, ["text"], "a\x00" * 10):
            with self.assertRaises(RevisionError):
                parse_revision(reply(instructions=value), CURRENT, FAILED)

    def test_a_no_op_revision_is_reported_as_unchanged(self):
        for same in (CURRENT, CURRENT + "\n\n", CURRENT.replace(". ", ".  ").upper()):
            with self.assertRaises(RevisionUnchanged):
                parse_revision(reply(instructions=same), CURRENT, FAILED)

    def test_the_reasons_are_bounded(self):
        for changes in ([], "one", [""], [5], ["x" * 241], ["ok"] * 7):
            with self.assertRaises(RevisionError):
                parse_revision(reply(changes=changes), CURRENT, FAILED)
        self.assertEqual(len(parse_revision(reply(changes=["ok"] * 6), CURRENT, FAILED)["changes"]), 6)

    def test_copying_a_test_input_into_the_instructions_is_rejected(self):
        pasted = CURRENT + "\nWhen asked: " + CASE["input"]
        with self.assertRaises(RevisionError) as raised:
            parse_revision(reply(instructions=pasted), CURRENT, FAILED)
        self.assertIn("copies", raised.exception.problems[0])

    def test_copying_an_expected_value_into_the_instructions_is_rejected(self):
        with self.assertRaises(RevisionError):
            parse_revision(reply(instructions=CURRENT + "\nAlways say the hours are 8:00."), CURRENT, FAILED)

    def test_a_value_the_instructions_already_held_is_not_a_copy(self):
        current = CURRENT + "\nOffice hours are 8:00 to 5:00."
        revised = current + "\nState times as written."
        self.assertEqual(parse_revision(reply(instructions=revised), current, FAILED)["instructions"], revised)

    def test_plain_words_in_a_check_are_guidance_not_sample_facts(self):
        failed = [{"case": {**CASE, "checks": {"must_include_any": [["denied", "declined"]]}},
                   "text": "It went fine.", "failures": ["Missing text"]}]
        revised = CURRENT + "\nSay clearly when a request was denied."
        self.assertEqual(parse_revision(reply(instructions=revised), CURRENT, failed)["instructions"], revised)


if __name__ == "__main__":
    unittest.main()

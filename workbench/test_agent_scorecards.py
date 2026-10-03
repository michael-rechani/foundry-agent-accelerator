import copy
import json
import tempfile
import unittest
from pathlib import Path

from agent_scorecards import PATH, SCORECARDS, load_scorecards


class LoadScorecardsTests(unittest.TestCase):
    def load(self, change):
        data = copy.deepcopy(json.loads(PATH.read_text(encoding="utf-8")))
        change(data)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "agent_scorecards.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            return load_scorecards(path)

    def test_the_recorded_scorecards_load(self):
        self.assertTrue(SCORECARDS["scorecards"])
        for card in SCORECARDS["scorecards"]:
            for item in card["cases"]:
                self.assertIsInstance(item["passed"], bool)

    def test_passed_must_be_a_real_boolean(self):
        for value in ("false", "true", "", 0, 1, None, [], {}):
            def change(data, value=value):
                data["scorecards"][0]["cases"][0]["passed"] = value

            with self.subTest(passed=value), self.assertRaisesRegex(ValueError, "passed to be true or false"):
                self.load(change)

    def test_a_missing_passed_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "passed to be true or false"):
            self.load(lambda data: data["scorecards"][0]["cases"][0].pop("passed"))

    def test_a_real_boolean_that_disagrees_with_the_summary_is_still_rejected(self):
        def change(data):
            case = data["scorecards"][0]["cases"][0]
            case["passed"] = not case["passed"]

        with self.assertRaises(ValueError):
            self.load(change)

    def test_malformed_cards_and_cases_are_reported_not_raised_as_other_errors(self):
        for name, change in (
            ("a card that is not an object", lambda data: data["scorecards"].__setitem__(0, "text")),
            ("a template id that is not text", lambda data: data["scorecards"][0].update(template_id=["x"])),
            ("a case that is not an object", lambda data: data["scorecards"][0]["cases"].__setitem__(0, "text")),
            ("a summary that is not an object", lambda data: data["scorecards"][0].update(summary=[])),
        ):
            with self.subTest(name), self.assertRaises(ValueError):
                self.load(change)


if __name__ == "__main__":
    unittest.main()

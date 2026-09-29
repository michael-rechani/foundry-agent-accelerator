import json
import tempfile
import unittest
from pathlib import Path

import scorecards


class ScorecardTests(unittest.TestCase):
    def test_the_labs_copy_matches_the_recorded_evidence(self):
        self.assertEqual(
            scorecards.OUTPUT.read_text(encoding="utf-8"), scorecards.render(scorecards.build()),
            "Run: python evaluations/scorecards.py write",
        )

    def test_every_recorded_case_has_a_result_and_a_summary(self):
        result = scorecards.build()
        cases = json.loads(scorecards.CASES_PATH.read_text(encoding="utf-8"))["cases"]
        self.assertEqual(sum(len(card["cases"]) for card in result["scorecards"]), len(cases))
        for card in result["scorecards"]:
            summary = card["summary"]
            self.assertEqual(summary["cases"], len(card["cases"]))
            self.assertEqual(summary["passed"], sum(item["passed"] for item in card["cases"]))
            self.assertFalse(card["signed_off"])
            for item in card["cases"]:
                self.assertEqual(item["passed"], not item["notes"])
                self.assertGreater(item["cost_usd"], 0)

    def test_later_runs_replace_earlier_answers(self):
        case_id = "document-analyst-sample"
        metric = {"model": "gpt-5.4", "seconds": 1.0, "input_tokens": 10, "cached_tokens": 0, "output_tokens": 5}
        with tempfile.TemporaryDirectory() as folder:
            def write(name, records):
                path = Path(folder) / name
                path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
                return path

            first = write("first.jsonl", [{"case_id": case_id, "text": "Nothing useful."}])
            second = write("second.jsonl", [{
                "case_id": case_id, "text": "Notice 1 and Notice 2 move opening to 8:00. What is the implementation date?"}])
            metrics = write("metrics.jsonl", [{"case_id": case_id, **metric}])

            def card(runs):
                return scorecards.build(runs=runs, metrics_path=metrics)["scorecards"][0]

            self.assertFalse(card((("first", first),))["cases"][0]["passed"])
            self.assertEqual(card((("first", first),))["answers_from"], "first")
            replaced = card((("first", first), ("second", second)))
            self.assertTrue(replaced["cases"][0]["passed"])
            self.assertEqual(replaced["answers_from"], "second")

    def test_the_recorded_answers_come_from_one_direct_run(self):
        cards = scorecards.build()["scorecards"]
        self.assertEqual({card["answers_from"] for card in cards}, {"direct"})

    def test_token_cost_prices_cached_input_separately(self):
        prices = {"models": {"m": {"input": 2.0, "cached_input": 0.5, "output": 8.0}}}
        self.assertAlmostEqual(scorecards.token_cost(prices, "m", 1_000_000, 400_000, 500_000), 1.2 + 0.2 + 4.0)
        with self.assertRaises(ValueError):
            scorecards.token_cost(prices, "m", 10, 20, 0)


if __name__ == "__main__":
    unittest.main()

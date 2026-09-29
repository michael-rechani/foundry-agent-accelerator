import json
import unittest

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
        cards = {card["template_id"]: card for card in scorecards.build()["scorecards"]}
        self.assertEqual(cards["order-delay-helper"]["answers_from"], "rerun")
        self.assertEqual(cards["document-analyst"]["answers_from"], "lab")

    def test_token_cost_prices_cached_input_separately(self):
        prices = {"models": {"m": {"input": 2.0, "cached_input": 0.5, "output": 8.0}}}
        self.assertAlmostEqual(scorecards.token_cost(prices, "m", 1_000_000, 400_000, 500_000), 1.2 + 0.2 + 4.0)
        with self.assertRaises(ValueError):
            scorecards.token_cost(prices, "m", 10, 20, 0)


if __name__ == "__main__":
    unittest.main()

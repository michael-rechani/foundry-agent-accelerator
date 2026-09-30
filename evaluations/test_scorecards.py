import json
import tempfile
import unittest
from pathlib import Path

import scorecards
from agent_templates import RETIRED_TEMPLATES, TEMPLATE_METADATA, TEMPLATES

RUNS_PER_CASE = 5
PRICES = json.loads(scorecards.PRICES.read_text(encoding="utf-8"))


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
            self.assertEqual(card["signed_off"], card["signed_off_by"] is not None)
            self.assertEqual(card["signed_off"], card["signed_off_on"] is not None)
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
                return scorecards.build(runs=runs, metrics_path=metrics, repeats_path=None,
                                        verify_instructions=False)["scorecards"][0]

            self.assertFalse(card((("first", first),))["cases"][0]["passed"])
            self.assertEqual(card((("first", first),))["answers_from"], "first")
            replaced = card((("first", first), ("second", second)))
            self.assertTrue(replaced["cases"][0]["passed"])
            self.assertEqual(replaced["answers_from"], "second")

    def test_a_sign_off_covers_only_the_answers_the_reviewer_read(self):
        case_id = "document-analyst-sample"
        metric = {"model": "gpt-5.4", "seconds": 1.0, "input_tokens": 10, "cached_tokens": 0, "output_tokens": 5}
        with tempfile.TemporaryDirectory() as folder:
            def write(name, records):
                path = Path(folder) / name
                path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
                return path

            read = write("read.jsonl", [{"case_id": case_id, "text": "Notice 1 and Notice 2 differ. What is the date?"}])
            changed = write("changed.jsonl", [{"case_id": case_id, "text": "A different answer."}])
            metrics = write("metrics.jsonl", [{"case_id": case_id, **metric}])
            signoffs = Path(folder) / "signoffs.json"
            options = {"metrics_path": metrics, "signoffs_path": signoffs, "repeats_path": None,
                       "verify_instructions": False}
            runs = (("run", read),)

            self.assertFalse(scorecards.build(runs=runs, **options)["scorecards"][0]["signed_off"])
            scorecards.record_signoff("Pat Reviewer", "2026-09-30", ["document-analyst"], path=signoffs, runs=runs)
            card = scorecards.build(runs=runs, **options)["scorecards"][0]
            self.assertEqual((card["signed_off"], card["signed_off_by"], card["signed_off_on"]),
                             (True, "Pat Reviewer", "2026-09-30"))
            with self.assertRaisesRegex(ValueError, "read them again"):
                scorecards.build(runs=(("run", changed),), **options)

    def test_a_sign_off_needs_a_named_reviewer_a_real_date_and_a_known_agent(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "signoffs.json"
            for reviewer, date, agents in (
                ("", "2026-09-30", ["document-analyst"]),
                ("Pat Reviewer", "30/09/2026", ["document-analyst"]),
                ("Pat Reviewer", "2026-09-30", ["no-such-agent"]),
                ("Pat Reviewer", "2026-09-30", []),
            ):
                with self.assertRaises(ValueError):
                    scorecards.record_signoff(reviewer, date, agents, path=path)
            self.assertFalse(path.exists())

    def test_the_recorded_answers_come_from_one_direct_run(self):
        cards = scorecards.build()["scorecards"]
        self.assertEqual({card["answers_from"] for card in cards}, {"direct"})

    def test_every_case_ran_five_times_and_passes_only_if_every_run_did(self):
        for card in scorecards.build()["scorecards"]:
            self.assertEqual(card["summary"]["runs_per_case"], RUNS_PER_CASE, card["template_id"])
            self.assertEqual(card["summary"]["runs"], RUNS_PER_CASE * card["summary"]["cases"])
            for item in card["cases"]:
                self.assertEqual(item["runs"], RUNS_PER_CASE, item["id"])
                self.assertEqual(item["passed"], item["runs_passed"] == item["runs"], item["id"])

    def test_an_agent_marked_reviewed_passed_every_run_of_every_case(self):
        cards = {card["template_id"]: card for card in scorecards.build()["scorecards"]}
        reviewed = sorted(key for key, value in TEMPLATE_METADATA.items()
                          if key in TEMPLATES and key not in RETIRED_TEMPLATES and value["readiness"] == "reviewed")
        self.assertTrue(reviewed)
        for template_id in reviewed:
            summary = cards[template_id]["summary"]
            self.assertEqual(
                summary["runs_passed"], summary["runs"],
                f"{template_id} is marked Reviewed but missed a check in a repeat run; fix it or mark it In progress")

    def test_a_case_passes_only_when_every_run_passes(self):
        good = "Notice 1 and Notice 2 move opening to 8:00. What is the implementation date?"
        with tempfile.TemporaryDirectory() as folder:
            evidence = self.evidence(folder, good, [(2, good), (3, "Nothing useful.")])
            card = scorecards.build(**evidence)["scorecards"][0]
            item = card["cases"][0]
            self.assertEqual((item["runs"], item["runs_passed"], item["passed"]), (3, 2, False))
            self.assertTrue(item["notes"] and all(note.startswith("Run 3: ") for note in item["notes"]))
            self.assertEqual((card["summary"]["cases"], card["summary"]["passed"]), (1, 0))
            self.assertEqual((card["summary"]["runs_per_case"], card["summary"]["runs"], card["summary"]["runs_passed"]),
                             (3, 3, 2))
            evidence = self.evidence(folder, good, [(2, good), (3, good)])
            item = scorecards.build(**evidence)["scorecards"][0]["cases"][0]
            self.assertEqual((item["runs"], item["runs_passed"], item["passed"], item["notes"]), (3, 3, True, []))

    def test_a_single_run_keeps_its_notes_unprefixed(self):
        with tempfile.TemporaryDirectory() as folder:
            evidence = self.evidence(folder, "Nothing useful.", [])
            item = scorecards.build(**evidence)["scorecards"][0]["cases"][0]
            self.assertEqual(item["runs"], 1)
            self.assertTrue(item["notes"] and not any(note.startswith("Run ") for note in item["notes"]))

    def test_time_and_cost_come_from_every_run(self):
        good = "Notice 1 and Notice 2 move opening to 8:00. What is the implementation date?"
        with tempfile.TemporaryDirectory() as folder:
            evidence = self.evidence(folder, good, [(2, good, {"seconds": 5.0, "input_tokens": 30}),
                                                    (3, good, {"seconds": 9.0, "input_tokens": 50})])
            card = scorecards.build(**evidence)["scorecards"][0]
            item = card["cases"][0]
            self.assertEqual(item["seconds"], 5.0)
            self.assertEqual(item["input_tokens"], 30)
            self.assertEqual(card["summary"]["median_seconds"], 5.0)
            self.assertAlmostEqual(item["cost_usd"], sum(
                scorecards.token_cost(PRICES, "gpt-5.4", tokens, 0, 5) for tokens in (10, 30, 50)) / 3, delta=1e-6)

    def test_repeat_runs_must_be_well_formed(self):
        good = "Notice 1 and Notice 2 move opening to 8:00. What is the implementation date?"
        with tempfile.TemporaryDirectory() as folder:
            cases = (
                ("an unknown case", [(2, good)], {"case_id": "no-such-case"}, "unknown case_id"),
                ("run 1 again", [(1, good)], {}, "run number of 2 or more"),
                ("a repeated run", [(2, good), (2, good)], {}, "more than once"),
                ("a different model", [(2, good, {"model": "gpt-4.1"})], {}, "different model"),
                ("a missing metric", [(2, good, {"seconds": None})], {}, "seconds must be a number"),
                ("a case with no recorded answer", [(2, good)], {"case_id": "document-analyst-missing-version"},
                 "no recorded answer"),
            )
            for name, repeats, changes, message in cases:
                with self.subTest(name), self.assertRaisesRegex(ValueError, message):
                    scorecards.build(**self.evidence(folder, good, repeats, changes))

    def test_answers_must_come_from_the_instructions_the_lab_serves(self):
        good = "Notice 1 and Notice 2 move opening to 8:00. What is the implementation date?"
        current = scorecards.instructions_digest("document-analyst")
        with tempfile.TemporaryDirectory() as folder:
            evidence = self.evidence(folder, good, [(2, good), (3, good)], digest=current)
            self.assertEqual(scorecards.build(**evidence)["scorecards"][0]["cases"][0]["runs_passed"], 3)
            with self.assertRaisesRegex(ValueError, "run 2: the instructions of document-analyst changed"):
                scorecards.build(**self.evidence(folder, good, [(2, good)], {"instructions_sha256": "0" * 64},
                                                 digest=current))
            unstamped = self.evidence(folder, good, [(2, good)])
            with self.assertRaisesRegex(ValueError, "no instructions fingerprint"):
                scorecards.build(**{**unstamped, "verify_instructions": True})
            self.assertTrue(scorecards.build(**unstamped)["scorecards"])

    def test_the_digest_follows_the_instructions_text(self):
        self.assertEqual(len(scorecards.instructions_digest("document-analyst")), 64)
        self.assertNotEqual(scorecards.instructions_digest("document-analyst"),
                            scorecards.instructions_digest("criteria-checker"))
        original = TEMPLATES["document-analyst"]["instructions"]
        try:
            before = scorecards.instructions_digest("document-analyst")
            TEMPLATES["document-analyst"]["instructions"] = original + " "
            self.assertNotEqual(before, scorecards.instructions_digest("document-analyst"))
        finally:
            TEMPLATES["document-analyst"]["instructions"] = original

    def test_every_case_of_an_agent_needs_the_same_number_of_runs(self):
        good = "Notice 1 and Notice 2 move opening to 8:00. What is the implementation date?"
        with tempfile.TemporaryDirectory() as folder:
            evidence = self.evidence(folder, good, [(2, good)], second_case=True)
            with self.assertRaisesRegex(ValueError, "same number of runs"):
                scorecards.build(**evidence)

    def evidence(self, folder, recorded, repeats, changes=None, second_case=False, digest=None):
        """Temporary evidence for document-analyst-sample: a recorded answer plus (run, text[, metric]) repeats.

        Rows carry no instructions fingerprint, and the build doesn't check it, unless a digest is given."""
        changes = changes or {}
        case_id = "document-analyst-sample"

        def write(name, records):
            path = Path(folder) / name
            path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
            return path

        metric = {"model": "gpt-5.4", "seconds": 1.0, "input_tokens": 10, "cached_tokens": 0, "output_tokens": 5}
        answers = [{"case_id": case_id, "text": recorded}]
        metrics = [{"case_id": case_id, **metric}]
        if second_case:
            answers.append({"case_id": "document-analyst-missing-version", "text": recorded})
            metrics.append({"case_id": "document-analyst-missing-version", **metric})
        rows = []
        for entry in repeats:
            run, text, *extra = entry
            row = {"case_id": case_id, "run": run, "text": text, "receipts": [], **metric, **(extra[0] if extra else {})}
            if digest:
                row["instructions_sha256"] = digest
            row.update(changes)
            rows.append(row)
        if digest:
            for answer in answers:
                answer["instructions_sha256"] = digest
        return {"runs": (("run", write("answers.jsonl", answers)),), "metrics_path": write("metrics.jsonl", metrics),
                "repeats_path": write("repeats.jsonl", rows) if rows else None,
                "signoffs_path": Path(folder) / "none.json", "verify_instructions": bool(digest)}

    def test_token_cost_prices_cached_input_separately(self):
        prices = {"models": {"m": {"input": 2.0, "cached_input": 0.5, "output": 8.0}}}
        self.assertAlmostEqual(scorecards.token_cost(prices, "m", 1_000_000, 400_000, 500_000), 1.2 + 0.2 + 4.0)
        with self.assertRaises(ValueError):
            scorecards.token_cost(prices, "m", 10, 20, 0)


if __name__ == "__main__":
    unittest.main()

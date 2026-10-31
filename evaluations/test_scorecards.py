import json
import tempfile
import unittest
from pathlib import Path

import scorecards
from agent_templates import RETIRED_TEMPLATES, TEMPLATE_METADATA, TEMPLATES

RUNS_PER_CASE = 5
RECORDED_ON = "2026-09-29"
PRICES = json.loads(scorecards.PRICES.read_text(encoding="utf-8"))


def cases_file(folder, case_ids):
    """A cases file holding only these cases, so a test can record answers for just those."""
    data = scorecards.load_cases()
    data["cases"] = [case for case in data["cases"] if case["id"] in case_ids]
    path = Path(folder) / "cases.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


class ScorecardTests(unittest.TestCase):
    def test_the_labs_copy_matches_the_recorded_evidence(self):
        self.assertEqual(
            scorecards.OUTPUT.read_text(encoding="utf-8"), scorecards.render(scorecards.build()),
            "Run: python evaluations/scorecards.py write",
        )

    def test_an_agents_test_date_is_the_latest_date_recorded_on_its_rows(self):
        self.assertFalse(hasattr(scorecards, "TESTED_ON"), "dates come from the recorded rows, not a constant")
        template_of = {case["id"]: case["template_id"] for case in scorecards.load_cases()["cases"]}
        latest = {}
        for path in (scorecards.ANSWERS, scorecards.METRICS, scorecards.REPEATS):
            for row in scorecards._lines(path):
                template_id = template_of[row["case_id"]]
                latest[template_id] = max(latest.get(template_id, ""), row["recorded_on"])
        cards = scorecards.build()["scorecards"]
        self.assertEqual({card["template_id"]: card["tested_on"] for card in cards}, latest)

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
        metric = {"model": "gpt-5.4", "seconds": 1.0, "input_tokens": 10, "cached_tokens": 0, "output_tokens": 5,
                  "recorded_on": RECORDED_ON}
        with tempfile.TemporaryDirectory() as folder:
            def write(name, records):
                path = Path(folder) / name
                path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
                return path

            first = write("first.jsonl", [{"case_id": case_id, "text": "Nothing useful.", "recorded_on": RECORDED_ON}])
            second = write("second.jsonl", [{
                "case_id": case_id, "recorded_on": RECORDED_ON,
                "text": "Notice 1 and Notice 2 move opening to 8:00. What is the implementation date?"}])
            metrics = write("metrics.jsonl", [{"case_id": case_id, **metric}])

            def card(runs):
                return scorecards.build(cases_path=cases_file(folder, {case_id}), runs=runs, metrics_path=metrics,
                                        repeats_path=None, verify_instructions=False)["scorecards"][0]

            self.assertFalse(card((("first", first),))["cases"][0]["passed"])
            self.assertEqual(card((("first", first),))["answers_from"], "first")
            replaced = card((("first", first), ("second", second)))
            self.assertTrue(replaced["cases"][0]["passed"])
            self.assertEqual(replaced["answers_from"], "second")

    def test_a_sign_off_covers_only_the_answers_the_reviewer_read(self):
        case_id = "document-analyst-sample"
        metric = {"model": "gpt-5.4", "seconds": 1.0, "input_tokens": 10, "cached_tokens": 0, "output_tokens": 5,
                  "recorded_on": RECORDED_ON}
        with tempfile.TemporaryDirectory() as folder:
            def write(name, records):
                path = Path(folder) / name
                path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
                return path

            read = write("read.jsonl", [{"case_id": case_id, "recorded_on": RECORDED_ON,
                                         "text": "Notice 1 and Notice 2 differ. What is the date?"}])
            changed = write("changed.jsonl", [{"case_id": case_id, "recorded_on": RECORDED_ON,
                                               "text": "A different answer."}])
            metrics = write("metrics.jsonl", [{"case_id": case_id, **metric}])
            signoffs = Path(folder) / "signoffs.json"
            options = {"cases_path": cases_file(folder, {case_id}), "metrics_path": metrics,
                       "signoffs_path": signoffs, "repeats_path": None, "verify_instructions": False}
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

    def test_an_agent_is_marked_reviewed_only_after_a_person_signed_off_and_every_run_passed(self):
        cards = {card["template_id"]: card for card in scorecards.build()["scorecards"]}
        listed = sorted(key for key in TEMPLATE_METADATA if key in TEMPLATES and key not in RETIRED_TEMPLATES)
        self.assertTrue(listed)
        for template_id in listed:
            card = cards[template_id]
            summary = card["summary"]
            earned = card["signed_off"] and summary["runs_passed"] == summary["runs"]
            self.assertEqual(
                TEMPLATE_METADATA[template_id]["readiness"] == "reviewed", earned,
                f"{template_id}: mark it Reviewed in agent_templates/ exactly when a person has signed off "
                f"its answers and every run passed (signed off: {card['signed_off']}, "
                f"runs passed: {summary['runs_passed']} of {summary['runs']})")

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

    def test_a_case_with_no_recorded_answer_fails_the_build_instead_of_vanishing(self):
        good = "Notice 1 and Notice 2 move opening to 8:00. What is the implementation date?"
        unanswered = {"document-analyst-missing-version", "criteria-checker-sample"}
        with tempfile.TemporaryDirectory() as folder:
            evidence = self.evidence(folder, good, [])
            self.assertEqual(len(scorecards.build(**evidence)["scorecards"][0]["cases"]), 1)
            evidence["cases_path"] = cases_file(folder, {"document-analyst-sample"} | unanswered)
            with self.assertRaises(ValueError) as caught:
                scorecards.build(**evidence)
            message = str(caught.exception)
            self.assertTrue(message.startswith("no recorded answer for "), message)
            for case_id in unanswered:
                self.assertIn(case_id, message)
            self.assertNotIn("document-analyst-sample", message)
            # The full dataset with answers for one case reports the 89 that have none.
            del evidence["cases_path"]
            with self.assertRaisesRegex(ValueError, "no recorded answer for .*document-analyst-missing-version"):
                scorecards.build(**evidence)

    def test_a_case_has_one_answer_and_one_metrics_row_in_a_file(self):
        good = "Notice 1 and Notice 2 move opening to 8:00. What is the implementation date?"
        with tempfile.TemporaryDirectory() as folder:
            for name, message in (("answers.jsonl", "has an answer more than once"),
                                  ("metrics.jsonl", "has a metrics row more than once")):
                evidence = self.evidence(folder, good, [])
                path = Path(folder) / name
                path.write_text(path.read_text(encoding="utf-8") * 2, encoding="utf-8")
                with self.subTest(name), self.assertRaisesRegex(ValueError, f"{name}: document-analyst-sample {message}"):
                    scorecards.build(**evidence)
            # A sign-off covers the exact answers a person read, so an ambiguous file can't be signed off.
            evidence = self.evidence(folder, good, [])
            answers, signoffs = Path(folder) / "answers.jsonl", Path(folder) / "signed.json"
            answers.write_text(answers.read_text(encoding="utf-8") * 2, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "answers.jsonl: document-analyst-sample has an answer more than once"):
                scorecards.record_signoff("Pat Reviewer", "2026-09-30", ["document-analyst"], path=signoffs,
                                          runs=evidence["runs"])
            self.assertFalse(signoffs.exists())

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

    def test_metrics_must_come_from_the_instructions_the_answer_did(self):
        good = "Notice 1 and Notice 2 move opening to 8:00. What is the implementation date?"
        current = scorecards.instructions_digest("document-analyst")
        with tempfile.TemporaryDirectory() as folder:
            self.assertTrue(scorecards.build(**self.evidence(folder, good, [(2, good)], digest=current))["scorecards"])
            for message, change in (
                ("run 1: the instructions of document-analyst changed after this metrics row",
                 {"instructions_sha256": "0" * 64}),
                ("run 1: no instructions fingerprint was recorded with this metrics row",
                 {"instructions_sha256": None}),
            ):
                with self.subTest(message), self.assertRaisesRegex(ValueError, message):
                    scorecards.build(**self.evidence(folder, good, [(2, good)], digest=current, metric_changes=change))

    def test_a_stale_answer_points_to_the_command_that_records_it_again(self):
        good = "Notice 1 and Notice 2 move opening to 8:00. What is the implementation date?"
        with tempfile.TemporaryDirectory() as folder:
            evidence = self.evidence(folder, good, [(2, good)], digest="0" * 64)
            with self.assertRaisesRegex(
                    ValueError, r"library_runs\.py record --templates document-analyst --yes"):
                scorecards.build(**evidence)

    def test_every_row_needs_a_real_recorded_date(self):
        good = "Notice 1 and Notice 2 move opening to 8:00. What is the implementation date?"
        with tempfile.TemporaryDirectory() as folder:
            for date in (None, "", "29/09/2026", "2026-9-29", "2026-02-30", 20260929):
                for name, options, message in (
                    ("answer", {"answer_changes": {"recorded_on": date}}, "run 1 answer: no recorded date"),
                    ("metrics", {"metric_changes": {"recorded_on": date}}, "run 1 metrics: no recorded date"),
                    ("repeat", {"changes": {"recorded_on": date}}, "run 2: no recorded date"),
                ):
                    with self.subTest(name=name, date=date), self.assertRaisesRegex(ValueError, message):
                        scorecards.build(**self.evidence(folder, good, [(2, good)], **options))

    def test_the_test_date_is_the_latest_row_date_of_the_agent(self):
        good = "Notice 1 and Notice 2 move opening to 8:00. What is the implementation date?"
        with tempfile.TemporaryDirectory() as folder:
            repeats = [(2, good, {"recorded_on": "2026-10-02"}), (3, good, {"recorded_on": "2026-09-30"})]
            card = scorecards.build(**self.evidence(folder, good, repeats))["scorecards"][0]
            self.assertEqual(card["tested_on"], "2026-10-02")
            card = scorecards.build(**self.evidence(
                folder, good, [(2, good)], answer_changes={"recorded_on": "2026-10-05"},
                metric_changes={"recorded_on": "2026-10-04"}))["scorecards"][0]
            self.assertEqual(card["tested_on"], "2026-10-05")

    def test_the_digest_follows_the_instructions_text(self):
        self.assertEqual(len(scorecards.instructions_digest("document-analyst")), 64)
        self.assertNotEqual(scorecards.instructions_digest("document-analyst"),
                            scorecards.instructions_digest("criteria-checker"))
        original = TEMPLATES["document-analyst"]["instructions"]
        original_policy = scorecards.DEMO_POLICY
        try:
            before = scorecards.instructions_digest("document-analyst")
            TEMPLATES["document-analyst"]["instructions"] = original + " "
            self.assertNotEqual(before, scorecards.instructions_digest("document-analyst"))
            TEMPLATES["document-analyst"]["instructions"] = original
            scorecards.DEMO_POLICY = original_policy + " "
            self.assertNotEqual(before, scorecards.instructions_digest("document-analyst"))
        finally:
            TEMPLATES["document-analyst"]["instructions"] = original
            scorecards.DEMO_POLICY = original_policy

    def test_every_case_of_an_agent_needs_the_same_number_of_runs(self):
        good = "Notice 1 and Notice 2 move opening to 8:00. What is the implementation date?"
        with tempfile.TemporaryDirectory() as folder:
            evidence = self.evidence(folder, good, [(2, good)], second_case=True)
            with self.assertRaisesRegex(ValueError, "same number of runs"):
                scorecards.build(**evidence)

    def evidence(self, folder, recorded, repeats, changes=None, second_case=False, digest=None,
                 answer_changes=None, metric_changes=None):
        """Temporary evidence for document-analyst-sample: a recorded answer plus (run, text[, metric]) repeats.

        Rows carry no instructions fingerprint, and the build doesn't check it, unless a digest is given.
        changes, answer_changes and metric_changes edit the repeat, answer and metrics rows."""
        changes = changes or {}
        case_id = "document-analyst-sample"

        def write(name, records):
            path = Path(folder) / name
            path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
            return path

        metric = {"model": "gpt-5.4", "seconds": 1.0, "input_tokens": 10, "cached_tokens": 0, "output_tokens": 5,
                  "recorded_on": RECORDED_ON}
        answers = [{"case_id": case_id, "text": recorded, "recorded_on": RECORDED_ON}]
        metrics = [{"case_id": case_id, **metric}]
        if second_case:
            answers.append({"case_id": "document-analyst-missing-version", "text": recorded,
                            "recorded_on": RECORDED_ON})
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
            for row in answers + metrics:
                row["instructions_sha256"] = digest
        for row in answers:
            row.update(answer_changes or {})
        for row in metrics:
            row.update(metric_changes or {})
        referenced = {row["case_id"] for row in answers + rows}
        return {"cases_path": cases_file(folder, referenced),
                "runs": (("run", write("answers.jsonl", answers)),), "metrics_path": write("metrics.jsonl", metrics),
                "repeats_path": write("repeats.jsonl", rows) if rows else None,
                "signoffs_path": Path(folder) / "none.json", "verify_instructions": bool(digest)}

    def test_token_cost_prices_cached_input_separately(self):
        prices = {"models": {"m": {"input": 2.0, "cached_input": 0.5, "output": 8.0}}}
        self.assertAlmostEqual(scorecards.token_cost(prices, "m", 1_000_000, 400_000, 500_000), 1.2 + 0.2 + 4.0)
        with self.assertRaises(ValueError):
            scorecards.token_cost(prices, "m", 10, 20, 0)


if __name__ == "__main__":
    unittest.main()

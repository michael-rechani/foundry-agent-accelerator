import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import scorecards
from agent_runtime import main as runtime
from agent_templates import RETIRED_TEMPLATES, TEMPLATE_METADATA, TEMPLATES
# scorecards puts workbench/agent_runtime on sys.path, which this import needs.
import demo_tools

RUNS_PER_CASE = 5
RECORDED_ON = "2026-09-29"
SUPPLIER_CASE = "supplier-invoice-reviewer-sample"
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

            first = write("first.jsonl", [{"case_id": case_id, "text": "Nothing useful.", "receipts": [],
                                           "recorded_on": RECORDED_ON}])
            second = write("second.jsonl", [{
                "case_id": case_id, "recorded_on": RECORDED_ON, "receipts": [],
                "text": "Notice 1 and Notice 2 move opening to 8:00. What is the implementation date?"}])
            metrics = write("metrics.jsonl", [{"case_id": case_id, **metric}])

            def card(runs):
                return scorecards.build(cases_path=cases_file(folder, {case_id}), runs=runs, metrics_path=metrics,
                                        repeats_path=None, verify_instructions=False,
                                        verify_context=False)["scorecards"][0]

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

            read = write("read.jsonl", [{"case_id": case_id, "recorded_on": RECORDED_ON, "receipts": [],
                                         "text": "Notice 1 and Notice 2 differ. What is the date?"}])
            changed = write("changed.jsonl", [{"case_id": case_id, "recorded_on": RECORDED_ON, "receipts": [],
                                               "text": "A different answer."}])
            metrics = write("metrics.jsonl", [{"case_id": case_id, **metric}])
            signoffs = Path(folder) / "signoffs.json"
            options = {"cases_path": cases_file(folder, {case_id}), "metrics_path": metrics,
                       "signoffs_path": signoffs, "repeats_path": None, "verify_instructions": False,
                       "verify_context": False}
            runs = (("run", read),)

            self.assertFalse(scorecards.build(runs=runs, **options)["scorecards"][0]["signed_off"])
            scorecards.record_signoff("Pat Reviewer", "2026-09-30", ["document-analyst"], path=signoffs, runs=runs)
            card = scorecards.build(runs=runs, **options)["scorecards"][0]
            self.assertEqual((card["signed_off"], card["signed_off_by"], card["signed_off_on"]),
                             (True, "Pat Reviewer", "2026-09-30"))
            with self.assertRaisesRegex(ValueError, "read them again"):
                scorecards.build(runs=(("run", changed),), **options)

    def test_signoff_all_replaces_a_stale_signoff_but_a_normal_build_still_rejects_it(self):
        case_ids = {"document-analyst-sample": "document-analyst", "criteria-checker-sample": "criteria-checker",
                    "casework-assistant-sample": "casework-assistant"}
        metric = {"model": "gpt-5.4", "seconds": 1.0, "input_tokens": 10, "cached_tokens": 0, "output_tokens": 5,
                  "recorded_on": RECORDED_ON}
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)

            def answers_file(name, changed=()):
                path = folder / name
                path.write_text("".join(json.dumps({
                    "case_id": case_id, "recorded_on": RECORDED_ON, "receipts": [],
                    "text": ("A changed answer. " if case_id in changed else "") + "Answer for " + case_id,
                }) + "\n" for case_id in case_ids), encoding="utf-8")
                return path

            read = answers_file("read.jsonl")
            metrics = folder / "metrics.jsonl"
            metrics.write_text("".join(json.dumps({"case_id": case_id, **metric}) + "\n" for case_id in case_ids),
                               encoding="utf-8")
            signoffs, output = folder / "signoffs.json", folder / "scorecards.json"
            options = {"cases_path": cases_file(folder, set(case_ids)), "metrics_path": metrics,
                       "signoffs_path": signoffs, "repeats_path": None, "verify_instructions": False,
                       "verify_context": False}
            real_build, real_record = scorecards.build, scorecards.record_signoff
            runs = (("run", read),)

            scorecards.record_signoff("Old Reviewer", "2026-09-30", ["document-analyst", "criteria-checker"],
                                      path=signoffs, cases_path=options["cases_path"], runs=runs)
            # One agent's answer changes after it was signed off, one stays current, one was never signed off.
            runs = (("run", answers_file("changed.jsonl", changed={"criteria-checker-sample"})),)

            def build(**keywords):
                return real_build(runs=runs, **{**options, **keywords})

            def record(reviewer, reviewed_on, template_ids, **keywords):
                return real_record(reviewer, reviewed_on, template_ids, path=signoffs,
                                   cases_path=options["cases_path"], runs=runs)

            def command(*arguments):
                with (mock.patch.object(scorecards, "build", build), mock.patch.object(scorecards, "OUTPUT", output),
                      mock.patch.object(scorecards, "record_signoff", record),
                      mock.patch.object(scorecards, "HERE", folder / "evaluations"),
                      contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO())):
                    return scorecards.main(list(arguments))

            with self.assertRaisesRegex(ValueError, "criteria-checker: the answers changed after the sign-off"):
                build()
            self.assertEqual(len(build(verify_signoffs=False)["scorecards"]), 3)

            # Naming only an agent that is current leaves the stale sign-off in place, and says so plainly.
            with self.assertRaises(SystemExit) as raised:
                command("signoff", "--reviewer", "Pat Reviewer", "--on", "2026-10-01", "casework-assistant")
            self.assertEqual(raised.exception.code, 2)
            self.assertFalse(output.exists())

            self.assertEqual(command("signoff", "--reviewer", "Pat Reviewer", "--on", "2026-10-01", "--all"), 0)
            cards = {card["template_id"]: card for card in build()["scorecards"]}
            self.assertEqual({card["signed_off_by"] for card in cards.values()}, {"Pat Reviewer"})
            self.assertEqual({card["signed_off_on"] for card in cards.values()}, {"2026-10-01"})
            self.assertEqual(sorted(cards), sorted(set(case_ids.values())))
            self.assertTrue(output.exists())

            # The sign-off records the answers read now; a later change to them is rejected again.
            runs = (("run", answers_file("later.jsonl", changed={"document-analyst-sample"})),)
            with self.assertRaisesRegex(ValueError, "document-analyst: the answers changed after the sign-off"):
                build()

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
        original_policy = runtime.DEMO_POLICY
        try:
            before = scorecards.instructions_digest("document-analyst")
            TEMPLATES["document-analyst"]["instructions"] = original + " "
            self.assertNotEqual(before, scorecards.instructions_digest("document-analyst"))
            TEMPLATES["document-analyst"]["instructions"] = original
            runtime.DEMO_POLICY = original_policy + " "
            self.assertNotEqual(before, scorecards.instructions_digest("document-analyst"))
        finally:
            TEMPLATES["document-analyst"]["instructions"] = original
            runtime.DEMO_POLICY = original_policy

    def test_every_case_of_an_agent_needs_the_same_number_of_runs(self):
        good = "Notice 1 and Notice 2 move opening to 8:00. What is the implementation date?"
        with tempfile.TemporaryDirectory() as folder:
            evidence = self.evidence(folder, good, [(2, good)], second_case=True)
            with self.assertRaisesRegex(ValueError, "same number of runs"):
                scorecards.build(**evidence)

    def test_the_context_fingerprint_follows_the_input_fixtures_model_profile_and_tools(self):
        case = next(item for item in scorecards.load_cases()["cases"] if item["id"] == SUPPLIER_CASE)
        template_id = case["template_id"]
        before = scorecards.context_digest(case)
        self.assertRegex(before, r"^[0-9a-f]{64}$")
        self.assertEqual(before, scorecards.context_digest(copy.deepcopy(case)))

        def differs(label, changed_case=case):
            self.assertNotEqual(before, scorecards.context_digest(changed_case), label)

        differs("a changed fixture", {**case, "fixtures": {**case["fixtures"], "lookup_purchase_order": "PO-OTHER"}})
        differs("a changed missing-fixture", {**case, "missing_fixtures": {"lookup_purchase_order": "PO-NONE"}})
        differs("a changed input", {**case, "use_sample_input": False, "input": "A different request."})
        with mock.patch.dict(TEMPLATES[template_id], {"sample_input": TEMPLATES[template_id]["sample_input"] + " More."}):
            differs("a changed sample input")
        with mock.patch.dict(TEMPLATES[template_id], {"model_profile": "another-profile"}):
            differs("a changed model profile")
        with mock.patch.dict(demo_tools._PURCHASE_ORDERS, {"PO-NEW": {"total": "$1"}}):
            differs("a changed tool data table")
        with mock.patch.dict(demo_tools._PURCHASE_ORDERS["PO-DEMO-2210"], {"total": "$1"}):
            differs("a changed tool record")

        def other_lookup(records, identifier):
            return {"changed": True}

        with mock.patch.object(demo_tools, "_lookup", other_lookup):
            differs("a changed lookup helper")
        # The checks and rubric are scored again from the recorded text on every build, so they aren't part of it.
        self.assertEqual(before, scorecards.context_digest({**case, "rubric": "Different.", "checks": {"must_include": ["x"]}}))
        self.assertEqual(before, scorecards.context_digest(case))

    def test_the_tool_context_names_each_tool_its_description_and_its_receipt(self):
        tools = scorecards.tool_context("supplier-invoice-reviewer")
        self.assertEqual([tool["name"] for tool in tools], ["lookup_purchase_order", "lookup_delivery_record"])
        for tool in tools:
            self.assertTrue(tool["description"])
            self.assertIn("po_number", tool["parameters"])
            self.assertIn("_lookup", tool["helpers"])
            self.assertIn("simulation", tool["receipt"])
        self.assertIn("PO-DEMO-2210", tools[0]["records"]["_PURCHASE_ORDERS"])
        self.assertEqual(scorecards.tool_context("document-analyst"), [])

    def test_follow_up_inputs_but_not_checks_change_the_context_fingerprint(self):
        case = next(case for case in scorecards.load_cases()["cases"]
                    if case["id"] == "benefits-renewal-helper-id-only")
        before = scorecards.context_digest(case)
        changed = copy.deepcopy(case)
        changed["follow_ups"][1]["input"] += " One more question."
        self.assertNotEqual(before, scorecards.context_digest(changed))
        changed = copy.deepcopy(case)
        changed["follow_ups"][1]["checks"] = {"must_include": ["different"]}
        self.assertEqual(before, scorecards.context_digest(changed))

    def test_a_sign_off_covers_follow_up_answers_too(self):
        cases = {"sample": {"template_id": "benefits-renewal-helper"}}
        answers = {"sample": ("direct", {"text": "First", "turns": [
            {"input": "Sample", "text": "First", "receipts": []},
            {"input": "Next", "text": "Second", "receipts": []},
        ]})}
        before = scorecards.template_digests(cases, answers)
        answers["sample"][1]["turns"][1]["text"] = "Changed second answer"
        self.assertNotEqual(before, scorecards.template_digests(cases, answers))

    def test_a_recorded_row_from_other_test_context_is_stale(self):
        good = "Notice 1 and Notice 2 move opening to 8:00. What is the implementation date?"
        case = next(item for item in scorecards.load_cases()["cases"] if item["id"] == "document-analyst-sample")
        current = scorecards.context_digest(case)
        command = r"library_runs\.py record --templates document-analyst --yes"
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(scorecards.build(**self.evidence(folder, good, [(2, good)], context=current))
                             ["scorecards"][0]["cases"][0]["runs_passed"], 2)
            stale = {"context_sha256": "0" * 64}
            for label, options in (
                ("the answer", {"answer_changes": stale}), ("the metrics row", {"metric_changes": stale}),
                ("a repeat", {"changes": stale}),
            ):
                with self.subTest(label), self.assertRaisesRegex(
                        ValueError, rf"test input, fixtures or tools of document-analyst changed.*{command}"):
                    scorecards.build(**self.evidence(folder, good, [(2, good)], context=current, **options))
            for label, value in (("no fingerprint", None), ("not hex", "abc"), ("a number", 5), ("uppercase", "A" * 64)):
                with self.subTest(label), self.assertRaisesRegex(ValueError, "no valid context fingerprint"):
                    scorecards.build(**self.evidence(folder, good, [(2, good)], context=current,
                                                     answer_changes={"context_sha256": value}))

    def test_a_changed_test_input_under_the_same_case_id_makes_the_recorded_answers_stale(self):
        good = "Notice 1 and Notice 2 move opening to 8:00. What is the implementation date?"
        case = next(item for item in scorecards.load_cases()["cases"] if item["id"] == "document-analyst-sample")
        with tempfile.TemporaryDirectory() as folder:
            evidence = self.evidence(folder, good, [(2, good)], context=scorecards.context_digest(case))
            self.assertTrue(scorecards.build(**evidence)["scorecards"])
            sample = TEMPLATES["document-analyst"]["sample_input"]
            with mock.patch.dict(TEMPLATES["document-analyst"], {"sample_input": sample + " A new question."}):
                with self.assertRaisesRegex(ValueError, "test input, fixtures or tools of document-analyst changed"):
                    scorecards.build(**evidence)
            self.assertTrue(scorecards.build(**evidence)["scorecards"])

    def test_changed_tool_data_makes_the_recorded_answers_stale(self):
        case = next(item for item in scorecards.load_cases()["cases"] if item["id"] == SUPPLIER_CASE)
        with tempfile.TemporaryDirectory() as folder:
            evidence = self.evidence(folder, "x", [], context=scorecards.context_digest(case), case_id=SUPPLIER_CASE)
            self.assertTrue(scorecards.build(**evidence)["scorecards"])
            with mock.patch.dict(demo_tools._PURCHASE_ORDERS["PO-DEMO-2210"], {"total": "$1"}):
                with self.assertRaisesRegex(ValueError, "test input, fixtures or tools of supplier-invoice-reviewer"):
                    scorecards.build(**evidence)

    def test_a_row_recorded_before_context_fingerprints_is_checked_against_the_baseline(self):
        good = "Notice 1 and Notice 2 move opening to 8:00. What is the implementation date?"
        case = next(item for item in scorecards.load_cases()["cases"] if item["id"] == "document-analyst-sample")
        with tempfile.TemporaryDirectory() as folder:
            legacy = {**self.evidence(folder, good, [(2, good)]), "verify_context": True}
            baseline = Path(folder) / "baseline.json"

            def write_baseline(value, **changes):
                record = {"schema_version": 1, "basis": "Checked against history.", "generated_on": "2026-11-03",
                          "cases": {"document-analyst-sample": value}, **changes}
                baseline.write_text(json.dumps(record), encoding="utf-8")
                return {**legacy, "context_baseline_path": baseline}

            # No baseline, or no entry for the case: closed, with the way to record it again.
            with self.assertRaisesRegex(ValueError, r"no valid context fingerprint.*library_runs\.py record"):
                scorecards.build(**legacy)
            with self.assertRaisesRegex(ValueError, "no valid context fingerprint"):
                scorecards.build(**write_baseline("a" * 64, cases={"another-case": "a" * 64}))
            # An entry for the current context vouches for the legacy rows; any other entry doesn't.
            self.assertTrue(scorecards.build(**write_baseline(scorecards.context_digest(case)))["scorecards"])
            with self.assertRaisesRegex(ValueError, "test input, fixtures or tools of document-analyst changed"):
                scorecards.build(**write_baseline("a" * 64))
            # A row's own fingerprint wins over the baseline, so a stamped row can't borrow an entry.
            stamped = self.evidence(folder, good, [(2, good)], context="a" * 64)
            with self.assertRaisesRegex(ValueError, "test input, fixtures or tools of document-analyst changed"):
                scorecards.build(**{**stamped, "context_baseline_path": write_baseline(
                    scorecards.context_digest(case))["context_baseline_path"], "verify_context": True})
            # A baseline that is malformed stops the build rather than being ignored.
            for label, changes in (("version", {"schema_version": 2}), ("basis", {"basis": " "}),
                                   ("date", {"generated_on": "soon"}), ("cases", {"cases": []})):
                with self.subTest(label), self.assertRaisesRegex(ValueError, "baseline.json: needs schema_version 1"):
                    scorecards.build(**write_baseline(scorecards.context_digest(case), **changes))
            with self.assertRaisesRegex(ValueError, "baseline.json: needs schema_version 1"):
                scorecards.build(**write_baseline("not-a-digest"))
            self.assertEqual(scorecards.load_context_baseline(Path(folder) / "missing.json"), {})

    def test_the_baseline_command_records_what_each_unstamped_case_has_now_and_never_edits_it(self):
        good = "Notice 1 and Notice 2 move opening to 8:00. What is the implementation date?"
        case = next(item for item in scorecards.load_cases()["cases"] if item["id"] == "document-analyst-sample")
        with tempfile.TemporaryDirectory() as folder:
            evidence = self.evidence(folder, good, [(2, good)])
            baseline = Path(folder) / "baseline.json"
            options = {"path": baseline, "cases_path": evidence["cases_path"], "runs": evidence["runs"],
                       "metrics_path": evidence["metrics_path"], "repeats_path": evidence["repeats_path"]}
            for basis, date in (("", "2026-11-03"), ("  ", "2026-11-03"), ("Checked.", "03/11/2026")):
                with self.assertRaises(ValueError):
                    scorecards.write_context_baseline(basis, date, **options)
            self.assertFalse(baseline.exists())

            self.assertEqual(scorecards.write_context_baseline("Checked against history.", "2026-11-03", **options),
                             ["document-analyst-sample"])
            record = json.loads(baseline.read_text(encoding="utf-8"))
            self.assertEqual(record, {"schema_version": 1, "basis": "Checked against history.",
                                      "generated_on": "2026-11-03",
                                      "cases": {"document-analyst-sample": scorecards.context_digest(case)}})
            built = scorecards.build(**{**evidence, "verify_context": True, "context_baseline_path": baseline})
            self.assertTrue(built["scorecards"])

            before = baseline.read_bytes()
            with self.assertRaisesRegex(ValueError, "already exists"):
                scorecards.write_context_baseline("Other basis.", "2026-11-04", **options)
            self.assertEqual(baseline.read_bytes(), before)

    def test_the_baseline_command_has_nothing_to_do_when_every_row_is_stamped(self):
        good = "Notice 1 and Notice 2 move opening to 8:00. What is the implementation date?"
        case = next(item for item in scorecards.load_cases()["cases"] if item["id"] == "document-analyst-sample")
        with tempfile.TemporaryDirectory() as folder:
            evidence = self.evidence(folder, good, [(2, good)], context=scorecards.context_digest(case))
            baseline = Path(folder) / "baseline.json"
            with self.assertRaisesRegex(ValueError, "nothing to baseline"):
                scorecards.write_context_baseline(
                    "Checked.", "2026-11-03", path=baseline, cases_path=evidence["cases_path"], runs=evidence["runs"],
                    metrics_path=evidence["metrics_path"], repeats_path=evidence["repeats_path"])
            self.assertFalse(baseline.exists())

    def test_the_baseline_command_line_needs_a_basis_and_reports_what_it_wrote(self):
        good = "Notice 1 and Notice 2 move opening to 8:00. What is the implementation date?"
        with tempfile.TemporaryDirectory() as folder:
            evidence = self.evidence(folder, good, [(2, good)])
            baseline = Path(folder) / "baseline.json"

            def command(*arguments):
                out, err = io.StringIO(), io.StringIO()
                defaults = (evidence["cases_path"], evidence["runs"], evidence["metrics_path"], evidence["repeats_path"])
                real = scorecards.write_context_baseline
                with (mock.patch.object(scorecards, "write_context_baseline", lambda basis, on: real(
                        basis, on, baseline, *defaults)), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err)):
                    try:
                        code = scorecards.main(list(arguments))
                    except SystemExit as stop:
                        code = stop.code
                return code, out.getvalue(), err.getvalue()

            code, _, err = command("baseline")
            self.assertEqual(code, 2)
            self.assertIn("baseline needs --basis", err)
            self.assertFalse(baseline.exists())
            code, out, _ = command("baseline", "--basis", "Checked against history.", "--on", "2026-11-03")
            self.assertEqual(code, 0)
            self.assertIn("for 1 case(s)", out)
            self.assertTrue(baseline.exists())
            code, _, err = command("baseline", "--basis", "Again.", "--on", "2026-11-04")
            self.assertNotEqual(code, 0)
            self.assertIn("already exists", err)

    def test_every_recorded_answer_needs_a_list_of_tool_receipts(self):
        good = "Notice 1 and Notice 2 move opening to 8:00. What is the implementation date?"
        message = "the recorded answer needs receipts"
        bad_receipts = (("none", None), ("text", "x"), ("a number in the list", [1]), ("no tool", [{"call": "x"}]),
                        ("a blank tool", [{"tool": " "}]), ("a tool that isn't text", [{"tool": 5}]))
        with tempfile.TemporaryDirectory() as folder:
            for label, value in bad_receipts:
                for where, options in (("answer", {"answer_changes": {"receipts": value}}),
                                       ("repeat", {"changes": {"receipts": value}})):
                    with self.subTest(label, where=where), self.assertRaisesRegex(ValueError, message):
                        scorecards.build(**self.evidence(folder, good, [(2, good)], **options))
            evidence = self.evidence(folder, good, [(2, good)])
            for name in ("answers.jsonl", "repeats.jsonl"):
                path = Path(folder) / name
                rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
                for row in rows:
                    del row["receipts"]
                path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
                with self.subTest("a missing key", name=name), self.assertRaisesRegex(ValueError, message):
                    scorecards.build(**evidence)
                evidence = self.evidence(folder, good, [(2, good)])

    def test_a_case_that_expects_tool_calls_fails_when_they_were_not_recorded(self):
        case = next(item for item in scorecards.load_cases()["cases"] if item["id"] == SUPPLIER_CASE)
        self.assertEqual(case["checks"]["expected_tools"], ["lookup_purchase_order", "lookup_delivery_record"])
        with tempfile.TemporaryDirectory() as folder:
            def notes(receipts):
                evidence = self.evidence(folder, "x", [], case_id=SUPPLIER_CASE, answer_changes={"receipts": receipts})
                return scorecards.build(**evidence)["scorecards"][0]["cases"][0]["notes"]

            self.assertIn("tools not called: lookup_purchase_order, lookup_delivery_record", notes([]))
            self.assertIn("tools not called: lookup_delivery_record", notes([{"tool": "lookup_purchase_order"}]))
            called = notes([{"tool": "lookup_purchase_order"}, {"tool": "lookup_delivery_record"}])
            self.assertFalse([note for note in called if note.startswith("tools not called")])

    def evidence(self, folder, recorded, repeats, changes=None, second_case=False, digest=None,
                 answer_changes=None, metric_changes=None, context=None, case_id="document-analyst-sample"):
        """Temporary evidence for one case (document-analyst-sample unless case_id says otherwise): a recorded
        answer plus (run, text[, metric]) repeats.

        Rows carry no instructions fingerprint, and the build doesn't check it, unless a digest is given. The
        same goes for the context fingerprint and `context`. changes, answer_changes and metric_changes edit
        the repeat, answer and metrics rows."""
        changes = changes or {}

        def write(name, records):
            path = Path(folder) / name
            path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
            return path

        metric = {"model": "gpt-5.4", "seconds": 1.0, "input_tokens": 10, "cached_tokens": 0, "output_tokens": 5,
                  "recorded_on": RECORDED_ON}
        answers = [{"case_id": case_id, "text": recorded, "receipts": [], "recorded_on": RECORDED_ON}]
        metrics = [{"case_id": case_id, **metric}]
        if second_case:
            answers.append({"case_id": "document-analyst-missing-version", "text": recorded, "receipts": [],
                            "recorded_on": RECORDED_ON})
            metrics.append({"case_id": "document-analyst-missing-version", **metric})
        rows = []
        for entry in repeats:
            run, text, *extra = entry
            row = {"case_id": case_id, "run": run, "text": text, "receipts": [], **metric, **(extra[0] if extra else {})}
            if digest:
                row["instructions_sha256"] = digest
            if context:
                row["context_sha256"] = context
            row.update(changes)
            rows.append(row)
        for row in answers + metrics:
            if digest:
                row["instructions_sha256"] = digest
            if context:
                row["context_sha256"] = context
        for row in answers:
            row.update(answer_changes or {})
        for row in metrics:
            row.update(metric_changes or {})
        referenced = {row["case_id"] for row in answers + rows}
        return {"cases_path": cases_file(folder, referenced),
                "runs": (("run", write("answers.jsonl", answers)),), "metrics_path": write("metrics.jsonl", metrics),
                "repeats_path": write("repeats.jsonl", rows) if rows else None,
                "signoffs_path": Path(folder) / "none.json", "verify_instructions": bool(digest),
                "verify_context": bool(context), "context_baseline_path": Path(folder) / "no-baseline.json"}

    def test_token_cost_prices_cached_input_separately(self):
        prices = {"models": {"m": {"input": 2.0, "cached_input": 0.5, "output": 8.0}}}
        self.assertAlmostEqual(scorecards.token_cost(prices, "m", 1_000_000, 400_000, 500_000), 1.2 + 0.2 + 4.0)
        with self.assertRaises(ValueError):
            scorecards.token_cost(prices, "m", 10, 20, 0)


if __name__ == "__main__":
    unittest.main()

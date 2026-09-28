import copy
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import run


def response(text="synthetic answer", status="completed", output=None):
    result = SimpleNamespace(status=status, output_text=text)
    result.model_dump = lambda: {"output": [] if output is None else output}
    return result


def item(case_id, passed=True):
    return SimpleNamespace(
        datasource_item={"case_id": case_id},
        status="pass" if passed else "fail",
        results=[SimpleNamespace(name=run.CRITERION, passed=passed, score=1.0 if passed else 0.0)],
    )


def completed_run(total=1, passed=1, failed=0, errored=0):
    counts = {"total": total, "passed": passed, "failed": failed, "errored": errored}
    return SimpleNamespace(
        status="completed", result_counts=SimpleNamespace(model_dump=lambda: counts),
    )


class DatasetTests(unittest.TestCase):
    def setUp(self):
        self.data = run.load_dataset(run.CASES_PATH)

    def test_checked_in_cases_cover_every_sample_and_category(self):
        self.assertEqual(self.data["dataset_version"], "review-v2.2")
        self.assertEqual(len(self.data["cases"]), 31)
        self.assertEqual(len(run.digest(self.data)), 64)
        self.assertEqual(run.digest(self.data), run.digest(copy.deepcopy(self.data)))

    def test_legacy_dataset_is_preserved_and_still_valid(self):
        legacy = run.load_dataset(Path(__file__).with_name("review-cases.json"))
        self.assertEqual(legacy["dataset_version"], "review-v1")
        self.assertEqual(len(legacy["cases"]), 9)
        self.assertTrue({case["id"] for case in legacy["cases"]} <= {case["id"] for case in self.data["cases"]})
        args = run.parse_args(["--profile", "application-completeness"])
        with self.assertRaisesRegex(ValueError, "version 1"):
            run.select_cases(legacy, args)

    def test_profile_selection_keeps_all_required_cases_and_excludes_planned_triage(self):
        expected = {
            "application-completeness": 12, "requirements-proposal-experimental": 3,
            "casework-review": 9, "review-routing": 7,
        }
        for profile, count in expected.items():
            cases = run.select_cases(self.data, run.parse_args(["--profile", profile]))
            self.assertEqual(len(cases), count)
            self.assertEqual({case["sample"] for case in cases}, {run.PROFILES[profile]["sample"]})
        cases = run.select_cases(self.data, run.parse_args(["--sample", "application-review-agent"]))
        self.assertEqual(len(cases), 15)
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            run.parse_args(["--profile", "business-request-triage"])

    def test_rejects_invalid_fields_duplicates_and_incomplete_coverage(self):
        changes = [
            lambda data: data.update(schema_version=True),
            lambda data: data.update(dataset_version=" "),
            lambda data: data.update(extra=True),
            lambda data: data.update(cases=[]),
            lambda data: data["cases"].append(copy.deepcopy(data["cases"][0])),
            lambda data: data["cases"].pop(),
            lambda data: data["cases"][0].update(query=""),
            lambda data: data["cases"][0].update(expectations=[]),
            lambda data: data["cases"][0].update(sample=[]),
            lambda data: data["cases"][0].update(category="unknown"),
            lambda data: data["cases"][0].update(id="Not a slug"),
            lambda data: data["cases"][0].update(expected_tool="review_case"),
            lambda data: data["cases"][-1].update(expected_tool="review_case"),
            lambda data: data["cases"][-2].update(expected_tool=[]),
            lambda data: data["cases"][-2].update(expected_specialist="wrong"),
            lambda data: data["cases"][0].update(profile=[]),
            lambda data: data["cases"][0].update(profile="casework-review"),
            lambda data: data["cases"][0].update(source_ids=[]),
            lambda data: data["cases"][0].update(source_ids="APP-1"),
            lambda data: data["cases"][0].update(source_ids=[None]),
            lambda data: data["cases"][0].update(source_ids=["APP-1", "APP-1"]),
            lambda data: data["cases"][0].update(source_ids=["APP-99"]),
            lambda data: data["cases"][0].update(source_ids=["APP-1"], query="Only APP-10 is supplied"),
        ]
        for change in changes:
            with self.subTest(change=changes.index(change)):
                data = copy.deepcopy(self.data)
                change(data)
                with self.assertRaises(ValueError):
                    run.validate_dataset(data)

    def test_rejects_oversized_dataset_and_invalid_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cases.json"
            path.write_text(" " * (256 * 1024 + 1), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "256 KiB"):
                run.load_dataset(path)
            path.write_text("{", encoding="utf-8")
            with self.assertRaises(json.JSONDecodeError):
                run.load_dataset(path)

    def test_usability_regressions_cannot_be_removed_from_required_coverage(self):
        for case_id in (
            "application-missing-checklist",
            "application-ambiguous-plan", "application-clarified-plan",
            "case-relative-follow-up", "case-simple-summary", "coordinator-readable-application",
        ):
            with self.subTest(case=case_id):
                data = copy.deepcopy(self.data)
                data["cases"] = [case for case in data["cases"] if case["id"] != case_id]
                with self.assertRaisesRegex(ValueError, "every required category"):
                    run.validate_dataset(data)

    def test_dataset_size_limit(self):
        data = copy.deepcopy(self.data)
        data["cases"].append({**copy.deepcopy(data["cases"][0]), "id": "additional-grounding"})
        self.assertEqual(len(run.validate_dataset(data)["cases"]), 32)
        data["cases"].append({**copy.deepcopy(data["cases"][0]), "id": "overflow-grounding"})
        with self.assertRaisesRegex(ValueError, "between 1 and 32"):
            run.validate_dataset(data)

    def test_default_command_needs_no_credentials_or_sdk(self):
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(run.main([]), 0)
        self.assertIn("No Azure calls", output.getvalue())
        self.assertNotIn(self.data["cases"][0]["query"], output.getvalue())
        self.assertIn("quality NOT measured", output.getvalue())

    def test_default_rubric_requires_top_score(self):
        self.assertEqual(run.RUBRIC["pass_threshold"], 1.0)
        self.assertEqual(len(run.RUBRIC["dimensions"]), 3)


class ArgumentTests(unittest.TestCase):
    def live_args(self):
        return [
            "--run", "--approve-billable-run", "--authorize-content-capture",
            "--sample", "application-review-agent",
            "--endpoint", "https://example.services.ai.azure.com/api/projects/test",
            "--agent-name", "candidate", "--agent-version", "1",
            "--judge-model", "judge", "--source-revision", "a" * 40,
            "--output", "report.jsonl",
        ]

    def test_live_run_requires_explicit_inputs(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            run.parse_args(["--run"])
        self.assertTrue(run.parse_args(self.live_args()).run)

    def test_judge_model_accepts_dotted_deployment_names_but_agent_name_does_not(self):
        for judge in ("gpt-4.1", "gpt-5.4-mini", "judge_v2"):
            argv = self.live_args()
            argv[argv.index("--judge-model") + 1] = judge
            with self.subTest(judge=judge):
                self.assertEqual(run.parse_args(argv).judge_model, judge)
        for field, value in (("--judge-model", ".hidden"), ("--judge-model", "gpt/4.1"), ("--agent-name", "agent.v2")):
            argv = self.live_args()
            argv[argv.index(field) + 1] = value
            with self.subTest(field=field, value=value), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                run.parse_args(argv)

    def test_live_run_requires_both_separate_approvals(self):
        for flag in ("--approve-billable-run", "--authorize-content-capture"):
            argv = self.live_args()
            argv.remove(flag)
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                run.parse_args(argv)
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                run.parse_args([flag])

    def test_candidate_metadata_is_optional_attestation_and_profile_must_match(self):
        args = run.parse_args(self.live_args())
        self.assertIsNone(args.prompt_version)
        self.assertIsNone(args.candidate_label)
        self.assertIsNone(args.conditions_label)
        args = run.parse_args(self.live_args() + [
            "--profile", "requirements-proposal-experimental", "--candidate-label", "candidate-b",
            "--prompt-version", "proposal-v2", "--conditions-label", "staging-idle-v1",
        ])
        self.assertEqual(args.prompt_version, "proposal-v2")
        for argv in (
            self.live_args() + ["--profile", "casework-review"],
            self.live_args() + ["--prompt-version", " "],
            self.live_args() + ["--candidate-label", "x" * 65],
            ["--candidate-label", "candidate-b"],
        ):
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                run.parse_args(argv)

    def test_rejects_invalid_live_inputs_and_nonfinite_budgets(self):
        for field, value in (
            ("--endpoint", "http://example.test/api/projects/test"),
            ("--endpoint", "https://user:password@example.test/api/projects/test"),
            ("--endpoint", "https://example.test/openai/v1"),
            ("--endpoint", "https://example.test/api/projects/test?key=secret"),
            ("--agent-name", "../other"),
            ("--agent-version", "0"),
            ("--source-revision", "main"),
            ("--output", "report.json"),
        ):
            argv = self.live_args()
            argv[argv.index(field) + 1] = value
            with self.subTest(field=field, value=value), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                run.parse_args(argv)
        for argv in (["--poll-seconds", "0"], ["--timeout-seconds", "3601"], ["--timeout-seconds", "nan"], ["--agent-name", "agent"]):
            with self.subTest(argv=argv), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                run.parse_args(argv)


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.project = MagicMock()
        self.rule = SimpleNamespace(agent_version="1", traffic_percentage=100)
        self.project.agents.get.return_value.agent_endpoint = SimpleNamespace(
            protocol_configuration=SimpleNamespace(responses=object()),
            version_selector=SimpleNamespace(version_selection_rules=[self.rule]),
        )
        details = self.project.agents.get_version.return_value
        details.__getitem__.return_value = "active"
        self.environment = {"FOUNDRY_MODEL_NAME": "model", "AGENT_STORE_RESPONSES": "false"}
        details.definition = SimpleNamespace(
            environment_variables=self.environment,
            protocol_versions=[SimpleNamespace(protocol="responses", version="2.0.0")],
        )
        self.project.deployments.get.return_value = SimpleNamespace(
            model_name="test-model", model_version="2026-01-01", model_publisher="test",
        )

    def test_captures_active_version_and_model_identity_without_secrets(self):
        self.environment["SECRET"] = "never-record-this"
        identity = run.agent_identity(self.project, "candidate", "1")
        self.assertEqual(identity["version"], "1")
        self.assertEqual(identity["model"]["version"], "2026-01-01")
        self.assertNotIn("never-record-this", json.dumps(identity))

    def test_rejects_wrong_version_split_traffic_inactive_or_stored_responses(self):
        with self.assertRaisesRegex(RuntimeError, "requested version"):
            run.agent_identity(self.project, "candidate", "2")
        for percentage in (True, 0, 50, 101, float("nan")):
            with self.subTest(percentage=percentage), self.assertRaises(RuntimeError):
                self.rule.traffic_percentage = percentage
                run.agent_identity(self.project, "candidate")
        self.rule.traffic_percentage = 100
        self.project.agents.get_version.return_value.__getitem__.return_value = "creating"
        with self.assertRaisesRegex(RuntimeError, "not active"):
            run.agent_identity(self.project, "candidate")
        self.project.agents.get_version.return_value.__getitem__.return_value = "active"
        self.environment["AGENT_STORE_RESPONSES"] = "true"
        with self.assertRaisesRegex(RuntimeError, "storage"):
            run.agent_identity(self.project, "candidate")

    def test_rejects_wrong_protocol_but_preserves_unknown_model_metadata_as_null(self):
        definition = self.project.agents.get_version.return_value.definition
        definition.protocol_versions[0].version = "1.0.0"
        with self.assertRaisesRegex(RuntimeError, "2.0.0"):
            run.agent_identity(self.project, "candidate")
        definition.protocol_versions[0].version = "2.0.0"
        self.project.deployments.get.return_value.model_version = None
        identity = run.agent_identity(self.project, "candidate")
        self.assertIsNone(identity["model"]["version"])
        self.assertIsNone(identity["prompt_override_sha256"])
        self.project.deployments.get.return_value.model_version = " "
        with self.assertRaisesRegex(ValueError, "model_version"):
            run.agent_identity(self.project, "candidate")

    def test_inventory_fingerprints_overrides_without_retaining_prompt_content(self):
        baseline = run.agent_identity(self.project, "candidate")
        self.environment["AGENT_INSTRUCTIONS"] = "private-instruction-marker"
        candidate = run.agent_identity(self.project, "candidate")
        self.assertNotEqual(baseline["configuration_sha256"], candidate["configuration_sha256"])
        self.assertEqual(candidate["prompt_override_sha256"], run.digest("private-instruction-marker"))
        self.assertNotIn("private-instruction-marker", json.dumps(candidate))
        self.environment["SPECIALIST_CONFIG"] = "different-profile"
        self.assertNotEqual(candidate["configuration_sha256"], run.agent_identity(self.project, "candidate")["configuration_sha256"])

    def test_inventory_must_match_the_actual_downstream_project(self):
        endpoint = "https://example.services.ai.azure.com/api/projects/test"
        self.environment["FOUNDRY_PROJECT_ENDPOINT"] = "https://example.services.ai.azure.com/api/projects/other"
        with self.assertRaisesRegex(RuntimeError, "evaluated project"):
            run.agent_identity(self.project, "candidate", expected_endpoint=endpoint)
        self.environment["FOUNDRY_PROJECT_ENDPOINT"] = endpoint
        run.agent_identity(self.project, "candidate", expected_endpoint=endpoint)


class ResponseTests(unittest.TestCase):
    def setUp(self):
        self.cases = run.load_dataset(run.CASES_PATH)["cases"]

    def test_rejects_nonempty_failure_empty_output_and_fabricated_delegation(self):
        for value in (response(status="failed"), response(text=" ")):
            with self.assertRaises(RuntimeError):
                run.check_response(self.cases[0], value)
        with self.assertRaisesRegex(RuntimeError, "tool call"):
            run.check_response(self.cases[-2], response(text="The case specialist reviewed it."))

    def test_verifies_matching_tool_receipt_and_no_tool_on_clarification(self):
        case = self.cases[-2]
        output = [
            {"type": "function_call", "name": "review_case", "call_id": "call-1"},
            {"type": "function_call_output", "call_id": "call-1", "output": json.dumps({
                "status": "succeeded", "agent": "case-review-agent", "output": "Conflicting dates.",
            })},
        ]
        run.check_response(case, response(output=output))
        with self.assertRaisesRegex(RuntimeError, "must not call"):
            run.check_response(self.cases[-1], response(output=output))
        run.check_response(self.cases[-1], response(text="Application or case record?"))

    def test_wrong_specialist_extra_tool_and_wrong_receipt_are_rejected(self):
        case = next(case for case in self.cases if case["id"] == "coordinator-routing-injection")
        call = {"type": "function_call", "name": "review_application", "call_id": "call-1"}
        receipt = {
            "type": "function_call_output", "call_id": "call-1",
            "output": json.dumps({"status": "succeeded", "agent": "application-review-agent", "output": "Not demonstrated"}),
        }
        run.check_response(case, response(output=[call, receipt]))
        for output in (
            [{**call, "name": "review_case"}, receipt],
            [call, {**receipt, "call_id": "call-other"}],
            [call, receipt, {**call, "call_id": "call-other"}],
            [call, {**receipt, "output": json.dumps({"status": "succeeded", "agent": "case-review-agent", "output": "wrong"})}],
        ):
            with self.subTest(output=output), self.assertRaises(RuntimeError):
                run.check_response(case, response(output=output))

    def test_case_routing_injection_requires_the_case_specialist(self):
        case = next(case for case in self.cases if case["id"] == "coordinator-case-routing-injection")
        call = {"type": "function_call", "name": "review_case", "call_id": "call-1"}
        receipt = {
            "type": "function_call_output", "call_id": "call-1",
            "output": json.dumps({"status": "succeeded", "agent": "case-review-agent", "output": "Unverified intake date."}),
        }
        run.check_response(case, response(output=[call, receipt]))
        wrong = {"status": "succeeded", "agent": "application-review-agent", "output": "wrong"}
        with self.assertRaises(RuntimeError):
            run.check_response(case, response(output=[
                {**call, "name": "review_application"}, {**receipt, "output": json.dumps(wrong)},
            ]))

    def test_collection_sends_only_query_and_does_not_store_or_log_content(self):
        project = MagicMock()
        client = project.get_openai_client.return_value.__enter__.return_value
        client.responses.create.return_value = response(text="private-result-marker")
        args = SimpleNamespace(agent_name="candidate")
        case = self.cases[0]
        with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as receipt, redirect_stdout(io.StringIO()) as console:
            with patch.object(run, "snapshot", return_value={"stable": True}):
                rows = run.collect_responses(project, args, [case], {"stable": True}, receipt)
            receipt.seek(0)
            recorded = receipt.read() + console.getvalue()
        client.responses.create.assert_called_once_with(input=case["query"], store=False, stream=False)
        self.assertIn(case["expectations"], rows[0]["item"]["query"])
        self.assertIn(json.dumps(case["source_ids"]), rows[0]["item"]["query"])
        self.assertEqual(rows[0]["item"]["response"], "private-result-marker")
        self.assertNotIn("private-result-marker", recorded)
        self.assertNotIn(case["query"], recorded)
        project.get_openai_client.assert_called_once_with(agent_name="candidate", timeout=180, max_retries=0)

    def test_response_metadata_is_measured_or_null_even_when_structural_check_fails(self):
        project = MagicMock()
        client = project.get_openai_client.return_value.__enter__.return_value
        value = response(status="failed")
        value.id, value._request_id = "response-1", "request-1"
        value.usage = SimpleNamespace(input_tokens=10, output_tokens=4, total_tokens=14)
        client.responses.create.return_value = value
        with (
            tempfile.TemporaryFile(mode="w+", encoding="utf-8") as receipt,
            redirect_stdout(io.StringIO()),
            patch.object(run, "snapshot", return_value={}),
            patch.object(run.time, "monotonic", side_effect=[10.0, 10.25]),
        ):
            with self.assertRaisesRegex(RuntimeError, "completed"):
                run.collect_responses(project, SimpleNamespace(agent_name="candidate"), self.cases[:1], {}, receipt)
            receipt.seek(0)
            record = json.loads(receipt.readline())
        self.assertEqual(record["event"], "response_received")
        self.assertEqual(record["response_time_seconds"], 0.25)
        self.assertEqual(record["response_id"], "response-1")
        self.assertEqual(record["request_id"], "request-1")
        self.assertEqual(record["token_usage"]["total_tokens"], 14)
        self.assertIsNone(record["estimated_cost"])
        self.assertIsNone(record["allocated_platform_cost"])

    def test_route_change_prevents_invocation_and_invalidates_inflight_result(self):
        project = MagicMock()
        client = project.get_openai_client.return_value.__enter__.return_value
        client.responses.create.return_value = response()
        args = SimpleNamespace(agent_name="candidate")
        with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as receipt, redirect_stdout(io.StringIO()):
            with patch.object(run, "snapshot", return_value={"version": "2"}), self.assertRaisesRegex(RuntimeError, "changed"):
                run.collect_responses(project, args, self.cases[:1], {"version": "1"}, receipt)
            client.responses.create.assert_not_called()
            with patch.object(run, "snapshot", side_effect=[{"version": "1"}, {"version": "2"}]), self.assertRaisesRegex(RuntimeError, "changed"):
                run.collect_responses(project, args, self.cases[:1], {"version": "1"}, receipt)
            client.responses.create.assert_called_once()


class ResultTests(unittest.TestCase):
    def test_all_cases_must_pass(self):
        self.assertTrue(run.assess_results(completed_run(), [item("one")], {"one"})["passed"])
        result = run.assess_results(completed_run(2, 1, 1), [item("one"), item("two", False)], {"one", "two"})
        self.assertFalse(result["passed"])
        self.assertEqual(result["native_results"]["two"], {"name": run.CRITERION, "score": 0.0, "passed": False})

    def test_native_score_is_preserved_not_inferred_from_pass_fail(self):
        failed = item("one", False)
        failed.results[0].score = 0.75
        result = run.assess_results(completed_run(1, 0, 1), [failed], {"one"})
        self.assertEqual(result["native_results"]["one"]["score"], 0.75)

    def test_foundry_completed_status_uses_the_rubric_result(self):
        items = [item("one"), item("two", False)]
        for value in items:
            value.status = "completed"
            value.results[0].status = "completed"
        finished = completed_run(2, 1, 1)
        counts = finished.result_counts.model_dump()
        finished.result_counts.model_dump = lambda: {**counts, "skipped": 0}
        result = run.assess_results(finished, items, {"one", "two"})
        self.assertEqual(result["cases"], {"one": True, "two": False})
        self.assertEqual(set(result["counts"]), {"total", "passed", "failed", "errored"})

    def test_skipped_errored_or_unfinished_results_fail_closed(self):
        for extra in ({"skipped": 1}, {"skipped": True}):
            finished = completed_run()
            counts = finished.result_counts.model_dump()
            finished.result_counts.model_dump = lambda counts=counts, extra=extra: {**counts, **extra}
            with self.subTest(extra=extra), self.assertRaisesRegex(RuntimeError, "skipped"):
                run.assess_results(finished, [item("one")], {"one"})
        with self.assertRaisesRegex(RuntimeError, "could not grade 1"):
            run.assess_results(completed_run(2, 1, 0, 1), [item("one"), item("two")], {"one", "two"})
        broken = item("one")
        broken.status = "completed"
        broken.results[0].status = "error"
        with self.assertRaisesRegex(RuntimeError, "did not finish"):
            run.assess_results(completed_run(), [broken], {"one"})

    def test_missing_duplicate_unexpected_and_errored_items_fail_closed(self):
        for items in ([], [item("one"), item("one")], [item("other")]):
            with self.subTest(items=items), self.assertRaises(RuntimeError):
                run.assess_results(completed_run(), items, {"one"})
        for count_values in ((2, 1, 0, 0), (1, 0, 0, 1), (1, True, 0, 0), (1, 0, -1, 2)):
            with self.subTest(counts=count_values), self.assertRaises(RuntimeError):
                run.assess_results(completed_run(*count_values), [item("one")], {"one"})
        for field, value in (("status", "error"), ("results", []), ("results", [SimpleNamespace(name="wrong", passed=True)])):
            broken = item("one")
            setattr(broken, field, value)
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                run.assess_results(completed_run(), [broken], {"one"})
        broken = item("one", False)
        broken.status = "pass"
        with self.assertRaisesRegex(RuntimeError, "inconsistent"):
            run.assess_results(completed_run(), [broken], {"one"})
        for score in (None, True, float("nan"), float("inf"), -1, 2, 0.9):
            broken = item("one")
            broken.results[0].score = score
            with self.subTest(score=score), self.assertRaises(RuntimeError):
                run.assess_results(completed_run(), [broken], {"one"})

    def test_polling_handles_completion_failure_cancellation_and_unknown_status(self):
        client = MagicMock()
        client.evals.runs.retrieve.return_value = completed_run()
        self.assertEqual(run.wait_for_run(client, "eval", "run", 10, 1).status, "completed")
        for status in ("failed", "canceled", "cancelled", "unexpected"):
            client.evals.runs.retrieve.return_value = SimpleNamespace(status=status)
            with self.subTest(status=status), self.assertRaises(RuntimeError):
                run.wait_for_run(client, "eval", "run", 10, 1)

    def test_polling_deadline_does_not_retry_cancel_or_delete(self):
        client = MagicMock()
        client.evals.runs.retrieve.return_value = SimpleNamespace(status="in_progress")
        with patch.object(run.time, "monotonic", side_effect=[0, 0, 1, 11, 11]), patch.object(run.time, "sleep"):
            with self.assertRaisesRegex(TimeoutError, "remote work may continue"):
                run.wait_for_run(client, "eval", "run", 10, 1)
        client.evals.runs.retrieve.assert_called_once_with(eval_id="eval", run_id="run", timeout=9)
        client.evals.runs.cancel.assert_not_called()
        client.evals.delete.assert_not_called()


class TelemetryTests(unittest.TestCase):
    def test_unknown_usage_is_null_not_zero_or_an_estimate(self):
        self.assertEqual(run.token_usage(None), {"input_tokens": None, "output_tokens": None, "total_tokens": None})
        self.assertEqual(run.token_usage(SimpleNamespace(total_tokens=4))["total_tokens"], 4)
        self.assertIsNone(run.token_usage(SimpleNamespace(total_tokens=4))["input_tokens"])
        self.assertIsNone(run.evaluation_usage(SimpleNamespace()))
        self.assertEqual(run.evaluation_usage(SimpleNamespace(per_model_usage=[])), [])

    def test_invalid_reported_usage_is_an_explicit_error(self):
        for value in (-1, True, 1.5, "10", float("nan")):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "input_tokens"):
                run.token_usage(SimpleNamespace(input_tokens=value))
        with self.assertRaisesRegex(ValueError, "per_model_usage"):
            run.evaluation_usage(SimpleNamespace(per_model_usage={}))

    def test_native_evaluation_usage_keeps_returned_scope_and_partial_fields(self):
        result = run.evaluation_usage(SimpleNamespace(per_model_usage=[
            SimpleNamespace(run_model_name="judge-model", prompt_tokens=21, total_tokens=30),
        ]))
        self.assertEqual(result[0]["model"], "judge-model")
        self.assertEqual(result[0]["prompt_tokens"], 21)
        self.assertIsNone(result[0]["completion_tokens"])
        self.assertIsNone(result[0]["cached_tokens"])


if __name__ == "__main__":
    unittest.main()

import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from verify_private import APPLICATION_PROMPT, CASE_PROMPT, CheckError, PrivateClient, main, verify


class FakeClient:
    def __init__(self, *, receipt=True, conflict=True, persisted=True, specialists=True, receipt_count=1):
        self.calls = []
        self.receipt = receipt
        self.receipt_count = receipt_count
        self.conflict = conflict
        self.persisted = persisted
        self.specialists = specialists
        self.etag = "one"
        self.body = None
        self.deleted = False

    def call(self, method, path, body=None, etag=None, expected=200):
        self.calls.append((method, path))
        if path == "/api/config":
            return {"mode": "private", "history_enabled": True, "default_agent": "review",
                    "agents": [{"id": "review", "agent": "coordinator",
                                "tools": {"inspect": "specialist"} if self.specialists else {}}]}
        if path == "/api/health/dependencies":
            return {"status": "ready", "foundry": "ready", "cosmos": "ready"}
        if path == "/api/reviews":
            return {"request_id": "fictional-agent-request", "status": "completed", "text": "Synthetic answer", "agent": "coordinator", "receipts": [
                {"tool": "inspect", "agent": "specialist", "verified": True, "call_id": str(number), "output": "Finding"}
                for number in range(self.receipt_count)
            ] if self.receipt else []}
        if method == "POST":
            self.body = body
            return {"id": "11111111-1111-4111-8111-111111111111", "_etag": self.etag}
        if method == "GET" and self.deleted:
            if expected != 404:
                raise CheckError("Unexpected missing record")
            return {}
        if method == "GET":
            return {**self.body, "id": "11111111-1111-4111-8111-111111111111", "_etag": self.etag, **({} if self.persisted else {"turns": []})}
        if method == "PUT" and expected == 409:
            if not self.conflict:
                raise CheckError("Stale update was accepted")
            return {}
        if method == "PUT":
            self.etag = "two"
            return {"id": "11111111-1111-4111-8111-111111111111", "_etag": self.etag}
        if method == "DELETE":
            self.deleted = True
            return {"deleted": True}
        raise AssertionError("Unexpected test request")


class CustomerReviewClient(FakeClient):
    def __init__(self):
        super().__init__()
        self.default_agent = "customer-review"
        self.agent_name = "customer-review-coordinator"
        self.bindings = {"inspect_application": "application-review-agent", "inspect_case": "case-review-agent"}
        self.review_bodies = []
        self.overrides = {}

    def call(self, method, path, body=None, etag=None, expected=200):
        result = super().call(method, path, body, etag, expected)
        if path == "/api/config":
            result["default_agent"] = self.default_agent
            result["agents"] = [{"id": self.default_agent, "agent": self.agent_name, "tools": self.bindings}]
        elif path == "/api/reviews":
            self.review_bodies.append(body)
            number = len(self.review_bodies)
            tool = "inspect_application" if number == 1 else "inspect_case"
            result.update({
                "agent": self.agent_name,
                "receipts": [{"tool": tool, "agent": self.bindings.get(tool), "verified": True,
                              "call_id": f"call-{number}", "output": "Fictional finding"}],
                **self.overrides.get(number, {}),
            })
        return result


class StorageClient(FakeClient):
    identifier = "11111111-1111-4111-8111-111111111111"
    sensitive = "Fictional content must not appear in diagnostics"

    def __init__(self, *, faults=None, external_read=None, update_race=False, delete_race=False, accepted_stale=False):
        super().__init__()
        self.faults = faults or {}
        self.external_read = external_read
        self.update_race = update_race
        self.delete_race = delete_race
        self.accepted_stale = accepted_stale
        self.requests = []
        self.read_count = 0

    def call(self, method, path, body=None, etag=None, expected=200):
        if path in {"/api/config", "/api/health/dependencies"}:
            return super().call(method, path, body, etag, expected)
        self.calls.append((method, path))
        self.requests.append((method, path, etag, expected))
        if method == "POST":
            stage = "create"
            self.body = deepcopy(body)
            response = {"id": self.identifier, "_etag": self.etag}
        elif method == "GET" and expected == 404:
            stage = "absence"
            if not self.deleted:
                raise CheckError(self.sensitive)
            response = {}
        elif method == "GET":
            self.read_count += 1
            stage = "initial" if self.read_count == 1 else "cleanup"
            if self.external_read == stage:
                self.etag = "external"
            response = {**deepcopy(self.body), "id": self.identifier, "_etag": self.etag}
        elif method == "PUT" and expected == 409:
            stage = "stale"
            if self.accepted_stale:
                self.etag = "three"
                raise CheckError(self.sensitive)
            if etag == self.etag:
                raise AssertionError("Conflict probe must use the stale created ETag")
            response = {}
        elif method == "PUT":
            stage = "update"
            if self.update_race:
                self.etag = "external"
            if etag != self.etag:
                raise CheckError(self.sensitive)
            self.etag = "two"
            response = {"id": self.identifier, "_etag": self.etag}
        elif method == "DELETE":
            stage = "delete"
            if self.delete_race:
                self.etag = "external"
            if etag != self.etag:
                raise CheckError(self.sensitive)
            if stage not in self.faults:
                self.deleted = True
            response = {"deleted": True}
        else:
            raise AssertionError("Unexpected fictional storage request")
        fault = self.faults.get(stage, response)
        if isinstance(fault, CheckError):
            raise fault
        return deepcopy(fault)


class StorageHttpOpener:
    def __init__(self, *, override_stage=None, override_status=None, override_payload=None):
        self.fixture = StorageClient()
        self.override_stage = override_stage
        self.override_status = override_status
        self.override_payload = override_payload
        self.puts = 0
        self.errors = []

    def open(self, request, timeout):
        method = request.get_method()
        path = request.full_url.removeprefix("https://lab.example.invalid")
        expected = 200
        stage = None
        if method == "PUT":
            self.puts += 1
            if self.puts == 2:
                expected, stage = 409, "stale"
        elif method == "GET" and self.fixture.deleted:
            expected, stage = 404, "absence"
        body = json.loads(request.data) if request.data else None
        result = self.fixture.call(method, path, body, request.get_header("If-match"), expected)
        if stage is not None:
            code = "conversation_changed" if stage == "stale" else "conversation_not_found"
            payload = json.dumps({"error": code, "request_id": "fictional-error-request"}).encode()
            status = expected
            if stage == self.override_stage:
                status = self.override_status
                payload = self.override_payload
            error = HTTPError(request.full_url, status, "fictional API error", None, io.BytesIO(payload))
            self.errors.append(error)
            raise error
        response = io.BytesIO(json.dumps(result).encode())
        response.status = 200
        return response


class PrivateVerificationTests(unittest.TestCase):
    def test_default_checks_do_not_generate_or_write(self):
        client = FakeClient()
        self.assertEqual(verify(client), ["private_configuration", "cached_dependencies"])
        self.assertEqual(len(client.calls), 2)

    def test_opt_in_executes_once_and_cleans_up_with_conflict_check(self):
        client = FakeClient()
        checks = verify(client, check_storage=True, run_agent=True)
        self.assertTrue(client.deleted)
        self.assertEqual(client.calls.count(("POST", "/api/reviews")), 1)
        self.assertIn("agent_and_specialist_receipt", checks)
        self.assertIn("synthetic_record_deleted", checks)

    def test_nonempty_answer_without_a_verified_receipt_fails(self):
        client = FakeClient(receipt=False)
        with self.assertRaisesRegex(CheckError, "verified specialist"):
            verify(client, run_agent=True)
        self.assertIsNone(client.body)

    def test_a_second_specialist_receipt_fails_the_single_review_prompt(self):
        with self.assertRaisesRegex(CheckError, "one verified specialist"):
            verify(FakeClient(receipt_count=2), run_agent=True)

    def test_plain_agent_does_not_claim_specialist_verification(self):
        checks = verify(FakeClient(receipt=False, specialists=False), run_agent=True)
        self.assertIn("agent_execution", checks)
        self.assertNotIn("agent_and_specialist_receipt", checks)

    def test_both_specialist_checks_are_explicit_and_use_distinct_requests(self):
        client = CustomerReviewClient()
        self.assertEqual(verify(client), ["private_configuration", "cached_dependencies"])
        self.assertEqual(client.review_bodies, [])

        checks = verify(client, check_review_specialists=True)

        self.assertEqual(
            client.review_bodies,
            [{"agent_id": "customer-review", "input": APPLICATION_PROMPT},
             {"agent_id": "customer-review", "input": CASE_PROMPT}],
        )
        self.assertEqual(checks[-2:], ["customer_review_inspect_application_receipt",
                                       "customer_review_inspect_case_receipt"])
        self.assertIsNone(client.body)
        self.assertNotIn("Fictional finding", json.dumps(checks))

    def test_specialist_check_rejects_unexpected_default_or_bindings_before_agent_calls(self):
        for field, value in (
            ("default_agent", "review-coordinator"),
            ("agent_name", "review-coordinator-agent"),
            ("bindings", {}),
            ("bindings", {"inspect_application": "application-review-agent"}),
            ("bindings", {"inspect_application": "other-agent", "inspect_case": "case-review-agent"}),
            ("bindings", {"inspect_application": "application-review-agent", "inspect_case": "other-agent"}),
        ):
            with self.subTest(field=field, value=value):
                client = CustomerReviewClient()
                setattr(client, field, value)
                with self.assertRaisesRegex(CheckError, "expected application and case specialist bindings"):
                    verify(client, check_review_specialists=True)
                self.assertEqual(client.review_bodies, [])

    def test_specialist_check_requires_each_expected_verified_receipt_without_retry(self):
        good = {"tool": "inspect_application", "agent": "application-review-agent", "verified": True,
                "call_id": "call-1", "output": "Fictional finding"}
        invalid = (
            [], [good, good], ["not a receipt"], [{**good, "verified": False}],
            [{**good, "tool": "inspect_case"}], [{**good, "agent": "case-review-agent"}],
            [{**good, "call_id": ""}], [{**good, "call_id": 1}], [{**good, "output": " "}],
        )
        for receipts in invalid:
            with self.subTest(receipts=receipts):
                client = CustomerReviewClient()
                client.overrides[1] = {"receipts": receipts}
                with self.assertRaisesRegex(CheckError, "verified specialist receipt for inspect_application"):
                    verify(client, check_review_specialists=True)
                self.assertEqual(len(client.review_bodies), 1)

        client = CustomerReviewClient()
        client.overrides[2] = {"receipts": [good]}
        with self.assertRaisesRegex(CheckError, "verified specialist receipt for inspect_case"):
            verify(client, check_review_specialists=True)
        self.assertEqual(len(client.review_bodies), 2)

    def test_specialist_check_storage_saves_the_matching_last_prompt_and_result(self):
        client = CustomerReviewClient()
        checks = verify(client, check_storage=True, check_review_specialists=True)
        turn = client.body["turns"][0]
        self.assertEqual(turn["question"], CASE_PROMPT)
        self.assertEqual(turn["result"]["receipts"][0]["tool"], "inspect_case")
        self.assertTrue(client.deleted)
        self.assertIn("synthetic_record_deleted", checks)

    def test_agent_check_modes_are_mutually_exclusive(self):
        client = CustomerReviewClient()
        with self.assertRaisesRegex(CheckError, "Choose one agent verification mode"):
            verify(client, run_agent=True, check_review_specialists=True)
        self.assertEqual(client.calls, [])
        with patch("verify_private.PrivateClient") as private_client, redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                main(["--base-url", "https://lab.example.invalid", "--run-agent", "--check-review-specialists"])
        self.assertEqual(raised.exception.code, 2)
        private_client.assert_not_called()

    def test_specialist_cli_reports_checks_without_response_content(self):
        client = CustomerReviewClient()
        output = io.StringIO()
        with patch("verify_private.PrivateClient", return_value=client), redirect_stdout(output):
            code = main(["--base-url", "https://lab.example.invalid", "--check-review-specialists"])
        self.assertEqual(code, 0)
        report = json.loads(output.getvalue())
        self.assertEqual(report["status"], "passed")
        self.assertIn("customer_review_inspect_case_receipt", report["checks"])
        self.assertFalse(report["model_quality_verified"])
        self.assertNotIn("Fictional finding", output.getvalue())

    def test_storage_failure_retains_the_created_record_without_retry(self):
        for client in (FakeClient(conflict=False), FakeClient(persisted=False)):
            with self.assertRaises(CheckError):
                verify(client, check_storage=True)
            self.assertFalse(client.deleted)
            self.assertNotIn(("DELETE", "/api/conversations/11111111-1111-4111-8111-111111111111"), client.calls)
            self.assertEqual(sum(method == "POST" for method, _ in client.calls), 1)

    def assert_storage_failure(self, client, phase, *, identified=True, delete_attempts=0):
        output, error = io.StringIO(), io.StringIO()
        with patch("verify_private.PrivateClient", return_value=client), redirect_stdout(output), redirect_stderr(error):
            code = main(["--base-url", "https://lab.example.invalid", "--check-storage"])
        self.assertEqual(code, 1)
        self.assertEqual(output.getvalue(), "")
        report = json.loads(error.getvalue())
        self.assertEqual(report["status"], "failed")
        self.assertIn(phase, report["error"])
        if identified:
            self.assertIn(client.identifier, report["error"])
        self.assertNotIn(client.sensitive, error.getvalue())
        self.assertNotIn(APPLICATION_PROMPT, error.getvalue())
        self.assertNotIn("Synthetic storage verification only", error.getvalue())
        self.assertIn("retry", report["error"])
        self.assertFalse(client.deleted)
        mutations = [request for request in client.requests if request[0] in {"PUT", "DELETE"}]
        self.assertTrue(all(request[2] in {"one", "two"} for request in mutations))
        self.assertTrue(all(request[1] == "/api/conversations/" + client.identifier for request in mutations))
        self.assertEqual(sum(request[0] == "DELETE" for request in mutations), delete_attempts)
        self.assertEqual(sum(request[0] == "POST" for request in client.requests), 1)
        return report["error"]

    def test_storage_happy_path_uses_only_confirmed_owned_versions(self):
        client = StorageClient()
        self.assertEqual(verify(client, check_storage=True)[-2:],
                         ["cosmos_create_read_update_conflict", "synthetic_record_deleted"])
        path = "/api/conversations/" + client.identifier
        self.assertEqual(client.requests, [
            ("POST", "/api/conversations", None, 200), ("GET", path, None, 200),
            ("PUT", path, "one", 200), ("PUT", path, "one", 409),
            ("GET", path, None, 200), ("DELETE", path, "two", 200), ("GET", path, None, 404),
        ])
        self.assertTrue(client.deleted)

    def test_storage_invalid_version_fields_never_enable_an_unowned_mutation(self):
        invalid = (None, "", " ", 1, True, [], {}, "*", "one,two", "one\n", "\tone")
        phases = {"create": "create version confirmation", "initial": "initial record verification",
                  "update": "conditional update confirmation", "cleanup": "cleanup version confirmation"}
        for stage, phase in phases.items():
            for number, etag in enumerate(invalid):
                with self.subTest(stage=stage, case=number):
                    client = StorageClient(faults={stage: {"id": StorageClient.identifier, "_etag": etag}})
                    self.assert_storage_failure(client, phase)
                    self.assertEqual(sum(request[0] == "PUT" for request in client.requests),
                                     0 if stage in {"create", "initial"} else 1 if stage == "update" else 2)
            with self.subTest(stage=stage, case="missing"):
                self.assert_storage_failure(StorageClient(faults={stage: {"id": StorageClient.identifier}}), phase)

    def test_storage_unidentifiable_create_response_retains_records_without_mutation(self):
        for number, response in enumerate(({}, {"id": None}, {"id": 1}, {"id": []},
                                           {"id": "not-a-uuid"}, {"id": "AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA"}, [])):
            with self.subTest(case=number):
                client = StorageClient(faults={"create": response})
                self.assert_storage_failure(client, "usable conversation ID", identified=False)
                self.assertEqual(len(client.requests), 1)
        client = StorageClient(faults={"create": CheckError(StorageClient.sensitive)})
        self.assert_storage_failure(client, "create outcome is unconfirmed", identified=False)
        self.assertEqual(len(client.requests), 1)

    def test_storage_wrong_or_missing_record_identity_never_enables_cleanup(self):
        other = "22222222-2222-4222-8222-222222222222"
        for stage, phase in (("initial", "initial record verification"),
                             ("update", "conditional update confirmation"),
                             ("cleanup", "cleanup version confirmation")):
            for number, response in enumerate(({"id": other, "_etag": "two"}, {"_etag": "two"},
                                               {"id": [StorageClient.identifier, other], "_etag": "two"}, [])):
                with self.subTest(stage=stage, case=number):
                    self.assert_storage_failure(StorageClient(faults={stage: response}), phase)
        self.assert_storage_failure(StorageClient(faults={"create": {"id": other, "_etag": "one"}}),
                                    "initial record verification", identified=False)

    def test_external_versions_before_update_or_cleanup_are_never_adopted(self):
        for stage, phase in (("initial", "initial record verification"), ("cleanup", "cleanup version confirmation")):
            with self.subTest(stage=stage):
                client = StorageClient(external_read=stage)
                self.assert_storage_failure(client, phase)
                self.assertEqual(client.etag, "external")
                self.assertEqual(sum(request[0] == "PUT" for request in client.requests), 0 if stage == "initial" else 2)

    def test_cleanup_read_delete_race_conflicts_without_retry_or_new_etag(self):
        client = StorageClient(delete_race=True)
        message = self.assert_storage_failure(client, "conditional deletion confirmation", delete_attempts=1)
        self.assertEqual(client.requests[-1][2], "two")
        self.assertEqual(client.etag, "external")
        self.assertIn("deletion may already have completed", message)

    def test_possible_update_or_stale_commit_retains_records_without_delete(self):
        for stage, phase in (("update", "conditional update confirmation"), ("stale", "stale-update conflict confirmation")):
            for number, failure in enumerate((CheckError(StorageClient.sensitive), [], {"id": StorageClient.identifier},
                                              {"id": StorageClient.identifier, "_etag": "one"})):
                with self.subTest(stage=stage, case=number):
                    client = StorageClient(faults={stage: failure})
                    self.assert_storage_failure(client, phase)
                    self.assertEqual(client.etag, "two")
                    self.assertEqual(client.read_count, 1)
        client = StorageClient(accepted_stale=True)
        self.assert_storage_failure(client, "stale-update conflict confirmation")
        self.assertEqual(client.etag, "three")

    def test_failed_initial_transcript_verification_retains_record(self):
        valid_result = {"request_id": "wrong", "agent": "coordinator", "text": StorageClient.sensitive}
        for number, turns in enumerate((None, [], [None], [{}], [{"result": []}],
                                         [{"question": APPLICATION_PROMPT, "result": valid_result}], [{}, {}])):
            with self.subTest(case=number):
                response = {"id": StorageClient.identifier, "_etag": "one", "agent_id": "review", "turns": turns}
                client = StorageClient(faults={"initial": response})
                self.assert_storage_failure(client, "initial record verification")
                self.assertEqual(sum(request[0] == "PUT" for request in client.requests), 0)

    def test_read_failures_and_unconfirmed_deletion_do_not_trigger_fallback_mutations(self):
        for stage, phase, deletes in (("initial", "initial record verification", 0),
                                     ("cleanup", "cleanup version confirmation", 0),
                                     ("delete", "conditional deletion confirmation", 1)):
            with self.subTest(stage=stage):
                self.assert_storage_failure(StorageClient(faults={stage: CheckError(StorageClient.sensitive)}),
                                            phase, delete_attempts=deletes)
        for response in ({}, {"deleted": False}, {"deleted": 1}, []):
            self.assert_storage_failure(StorageClient(faults={"delete": response}),
                                        "conditional deletion confirmation", delete_attempts=1)

    def test_post_delete_failure_reports_uncertainty_without_retry(self):
        client = StorageClient(faults={"absence": CheckError(StorageClient.sensitive)})
        with self.assertRaisesRegex(CheckError, "deletion absence verification.*deletion may already have completed"):
            verify(client, check_storage=True)
        self.assertTrue(client.deleted)
        self.assertEqual(sum(request[0] == "DELETE" for request in client.requests), 1)

    def test_initial_read_update_race_refuses_mutation_without_cleanup(self):
        client = StorageClient(update_race=True)
        self.assert_storage_failure(client, "conditional update confirmation")
        self.assertEqual(client.etag, "external")
        self.assertEqual(client.requests[-1][2], "one")

    def test_missing_expected_request_id_fails_explicitly_without_cleanup(self):
        client = CustomerReviewClient()
        client.overrides[2] = {"request_id": None}
        original = client.call

        def without_request_id(method, path, body=None, etag=None, expected=200):
            result = original(method, path, body, etag, expected)
            if path == "/api/reviews":
                result.pop("request_id", None)
            return result

        with patch.object(client, "call", side_effect=without_request_id), \
                self.assertRaisesRegex(CheckError, "initial record verification"):
            verify(client, check_storage=True, check_review_specialists=True)
        self.assertFalse(client.deleted)
        self.assertFalse(any(method in {"PUT", "DELETE"} for method, _ in client.calls))

    def test_http_failures_after_possible_mutation_commit_never_start_cleanup(self):
        cases = (("timeout", None), ("connection", None), ("invalid-json", b"not JSON"),
                 ("invalid-object", b"[]"), ("missing-version", b"{}"),
                 ("duplicate-id", b'{"id":"11111111-1111-4111-8111-111111111111","id":"content-not-for-logs"}'))
        for stage in ("create", "update", "stale"):
            for name, payload in cases:
                with self.subTest(stage=stage, failure=name):
                    fixture = StorageClient()
                    puts = 0

                    def respond(request, timeout):
                        nonlocal puts
                        method = request.get_method()
                        path = request.full_url.removeprefix("https://lab.example.invalid")
                        expected = 200
                        current_stage = "create" if method == "POST" else None
                        if method == "PUT":
                            puts += 1
                            current_stage = "update" if puts == 1 else "stale"
                            expected = 200 if puts == 1 else 409
                        body = json.loads(request.data) if request.data else None
                        result = fixture.call(method, path, body, request.get_header("If-match"), expected)
                        if current_stage == stage:
                            if stage == "stale":
                                fixture.etag = "three"
                            if name == "timeout":
                                raise TimeoutError(fixture.sensitive)
                            if name == "connection":
                                raise URLError(fixture.sensitive)
                            if stage == "stale":
                                raise HTTPError(request.full_url, 409, "fictional conflict", None, io.BytesIO(payload))
                            response = io.BytesIO(payload)
                        elif expected == 409:
                            payload = b'{"error":"conversation_changed","request_id":"fictional-error-request"}'
                            raise HTTPError(request.full_url, 409, "fictional conflict", None, io.BytesIO(payload))
                        else:
                            response = io.BytesIO(json.dumps(result).encode("utf-8"))
                        response.status = expected
                        return response

                    output, error = io.StringIO(), io.StringIO()
                    with patch("verify_private.build_opener") as opener, redirect_stdout(output), redirect_stderr(error):
                        opener.return_value.open.side_effect = respond
                        code = main(["--base-url", "https://lab.example.invalid", "--check-storage"])
                    self.assertEqual(code, 1)
                    self.assertEqual(output.getvalue(), "")
                    message = json.loads(error.getvalue())["error"]
                    expected_phase = ("usable conversation ID" if stage == "create" and name == "missing-version"
                                      else "create outcome is unconfirmed" if stage == "create"
                                      else "conditional update" if stage == "update"
                                      else "stale-update conflict")
                    self.assertIn(expected_phase, message)
                    if stage != "create":
                        self.assertIn(fixture.identifier, message)
                    self.assertNotIn(fixture.sensitive, error.getvalue())
                    self.assertNotIn("content-not-for-logs", error.getvalue())
                    self.assertFalse(fixture.deleted)
                    expected_reads = 0 if stage == "create" else 1
                    self.assertEqual(fixture.read_count, expected_reads)
                    self.assertFalse(any(method == "DELETE" for method, _, _, _ in fixture.requests))
                    self.assertEqual(puts, 0 if stage == "create" else 1 if stage == "update" else 2)

    def run_http_error_storage(self, opener):
        output, error = io.StringIO(), io.StringIO()
        with patch("verify_private.build_opener", return_value=opener), redirect_stdout(output), redirect_stderr(error):
            code = main(["--base-url", "https://lab.example.invalid", "--check-storage"])
        return code, output.getvalue(), error.getvalue()

    def assert_unconfirmed_http_error(self, stage, status, payload):
        opener = StorageHttpOpener(override_stage=stage, override_status=status, override_payload=payload)
        code, output, error = self.run_http_error_storage(opener)
        self.assertEqual(code, 1)
        self.assertEqual(output, "")
        report = json.loads(error)
        self.assertEqual(report["status"], "failed")
        self.assertIn("stale-update conflict confirmation" if stage == "stale" else "deletion absence verification",
                      report["error"])
        self.assertIn(opener.fixture.identifier, report["error"])
        self.assertNotIn("content-not-for-logs", error)
        self.assertNotIn("fictional-error-request", error)
        self.assertNotIn(APPLICATION_PROMPT, error)
        self.assertEqual(opener.puts, 2)
        self.assertEqual(sum(method == "POST" for method, _, _, _ in opener.fixture.requests), 1)
        deletes = [request for request in opener.fixture.requests if request[0] == "DELETE"]
        self.assertEqual(len(deletes), 0 if stage == "stale" else 1)
        self.assertTrue(all(request[2] == "two" for request in deletes))
        self.assertEqual(opener.fixture.deleted, stage == "absence")
        self.assertEqual(opener.fixture.requests[-1][0], "PUT" if stage == "stale" else "GET")
        self.assertEqual(opener.fixture.requests[-1][3], 409 if stage == "stale" else 404)
        return opener

    def test_actual_http_errors_with_exact_api_codes_confirm_conflict_and_absence(self):
        opener = StorageHttpOpener()
        code, output, error = self.run_http_error_storage(opener)
        self.assertEqual(code, 0)
        self.assertEqual(error, "")
        report = json.loads(output)
        self.assertEqual(report["checks"][-2:], ["cosmos_create_read_update_conflict", "synthetic_record_deleted"])
        self.assertFalse(report["ingress_verified"])
        self.assertFalse(report["private_network_verified"])
        self.assertFalse(report["rendered_ui_verified"])
        self.assertEqual([error.code for error in opener.errors], [409, 404])
        self.assertTrue(all(error.fp.closed for error in opener.errors))
        self.assertNotIn("fictional-error-request", output)
        self.assertNotIn(APPLICATION_PROMPT, output)

    def test_actual_http_error_bodies_reject_missing_wrong_or_nonstring_codes(self):
        for stage, status, correct, other in (("stale", 409, "conversation_changed", "conversation_not_found"),
                                              ("absence", 404, "conversation_not_found", "conversation_changed")):
            bodies = ({}, {"request_id": "content-not-for-logs"}, {"error": other},
                      {"error": "request_not_allowed"}, {"error": True}, {"error": None},
                      {"error": 409}, {"error": [correct]}, {"error": {"code": correct}},
                      {"error": correct + " "}, {"error": correct.upper()})
            for number, body in enumerate(bodies):
                with self.subTest(stage=stage, case=number):
                    self.assert_unconfirmed_http_error(stage, status, json.dumps(body).encode())

    def test_actual_http_error_bodies_reject_empty_malformed_nonobject_and_duplicate_json(self):
        for stage, status, correct in (("stale", 409, "conversation_changed"),
                                       ("absence", 404, "conversation_not_found")):
            payloads = (b"", b"not JSON content-not-for-logs", b"{", b"[]", b"null", b"true", b'"content-not-for-logs"',
                        ('{"error":"content-not-for-logs","error":"' + correct + '"}').encode(),
                        ('{"error":"' + correct + '","request_id":"one","request_id":"content-not-for-logs"}').encode(),
                        ('{"error":"' + correct + '","extra":{"id":"one","id":"content-not-for-logs"}}').encode())
            for number, payload in enumerate(payloads):
                with self.subTest(stage=stage, case=number):
                    opener = self.assert_unconfirmed_http_error(stage, status, payload)
                    self.assertTrue(opener.errors[-1].fp.closed)

    def test_actual_http_error_status_interference_is_rejected_even_with_matching_code(self):
        for stage, expected, correct in (("stale", 409, "conversation_changed"),
                                        ("absence", 404, "conversation_not_found")):
            payload = json.dumps({"error": correct, "request_id": "content-not-for-logs"}).encode()
            for status in (404 if expected == 409 else 409, 400, 403, 429, 500, 503):
                with self.subTest(stage=stage, status=status):
                    self.assert_unconfirmed_http_error(stage, status, payload)

    def test_expected_codes_are_checked_even_when_opener_returns_an_error_response_normally(self):
        path = "/api/conversations/" + StorageClient.identifier
        for method, status in (("PUT", 409), ("GET", 404)):
            with self.subTest(method=method):
                response = io.BytesIO(b"{}")
                response.status = status
                with patch("verify_private.build_opener") as opener:
                    opener.return_value.open.return_value = response
                    client = PrivateClient("https://lab.example.invalid")
                    with self.assertRaisesRegex(CheckError, "expected conversation error code"):
                        client.call(method, path, etag="one" if method == "PUT" else None, expected=status)

    def test_expected_conversation_errors_do_not_verify_unrelated_api_routes(self):
        payload = b'{"error":"conversation_not_found","request_id":"content-not-for-logs"}'
        with patch("verify_private.build_opener") as opener:
            opener.return_value.open.side_effect = HTTPError("https://lab.example.invalid/api/config", 404,
                                                             "fictional error", None, io.BytesIO(payload))
            client = PrivateClient("https://lab.example.invalid")
            with self.assertRaisesRegex(CheckError, "HTTP 404") as raised:
                client.call("GET", "/api/config", expected=404)
        self.assertNotIn("content-not-for-logs", str(raised.exception))
        opener.return_value.open.assert_called_once()

    def test_primary_failure_is_preserved_without_a_cleanup_error_replacing_it(self):
        primary = CheckError(StorageClient.sensitive)
        client = StorageClient(faults={"initial": primary})
        with self.assertRaises(CheckError) as raised:
            verify(client, check_storage=True)
        self.assertIs(raised.exception.__cause__, primary)
        self.assertIn("initial record verification", str(raised.exception))
        self.assertNotIn(client.sensitive, str(raised.exception))
        self.assertFalse(any(method in {"PUT", "DELETE"} for method, _, _, _ in client.requests))

    def test_http_accepted_stale_update_retains_record_without_cleanup(self):
        fixture = StorageClient()
        puts = 0

        def respond(request, timeout):
            nonlocal puts
            method = request.get_method()
            path = request.full_url.removeprefix("https://lab.example.invalid")
            if method == "PUT":
                puts += 1
                if puts == 2:
                    fixture.etag = "three"
                    response = io.BytesIO(json.dumps({"id": fixture.identifier, "_etag": fixture.etag}).encode())
                    response.status = 200
                    return response
            body = json.loads(request.data) if request.data else None
            result = fixture.call(method, path, body, request.get_header("If-match"))
            response = io.BytesIO(json.dumps(result).encode())
            response.status = 200
            return response

        output, error = io.StringIO(), io.StringIO()
        with patch("verify_private.build_opener") as opener, redirect_stdout(output), redirect_stderr(error):
            opener.return_value.open.side_effect = respond
            code = main(["--base-url", "https://lab.example.invalid", "--check-storage"])
        self.assertEqual(code, 1)
        self.assertEqual(output.getvalue(), "")
        self.assertIn("stale-update conflict confirmation", json.loads(error.getvalue())["error"])
        self.assertFalse(fixture.deleted)
        self.assertEqual(puts, 2)
        self.assertEqual(fixture.read_count, 1)

    def test_private_client_rejects_invalid_mutation_etags_before_request(self):
        with patch("verify_private.build_opener") as opener:
            client = PrivateClient("https://lab.example.invalid")
            for method in ("PUT", "DELETE"):
                for etag in (None, "", " ", 1, True, {}, [], "*", "one,two", "one\n"):
                    with self.subTest(method=method, etag=etag), self.assertRaisesRegex(CheckError, "Conditional mutation"):
                        client.call(method, "/api/conversations/" + StorageClient.identifier, etag=etag)
            opener.return_value.open.assert_not_called()

    def test_private_client_sends_if_match_for_every_update_and_delete(self):
        with patch("verify_private.build_opener") as opener:
            client = PrivateClient("https://lab.example.invalid")
            for method in ("PUT", "DELETE"):
                response = io.BytesIO(b"{}")
                response.status = 200
                opener.return_value.open.return_value = response
                client.call(method, "/api/conversations/" + StorageClient.identifier, etag='"owned-version"')
                request = opener.return_value.open.call_args.args[0]
                self.assertEqual(request.get_header("If-match"), '"owned-version"')
                self.assertEqual(request.get_method(), method)

    def test_duplicate_json_identifiers_are_rejected_without_logging_content(self):
        response = io.BytesIO(b'{"id":"11111111-1111-4111-8111-111111111111","id":"content-not-for-logs"}')
        response.status = 200
        with patch("verify_private.build_opener") as opener:
            opener.return_value.open.return_value = response
            client = PrivateClient("https://lab.example.invalid")
            with self.assertRaisesRegex(CheckError, "invalid JSON response") as raised:
                client.call("POST", "/api/conversations", {})
        self.assertNotIn("content-not-for-logs", str(raised.exception))
        opener.return_value.open.assert_called_once()

    def run_mocked_api_checks(self, arguments):
        fixture = FakeClient()
        responses = []
        for path in ("/api/config", "/api/health/dependencies"):
            response = io.BytesIO(json.dumps(fixture.call("GET", path)).encode("utf-8"))
            response.status = 200
            responses.append(response)
        output = io.StringIO()
        with patch("verify_private.build_opener") as build_opener, redirect_stdout(output):
            build_opener.return_value.open.side_effect = responses
            code = main(arguments)
        return code, output.getvalue(), build_opener.return_value.open.call_args_list

    def assert_api_only_report(self, output, *, path, https_origin_reached):
        self.assertEqual(json.loads(output), {
            "status": "passed",
            "path": path,
            "checks": ["private_configuration", "cached_dependencies"],
            "https_origin_reached": https_origin_reached,
            "ingress_verified": False,
            "private_network_verified": False,
            "rendered_ui_verified": False,
            "container_isolation_verified": False,
            "model_quality_verified": False,
        })

    def test_https_origins_report_api_evidence_not_private_ingress_or_ui(self):
        for origin in ("https://localhost:8443", "https://lab.example.invalid", "https://lab.example.invalid/",
                       "https://lab.example.invalid:8443", "https://[::1]", "https://[::1]:443",
                       "https://[2001:db8::1]:65535/"):
            with self.subTest(origin=origin):
                code, output, calls = self.run_mocked_api_checks(["--base-url", origin])
                self.assertEqual(code, 0)
                self.assert_api_only_report(output, path="https_origin", https_origin_reached=True)
                requests = [call.args[0] for call in calls]
                base = origin.rstrip("/")
                self.assertEqual([request.full_url for request in requests],
                                 [base + "/api/config", base + "/api/health/dependencies"])
                self.assertEqual([request.get_method() for request in requests], ["GET", "GET"])
                self.assertEqual([request.get_header("Origin") for request in requests], [base, base])
                host = base[len("https://"):]
                self.assertEqual([request.get_header("Host") for request in requests], [host, host])

    def test_loopback_reports_http_api_evidence_not_container_or_ingress(self):
        environment = {"WORKBENCH_MODE": "private", "WORKBENCH_ALLOWED_HOSTS": "lab.example.invalid"}
        with patch.dict("os.environ", environment, clear=True):
            code, output, calls = self.run_mocked_api_checks(["--loopback"])
        self.assertEqual(code, 0)
        self.assert_api_only_report(output, path="loopback_http", https_origin_reached=False)
        requests = [call.args[0] for call in calls]
        self.assertEqual([request.full_url for request in requests],
                         ["http://127.0.0.1:8080/api/config", "http://127.0.0.1:8080/api/health/dependencies"])
        self.assertEqual([request.get_method() for request in requests], ["GET", "GET"])
        self.assertEqual([request.get_header("Origin") for request in requests],
                         ["https://lab.example.invalid", "https://lab.example.invalid"])

    def assert_invalid_origin(self, origin):
        output, error = io.StringIO(), io.StringIO()
        with patch("verify_private.build_opener", side_effect=AssertionError("Unexpected opener")) as opener, \
                redirect_stdout(output), redirect_stderr(error):
            code = main(["--base-url", origin])
        self.assertEqual(code, 1)
        self.assertEqual(output.getvalue(), "")
        self.assertEqual(json.loads(error.getvalue()), {
            "status": "failed",
            "error": "Supply the exact HTTPS origin, not a path, query, fragment, or credentials",
        })
        opener.assert_not_called()

    def test_empty_query_and_fragment_delimiters_fail_before_opening_a_connection(self):
        for suffix in ("?", "/?", "#", "/#"):
            with self.subTest(suffix=suffix):
                self.assert_invalid_origin("https://lab.example.invalid" + suffix)

    def test_malformed_authorities_and_userinfo_fail_with_fixed_json_before_opener(self):
        origins = ("https://[broken", "https://[not-an-address]", "https://[127.0.0.1]",
                   "https://lab.example.invalid:invalid", "https://lab.example.invalid:65536",
                   "https://lab.example.invalid:-1", "https://lab.example.invalid:",
                   "https://[::1]:invalid", "https://[::1]:65536", "https://[::1]:",
                   "https://@lab.example.invalid", "https://:@lab.example.invalid",
                   "https://user@lab.example.invalid", "https://user:@lab.example.invalid",
                   "https://user:example@lab.example.invalid")
        for number, origin in enumerate(origins):
            with self.subTest(case=number):
                self.assert_invalid_origin(origin)

    def test_raw_controls_and_ascii_spaces_fail_with_fixed_json_before_opener(self):
        base = "https://lab.example.invalid"
        for number in (*range(0x21), *range(0x7F, 0xA0)):
            character = chr(number)
            origins = (character + base, base + character, "https://lab." + character + "example.invalid")
            for position, origin in enumerate(origins):
                with self.subTest(codepoint=hex(number), position=position):
                    self.assert_invalid_origin(origin)

    def test_loopback_requires_private_mode_and_one_host_before_opening_a_connection(self):
        for environment in ({}, {"WORKBENCH_MODE": "private", "WORKBENCH_ALLOWED_HOSTS": "one,two"},
                            {"WORKBENCH_MODE": "public", "WORKBENCH_ALLOWED_HOSTS": "lab.example.invalid"}):
            with self.subTest(environment=environment):
                output, error = io.StringIO(), io.StringIO()
                with patch.dict("os.environ", environment, clear=True), \
                        patch("verify_private.build_opener") as opener, \
                        redirect_stdout(output), redirect_stderr(error):
                    code = main(["--loopback"])
                self.assertEqual(code, 1)
                self.assertEqual(output.getvalue(), "")
                report = json.loads(error.getvalue())
                self.assertEqual(report["status"], "failed")
                self.assertIn("Loopback verification", report["error"])
                opener.assert_not_called()

    def test_api_errors_fail_without_retry_or_success_report(self):
        failures = ((URLError("synthetic outage"), "connection unavailable or timed out"),
                    (HTTPError("https://lab.example.invalid/api/config", 503, "unavailable", None, None), "HTTP 503"))
        for failure, expected in failures:
            with self.subTest(failure=type(failure).__name__):
                output, error = io.StringIO(), io.StringIO()
                with patch("verify_private.build_opener") as opener, redirect_stdout(output), redirect_stderr(error):
                    opener.return_value.open.side_effect = failure
                    code = main(["--base-url", "https://lab.example.invalid"])
                self.assertEqual(code, 1)
                self.assertEqual(output.getvalue(), "")
                report = json.loads(error.getvalue())
                self.assertEqual(report["status"], "failed")
                self.assertIn(expected, report["error"])
                opener.return_value.open.assert_called_once()

    def test_invalid_api_json_fails_without_retry_or_success_report(self):
        response = io.BytesIO(b"not JSON")
        response.status = 200
        output, error = io.StringIO(), io.StringIO()
        with patch("verify_private.build_opener") as opener, redirect_stdout(output), redirect_stderr(error):
            opener.return_value.open.return_value = response
            code = main(["--base-url", "https://lab.example.invalid"])
        self.assertEqual(code, 1)
        self.assertEqual(output.getvalue(), "")
        report = json.loads(error.getvalue())
        self.assertEqual(report["status"], "failed")
        self.assertIn("invalid JSON response", report["error"])
        opener.return_value.open.assert_called_once()

    def test_requires_private_https_or_the_explicit_runtime_context(self):
        for url in ("http://lab.example.invalid", "https://user:secret@lab.example.invalid", "https://lab.example.invalid/api/config"):
            with self.assertRaises(CheckError):
                PrivateClient(url)
        with patch.dict("os.environ", {}, clear=True), self.assertRaises(CheckError):
            PrivateClient(loopback=True)


if __name__ == "__main__":
    unittest.main()

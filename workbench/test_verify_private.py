import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
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
            return {"status": "completed", "text": "Synthetic answer", "agent": "coordinator", "receipts": [
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
            return {**self.body, "_etag": self.etag, **({} if self.persisted else {"turns": []})}
        if method == "PUT" and expected == 409:
            if not self.conflict:
                raise CheckError("Stale update was accepted")
            return {}
        if method == "PUT":
            self.etag = "two"
            return {"_etag": self.etag}
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

    def test_storage_failure_still_deletes_only_the_created_record(self):
        for client in (FakeClient(conflict=False), FakeClient(persisted=False)):
            with self.assertRaises(CheckError):
                verify(client, check_storage=True)
            self.assertTrue(client.deleted)
            self.assertEqual(sum(method == "POST" for method, _ in client.calls), 1)

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

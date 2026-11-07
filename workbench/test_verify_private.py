import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

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

    def test_requires_private_https_or_the_explicit_runtime_context(self):
        for url in ("http://lab.example.invalid", "https://user:secret@lab.example.invalid", "https://lab.example.invalid/api/config"):
            with self.assertRaises(CheckError):
                PrivateClient(url)
        with patch.dict("os.environ", {}, clear=True), self.assertRaises(CheckError):
            PrivateClient(loopback=True)


if __name__ == "__main__":
    unittest.main()

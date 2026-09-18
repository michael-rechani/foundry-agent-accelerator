import unittest
from unittest.mock import patch

from verify_private import CheckError, PrivateClient, verify


class FakeClient:
    def __init__(self, *, receipt=True, conflict=True, persisted=True, specialists=True):
        self.calls = []
        self.receipt = receipt
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
                {"tool": "inspect", "agent": "specialist", "verified": True, "call_id": "one", "output": "Finding"}
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

    def test_plain_agent_does_not_claim_specialist_verification(self):
        checks = verify(FakeClient(receipt=False, specialists=False), run_agent=True)
        self.assertIn("agent_execution", checks)
        self.assertNotIn("agent_and_specialist_receipt", checks)

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

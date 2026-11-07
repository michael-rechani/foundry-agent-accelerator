import contextlib
import http.client
import io
import os
import ssl
import unittest
from unittest import mock

import snapshot_http_transport as transport
import snapshot_integrity_guard as guard

TARGETS = {
    "platform_state": "https://state.example.invalid/container/state.tfstate",
    "input": "https://input.example.invalid/container/input.json",
}
TOKEN = "fictional-token"
HEADERS = (
    ("ETag", '"fictional"'),
    ("Last-Modified", "Mon, 06 Nov 2023 12:00:00 GMT"),
    ("x-ms-creation-time", "Mon, 06 Nov 2023 12:00:00 GMT"),
    ("Content-Length", "4"),
    ("x-ms-version", "2023-11-03"),
    ("x-ms-blob-type", "BlockBlob"),
    ("x-ms-lease-status", "unlocked"),
    ("x-ms-lease-state", "available"),
)


class FakeSocket:
    def __init__(self, data):
        self.data = data

    def makefile(self, mode):
        return io.BytesIO(self.data)


class FixtureConnection:
    raw = b""
    made = []
    failure = None
    close_failure = None

    def __init__(self, host, port, timeout, context):
        self.host, self.port, self.timeout, self.context = host, port, timeout, context
        self.calls = []
        self.closed = False
        self.close_attempts = 0
        self.__class__.made.append(self)

    def request(self, method, path, headers):
        self.calls.append((method, path, headers))
        if self.failure:
            raise RuntimeError(self.failure)

    def getresponse(self):
        response = http.client.HTTPResponse(FakeSocket(self.raw))
        response.begin()
        return response

    def close(self):
        self.close_attempts += 1
        self.closed = True
        if self.close_failure:
            raise RuntimeError(self.close_failure)


def wire(status=200, headers=HEADERS, body=b"data"):
    return (f"HTTP/1.1 {status} Fictional\r\n".encode("ascii")
            + b"".join(f"{name}: {value}\r\n".encode("ascii") for name, value in headers)
            + b"\r\n" + body)


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.assertNotEqual(os.getuid(), 0)
        self.assertFalse(any(key.startswith(("AZURE_", "ARM_")) or key in
                             ("GITHUB_TOKEN", "GH_TOKEN", "ACTIONS_ID_TOKEN_REQUEST_TOKEN")
                             for key in os.environ))
        FixtureConnection.raw = wire()
        FixtureConnection.made = []
        FixtureConnection.failure = None
        FixtureConnection.close_failure = None
        self.real_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        self.context = mock.Mock(spec=ssl.SSLContext)
        self.context_patch = mock.patch.object(transport.ssl, "SSLContext", return_value=self.context)
        self.connection_patch = mock.patch.object(transport.http.client, "HTTPSConnection", FixtureConnection)
        self.context_patch.start()
        self.connection_patch.start()
        self.addCleanup(self.context_patch.stop)
        self.addCleanup(self.connection_patch.stop)
        self.reader = transport.SnapshotTransport.create(TARGETS.copy(), TOKEN, "/fictional/ca.pem")
        self.assertIsNotNone(self.reader)

    def test_exact_record_and_guard(self):
        before = {role: self.reader(role) for role in guard.ROLES}
        self.assertEqual(before["platform_state"], {
            "identity": TARGETS["platform_state"], "status": 200,
            "body": b"data", "headers": HEADERS,
        })
        self.assertEqual(guard.compare_snapshots(TARGETS, before, before), guard.PASSED)
        self.assertEqual(guard.guarded_diagnostic(TARGETS, self.reader, lambda: guard.DIAGNOSTIC_SUCCESS),
                         guard.PASSED)
        for connection in FixtureConnection.made:
            self.assertEqual(connection.port, 443)
            self.assertEqual(connection.timeout, transport.TIMEOUT)
            self.assertIs(connection.context, self.context)
            self.assertTrue(connection.closed)
            method, path, headers = connection.calls[0]
            self.assertEqual(method, "GET")
            self.assertIn(path, ("/container/state.tfstate", "/container/input.json"))
            self.assertEqual(headers["Authorization"], "Bearer " + TOKEN)
            self.assertEqual(headers["x-ms-version"], "2023-11-03")
            self.assertRegex(headers["x-ms-date"], r"^(Mon|Tue|Wed|Thu|Fri|Sat|Sun), .+ GMT$")
            self.assertEqual(headers["Accept-Encoding"], "identity")
            self.assertNotIn("Range", headers)
            self.assertNotIn("x-ms-range", headers)

    def test_bound_entry_rejects_unapproved_expected_without_connections(self):
        cases = [None, {}, dict(TARGETS, extra=TARGETS["input"]),
                 {"platform_state": TARGETS["input"], "input": TARGETS["platform_state"]},
                 dict.fromkeys(guard.ROLES, TARGETS["input"]),
                 dict(TARGETS, input=None), dict(TARGETS, input=1),
                 dict(TARGETS, input="https://unapproved.example.invalid/container/input.json"),
                 dict(TARGETS, input=TARGETS["input"] + "?"),
                 dict(TARGETS, input=TARGETS["input"] + "#"),
                 dict(TARGETS, input="https://input.example.invalid/container/in\nput.json")]
        for expected in cases:
            with self.subTest(expected_type=type(expected).__name__):
                diagnostic = mock.Mock(return_value=guard.DIAGNOSTIC_SUCCESS)
                output, errors = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
                    result = self.reader.guarded_diagnostic(expected, diagnostic)
                self.assertEqual(result, guard.UNVERIFIED)
                self.assertEqual(FixtureConnection.made, [])
                diagnostic.assert_not_called()
                self.assertEqual((output.getvalue(), errors.getvalue()), ("", ""))

    def test_bound_entry_checks_both_roles_before_first_connection(self):
        for role in guard.ROLES:
            with self.subTest(role=role):
                expected = dict(TARGETS)
                expected[role] = "https://unapproved.example.invalid/container/blob"
                diagnostic = mock.Mock(return_value=guard.DIAGNOSTIC_SUCCESS)
                self.assertEqual(self.reader.guarded_diagnostic(expected, diagnostic), guard.UNVERIFIED)
                diagnostic.assert_not_called()
                self.assertEqual(FixtureConnection.made, [])

    def test_generic_guard_is_not_destination_binding(self):
        configured = dict(TARGETS, input="https://unapproved.example.invalid/container/input")
        reader = transport.SnapshotTransport.create(configured, TOKEN, "/fictional/ca.pem")
        diagnostic = mock.Mock(return_value=guard.DIAGNOSTIC_SUCCESS)
        self.assertEqual(guard.guarded_diagnostic(TARGETS, reader, diagnostic), guard.UNVERIFIED)
        diagnostic.assert_not_called()
        self.assertEqual([connection.host for connection in FixtureConnection.made],
                         ["state.example.invalid", "unapproved.example.invalid"] * 2)

    def test_post_construction_caller_mutation_is_rejected_before_io(self):
        for role in guard.ROLES:
            with self.subTest(role=role):
                configured = dict(TARGETS)
                reader = transport.SnapshotTransport.create(configured, TOKEN, "/fictional/ca.pem")
                expected = dict(TARGETS)
                configured[role] = "https://unapproved.example.invalid/container/configured"
                expected[role] = configured[role]
                diagnostic = mock.Mock(return_value=guard.DIAGNOSTIC_SUCCESS)
                self.assertEqual(reader.guarded_diagnostic(expected, diagnostic), guard.UNVERIFIED)
                diagnostic.assert_not_called()
                self.assertEqual(FixtureConnection.made, [])
                self.assertEqual(dict(reader._targets), TARGETS)

    def test_bound_entry_rejects_replaced_or_malformed_sealed_targets(self):
        for sealed in (None, (), list(TARGETS.items()), (("input",),),
                       (("platform_state", TARGETS["input"]), ("input", TARGETS["platform_state"])),
                       (("platform_state", TARGETS["input"]), ("input", TARGETS["input"])),
                       (("platform_state", TARGETS["platform_state"]), ("input", None))):
            with self.subTest(sealed_type=type(sealed).__name__):
                reader = transport.SnapshotTransport.create(TARGETS, TOKEN, "/fictional/ca.pem")
                object.__setattr__(reader, "_targets", sealed)
                diagnostic = mock.Mock(return_value=guard.DIAGNOSTIC_SUCCESS)
                self.assertEqual(reader.guarded_diagnostic(TARGETS, diagnostic), guard.UNVERIFIED)
                diagnostic.assert_not_called()
                self.assertEqual(FixtureConnection.made, [])

    def test_bound_entry_rejects_other_reader_types_and_uninitialized_transport(self):
        for reader in (None, object(), transport.SnapshotTransport()):
            diagnostic = mock.Mock(return_value=guard.DIAGNOSTIC_SUCCESS)
            self.assertEqual(transport.SnapshotTransport.guarded_diagnostic(
                reader, TARGETS, diagnostic), guard.UNVERIFIED)
            diagnostic.assert_not_called()
            self.assertEqual(FixtureConnection.made, [])

    def test_bound_entry_copies_expected_and_keeps_approved_rechecks(self):
        expected = dict(TARGETS)

        def diagnostic():
            expected["input"] = "https://unapproved.example.invalid/container/changed"
            return guard.DIAGNOSTIC_SUCCESS

        self.assertEqual(self.reader.guarded_diagnostic(expected, diagnostic), guard.PASSED)
        self.assertEqual([connection.host for connection in FixtureConnection.made],
                         ["state.example.invalid", "input.example.invalid"] * 2)
        self.assertTrue(all(connection.calls[0][2]["Authorization"] == "Bearer " + TOKEN
                            for connection in FixtureConnection.made))

    def test_bound_entry_preserves_failure_and_instability_precedence(self):
        for unstable in (False, True):
            with self.subTest(unstable=unstable):
                FixtureConnection.close_failure = None
                FixtureConnection.made = []

                def diagnostic(unstable=unstable):
                    if unstable:
                        FixtureConnection.close_failure = "fictional-close-token fictional-close-body"
                    raise RuntimeError("fictional-diagnostic-token fictional-diagnostic-body")

                result = self.reader.guarded_diagnostic(TARGETS, diagnostic)
                self.assertEqual(result, guard.UNVERIFIED if unstable else guard.FAILED)
                self.assertEqual([connection.host for connection in FixtureConnection.made],
                                 ["state.example.invalid", "input.example.invalid"] * 2)

    def test_bound_invalid_baseline_still_rechecks_both_approved_roles(self):
        FixtureConnection.close_failure = "fictional-close-token fictional-close-body"
        diagnostic = mock.Mock(return_value=guard.DIAGNOSTIC_SUCCESS)
        self.assertEqual(self.reader.guarded_diagnostic(TARGETS, diagnostic), guard.UNVERIFIED)
        diagnostic.assert_not_called()
        self.assertEqual([connection.host for connection in FixtureConnection.made],
                         ["state.example.invalid", "input.example.invalid"] * 2)

    def test_sealed_replacement_after_validation_cannot_send_to_new_target(self):
        def diagnostic():
            object.__setattr__(self.reader, "_targets", (
                ("platform_state", TARGETS["platform_state"]),
                ("input", "https://unapproved.example.invalid/container/input"),
            ))
            return guard.DIAGNOSTIC_SUCCESS

        self.assertEqual(self.reader.guarded_diagnostic(TARGETS, diagnostic), guard.UNVERIFIED)
        self.assertEqual([connection.host for connection in FixtureConnection.made],
                         ["state.example.invalid", "input.example.invalid"])

    def test_frozen_independent_targets_and_no_override(self):
        targets = TARGETS.copy()
        reader = transport.SnapshotTransport.create(targets, TOKEN, "/fictional/ca.pem")
        targets["platform_state"] = "https://attacker.example.invalid/container/other"
        self.assertEqual(reader("platform_state")["identity"], TARGETS["platform_state"])
        with self.assertRaises(AttributeError):
            reader._targets = (("platform_state", targets["platform_state"]),)
        self.assertIsNone(reader("https://attacker.example.invalid/container/other"))
        self.assertEqual(FixtureConnection.made[-1].host, "state.example.invalid")
        self.assertIsNone(transport.SnapshotTransport.create(
            dict.fromkeys(guard.ROLES, TARGETS["input"]), TOKEN, "/fictional/ca.pem"))

    def test_destination_confusion_is_rejected(self):
        bad = (
            "http://state.example.invalid/container/state",
            "https://user@state.example.invalid/container/state",
            "https://state.example.invalid:443/container/state",
            "https://state.example.invalid/container/state?version=1",
            "https://state.example.invalid/container/state?",
            "https://state.example.invalid/container/state#fragment",
            "https://state.example.invalid/container/state#",
            "https://state.example.invalid/container/../state",
            "https://state.example.invalid/container/%2e%2e",
            "https://state.example.invalid\\@attacker.invalid/container/state",
        )
        for target in bad:
            with self.subTest(target=target):
                targets = dict(TARGETS, platform_state=target)
                self.assertIsNone(transport.SnapshotTransport.create(targets, TOKEN, "/fictional/ca.pem"))
        self.assertEqual(FixtureConnection.made, [])

    def test_proxy_and_ca_environment_not_consulted(self):
        with mock.patch.dict(os.environ, {"HTTPS_PROXY": "http://fictional-proxy.invalid:80",
                                         "SSL_CERT_FILE": "/fictional/attacker.pem",
                                         "SSL_CERT_DIR": "/fictional/attacker"}, clear=True):
            with mock.patch.object(transport.ssl, "create_default_context", side_effect=AssertionError):
                reader = transport.SnapshotTransport.create(TARGETS, TOKEN, "/fictional/ca.pem")
                self.assertIsNotNone(reader("input"))
        self.context.load_verify_locations.assert_called_with(cafile="/fictional/ca.pem")
        transport.ssl.SSLContext.assert_called_with(ssl.PROTOCOL_TLS_CLIENT)
        self.assertTrue(self.real_context.check_hostname)
        self.assertEqual(self.real_context.verify_mode, ssl.CERT_REQUIRED)
        self.assertEqual(FixtureConnection.made[-1].host, "input.example.invalid")

    def test_bad_status_redirect_or_partial(self):
        for status in (206, 301, 302, 307, 308, 401, 403, 404, 500):
            with self.subTest(status=status):
                FixtureConnection.raw = wire(status, HEADERS + (("Location", "https://attacker.invalid/"),))
                self.assertIsNone(self.reader("input"))
        self.assertEqual(len(FixtureConnection.made), 9)

    def test_duplicate_raw_headers_and_ambiguous_framing(self):
        duplicates = HEADERS + (("etag", '"other"'),)
        FixtureConnection.raw = wire(headers=duplicates)
        response = http.client.HTTPResponse(FakeSocket(FixtureConnection.raw))
        response.begin()
        self.assertEqual(tuple(response.headers.raw_items()), duplicates)
        self.assertIsNone(self.reader("input"))
        for extra in (("Transfer-Encoding", "chunked"), ("Content-Range", "bytes 0-3/8")):
            with self.subTest(extra=extra):
                FixtureConnection.raw = wire(headers=HEADERS + (extra,))
                self.assertIsNone(self.reader("input"))

    def test_short_empty_oversized_and_malformed_lengths(self):
        for length, body in (("4", b"dat"), ("0", b""), ("64000001", b""),
                             ("04", b"data"), ("+4", b"data"), ("4, 4", b"data")):
            with self.subTest(length=length):
                headers = tuple((name, length if name == "Content-Length" else value)
                                for name, value in HEADERS)
                FixtureConnection.raw = wire(headers=headers, body=body)
                self.assertIsNone(self.reader("input"))

    def test_token_and_response_header_injection(self):
        for token in ("", "token\r\nX-Injected: yes", "token with spaces", "x" * 16385):
            self.assertIsNone(transport.SnapshotTransport.create(TARGETS, token, "/fictional/ca.pem"))
        FixtureConnection.raw = wire(headers=HEADERS + (("X-Fictional", "value\r\n folded"),))
        self.assertIsNone(self.reader("input"))
        FixtureConnection.raw = wire().replace(b"\r\n\r\n", b"\r\nmalformed\r\n\r\n", 1)
        self.assertIsNone(self.reader("input"))

    def test_exception_and_constructor_failure_are_redacted(self):
        FixtureConnection.failure = "fictional-token https://fictional-secret.invalid sensitive-body"
        self.assertIsNone(self.reader("input"))
        self.assertTrue(FixtureConnection.made[-1].closed)
        self.context.load_verify_locations.side_effect = ValueError(FixtureConnection.failure)
        self.assertIsNone(transport.SnapshotTransport.create(TARGETS, TOKEN, "/fictional/ca.pem"))

    def test_successful_response_failed_close_is_redacted_failure(self):
        FixtureConnection.close_failure = "fictional-close-token fictional-close-body"
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            result = self.reader("input")
        self.assertIsNone(result)
        self.assertEqual(FixtureConnection.made[-1].close_attempts, 1)
        self.assertEqual((output.getvalue(), errors.getvalue()), ("", ""))

    def test_failed_request_failed_close_is_redacted_failure(self):
        FixtureConnection.failure = "fictional-request-token fictional-request-body"
        FixtureConnection.close_failure = "fictional-close-token fictional-close-body"
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            result = self.reader("input")
        self.assertIsNone(result)
        self.assertEqual(FixtureConnection.made[-1].close_attempts, 1)
        self.assertEqual((output.getvalue(), errors.getvalue()), ("", ""))

    def test_post_close_failure_precedes_diagnostic_outcome(self):
        for fails in (False, True):
            with self.subTest(fails=fails):
                FixtureConnection.close_failure = None
                FixtureConnection.made = []
                called = []

                def diagnostic(fails=fails, called=called):
                    called.append(True)
                    FixtureConnection.close_failure = "fictional-close-token fictional-close-body"
                    if fails:
                        raise RuntimeError("fictional-diagnostic-token fictional-diagnostic-body")
                    return guard.DIAGNOSTIC_SUCCESS

                output, errors = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
                    outcome = guard.guarded_diagnostic(TARGETS, self.reader, diagnostic)
                self.assertEqual(outcome, guard.UNVERIFIED)
                self.assertEqual(called, [True])
                self.assertEqual([connection.host for connection in FixtureConnection.made],
                                 ["state.example.invalid", "input.example.invalid"] * 2)
                self.assertTrue(all(connection.close_attempts == 1
                                    for connection in FixtureConnection.made))
                self.assertEqual((output.getvalue(), errors.getvalue()), ("", ""))

    def test_baseline_close_failure_skips_diagnostic_and_rechecks_both(self):
        FixtureConnection.close_failure = "fictional-close-token fictional-close-body"
        diagnostic = mock.Mock(return_value=guard.DIAGNOSTIC_SUCCESS)
        self.assertEqual(guard.guarded_diagnostic(TARGETS, self.reader, diagnostic), guard.UNVERIFIED)
        diagnostic.assert_not_called()
        self.assertEqual([connection.host for connection in FixtureConnection.made],
                         ["state.example.invalid", "input.example.invalid"] * 2)

    def test_unknown_profile_preserved_then_guard_rejects(self):
        FixtureConnection.raw = wire(headers=HEADERS + (("x-ms-access-tier", "Hot"),))
        record = self.reader("input")
        self.assertIn(("x-ms-access-tier", "Hot"), record["headers"])
        snapshots = {"platform_state": record, "input": record}
        snapshots["platform_state"] = dict(record, identity=TARGETS["platform_state"])
        self.assertEqual(guard.compare_snapshots(TARGETS, snapshots, snapshots), guard.UNVERIFIED)

    def test_encoded_bytes_are_not_decoded(self):
        FixtureConnection.raw = wire(headers=HEADERS + (("Content-Encoding", "gzip"),))
        self.assertEqual(self.reader("input")["body"], b"data")


if __name__ == "__main__":
    unittest.main()

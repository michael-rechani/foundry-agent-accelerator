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

    def __init__(self, host, port, timeout, context):
        self.host, self.port, self.timeout, self.context = host, port, timeout, context
        self.calls = []
        self.closed = False
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
        self.closed = True


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

    def test_frozen_independent_targets_and_no_override(self):
        targets = TARGETS.copy()
        reader = transport.SnapshotTransport.create(targets, TOKEN, "/fictional/ca.pem")
        targets["platform_state"] = "https://attacker.example.invalid/container/other"
        self.assertEqual(reader("platform_state")["identity"], TARGETS["platform_state"])
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

    def test_exception_and_constructor_failure_are_redacted(self):
        FixtureConnection.failure = "fictional-token https://fictional-secret.invalid sensitive-body"
        self.assertIsNone(self.reader("input"))
        self.assertTrue(FixtureConnection.made[-1].closed)
        self.context.load_verify_locations.side_effect = ValueError(FixtureConnection.failure)
        self.assertIsNone(transport.SnapshotTransport.create(TARGETS, TOKEN, "/fictional/ca.pem"))

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

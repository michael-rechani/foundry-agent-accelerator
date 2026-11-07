"""Fictional peer verification and real loopback TLS only."""
import contextlib
import http.client
import io
import os
import socket
import ssl
import unittest
from unittest import mock

import snapshot_integrity_guard as guard
import snapshot_peer_transport as peer
import test_snapshot_http_tls as tls
from test_snapshot_http_transport import TARGETS, TOKEN, FakeSocket, wire

PEERS = dict.fromkeys(guard.ROLES, ("127.0.0.1", 443))


class PeerMechanicsTests(unittest.TestCase):
    def setUp(self):
        self.assertNotEqual(os.getuid(), 0)
        self.assertFalse(any(key.startswith(("AZURE_", "ARM_", "ACTIONS_ID_TOKEN_"))
                             or key in ("GH_TOKEN", "GITHUB_TOKEN") for key in os.environ))
        self.context = mock.Mock(spec=ssl.SSLContext)
        self.context.verify_mode = ssl.CERT_REQUIRED
        self.context.check_hostname = True
        self.raw = mock.Mock()
        self.raw.getpeername.return_value = ("127.0.0.1", 443)
        self.encrypted = mock.Mock()
        self.encrypted.getpeername.return_value = ("127.0.0.1", 443)
        self.context.wrap_socket.return_value = self.encrypted
        self.events = []
        self.raw.connect.side_effect = lambda destination: self.events.append("connect")
        self.raw.getpeername.side_effect = lambda: self.events.append("peer") or ("127.0.0.1", 443)
        self.context.wrap_socket.side_effect = lambda *args, **kwargs: (
            self.events.append("tls") or self.encrypted
        )
        self.encrypted.getpeername.side_effect = lambda: (
            self.events.append("tls-peer") or ("127.0.0.1", 443)
        )
        self.encrypted.sendall.side_effect = lambda data: self.events.append("send")
        self.socket_patch = mock.patch.object(peer.socket, "socket", return_value=self.raw)
        self.context_patch = mock.patch.object(peer.ssl, "SSLContext", return_value=self.context)
        self.socket_patch.start()
        self.context_patch.start()
        self.addCleanup(self.socket_patch.stop)
        self.addCleanup(self.context_patch.stop)
        self.reader = peer.PeerSnapshotTransport.create(TARGETS, PEERS, TOKEN, "/fictional/ca.pem")

    def response(self):
        response = http.client.HTTPResponse(FakeSocket(wire()))
        response.begin()
        return response

    def test_bindings_fail_before_socket_tls_request_or_diagnostic(self):
        invalid = (None, {}, dict(PEERS, extra=("127.0.0.1", 443)),
                   dict(PEERS, input=["127.0.0.1", 443]),
                   dict(PEERS, input=("localhost", 443)),
                   dict(PEERS, input=("127.000.0.1", 443)),
                   dict(PEERS, input=("::1%lo", 443)),
                   dict(PEERS, input=("::ffff:7f00:1", 443)),
                   dict(PEERS, input=("0.0.0.0", 443)),
                   dict(PEERS, input=("224.0.0.1", 443)),
                   dict(PEERS, input=("127.0.0.1", True)),
                   dict(PEERS, input=("127.0.0.1", 0)),
                   dict(PEERS, input=("127.0.0.1", 65536)),
                   dict(PEERS, input=("127.0.0.2", 443)),
                   dict(PEERS, input=("127.0.0.1", 23457)))
        for expected_peers in invalid:
            with self.subTest(kind=type(expected_peers).__name__):
                diagnostic = mock.Mock()
                self.assertEqual(self.reader.guarded_diagnostic(TARGETS, expected_peers, diagnostic),
                                 guard.UNVERIFIED)
                diagnostic.assert_not_called()
        self.assertEqual(self.events, [])
        peer.socket.socket.assert_not_called()
        self.context.wrap_socket.assert_not_called()
        self.encrypted.sendall.assert_not_called()

    def test_invalid_constructor_and_direct_read_are_disconnected(self):
        self.assertIsNone(peer.PeerSnapshotTransport.create(TARGETS, None, TOKEN, "/fictional/ca.pem"))
        self.assertIsNone(self.reader("input"))
        self.assertEqual(self.events, [])
        self.assertEqual(guard.guarded_diagnostic(TARGETS, self.reader, mock.Mock()), guard.UNVERIFIED)
        self.assertEqual(self.events, [])

    def test_wrong_target_map_and_mutated_caller_bindings_send_nothing(self):
        configured = dict(PEERS)
        reader = peer.PeerSnapshotTransport.create(TARGETS, configured, TOKEN, "/fictional/ca.pem")
        configured["input"] = ("127.0.0.2", 443)
        diagnostic = mock.Mock()
        self.assertEqual(reader.guarded_diagnostic(TARGETS, configured, diagnostic), guard.UNVERIFIED)
        swapped = {"input": TARGETS["platform_state"], "platform_state": TARGETS["input"]}
        self.assertEqual(reader.guarded_diagnostic(swapped, PEERS, diagnostic), guard.UNVERIFIED)
        diagnostic.assert_not_called()
        peer.socket.socket.assert_not_called()

    def test_peer_and_tls_checks_precede_any_header_send(self):
        connection = peer._PeerHTTPSConnection("input.example.invalid", PEERS["input"], self.context)
        connection.request("GET", "/container/input.json", headers={"Authorization": "Bearer " + TOKEN})
        self.assertEqual(self.events, ["connect", "peer", "tls", "tls-peer", "send"])
        self.context.wrap_socket.assert_called_once_with(self.raw, server_hostname="input.example.invalid")
        self.raw.connect.assert_called_once_with(("127.0.0.1", 443))
        connection.close()

    def test_wrong_peer_or_bad_tls_never_sends_authorization(self):
        for phase in ("raw-ip", "raw-port", "tls-peer", "tls-error", "disabled-verification"):
            with self.subTest(phase=phase):
                self.events.clear()
                self.encrypted.sendall.reset_mock()
                self.raw.getpeername.side_effect = None
                self.raw.getpeername.return_value = ("127.0.0.2" if phase == "raw-ip" else "127.0.0.1",
                                                    444 if phase == "raw-port" else 443)
                self.encrypted.getpeername.side_effect = None
                self.encrypted.getpeername.return_value = (
                    "127.0.0.2" if phase == "tls-peer" else "127.0.0.1", 443
                )
                self.context.wrap_socket.side_effect = (
                    ssl.SSLError("fictional-sensitive-error") if phase == "tls-error" else None
                )
                self.context.check_hostname = phase != "disabled-verification"
                diagnostic = mock.Mock()
                output, errors = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
                    result = self.reader.guarded_diagnostic(TARGETS, PEERS, diagnostic)
                self.assertEqual(result, guard.UNVERIFIED)
                diagnostic.assert_not_called()
                self.encrypted.sendall.assert_not_called()
                self.assertEqual((output.getvalue(), errors.getvalue()), ("", ""))

    def test_literal_ipv6_and_shared_peers(self):
        values = dict.fromkeys(guard.ROLES, ("::1", 443))
        reader = peer.PeerSnapshotTransport.create(TARGETS, values, TOKEN, "/fictional/ca.pem")
        self.assertIsNotNone(reader)
        self.raw.getpeername.side_effect = None
        self.raw.getpeername.return_value = ("::1", 443, 0, 0)
        self.encrypted.getpeername.side_effect = None
        self.encrypted.getpeername.return_value = ("::1", 443, 0, 0)
        connection = reader._connection("input")
        peer.socket.socket.assert_called_with(socket.AF_INET6, socket.SOCK_STREAM)
        self.raw.connect.assert_called_with(("::1", 443, 0, 0))
        connection.close()
        self.encrypted.getpeername.return_value = ("::1", 443, 0, 1)
        with self.assertRaises(ValueError):
            reader._connection("input")

    def test_repeated_reads_and_mutation_keep_precedence(self):
        expected, expected_peers = dict(TARGETS), dict(PEERS)

        def diagnostic():
            expected["input"] = "https://changed.example.invalid/container/input"
            expected_peers["input"] = ("127.0.0.2", 443)
            return guard.DIAGNOSTIC_SUCCESS

        with mock.patch.object(peer._PeerHTTPSConnection, "getresponse", side_effect=self.response):
            self.assertEqual(self.reader.guarded_diagnostic(expected, expected_peers, diagnostic), guard.PASSED)
        self.assertEqual(self.events.count("send"), 4)
        self.events.clear()

        def replace():
            object.__setattr__(self.reader, "_peers", ())
            raise RuntimeError("fictional-sensitive-error")

        with mock.patch.object(peer._PeerHTTPSConnection, "getresponse", side_effect=self.response):
            self.assertEqual(self.reader.guarded_diagnostic(TARGETS, PEERS, replace), guard.UNVERIFIED)
        self.assertEqual(self.events.count("send"), 2)

    def test_redirect_or_short_response_remains_unverified(self):
        for raw in (wire(302), wire(body=b"dat")):
            with self.subTest(kind=len(raw)):
                response = http.client.HTTPResponse(FakeSocket(raw))
                response.begin()
                diagnostic = mock.Mock()
                with mock.patch.object(peer._PeerHTTPSConnection, "getresponse", return_value=response):
                    self.assertEqual(self.reader.guarded_diagnostic(TARGETS, PEERS, diagnostic),
                                     guard.UNVERIFIED)
                diagnostic.assert_not_called()


class PeerTLSTests(tls.LoopbackTLSTests):
    @contextlib.contextmanager
    def literal_loopback_only(self, server):
        original = socket.socket.connect
        real_connection = peer._PeerHTTPSConnection

        class TestOnlyHighPortConnection(real_connection):
            def __init__(self, host, endpoint, context):
                if endpoint != ("127.0.0.1", 443):
                    raise AssertionError("Unselected test endpoint.")
                super().__init__(host, ("127.0.0.1", server.port), context)

        def guarded_connect(connection, address):
            if address != ("127.0.0.1", server.port):
                raise AssertionError("Remote connection forbidden.")
            return original(connection, address)

        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(socket.socket, "connect", guarded_connect))
            stack.enter_context(mock.patch.object(socket, "create_connection", side_effect=AssertionError))
            stack.enter_context(mock.patch.object(socket, "getaddrinfo", side_effect=AssertionError))
            stack.enter_context(mock.patch.object(peer, "_PeerHTTPSConnection", TestOnlyHighPortConnection))
            yield

    def test_real_literal_peer_tls_sni_host_and_snapshots(self):
        with self.server() as server, self.literal_loopback_only(server):
            peers = dict(PEERS)
            with mock.patch.dict(os.environ, self.environment("unrelated.pem"), clear=True):
                reader = peer.PeerSnapshotTransport.create(TARGETS, peers, TOKEN, str(self.root / "trusted.pem"))
                self.assertEqual(reader.guarded_diagnostic(
                    TARGETS, peers, lambda: guard.DIAGNOSTIC_SUCCESS), guard.PASSED)
        self.assertEqual(server.names, ["state.example.invalid", "input.example.invalid"] * 2)
        self.assertEqual(server.peers, ["127.0.0.1"] * 4)
        for request, hostname in zip(server.requests, server.names, strict=True):
            self.assertIn(f"\r\nHost: {hostname}\r\n".encode("ascii"), request)
        server.requests.clear()

    def test_real_literal_bad_ca_hostname_and_peer_binding_fail_closed(self):
        for bad in ("ca", "hostname", "binding"):
            with self.subTest(bad=bad):
                with self.server() as server, self.literal_loopback_only(server):
                    peers = dict(PEERS)
                    targets = dict(TARGETS)
                    if bad == "hostname":
                        targets["input"] = "https://wrong.example.invalid/container/input"
                    reader = peer.PeerSnapshotTransport.create(
                        targets, peers, TOKEN, str(self.root / ("unrelated.pem" if bad == "ca" else "trusted.pem"))
                    )
                    expected_peers = dict(peers)
                    if bad == "binding":
                        expected_peers["input"] = ("127.0.0.2", 443)
                    diagnostic = mock.Mock()
                    with mock.patch.dict(os.environ, self.environment("trusted.pem"), clear=True):
                        self.assertEqual(reader.guarded_diagnostic(targets, expected_peers, diagnostic),
                                         guard.UNVERIFIED)
                    diagnostic.assert_not_called()
                if bad != "hostname":
                    self.assertEqual(server.requests, [])
                else:
                    self.assertEqual(len(server.requests), 2)
                server.requests.clear()


if __name__ == "__main__":
    unittest.main()

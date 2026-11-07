"""Real TLS against generated fictional certificates, restricted to loopback."""
import contextlib
import os
from pathlib import Path
import shutil
import socket
import ssl
import subprocess
import tempfile
import threading
import unittest
from unittest import mock

import snapshot_http_transport as transport
import snapshot_integrity_guard as guard
from test_snapshot_http_transport import HEADERS, TARGETS, TOKEN, wire


class LoopbackTLS:
    def __init__(self, certificate, key):
        self.context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.context.load_cert_chain(str(certificate), str(key))
        self.names = []
        self.requests = []
        self.peers = []
        self.failures = []
        self.context.set_servername_callback(self._sni)
        self.stop = threading.Event()
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener.settimeout(0.2)
        self.listener.bind(("127.0.0.1", 0))
        self.port = self.listener.getsockname()[1]
        if self.port <= 1023:
            self.listener.close()
            raise AssertionError("Fictional TLS fixture requires an unprivileged port.")
        self.listener.listen(8)
        self.thread = threading.Thread(target=self._serve, name="fictional-loopback-tls")

    def _sni(self, connection, name, context):
        self.names.append(name)

    def _serve(self):
        try:
            while not self.stop.is_set():
                try:
                    connection, peer = self.listener.accept()
                except TimeoutError:
                    continue
                self.peers.append(peer[0])
                with connection:
                    connection.settimeout(2)
                    try:
                        with self.context.wrap_socket(connection, server_side=True) as stream:
                            request = b""
                            while b"\r\n\r\n" not in request and len(request) <= 16384:
                                chunk = stream.recv(4096)
                                if not chunk:
                                    break
                                request += chunk
                            if not request:
                                continue
                            if b"\r\n\r\n" not in request or len(request) > 16384:
                                raise ValueError("Incomplete fictional request.")
                            self.requests.append(request)
                            stream.sendall(wire())
                    except ssl.SSLError:
                        # Certificate-verification failures are expected test cases.
                        continue
        except BaseException:
            self.failures.append("Fictional loopback fixture failed.")

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.stop.set()
        self.thread.join(4)
        self.listener.close()
        if self.thread.is_alive():
            self.thread.join(4)
        if self.thread.is_alive() or self.failures:
            raise AssertionError("Fictional loopback worker did not finish successfully.")


@contextlib.contextmanager
def loopback_only(server):
    real_connect = socket.socket.connect
    attempts = []
    allowed_hosts = {"state.example.invalid", "input.example.invalid", "wrong.example.invalid"}

    def connect_local(connection, address):
        if address != ("127.0.0.1", server.port):
            raise AssertionError("Non-loopback connection forbidden in fictional TLS test.")
        return real_connect(connection, address)

    def mapped_connection(address, timeout=2, source_address=None, **kwargs):
        if (address[0] not in allowed_hosts or address[1] != 443
                or source_address is not None or kwargs):
            raise AssertionError("Unselected connection forbidden in fictional TLS test.")
        attempts.append(address)
        connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            connection.settimeout(min(timeout, 2))
            connection.connect(("127.0.0.1", server.port))
            return connection
        except BaseException:
            connection.close()
            raise

    with contextlib.ExitStack() as stack:
        stack.enter_context(mock.patch.object(socket, "create_connection", mapped_connection))
        stack.enter_context(mock.patch.object(socket.socket, "connect", connect_local))
        stack.enter_context(mock.patch.object(socket.socket, "connect_ex",
                                             side_effect=AssertionError("Alternate connection forbidden.")))
        stack.enter_context(mock.patch.object(socket, "getaddrinfo",
                                             side_effect=AssertionError("DNS forbidden in fictional TLS test.")))
        yield attempts


class LoopbackTLSTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.getuid() == 0:
            raise AssertionError("Fictional TLS tests must run non-root.")
        cls.openssl = shutil.which("openssl")
        if cls.openssl is None:
            raise RuntimeError("Real loopback TLS tests require local OpenSSL; not validated.")
        cls.directory = tempfile.TemporaryDirectory(prefix="fictional-snapshot-tls-")
        cls.addClassCleanup(cls.directory.cleanup)
        cls.root = Path(cls.directory.name)
        for prefix in ("trusted", "unrelated"):
            cls._openssl(
                "req", "-x509", "-newkey", "rsa:2048", "-sha256", "-nodes", "-days", "1",
                "-keyout", f"{prefix}.key", "-out", f"{prefix}.pem",
                "-subj", f"/CN=Fictional {prefix} CA",
                "-addext", "basicConstraints=critical,CA:TRUE",
                "-addext", "keyUsage=critical,keyCertSign,cRLSign",
            )
        cls._openssl(
            "req", "-new", "-newkey", "rsa:2048", "-nodes", "-keyout", "server.key",
            "-out", "server.csr", "-subj", "/CN=state.example.invalid",
        )
        (cls.root / "server.ext").write_text(
            "basicConstraints=critical,CA:FALSE\n"
            "keyUsage=critical,digitalSignature,keyEncipherment\n"
            "extendedKeyUsage=serverAuth\n"
            "subjectAltName=DNS:state.example.invalid,DNS:input.example.invalid\n",
            encoding="ascii",
        )
        cls._openssl(
            "x509", "-req", "-in", "server.csr", "-CA", "trusted.pem", "-CAkey", "trusted.key",
            "-set_serial", "3", "-days", "1", "-sha256", "-extfile", "server.ext", "-out", "server.pem",
        )
        (cls.root / "empty-ca-directory").mkdir()

    @classmethod
    def _openssl(cls, *arguments):
        try:
            result = subprocess.run(
                [cls.openssl, *arguments], cwd=cls.root,
                env={"PATH": os.environ["PATH"], "LANG": "C.UTF-8"},
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            raise RuntimeError("Fictional TLS certificate generation unavailable.") from None
        if result.returncode != 0:
            raise RuntimeError("Fictional TLS certificate generation failed.")

    def setUp(self):
        self.assertNotEqual(os.getuid(), 0)
        self.assertFalse(any(key.startswith(("AZURE_", "ARM_")) or key in
                             ("GITHUB_TOKEN", "GH_TOKEN", "ACTIONS_ID_TOKEN_REQUEST_TOKEN")
                             for key in os.environ))

    def environment(self, inherited_ca):
        return {
            "PATH": os.environ["PATH"],
            "LANG": "C.UTF-8",
            "PYTHONNOUSERSITE": "1",
            "HTTPS_PROXY": "http://proxy.example.invalid:80",
            "https_proxy": "http://proxy.example.invalid:80",
            "ALL_PROXY": "http://proxy.example.invalid:80",
            "SSL_CERT_FILE": str(self.root / inherited_ca),
            "SSL_CERT_DIR": str(self.root / "empty-ca-directory"),
        }

    def server(self):
        return LoopbackTLS(self.root / "server.pem", self.root / "server.key")

    def test_trusted_ca_hostname_sni_and_no_proxy_or_ambient_ca(self):
        with self.server() as server:
            with loopback_only(server) as attempts:
                with mock.patch.dict(os.environ, self.environment("unrelated.pem"), clear=True):
                    reader = transport.SnapshotTransport.create(
                        TARGETS, TOKEN, str(self.root / "trusted.pem")
                    )
                    self.assertIsNotNone(reader)
                    self.assertTrue(reader._context.check_hostname)
                    self.assertEqual(reader._context.verify_mode, ssl.CERT_REQUIRED)
                    records = {role: reader(role) for role in guard.ROLES}
                    self.assertEqual(guard.compare_snapshots(TARGETS, records, records), guard.PASSED)
                    self.assertEqual(records["input"]["headers"], HEADERS)
                    self.assertEqual(records["input"]["body"], b"data")
                    self.assertEqual(attempts, [("state.example.invalid", 443),
                                                ("input.example.invalid", 443)])
        self.assertEqual(server.names, ["state.example.invalid", "input.example.invalid"])
        self.assertEqual(server.peers, ["127.0.0.1", "127.0.0.1"])
        self.assertEqual(len(server.requests), 2)
        for request, host, path in zip(
                server.requests, server.names, ("/container/state.tfstate", "/container/input.json"),
                strict=True):
            self.assertTrue(request.startswith(f"GET {path} HTTP/1.1\r\n".encode("ascii")))
            self.assertIn(f"\r\nHost: {host}\r\n".encode("ascii"), request)
            self.assertIn(f"\r\nAuthorization: Bearer {TOKEN}\r\n".encode("ascii"), request)
            self.assertNotIn(TOKEN.encode("ascii"), request.split(b"\r\n", 1)[0])

    def test_wrong_hostname_is_rejected_before_http_request(self):
        targets = dict(TARGETS, platform_state="https://wrong.example.invalid/container/state.tfstate")
        with self.server() as server:
            with loopback_only(server):
                with mock.patch.dict(os.environ, self.environment("unrelated.pem"), clear=True):
                    reader = transport.SnapshotTransport.create(
                        targets, TOKEN, str(self.root / "trusted.pem")
                    )
                    self.assertIsNotNone(reader)
                    self.assertIsNone(reader("platform_state"))
        self.assertEqual(server.names, ["wrong.example.invalid"])
        self.assertEqual(server.requests, [])

    def test_wrong_ca_is_not_rescued_by_ambient_trusted_ca(self):
        with self.server() as server:
            with loopback_only(server):
                with mock.patch.dict(os.environ, self.environment("trusted.pem"), clear=True):
                    reader = transport.SnapshotTransport.create(
                        TARGETS, TOKEN, str(self.root / "unrelated.pem")
                    )
                    self.assertIsNotNone(reader)
                    self.assertIsNone(reader("platform_state"))
        self.assertEqual(server.names, ["state.example.invalid"])
        self.assertEqual(server.requests, [])

    def test_socket_mapping_denies_remote_targets_and_dns(self):
        with self.server() as server:
            with loopback_only(server) as attempts:
                with self.assertRaises(AssertionError):
                    socket.create_connection(("unselected.example.invalid", 443))
                with self.assertRaises(AssertionError):
                    socket.getaddrinfo("unselected.example.invalid", 443)
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
                    with self.assertRaises(AssertionError):
                        connection.connect(("192.0.2.123", 443))
                self.assertEqual(attempts, [])
        self.assertEqual(server.peers, [])

    def test_bound_entry_runs_only_approved_tls_rechecks(self):
        with self.server() as server:
            with loopback_only(server) as attempts:
                with mock.patch.dict(os.environ, self.environment("unrelated.pem"), clear=True):
                    reader = transport.SnapshotTransport.create(
                        TARGETS, TOKEN, str(self.root / "trusted.pem")
                    )
                    self.assertIsNotNone(reader)
                    self.assertEqual(reader.guarded_diagnostic(
                        TARGETS, lambda: guard.DIAGNOSTIC_SUCCESS), guard.PASSED)
                    self.assertEqual(attempts, [("state.example.invalid", 443),
                                                ("input.example.invalid", 443)] * 2)
        self.assertEqual(server.names, ["state.example.invalid", "input.example.invalid"] * 2)
        self.assertEqual(len(server.requests), 4)

    def test_bound_mismatch_creates_no_loopback_connection(self):
        with self.server() as server:
            with loopback_only(server) as attempts:
                with mock.patch.dict(os.environ, self.environment("unrelated.pem"), clear=True):
                    reader = transport.SnapshotTransport.create(
                        TARGETS, TOKEN, str(self.root / "trusted.pem")
                    )
                    diagnostic = mock.Mock(return_value=guard.DIAGNOSTIC_SUCCESS)
                    expected = dict(TARGETS, input="https://wrong.example.invalid/container/input.json")
                    self.assertEqual(reader.guarded_diagnostic(expected, diagnostic), guard.UNVERIFIED)
                    diagnostic.assert_not_called()
                    self.assertEqual(attempts, [])
        self.assertEqual(server.peers, [])
        self.assertEqual(server.names, [])
        self.assertEqual(server.requests, [])


if __name__ == "__main__":
    unittest.main()

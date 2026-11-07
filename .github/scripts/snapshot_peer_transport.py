"""Offline literal-peer binding; address and CA authority are external inputs."""
import http.client
import ipaddress
import socket
import ssl
from urllib.parse import urlsplit

from snapshot_http_transport import FAILURE, TIMEOUT, SnapshotTransport
from snapshot_integrity_guard import ROLES, UNVERIFIED, _expected_identities, guarded_diagnostic


def _peers(value):
    if (type(value) is not dict or len(value) != len(ROLES)
            or any(type(role) is not str for role in value) or set(value) != set(ROLES)):
        raise ValueError("Endpoint binding invalid.")
    frozen = []
    for role in ROLES:
        pair = value[role]
        if (type(pair) is not tuple or len(pair) != 2 or type(pair[0]) is not str
                or "%" in pair[0] or type(pair[1]) is not int or pair[1] != 443):
            raise ValueError("Endpoint binding invalid.")
        address = ipaddress.ip_address(pair[0])
        if (str(address) != pair[0] or address.is_unspecified or address.is_multicast
                or (address.version == 6 and address.ipv4_mapped is not None)):
            raise ValueError("Endpoint binding invalid.")
        frozen.append((role, pair))
    return tuple(frozen)


class _PeerHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host, peer, context):
        super().__init__(host, port=443, timeout=TIMEOUT, context=context)
        self._peer = peer

    def _verify_peer(self, connection):
        value = connection.getpeername()
        address = ipaddress.ip_address(self._peer[0])
        if (type(value) is not tuple or len(value) != (2 if address.version == 4 else 4)
                or type(value[0]) is not str or type(value[1]) is not int
                or ipaddress.ip_address(value[0]) != address or value[1] != self._peer[1]
                or (address.version == 6 and value[2:] != (0, 0))):
            raise ValueError("Endpoint verification failed.")

    def connect(self):
        if self._tunnel_host is not None:
            raise ValueError("Endpoint verification failed.")
        if (self._context.verify_mode != ssl.CERT_REQUIRED
                or not self._context.check_hostname):
            raise ValueError("TLS verification required.")
        address = ipaddress.ip_address(self._peer[0])
        raw = socket.socket(socket.AF_INET if address.version == 4 else socket.AF_INET6,
                            socket.SOCK_STREAM)
        try:
            raw.settimeout(TIMEOUT)
            destination = self._peer if address.version == 4 else (*self._peer, 0, 0)
            raw.connect(destination)
            self._verify_peer(raw)
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
            self._verify_peer(self.sock)
        except BaseException:
            try:
                if self.sock is not None:
                    self.close()
            finally:
                raw.close()
            raise


class PeerSnapshotTransport(SnapshotTransport):
    """Opt-in bound callback only; direct reads reject without network activity."""

    __slots__ = ("_peers",)

    @classmethod
    def create(cls, targets, peers, token, ca_file):
        try:
            if cls is not PeerSnapshotTransport:
                return FAILURE
            frozen = _peers(peers)
            base = SnapshotTransport.create(targets, token, ca_file)
            if base is None:
                return FAILURE
            instance = cls()
            for name in ("_targets", "_token", "_context"):
                object.__setattr__(instance, name, getattr(base, name))
            object.__setattr__(instance, "_peers", frozen)
            return instance
        except BaseException:
            return FAILURE

    def __call__(self, role):
        return FAILURE

    def guarded_diagnostic(self, expected, expected_peers, diagnostic):
        try:
            if type(self) is not PeerSnapshotTransport:
                return UNVERIFIED
            targets = tuple(_expected_identities(expected).items())
            peers = _peers(expected_peers)
            sealed_targets, sealed_peers = self._targets, self._peers
            if (type(sealed_targets) is not tuple or type(sealed_peers) is not tuple
                    or any(type(pair) is not tuple or len(pair) != 2 for pair in sealed_targets)
                    or any(type(pair) is not tuple or len(pair) != 2 for pair in sealed_peers)
                    or targets != sealed_targets or peers != sealed_peers):
                return UNVERIFIED
        except BaseException:
            return UNVERIFIED

        def read(role):
            if self._targets is not sealed_targets or self._peers is not sealed_peers:
                return FAILURE
            return SnapshotTransport.__call__(self, role)

        return guarded_diagnostic(dict(targets), read, diagnostic)

    def _connection(self, role):
        host = urlsplit(dict(self._targets)[role]).hostname
        connection = _PeerHTTPSConnection(host, dict(self._peers)[role], self._context)
        try:
            # Complete peer and TLS checks before the base builds Authorization.
            connection.connect()
            return connection
        except BaseException:
            connection.close()
            raise

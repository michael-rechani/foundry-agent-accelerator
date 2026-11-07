"""Unintegrated full-GET snapshot transport; callers must establish authority."""
import contextlib
import http.client
import os
import re
import ssl
from email.utils import formatdate
from urllib.parse import urlsplit

from snapshot_integrity_guard import ROLES, _identity

MAX_BODY = 64_000_000
TIMEOUT = 10
FAILURE = None


class SnapshotTransport:
    """Synchronous, single-thread callback. Invalid inputs return a fixed failure."""

    __slots__ = ("_targets", "_token", "_context")

    def __setattr__(self, name, value):
        raise AttributeError("Snapshot transport configuration is frozen.")

    @classmethod
    def create(cls, targets, token, ca_file):
        try:
            if type(targets) is not dict or set(targets) != set(ROLES):
                return FAILURE
            frozen = tuple((role, _identity(targets[role])) for role in ROLES)
            if (len({identity for _, identity in frozen}) != len(ROLES)
                    or any("?" in identity or "#" in identity for _, identity in frozen)):
                return FAILURE
            if (type(token) is not str or len(token) > 16384
                    or re.fullmatch(r"[A-Za-z0-9._~+/-]+=*", token) is None):
                return FAILURE
            if (type(ca_file) is not str or not os.path.isabs(ca_file)
                    or "\x00" in ca_file):
                return FAILURE
            # Do not call create_default_context or load_default_certs: their
            # default OpenSSL CA paths may be overridden by the environment.
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.load_verify_locations(cafile=ca_file)
            instance = cls()
            object.__setattr__(instance, "_targets", frozen)
            object.__setattr__(instance, "_token", token)
            object.__setattr__(instance, "_context", context)
            return instance
        except BaseException:
            return FAILURE

    def __call__(self, role):
        try:
            if type(role) is not str or role not in ROLES:
                return FAILURE
            identity = dict(self._targets)[role]
            target = urlsplit(identity)
            with contextlib.closing(http.client.HTTPSConnection(
                target.netloc, port=443, timeout=TIMEOUT, context=self._context
            )) as connection:
                connection.debuglevel = 0
                connection.request(
                    "GET", target.path,
                    headers={
                        "Authorization": "Bearer " + self._token,
                        "x-ms-date": formatdate(usegmt=True),
                        "x-ms-version": "2023-11-03",
                        "Accept-Encoding": "identity",
                        "Connection": "close",
                    },
                )
                response = connection.getresponse()
                if response.status != 200 or response.headers.defects:
                    return FAILURE
                headers = tuple(response.headers.raw_items())
                if not 0 < len(headers) <= 128:
                    return FAILURE
                names = []
                for name, value in headers:
                    if (type(name) is not str or re.fullmatch(r"[A-Za-z0-9-]{1,128}", name) is None
                            or type(value) is not str or len(value) > 8192
                            or any(ord(char) < 32 or ord(char) > 126 for char in value)):
                        return FAILURE
                    names.append(name.lower())
                if len(set(names)) != len(names):
                    return FAILURE
                fields = dict(zip(names, (value for _, value in headers), strict=True))
                length = fields.get("content-length", "")
                if (re.fullmatch(r"[1-9][0-9]{0,7}", length) is None
                        or int(length) > MAX_BODY or "transfer-encoding" in fields
                        or "content-range" in fields):
                    return FAILURE
                body = response.read(int(length))
                if type(body) is not bytes or len(body) != int(length):
                    return FAILURE
                return {"identity": identity, "status": 200, "body": body, "headers": headers}
        except BaseException:
            return FAILURE

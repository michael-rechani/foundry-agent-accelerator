"""Synthetic full-GET snapshot contract; no transport, authority or live integration."""
import contextlib
from datetime import datetime
import re
from urllib.parse import urlsplit

UNVERIFIED = "Snapshot integrity unverified; no diagnostic outcome."
FAILED = "Diagnostic failed after endpoint snapshot rechecks."
PASSED = "Diagnostic completed with equal endpoint snapshots only."
ROLES = ("platform_state", "input")
REQUIRED = frozenset({"etag", "last-modified", "x-ms-creation-time", "content-length",
                      "x-ms-version", "x-ms-blob-type", "x-ms-lease-status", "x-ms-lease-state"})
OPTIONAL = frozenset({"content-type", "content-md5", "content-encoding", "content-language",
                      "cache-control", "content-disposition", "x-ms-server-encrypted",
                      "x-ms-encryption-key-sha256", "x-ms-encryption-scope", "x-ms-lease-duration", "x-ms-version-id"})
VOLATILE = frozenset({"date", "server", "x-ms-request-id", "x-ms-client-request-id", "accept-ranges"})


class SnapshotError(Exception):
    pass


class _Discard:
    def write(self, value):
        return len(value)

    def flush(self):
        pass


def _identity(value):
    if type(value) is not str or len(value) > 2048:
        raise SnapshotError(UNVERIFIED)
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or not parsed.netloc or parsed.username is not None
            or parsed.password is not None or parsed.query or parsed.fragment
            or re.fullmatch(r"[a-z0-9]+(?:[.-][a-z0-9]+)*", parsed.netloc) is None
            or re.fullmatch(r"/[a-z0-9-]+/(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_.-]+", parsed.path) is None
            or any(part in (".", "..") for part in parsed.path.split("/"))):
        raise SnapshotError(UNVERIFIED)
    return value


def _snapshot(value, identity):
    if type(value) is not dict or set(value) != {"identity", "status", "body", "headers"}:
        raise SnapshotError(UNVERIFIED)
    if (_identity(value["identity"]) != identity or type(value["status"]) is not int
            or value["status"] != 200 or type(value["body"]) is not bytes
            or not 0 < len(value["body"]) <= 64_000_000
            or type(value["headers"]) is not tuple or not 0 < len(value["headers"]) <= 128):
        raise SnapshotError(UNVERIFIED)
    headers = {}
    for pair in value["headers"]:
        if type(pair) is not tuple or len(pair) != 2:
            raise SnapshotError(UNVERIFIED)
        name, content = pair
        if (type(name) is not str or re.fullmatch(r"[A-Za-z0-9-]{1,128}", name) is None
                or type(content) is not str or len(content) > 8192
                or any(ord(char) < 32 or ord(char) > 126 for char in content)):
            raise SnapshotError(UNVERIFIED)
        name = name.lower()
        if name in headers:
            raise SnapshotError(UNVERIFIED)
        if (name not in REQUIRED | OPTIONAL | VOLATILE
                and re.fullmatch(r"x-ms-meta-[a-z_][a-z0-9_]*", name) is None):
            raise SnapshotError(UNVERIFIED)
        headers[name] = content
    if (not REQUIRED <= headers.keys()
            or re.fullmatch(r'"[^"\s]+"', headers["etag"]) is None
            or headers["content-length"] != str(len(value["body"]))
            or headers["x-ms-version"] != "2023-11-03"
            or headers["x-ms-blob-type"] != "BlockBlob"
            or headers["x-ms-lease-status"] != "unlocked"
            or headers["x-ms-lease-state"] != "available"
            or "x-ms-lease-duration" in headers
            or "x-ms-meta-terraformlockid" in headers):
        raise SnapshotError(UNVERIFIED)
    if "x-ms-version-id" in headers and not headers["x-ms-version-id"]:
        raise SnapshotError(UNVERIFIED)
    for name in ("last-modified", "x-ms-creation-time"):
        if re.fullmatch(r"(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun), [0-9]{2} "
                        r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) [0-9]{4} "
                        r"[0-9]{2}:[0-9]{2}:[0-9]{2} GMT", headers[name]) is None:
            raise SnapshotError(UNVERIFIED)
        try:
            stamp = datetime.strptime(headers[name], "%a, %d %b %Y %H:%M:%S GMT")
        except ValueError:
            raise SnapshotError(UNVERIFIED) from None
        if stamp.strftime("%a, %d %b %Y %H:%M:%S GMT") != headers[name]:
            raise SnapshotError(UNVERIFIED)
    return (identity, value["body"], tuple(sorted((name, content) for name, content in headers.items()
                                               if name not in VOLATILE)))


def compare_snapshots(expected, before, after):
    """Fixed output only. Unknown properties fail closed; no lease ID is fabricated."""
    try:
        if (type(expected) is not dict or set(expected) != set(ROLES)
                or type(before) is not dict or set(before) != set(ROLES)
                or type(after) is not dict or set(after) != set(ROLES)):
            raise SnapshotError(UNVERIFIED)
        identities = {role: _identity(expected[role]) for role in ROLES}
        if len(set(identities.values())) != 2:
            raise SnapshotError(UNVERIFIED)
        left = {role: _snapshot(before[role], identities[role]) for role in ROLES}
        right = {role: _snapshot(after[role], identities[role]) for role in ROLES}
        return PASSED if left == right else UNVERIFIED
    except (SnapshotError, ValueError, TypeError, KeyError):
        return UNVERIFIED


def guarded_diagnostic(expected, read, diagnostic):
    """Single-thread synchronous callbacks must finish and be fully supervised.

    Every boundary attempts both roles even when a read fails. The frozen baseline
    is captured immediately; callback data cannot rewrite it. Stream redirection
    is not a subprocess/security sandbox. This helper does not implement timeouts.
    """
    with contextlib.redirect_stdout(_Discard()), contextlib.redirect_stderr(_Discard()):
        try:
            if type(expected) is not dict or set(expected) != set(ROLES):
                raise SnapshotError(UNVERIFIED)
            identities = {role: _identity(expected[role]) for role in ROLES}
            if len(set(identities.values())) != 2:
                raise SnapshotError(UNVERIFIED)
        except (SnapshotError, ValueError, TypeError, KeyError):
            identities = None

        def capture():
            pair = {}
            for role in ROLES:
                try:
                    value = read(role)
                    pair[role] = _snapshot(value, identities[role]) if identities is not None else None
                except BaseException:
                    pair[role] = None
            return pair

        before = capture()
        valid = all(before[role] is not None for role in ROLES)
        failed = False
        try:
            if valid:
                diagnostic()
        except BaseException:
            failed = True
        finally:
            after = capture()
        if not valid or before != after or any(after[role] is None for role in ROLES):
            return UNVERIFIED
        return FAILED if failed else PASSED

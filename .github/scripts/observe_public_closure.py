"""One bounded public-artifact observation; no extraction or artifact code execution."""

import hashlib
import io
import json
import os
import re
import ssl
import sys
import time
from urllib import error, parse, request
import zipfile

import public_closure_transport as transport
from test_azapi_registration_overlay import assert_no_azapi_bypass_bytes

REPOSITORY = "michael-rechani/foundry-agent-accelerator"
ARTIFACT = 13588508507
RUN = 42409161870
ZIP_SHA = "a6620be72b125b4860cd13c7edb5644bd5e51ba89d65477e23ec533925a46838"
TAR_SHA = "7afd7b7630954d34b9a83876369058eec6500cef0ddb4deac8b2d37872fa0e55"
MANIFEST_SHA = "f6cee223894fae61d3d9bb2cac17ae86df38c1c6ed72d390dd7498b9a1df70b0"
SOURCE_SHA = "446b078df12c9a08daec7bc5e9f0b5a57d8d7a5d"
MAX_ZIP = 200_000_000
MAX_MANIFEST = 8_000_000
MAX_SOURCE = 2_000_000
MAX_SOURCES = 5000
MAX_SOURCE_TOTAL = 40_000_000
MAX_MODULES = 2000
MAX_JSON_DEPTH = 64
MAX_SECONDS = 180
API_URL = f"https://api.github.com/repos/{REPOSITORY}/actions/artifacts/{ARTIFACT}/zip"
CATEGORIES = frozenset({
    "accepted", "integrity_mismatch", "archive_refused", "manifest_refused",
    "graph_refused", "source_bounds", "download_refused", "runtime_refused",
    "scanner_provider_routing", "scanner_unsupported_hcl", "scanner_ambiguous_hcl",
    "scanner_invalid_source", "scanner_invalid_json", "scanner_json_shape",
    "unexpected_failure",
})
COUNTS = (
    "archive_entries", "modules", "local_modules", "downloaded_modules",
    "unique_sources", "source_visits", "hcl_sources", "json_sources",
    "source_bytes", "checked_sources", "refused_sources",
)


class ObservationError(Exception):
    def __init__(self, category):
        super().__init__(category if category in CATEGORIES else "unexpected_failure")
        self.category = str(self)


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def opener():
    # No proxy environment, HTTP fallback, custom trust, or automatic redirects.
    return request.build_opener(
        request.ProxyHandler({}), NoRedirect(),
        request.HTTPSHandler(context=ssl.create_default_context()),
    )


def redirect_url(value):
    if (not isinstance(value, str) or len(value) > 8192
            or not value.isascii() or any(ord(c) <= 32 or ord(c) == 127 for c in value)
            or "\\" in value):
        raise ObservationError("download_refused")
    parts = parse.urlsplit(value)
    # GitHub Actions artifact service's current public signed-blob transport only.
    if (parts.scheme != "https" or parts.username is not None or parts.password is not None
            or parts.port is not None or parts.fragment
            or not re.fullmatch(r"productionresultssa[0-9]+\.blob\.core\.windows\.net",
                                parts.hostname or "")
            or not parts.path.startswith("/") or not parts.query
            or "%" in parts.netloc):
        raise ObservationError("download_refused")
    return value


def bounded_read(response, maximum, deadline):
    if (response.headers.get("Content-Encoding") not in (None, "identity")
            or response.headers.get("Transfer-Encoding") not in (None, "chunked")):
        raise ObservationError("download_refused")
    lengths = response.headers.get_all("Content-Length", [])
    if len(lengths) > 1 or lengths and not re.fullmatch(r"[0-9]{1,10}", lengths[0]):
        raise ObservationError("download_refused")
    expected = int(lengths[0]) if lengths else None
    if expected is not None and not 0 < expected <= maximum:
        raise ObservationError("download_refused")
    output = io.BytesIO()
    while True:
        if time.monotonic() > deadline:
            raise ObservationError("download_refused")
        chunk = response.read(min(65536, maximum - output.tell() + 1))
        if not chunk:
            break
        output.write(chunk)
        if output.tell() > maximum:
            raise ObservationError("download_refused")
    if not output.tell() or expected is not None and output.tell() != expected:
        raise ObservationError("download_refused")
    output.seek(0)
    return output


def download(token, client=None):
    if not isinstance(token, str) or not token or "\r" in token or "\n" in token:
        raise ObservationError("download_refused")
    client = client or opener()
    deadline = time.monotonic() + MAX_SECONDS
    authenticated = request.Request(  # noqa: S310 -- constant HTTPS GitHub API endpoint.
        API_URL, headers={
            "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28", "Accept-Encoding": "identity",
        },
    )
    try:
        with client.open(authenticated, timeout=20) as response:
            if response.status != 200:
                raise ObservationError("download_refused")
            return bounded_read(response, MAX_ZIP, deadline)
    except error.HTTPError as exc:
        try:
            if exc.code != 302 or len(exc.headers.get_all("Location", [])) != 1:
                raise ObservationError("download_refused") from None
            destination = redirect_url(exc.headers["Location"])
        finally:
            exc.close()
    # Construct a NEW request: no GitHub Authorization header on blob storage.
    anonymous = request.Request(  # noqa: S310 -- strict HTTPS signed-blob allowlist above.
        destination, headers={"Accept-Encoding": "identity"},
    )
    with client.open(anonymous, timeout=20) as response:
        if response.status != 200:
            raise ObservationError("download_refused")
        return bounded_read(response, MAX_ZIP, deadline)


def verified_zip(stream, zip_sha, tar_sha):
    stream.seek(0, os.SEEK_END)
    length = stream.tell()
    if not 0 < length <= MAX_ZIP:
        raise ObservationError("archive_refused")
    stream.seek(0)
    if hashlib.file_digest(stream, "sha256").hexdigest() != zip_sha:
        raise ObservationError("integrity_mismatch")
    stream.seek(0)
    # Canonical single-file, non-ZIP64 ZIP. Reject trailing bytes and ZIP comments.
    if length < 22:
        raise ObservationError("archive_refused")
    stream.seek(-22, os.SEEK_END)
    end = stream.read(22)
    if (end[:4] != b"PK\x05\x06" or end[4:8] != b"\0" * 4
            or end[8:12] != b"\x01\0\x01\0" or end[20:] != b"\0\0"):
        raise ObservationError("archive_refused")
    central_size = int.from_bytes(end[12:16], "little")
    central_offset = int.from_bytes(end[16:20], "little")
    if not 46 <= central_size <= 8192 or central_size + central_offset != length - 22:
        raise ObservationError("archive_refused")
    stream.seek(0)
    with zipfile.ZipFile(stream) as archive:
        members = archive.infolist()
        if len(members) != 1:
            raise ObservationError("archive_refused")
        member = members[0]
        mode = member.external_attr >> 16
        if (member.filename != "public-closure.tar.gz" or member.orig_filename != member.filename
                or member.is_dir() or member.header_offset != 0 or member.flag_bits & ~0x808
                or member.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)
                or member.extra or member.comment or member.create_system not in (0, 3)
                or mode and mode & 0o170000 not in (0, 0o100000)
                or not 0 < member.file_size <= transport.MAX_COMPRESSED
                or not 0 < member.compress_size <= MAX_ZIP):
            raise ObservationError("archive_refused")
        stream.seek(0)
        local = stream.read(30)
        name_length = int.from_bytes(local[26:28], "little")
        extra_length = int.from_bytes(local[28:30], "little")
        if (local[:4] != b"PK\x03\x04" or extra_length
                or name_length != len(member.filename)
                or stream.read(name_length) != member.filename.encode("ascii")
                or int.from_bytes(local[6:8], "little") != member.flag_bits
                or int.from_bytes(local[8:10], "little") != member.compress_type):
            raise ObservationError("archive_refused")
        end_body = 30 + name_length + member.compress_size
        if member.flag_bits & 8:
            if central_offset != end_body + 16:
                raise ObservationError("archive_refused")
            stream.seek(end_body)
            descriptor = stream.read(16)
            if (descriptor[:4] != b"PK\x07\x08"
                    or int.from_bytes(descriptor[4:8], "little") != member.CRC
                    or int.from_bytes(descriptor[8:12], "little") != member.compress_size
                    or int.from_bytes(descriptor[12:16], "little") != member.file_size):
                raise ObservationError("archive_refused")
        elif (central_offset != end_body
              or int.from_bytes(local[14:18], "little") != member.CRC
              or int.from_bytes(local[18:22], "little") != member.compress_size
              or int.from_bytes(local[22:26], "little") != member.file_size):
            raise ObservationError("archive_refused")
        compressed = io.BytesIO()
        with archive.open(member) as body:
            while chunk := body.read(min(65536, transport.MAX_COMPRESSED - compressed.tell() + 1)):
                compressed.write(chunk)
                if compressed.tell() > transport.MAX_COMPRESSED:
                    raise ObservationError("archive_refused")
        if compressed.tell() != member.file_size:
            raise ObservationError("archive_refused")
        compressed.seek(0)
        if hashlib.file_digest(compressed, "sha256").hexdigest() != tar_sha:
            raise ObservationError("integrity_mismatch")
        compressed.seek(0)
        return compressed


def unique_pairs(items):
    value = {}
    for key, item in items:
        if key in value:
            raise ObservationError("manifest_refused")
        value[key] = item
    return value


def invalid_constant(_value):
    raise ObservationError("manifest_refused")


def strict_json(raw):
    try:
        result = json.loads(raw, object_pairs_hook=unique_pairs, parse_constant=invalid_constant)
        pending = [(result, 0)]
        nodes = 0
        while pending:
            value, depth = pending.pop()
            nodes += 1
            if depth > MAX_JSON_DEPTH or nodes > 200_000:
                raise ObservationError("manifest_refused")
            if isinstance(value, dict):
                pending.extend((item, depth + 1) for item in value.values())
            elif isinstance(value, list):
                pending.extend((item, depth + 1) for item in value)
        return result
    except (ValueError, UnicodeError, RecursionError):
        raise ObservationError("manifest_refused") from None


def relative(value):
    if not isinstance(value, str):
        raise ObservationError("manifest_refused")
    try:
        return transport.member_path(transport.ROOT + "/" + value)[len(transport.ROOT) + 1:]
    except transport.ExtractionError:
        raise ObservationError("manifest_refused") from None


def read_member(stream, entry, bound):
    _, directory, _, size, offset = entry
    if directory or size > bound:
        raise ObservationError("source_bounds")
    stream.seek(offset)
    raw = stream.read(size)
    if len(raw) != size:
        raise ObservationError("archive_refused")
    return raw


def verify_manifest(expanded, entries, manifest_sha, source_sha):
    prefix = transport.ROOT + "/"
    index = {name[len(prefix):]: entry for entry in entries
             if (name := entry[0]) != transport.ROOT}
    if "manifest.json" not in index:
        raise ObservationError("manifest_refused")
    raw = read_member(expanded, index["manifest.json"], MAX_MANIFEST)
    if hashlib.sha256(raw).hexdigest() != manifest_sha:
        raise ObservationError("integrity_mismatch")
    manifest = strict_json(raw)
    if (not isinstance(manifest, dict) or set(manifest) != {
            "format", "source_sha", "source_files", "terraform", "platform", "provenance",
            "files", "modules", "providers",
    } or type(manifest["format"]) is not int or manifest["format"] != 1
            or manifest["source_sha"] != source_sha or manifest["terraform"] != "1.16.4"
            or manifest["platform"] != "linux_amd64"
            or manifest["provenance"] != "generated-public-resolution-not-reviewed"):
        raise ObservationError("manifest_refused")
    providers = manifest["providers"]
    if (not isinstance(providers, dict) or not 0 < len(providers) <= 100
            or not all(isinstance(k, str) and isinstance(v, str) and 0 < len(k) <= 200
                       and 0 < len(v) <= 100 for k, v in providers.items())):
        raise ObservationError("manifest_refused")
    files = manifest["files"]
    if not isinstance(files, dict) or not 0 < len(files) <= transport.MAX_ENTRIES:
        raise ObservationError("manifest_refused")
    if set(index) - {"manifest.json"} != set(files):
        raise ObservationError("manifest_refused")
    for name, record in files.items():
        path = relative(name)
        if (path.split("/")[0] not in ("root", "mirror") or not isinstance(record, dict)
                or set(record) != {"sha256", "mode"}):
            raise ObservationError("manifest_refused")
        entry = index[path]
        if type(record["mode"]) is not int or entry[2] != record["mode"]:
            raise ObservationError("manifest_refused")
        if entry[1]:
            digest = "directory"
        else:
            expanded.seek(entry[4])
            remaining = entry[3]
            hasher = hashlib.sha256()
            while remaining:
                chunk = expanded.read(min(65536, remaining))
                if not chunk:
                    raise ObservationError("archive_refused")
                remaining -= len(chunk)
                hasher.update(chunk)
            digest = hasher.hexdigest()
        if record["sha256"] != digest:
            raise ObservationError("integrity_mismatch")
    sources = manifest["source_files"]
    if not isinstance(sources, dict) or not sources or len(sources) > transport.MAX_ENTRIES:
        raise ObservationError("manifest_refused")
    for name, record in sources.items():
        relative(name)
        if files.get("root/" + name) != record or index["root/" + name][1]:
            raise ObservationError("manifest_refused")
    if "root/.terraform.lock.hcl" not in files or index["root/.terraform.lock.hcl"][1]:
        raise ObservationError("manifest_refused")
    return manifest, index


def graph_sources(expanded, manifest, index, counts):
    graph_entry = index.get("root/.terraform/modules/modules.json")
    if graph_entry is None:
        raise ObservationError("graph_refused")
    graph = strict_json(read_member(expanded, graph_entry, MAX_MANIFEST))
    modules = manifest["modules"]
    if (not isinstance(graph, dict) or set(graph) != {"Modules"} or graph["Modules"] != modules
            or not isinstance(modules, list) or not 0 < len(modules) <= MAX_MODULES):
        raise ObservationError("graph_refused")
    by_key = {}
    descendant_dirs = []
    for item in modules:
        if (not isinstance(item, dict) or set(item) - {"Key", "Source", "Version", "Dir"}
                or not {"Key", "Source", "Dir"} <= set(item)
                or not all(isinstance(v, str) and len(v) <= transport.MAX_PATH for v in item.values())
                or item["Key"] in by_key):
            raise ObservationError("graph_refused")
        key = item["Key"]
        if key and not re.fullmatch(r"[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*", key):
            raise ObservationError("graph_refused")
        by_key[key] = item
        directory = item["Dir"]
        if not key:
            if directory not in ("", ".") or item["Source"] != "":
                raise ObservationError("graph_refused")
            continue
        if not directory or directory == "." or not item["Source"]:
            raise ObservationError("graph_refused")
        relative(directory)
        name = "root/" + directory
        if name not in index or not index[name][1]:
            raise ObservationError("graph_refused")
        descendant_dirs.append(name)
        counts["modules"] += 1
        counts["downloaded_modules" if directory.startswith(".terraform/modules/")
               else "local_modules"] += 1
    if "" not in by_key or not descendant_dirs:
        raise ObservationError("graph_refused")
    for key in by_key:
        if key and key.rpartition(".")[0] not in by_key:
            raise ObservationError("graph_refused")
    actual_sources = {name for name, entry in index.items()
                      if not entry[1] and name.startswith("root/")
                      and (name.endswith(".tf") or name.endswith(".tf.json"))}
    selected = set()
    for directory in descendant_dirs:
        contained = {name for name in actual_sources if name.startswith(directory + "/")}
        if not contained:
            raise ObservationError("graph_refused")
        counts["source_visits"] += len(contained)
        selected.update(contained)
    # Every installed module source must be graph-covered. Non-module Terraform
    # sources must be recorded as captured root source, not silently unaccounted.
    for name in actual_sources:
        if name not in selected and (
                name.startswith("root/.terraform/modules/")
                or name[len("root/"):] not in manifest["source_files"]):
            raise ObservationError("graph_refused")
    if (not selected or len(selected) > MAX_SOURCES
            or counts["source_visits"] > MAX_SOURCES * MAX_MODULES):
        raise ObservationError("source_bounds")
    for name in selected:
        size = index[name][3]
        if size > MAX_SOURCE:
            raise ObservationError("source_bounds")
        counts["source_bytes"] += size
        if counts["source_bytes"] > MAX_SOURCE_TOTAL:
            raise ObservationError("source_bounds")
        counts["json_sources" if name.endswith(".tf.json") else "hcl_sources"] += 1
    counts["unique_sources"] = len(selected)
    return sorted(selected)


SCANNER_ERRORS = {
    "descendant module HCL contains provider routing syntax": "scanner_provider_routing",
    "descendant module JSON contains provider routing syntax": "scanner_provider_routing",
    "descendant module HCL uses unsupported heredoc syntax": "scanner_unsupported_hcl",
    "descendant module HCL has ambiguous delimiter structure": "scanner_ambiguous_hcl",
    "descendant module HCL is incomplete or ambiguous": "scanner_ambiguous_hcl",
    "descendant module source is unreadable or invalid": "scanner_invalid_source",
    "descendant module JSON is malformed or ambiguous": "scanner_invalid_json",
    "descendant module JSON has an unexpected root shape": "scanner_json_shape",
}


def inspect(stream, zip_sha=ZIP_SHA, tar_sha=TAR_SHA, manifest_sha=MANIFEST_SHA,
            source_sha=SOURCE_SHA):
    counts = dict.fromkeys(COUNTS, 0)
    with verified_zip(stream, zip_sha, tar_sha) as compressed, io.BytesIO() as expanded:
        try:
            length = transport.decompress_verified(compressed, expanded)
            entries = transport.validate_tar(expanded, length)
        except transport.ExtractionError:
            raise ObservationError("archive_refused") from None
        counts["archive_entries"] = len(entries)
        manifest, index = verify_manifest(expanded, entries, manifest_sha, source_sha)
        sources = graph_sources(expanded, manifest, index, counts)
        categories = set()
        # Do not stop at the first scanner refusal: inventory and visit all sources.
        for name in sources:
            raw = read_member(expanded, index[name], MAX_SOURCE)
            counts["checked_sources"] += 1
            try:
                assert_no_azapi_bypass_bytes(name, raw)
            except AssertionError as exc:
                category = SCANNER_ERRORS.get(str(exc))
                if category is None:
                    raise ObservationError("unexpected_failure") from None
                categories.add(category)
                counts["refused_sources"] += 1
        return categories or {"accepted"}, counts


def report(categories, counts, output=sys.stdout):
    if (not isinstance(categories, set) or not categories or not categories <= CATEGORIES
            or set(counts) != set(COUNTS)
            or not all(type(v) is int and 0 <= v <= 1_000_000_000 for v in counts.values())):
        categories, counts = {"unexpected_failure"}, dict.fromkeys(COUNTS, 0)
    print("observation=" + ",".join(sorted(categories)), file=output)
    for key in COUNTS:
        print(f"{key}={counts[key]}", file=output)


def main():
    try:
        if sys.platform != "linux" or os.geteuid() == 0:
            raise ObservationError("runtime_refused")
        token = os.environ.pop("PUBLIC_ARTIFACT_TOKEN", "")
        with download(token) as stream:
            categories, counts = inspect(stream)
        report(categories, counts)
        return 0 if categories == {"accepted"} else 2
    except ObservationError as exc:
        report({exc.category}, dict.fromkeys(COUNTS, 0))
    except Exception:
        # Network/archive/library errors can contain signed URLs or artifact text.
        # Explicit fixed failure, never a success-shaped fallback.
        report({"unexpected_failure"}, dict.fromkeys(COUNTS, 0))
    return 1


def unexpected_failure(_type, _value, _traceback):
    report({"unexpected_failure"}, dict.fromkeys(COUNTS, 0))


if __name__ == "__main__":
    sys.excepthook = unexpected_failure
    sys.exit(main())

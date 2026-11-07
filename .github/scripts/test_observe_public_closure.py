"""Synthetic archive and download tests; never fetch a real artifact."""

import contextlib
import gzip
import hashlib
import io
import json
from email.message import Message
import tarfile
import unittest
from unittest import mock
from urllib import error
import zipfile

import observe_public_closure as observation
import public_closure_transport as transport
from test_azapi_registration_overlay import assert_no_azapi_bypass_bytes


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def tar_bytes(items):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w", format=tarfile.GNU_FORMAT) as archive:
        for name, raw, kind in items:
            entry = tarfile.TarInfo(name)
            entry.type = kind
            entry.mode = 0o755 if kind == tarfile.DIRTYPE else 0o644
            entry.size = len(raw)
            if kind == tarfile.SYMTYPE:
                entry.linkname = "outside"
            archive.addfile(entry, io.BytesIO(raw))
    return output.getvalue()


def wrapped_zip(compressed, name="public-closure.tar.gz", duplicate=False):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(name, compressed)
        if duplicate:
            archive.writestr("extra", b"extra")
    return output.getvalue()


def fixture(source=b'resource "azapi_resource" "x" { type = "Example/type" }\n',
            transform=None):
    directories = [
        "root", "root/modules", "root/modules/local",
        "root/.terraform", "root/.terraform/modules", "root/.terraform/modules/remote",
        "mirror",
    ]
    modules = [
        {"Key": "", "Source": "", "Dir": "."},
        {"Key": "local", "Source": "./modules/local", "Dir": "modules/local"},
        {"Key": "remote", "Source": "public/example", "Dir": ".terraform/modules/remote"},
    ]
    files = {
        "root/.terraform.lock.hcl": b"# public lock fixture\n",
        "root/main.tf": b'module "local" { source = "./modules/local" }\n',
        "root/modules/local/main.tf": source,
        "root/.terraform/modules/remote/main.tf.json": b'{"resource":{}}',
        "root/.terraform/modules/modules.json": json.dumps({"Modules": modules}).encode(),
    }
    records = {name: {"sha256": "directory", "mode": 0o755} for name in directories}
    records.update({name: {"sha256": digest(raw), "mode": 0o644} for name, raw in files.items()})
    manifest = {
        "format": 1, "source_sha": observation.SOURCE_SHA, "terraform": "1.16.4",
        "platform": "linux_amd64", "provenance": "generated-public-resolution-not-reviewed",
        "files": records, "providers": {"registry.terraform.io/azure/azapi": "2.12.0"},
        "modules": modules, "source_files": {
            "main.tf": records["root/main.tf"],
            "modules/local/main.tf": records["root/modules/local/main.tf"],
        },
    }
    if transform:
        transform(manifest, files, directories)
    raw_manifest = json.dumps(manifest).encode()
    items = [("public-closure", b"", tarfile.DIRTYPE)]
    items += [("public-closure/" + name, b"", tarfile.DIRTYPE) for name in directories]
    items += [("public-closure/" + name, raw, tarfile.REGTYPE) for name, raw in files.items()]
    items.append(("public-closure/manifest.json", raw_manifest, tarfile.REGTYPE))
    compressed = gzip.compress(tar_bytes(items))
    outer = wrapped_zip(compressed)
    return outer, dict(zip_sha=digest(outer), tar_sha=digest(compressed),
                       manifest_sha=digest(raw_manifest))


class ArchiveTests(unittest.TestCase):
    def test_safe_local_and_downloaded_graph_exact_inventory(self):
        raw, pins = fixture()
        categories, counts = observation.inspect(io.BytesIO(raw), **pins)
        self.assertEqual(categories, {"accepted"})
        self.assertEqual(counts["modules"], 2)
        self.assertEqual(counts["local_modules"], 1)
        self.assertEqual(counts["downloaded_modules"], 1)
        self.assertEqual(counts["unique_sources"], 2)
        self.assertEqual(counts["checked_sources"], 2)
        self.assertEqual(counts["source_visits"], 2)

    def test_all_three_integrity_mismatches(self):
        raw, pins = fixture()
        for key in pins:
            with self.subTest(key=key):
                wrong = dict(pins, **{key: "0" * 64})
                with self.assertRaisesRegex(observation.ObservationError, "^integrity_mismatch$"):
                    observation.inspect(io.BytesIO(raw), **wrong)

    def test_zip_extra_escaping_link_and_trailing_entries(self):
        for name, duplicate, mode, trailing in (
            ("../public-closure.tar.gz", False, None, b""),
            ("public-closure.tar.gz", True, None, b""),
            ("public-closure.tar.gz", False, 0o120777, b""),
            ("public-closure.tar.gz", False, None, b"trailing"),
        ):
            with self.subTest(name=name, duplicate=duplicate, mode=mode, trailing=trailing):
                output = io.BytesIO()
                with zipfile.ZipFile(output, "w") as archive:
                    info = zipfile.ZipInfo(name)
                    if mode:
                        info.external_attr = mode << 16
                    archive.writestr(info, b"fake")
                    if duplicate:
                        archive.writestr("extra", b"extra")
                raw = output.getvalue() + trailing
                with self.assertRaisesRegex(observation.ObservationError, "^archive_refused$"):
                    observation.verified_zip(io.BytesIO(raw), digest(raw), digest(b"fake"))

    def test_tar_links_special_duplicate_escape_unsupported_format(self):
        base = [("public-closure", b"", tarfile.DIRTYPE)]
        cases = [
            ("public-closure/link", b"", tarfile.SYMTYPE),
            ("public-closure/fifo", b"", tarfile.FIFOTYPE),
            ("public-closure", b"", tarfile.DIRTYPE),
            ("public-closure/../escape", b"x", tarfile.REGTYPE),
            ("public-closure/pax", b"", tarfile.XHDTYPE),
        ]
        for item in cases:
            with self.subTest(kind=item[2]):
                raw = tar_bytes(base + [item])
                with self.assertRaises(transport.ExtractionError):
                    transport.validate_tar(io.BytesIO(raw), len(raw))

    def test_manifest_graph_inventory_omissions(self):
        def missing_graph(manifest, _files, _directories):
            manifest["modules"] = manifest["modules"][:-1]

        def missing_record(manifest, _files, _directories):
            manifest["files"].pop("root/modules/local/main.tf")

        def missing_directory(manifest, files, _directories):
            manifest["modules"][1]["Dir"] = "modules/missing"
            files["root/.terraform/modules/modules.json"] = json.dumps(
                {"Modules": manifest["modules"]}).encode()
            manifest["files"]["root/.terraform/modules/modules.json"]["sha256"] = digest(
                files["root/.terraform/modules/modules.json"])

        def orphan_downloaded_source(manifest, files, directories):
            directories.append("root/.terraform/modules/orphan")
            name = "root/.terraform/modules/orphan/main.tf"
            files[name] = b"locals { value = 1 }"
            manifest["files"]["root/.terraform/modules/orphan"] = {"sha256": "directory", "mode": 0o755}
            manifest["files"][name] = {"sha256": digest(files[name]), "mode": 0o644}

        for transform, category in (
            (missing_graph, "graph_refused"), (missing_record, "manifest_refused"),
            (missing_directory, "graph_refused"), (orphan_downloaded_source, "graph_refused"),
        ):
            with self.subTest(category=category):
                raw, pins = fixture(transform=transform)
                with self.assertRaisesRegex(observation.ObservationError, "^" + category + "$"):
                    observation.inspect(io.BytesIO(raw), **pins)

    def test_bounds_compressed_expanded_member_source_and_count(self):
        raw, pins = fixture()
        for module, constant, limit in (
            (observation, "MAX_ZIP", 10), (transport, "MAX_COMPRESSED", 10),
            (transport, "MAX_DECOMPRESSED", 512), (transport, "MAX_FILE", 10),
            (transport, "MAX_ENTRIES", 2), (transport, "MAX_TOTAL", 10),
            (observation, "MAX_SOURCE", 1), (observation, "MAX_SOURCE_TOTAL", 1),
            (observation, "MAX_SOURCES", 1), (observation, "MAX_MODULES", 1),
            (observation, "MAX_MANIFEST", 1),
        ):
            with self.subTest(constant=constant), mock.patch.object(module, constant, limit):
                with self.assertRaises(observation.ObservationError):
                    observation.inspect(io.BytesIO(raw), **pins)

    def test_duplicate_json_and_invalid_context(self):
        for raw in (b'{"Modules":[],"Modules":[]}', b'{"value":NaN}', b'{"bad":'):
            with self.subTest(raw=raw):
                with self.assertRaises(observation.ObservationError):
                    observation.strict_json(raw)
        raw, pins = fixture()
        with self.assertRaisesRegex(observation.ObservationError, "^manifest_refused$"):
            observation.inspect(io.BytesIO(raw), **pins, source_sha="0" * 40)

    def test_scanner_refusal_still_checks_every_source(self):
        raw, pins = fixture(b'# provider mention; private-data-must-not-print\n')
        categories, counts = observation.inspect(io.BytesIO(raw), **pins)
        self.assertEqual(categories, {"scanner_provider_routing"})
        self.assertEqual(counts["checked_sources"], counts["unique_sources"])
        self.assertEqual(counts["refused_sources"], 1)
        output = io.StringIO()
        observation.report(categories, counts, output)
        self.assertNotIn("private-data", output.getvalue())
        self.assertNotIn("main.tf", output.getvalue())

    def test_exact_scanner_sources_alias_remap_heredoc_and_json(self):
        safe = [
            ("main.tf", b'terraform { required_providers { azapi = { source = "Azure/azapi" } } }'),
            ("main.tf.json", b'{"terraform":{"required_providers":{"azapi":{"source":"Azure/azapi"}}}}'),
            ("main.tf", b'locals {\r\n value = 1\r\n}\r\n'),
        ]
        for name, raw in safe:
            assert_no_azapi_bypass_bytes(name, raw)
        refused = [
            ("main.tf", b'provider "azapi" { alias = "bypass" }'),
            ("main.tf", b'module "x" { source = "./x" providers = { azapi = azapi.bypass } }'),
            ("main.tf", b'resource "azapi_resource" "x" { provider = azapi.bypass }'),
            ("main.tf", b'configuration_aliases = [azapi.bypass]'),
            ("main.tf", b'locals { value = <<EOF\ntext\nEOF\n}'),
            ("main.tf", b'resource "x" "y" {'),
            ("main.tf", b"\xff"),
            ("main.tf.json", b'{"provider":{},"provider":{}}'),
            ("main.tf.json", b'{"prov\\u0069der":{}}'),
        ]
        for name, raw in refused:
            with self.subTest(name=name, raw=raw), self.assertRaises(AssertionError):
                assert_no_azapi_bypass_bytes(name, raw)


def response(raw=b"body", status=200, headers=None):
    result = mock.MagicMock()
    result.status = status
    result.headers = headers or Message()
    result.read.side_effect = io.BytesIO(raw).read
    result.__enter__.return_value = result
    return result


def redirect(url, code=302):
    headers = Message()
    headers["Location"] = url
    return error.HTTPError(observation.API_URL, code, "untrusted-secret-error", headers, io.BytesIO())


class DownloadTests(unittest.TestCase):
    def test_auth_only_on_constant_github_api_request(self):
        target = "https://productionresultssa10.blob.core.windows.net/path?sig=synthetic"
        client = mock.Mock()
        client.open.side_effect = [redirect(target), response()]
        self.assertEqual(observation.download("synthetic-token", client).read(), b"body")
        first, second = [call.args[0] for call in client.open.call_args_list]
        self.assertEqual(first.full_url, observation.API_URL)
        self.assertEqual(first.get_header("Authorization"), "Bearer synthetic-token")
        self.assertIsNone(second.get_header("Authorization"))
        self.assertEqual(second.full_url, target)
        self.assertEqual(dict(second.header_items()), {"Accept-encoding": "identity"})

    def test_bad_redirect_destinations_never_requested(self):
        for target in (
            "http://productionresultssa10.blob.core.windows.net/path?sig=x",
            "https://evil.example/path?sig=x", "https://api.github.com/path",
            "https://productionresultssa10.blob.core.windows.net.evil.example/path?sig=x",
            "https://user@productionresultssa10.blob.core.windows.net/path?sig=x",
            "https://productionresultssa10.blob.core.windows.net:443/path?sig=x",
            "https://productionresultssa10.blob.core.windows.net/path?sig=x#fragment",
            "https://productionresultssa10.blob.core.windows.net/path?sig=x\n",
        ):
            with self.subTest(target=target):
                client = mock.Mock()
                client.open.side_effect = redirect(target)
                with self.assertRaises(observation.ObservationError):
                    observation.download("synthetic-token", client)
                self.assertEqual(client.open.call_count, 1)

    def test_second_redirect_never_followed(self):
        client = mock.Mock()
        client.open.side_effect = [
            redirect("https://productionresultssa10.blob.core.windows.net/path?sig=x"),
            redirect("https://evil.example/secret"),
        ]
        with self.assertRaises(error.HTTPError):
            observation.download("synthetic-token", client)
        self.assertEqual(client.open.call_count, 2)
        self.assertIsNone(client.open.call_args_list[1].args[0].get_header("Authorization"))

    def test_no_proxy_safe_tls_no_automatic_redirect(self):
        with mock.patch.object(observation.request, "build_opener") as build, \
                mock.patch.object(observation.ssl, "create_default_context") as tls:
            observation.opener()
        self.assertEqual(build.call_args.args[0].proxies, {})
        self.assertIsInstance(build.call_args.args[1], observation.NoRedirect)
        tls.assert_called_once_with()
        self.assertIsNone(observation.NoRedirect().redirect_request(None, None, 302, "", {}, ""))

    def test_content_length_encoding_stream_and_deadline_bounds(self):
        for header, value in (
            ("Content-Length", "100"), ("Content-Length", "-1"),
            ("Content-Length", "1"), ("Content-Encoding", "gzip"),
        ):
            headers = Message()
            headers[header] = value
            with self.subTest(header=header, value=value), self.assertRaises(observation.ObservationError):
                observation.bounded_read(response(headers=headers), 10, float("inf"))
        with self.assertRaises(observation.ObservationError):
            observation.bounded_read(response(), 1, float("inf"))
        with self.assertRaises(observation.ObservationError):
            observation.bounded_read(response(), 10, 0)

    def test_fixed_redaction_of_unexpected_errors_and_invalid_reports(self):
        output = io.StringIO()
        with mock.patch.object(observation.sys, "platform", "linux"), \
                mock.patch.object(observation.os, "geteuid", return_value=1001), \
                mock.patch.dict(observation.os.environ, {"PUBLIC_ARTIFACT_TOKEN": "synthetic-token"}), \
                mock.patch.object(observation, "download", side_effect=ValueError("https://signed/secret")), \
                contextlib.redirect_stdout(output):
            # report's output argument is bound at import, so replace it explicitly.
            real_report = observation.report
            with mock.patch.object(observation, "report", side_effect=lambda c, n: real_report(c, n, output)):
                self.assertEqual(observation.main(), 1)
        self.assertIn("observation=unexpected_failure", output.getvalue())
        self.assertNotIn("secret", output.getvalue())
        self.assertNotIn("https", output.getvalue())
        output = io.StringIO()
        observation.report({"secret"}, {"secret": "secret"}, output)
        self.assertIn("observation=unexpected_failure", output.getvalue())
        self.assertNotIn("secret", output.getvalue())


if __name__ == "__main__":
    unittest.main()

"""Backend-disabled Terraform integration check for the exact public platform root."""

import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import check_platform_router_plan as diagnostic


def _unique_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject_json_constant(_value):
    raise ValueError("invalid JSON constant")


_ROUTING_MARKER = re.compile(r"(?i)(?<![A-Za-z0-9_-])(?:providers?|configuration_aliases)(?![A-Za-z0-9_-])")


def _has_routing_marker(value):
    return _ROUTING_MARKER.search(value) is not None


def _validate_hcl_structure(source):
    pairs = {"}": "{", "]": "[", ")": "("}
    stack = []
    quote = False
    escaped = False
    line_comment = False
    block_comment = False
    index = 0
    while index < len(source):
        char = source[index]
        following = source[index:index + 2]
        if line_comment:
            if char == "\n":
                line_comment = False
        elif block_comment:
            if following == "*/":
                block_comment = False
                index += 1
        elif quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif ord(char) == 34:
                quote = False
        elif ord(char) == 34:
            quote = True
        elif char == "#" or following == "//":
            line_comment = True
            if following == "//":
                index += 1
        elif following == "/*":
            block_comment = True
            index += 1
        elif following == "<<":
            raise AssertionError("descendant module HCL uses unsupported heredoc syntax")
        elif char in "{[(":
            stack.append(char)
        elif char in "})]":
            if not stack or stack.pop() != pairs[char]:
                raise AssertionError("descendant module HCL has ambiguous delimiter structure")
        index += 1
    if quote or block_comment or stack:
        raise AssertionError("descendant module HCL is incomplete or ambiguous")


def _contains_provider_reference(value):
    if isinstance(value, dict):
        return any(
            _has_routing_marker(key) or _contains_provider_reference(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_provider_reference(item) for item in value)
    return isinstance(value, str) and _has_routing_marker(value)


def _iter_source_files(directory):
    pending = [directory]
    while pending:
        current = pending.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    info = entry.stat(follow_symlinks=False)
                    mode = info.st_mode
                    if stat.S_ISLNK(mode):
                        raise AssertionError("descendant module contains a symlinked source entry")
                    if stat.S_ISDIR(mode):
                        pending.append(Path(entry.path))
                    elif stat.S_ISREG(mode):
                        path = Path(entry.path)
                        if path.suffix == ".tf" or path.name.endswith(".tf.json"):
                            yield path
                    else:
                        raise AssertionError("descendant module contains a special source entry")
        except OSError:
            raise AssertionError("descendant module source tree could not be inspected") from None


def assert_no_azapi_bypass_bytes(name, raw):
    """Use the identical conservative parser on bounded, verified archive bytes."""
    try:
        source = raw.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    except UnicodeError:
        raise AssertionError("descendant module source is unreadable or invalid") from None
    if name.endswith(".tf.json"):
        try:
            document = json.loads(
                source,
                object_pairs_hook=_unique_json_object,
                parse_constant=_reject_json_constant,
            )
        except (json.JSONDecodeError, ValueError):
            raise AssertionError("descendant module JSON is malformed or ambiguous") from None
        if not isinstance(document, dict):
            raise AssertionError("descendant module JSON has an unexpected root shape")
        if _contains_provider_reference(document):
            raise AssertionError("descendant module JSON contains provider routing syntax")
    else:
        if _has_routing_marker(source):
            raise AssertionError("descendant module HCL contains provider routing syntax")
        _validate_hcl_structure(source)

def assert_no_azapi_bypass(directory):
    for path in sorted(_iter_source_files(directory)):
        try:
            raw = path.read_bytes()
        except OSError:
            raise AssertionError("descendant module source is unreadable or invalid") from None
        assert_no_azapi_bypass_bytes(path.name, raw)

def _run_bundle_integration(testcase, bundle, terraform):
    manifest = json.loads((bundle / "manifest.json").read_bytes())
    testcase.assertEqual(manifest["source_sha"], diagnostic.DIAGNOSTIC_SOURCE_SHA)
    testcase.assertEqual(manifest["terraform"], "1.16.4")
    testcase.assertEqual(manifest["providers"]["registry.terraform.io/azure/azapi"], "2.12.0")
    testcase.assertEqual(manifest["providers"]["registry.terraform.io/hashicorp/azurerm"], "4.81.0")
    with tempfile.TemporaryDirectory() as folder:
        base = Path(folder)
        root = base / "terraform"
        shutil.copytree(bundle / "root", root)
        diagnostic.write_backend(root)
        overlay = json.loads((root / diagnostic.DIAGNOSTIC_OVERLAY).read_text(encoding="utf-8"))
        testcase.assertEqual(overlay["provider"]["azapi"], {"skip_provider_registration": True})
        testcase.assertEqual(overlay["provider"]["modtm"], {"enabled": False})
        existing_provider = (root / "providers.tf").read_text(encoding="utf-8")
        testcase.assertEqual(existing_provider.count('provider "azapi" {'), 1)
        testcase.assertIn("subscription_id = var.subscription_id", existing_provider)
        testcase.assertNotRegex(existing_provider, r"(?im)^\s*alias\s*=")
        home = base / "home"
        home.mkdir(mode=0o700)
        cli_config = home / "terraform.rc"
        mirror = (bundle / "mirror").resolve().as_posix()
        cli_config.write_text(
            "disable_checkpoint = true\nprovider_installation {\n  filesystem_mirror {\n"
            + f"    path = {json.dumps(mirror)}\n  }}\n}}\n", encoding="utf-8",
        )
        env = {
            "PATH": os.environ["PATH"], "HOME": str(home), "LANG": "C.UTF-8",
            "TF_CLI_CONFIG_FILE": str(cli_config), "TF_IN_AUTOMATION": "true",
            "TF_INPUT": "0", "CHECKPOINT_DISABLE": "1",
        }
        def run(args):
            result = subprocess.run(
                [terraform, f"-chdir={root}", *args], env=env,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
            )
            testcase.assertEqual(result.returncode, 0, f"captured public Terraform {args[0]} failed")
            return result.stdout
        version = json.loads(run(["version", "-json"]))
        testcase.assertEqual(version["terraform_version"], "1.16.4")
        run(["init", "-backend=false", "-get=false", "-input=false", "-lockfile=readonly", "-no-color"])
        selections = json.loads(run(["version", "-json"]))["provider_selections"]
        testcase.assertEqual(selections, manifest["providers"])
        modules_path = root / ".terraform" / "modules" / "modules.json"
        manifest_modules = json.loads(modules_path.read_text(encoding="utf-8")).get("Modules")
        testcase.assertIsInstance(manifest_modules, list)
        descendants = [entry for entry in manifest_modules if isinstance(entry, dict) and entry.get("Key")]
        testcase.assertTrue(descendants, "captured Terraform module closure must be present")
        for entry in descendants:
            module_root = (root / entry["Dir"]).resolve()
            testcase.assertTrue(module_root.is_relative_to(root.resolve()))
            testcase.assertTrue(module_root.is_dir())
            assert_no_azapi_bypass(module_root)
        validation = json.loads(run(["validate", "-json"]))
        testcase.assertIs(validation.get("valid"), True)
        testcase.assertEqual(validation.get("error_count"), 0)

class AzapiRegistrationOverlayTests(unittest.TestCase):
    def test_hcl_provider_routing_is_rejected_conservatively(self):
        cases = {
            "provider configuration": 'provider "azapi" { alias = "bypass" }',
            "same-line selector": 'data "azapi_client_config" "x" { provider = azapi.bypass }',
            "comments and whitespace": 'resource "azapi_resource" "x" { # provider selector follows\n provider /* comment */ =\n azapi.bypass\n}',
            "module remapping": 'module "x" { source = "./x" providers = { azapi = azapi.bypass } }',
            "configuration aliases": 'configuration_aliases = [azapi.bypass]',
            "comment mention": '# provider is deliberately rejected conservatively',
            "string mention": 'locals { note = "provider routing is not parsed" }',
            "nested source": 'resource "azapi_resource" "x" { provider = azapi.bypass }',
        }
        for name, source in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                path = root / "main.tf"
                if name == "nested source":
                    path = root / "nested" / "main.tf"
                    path.parent.mkdir()
                path.write_text(source, encoding="utf-8")
                with self.assertRaises(AssertionError):
                    assert_no_azapi_bypass(root)

    def test_tf_json_provider_routing_is_rejected(self):
        cases = {
            "provider configuration": '{"provider":{"azapi":[{"alias":"bypass"}]}}',
            "resource selector": '{"resource":{"azapi_resource":{"x":{"provider":"azapi.bypass"}}}}',
            "module remapping": '{"module":{"x":{"providers":{"azapi":"azapi.bypass"}}}}',
            "configuration aliases": '{"terraform":{"required_providers":{"azapi":{"configuration_aliases":["azapi.bypass"]}}}}',
            "escaped key": r'{"prov\u0069der":{"azapi":[{"alias":"bypass"}]}}',
        }
        for name, source in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as folder:
                Path(folder, "main.tf.json").write_text(source, encoding="utf-8")
                with self.assertRaises(AssertionError):
                    assert_no_azapi_bypass(Path(folder))

    def test_malformed_and_duplicate_tf_json_fail_closed(self):
        for source in ('{"resource":', '{"provider":{},"provider":{}}', '{"value":NaN}'):
            with self.subTest(source=source), tempfile.TemporaryDirectory() as folder:
                Path(folder, "main.tf.json").write_text(source, encoding="utf-8")
                with self.assertRaises(AssertionError):
                    assert_no_azapi_bypass(Path(folder))

    def test_safe_hcl_and_tf_json_without_provider_routing_pass(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "main.tf").write_text(
                'resource "azapi_resource" "x" { type = "Example/type@2024-01-01" }',
                encoding="utf-8",
            )
            (root / "main.tf.json").write_text(
                '{"resource":{"azapi_resource":{"x":{"type":"Example/type@2024-01-01"}}}}',
                encoding="utf-8",
            )
            assert_no_azapi_bypass(root)
    def test_ambiguous_hcl_fails_closed(self):
        for source in ("terraform { required_providers {", "locals { value = <<EOF\ntext\nEOF\n}"):
            with self.subTest(source=source), tempfile.TemporaryDirectory() as folder:
                Path(folder, "main.tf").write_text(source, encoding="utf-8")
                with self.assertRaises(AssertionError):
                    assert_no_azapi_bypass(Path(folder))
    def test_required_provider_declarations_pass(self):
        router_versions = """terraform {
  required_version = "~> 1.16.4"
  required_providers {
    azapi = {
      source  = "Azure/azapi"
      version = "~> 2.12.0"
    }
  }
}
"""
        benign_hcl = """terraform {
  required_providers {
    azapi = { source = "Azure/azapi", version = "~> 2.12.0" }
  }
}
"""
        benign_json = '{"terraform":{"required_providers":{"azapi":{"source":"Azure/azapi","version":"~> 2.12.0"}}}}'
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "router-versions.tf").write_text(router_versions, encoding="utf-8")
            (root / "benign.tf").write_text(benign_hcl, encoding="utf-8")
            (root / "benign.tf.json").write_text(benign_json, encoding="utf-8")
            assert_no_azapi_bypass(root)

    def test_fifo_configuration_entries_are_rejected(self):
        for name in ("main.tf", "variables.tf.json"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                os.mkfifo(root / name)
                with self.assertRaisesRegex(AssertionError, "special source entry"):
                    assert_no_azapi_bypass(root)

    def test_mocked_socket_and_device_entries_are_rejected(self):
        for mode in (stat.S_IFSOCK, stat.S_IFCHR, stat.S_IFBLK):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as folder:
                entry = mock.Mock()
                entry.path = str(Path(folder) / "main.tf")
                entry.stat.return_value.st_mode = mode
                scanner = mock.MagicMock()
                scanner.__enter__.return_value = [entry]
                with mock.patch("os.scandir", return_value=scanner):
                    with self.assertRaisesRegex(AssertionError, "special source entry"):
                        assert_no_azapi_bypass(Path(folder))
                entry.stat.assert_called_once_with(follow_symlinks=False)

    def test_vanished_or_uninspectable_entries_fail_explicitly(self):
        for error in (FileNotFoundError, PermissionError):
            with self.subTest(error=error.__name__), tempfile.TemporaryDirectory() as folder:
                entry = mock.Mock()
                entry.path = str(Path(folder) / "main.tf")
                entry.stat.side_effect = error
                scanner = mock.MagicMock()
                scanner.__enter__.return_value = [entry]
                with mock.patch("os.scandir", return_value=scanner):
                    with self.assertRaisesRegex(AssertionError, "could not be inspected"):
                        assert_no_azapi_bypass(Path(folder))
                entry.stat.assert_called_once_with(follow_symlinks=False)
    def test_unreadable_subtree_fails_explicitly(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            nested = root / "unreadable"
            nested.mkdir()
            real_scandir = os.scandir

            def fail_nested_scan(path):
                if Path(path) == nested:
                    raise PermissionError
                return real_scandir(path)

            with mock.patch("os.scandir", side_effect=fail_nested_scan):
                with self.assertRaisesRegex(AssertionError, "could not be inspected"):
                    assert_no_azapi_bypass(root)

    def test_mocked_integration_control_flow(self):
        providers = {
            "registry.terraform.io/azure/azapi": "2.12.0",
            "registry.terraform.io/hashicorp/azurerm": "4.81.0",
        }
        with tempfile.TemporaryDirectory() as folder:
            bundle = Path(folder)
            root = bundle / "root"
            module = root / "modules" / "model-router"
            module.mkdir(parents=True)
            (root / "providers.tf").write_text(
                'provider "azapi" { subscription_id = var.subscription_id }', encoding="utf-8"
            )
            (module / "versions.tf").write_text(
                'terraform { required_providers { azapi = { source = "Azure/azapi" } } }',
                encoding="utf-8",
            )
            (bundle / "mirror").mkdir()
            (bundle / "manifest.json").write_text(json.dumps({
                "source_sha": diagnostic.DIAGNOSTIC_SOURCE_SHA,
                "terraform": "1.16.4", "providers": providers,
            }), encoding="utf-8")

            def write_overlay(root_path):
                (root_path / diagnostic.DIAGNOSTIC_OVERLAY).write_text(json.dumps({
                    "provider": {
                        "azapi": {"skip_provider_registration": True},
                        "modtm": {"enabled": False},
                    }
                }), encoding="utf-8")

            fail_validate = False

            def fake_run(command, **kwargs):
                root_path = Path(command[1].split("=", 1)[1])
                arguments = command[2:]
                if arguments[0] == "init":
                    modules_path = root_path / ".terraform" / "modules"
                    modules_path.mkdir(parents=True)
                    (modules_path / "modules.json").write_text(json.dumps({
                        "Modules": [{"Key": "model-router", "Dir": "modules/model-router"}]
                    }), encoding="utf-8")
                    output = b""
                elif arguments[0] == "version":
                    output = json.dumps({
                        "terraform_version": "1.16.4", "provider_selections": providers,
                    }).encode()
                elif arguments[0] == "validate":
                    output = b'{"valid":true,"error_count":0}'
                else:
                    raise AssertionError("unexpected mocked Terraform command")
                return subprocess.CompletedProcess(command, int(fail_validate and arguments[0] == "validate"), output, b"")

            with mock.patch.object(diagnostic, "write_backend", side_effect=write_overlay), \
                    mock.patch("subprocess.run", side_effect=fake_run) as run:
                _run_bundle_integration(self, bundle, "mock-terraform")
                self.assertEqual(run.call_count, 4)
                fail_validate = True
                with self.assertRaisesRegex(AssertionError, "captured public Terraform validate failed"):
                    _run_bundle_integration(self, bundle, "mock-terraform")
    @unittest.skipUnless(os.environ.get("PUBLIC_OVERLAY_BUNDLE") and os.environ.get("OVERLAY_TERRAFORM"), "requires credential-free public closure fixture")
    def test_actual_reviewed_root_init_validate_and_descendant_provider_graph(self):
        terraform = shutil.which(os.environ.get("OVERLAY_TERRAFORM", "terraform"))
        self.assertTrue(terraform, "pinned Terraform executable required")
        _run_bundle_integration(self, Path(os.environ["PUBLIC_OVERLAY_BUNDLE"]), terraform)


if __name__ == "__main__":
    unittest.main()

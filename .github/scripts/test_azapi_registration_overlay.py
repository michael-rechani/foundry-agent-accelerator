"""Backend-disabled Terraform integration check for the exact public platform root."""

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

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


_ROUTING_MARKER = re.compile(r"(?i)(?<![A-Za-z0-9_-])(?:provider|configuration_aliases)(?![A-Za-z0-9_-])")


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
                    if entry.is_symlink():
                        raise AssertionError("descendant module contains a symlinked source entry")
                    if entry.is_dir(follow_symlinks=False):
                        pending.append(Path(entry.path))
                    elif entry.is_file(follow_symlinks=False):
                        path = Path(entry.path)
                        if path.suffix == ".tf" or path.name.endswith(".tf.json"):
                            yield path
        except OSError:
            raise AssertionError("descendant module source tree could not be inspected") from None


def assert_no_azapi_bypass(directory):
    for path in sorted(_iter_source_files(directory)):
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            raise AssertionError("descendant module source is unreadable or invalid") from None
        if path.name.endswith(".tf.json"):
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
    def test_actual_reviewed_root_init_validate_and_descendant_provider_graph(self):
        terraform = shutil.which(os.environ.get("OVERLAY_TERRAFORM", "terraform"))
        self.assertTrue(terraform, "pinned Terraform executable required")
        bundle = Path(os.environ["PUBLIC_OVERLAY_BUNDLE"])
        manifest = json.loads((bundle / "manifest.json").read_bytes())
        self.assertEqual(manifest["source_sha"], diagnostic.DIAGNOSTIC_SOURCE_SHA)
        self.assertEqual(manifest["terraform"], "1.16.4")
        self.assertEqual(manifest["providers"]["registry.terraform.io/azure/azapi"], "2.12.0")
        self.assertEqual(manifest["providers"]["registry.terraform.io/hashicorp/azurerm"], "4.81.0")

        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            root = base / "terraform"
            shutil.copytree(bundle / "root", root)
            diagnostic.write_backend(root)
            overlay = json.loads((root / diagnostic.DIAGNOSTIC_OVERLAY).read_text(encoding="utf-8"))
            self.assertEqual(overlay["provider"]["azapi"], {"skip_provider_registration": True})
            self.assertEqual(overlay["provider"]["modtm"], {"enabled": False})
            existing_provider = (root / "providers.tf").read_text(encoding="utf-8")
            self.assertEqual(len(list(AZAPI_PROVIDER_BLOCK.finditer(existing_provider))), 1)
            self.assertIn("subscription_id = var.subscription_id", existing_provider)
            self.assertNotRegex(existing_provider, r"(?im)^\s*alias\s*=")

            home = base / "home"
            home.mkdir(mode=0o700)
            cli_config = home / "terraform.rc"
            mirror = (bundle / "mirror").resolve().as_posix()
            cli_config.write_text(
                "disable_checkpoint = true\nprovider_installation {\n  filesystem_mirror {\n"
                + f"    path = {json.dumps(mirror)}\n  }}\n}}\n",
                encoding="utf-8",
            )
            env = {
                "PATH": os.environ["PATH"],
                "HOME": str(home),
                "LANG": "C.UTF-8",
                "TF_CLI_CONFIG_FILE": str(cli_config),
                "TF_IN_AUTOMATION": "true",
                "TF_INPUT": "0",
                "CHECKPOINT_DISABLE": "1",
            }

            def run(args):
                result = subprocess.run(
                    [terraform, f"-chdir={root}", *args], env=env,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
                )
                self.assertEqual(result.returncode, 0, f"captured public Terraform {args[0]} failed")
                return result.stdout

            version = json.loads(run(["version", "-json"]))
            self.assertEqual(version["terraform_version"], "1.16.4")
            run(["init", "-backend=false", "-get=false", "-input=false", "-lockfile=readonly", "-no-color"])
            selections = json.loads(run(["version", "-json"]))["provider_selections"]
            self.assertEqual(selections, manifest["providers"])

            modules_path = root / ".terraform" / "modules" / "modules.json"
            manifest_modules = json.loads(modules_path.read_text(encoding="utf-8")).get("Modules")
            self.assertIsInstance(manifest_modules, list)
            descendants = [entry for entry in manifest_modules if isinstance(entry, dict) and entry.get("Key")]
            self.assertTrue(descendants, "captured Terraform module closure must be present")
            for entry in descendants:
                module_root = (root / entry["Dir"]).resolve()
                self.assertTrue(module_root.is_relative_to(root.resolve()))
                self.assertTrue(module_root.is_dir())
                assert_no_azapi_bypass(module_root)

            validation = json.loads(run(["validate", "-json"]))
            self.assertIs(validation.get("valid"), True)
            self.assertEqual(validation.get("error_count"), 0)


if __name__ == "__main__":
    unittest.main()
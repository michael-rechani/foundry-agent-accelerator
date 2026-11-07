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


AZAPI_PROVIDER_BLOCK = re.compile(r'(?im)^\s*provider\s+"azapi"\s*\{')
AZAPI_SELECTOR = re.compile(r'(?im)^\s*provider\s*=\s*azapi(?:\.|\s|$)')
PROVIDERS_MAP = re.compile(r'(?is)\bproviders\s*=\s*\{([^}]*)\}')
CONFIGURATION_ALIASES = re.compile(r'(?is)\bconfiguration_aliases\s*=\s*\[[^]]*\bazapi\b')


def assert_no_azapi_bypass(directory):
    for path in sorted(directory.iterdir()):
        if not path.is_file() or path.suffix not in (".tf", ".json"):
            continue
        source = path.read_text(encoding="utf-8")
        if AZAPI_PROVIDER_BLOCK.search(source):
            raise AssertionError("descendant module has an explicit AzAPI provider configuration")
        if AZAPI_SELECTOR.search(source):
            raise AssertionError("descendant module selects a non-default AzAPI provider")
        if CONFIGURATION_ALIASES.search(source):
            raise AssertionError("descendant module declares an AzAPI configuration alias")
        for match in PROVIDERS_MAP.finditer(source):
            if re.search(r"\bazapi\b", match.group(1), re.IGNORECASE):
                raise AssertionError("descendant module remaps an AzAPI provider")


class AzapiRegistrationOverlayTests(unittest.TestCase):
    def test_descendant_provider_bypass_patterns_fail_closed(self):
        cases = {
            "provider block": 'provider "azapi" { alias = "other" }',
            "resource selector": 'resource "azapi_resource" "x" {\n provider = azapi.other\n}',
            "configuration alias": 'configuration_aliases = [azapi.other]',
            "module remap": 'module "x" { source = "./x" providers = { azapi = azapi.other } }',
        }
        for name, source in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as folder:
                Path(folder, "main.tf").write_text(source, encoding="utf-8")
                with self.assertRaises(AssertionError):
                    assert_no_azapi_bypass(Path(folder))
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, "main.tf").write_text(
                'resource "azapi_resource" "x" { type = "Example/type@2024-01-01" }',
                encoding="utf-8",
            )
            assert_no_azapi_bypass(Path(folder))
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
                if result.returncode:
                    detail = ""
                    if args[0] == "validate":
                        try:
                            report = json.loads(result.stdout)
                            diagnostics = report.get("diagnostics", [])
                            detail = "; ".join(
                                (str(item.get("summary", "")) + ": " + str(item.get("detail", "")))[:320]
                                for item in diagnostics if isinstance(item, dict)
                            )[:640]
                        except (json.JSONDecodeError, AttributeError):
                            detail = "unclassified"
                    self.fail(f"captured public Terraform {args[0]} failed: {detail or 'unclassified'}")
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
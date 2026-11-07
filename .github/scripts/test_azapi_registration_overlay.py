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
    def test_actual_reviewed_root_init_validate_and_descendant_provider_graph(self):
        terraform = os.environ.get("OVERLAY_TERRAFORM")
        self.assertTrue(terraform and Path(terraform).is_file(), "pinned Terraform executable required")
        source_root = Path(__file__).resolve().parents[2] / "terraform"
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            root = base / "terraform"
            shutil.copytree(source_root, root)
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
            cli_config.write_text("disable_checkpoint = true\n", encoding="utf-8")
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
                self.assertEqual(result.returncode, 0, f"public Terraform {args[0]} failed")
                return result.stdout

            version = json.loads(run(["version", "-json"]))
            self.assertEqual(version["terraform_version"], "1.16.4")
            run(["init", "-backend=false", "-input=false", "-lockfile=readonly", "-no-color"])
            selections = json.loads(run(["version", "-json"]))["provider_selections"]
            self.assertEqual(selections["registry.terraform.io/azure/azapi"], "2.12.0")
            self.assertEqual(selections["registry.terraform.io/hashicorp/azurerm"], "4.81.0")

            modules_path = root / ".terraform" / "modules" / "modules.json"
            manifest = json.loads(modules_path.read_text(encoding="utf-8"))
            modules = manifest.get("Modules")
            self.assertIsInstance(modules, list)
            descendants = [entry for entry in modules if isinstance(entry, dict) and entry.get("Key")]
            self.assertTrue(descendants, "Terraform module closure must be present")
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
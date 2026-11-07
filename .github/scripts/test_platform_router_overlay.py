"""Credential-free Linux regression against exact public root and module cache."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import check_platform_router_plan as diagnostic
import reconcile_runner_state as runner


class OverlayTests(unittest.TestCase):
    def root(self, path):
        source = Path(__file__).resolve().parents[2] / "terraform"
        for name in diagnostic.DIAGNOSTIC_ROOT_FILES:
            shutil.copyfile(source / name, path / name)

    def test_exact_root_unchanged_and_minimal_override(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.root(root)
            before = {p.name: p.read_bytes() for p in root.iterdir()}
            diagnostic.write_backend(root)
            self.assertEqual(before, {name: (root / name).read_bytes() for name in before})
            value = json.loads((root / diagnostic.DIAGNOSTIC_OVERLAY).read_bytes())
            self.assertEqual(value, {
                "terraform": {"backend": {"azurerm": {}}, "required_providers": {
                    "modtm": {"source": "azure/modtm", "version": "~> 0.3"}}},
                "provider": {
                    "azapi": {"skip_provider_registration": True},
                    "modtm": {"enabled": False},
                },
            })

    def test_unreviewed_definitions_collisions_links_and_changes(self):
        cases = {
            "backend.tf": 'terraform { backend "local" {} }',
            "added.tf": 'terraform { required_providers { modtm = { source = "hashicorp/modtm" } } }',
            "telemetry.tf": 'provider "modtm" { enabled = true }',
            "alias.tf": 'provider "modtm" { alias = "extra" }',
            "azapi-alias.tf": 'provider "azapi" { alias = "alternate" }',
            "azapi-remap.tf": 'module "router" { source = "./modules/model-router" providers = { azapi = azapi.alternate } }',
            "azapi-resource-alias.tf": 'resource "azapi_resource" "extra" { provider = azapi.alternate }',
            "override.tf": 'terraform { required_providers { azurerm = { version = "0.0.0" } } }',
            "unrelated_override.tf.json": '{}',
            "runner-diagnostic.tf": 'terraform { backend "azurerm" {} }',
            diagnostic.DIAGNOSTIC_OVERLAY: '{}',
            "versions.tf": 'terraform { required_providers {} }',
        }
        for name, content in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                self.root(root)
                (root / name).write_text(content)
                with self.assertRaises(diagnostic.CheckError):
                    diagnostic.write_backend(root)
                if name != diagnostic.DIAGNOSTIC_OVERLAY:
                    self.assertFalse((root / diagnostic.DIAGNOSTIC_OVERLAY).exists())
        for mutation in ("missing", "symlink", "hardlink", "reserved-dangling", "reserved-directory"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                self.root(root)
                if mutation == "missing":
                    (root / "versions.tf").unlink()
                elif mutation == "symlink":
                    (root / "versions.tf").rename(root / "version-copy")
                    (root / "versions.tf").symlink_to(root / "version-copy")
                elif mutation == "hardlink":
                    os.link(root / "versions.tf", root / "duplicate")
                elif mutation == "reserved-dangling":
                    (root / diagnostic.DIAGNOSTIC_OVERLAY).symlink_to(root / "missing")
                else:
                    (root / diagnostic.DIAGNOSTIC_OVERLAY).mkdir()
                with self.assertRaises(diagnostic.CheckError):
                    diagnostic.write_backend(root)

    def test_exclusive_write_rejects_late_collision(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.root(root)
            real_open = Path.open
            target = root / diagnostic.DIAGNOSTIC_OVERLAY
            def collision(path, *args, **kwargs):
                if path == target and args and args[0] == "x":
                    with real_open(target, "w") as stream:
                        stream.write("external concurrent file")
                return real_open(path, *args, **kwargs)
            with patch.object(Path, "open", collision):
                with self.assertRaises(diagnostic.CheckError):
                    diagnostic.write_backend(root)
            self.assertEqual(target.read_text(), "external concurrent file")

    def test_generation_rejects_concurrent_root_mutation(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.root(root)
            real_open = Path.open
            def mutation(path, *args, **kwargs):
                if path.name == diagnostic.DIAGNOSTIC_OVERLAY and args and args[0] == "x":
                    with real_open(root / "versions.tf", "w") as stream:
                        stream.write("changed during overlay generation")
                return real_open(path, *args, **kwargs)
            with patch.object(Path, "open", mutation):
                with self.assertRaisesRegex(diagnostic.CheckError, "changed during generation"):
                    diagnostic.write_backend(root)
    def test_generation_rejects_reserved_inode_replacement(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.root(root)
            target = root / diagnostic.DIAGNOSTIC_OVERLAY
            real_lstat = Path.lstat
            replaced = False
            def replacement(path):
                nonlocal replaced
                if path == target and not replaced:
                    replaced = True
                    saved = root / "displaced-overlay"
                    path.rename(saved)
                    path.write_bytes(saved.read_bytes())
                return real_lstat(path)
            with patch.object(Path, "lstat", replacement):
                with self.assertRaisesRegex(diagnostic.CheckError, "changed during generation"):
                    diagnostic.write_backend(root)
            self.assertTrue((root / "displaced-overlay").is_file())
            self.assertTrue(target.is_file())
    def test_azure_rm_registration_environment_remains_none_without_skip_conflict(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "root"
            scratch = Path(folder) / "scratch"
            root.mkdir()
            scratch.mkdir(mode=0o700)
            environ = {
                "AZURE_CLIENT_ID": "fictional-client",
                "AZURE_TENANT_ID": "fictional-tenant",
                "AZURE_SUBSCRIPTION_ID": "fictional-subscription",
                "TF_STATE_ACCOUNT": "fictionalaccount",
                "TF_STATE_CONTAINER": "fictional-container",
                "ARM_SKIP_PROVIDER_REGISTRATION": "true",
                "ARM_RESOURCE_PROVIDER_REGISTRATIONS": "register",
            }
            with patch.object(runner.Terraform, "command", return_value=b""):
                terraform = runner.Terraform(root, scratch, environ, "fictional.tfstate", b"{}")
            self.assertEqual(terraform.env["ARM_RESOURCE_PROVIDER_REGISTRATIONS"], "none")
            self.assertNotIn("ARM_SKIP_PROVIDER_REGISTRATION", terraform.env)
    @unittest.skipUnless(os.environ.get("PUBLIC_OVERLAY_BUNDLE"), "Public module/mirror fixture not selected.")
    def test_actual_root_module_graph_reinstall_validate_and_requirements(self):
        bundle = Path(os.environ["PUBLIC_OVERLAY_BUNDLE"])
        original = json.loads((bundle / "manifest.json").read_bytes())
        self.assertEqual(original["source_sha"], diagnostic.DIAGNOSTIC_SOURCE_SHA)
        self.assertEqual(original["terraform"], "1.16.4")
        self.assertEqual(original["providers"]["registry.terraform.io/azure/modtm"], "0.4.0")
        self.assertEqual(original["providers"]["registry.terraform.io/azure/azapi"], "2.12.0")
        self.assertEqual(original["providers"]["registry.terraform.io/hashicorp/azurerm"], "4.81.0")
        results = []
        for overlay in (False, True, "legacy"):
            with tempfile.TemporaryDirectory() as folder:
                base = Path(folder)
                root = base / "root"
                shutil.copytree(bundle / "root", root)
                original_root = {name: (root / name).read_bytes() for name in diagnostic.DIAGNOSTIC_ROOT_FILES}
                original_lock = (root / ".terraform.lock.hcl").read_bytes()
                original_modules = (root / ".terraform/modules/modules.json").read_bytes()
                if overlay == "legacy":
                    (root / "runner-diagnostic.tf").write_text(
                        'terraform {\n required_providers {\n modtm = {\n source = "azure/modtm"\n version = "~> 0.3"\n }\n }\n}\n')
                elif overlay:
                    diagnostic.write_backend(root)
                home = base / "home"
                home.mkdir(mode=0o700)
                config = home / "terraform.rc"
                config.write_text('disable_checkpoint = true\nprovider_installation {\n filesystem_mirror {\n path = '
                                  + json.dumps(str(bundle / "mirror")) + '\n }\n}\n')
                env = {"PATH": os.environ["PATH"], "HOME": str(home), "LANG": "C.UTF-8",
                       "TF_CLI_CONFIG_FILE": str(config), "TF_IN_AUTOMATION": "true", "TF_INPUT": "0",
                       "CHECKPOINT_DISABLE": "1"}
                def run(args, duplicate=False):
                    allowed = (
                        ["version", "-json"],
                        ["init", "-backend=false", "-get=false", "-lockfile=readonly", "-input=false", "-no-color"],
                        ["providers"], ["providers", "schema", "-json"], ["validate", "-json"],
                    )
                    self.assertIn(args, allowed)
                    result = subprocess.run([os.environ["OVERLAY_TERRAFORM"], f"-chdir={root}", *args],
                                            env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
                    if duplicate:
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn(b"Duplicate required providers configuration", result.stderr + result.stdout)
                    else:
                        categories = (b"Backend initialization required", b"Duplicate required providers configuration",
                                      b"Invalid provider configuration", b"Missing required argument")
                        category = next((value.decode() for value in categories if value in result.stderr + result.stdout), "unclassified")
                        headline = next((line.strip() for line in (result.stderr + result.stdout).decode(
                            errors="replace").splitlines() if line.strip().startswith("Error:")), "")
                        if not headline:
                            try:
                                report = json.loads(result.stdout)
                            except (ValueError, UnicodeError):
                                report = {}
                            diagnostics = report.get("diagnostics", []) if isinstance(report, dict) else []
                            summaries = [item.get("summary") for item in diagnostics
                                         if isinstance(item, dict) and isinstance(item.get("summary"), str)]
                            headline = "; ".join(summaries[:3])
                        self.assertEqual(result.returncode, 0, "Public offline Terraform " + args[0]
                                         + " failed: " + category + ("; " + headline if headline else ""))
                    return result.stdout
                if overlay == "legacy":
                    run(["init", "-backend=false", "-get=false", "-lockfile=readonly", "-input=false", "-no-color"], duplicate=True)
                    print("Legacy second required_providers block rejected by real Terraform.")
                    continue
                version = json.loads(run(["version", "-json"]))
                self.assertEqual((version["terraform_version"], version["platform"]), ("1.16.4", "linux_amd64"))
                run(["init", "-backend=false", "-get=false", "-lockfile=readonly", "-input=false", "-no-color"])
                selections = json.loads(run(["version", "-json"]))["provider_selections"]
                self.assertEqual(selections, original["providers"])
                # Validate the actual generated backend-bearing overlay without initializing its backend.
                validation = json.loads(run(["validate", "-json"]))
                self.assertTrue(validation["valid"])
                self.assertEqual(validation["error_count"], 0)
                if overlay:
                    # providers/schema inspect backend state; isolate requirement inspection from that backend.
                    value = json.loads((root / diagnostic.DIAGNOSTIC_OVERLAY).read_bytes())
                    self.assertEqual(value["terraform"].pop("backend"), {"azurerm": {}})
                    (root / diagnostic.DIAGNOSTIC_OVERLAY).write_text(json.dumps(value))
                    run(["init", "-backend=false", "-get=false", "-lockfile=readonly", "-input=false", "-no-color"])
                providers = run(["providers"]).decode()
                self.assertNotIn("hashicorp/modtm", providers)
                schema = json.loads(run(["providers", "schema", "-json"]))
                self.assertEqual(set(schema["provider_schemas"]), set(original["providers"]))
                validation = json.loads(run(["validate", "-json"]))
                self.assertTrue(validation["valid"])
                self.assertEqual(validation["error_count"], 0)
                self.assertEqual(original_lock, (root / ".terraform.lock.hcl").read_bytes())
                self.assertEqual(original_modules, (root / ".terraform/modules/modules.json").read_bytes())
                self.assertEqual(original_root, {name: (root / name).read_bytes() for name in original_root})
                self.assertFalse((root / ".terraform/terraform.tfstate").exists())
                self.assertFalse((root / "terraform.tfstate").exists())
                results.append(providers)
        def requirements(text, provider):
            match = re.search(r"provider\[" + re.escape(provider) + r"\]([^\n]*)", text)
            self.assertIsNotNone(match)
            return match.group(1).strip()
        for provider, expected in (("registry.terraform.io/azure/azapi", "~> 2.12.0"),
                                   ("registry.terraform.io/hashicorp/azurerm", ">= 4.81.0, < 5.0.0")):
            self.assertEqual(requirements(results[0], provider), expected)
            self.assertEqual(requirements(results[1], provider), expected)
        self.assertIn("~> 0.3", requirements(results[1], "registry.terraform.io/azure/modtm"))
        print("Exact root/full module graph: unchanged AzureRM/AzAPI requirements and all selections; azure/modtm override; backend-disabled init/schema/validate passed.")


if __name__ == "__main__":
    if os.name != "posix":
        raise SystemExit("Linux fixture validation required.")
    unittest.main()

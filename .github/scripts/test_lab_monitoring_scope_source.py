import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]


class LabMonitoringScopeSourceTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("terraform"), "Terraform is not installed")
    def test_scope_source_check_matches_the_real_scope_selection(self):
        platform = (ROOT / "workbench" / "infra" / "platform.tf").read_text(encoding="utf-8")
        monitoring = (ROOT / "workbench" / "infra" / "monitoring.tf").read_text(encoding="utf-8")
        expression = re.search(r"(?m)^  monitor_private_link_scope_name = (.+)$", platform)
        self.assertIsNotNone(expression)
        start = monitoring.index('check "monitor_private_link_scope_source" {')
        end = monitoring.index("\n}\n", start) + 2
        check = monitoring[start:end]

        config = (
            'variable "monitor_private_link_scope_name" {\n  type = string\n  default = null\n}\n'
            'variable "platform_scope" {\n  type = string\n  default = null\n}\n'
            'variable "platform_unknown" {\n  type = bool\n  default = false\n}\n'
            'resource "terraform_data" "unknown" { input = "fixture" }\n'
            "locals {\n"
            "  platform_outputs = var.platform_unknown ? "
            "{ monitor_private_link_scope_name = terraform_data.unknown.id } : (\n"
            "    var.platform_scope == null ? {} : { monitor_private_link_scope_name = var.platform_scope }\n"
            "  )\n"
            f"  monitor_private_link_scope_name = {expression.group(1)}\n"
            "}\n"
            f"{check}\n"
            'output "selected_scope" { value = local.monitor_private_link_scope_name }\n'
        )
        environment = {
            key: value for key, value in os.environ.items()
            if not key.upper().startswith(("TF_", "ARM_", "AZURE_"))
            and key.upper() not in ("GITHUB_TOKEN", "GH_TOKEN")
        }
        environment.update({"TF_IN_AUTOMATION": "true", "TF_INPUT": "0", "CHECKPOINT_DISABLE": "1"})
        cases = (
            ("missing", None, None, False, "ampls-aifnd-dev", "fail"),
            ("empty explicit", "", None, False, "ampls-aifnd-dev", "fail"),
            ("empty platform", None, "", False, "ampls-aifnd-dev", "fail"),
            ("both empty", "", "", False, "ampls-aifnd-dev", "fail"),
            ("explicit", "explicit-scope", None, False, "explicit-scope", "pass"),
            ("platform", None, "platform-scope", False, "platform-scope", "pass"),
            ("empty explicit with platform", "", "platform-scope", False, "platform-scope", "pass"),
            ("explicit with empty platform", "explicit-scope", "", False, "explicit-scope", "pass"),
            ("explicit wins", "explicit-scope", "platform-scope", False, "explicit-scope", "pass"),
            ("unknown platform", None, None, True, None, "unknown"),
            ("explicit with unknown platform", "explicit-scope", None, True, "explicit-scope", "pass"),
        )

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "main.tf").write_text(config, encoding="utf-8")
            terraform = shutil.which("terraform")
            init = subprocess.run(
                [terraform, f"-chdir={root}", "init", "-backend=false", "-input=false", "-no-color"],
                env=environment, capture_output=True, text=True, check=False,
            )
            self.assertEqual(init.returncode, 0, init.stderr)
            for name, explicit, platform_scope, unknown, expected_scope, expected_status in cases:
                with self.subTest(case=name):
                    plan = root / "fixture.tfplan"
                    args = [
                        terraform, f"-chdir={root}", "plan", "-input=false", "-lock=false",
                        "-no-color", f"-out={plan}", f"-var=platform_unknown={str(unknown).lower()}",
                    ]
                    if explicit is not None:
                        args.append(f"-var=monitor_private_link_scope_name={explicit}")
                    if platform_scope is not None:
                        args.append(f"-var=platform_scope={platform_scope}")
                    planned = subprocess.run(
                        args, env=environment, capture_output=True, text=True, check=False,
                    )
                    self.assertEqual(planned.returncode, 0, planned.stderr)
                    shown = subprocess.run(
                        [terraform, f"-chdir={root}", "show", "-json", str(plan)],
                        env=environment, capture_output=True, text=True, check=False,
                    )
                    self.assertEqual(shown.returncode, 0, shown.stderr)
                    result = json.loads(shown.stdout)
                    selected = result["planned_values"]["outputs"]["selected_scope"].get("value")
                    checks = [
                        item["status"] for item in result["checks"]
                        if item["address"]["to_display"] == "check.monitor_private_link_scope_source"
                    ]
                    self.assertEqual(selected, expected_scope)
                    self.assertEqual(checks, [expected_status])


if __name__ == "__main__":
    unittest.main()

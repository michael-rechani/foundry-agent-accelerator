import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]


class LabMonitoringQueryTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("terraform"), "Terraform is not installed")
    def test_alert_queries_match_existing_line_endings_on_lf_and_crlf_checkouts(self):
        source = (ROOT / "workbench" / "infra" / "monitoring.tf").read_text(encoding="utf-8")
        start = source.index("locals {\n  request_log_query_raw = <<-KQL\n")
        end = source.index('\n}\n\nresource "azurerm_monitor_scheduled_query_rules_alert_v2" "operational"', start)
        locals_block = source[start:end + 2]
        heartbeat = source.split('resource "azurerm_monitor_scheduled_query_rules_alert_v2" "heartbeat"', 1)[1]
        expression = re.search(r"^    query\s*=\s*(.+)$", heartbeat, re.MULTILINE)
        self.assertIsNotNone(expression)
        console = (
            'jsonencode({request_failures = local.operational_alerts["request-failures"].query, '
            'dependencies = local.operational_alerts["dependencies"].query, '
            f'heartbeat = {expression.group(1)}}})\n'
        ).encode()
        prefix = (
            "union isfuzzy=true ContainerAppConsoleLogs_CL, ContainerAppConsoleLogs\r\n"
            '| where tostring(column_ifexists("ContainerAppName_s", column_ifexists("ContainerAppName", ""))) '
            '== "lab-fixture"\r\n'
            '| extend payload = parse_json(extract(@"(\\{.*\\})", 1, '
            'tostring(column_ifexists("Log_s", column_ifexists("Log", "")))))\r\n'
        )
        expected = {
            "request_failures": prefix + "\n| where payload.event == 'workbench_request' and "
                                "(toint(payload.status) >= 500 or toint(payload.status) == 429)",
            "dependencies": prefix + "\n| where payload.event == 'workbench_dependencies' "
                                     "and payload.status != 'ready'",
            "heartbeat": prefix + "\n| where payload.event == 'workbench_dependencies'\n"
                                  "| summarize Heartbeats=count()",
        }
        env = {
            key: value for key, value in os.environ.items()
            if not key.startswith(("TF_", "ARM_", "AZURE_"))
        }
        env.update({"TF_IN_AUTOMATION": "true", "TF_INPUT": "0", "CHECKPOINT_DISABLE": "1"})
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for newline in ("\n", "\r\n"):
                with self.subTest(checkout_line_endings=repr(newline)):
                    main = 'variable "name" { default = "lab-fixture" }\n' + locals_block + "\n"
                    (root / "main.tf").write_bytes(main.replace("\n", newline).encode())
                    result = subprocess.run(
                        [shutil.which("terraform"), f"-chdir={root}", "console", "-no-color"],
                        input=console, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
                    self.assertEqual(json.loads(json.loads(result.stdout)), expected)


if __name__ == "__main__":
    unittest.main()

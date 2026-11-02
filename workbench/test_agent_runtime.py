import inspect
import io
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from zipfile import ZipFile

from agent_package import runtime_package
from agent_runtime.demo_tools import TEMPLATE_IDS, create_demo_tools
from agent_runtime.main import DEMO_POLICY, build_agent, demo_policy, read_configuration
from agent_templates import TEMPLATES

SAMPLE_LOOKUPS = {
    "workflow-coordinator": [("lookup_demo_request", "REQ-101"), ("lookup_demo_service", "SVC-DEMO-ACCESS")],
    "medical-bill-reviewer": [("lookup_plan_benefits", "PLAN-DEMO-SILVER")] + [
        ("lookup_usual_price", code) for code in ("DEMO-ER-3", "DEMO-XR-2", "DEMO-LAB-7", "DEMO-SUP-1")
    ],
    "insurance-preapproval-helper": [
        ("lookup_preapproval_rules", "PLAN-DEMO-SILVER", "DEMO-MRI-LS"), ("lookup_facility", "FAC-DEMO-22"),
    ],
    "benefits-renewal-helper": [
        ("lookup_renewal_rules", "PROG-DEMO-FOOD"), ("lookup_documents_on_file", "HH-DEMO-5150"),
    ],
    "supplier-invoice-reviewer": [
        ("lookup_purchase_order", "PO-DEMO-2210"), ("lookup_delivery_record", "PO-DEMO-2210"),
    ],
    "expense-report-checker": [
        ("lookup_expense_policy", "POL-DEMO-TRAVEL"), ("lookup_trip_request", "TRIP-DEMO-4410"),
    ],
    "order-delay-helper": [("lookup_order", "ORD-DEMO-3307"), ("lookup_shipment", "ORD-DEMO-3307")],
}


def environment(template="document-analyst"):
    return {
        "FOUNDRY_PROJECT_ENDPOINT": "https://fictional.services.ai.azure.com/api/projects/demo",
        "FOUNDRY_MODEL_NAME": "fictional-model", "AGENT_NAME": "lab-demo-fictional",
        "AGENT_INSTRUCTIONS": "Summarize only the supplied fictional text.",
        "DEMO_TEMPLATE_ID": template, "AGENT_STORE_RESPONSES": "false",
    }


class RuntimeTests(unittest.TestCase):
    def test_text_jobs_have_no_tools_and_sample_tools_are_read_only(self):
        for identifier in TEMPLATE_IDS:
            with self.subTest(identifier=identifier):
                tools = create_demo_tools(identifier, "lab-demo-fictional")
                expected = 3 if identifier == "medical-bill-reviewer" else 2 if identifier in SAMPLE_LOOKUPS else 0
                self.assertEqual(len(tools), expected)
                self.assertTrue(all("read" in tool.__doc__.lower() for tool in tools))
                self.assertTrue(all("SAMPLE DATA" in tool.__doc__ for tool in tools))

    def test_every_identifier_in_each_sample_resolves_to_a_simulated_receipt(self):
        for template, calls in SAMPLE_LOOKUPS.items():
            tools = {tool.__name__: tool for tool in create_demo_tools(template, "lab-demo-fictional")}
            expected = {call[0] for call in calls}
            if template == "medical-bill-reviewer":
                expected.add("calculate_bill_math")
            self.assertEqual(set(tools), expected)
            seen = [TEMPLATES[template]["sample_input"]]
            for name, *arguments in calls:
                with self.subTest(template=template, tool=name, arguments=arguments):
                    for argument in arguments:
                        self.assertTrue(any(argument in text for text in seen), argument)
                    result = json.loads(tools[name](*arguments))
                    seen.append(result["output"])
                    self.assertEqual((result["status"], result["agent"], result["simulation"]),
                                     ("succeeded", "lab-demo-fictional", True))
                    self.assertTrue(result["output"].startswith("SAMPLE read-only lookup."))
                    self.assertIn(arguments[-1], result["output"])
                    self.assertIn("Example only", result["output"])
                    self.assertEqual(tools[name](*[f"  {item.lower()} " for item in arguments]), tools[name](*arguments))

    def test_simulated_results_have_receipts_bound_to_actual_runtime_name(self):
        request, service = create_demo_tools("workflow-coordinator", "lab-demo-fictional")
        for tool, identifier in ((request, "REQ-101"), (service, "SVC-DEMO-ACCESS")):
            result = json.loads(tool(identifier))
            self.assertEqual(result["status"], "succeeded")
            self.assertEqual(result["agent"], "lab-demo-fictional")
            self.assertTrue(result["simulation"])
            self.assertIn("SAMPLE", result["output"])
            self.assertIn("No external system was contacted or changed", result["output"])
            self.assertIn(identifier, result["output"])
        self.assertIn("SVC-DEMO-ACCESS", json.loads(request("REQ-101"))["output"])

    def test_unknown_ids_and_unsupported_templates_do_not_fake_success(self):
        for template, name in (("unknown", "demo-agent"), ("document-analyst", ""), ("workflow-coordinator", "bad/name")):
            with self.subTest(template=template, name=name), self.assertRaises(ValueError):
                create_demo_tools(template, name)
        for template in SAMPLE_LOOKUPS:
            for tool in create_demo_tools(template, "demo-agent"):
                width = len(inspect.signature(tool).parameters)
                for identifier in ("unknown", "", "../secret", None):
                    with self.subTest(tool=tool.__name__, identifier=identifier), self.assertRaises(ValueError):
                        tool(*[identifier] * width)

    def test_lookup_results_are_read_only_and_deterministic(self):
        tools = create_demo_tools("workflow-coordinator", "demo-agent")
        first = tools[0]("REQ-101")
        result = json.loads(first)
        result["output"] = "Changed outside the tool"
        self.assertEqual(tools[0]("REQ-101"), first)

    def test_configuration_is_required_bounded_and_never_stores_responses(self):
        config = environment()
        self.assertEqual(read_configuration(config)["DEMO_TEMPLATE_ID"], "document-analyst")
        for key in ("FOUNDRY_PROJECT_ENDPOINT", "FOUNDRY_MODEL_NAME", "AGENT_NAME", "AGENT_INSTRUCTIONS", "DEMO_TEMPLATE_ID"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                read_configuration({**config, key: ""})
        for values in (
            {"DEMO_TEMPLATE_ID": "unknown"}, {"AGENT_INSTRUCTIONS": "x" * 6001},
            {"AGENT_STORE_RESPONSES": "true"}, {"FOUNDRY_PROJECT_ENDPOINT": "http://untrusted.test"},
            {"FOUNDRY_PROJECT_ENDPOINT": "https://fictional.services.ai.azure.com/api/projects/demo?token=invalid"},
        ):
            with self.subTest(values=values), self.assertRaises(ValueError):
                read_configuration({**config, **values})
        self.assertIn("SAMPLE DATA", DEMO_POLICY)
        self.assertIn("not an executed action", DEMO_POLICY)

    def test_real_sdk_agent_uses_fixed_policy_and_template_tool_set(self):
        from agent_framework import Agent
        from agent_framework.foundry import FoundryChatClient

        credential = MagicMock()
        for identifier in ("document-analyst", "workflow-coordinator", "medical-bill-reviewer"):
            with self.subTest(identifier=identifier), patch(
                "agent_framework.foundry.FoundryChatClient", wraps=FoundryChatClient,
            ) as client, patch("agent_framework.Agent", wraps=Agent) as constructor:
                agent = build_agent(credential, environment(identifier))
                self.assertIsInstance(agent, Agent)
                self.assertEqual(client.call_args.kwargs["model"], "fictional-model")
                self.assertEqual(client.call_args.kwargs["credential"], credential)
                options = constructor.call_args.kwargs
                self.assertTrue(options["instructions"].startswith(demo_policy(identifier)))
                self.assertIn(environment()["AGENT_INSTRUCTIONS"], options["instructions"])
                self.assertEqual(options["default_options"], {"store": False})
                self.assertEqual(len(options["tools"]),
                                 0 if identifier == "document-analyst" else 3 if identifier == "medical-bill-reviewer" else 2)
        credential.get_token.assert_not_called()

    def test_calculator_policy_does_not_change_other_agents(self):
        self.assertIn("sample-lookup and arithmetic tools", demo_policy("medical-bill-reviewer"))
        for identifier in TEMPLATE_IDS - {"medical-bill-reviewer"}:
            self.assertEqual(demo_policy(identifier), DEMO_POLICY)

    def test_packaged_tools_calculate_without_access_to_the_workbench(self):
        package, _ = runtime_package()
        with tempfile.TemporaryDirectory() as directory:
            with ZipFile(io.BytesIO(package)) as archive:
                archive.extractall(directory)
            script = (
                "import json, sys; sys.path.insert(0, sys.argv[1]); "
                "from demo_tools import create_demo_tools; "
                "tool = next(t for t in create_demo_tools('medical-bill-reviewer', 'demo-agent') "
                "if t.__name__ == 'calculate_bill_math'); "
                "data = {'lines': [{'label': 'one', 'amount': '2', 'quantity': '1', 'unit_price': '2'}]}; "
                "receipt = json.loads(tool(json.dumps(data))); "
                "result = json.loads(receipt['output'].split('\\n', 1)[1]); "
                "assert receipt['status'] == 'succeeded' and result['line_amount_sum'] == '$2.00'"
            )
            result = subprocess.run([sys.executable, "-I", "-c", script, directory],
                                    cwd=directory, capture_output=True, text=True, timeout=30, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()

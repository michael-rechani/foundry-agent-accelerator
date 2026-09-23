import inspect
import json
import unittest
from unittest.mock import MagicMock, patch

from agent_runtime.demo_tools import TEMPLATE_IDS, create_demo_tools
from agent_runtime.main import DEMO_POLICY, build_agent, read_configuration
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
}


def environment(template="document-analyst"):
    return {
        "FOUNDRY_PROJECT_ENDPOINT": "https://fictional.services.ai.azure.com/api/projects/demo",
        "FOUNDRY_MODEL_NAME": "fictional-model", "AGENT_NAME": "lab-demo-fictional",
        "AGENT_INSTRUCTIONS": "Summarize only the supplied fictional text.",
        "DEMO_TEMPLATE_ID": template, "AGENT_STORE_RESPONSES": "false",
    }


class RuntimeTests(unittest.TestCase):
    def test_text_jobs_have_no_tools_and_lookup_jobs_have_only_read_only_lookups(self):
        for identifier in TEMPLATE_IDS:
            with self.subTest(identifier=identifier):
                tools = create_demo_tools(identifier, "lab-demo-fictional")
                self.assertEqual(len(tools), 2 if identifier in SAMPLE_LOOKUPS else 0)
                self.assertTrue(all("read" in tool.__doc__.lower() for tool in tools))
                self.assertTrue(all("SIMULATED" in tool.__doc__ for tool in tools))

    def test_every_identifier_in_each_sample_resolves_to_a_simulated_receipt(self):
        for template, calls in SAMPLE_LOOKUPS.items():
            tools = {tool.__name__: tool for tool in create_demo_tools(template, "lab-demo-fictional")}
            self.assertEqual(set(tools), {call[0] for call in calls})
            seen = [TEMPLATES[template]["sample_input"]]
            for name, *arguments in calls:
                with self.subTest(template=template, tool=name, arguments=arguments):
                    for argument in arguments:
                        self.assertTrue(any(argument in text for text in seen), argument)
                    result = json.loads(tools[name](*arguments))
                    seen.append(result["output"])
                    self.assertEqual((result["status"], result["agent"], result["simulation"]),
                                     ("succeeded", "lab-demo-fictional", True))
                    self.assertTrue(result["output"].startswith("SIMULATED read-only fixture lookup."))
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
            self.assertIn("SIMULATED", result["output"])
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
        self.assertIn("SIMULATED", DEMO_POLICY)
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
                self.assertTrue(options["instructions"].startswith(DEMO_POLICY))
                self.assertIn(environment()["AGENT_INSTRUCTIONS"], options["instructions"])
                self.assertEqual(options["default_options"], {"store": False})
                self.assertEqual(len(options["tools"]), 0 if identifier == "document-analyst" else 2)
        credential.get_token.assert_not_called()


if __name__ == "__main__":
    unittest.main()

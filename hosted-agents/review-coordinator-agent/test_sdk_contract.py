import asyncio
import importlib.util
import json
import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

try:
    import httpx2
    from agent_framework import Agent
    from agent_framework.foundry import FoundryChatClient
    from azure.ai.projects.aio import AIProjectClient
    from azure.core.credentials import AccessToken
    from openai.types.responses import Response
except ImportError:
    SDK_AVAILABLE = False
else:
    SDK_AVAILABLE = True


@unittest.skipUnless(SDK_AVAILABLE, "Install requirements.txt to run the real SDK contract tests")
class SDKContractTests(unittest.TestCase):
    def test_interrupted_smoke_test_attempts_cleanup_and_reraises(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        try:
            from deployment import AgentProfile, deploy
        finally:
            sys.path.pop(0)
        profile = AgentProfile(
            Path(__file__).parent, "coordinator", "description", "instructions", "review",
            environment_variables={
                "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "true",
                "ENABLE_SENSITIVE_DATA": "true",
                "AZURE_TRACING_GEN_AI_CONTENT_RECORDING_ENABLED": "true",
                "APPLICATIONINSIGHTS_AUTH_MODE": "key",
                "APPLICATIONINSIGHTS_STATSBEAT_DISABLED_ALL": "false",
            },
        )
        args = SimpleNamespace(endpoint="https://example.test", agent_name="coordinator",
                               cpu="0.5", memory="1Gi", runtime="python_3_14", model="test",
                               instructions="instructions", poll_seconds=1, max_polls=1,
                               smoke_test_prompt="review")
        with (patch("azure.ai.projects.AIProjectClient") as project,
              patch("azure.identity.DefaultAzureCredential"),
              patch("deployment.wait_until_active"),
              patch("deployment.smoke_test", side_effect=KeyboardInterrupt),
              patch("deployment.cleanup_failed_version") as cleanup):
            client = project.return_value.__enter__.return_value
            client.agents.create_version_from_code.return_value.version = "2"
            original_endpoint = client.agents.get.return_value.agent_endpoint
            with self.assertRaises(KeyboardInterrupt):
                deploy(profile, args)
            cleanup.assert_called_once_with(client, "coordinator", "2", original_endpoint, True)
            definition = client.agents.create_version_from_code.call_args.kwargs["definition"]
            for key in (
                "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT",
                "ENABLE_SENSITIVE_DATA",
                "AZURE_TRACING_GEN_AI_CONTENT_RECORDING_ENABLED",
            ):
                self.assertEqual(definition.environment_variables[key], "false")
            self.assertEqual(definition.environment_variables["APPLICATIONINSIGHTS_AUTH_MODE"], "entra")
            self.assertEqual(
                definition.environment_variables["APPLICATIONINSIGHTS_STATSBEAT_DISABLED_ALL"], "true")

    def test_specialist_preflight_with_real_endpoint_models(self):
        from azure.ai.projects.models import (
            AgentEndpointConfig, FixedRatioVersionSelectionRule,
            ProtocolConfiguration, ResponsesProtocolConfiguration, VersionSelector,
        )
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        try:
            from deployment import AgentProfile, verify_specialist_endpoints
        finally:
            sys.path.pop(0)
        profile = AgentProfile(Path("."), "coordinator", "description", "instructions", "",
                               (("review", "inspect", "specialist"),))
        client = MagicMock()
        client.agents.get.return_value.agent_endpoint = AgentEndpointConfig(
            version_selector=VersionSelector(version_selection_rules=[
                FixedRatioVersionSelectionRule(agent_version="1", traffic_percentage=100),
            ]),
            protocol_configuration=ProtocolConfiguration(responses=ResponsesProtocolConfiguration()),
        )
        client.agents.get_version.return_value = {"status": "active"}
        verify_specialist_endpoints(client, profile, "coordinator")
        client.agents.get_version.assert_called_once_with(agent_name="specialist", agent_version="1")

    def test_failed_preflight_prevents_version_creation(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        try:
            from deployment import AgentProfile, deploy
        finally:
            sys.path.pop(0)
        profile = AgentProfile(Path(__file__).parent, "coordinator", "description", "instructions", "",
                               (("review", "inspect", "missing-specialist"),))
        with patch("azure.ai.projects.AIProjectClient") as project, patch("azure.identity.DefaultAzureCredential"):
            client = project.return_value.__enter__.return_value
            client.agents.get.side_effect = RuntimeError("specialist unavailable")
            args = SimpleNamespace(endpoint="https://example.test", agent_name="coordinator")
            with self.assertRaisesRegex(RuntimeError, "specialist unavailable"):
                deploy(profile, args)
            client.agents.create_version_from_code.assert_not_called()
            client.agents.update_details.assert_not_called()
            client.agents.delete_version.assert_not_called()

    def test_async_specialist_uses_authenticated_named_endpoint(self):
        class Credential:
            async def get_token(self, *scopes, **kwargs):
                return AccessToken("test-only-token", int(time.time()) + 3600)

        async def run_check():
            path = Path(__file__).with_name("main.py")
            spec = importlib.util.spec_from_file_location("coordinator_sdk_contract", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            requests = []

            def respond(request):
                requests.append(request)
                return httpx2.Response(200, json={
                    "id": "resp-test", "object": "response", "created_at": 0,
                    "status": "completed", "model": "test", "output": [{
                        "id": "msg-test", "type": "message", "role": "assistant",
                        "status": "completed", "content": [{
                            "type": "output_text", "text": "grounded finding", "annotations": []
                        }],
                    }],
                })

            original = AIProjectClient.get_openai_client

            def get_client(project, **kwargs):
                return original(project, http_client=httpx2.AsyncClient(
                    transport=httpx2.MockTransport(respond)
                ), **kwargs)

            credential = Credential()
            with patch.object(AIProjectClient, "get_openai_client", get_client):
                result = await module.invoke_specialist(
                    "https://example.services.ai.azure.com/api/projects/test",
                    credential, "application-review-agent", "review", 2,
                )
            self.assertEqual(result, "grounded finding")
            self.assertEqual(len(requests), 1)
            self.assertTrue(requests[0].url.path.endswith(
                "/agents/application-review-agent/endpoint/protocols/openai/responses"
            ))
            self.assertEqual(json.loads(requests[0].content)["store"], False)
            self.assertEqual(requests[0].headers["authorization"], "Bearer test-only-token")
            tools = module.create_specialist_tools("https://example.test", credential)
            client = FoundryChatClient(project_endpoint="https://example.test", model="test",
                                       credential=credential, allow_preview=True)
            agent = Agent(client=client, tools=tools)
            self.assertEqual({tool.name for tool in agent.default_options["tools"]},
                             {"review_application", "review_case"})
            registry = [{"tool": "inspect_stock", "agent": "stock-agent", "description": "Inspect supplied inventory."}]
            with patch.dict(module.os.environ, {"SPECIALIST_CONFIG": json.dumps(registry)}):
                custom_agent = Agent(client=client, tools=module.create_specialist_tools("https://example.test", credential))
            registered = custom_agent.default_options["tools"]
            self.assertEqual([tool.name for tool in registered], ["inspect_stock"])
            self.assertEqual(registered[0].description, "Inspect supplied inventory.")

        asyncio.run(run_check())

    def test_openai_preserves_host_function_output_receipts(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        try:
            from deployment import verify_delegation
        finally:
            sys.path.pop(0)
        response = Response.model_validate({
            "id": "resp-test", "object": "response", "created_at": 0,
            "status": "completed", "model": "test", "parallel_tool_calls": False,
            "tool_choice": "auto", "tools": [], "output": [
                {"id": "fc-test", "type": "function_call", "name": "review_case",
                 "call_id": "call-test", "arguments": "{}", "status": "completed"},
                {"id": "result-test", "type": "function_call_output", "call_id": "call-test", "status": "completed",
                 "output": json.dumps({"status": "succeeded", "agent": "case-review-agent",
                                       "output": "grounded finding"})},
            ],
        })
        verify_delegation(response, "review_case")


if __name__ == "__main__":
    unittest.main()
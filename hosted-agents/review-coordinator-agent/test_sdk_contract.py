import asyncio
import importlib.util
import json
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    import httpx
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
                return httpx.Response(200, json={
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
                return original(project, http_client=httpx.AsyncClient(
                    transport=httpx.MockTransport(respond)
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
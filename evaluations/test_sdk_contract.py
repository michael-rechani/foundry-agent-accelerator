import io
import json
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import run

try:
    import httpx
    from azure.ai.projects import AIProjectClient
    from azure.core.credentials import AccessToken
    from azure.core.pipeline.transport import HttpResponse, HttpTransport
    from openai import APIConnectionError
except ImportError:
    SDK_AVAILABLE = False
else:
    SDK_AVAILABLE = True


@unittest.skipUnless(SDK_AVAILABLE, "Install evaluations/requirements.txt for real SDK contract tests")
class SDKContractTests(unittest.TestCase):
    def project_client(self, respond, status_code=200):
        class Credential:
            def get_token(self, *scopes, **kwargs):
                return AccessToken("test-only", int(time.time()) + 3600)

        class Response(HttpResponse):
            def __init__(self, request):
                super().__init__(request, None)
                self.status_code = status_code
                self.headers = {"content-type": "application/json"}
                self.content_type = "application/json"
                self._body = json.dumps(respond(request)).encode()

            def body(self):
                return self._body

            def json(self):
                return json.loads(self.body())

        class Transport(HttpTransport):
            def open(self):
                pass

            def close(self):
                pass

            def __exit__(self, *args):
                self.close()

            def send(self, request, **kwargs):
                return Response(request)

        return AIProjectClient(
            endpoint="https://example.services.ai.azure.com/api/projects/test",
            credential=Credential(), transport=Transport(), allow_preview=True, retry_total=0,
        )

    def test_evaluator_creation_uses_real_sdk_serialization(self):
        requests = []

        def respond(request):
            requests.append(request)
            return {
                "name": "review-test", "version": "1", "evaluator_type": "custom",
                "categories": ["quality"], "definition": run.RUBRIC,
            }

        with self.project_client(respond, status_code=201) as project:
            evaluator = project.beta.evaluators.create_version(
                name="review-test", evaluator_version={
                    "name": "review-test", "evaluator_type": "custom",
                    "categories": ["quality"], "definition": run.RUBRIC,
                },
            )
        self.assertEqual(evaluator.name, "review-test")
        self.assertEqual(evaluator.definition.pass_threshold, 1.0)
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0].method, "POST")
        self.assertIn("/evaluators/review-test/versions", requests[0].url)
        payload = json.loads(requests[0].body)
        self.assertEqual(payload["definition"], run.RUBRIC)

    def test_real_inventory_deserializes_declared_sdk_fields(self):
        self.exercise_inventory(True)

    def test_missing_real_inventory_metadata_remains_null(self):
        self.exercise_inventory(False)

    def exercise_inventory(self, include_metadata):
        requests = []
        endpoint = "https://example.services.ai.azure.com/api/projects/test"

        def respond(request):
            requests.append(request)
            path = request.url.split("?")[0]
            if path.endswith("/agents/candidate"):
                return {
                    "object": "agent", "id": "agent-test", "name": "candidate", "state": "enabled",
                    "agent_endpoint": {
                        "protocol_configuration": {"responses": {}},
                        "version_selector": {"version_selection_rules": [{
                            "type": "FixedRatio", "agent_version": "1", "traffic_percentage": 100,
                        }]},
                    },
                }
            if path.endswith("/agents/candidate/versions/1"):
                return {
                    "object": "agent.version", "id": "version-test", "name": "candidate", "version": "1",
                    "metadata": {}, "created_at": 0, "status": "active",
                    "definition": {
                        "kind": "hosted", "cpu": "1", "memory": "2Gi",
                        "protocol_versions": [{"protocol": "responses", "version": "2.0.0"}],
                        "environment_variables": {
                            "FOUNDRY_PROJECT_ENDPOINT": endpoint, "FOUNDRY_MODEL_NAME": "model",
                            "AGENT_STORE_RESPONSES": "false", "SECRET": "never-retain-this",
                            **({"AGENT_INSTRUCTIONS": "private-instruction-marker"} if include_metadata else {}),
                        },
                    },
                }
            if path.endswith("/deployments/model"):
                return {
                    "type": "ModelDeployment", "name": "model", "capabilities": {},
                    **({
                        "modelName": "test-model", "modelVersion": "2026-01-01", "modelPublisher": "test",
                    } if include_metadata else {}),
                }
            raise AssertionError(f"Unexpected SDK request: {request.method} {path}")

        with self.project_client(respond) as project:
            identity = run.agent_identity(project, "candidate", "1", endpoint)
        self.assertEqual(len(requests), 3)
        self.assertTrue(all(request.method == "GET" for request in requests))
        self.assertTrue(all(request.url.startswith(endpoint + "/") for request in requests))
        self.assertEqual(identity["version"], "1")
        self.assertEqual(identity["model"], {
            "deployment": "model",
            "model": "test-model" if include_metadata else None,
            "version": "2026-01-01" if include_metadata else None,
            "publisher": "test" if include_metadata else None,
        })
        self.assertEqual(
            identity["prompt_override_sha256"],
            run.digest("private-instruction-marker") if include_metadata else None,
        )
        self.assertNotIn("private-instruction-marker", json.dumps(identity))
        self.assertNotIn("never-retain-this", json.dumps(identity))

    def test_real_evals_serialization_and_paginated_results(self):
        self.exercise_evaluation(False)

    def test_real_evals_failed_case_returns_failed_gate(self):
        self.exercise_evaluation(True)

    def test_missing_native_evaluation_usage_remains_null(self):
        self.exercise_evaluation(False, include_usage=False)

    def exercise_evaluation(self, fail_last, include_usage=True):
        data = run.load_dataset(run.CASES_PATH)
        cases = data["cases"][:3]
        rows = [{"item": {"case_id": case["id"], "query": case["query"], "response": "synthetic"}} for case in cases]
        requests = []
        project = MagicMock()
        project.beta.evaluators.create_version.return_value = SimpleNamespace(name="review-rubric", version="1")
        args = SimpleNamespace(
            sample="application-review-agent", agent_name="candidate", agent_version="1",
            judge_model="judge", source_revision="a" * 40, timeout_seconds=10, poll_seconds=1,
            profile="application-completeness", candidate_label="candidate-b",
            prompt_version="application-v2", conditions_label="staging-idle-v1",
        )

        def respond(request):
            requests.append(request)
            path = request.url.path
            if request.method == "POST" and path.endswith("/evals"):
                return httpx.Response(200, json={"id": "eval-test", "object": "eval"})
            if request.method == "POST" and path.endswith("/runs"):
                return httpx.Response(200, json={"id": "run-test", "object": "eval.run", "status": "queued"})
            if path.endswith("/output_items"):
                second_page = request.url.params.get("after") == "output-1"
                indexes = (1, 2) if second_page else (0,)
                items = [{
                    "id": f"output-{index + 1}", "created_at": 0,
                    "datasource_item": rows[index]["item"], "datasource_item_id": index,
                    "eval_id": "eval-test", "run_id": "run-test", "object": "eval.run.output_item",
                    "status": "fail" if fail_last and index == 2 else "pass",
                    "results": [{
                        "name": run.CRITERION, "passed": not (fail_last and index == 2),
                        "score": 0.0 if fail_last and index == 2 else 1.0, "type": "azure_ai_evaluator",
                    }],
                    "sample": {},
                } for index in indexes]
                return httpx.Response(200, json={
                    "object": "list", "data": items, "has_more": not second_page,
                    "first_id": items[0]["id"], "last_id": items[-1]["id"],
                })
            if path.endswith("/runs/run-test"):
                return httpx.Response(200, json={
                    "id": "run-test", "eval_id": "eval-test", "object": "eval.run", "status": "completed",
                    "result_counts": {"total": 3, "passed": 2 if fail_last else 3, "failed": int(fail_last), "errored": 0},
                    **({"per_model_usage": [{
                        "model_name": "judge-model", "prompt_tokens": 21, "completion_tokens": 9,
                        "total_tokens": 30, "cached_tokens": 0, "invocation_count": 3,
                    }]} if include_usage else {}),
                })
            raise AssertionError(f"Unexpected SDK request: {request.method} {path}")

        class Credential:
            def get_token(self, *scopes, **kwargs):
                return AccessToken("test-only", int(time.time()) + 3600)

        with (
            AIProjectClient("https://example.services.ai.azure.com/api/projects/test", Credential()) as real_project,
            real_project.get_openai_client(http_client=httpx.Client(transport=httpx.MockTransport(respond)), max_retries=0) as client,
            tempfile.TemporaryFile(mode="w+", encoding="utf-8") as receipt,
            patch.object(run, "snapshot", return_value={"stable": True}),
            patch.object(run, "collect_responses", return_value=rows),
            redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(run.evaluate(project, client, args, data, cases, receipt), not fail_last)
            receipt.seek(0)
            records = [json.loads(line) for line in receipt]
        self.assertEqual(records[-1]["event"], "evaluation_completed")
        self.assertEqual(records[-1]["passed"], not fail_last)
        if include_usage:
            self.assertEqual(records[-1]["native_evaluation_usage"][0]["model"], "judge-model")
            self.assertEqual(records[-1]["native_evaluation_usage"][0]["total_tokens"], 30)
        else:
            self.assertIsNone(records[-1]["native_evaluation_usage"])
        self.assertEqual(records[-1]["native_results"][cases[-1]["id"]]["score"], 0.0 if fail_last else 1.0)
        self.assertEqual(len(requests), 5)
        payload = json.loads(requests[0].content)
        self.assertEqual(payload["testing_criteria"][0]["type"], "azure_ai_evaluator")
        self.assertEqual(payload["testing_criteria"][0]["initialization_parameters"], {"deployment_name": "judge"})
        self.assertEqual(payload["metadata"]["prompt_version"], "application-v2")
        self.assertEqual(payload["metadata"]["profile"], "application-completeness")
        self.assertEqual(payload["metadata"]["selected_cases_sha256"], run.digest(cases))
        self.assertEqual(json.loads(requests[1].content)["data_source"]["source"]["content"], rows)
        self.assertTrue(all(request.url.host == "example.services.ai.azure.com" for request in requests))
        self.assertEqual(requests[-1].url.params["after"], "output-1")
        self.assertNotIn(cases[0]["query"], json.dumps(records))
        project.agents.update_details.assert_not_called()
        project.agents.create_version_from_code.assert_not_called()

    def test_named_client_uses_agent_endpoint_and_store_false(self):
        self.exercise_agent_response(True)

    def test_missing_sdk_usage_remains_null_in_receipt(self):
        self.exercise_agent_response(False)

    def exercise_agent_response(self, include_usage):
        requests = []

        class Credential:
            def get_token(self, *scopes, **kwargs):
                return AccessToken("test-only", int(time.time()) + 3600)

        def respond(request):
            requests.append(request)
            return httpx.Response(200, headers={"x-request-id": "request-test"} if include_usage else {}, json={
                "id": "response-test", "object": "response", "created_at": 0,
                "status": "completed", "model": "test", "output": [{
                    "id": "message-test", "type": "message", "role": "assistant",
                    "status": "completed", "content": [{
                        "type": "output_text", "text": "Synthetic answer.", "annotations": [],
                    }],
                }],
                **({"usage": {"input_tokens": 10, "output_tokens": 4, "total_tokens": 14}} if include_usage else {}),
            })

        original = AIProjectClient.get_openai_client

        def get_client(project, **kwargs):
            return original(project, http_client=httpx.Client(transport=httpx.MockTransport(respond)), **kwargs)

        with (
            AIProjectClient("https://example.services.ai.azure.com/api/projects/test", Credential(), allow_preview=True) as project,
            patch.object(AIProjectClient, "get_openai_client", get_client),
            patch.object(run, "snapshot", return_value={}),
            tempfile.TemporaryFile(mode="w+", encoding="utf-8") as receipt,
            redirect_stdout(io.StringIO()),
        ):
            case = run.load_dataset(run.CASES_PATH)["cases"][0]
            run.collect_responses(project, SimpleNamespace(agent_name="candidate"), [case], {}, receipt)
            receipt.seek(0)
            telemetry = json.loads(receipt.readline())
        self.assertEqual(len(requests), 1)
        self.assertTrue(requests[0].url.path.endswith("/agents/candidate/endpoint/protocols/openai/responses"))
        self.assertEqual(json.loads(requests[0].content), {"input": case["query"], "store": False, "stream": False})
        self.assertEqual(telemetry["response_id"], "response-test")
        self.assertEqual(telemetry["request_id"], "request-test" if include_usage else None)
        self.assertEqual(telemetry["token_usage"]["total_tokens"], 14 if include_usage else None)
        self.assertIsNone(telemetry["estimated_cost"])

    def test_missing_approval_prevents_any_azure_client_creation_or_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "receipt.jsonl"
            for flag in ("--approve-billable-run", "--authorize-content-capture"):
                argv = self.arguments(output)
                argv.remove(flag)
                with (
                    patch("azure.ai.projects.AIProjectClient") as project,
                    patch("azure.identity.DefaultAzureCredential") as credential,
                    redirect_stderr(io.StringIO()), self.assertRaises(SystemExit),
                ):
                    run.main(argv)
                project.assert_not_called()
                credential.assert_not_called()
                self.assertFalse(output.exists())

    def test_existing_report_prevents_any_azure_client_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "receipt.jsonl"
            output.write_text("existing", encoding="utf-8")
            with patch("azure.ai.projects.AIProjectClient") as project, self.assertRaises(FileExistsError):
                run.main(self.arguments(output))
            project.assert_not_called()
            self.assertEqual(output.read_text(encoding="utf-8"), "existing")

    def test_sdk_failure_records_only_error_type_and_retains_prior_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "receipt.jsonl"

            def fail(project, client, args, data, cases, receipt):
                run.emit(receipt, "run_created", eval_id="eval-test", run_id="run-test")
                raise APIConnectionError(message="sensitive-service-body", request=httpx.Request("POST", "https://example.test"))

            with (
                patch("azure.ai.projects.AIProjectClient"),
                patch("azure.identity.DefaultAzureCredential"),
                patch.object(run, "evaluate", side_effect=fail),
                redirect_stdout(io.StringIO()) as console,
                self.assertRaisesRegex(RuntimeError, "Azure evaluation request failed"),
            ):
                run.main(self.arguments(output))
            text = output.read_text(encoding="utf-8")
            self.assertNotIn("sensitive-service-body", text + console.getvalue())
            self.assertIn("run-test", text)
            self.assertEqual(json.loads(text.splitlines()[-1])["event"], "failed")
            started = json.loads(text.splitlines()[0])
            self.assertIsNone(started["prompt_version_attested"])
            self.assertIsNone(started["candidate_label"])
            self.assertIsNone(started["conditions_label_attested"])
            self.assertEqual(started["approvals"], {"billable_run": True, "evaluation_content_capture": True})
            self.assertEqual(started["run_conditions"]["client_retries"], 0)
            self.assertIsNone(started["run_conditions"]["server_load"])

    def arguments(self, output):
        return [
            "--run", "--approve-billable-run", "--authorize-content-capture",
            "--sample", "application-review-agent",
            "--endpoint", "https://example.services.ai.azure.com/api/projects/test",
            "--agent-name", "candidate", "--agent-version", "1", "--judge-model", "judge",
            "--source-revision", "a" * 40, "--output", str(output),
        ]


if __name__ == "__main__":
    unittest.main()

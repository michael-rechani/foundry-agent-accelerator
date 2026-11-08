import hashlib
import importlib.util
import io
import json
import runpy
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import deployment
import test_deployment_sdk as sdk_fixture


class CustomerProfilePromotionIntegrationTests(unittest.TestCase):
    ROUTER_LABEL = "fictional-router-label"
    SESSION_ID = "fictional-customer-profile-session"
    CLIENT_ID = "12345678-1234-1234-1234-123456789abc"

    def setUp(self):
        self.assertTrue(sdk_fixture.SDK_AVAILABLE, "Synthetic integration requires requirements-deploy.txt")
        real_smoke = deployment.smoke_test
        real_candidate_smoke = deployment.candidate_smoke_test
        self.fixture = sdk_fixture.DeploymentSDKTests(
            methodName="test_pins_archive_integrity_preserves_authorization_and_reads_final_route")
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.default_credential = self.enterContext(patch("azure.identity.DefaultAzureCredential"))
        self.credential_environment = self.enterContext(patch.dict("os.environ", {
            "AZURE_TOKEN_CREDENTIALS": "ManagedIdentityCredential", "AZURE_CLIENT_ID": self.CLIENT_ID,
        }))
        self.managed_credential = self.enterContext(patch("azure.identity.ManagedIdentityCredential"))
        self.workload_credential = self.enterContext(patch("azure.identity.WorkloadIdentityCredential"))
        # Restore decision logic patched by the reusable SDK fixture; only external clients stay mocked.
        self.enterContext(patch("deployment.smoke_test", new=real_smoke))
        self.enterContext(patch("deployment.candidate_smoke_test", new=real_candidate_smoke))

        self.source = Path(__file__).parent / "review-coordinator-agent" / "deploy.py"
        self.example = self.source.parent / "profiles" / "evidence-review.example.json"
        self.digest = hashlib.sha256(self.example.read_bytes()).hexdigest()
        self.enterContext(patch.object(sys, "path", [str(self.source.parent), *sys.path]))
        spec = importlib.util.spec_from_file_location("integration_customer_profile", self.source)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.profile = module.profile_from_file(self.example, self.digest)
        from configuration import validate_specialists
        self.validate_specialists = validate_specialists
        self.registry = json.loads(dict(self.profile.environment_variables)["SPECIALIST_CONFIG"])
        self.fixture.profile = self.profile
        self.fixture.args = deployment.parse_args(self.profile, [
            "--endpoint", self.fixture.args.endpoint, "--model", self.ROUTER_LABEL,
            "--poll-seconds", "1", "--max-polls", "1",
        ])
        self.client = self.fixture.client
        self.specialist_routes = {item["agent"]: self.fixture.route("1") for item in self.registry}
        self.specialist_states = {name: "enabled" for name in self.specialist_routes}
        self.checks_by_prompt = {check[0]: check[1:] for check in self.profile.delegation_checks}
        self.timeline = []
        self.responses = []
        self.created = None
        self.client.agents.get.side_effect = self.get_agent
        self.client.agents.get_version.side_effect = self.get_version
        self.client.agents.create_version_from_code.side_effect = self.create_version
        self.client.agents.update_details.side_effect = self.update_route
        self.client.agents.create_session.side_effect = self.create_session
        self.client.get_openai_client.return_value.__enter__.return_value.responses.create.side_effect = self.respond

    def get_agent(self, *, agent_name):
        self.timeline.append(("get", agent_name))
        if agent_name == self.profile.name:
            return self.fixture.get(agent_name=agent_name)
        self.assertIn(agent_name, self.specialist_routes)
        return sdk_fixture.AgentDetails({
            "name": agent_name, "state": "enabled",
            "configuration_state": self.specialist_states[agent_name],
            "agent_endpoint": self.specialist_routes[agent_name].as_dict(),
        })

    def get_version(self, *, agent_name, agent_version):
        self.timeline.append(("version", agent_name, agent_version))
        return self.fixture.read_version(agent_name=agent_name, agent_version=agent_version)

    def create_version(self, **kwargs):
        self.timeline.append(("create", kwargs["agent_name"]))
        self.created = self.fixture.create(**kwargs)
        return self.created

    def update_route(self, **kwargs):
        self.timeline.append(("update", kwargs["agent_name"]))
        return self.fixture.update(**kwargs)

    def create_session(self, *, agent_name, version_indicator):
        self.assertEqual(agent_name, self.profile.name)
        self.assertEqual(version_indicator.agent_version, self.created.version)
        self.assertEqual(self.fixture.endpoint, self.fixture.original)
        self.timeline.append(("candidate-session", agent_name, version_indicator.agent_version))
        return SimpleNamespace(
            agent_session_id=self.SESSION_ID, status="active", version_indicator=version_indicator)

    def respond(self, **kwargs):
        self.assertFalse(kwargs["store"])
        tool, agent = self.checks_by_prompt[kwargs["input"]]
        candidate = "extra_body" in kwargs
        if candidate:
            self.assertEqual(kwargs["extra_body"], {"agent_session_id": self.SESSION_ID})
            self.assertEqual(self.fixture.endpoint, self.fixture.original)
        else:
            self.assertTrue(deployment.routes_to_version(self.fixture.endpoint, self.created.version))
        self.responses.append((kwargs["input"], candidate))
        self.timeline.append(("response", tool, candidate))
        call_id = f"fictional-call-{len(self.responses)}"
        return self.fixture.reply([
            {"type": "function_call", "name": tool, "call_id": call_id},
            {"type": "function_call_output", "call_id": call_id, "output": json.dumps({
                "status": "succeeded", "agent": agent, "output": "Fictional evidence-only finding.",
            })},
        ])

    def run_profile(self, path=None, mode="ManagedIdentityCredential"):
        path = self.example if path is None else path
        digest = self.digest if path == self.example else hashlib.sha256(path.read_bytes()).hexdigest()
        argv = [
            str(self.source), "--profile", str(path), "--profile-sha256", digest,
            "--endpoint", self.fixture.args.endpoint, "--model", self.ROUTER_LABEL,
            "--credential-mode", mode, "--credential-client-id", self.CLIENT_ID,
            "--poll-seconds", "1", "--max-polls", "1",
        ]
        with patch.object(sys, "argv", argv):
            runpy.run_path(str(self.source), run_name="__main__")

    def test_customer_profile_runtime_registry_and_version_pinned_promotion(self):
        self.assertEqual(self.profile.name, "customer-review-coordinator")
        self.assertEqual({(item["tool"], item["agent"]) for item in self.registry}, {
            ("inspect_application", "application-review-agent"),
            ("inspect_case", "case-review-agent"),
        })
        self.assertEqual(self.validate_specialists(deepcopy(self.registry)), self.registry)
        self.assertEqual([check[1] for check in self.profile.delegation_checks],
                         ["inspect_application", "inspect_case", "inspect_case"])
        with redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as result:
            self.run_profile()
        self.assertEqual(result.exception.code, 0)

        create = self.client.agents.create_version_from_code.call_args.kwargs
        self.assertEqual(create["agent_name"], self.profile.name)
        environment = create["definition"].environment_variables
        self.assertEqual(environment["FOUNDRY_MODEL_NAME"], self.ROUTER_LABEL)
        self.assertEqual(environment["AGENT_NAME"], self.profile.name)
        self.assertEqual(environment["SPECIALIST_CONFIG"],
                         dict(self.profile.environment_variables)["SPECIALIST_CONFIG"])
        self.assertEqual(self.validate_specialists(json.loads(environment["SPECIALIST_CONFIG"])), self.registry)
        self.client.deployments.get.assert_called_once_with(name=self.ROUTER_LABEL)
        for name in self.specialist_routes:
            self.assertLess(self.timeline.index(("version", name, "1")),
                            self.timeline.index(("create", self.profile.name)))
        session = self.client.agents.create_session.call_args.kwargs
        self.assertEqual(session["agent_name"], self.profile.name)
        self.assertEqual(session["version_indicator"].as_dict(),
                         {"type": "version_ref", "agent_version": self.created.version})
        self.assertLess(self.timeline.index(("candidate-session", self.profile.name, self.created.version)),
                        self.timeline.index(("update", self.profile.name)))
        required_prompts = [check[0] for check in self.profile.delegation_checks]
        self.assertEqual([prompt for prompt, candidate in self.responses if candidate], required_prompts)
        self.assertEqual([prompt for prompt, candidate in self.responses if not candidate], required_prompts)
        self.client.agents.delete_session.assert_called_once_with(
            agent_name=self.profile.name, session_id=self.SESSION_ID)
        self.client.agents.update_details.assert_called_once()
        self.assertTrue(deployment.routes_to_version(self.fixture.endpoint, self.created.version))
        self.assertEqual(self.fixture.endpoint.version_selector.version_selection_rules[0].traffic_percentage, 100)
        self.client.agents.delete_version.assert_not_called()
        self.client.agents.enable.assert_not_called()
        self.managed_credential.assert_called_once_with(client_id=self.CLIENT_ID)
        self.workload_credential.assert_not_called()
        self.default_credential.assert_not_called()

    def test_workload_flow_uses_only_selected_class_during_actual_deployment(self):
        import os
        os.environ["AZURE_TOKEN_CREDENTIALS"] = "WorkloadIdentityCredential"
        with redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as result:
            self.run_profile(mode="WorkloadIdentityCredential")
        self.assertEqual(result.exception.code, 0)
        self.workload_credential.assert_called_once_with(client_id=self.CLIENT_ID)
        self.managed_credential.assert_not_called()
        self.default_credential.assert_not_called()
        self.assertTrue(deployment.routes_to_version(self.fixture.endpoint, self.created.version))
        self.assertEqual(self.client.agents.create_version_from_code.call_args.kwargs[
            "definition"].environment_variables["FOUNDRY_MODEL_NAME"], self.ROUTER_LABEL)

    def test_disabled_specialist_stops_before_version_creation_or_route_update(self):
        self.specialist_states["case-review-agent"] = "disabled"
        with redirect_stdout(io.StringIO()), self.assertRaisesRegex(RuntimeError, "explicitly enabled"):
            self.run_profile()
        self.client.agents.create_version_from_code.assert_not_called()
        self.client.agents.update_details.assert_not_called()
        self.client.agents.create_session.assert_not_called()
        self.client.get_openai_client.assert_not_called()
        self.assertEqual(self.fixture.endpoint, self.fixture.original)

    def test_invalid_byte_bound_profile_stops_before_external_client_or_mutations(self):
        invalid = json.loads(self.example.read_text(encoding="utf-8"))
        invalid["specialists"][0]["agent"] = "7"
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "fictional-invalid-profile.json"
            path.write_text(json.dumps(invalid), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "numeric-leading specialist endpoint names"):
                self.run_profile(path)
        self.fixture.project.assert_not_called()
        self.client.agents.create_version_from_code.assert_not_called()
        self.client.agents.update_details.assert_not_called()
        self.assertEqual(self.fixture.endpoint, self.fixture.original)


if __name__ == "__main__":
    unittest.main()

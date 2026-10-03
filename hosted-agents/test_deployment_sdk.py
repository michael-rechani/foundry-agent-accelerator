import hashlib
import io
import time
import unittest
from contextlib import redirect_stdout
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from deployment import AgentProfile, create_package, deploy

try:
    import requests
    from azure.ai.projects.models import (
        AgentEndpointConfig, AgentIdentity, EntraAuthorizationScheme, FixedRatioVersionSelectionRule, McpProtocolConfiguration,
        ProtocolConfiguration, ResponsesProtocolConfiguration, VersionSelector,
    )
    from azure.core.credentials import AccessToken
    from azure.core.exceptions import AzureError, ResourceNotFoundError
except ImportError:
    SDK_AVAILABLE = False
else:
    SDK_AVAILABLE = True


@unittest.skipUnless(SDK_AVAILABLE, "Install requirements-deploy.txt for the real deployment SDK models")
class DeploymentSDKTests(unittest.TestCase):
    def setUp(self):
        self.profile = AgentProfile(
            Path(__file__).parent / "case-review-agent", "case-review-agent",
            "Fictional review", "Review supplied fictional evidence.", "Review a fictional case.",
        )
        self.args = SimpleNamespace(
            endpoint="https://fictional.services.ai.azure.com/api/projects/demo",
            model="model", agent_name=self.profile.name, cpu="0.5", memory="1Gi",
            runtime="python_3_14", instructions=self.profile.instructions,
            smoke_test_prompt=self.profile.smoke_test_prompt, poll_seconds=1, max_polls=1,
        )
        project = self.enterContext(patch("azure.ai.projects.AIProjectClient"))
        self.project = project
        self.enterContext(patch("azure.identity.DefaultAzureCredential"))
        self.smoke = self.enterContext(patch("deployment.smoke_test"))
        self.client = project.return_value.__enter__.return_value
        self.endpoint = self.route("1")
        self.original = deepcopy(self.endpoint)
        self.events = []
        self.missing = False
        self.identity = None
        self.client.agents.get.side_effect = self.get
        self.client.agents.create_version_from_code.side_effect = self.create
        self.client.agents.update_details.side_effect = self.update
        self.client.agents.get_version.return_value = {"status": "active"}

    def route(self, version):
        return AgentEndpointConfig(
            version_selector=VersionSelector(version_selection_rules=[
                FixedRatioVersionSelectionRule(agent_version=version, traffic_percentage=100),
            ]),
            protocol_configuration=ProtocolConfiguration(
                responses=ResponsesProtocolConfiguration(), mcp=McpProtocolConfiguration(),
            ),
            authorization_schemes=[EntraAuthorizationScheme()],
        )

    def get(self, **kwargs):
        self.events.append("read")
        if self.missing:
            raise ResourceNotFoundError()
        return SimpleNamespace(agent_endpoint=deepcopy(self.endpoint))

    def create(self, **kwargs):
        self.events.append("create")
        self.uploaded = kwargs["code"].read()
        if self.missing:
            self.endpoint = self.route("@latest")
            self.missing = False
        return SimpleNamespace(version="2", instance_identity=self.identity)

    def update(self, **kwargs):
        self.events.append("update")
        self.endpoint = deepcopy(kwargs["agent_endpoint"])

    def test_pins_archive_integrity_preserves_authorization_and_reads_final_route(self):
        deploy(self.profile, self.args)
        self.assertLess(self.events.index("read"), self.events.index("create"))
        self.assertEqual(self.events[-1], "read")
        self.assertEqual(self.endpoint.authorization_schemes, self.original.authorization_schemes)
        self.assertEqual(self.endpoint.protocol_configuration.mcp, self.original.protocol_configuration.mcp)
        self.assertEqual(self.endpoint.version_selector.version_selection_rules[0].agent_version, "2")
        uploaded = self.client.agents.create_version_from_code.call_args.kwargs
        self.assertEqual(uploaded["code_zip_sha256"], hashlib.sha256(self.uploaded).hexdigest())
        self.assertEqual(uploaded["metadata"]["source_sha256"], uploaded["code_zip_sha256"])
        self.client.deployments.get.assert_called_once_with(name="model")
        self.client.agents.delete_version.assert_not_called()

    def test_foundry_client_sets_explicit_timeouts_and_no_retries(self):
        deploy(self.profile, self.args)
        self.project.assert_called_once()
        options = dict(self.project.call_args.kwargs)
        self.assertEqual(options.pop("endpoint"), self.args.endpoint)
        options.pop("credential")
        self.assertEqual(options, {
            "allow_preview": True, "retry_total": 0, "connection_timeout": 30, "read_timeout": 60,
        })

    def test_first_deployment_pins_default_latest_route(self):
        self.missing = True
        deploy(self.profile, self.args)
        self.assertEqual(self.endpoint.version_selector.version_selection_rules[0].agent_version, "2")
        self.assertEqual(len(self.endpoint.authorization_schemes), 1)

    def test_symbolic_existing_route_is_rejected_before_creating_version(self):
        self.endpoint = self.route("@latest")
        with self.assertRaisesRegex(RuntimeError, "Pin the existing"):
            deploy(self.profile, self.args)
        self.client.agents.create_version_from_code.assert_not_called()
        self.client.agents.update_details.assert_not_called()

    def test_model_preflight_failure_never_uploads(self):
        self.client.deployments.get.side_effect = ResourceNotFoundError()
        with self.assertRaises(ResourceNotFoundError):
            deploy(self.profile, self.args)
        self.client.agents.create_version_from_code.assert_not_called()

    def test_inventory_failure_is_not_treated_as_a_missing_agent(self):
        self.client.agents.get.side_effect = RuntimeError("inventory unavailable")
        with self.assertRaisesRegex(RuntimeError, "inventory unavailable"):
            deploy(self.profile, self.args)
        self.client.agents.create_version_from_code.assert_not_called()

    def test_failed_or_interrupted_smoke_restores_exact_endpoint_before_deletion(self):
        for error in (RuntimeError("smoke failed"), KeyboardInterrupt()):
            with self.subTest(error=type(error).__name__):
                self.endpoint = deepcopy(self.original)
                self.client.agents.delete_version.reset_mock()
                self.smoke.side_effect = error
                with self.assertRaises(type(error)):
                    deploy(self.profile, self.args)
                self.assertEqual(self.endpoint, self.original)
                self.client.agents.delete_version.assert_called_once_with(
                    agent_name=self.profile.name, agent_version="2", force=True,
                )

    def test_failed_first_deployment_retains_candidate_without_recovery_target(self):
        self.missing = True
        self.smoke.side_effect = RuntimeError("smoke failed")
        with self.assertRaises(RuntimeError):
            deploy(self.profile, self.args)
        self.client.agents.delete_version.assert_not_called()

    def test_changed_route_before_promotion_is_not_overwritten(self):
        def creating(**kwargs):
            result = self.create(**kwargs)
            self.endpoint = self.route("3")
            return result

        self.client.agents.create_version_from_code.side_effect = creating
        with self.assertRaisesRegex(RuntimeError, "changed during deployment"):
            deploy(self.profile, self.args)
        self.client.agents.update_details.assert_not_called()
        self.assertEqual(self.endpoint.version_selector.version_selection_rules[0].agent_version, "3")

    def test_route_readback_failure_does_not_claim_success(self):
        def ignored_update(**kwargs):
            self.events.append("ignored-update")

        self.client.agents.update_details.side_effect = ignored_update
        with self.assertRaisesRegex(RuntimeError, "route was not confirmed"):
            deploy(self.profile, self.args)
        self.smoke.assert_not_called()

    def test_final_route_readback_is_not_replaced_by_successful_smoke(self):
        self.smoke.side_effect = lambda *args: setattr(self, "endpoint", self.route("@latest"))
        with self.assertRaisesRegex(RuntimeError, "route was not confirmed"):
            deploy(self.profile, self.args)

    def test_reports_agent_identity_principal_for_role_assignments(self):
        self.identity = AgentIdentity(principal_id="11111111-2222-3333-4444-555555555555", client_id="client")
        output = io.StringIO()
        with redirect_stdout(output):
            deploy(self.profile, self.args)
        self.assertIn("Agent identity principal ID: 11111111-2222-3333-4444-555555555555", output.getvalue())
        self.assertNotIn("client", output.getvalue())

    def test_missing_agent_identity_is_reported_without_failing(self):
        output = io.StringIO()
        with redirect_stdout(output):
            deploy(self.profile, self.args)
        self.assertIn("No agent instance identity was reported", output.getvalue())
        self.assertNotIn("principal ID:", output.getvalue())

    def test_portable_archive_is_uploaded_without_repackaging_local_source(self):
        package = io.BytesIO()
        create_package(self.profile.source_directory, package)
        profile = AgentProfile(
            Path("not-present"), "exported", "Exported sample", "Review supplied evidence.", "",
            code_archive=package.getvalue(),
        )
        deploy(profile, self.args)
        self.assertEqual(self.uploaded, package.getvalue())


@unittest.skipUnless(SDK_AVAILABLE, "Install requirements-deploy.txt for the real deployment SDK")
class DeploymentTimeoutTests(unittest.TestCase):
    class Credential:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def get_token(self, *scopes, **kwargs):
            return AccessToken("test-only", int(time.time()) + 3600)

    def deploy_against_failing_transport(self, error):
        attempts = []

        def failing(adapter, request, stream=False, timeout=None, **kwargs):
            attempts.append(timeout)
            raise error(request=request)

        profile = AgentProfile(
            Path(__file__).parent / "case-review-agent", "case-review-agent",
            "Fictional review", "Review supplied fictional evidence.", "",
        )
        args = SimpleNamespace(
            endpoint="https://fictional.services.ai.azure.com/api/projects/demo",
            model="model", agent_name=profile.name, cpu="0.5", memory="1Gi",
            runtime="python_3_14", instructions=profile.instructions,
            smoke_test_prompt="", poll_seconds=1, max_polls=1,
        )
        with (
            patch("azure.identity.DefaultAzureCredential", self.Credential),
            patch("time.sleep"),
            patch.object(requests.adapters.HTTPAdapter, "send", failing),
            self.assertRaises(AzureError),
        ):
            deploy(profile, args)
        return attempts

    def test_a_stalled_foundry_call_fails_once_on_the_clients_own_deadline(self):
        attempts = self.deploy_against_failing_transport(requests.exceptions.ReadTimeout)
        self.assertEqual(attempts, [(30, 60)])

    def test_a_failed_foundry_connection_is_not_retried(self):
        attempts = self.deploy_against_failing_transport(requests.exceptions.ConnectionError)
        self.assertEqual(attempts, [(30, 60)])


if __name__ == "__main__":
    unittest.main()

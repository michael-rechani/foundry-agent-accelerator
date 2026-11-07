import hashlib
import io
import json
import time
import unittest
from contextlib import redirect_stdout
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from deployment import (
    KNOWLEDGE_CHECK_PROMPT, AgentProfile, active_release, candidate_model_matches, create_package, deploy,
    enabled_endpoint, recovery_endpoint, smoke_test as real_smoke_test,
)

try:
    import requests
    from azure.ai.projects import AIProjectClient
    from azure.ai.projects.models import (
        AgentDetails, AgentEndpointConfig, AgentIdentity, AgentVersionDetails, EntraAuthorizationScheme,
        FixedRatioVersionSelectionRule, McpProtocolConfiguration, ProtocolConfiguration,
        ResponsesProtocolConfiguration, VersionSelector,
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
        self.candidate = self.enterContext(patch("deployment.candidate_smoke_test"))
        self.client = project.return_value.__enter__.return_value
        self.endpoint = self.route("1")
        self.original = deepcopy(self.endpoint)
        self.events = []
        self.missing = False
        self.state = "enabled"
        self.configuration_state = "enabled"
        self.identity = None
        self.client.agents.get.side_effect = self.get
        self.client.agents.create_version_from_code.side_effect = self.create
        self.client.agents.update_details.side_effect = self.update
        self.client.agents.get_version.side_effect = self.read_version

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
        endpoint = self.endpoint.as_dict() if self.endpoint is not None else None
        return AgentDetails({
            "name": kwargs["agent_name"], "state": self.state,
            "configuration_state": self.configuration_state, "agent_endpoint": endpoint,
        })

    def read_version(self, *, agent_name, agent_version):
        model = "previous-model" if agent_version == "1" else self.args.model
        return AgentVersionDetails({
            "name": agent_name, "version": agent_version, "status": "active",
            "definition": {"kind": "hosted", "cpu": "0.5", "memory": "1Gi",
                           "environment_variables": {"FOUNDRY_MODEL_NAME": model}},
        })

    def create(self, **kwargs):
        self.events.append("create")
        self.uploaded = kwargs["code"].read()
        if self.missing:
            self.endpoint = self.route("@latest")
            self.missing = False
        self.state = "enabled"
        self.configuration_state = "enabled"
        return SimpleNamespace(version="2", instance_identity=self.identity)

    @staticmethod
    def merge_patch(current, patch):
        if not isinstance(patch, dict):
            return deepcopy(patch)
        result = deepcopy(current) if isinstance(current, dict) else {}
        for key, value in patch.items():
            if value is None:
                result.pop(key, None)
            else:
                result[key] = DeploymentSDKTests.merge_patch(result.get(key), value)
        return result

    def update(self, **kwargs):
        self.events.append("update")
        current = self.endpoint.as_dict() if self.endpoint is not None else {}
        patch = kwargs["agent_endpoint"].as_dict(exclude_readonly=True)
        self.endpoint = AgentEndpointConfig(self.merge_patch(current, patch))

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

    def test_missing_wire_state_fields_fail_closed_before_creation(self):
        for field in ("state", "configuration_state"):
            with self.subTest(field=field):
                def missing(field=field, **kwargs):
                    details = self.get(**kwargs)
                    del details[field]
                    return details

                self.client.agents.get.side_effect = missing
                with self.assertRaisesRegex(RuntimeError, "explicitly enabled"):
                    deploy(self.profile, self.args)
                self.assert_no_agent_mutations()
                self.client.agents.enable.assert_not_called()

    def test_route_or_state_change_during_recovery_snapshot_prevents_creation(self):
        for change in ("route", "state", "configuration_state"):
            with self.subTest(change=change):
                self.endpoint = deepcopy(self.original)
                self.state = self.configuration_state = "enabled"

                def changed(*, agent_name, agent_version, change=change):
                    details = self.read_version(agent_name=agent_name, agent_version=agent_version)
                    if change == "route":
                        self.endpoint = self.route("3")
                    else:
                        setattr(self, change, "disabled")
                    return details

                self.client.agents.get_version.side_effect = changed
                expected = "recovery route changed" if change == "route" else "explicitly enabled"
                with self.assertRaisesRegex(RuntimeError, expected):
                    deploy(self.profile, self.args)
                self.assert_no_agent_mutations()
                self.client.agents.enable.assert_not_called()

    def test_recovery_version_identity_mismatch_prevents_creation(self):
        def wrong(*, agent_name, agent_version):
            return AgentVersionDetails({"name": "other", "version": agent_version, "status": "active"})

        self.client.agents.get_version.side_effect = wrong
        with self.assertRaisesRegex(RuntimeError, "not an active release"):
            deploy(self.profile, self.args)
        self.assert_no_agent_mutations()
        self.client.agents.enable.assert_not_called()

    def test_polled_candidate_identity_mismatch_prevents_smoke_and_promotion(self):
        def wrong(*, agent_name, agent_version):
            if agent_version == "2":
                return AgentVersionDetails({"name": agent_name, "version": "3", "status": "active"})
            return self.read_version(agent_name=agent_name, agent_version=agent_version)

        self.client.agents.get_version.side_effect = wrong
        with self.assertRaisesRegex(RuntimeError, "version identity was not confirmed"):
            deploy(self.profile, self.args)
        self.client.agents.create_version_from_code.assert_called_once()
        self.candidate.assert_not_called()
        self.client.agents.update_details.assert_not_called()
        self.client.agents.delete_version.assert_not_called()
        self.client.agents.enable.assert_not_called()

    def test_state_or_route_flip_before_candidate_smoke_never_invokes_candidate(self):
        for change in ("state", "configuration_state", "route"):
            with self.subTest(change=change):
                self.endpoint = deepcopy(self.original)
                self.state = self.configuration_state = "enabled"
                self.client.agents.create_version_from_code.reset_mock()
                self.candidate.reset_mock()

                def changed(*, agent_name, agent_version, change=change):
                    details = self.read_version(agent_name=agent_name, agent_version=agent_version)
                    if agent_version == "2":
                        if change == "route":
                            self.endpoint = self.route("3")
                        else:
                            setattr(self, change, "disabled")
                    return details

                self.client.agents.get_version.side_effect = changed
                expected = "changed during deployment" if change == "route" else "explicitly enabled"
                with self.assertRaisesRegex(RuntimeError, expected):
                    deploy(self.profile, self.args)
                self.client.agents.create_version_from_code.assert_called_once()
                self.candidate.assert_not_called()
                self.client.agents.create_session.assert_not_called()
                self.client.agents.update_details.assert_not_called()
                self.client.agents.delete_version.assert_not_called()
                self.client.agents.enable.assert_not_called()

    def test_candidate_identity_change_after_smoke_prevents_promotion(self):
        def checked(*args, **kwargs):
            def wrong(*, agent_name, agent_version):
                name = "other" if agent_version == "2" else agent_name
                return AgentVersionDetails({"name": name, "version": agent_version, "status": "active"})

            self.client.agents.get_version.side_effect = wrong

        self.candidate.side_effect = checked
        with self.assertRaisesRegex(RuntimeError, "candidate agent version is not active"):
            deploy(self.profile, self.args)
        self.client.agents.update_details.assert_not_called()
        self.client.agents.delete_version.assert_not_called()
        self.client.agents.enable.assert_not_called()

    def test_promoted_identity_mismatch_uses_guarded_rollback(self):
        def wrong_after_update(**kwargs):
            self.update(**kwargs)

            def wrong(*, agent_name, agent_version):
                version = "3" if agent_version == "2" else agent_version
                return AgentVersionDetails({"name": agent_name, "version": version, "status": "active"})

            self.client.agents.get_version.side_effect = wrong

        self.client.agents.update_details.side_effect = wrong_after_update
        with self.assertRaisesRegex(RuntimeError, "promoted agent version is not active"):
            deploy(self.profile, self.args)
        self.assertEqual(self.endpoint, self.original)
        self.assertEqual(self.client.agents.update_details.call_count, 2)
        self.smoke.assert_not_called()
        self.client.agents.delete_version.assert_not_called()
        self.client.agents.enable.assert_not_called()

    def test_recovery_identity_mismatch_after_promotion_does_not_restore(self):
        def fail_smoke(*args):
            def wrong(*, agent_name, agent_version):
                name = "other" if agent_version == "1" else agent_name
                return AgentVersionDetails({"name": name, "version": agent_version, "status": "active"})

            self.client.agents.get_version.side_effect = wrong
            raise RuntimeError("fictional smoke failed")

        self.smoke.side_effect = fail_smoke
        with redirect_stdout(io.StringIO()) as output:
            with self.assertRaisesRegex(RuntimeError, "fictional smoke failed"):
                deploy(self.profile, self.args)
        self.assertEqual(self.client.agents.update_details.call_count, 1)
        self.assertIn("manual recovery required", output.getvalue())
        self.assertNotIn("other", output.getvalue())
        self.client.agents.delete_version.assert_not_called()
        self.client.agents.enable.assert_not_called()

    def test_administrative_state_flip_before_promotion_never_updates_route(self):
        self.candidate.side_effect = lambda *args, **kwargs: setattr(self, "configuration_state", "disabled")
        with self.assertRaisesRegex(RuntimeError, "explicitly enabled"):
            deploy(self.profile, self.args)
        self.client.agents.update_details.assert_not_called()
        self.client.agents.delete_version.assert_not_called()
        self.client.agents.enable.assert_not_called()

    def test_specialist_state_flip_before_promotion_never_updates_route(self):
        profile = AgentProfile(
            self.profile.source_directory, self.profile.name, self.profile.description,
            self.profile.instructions, self.profile.smoke_test_prompt,
            (("fictional prompt", "inspect", "specialist"),),
        )
        state = {"configuration_state": "enabled"}

        def get_with_specialist(**kwargs):
            details = self.get(**kwargs)
            if kwargs["agent_name"] == "specialist":
                details["configuration_state"] = state["configuration_state"]
            return details

        self.client.agents.get.side_effect = get_with_specialist
        self.candidate.side_effect = lambda *args, **kwargs: state.update(configuration_state="disabled")
        with self.assertRaisesRegex(RuntimeError, "explicitly enabled"):
            deploy(profile, self.args)
        self.client.agents.update_details.assert_not_called()
        self.client.agents.delete_version.assert_not_called()
        self.client.agents.enable.assert_not_called()

    def test_administrative_state_flip_after_promotion_blocks_rollback(self):
        for value in ("disabled", None, "unknown", True):
            with self.subTest(value=value):
                self.endpoint = deepcopy(self.original)
                self.state = self.configuration_state = "enabled"
                self.client.agents.update_details.reset_mock()

                def smoke(*args, value=value):
                    self.configuration_state = value
                    raise RuntimeError("fictional smoke failed")

                self.smoke.side_effect = smoke
                with redirect_stdout(io.StringIO()) as output:
                    with self.assertRaisesRegex(RuntimeError, "fictional smoke failed"):
                        deploy(self.profile, self.args)
                self.assertEqual(self.client.agents.update_details.call_count, 1)
                self.assertIn("manual recovery required", output.getvalue())
                self.assertIn("retained version 2", output.getvalue())
                self.client.agents.delete_version.assert_not_called()
                self.client.agents.enable.assert_not_called()

    def test_candidate_model_mismatch_prevents_first_smoke_and_promotion(self):
        for definition in (
            None,
            {"kind": "hosted", "environment_variables": {}},
            {"kind": "hosted", "environment_variables": {"FOUNDRY_MODEL_NAME": "other"}},
            {"kind": "prompt", "environment_variables": {"FOUNDRY_MODEL_NAME": self.args.model}},
        ):
            with self.subTest(definition=definition):
                def wrong(*, agent_name, agent_version, definition=definition):
                    if agent_version == "2":
                        return {"name": agent_name, "version": agent_version, "status": "active",
                                "definition": definition}
                    return self.read_version(agent_name=agent_name, agent_version=agent_version)

                self.client.agents.get_version.side_effect = wrong
                with self.assertRaisesRegex(RuntimeError, "does not confirm the requested model"):
                    deploy(self.profile, self.args)
                self.assertEqual(self.endpoint, self.original)
                self.candidate.assert_not_called()
                self.smoke.assert_not_called()
                self.client.agents.create_session.assert_not_called()
                self.client.agents.update_details.assert_not_called()
                self.client.agents.delete_version.assert_not_called()
                self.client.agents.enable.assert_not_called()

    def test_candidate_model_change_after_smoke_never_promotes(self):
        def checked(*args, **kwargs):
            def wrong(*, agent_name, agent_version):
                details = self.read_version(agent_name=agent_name, agent_version=agent_version)
                if agent_version == "2":
                    details["definition"] = {"kind": "hosted", "environment_variables": {"FOUNDRY_MODEL_NAME": "other"}}
                return details

            self.client.agents.get_version.side_effect = wrong

        self.candidate.side_effect = checked
        with self.assertRaisesRegex(RuntimeError, "does not confirm the requested model"):
            deploy(self.profile, self.args)
        self.client.agents.update_details.assert_not_called()
        self.client.agents.delete_version.assert_not_called()
        self.client.agents.enable.assert_not_called()

    def test_candidate_model_change_after_promotion_uses_guarded_rollback(self):
        def changed(**kwargs):
            self.update(**kwargs)

            def wrong(*, agent_name, agent_version):
                details = self.read_version(agent_name=agent_name, agent_version=agent_version)
                if agent_version == "2":
                    details["definition"] = {"kind": "hosted", "environment_variables": {"FOUNDRY_MODEL_NAME": "other"}}
                return details

            self.client.agents.get_version.side_effect = wrong

        self.client.agents.update_details.side_effect = changed
        with self.assertRaisesRegex(RuntimeError, "promoted hosted definition does not confirm"):
            deploy(self.profile, self.args)
        self.assertEqual(self.endpoint, self.original)
        self.assertEqual(self.client.agents.update_details.call_count, 2)
        self.smoke.assert_not_called()
        self.client.agents.delete_version.assert_not_called()
        self.client.agents.enable.assert_not_called()

    def test_prior_and_specialist_versions_need_not_use_candidate_model(self):
        profile = AgentProfile(
            self.profile.source_directory, self.profile.name, self.profile.description,
            self.profile.instructions, self.profile.smoke_test_prompt,
            (("fictional prompt", "inspect", "specialist"),),
        )
        previous = self.read_version(agent_name=self.args.agent_name, agent_version="1")
        self.assertEqual(previous.definition.environment_variables["FOUNDRY_MODEL_NAME"], "previous-model")
        deploy(profile, self.args)
        self.assertEqual(self.endpoint.version_selector.version_selection_rules[0].agent_version, "2")
        self.assertEqual(self.smoke.call_count, 2)
        self.client.agents.delete_version.assert_not_called()

    def test_failed_provisioning_redacts_version_definition_and_metadata(self):
        marker = "fictional-sensitive-content"

        def failed(*, agent_name, agent_version):
            details = self.read_version(agent_name=agent_name, agent_version=agent_version)
            if agent_version == "2":
                details["status"] = "failed"
                details["metadata"] = {"fictional": marker}
                details["definition"] = {"kind": "hosted", "environment_variables": {"PRIVATE": marker}}
            return details

        self.client.agents.get_version.side_effect = failed
        with redirect_stdout(io.StringIO()) as output:
            with self.assertRaises(RuntimeError) as caught:
                deploy(self.profile, self.args)
        self.assertEqual(str(caught.exception), "Agent version provisioning failed")
        self.assertNotIn(marker, output.getvalue())
        self.candidate.assert_not_called()
        self.client.agents.update_details.assert_not_called()
        self.client.agents.delete_version.assert_not_called()
        self.client.agents.enable.assert_not_called()

    def test_unrecognized_provisioning_status_is_redacted(self):
        marker = "fictional-sensitive-status"
        for status in (None, True, {"fictional": marker}, marker):
            with self.subTest(status_type=type(status).__name__):
                def invalid(*, agent_name, agent_version, status=status):
                    details = self.read_version(agent_name=agent_name, agent_version=agent_version)
                    if agent_version == "2":
                        details["status"] = status
                    return details

                self.client.agents.get_version.side_effect = invalid
                with redirect_stdout(io.StringIO()) as output:
                    with self.assertRaises(RuntimeError) as caught:
                        deploy(self.profile, self.args)
                self.assertEqual(str(caught.exception), "The agent version provisioning status was not confirmed")
                self.assertNotIn(marker, output.getvalue())
                self.candidate.assert_not_called()
                self.client.agents.update_details.assert_not_called()
                self.client.agents.delete_version.assert_not_called()
                self.client.agents.enable.assert_not_called()

    def test_parent_states_fail_closed_before_creation(self):
        for state, configuration in (("disabled", "enabled"), ("enabled", "disabled"),
                                      (None, "enabled"), ("enabled", None),
                                      ("unknown", "enabled"), (True, "enabled"),
                                      ("enabled", {})):
            with self.subTest(state=state, configuration=configuration):
                self.state, self.configuration_state = state, configuration
                with self.assertRaisesRegex(RuntimeError, "explicitly enabled"):
                    deploy(self.profile, self.args)
                self.assert_no_agent_mutations()
                self.client.agents.enable.assert_not_called()

    def test_pinned_sdk_operational_enum_and_raw_field_mapping(self):
        from azure.ai.projects.models import AgentDetails, AgentState

        details = AgentDetails({"state": AgentState.ENABLED, "configuration_state": AgentState.ENABLED})
        self.assertIsInstance(details.state, str)
        self.assertEqual(details.state, "enabled")
        self.assertEqual(details.get("configuration_state"), "enabled")
        self.assertFalse(hasattr(details, "configuration_state"))
        self.state, self.configuration_state = AgentState.ENABLED, AgentState.ENABLED
        deploy(self.profile, self.args)
        self.candidate.assert_called_once()

    def test_state_flip_before_promotion_refuses_route_write(self):
        def check(*args, **kwargs):
            self.state = "disabled"
        self.candidate.side_effect = check
        with self.assertRaisesRegex(RuntimeError, "explicitly enabled"):
            deploy(self.profile, self.args)
        self.client.agents.update_details.assert_not_called()
        self.client.agents.delete_version.assert_not_called()
        self.client.agents.enable.assert_not_called()

    def test_state_flip_after_promotion_refuses_rollback(self):
        def smoke(*args, **kwargs):
            self.state = "disabled"
            raise RuntimeError("fictional smoke failed")
        self.smoke.side_effect = smoke
        with redirect_stdout(io.StringIO()) as output:
            with self.assertRaisesRegex(RuntimeError, "fictional smoke failed"):
                deploy(self.profile, self.args)
        self.assertEqual(self.client.agents.update_details.call_count, 1)
        self.client.agents.delete_version.assert_not_called()
        self.client.agents.enable.assert_not_called()
        self.assertIn("retained version 2", output.getvalue())

    def test_non_responses_recovery_refuses_creation(self):
        self.endpoint.protocol_configuration = ProtocolConfiguration(mcp=McpProtocolConfiguration())
        with self.assertRaisesRegex(RuntimeError, "Recovery route has no Responses"):
            deploy(self.profile, self.args)
        self.assert_no_agent_mutations()

    def assert_no_agent_mutations(self):
        for method in ("create_version_from_code", "create_version", "create_session", "update_details",
                       "delete", "delete_version", "delete_session"):
            getattr(self.client.agents, method).assert_not_called()
        self.candidate.assert_not_called()
        self.smoke.assert_not_called()

    def test_missing_agent_stops_before_version_creation(self):
        self.missing = True
        with self.assertRaisesRegex(RuntimeError, "First publication is unsupported"):
            deploy(self.profile, self.args)
        self.assert_no_agent_mutations()

    def test_missing_or_unconfirmed_endpoint_stops_without_mutation(self):
        for endpoint in (None, self.route("@latest"), self.route("")):
            with self.subTest(endpoint=endpoint):
                self.endpoint = endpoint
                with self.assertRaisesRegex(RuntimeError, "Pin the existing"):
                    deploy(self.profile, self.args)
                self.assert_no_agent_mutations()

    def test_inactive_recovery_stops_without_mutation(self):
        self.client.agents.get_version.side_effect = None
        self.client.agents.get_version.return_value = {
            "name": self.args.agent_name, "version": "1", "status": "failed",
        }
        with self.assertRaisesRegex(RuntimeError, "not an active release"):
            deploy(self.profile, self.args)
        self.assert_no_agent_mutations()

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

    def test_inactive_or_draft_recovery_version_prevents_version_creation(self):
        self.client.agents.get_version.side_effect = None
        for details in ({"status": "creating"}, {"status": "failed"}, {"status": "active", "draft": True}):
            with self.subTest(details=details):
                self.client.agents.get_version.return_value = AgentVersionDetails({
                    "name": self.args.agent_name, "version": "1", **details,
                })
                with self.assertRaisesRegex(RuntimeError, "not an active release"):
                    deploy(self.profile, self.args)
                self.client.agents.create_version_from_code.assert_not_called()
                self.client.agents.update_details.assert_not_called()

    def test_missing_recovery_version_is_not_treated_as_a_missing_agent(self):
        self.client.agents.get_version.side_effect = ResourceNotFoundError()
        with self.assertRaises(ResourceNotFoundError):
            deploy(self.profile, self.args)
        self.client.agents.create_version_from_code.assert_not_called()
        self.client.agents.update_details.assert_not_called()

    def test_recovery_version_lost_during_build_prevents_promotion_and_retains_candidate(self):
        reads = {"recovery": 0}

        def read_version(*, agent_version, **kwargs):
            if agent_version == "1":
                reads["recovery"] += 1
                status = "active" if reads["recovery"] == 1 else "failed"
            else:
                status = "active"
            details = self.read_version(agent_name=kwargs["agent_name"], agent_version=agent_version)
            details["status"], details["draft"] = status, False
            return details

        self.client.agents.get_version.side_effect = read_version
        with self.assertRaisesRegex(RuntimeError, "not an active release"):
            deploy(self.profile, self.args)
        self.client.agents.create_version_from_code.assert_called_once()
        self.client.agents.update_details.assert_not_called()
        self.client.agents.delete_version.assert_not_called()
        self.assertEqual(self.endpoint, self.original)

    def test_route_changed_during_recovery_status_check_prevents_promotion(self):
        reads = {"recovery": 0}

        def read_version(*, agent_version, **kwargs):
            if agent_version == "1":
                reads["recovery"] += 1
                if reads["recovery"] == 2:
                    self.endpoint = self.route("3")
            return self.read_version(agent_name=kwargs["agent_name"], agent_version=agent_version)

        self.client.agents.get_version.side_effect = read_version
        with self.assertRaisesRegex(RuntimeError, "changed during deployment"):
            deploy(self.profile, self.args)
        self.client.agents.update_details.assert_not_called()
        self.client.agents.delete_version.assert_not_called()
        self.assertEqual(self.endpoint.version_selector.version_selection_rules[0].agent_version, "3")

    def test_failed_or_interrupted_smoke_restores_exact_endpoint_before_deletion(self):
        for error in (RuntimeError("smoke failed"), KeyboardInterrupt()):
            with self.subTest(error=type(error).__name__):
                self.endpoint = deepcopy(self.original)
                self.client.agents.delete_version.reset_mock()
                self.smoke.side_effect = error
                with self.assertRaises(type(error)):
                    deploy(self.profile, self.args)
                self.assertEqual(self.endpoint, self.original)
                self.client.agents.delete_version.assert_not_called()

    def test_missing_original_responses_is_refused_without_mutations(self):
        for protocols in (ProtocolConfiguration(mcp=McpProtocolConfiguration()), None):
            with self.subTest(protocols=protocols):
                route = self.route("1")
                if protocols is None:
                    self.endpoint = AgentEndpointConfig(version_selector=route.version_selector)
                else:
                    route.protocol_configuration = protocols
                    self.endpoint = route
                with self.assertRaisesRegex(RuntimeError, "Recovery route has no Responses"):
                    deploy(self.profile, self.args)
                self.assert_no_agent_mutations()

    def test_existing_responses_configuration_is_preserved_during_recovery(self):
        self.endpoint.protocol_configuration.responses["extra_setting"] = "preserved"
        self.endpoint.version_selector["extra_setting"] = "preserved"
        self.original = deepcopy(self.endpoint)
        self.smoke.side_effect = RuntimeError("smoke failed")
        with self.assertRaisesRegex(RuntimeError, "smoke failed"):
            deploy(self.profile, self.args)
        self.assertEqual(self.endpoint, self.original)
        self.client.agents.delete_version.assert_not_called()

    def test_split_route_is_restored_exactly_after_smoke_failure(self):
        self.endpoint.version_selector.version_selection_rules = [
            FixedRatioVersionSelectionRule(agent_version="1", traffic_percentage=60),
            FixedRatioVersionSelectionRule(agent_version="4", traffic_percentage=40),
        ]
        self.original = deepcopy(self.endpoint)
        self.smoke.side_effect = RuntimeError("smoke failed")
        with self.assertRaisesRegex(RuntimeError, "smoke failed"):
            deploy(self.profile, self.args)
        self.assertEqual(self.endpoint, self.original)
        self.client.agents.delete_version.assert_not_called()

    def test_recovery_version_lost_after_promotion_leaves_candidate_untouched(self):
        state = {"recovery_active": True}

        def read_version(*, agent_version, **kwargs):
            status = "active" if agent_version != "1" or state["recovery_active"] else "failed"
            details = self.read_version(agent_name=kwargs["agent_name"], agent_version=agent_version)
            details["status"], details["draft"] = status, False
            return details

        def fail_smoke(*args):
            state["recovery_active"] = False
            raise RuntimeError("smoke failed")

        self.client.agents.get_version.side_effect = read_version
        self.smoke.side_effect = fail_smoke
        with self.assertRaisesRegex(RuntimeError, "smoke failed"):
            deploy(self.profile, self.args)
        self.assertEqual(self.endpoint.version_selector.version_selection_rules[0].agent_version, "2")
        self.assertEqual(self.client.agents.update_details.call_count, 1)
        self.client.agents.delete_version.assert_not_called()

    def test_server_populated_endpoint_fields_are_preserved_during_recovery(self):
        state = self.endpoint.as_dict()
        state["publish_approval_status"] = "approved"
        self.endpoint = AgentEndpointConfig(state)
        self.original = deepcopy(self.endpoint)
        self.smoke.side_effect = RuntimeError("smoke failed")
        with self.assertRaisesRegex(RuntimeError, "smoke failed"):
            deploy(self.profile, self.args)
        self.assertEqual(self.endpoint, self.original)
        self.client.agents.delete_version.assert_not_called()

    def test_promotion_timeout_after_server_update_restores_the_original_route(self):
        def accepted_then_failed(**kwargs):
            self.update(**kwargs)
            if self.client.agents.update_details.call_count == 1:
                raise RuntimeError("promotion response lost")

        self.client.agents.update_details.side_effect = accepted_then_failed
        with self.assertRaisesRegex(RuntimeError, "promotion response lost"):
            deploy(self.profile, self.args)
        self.assertEqual(self.endpoint, self.original)
        self.assertEqual(self.client.agents.update_details.call_count, 2)
        self.client.agents.delete_version.assert_not_called()
        self.smoke.assert_not_called()

    def test_attempted_route_is_snapshotted_before_the_sdk_call(self):
        def accepted_then_mutated(**kwargs):
            self.update(**kwargs)
            if self.client.agents.update_details.call_count == 1:
                kwargs["agent_endpoint"].authorization_schemes = []
                raise RuntimeError("promotion response lost")

        self.client.agents.update_details.side_effect = accepted_then_mutated
        with self.assertRaisesRegex(RuntimeError, "promotion response lost"):
            deploy(self.profile, self.args)
        self.assertEqual(self.endpoint, self.original)
        self.client.agents.delete_version.assert_not_called()

    def test_failure_after_another_operator_changes_the_route_does_not_overwrite_it(self):
        def change_route(*args):
            self.endpoint = self.route("3")
            raise RuntimeError("smoke failed")

        self.smoke.side_effect = change_route
        with self.assertRaisesRegex(RuntimeError, "smoke failed"):
            deploy(self.profile, self.args)
        self.assertEqual(self.endpoint, self.route("3"))
        self.assertEqual(self.client.agents.update_details.call_count, 1)
        self.client.agents.delete_version.assert_not_called()

    def test_failure_after_endpoint_authorization_changes_does_not_overwrite_it(self):
        def change_authorization(*args):
            self.endpoint.authorization_schemes = []
            raise RuntimeError("smoke failed")

        self.smoke.side_effect = change_authorization
        with self.assertRaisesRegex(RuntimeError, "smoke failed"):
            deploy(self.profile, self.args)
        self.assertEqual(self.endpoint.authorization_schemes, [])
        self.assertEqual(self.endpoint.version_selector.version_selection_rules[0].agent_version, "2")
        self.assertEqual(self.client.agents.update_details.call_count, 1)
        self.client.agents.delete_version.assert_not_called()

    def run_with_lookup_check(self, *responses):
        tool = "search_policy_guidance"
        profile = AgentProfile(
            self.profile.source_directory, self.profile.name, self.profile.description,
            self.profile.instructions, self.profile.smoke_test_prompt, ((KNOWLEDGE_CHECK_PROMPT, tool),),
        )
        general = self.reply([])
        create = self.client.get_openai_client.return_value.__enter__.return_value.responses.create
        create.side_effect = [general, *responses]
        self.smoke.side_effect = real_smoke_test
        self.endpoint = deepcopy(self.original)
        with redirect_stdout(io.StringIO()):
            try:
                deploy(profile, self.args)
            except RuntimeError as error:
                return create.call_count, error
        return create.call_count, None

    def reply(self, items):
        return SimpleNamespace(status="completed", output_text="reply", model_dump=lambda: {"output": items})

    def lookup(self, tool="search_policy_guidance"):
        receipt = {"status": "succeeded", "agent": "case-review-agent", "output": "passage",
                   "retrieval": True, "source_ids": ["POL-EVID-001"]}
        return self.reply([
            {"type": "function_call", "name": tool, "call_id": "call-1"},
            {"type": "function_call_output", "call_id": "call-1", "output": json.dumps(receipt)},
        ])

    def assert_rolled_back_and_retained(self):
        self.assertEqual(self.endpoint, self.original)
        self.client.agents.delete_version.assert_not_called()

    def test_a_lookup_skipped_once_is_retried_and_the_new_version_stays_promoted(self):
        calls, error = self.run_with_lookup_check(self.reply([]), self.lookup())
        self.assertIsNone(error)
        self.assertEqual(calls, 3)
        self.assertEqual(self.endpoint.version_selector.version_selection_rules[0].agent_version, "2")
        self.client.agents.delete_version.assert_not_called()

    def test_a_lookup_skipped_twice_rolls_back_and_retains_the_new_version(self):
        calls, error = self.run_with_lookup_check(self.reply([]), self.reply([]), self.lookup())
        self.assertEqual(str(error), "Expected exactly one search_policy_guidance tool call")
        self.assertEqual(calls, 3)
        self.assert_rolled_back_and_retained()

    def test_a_wrong_tool_fails_on_the_first_attempt_and_rolls_back_and_retains_the_new_version(self):
        calls, error = self.run_with_lookup_check(self.lookup(tool="other_tool"), self.lookup())
        self.assertIsInstance(error, RuntimeError)
        self.assertEqual(calls, 2)
        self.assert_rolled_back_and_retained()

    def test_changed_route_before_promotion_is_not_overwritten(self):
        def creating(**kwargs):
            result = self.create(**kwargs)
            self.endpoint = self.route("3")
            return result

        self.client.agents.create_version_from_code.side_effect = creating
        with self.assertRaisesRegex(RuntimeError, "changed during deployment"):
            deploy(self.profile, self.args)
        self.candidate.assert_not_called()
        self.client.agents.update_details.assert_not_called()
        self.client.agents.delete_version.assert_not_called()
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
        self.assertEqual(self.endpoint.version_selector.version_selection_rules[0].agent_version, "@latest")
        self.assertEqual(self.client.agents.update_details.call_count, 1)
        self.client.agents.delete_version.assert_not_called()

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


    def test_candidate_check_precedes_promotion_and_post_smoke(self):
        def check(*args, **kwargs):
            self.events.append("candidate")
            self.assertEqual(args[2], "2")
            self.assertEqual(self.endpoint, self.original)
        self.candidate.side_effect = check
        deploy(self.profile, self.args)
        self.assertLess(self.events.index("candidate"), self.events.index("update"))
        self.smoke.assert_called_once_with(self.client, self.profile.name, self.args.smoke_test_prompt)

    def test_candidate_failure_never_promotes(self):
        self.candidate.side_effect = RuntimeError("candidate failure")
        with self.assertRaisesRegex(RuntimeError, "candidate failure"):
            deploy(self.profile, self.args)
        self.client.agents.update_details.assert_not_called()
        self.client.agents.delete_version.assert_not_called()
        self.smoke.assert_not_called()
        self.assertEqual(self.endpoint, self.original)

    def test_route_changed_during_candidate_check_never_promotes(self):
        def race(*args, **kwargs):
            self.endpoint = self.route("3")
        self.candidate.side_effect = race
        with self.assertRaisesRegex(RuntimeError, "changed during deployment"):
            deploy(self.profile, self.args)
        self.client.agents.update_details.assert_not_called()
        self.client.agents.delete_version.assert_not_called()

    def test_candidate_inactive_after_smoke_never_promotes(self):
        def check(*args, **kwargs):
            self.client.agents.get_version.side_effect = lambda *, agent_version, **kwargs: {
                "name": kwargs["agent_name"], "version": agent_version,
                "status": "failed" if agent_version == "2" else "active",
            }
        self.candidate.side_effect = check
        with self.assertRaisesRegex(RuntimeError, "candidate agent version is not active"):
            deploy(self.profile, self.args)
        self.client.agents.update_details.assert_not_called()

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

    def test_real_sdk_deserializes_documented_administrative_wire_field(self):
        from urllib.parse import parse_qs, urlsplit

        from azure.ai.projects.models import AgentDetails

        payloads = [
            {"state": "enabled", "configuration_state": "enabled"},
            {"state": "enabled", "configuration_state": "disabled"},
            {"state": "enabled", "configuration_state": "unknown"},
            {"state": "enabled", "configuration_state": None},
            {"state": "enabled", "configuration_state": True},
            {"state": "enabled", "configuration_state": {}},
            {"state": "enabled"},
            {"state": "disabled", "configuration_state": "enabled"},
            {"state": "unknown", "configuration_state": "enabled"},
            {"state": True, "configuration_state": "enabled"},
            {"configuration_state": "enabled"},
        ]
        sent = []
        remaining = iter(payloads)

        def respond(adapter, request, **kwargs):
            sent.append((request.method, request.url))
            response = requests.Response()
            response.status_code = 200
            response._content = json.dumps(next(remaining)).encode()
            response.raw = io.BytesIO(response._content)
            response.headers["Content-Type"] = "application/json"
            response.request = request
            return response

        with patch.object(requests.adapters.HTTPAdapter, "send", respond):
            with AIProjectClient(
                endpoint="https://fictional.services.ai.azure.com/api/projects/demo",
                credential=self.Credential(), allow_preview=True, retry_total=0,
            ) as client:
                for payload in payloads:
                    with self.subTest(payload=payload):
                        details = client.agents.get(agent_name="fictional-agent")
                        self.assertIsInstance(details, AgentDetails)
                        self.assertEqual(details.get("state"), payload.get("state"))
                        self.assertEqual(
                            details.get("configuration_state"), payload.get("configuration_state"),
                        )
                        self.assertEqual("configuration_state" in details, "configuration_state" in payload)
                        self.assertFalse(hasattr(details, "configuration_state"))
                        fictional = SimpleNamespace(agents=SimpleNamespace(get=lambda details=details, **kwargs: details))
                        if payload.get("state") == payload.get("configuration_state") == "enabled":
                            self.assertIsNone(enabled_endpoint(fictional, "fictional-agent"))
                        else:
                            with self.assertRaisesRegex(RuntimeError, "explicitly enabled"):
                                enabled_endpoint(fictional, "fictional-agent")
        self.assertEqual(len(sent), len(payloads))
        for method, url in sent:
            self.assertEqual(method, "GET")
            self.assertEqual(parse_qs(urlsplit(url).query).get("api-version"), ["v1"])

    def test_real_sdk_deserializes_exact_agent_version_identity(self):
        from urllib.parse import parse_qs, urlsplit

        responses = [
            {"name": "fictional-agent", "version": "2", "status": "active", "draft": False},
            {"name": "other", "version": "2", "status": "active", "draft": False},
            {"name": "fictional-agent", "version": "3", "status": "active", "draft": False},
            {"version": "2", "status": "active"},
            {"name": "fictional-agent", "status": "active"},
            {"name": "fictional-agent", "version": 2, "status": "active"},
        ]
        remaining = iter(responses)
        sent = []

        def respond(adapter, request, **kwargs):
            sent.append((request.method, request.url))
            response = requests.Response()
            response.status_code = 200
            response._content = json.dumps(next(remaining)).encode()
            response.raw = io.BytesIO(response._content)
            response.headers["Content-Type"] = "application/json"
            response.request = request
            return response

        with patch.object(requests.adapters.HTTPAdapter, "send", respond):
            with AIProjectClient(
                endpoint="https://fictional.services.ai.azure.com/api/projects/demo",
                credential=self.Credential(), allow_preview=True, retry_total=0,
            ) as client:
                for index, payload in enumerate(responses):
                    with self.subTest(payload=payload):
                        details = client.agents.get_version(agent_name="fictional-agent", agent_version="2")
                        self.assertIsInstance(details, AgentVersionDetails)
                        self.assertEqual(details.get("name"), payload.get("name"))
                        self.assertEqual(details.get("version"), payload.get("version"))
                        self.assertEqual(active_release(details, "fictional-agent", "2"), index == 0)
        self.assertEqual(len(sent), len(responses))
        for method, url in sent:
            self.assertEqual(method, "GET")
            self.assertIn("/agents/fictional-agent/versions/2", urlsplit(url).path)
            self.assertEqual(parse_qs(urlsplit(url).query).get("api-version"), ["v1"])

    def test_real_sdk_deserializes_hosted_candidate_model_configuration(self):
        from azure.ai.projects.models import HostedAgentDefinition

        payload = {
            "name": "fictional-agent", "version": "2", "status": "active", "draft": False,
            "definition": {"kind": "hosted", "cpu": "0.5", "memory": "1Gi",
                           "environment_variables": {"FOUNDRY_MODEL_NAME": "router-model"}},
        }
        sent = []

        def respond(adapter, request, **kwargs):
            sent.append((request.method, request.url))
            response = requests.Response()
            response.status_code = 200
            response._content = json.dumps(payload).encode()
            response.raw = io.BytesIO(response._content)
            response.headers["Content-Type"] = "application/json"
            response.request = request
            return response

        with patch.object(requests.adapters.HTTPAdapter, "send", respond):
            with AIProjectClient(
                endpoint="https://fictional.services.ai.azure.com/api/projects/demo",
                credential=self.Credential(), allow_preview=True, retry_total=0,
            ) as client:
                details = client.agents.get_version(agent_name="fictional-agent", agent_version="2")
                self.assertIsInstance(details.definition, HostedAgentDefinition)
                self.assertEqual(details.definition.environment_variables["FOUNDRY_MODEL_NAME"], "router-model")
                self.assertTrue(candidate_model_matches(details, "router-model"))
                self.assertFalse(candidate_model_matches(details, "different-model"))
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0][0], "GET")

    def test_a_stalled_foundry_call_fails_once_on_the_clients_own_deadline(self):
        attempts = self.deploy_against_failing_transport(requests.exceptions.ReadTimeout)
        self.assertEqual(attempts, [(30, 60)])

    def test_a_failed_foundry_connection_is_not_retried(self):
        attempts = self.deploy_against_failing_transport(requests.exceptions.ConnectionError)
        self.assertEqual(attempts, [(30, 60)])

    def test_recovery_patch_serializes_protocol_removal_through_the_real_sdk(self):
        selector = VersionSelector(version_selection_rules=[
            FixedRatioVersionSelectionRule(agent_version="1", traffic_percentage=100),
        ])
        for protocols in (ProtocolConfiguration(mcp=McpProtocolConfiguration()), None):
            with self.subTest(protocols=protocols):
                original = AgentEndpointConfig(version_selector=selector)
                if protocols is not None:
                    original.protocol_configuration = protocols
                requests_sent = []

                def respond(adapter, request, requests_sent=requests_sent, **kwargs):
                    requests_sent.append((request.method, request.headers["Content-Type"], json.loads(request.body)))
                    response = requests.Response()
                    response.status_code = 200
                    response._content = b"{}"
                    response.raw = io.BytesIO(b"{}")
                    response.headers["Content-Type"] = "application/json"
                    response.request = request
                    return response

                with patch.object(requests.adapters.HTTPAdapter, "send", respond):
                    with AIProjectClient(
                        endpoint="https://fictional.services.ai.azure.com/api/projects/demo",
                        credential=self.Credential(), allow_preview=True, retry_total=0,
                    ) as client:
                        client.agents.update_details(agent_name="agent", agent_endpoint=recovery_endpoint(original))
                self.assertEqual(len(requests_sent), 1)
                self.assertEqual(requests_sent[0][0], "PATCH")
                self.assertEqual(requests_sent[0][1], "application/merge-patch+json")
                body = requests_sent[0][2]["agent_endpoint"]
                if protocols is None:
                    self.assertIsNone(body["protocol_configuration"])
                else:
                    self.assertIsNone(body["protocol_configuration"]["responses"])
                    self.assertEqual(body["protocol_configuration"]["mcp"], {})


if __name__ == "__main__":
    unittest.main()

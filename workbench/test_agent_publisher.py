import hashlib
import io
import stat
import unittest
from contextlib import asynccontextmanager
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from zipfile import ZipFile

from azure.ai.projects.models import (
    AgentEndpointConfig, AgentVersionDetails, EntraAuthorizationScheme, FixedRatioVersionSelectionRule,
    ProtocolConfiguration, ResponsesProtocolConfiguration, VersionSelector,
)
from azure.core.exceptions import ResourceNotFoundError

from agent_publisher import FoundryPublisher, PublicationError, ownership, runtime_package, service_error_code


def endpoint(version="1", percentage=100):
    return AgentEndpointConfig(
        version_selector=VersionSelector(version_selection_rules=[
            FixedRatioVersionSelectionRule(agent_version=version, traffic_percentage=percentage),
        ]),
        protocol_configuration=ProtocolConfiguration(responses=ResponsesProtocolConfiguration()),
    )


class FakeAgents:
    def __init__(self, document):
        self.document = document
        self.exists = False
        self.version = SimpleNamespace(name=document["runtime_name"], version="1",
                                       metadata=ownership(document), status="active", draft=False)
        self.endpoint = None
        self.created = []
        self.promotions = []
        self.deleted = []
        self.extra_versions = []
        self.get_version = AsyncMock(side_effect=self.read_version)
        self.preserve_after_delete = False

    async def get(self, *, agent_name):
        if not self.exists:
            raise ResourceNotFoundError()
        return SimpleNamespace(name=agent_name, agent_endpoint=self.endpoint)

    async def create_version_from_code(self, **kwargs):
        self.exists = True
        self.created.append({**kwargs, "zip": kwargs["code"].read(), "zip_name": kwargs["code"].name})
        return self.version

    async def list_versions(self, **kwargs):
        if not self.exists:
            raise ResourceNotFoundError()
        for version in [self.version, *self.extra_versions]:
            yield version

    async def read_version(self, **kwargs):
        return self.version

    async def update_details(self, **kwargs):
        self.promotions.append(kwargs)
        self.endpoint = kwargs["agent_endpoint"]

    async def delete(self, **kwargs):
        self.deleted.append(kwargs)
        if not self.preserve_after_delete:
            self.exists = False


class FakeDeployments:
    def __init__(self, names):
        self.names = set(names)
        self.reads = []

    async def get(self, *, name):
        self.reads.append(name)
        if name not in self.names:
            raise ResourceNotFoundError()
        return SimpleNamespace(name=name)


class PublisherTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        _, digest = runtime_package()
        self.document = {
            "id": "created-11111111-2222-4333-8444-555555555555",
            "runtime_name": "lab-demo-11111111222243338444555555555555",
            "template_id": "document-analyst", "instructions": "Summarize only fictional supplied documents.",
            "model": "configured-model", "setup_hash": "setup-hash", "runtime_hash": digest,
            "publication_started": False, "version": None,
        }
        self.agents = FakeAgents(self.document)
        self.deployments = FakeDeployments({"configured-model"})
        self.events = []

        @asynccontextmanager
        async def client():
            yield SimpleNamespace(agents=self.agents, deployments=self.deployments)

        self.publisher = FoundryPublisher(
            "https://fictional.services.ai.azure.com/api/projects/lab",
            poll_seconds=0, client_factory=client,
        )

    async def progress(self, stage, **changes):
        self.events.append((stage, deepcopy(changes)))
        self.document.update(changes)

    async def assert_code(self, code, operation):
        with self.assertRaises(PublicationError) as raised:
            await operation(self.document, self.progress)
        self.assertEqual(raised.exception.code, code)

    async def test_real_sdk_definition_and_named_integrity_checked_source_zip(self):
        await self.publisher.create(self.document, self.progress)
        self.assertEqual(len(self.agents.created), 1)
        submitted = self.agents.created[0]
        definition = submitted["definition"]
        serialized = definition.as_dict()
        self.assertEqual(definition.code_configuration.runtime, "python_3_14")
        self.assertEqual(definition.code_configuration.entry_point, ["python", "main.py"])
        self.assertEqual(definition.code_configuration.dependency_resolution, "remote_build")
        self.assertEqual(definition.environment_variables["AGENT_STORE_RESPONSES"], "false")
        for key in (
            "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT",
            "ENABLE_SENSITIVE_DATA",
            "AZURE_TRACING_GEN_AI_CONTENT_RECORDING_ENABLED",
        ):
            self.assertEqual(definition.environment_variables[key], "false")
        self.assertEqual(definition.environment_variables["APPLICATIONINSIGHTS_AUTH_MODE"], "entra")
        self.assertEqual(definition.environment_variables["APPLICATIONINSIGHTS_STATSBEAT_DISABLED_ALL"], "true")
        self.assertEqual(definition.environment_variables["AGENT_INSTRUCTIONS"], self.document["instructions"])
        self.assertEqual(definition.environment_variables["DEMO_TEMPLATE_ID"], "document-analyst")
        self.assertEqual(definition.environment_variables["FOUNDRY_MODEL_NAME"], "configured-model")
        self.assertEqual(definition.cpu, "0.5")
        self.assertEqual(definition.memory, "1Gi")
        self.assertEqual(serialized["kind"], "hosted")
        self.assertEqual(submitted["zip_name"], "agent.zip")
        self.assertEqual(hashlib.sha256(submitted["zip"]).hexdigest(), submitted["code_zip_sha256"])
        with ZipFile(io.BytesIO(submitted["zip"])) as archive:
            self.assertEqual(set(archive.namelist()), {"main.py", "demo_tools.py", "requirements.txt"})
        self.assertEqual(submitted["metadata"], ownership(self.document))
        self.assertTrue(self.document["publication_started"])
        self.assertEqual(self.events[0][0], "uploading")
        self.assertEqual(self.document["status"], "ready")
        self.assertTrue(self.publisher.route_matches(self.agents.endpoint, "1"))

    async def test_packaging_is_deterministic_and_does_not_include_other_workspace_files(self):
        first, digest = runtime_package()
        second, other_digest = runtime_package()
        self.assertEqual(first, second)
        self.assertEqual(digest, other_digest)
        with ZipFile(io.BytesIO(first)) as archive:
            for info in archive.infolist():
                name = info.filename
                self.assertNotIn("\\", name)
                self.assertNotIn("/", name)
                self.assertNotIn(".env", name)
                self.assertEqual(info.create_system, 3)
                self.assertTrue(stat.S_ISREG(info.external_attr >> 16))
                self.assertEqual(stat.S_IMODE(info.external_attr >> 16), 0o644)

    async def test_new_agent_default_latest_route_is_pinned_to_the_owned_version(self):
        original = self.agents.create_version_from_code

        async def create_with_default_route(**kwargs):
            created = await original(**kwargs)
            self.agents.endpoint = endpoint(version="@latest")
            self.agents.endpoint.authorization_schemes = [EntraAuthorizationScheme()]
            return created

        self.agents.create_version_from_code = create_with_default_route
        await self.publisher.create(self.document, self.progress)
        self.assertEqual(self.document["status"], "ready")
        self.assertTrue(self.publisher.route_matches(self.agents.endpoint, "1"))
        self.assertEqual(len(self.agents.endpoint.authorization_schemes), 1)

    async def test_partial_latest_route_is_not_overwritten(self):
        self.document["publication_started"] = True
        self.agents.exists = True
        self.agents.endpoint = endpoint(version="@latest", percentage=50)
        await self.assert_code("resource_changed", self.publisher.resume)
        self.assertEqual(self.agents.promotions, [])

    async def test_saved_model_deployment_is_used_and_must_exist_before_upload(self):
        self.document["model"] = "extraction-model"
        await self.assert_code("model_unavailable", self.publisher.create)
        self.assertEqual(self.deployments.reads, ["extraction-model"])
        self.assertEqual(self.agents.created, [])
        self.assertEqual(self.events, [])
        self.assertFalse(self.document["publication_started"])
        self.deployments.names.add("extraction-model")
        await self.publisher.create(self.document, self.progress)
        variables = self.agents.created[0]["definition"].environment_variables
        self.assertEqual(variables["FOUNDRY_MODEL_NAME"], "extraction-model")

    async def test_existing_name_is_never_given_a_new_version(self):
        self.agents.exists = True
        await self.assert_code("resource_changed", self.publisher.create)
        self.assertEqual(self.agents.created, [])
        self.assertEqual(self.events, [])

    async def test_changed_runtime_is_not_published_from_old_setup(self):
        self.document["runtime_hash"] = "old-code"
        await self.assert_code("runtime_changed", self.publisher.create)
        self.assertEqual(self.agents.created, [])

    async def test_publication_started_is_persisted_before_external_mutation(self):
        async def fail_to_save(stage, **changes):
            raise RuntimeError("Simulated storage outage")

        with self.assertRaises(RuntimeError):
            await self.publisher.create(self.document, fail_to_save)
        self.assertEqual(self.agents.created, [])

    async def test_resume_reconciles_existing_version_without_second_upload(self):
        self.document["publication_started"] = True
        self.agents.exists = True
        await self.publisher.resume(self.document, self.progress)
        self.assertEqual(self.agents.created, [])
        self.assertEqual(self.document["version"], "1")
        self.assertEqual(self.document["status"], "ready")

    async def test_resume_can_perform_first_submission_when_nothing_was_ever_started(self):
        await self.publisher.resume(self.document, self.progress)
        self.assertEqual(len(self.agents.created), 1)

    async def test_uncertain_creation_is_not_retried_just_because_resource_is_absent(self):
        self.document["publication_started"] = True
        await self.assert_code("publication_unconfirmed", self.publisher.resume)
        self.assertEqual(self.agents.created, [])
        self.assertEqual(self.agents.promotions, [])

    async def test_failed_runtime_is_not_routed(self):
        self.agents.version.status = "failed"
        await self.assert_code("runtime_failed", self.publisher.create)
        self.assertEqual(self.agents.promotions, [])

    async def test_failed_runtime_reports_only_a_safe_foundry_error_code(self):
        self.agents.version.status = "failed"
        self.agents.version.error = {"code": "CodeError", "message": "No Python dependency manifest found"}
        with self.assertRaises(PublicationError) as raised:
            await self.publisher.create(self.document, self.progress)
        self.assertEqual(raised.exception.code, "runtime_failed")
        self.assertEqual(raised.exception.service_error, "CodeError")
        self.assertEqual(service_error_code(AgentVersionDetails({"error": {"code": "CodeError"}})), "CodeError")
        for error in (None, {}, {"code": "free text with spaces"}, {"code": 7}, "CodeError"):
            with self.subTest(error=error):
                self.assertIsNone(service_error_code(SimpleNamespace(error=error)))

    async def test_activation_is_polled_before_routing(self):
        creating = deepcopy(self.agents.version)
        creating.status = "creating"
        self.agents.get_version.side_effect = [creating, self.agents.version, self.agents.version]
        await self.publisher.create(self.document, self.progress)
        self.assertEqual(self.agents.get_version.await_count, 3)
        self.assertEqual(len(self.agents.promotions), 1)

    async def test_missing_optional_status_is_pending_not_a_false_runtime_failure(self):
        pending = deepcopy(self.agents.version)
        pending.status = None
        self.agents.get_version.side_effect = [pending, self.agents.version, self.agents.version]
        await self.publisher.create(self.document, self.progress)
        self.assertEqual(self.agents.get_version.await_count, 3)
        self.assertEqual(self.document["status"], "ready")

    async def test_draft_version_is_not_routed_even_when_marked_active(self):
        self.agents.version.draft = True
        await self.assert_code("runtime_failed", self.publisher.create)
        self.assertEqual(self.agents.promotions, [])

    async def test_unrouted_endpoint_can_be_connected_without_changing_authorization(self):
        self.document["publication_started"] = True
        self.agents.exists = True
        for rules in (None, []):
            with self.subTest(rules=rules):
                self.agents.endpoint = AgentEndpointConfig(
                    version_selector=VersionSelector(version_selection_rules=rules),
                    authorization_schemes=[EntraAuthorizationScheme()],
                )
                authorization = deepcopy(self.agents.endpoint.authorization_schemes)
                await self.publisher.resume(self.document, self.progress)
                self.assertEqual(self.agents.endpoint.authorization_schemes, authorization)
                self.assertTrue(self.publisher.route_matches(self.agents.endpoint, "1"))
        self.assertEqual(self.agents.created, [])

    async def test_foreign_missing_metadata_or_extra_versions_block_promotion_and_deletion(self):
        self.agents.exists = True
        self.document["publication_started"] = True
        original = deepcopy(self.agents.version.metadata)
        for metadata in (None, {}, {**original, "workbench_creation_id": "someone-else"}):
            self.agents.version.metadata = metadata
            with self.subTest(metadata=metadata):
                await self.assert_code("resource_changed", self.publisher.resume)
                await self.assert_code("resource_changed", self.publisher.delete)
        self.agents.version.metadata = original
        self.agents.extra_versions = [deepcopy(self.agents.version)]
        await self.assert_code("resource_changed", self.publisher.resume)
        await self.assert_code("resource_changed", self.publisher.delete)
        self.assertEqual(self.agents.promotions, [])
        self.assertEqual(self.agents.deleted, [])

    async def test_changed_endpoint_is_not_overwritten(self):
        self.document["publication_started"] = True
        self.agents.exists = True
        self.agents.endpoint = endpoint(version="other-version")
        await self.assert_code("resource_changed", self.publisher.resume)
        self.assertEqual(self.agents.promotions, [])

    async def test_route_readback_is_required_before_ready(self):
        async def ignore_route(**kwargs):
            self.agents.endpoint = endpoint(percentage=50)

        self.agents.update_details = ignore_route
        await self.assert_code("publication_unconfirmed", self.publisher.create)
        self.assertNotIn("ready", [stage for stage, _ in self.events])

    async def test_delete_verifies_ownership_records_version_and_confirms_absence(self):
        self.document["publication_started"] = True
        self.agents.exists = True
        await self.publisher.delete(self.document, self.progress)
        self.assertEqual(self.document["version"], "1")
        self.assertEqual(self.agents.deleted, [{"agent_name": self.document["runtime_name"], "force": True}])
        self.assertEqual(self.document["status"], "deleted")
        self.assertEqual(self.events[0][0], "deleting")

    async def test_delete_after_uncertain_create_does_not_treat_404_as_confirmation(self):
        self.document["publication_started"] = True
        await self.assert_code("deletion_unconfirmed", self.publisher.delete)
        self.assertEqual(self.agents.deleted, [])
        self.assertNotIn("deleted", [stage for stage, _ in self.events])

    async def test_known_version_already_absent_can_be_confirmed_deleted(self):
        self.document.update(publication_started=True, version="1")
        await self.publisher.delete(self.document, self.progress)
        self.assertEqual(self.document["status"], "deleted")
        self.assertEqual(self.agents.deleted, [])

    async def test_never_submitted_record_can_be_retired_without_cloud_mutation(self):
        await self.publisher.delete(self.document, self.progress)
        self.assertEqual(self.document["status"], "deleted")
        self.assertEqual(self.agents.deleted, [])

    async def test_delete_does_not_claim_success_until_resource_disappears(self):
        self.document["publication_started"] = True
        self.agents.exists = True
        self.agents.preserve_after_delete = True
        with patch("agent_publisher.asyncio.sleep", side_effect=TimeoutError):
            with self.assertRaises(TimeoutError):
                await self.publisher.delete(self.document, self.progress)
        self.assertNotIn("deleted", [stage for stage, _ in self.events])

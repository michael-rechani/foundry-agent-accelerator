import asyncio
import hashlib
import io
import os
from contextlib import asynccontextmanager
from copy import deepcopy
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from azure.core.exceptions import ResourceNotFoundError


RUNTIME_FILES = ("main.py", "demo_tools.py", "requirements.txt")
RUNTIME_DIRECTORY = Path(__file__).with_name("agent_runtime")


class PublicationError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class CodeArchive(io.BytesIO):
    name = "agent.zip"


def runtime_package():
    output = io.BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for name in RUNTIME_FILES:
            source = (RUNTIME_DIRECTORY / name).read_bytes()
            if len(source) > 65536:
                raise PublicationError("runtime_unavailable")
            info = ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, source)
    package = output.getvalue()
    return package, hashlib.sha256(package).hexdigest()


def resource_name(identifier):
    return "lab-demo-" + identifier.removeprefix("created-").replace("-", "")


def ownership(document):
    return {
        "workbench_creation_id": document["id"],
        "workbench_template_id": document["template_id"],
        "workbench_setup_hash": document["setup_hash"],
        "workbench_runtime_hash": document["runtime_hash"],
    }


class FoundryPublisher:
    def __init__(self, endpoint, *, poll_seconds=5, client_factory=None):
        self.endpoint = endpoint
        self.poll_seconds, self.client_factory = poll_seconds, client_factory

    @asynccontextmanager
    async def client(self):
        if self.client_factory is not None:
            async with self.client_factory() as client:
                yield client
            return
        from azure.ai.projects.aio import AIProjectClient
        from azure.identity.aio import ManagedIdentityCredential

        async with ManagedIdentityCredential(client_id=os.getenv("AZURE_CLIENT_ID")) as credential:
            async with AIProjectClient(
                endpoint=self.endpoint, credential=credential, allow_preview=True,
                retry_total=0, connection_timeout=10, read_timeout=60,
            ) as client:
                yield client

    def verify_version(self, document, version):
        if (version.name != document["runtime_name"]
                or not isinstance(version.metadata, dict)
                or any(version.metadata.get(key) != value for key, value in ownership(document).items())
                or (document["version"] is not None and str(version.version) != document["version"])):
            raise PublicationError("resource_changed")

    async def only_owned_version(self, client, document):
        versions = []
        async for version in client.agents.list_versions(
            agent_name=document["runtime_name"], include_drafts=True, limit=2,
        ):
            versions.append(version)
            if len(versions) > 1:
                raise PublicationError("resource_changed")
        if not versions:
            raise PublicationError("publication_unconfirmed")
        self.verify_version(document, versions[0])
        return versions[0]

    @staticmethod
    def route_matches(endpoint, version):
        selector = getattr(endpoint, "version_selector", None)
        rules = getattr(selector, "version_selection_rules", None)
        protocols = getattr(endpoint, "protocol_configuration", None)
        return (
            getattr(protocols, "responses", None) is not None
            and isinstance(rules, list) and len(rules) == 1
            and str(rules[0].agent_version) == version
            and type(rules[0].traffic_percentage) in (int, float)
            and rules[0].traffic_percentage == 100
        )

    async def finish(self, client, document, progress):
        from azure.ai.projects.models import (
            AgentEndpointConfig, FixedRatioVersionSelectionRule, ProtocolConfiguration,
            ResponsesProtocolConfiguration, VersionSelector,
        )

        version = await self.only_owned_version(client, document)
        identifier = str(version.version)
        await progress("provisioning", version=identifier)
        while True:
            details = await client.agents.get_version(
                agent_name=document["runtime_name"], agent_version=identifier,
            )
            self.verify_version(document, details)
            if getattr(details, "draft", False):
                raise PublicationError("runtime_failed")
            if details.status == "active":
                break
            if details.status not in (None, "creating"):
                raise PublicationError("runtime_failed")
            await asyncio.sleep(self.poll_seconds)

        await self.only_owned_version(client, document)
        existing = await client.agents.get(agent_name=document["runtime_name"])
        selector = getattr(existing.agent_endpoint, "version_selector", None)
        rules = getattr(selector, "version_selection_rules", None)
        if (rules not in (None, [])
                and not self.route_matches(existing.agent_endpoint, identifier)):
            raise PublicationError("resource_changed")
        await progress("routing")
        protocols = deepcopy(getattr(existing.agent_endpoint, "protocol_configuration", None))
        if protocols is None:
            protocols = ProtocolConfiguration()
        protocols.responses = ResponsesProtocolConfiguration()
        configuration = AgentEndpointConfig(
            version_selector=VersionSelector(version_selection_rules=[
                FixedRatioVersionSelectionRule(agent_version=identifier, traffic_percentage=100),
            ]),
            protocol_configuration=protocols,
        )
        authorization = getattr(existing.agent_endpoint, "authorization_schemes", None)
        if authorization is not None:
            configuration.authorization_schemes = deepcopy(authorization)
        await client.agents.update_details(
            agent_name=document["runtime_name"],
            agent_endpoint=configuration,
        )
        endpoint = (await client.agents.get(agent_name=document["runtime_name"])).agent_endpoint
        details = await client.agents.get_version(
            agent_name=document["runtime_name"], agent_version=identifier,
        )
        self.verify_version(document, details)
        if (details.status != "active" or getattr(details, "draft", False)
                or not self.route_matches(endpoint, identifier)):
            raise PublicationError("publication_unconfirmed")
        await progress("ready", status="ready", error=None)

    async def create(self, document, progress):
        from azure.ai.projects.models import (
            CodeConfiguration, CodeDependencyResolution, HostedAgentDefinition, ProtocolVersionRecord,
        )

        package, digest = runtime_package()
        if digest != document["runtime_hash"]:
            raise PublicationError("runtime_changed")
        async with self.client() as client:
            try:
                await client.agents.get(agent_name=document["runtime_name"])
            except ResourceNotFoundError:
                pass
            else:
                raise PublicationError("resource_changed")
            try:
                await client.deployments.get(name=document["model"])
            except ResourceNotFoundError as problem:
                raise PublicationError("model_unavailable") from problem

            await progress("uploading", publication_started=True)
            with CodeArchive(package) as code:
                created = await client.agents.create_version_from_code(
                    agent_name=document["runtime_name"],
                    description="Fictional-input Lab demonstration: " + document["template_id"],
                    metadata=ownership(document),
                    definition=HostedAgentDefinition(
                        cpu="0.5", memory="1Gi",
                        code_configuration=CodeConfiguration(
                            runtime="python_3_14", entry_point=["python", "main.py"],
                            dependency_resolution=CodeDependencyResolution.REMOTE_BUILD,
                        ),
                        environment_variables={
                            "FOUNDRY_PROJECT_ENDPOINT": self.endpoint,
                            "FOUNDRY_MODEL_NAME": document["model"],
                            "AGENT_NAME": document["runtime_name"],
                            "AGENT_INSTRUCTIONS": document["instructions"],
                            "AGENT_STORE_RESPONSES": "false",
                            "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "false",
                            "ENABLE_SENSITIVE_DATA": "false",
                            "AZURE_TRACING_GEN_AI_CONTENT_RECORDING_ENABLED": "false",
                            "APPLICATIONINSIGHTS_AUTH_MODE": "entra",
                            "APPLICATIONINSIGHTS_STATSBEAT_DISABLED_ALL": "true",
                            "DEMO_TEMPLATE_ID": document["template_id"],
                        },
                        protocol_versions=[ProtocolVersionRecord(protocol="responses", version="2.0.0")],
                    ),
                    code=code, code_zip_sha256=digest,
                )
            self.verify_version(document, created)
            await progress("provisioning", version=str(created.version))
            await self.finish(client, document, progress)

    async def resume(self, document, progress):
        if not document["publication_started"]:
            await self.create(document, progress)
            return
        async with self.client() as client:
            try:
                await self.finish(client, document, progress)
            except ResourceNotFoundError as problem:
                raise PublicationError("publication_unconfirmed") from problem

    async def delete(self, document, progress):
        if not document["publication_started"]:
            await progress("deleted", status="deleted", error=None)
            return
        async with self.client() as client:
            try:
                await client.agents.get(agent_name=document["runtime_name"])
            except ResourceNotFoundError:
                if document["version"] is None:
                    raise PublicationError("deletion_unconfirmed")
                await progress("deleted", status="deleted", error=None)
                return
            version = await self.only_owned_version(client, document)
            await progress("deleting", version=str(version.version))
            await client.agents.delete(agent_name=document["runtime_name"], force=True)
            while True:
                try:
                    await client.agents.get(agent_name=document["runtime_name"])
                except ResourceNotFoundError:
                    await progress("deleted", status="deleted", error=None)
                    return
                await asyncio.sleep(self.poll_seconds)

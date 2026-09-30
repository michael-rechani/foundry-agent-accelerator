from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
import stat
import tempfile
import time
from copy import deepcopy
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

if TYPE_CHECKING:
    from azure.ai.projects import AIProjectClient

SOURCE_FILES = ("main.py", "requirements.txt")
OPTIONAL_SOURCE_FILES = ("instructions.md", "configuration.py")
REVIEW_SAMPLES = {"application-review-agent", "case-review-agent", "review-coordinator-agent"}


@dataclass(frozen=True)
class AgentProfile:
    source_directory: Path
    name: str
    description: str
    instructions: str
    smoke_test_prompt: str
    delegation_checks: tuple[tuple[str, str] | tuple[str, str, str], ...] = ()
    environment_variables: tuple[tuple[str, str], ...] = ()
    code_archive: bytes | None = None


def positive_number(value: str) -> str:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("value must be greater than zero")
    return value


def parse_args(profile: AgentProfile, argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Package and deploy a Foundry hosted-agent version.",
        allow_abbrev=False,
    )
    parser.add_argument(
        "--endpoint",
        default=os.getenv("FOUNDRY_PROJECT_ENDPOINT"),
        required=os.getenv("FOUNDRY_PROJECT_ENDPOINT") is None,
        help="Foundry project endpoint (or FOUNDRY_PROJECT_ENDPOINT).",
    )
    parser.add_argument(
        "--model",
        default=os.getenv("FOUNDRY_MODEL_NAME"),
        required=os.getenv("FOUNDRY_MODEL_NAME") is None,
        help="Foundry model deployment name (or FOUNDRY_MODEL_NAME).",
    )
    parser.add_argument(
        "--agent-name",
        default=os.getenv("FOUNDRY_HOSTED_AGENT_NAME", profile.name),
    )
    parser.add_argument("--cpu", type=positive_number, default="0.5")
    parser.add_argument("--memory", default="1Gi")
    parser.add_argument("--runtime", default="python_3_14")
    parser.add_argument("--instructions", default=profile.instructions)
    parser.add_argument(
        "--smoke-test-prompt",
        default=profile.smoke_test_prompt,
        help="Prompt sent after routing the new version (empty to skip).",
    )
    parser.add_argument("--poll-seconds", type=int, default=10)
    parser.add_argument("--max-polls", type=int, default=60)
    args = parser.parse_args(argv)

    if args.poll_seconds <= 0 or args.max_polls <= 0:
        parser.error("--poll-seconds and --max-polls must be greater than zero")

    supported_allocations = {"0.5": "1Gi", "1": "2Gi", "2": "4Gi"}
    if supported_allocations.get(args.cpu) != args.memory:
        parser.error(
            "unsupported allocation; use --cpu/--memory as 0.5/1Gi, "
            "1/2Gi, or 2/4Gi"
        )

    return args


def zip_entry(archive: ZipFile, name: str, content: bytes) -> None:
    info = ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
    info.compress_type = ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | 0o644) << 16
    archive.writestr(info, content)


def create_package(source_directory: Path, destination: Path) -> None:
    missing = [name for name in SOURCE_FILES if not (source_directory / name).is_file()]
    if missing:
        raise FileNotFoundError(f"Missing agent source files: {', '.join(missing)}")

    with ZipFile(destination, "w", compression=ZIP_DEFLATED) as archive:
        for name in (*SOURCE_FILES, *OPTIONAL_SOURCE_FILES):
            source = source_directory / name
            if source.is_file():
                zip_entry(archive, name, source.read_bytes())
        if source_directory.name in REVIEW_SAMPLES:
            zip_entry(archive, "review_output.py", (Path(__file__).parent / "review_output.py").read_bytes())


KNOWLEDGE_CHECK_PROMPT = (
    'Call search_policy_guidance exactly once with the query "missing evidence", '
    "then summarize in your own words what it returned and cite each source_id. "
    "Do not use quotation marks. Do not make an eligibility decision."
)


def knowledge_package(source_directory: Path) -> bytes:
    shared = Path(__file__).resolve().parent
    extra = source_directory / "requirements-knowledge.txt"
    if not extra.is_file():
        raise FileNotFoundError("Knowledge retrieval requires requirements-knowledge.txt")
    requirements = [
        line.strip()
        for source in (source_directory / "requirements.txt", extra)
        for line in source.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    files = {
        "main.py": (shared / "knowledge_main.py").read_bytes(),
        "requirements.txt": ("\n".join(requirements) + "\n").encode("utf-8"),
        "knowledge_retrieval.py": (shared / "knowledge_retrieval.py").read_bytes(),
        "review_output.py": (shared / "review_output.py").read_bytes(),
    }
    if (source_directory / "instructions.md").is_file():
        files["instructions.md"] = (source_directory / "instructions.md").read_bytes()
    output = io.BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for name, content in files.items():
            zip_entry(archive, name, content)
    return output.getvalue()


def with_knowledge_retrieval(profile: AgentProfile, environ=None) -> AgentProfile:
    """Return the profile unchanged unless KNOWLEDGE_RETRIEVAL_ENABLED is exactly true."""
    from knowledge_retrieval import TOOL_NAME, read_settings

    settings = read_settings(os.environ if environ is None else environ)
    if settings is None:
        return profile
    if profile.code_archive is not None:
        raise ValueError("Knowledge retrieval applies only to repository source profiles")
    return replace(
        profile,
        code_archive=knowledge_package(profile.source_directory),
        environment_variables=(*profile.environment_variables, *settings.environment()),
        delegation_checks=(*profile.delegation_checks, (KNOWLEDGE_CHECK_PROMPT, TOOL_NAME)),
    )


def wait_until_active(
    client: AIProjectClient,
    agent_name: str,
    version: str,
    poll_seconds: int,
    max_polls: int,
) -> None:
    for attempt in range(1, max_polls + 1):
        details = client.agents.get_version(
            agent_name=agent_name,
            agent_version=version,
        )
        status = details["status"]
        print(f"Version {version}: {status} ({attempt}/{max_polls})")

        if status == "active":
            return
        if status == "failed":
            raise RuntimeError(f"Agent version provisioning failed: {dict(details)}")
        time.sleep(poll_seconds)

    raise TimeoutError(f"Agent version {version} did not become active")


def verify_delegation(response, expected_tool: str, expected_agent: str | None = None) -> None:
    items = response.model_dump().get("output", [])
    calls = [item for item in items if item.get("type") == "function_call"]
    if len(calls) != 1 or calls[0].get("name") != expected_tool or not calls[0].get("call_id"):
        raise RuntimeError(f"Expected exactly one {expected_tool} tool call")
    results = [
        item for item in items
        if item.get("type") == "function_call_output"
        and item.get("call_id") == calls[0]["call_id"]
    ]
    if len(results) != 1:
        raise RuntimeError("Missing matching specialist result")
    try:
        result = json.loads(results[0].get("output", ""))
    except (ValueError, TypeError) as error:
        raise RuntimeError("Specialist result is not a success receipt") from error
    if (
        not isinstance(result, dict)
        or result.get("status") != "succeeded"
        or not isinstance(result.get("agent"), str)
        or not result["agent"].strip()
        or not isinstance(result.get("output"), str)
        or not result["output"].strip()
    ):
        raise RuntimeError("Specialist result is not a success receipt")
    # A lookup that matched nothing is an honest success receipt, but it proves nothing about the index.
    if result.get("retrieval") is True:
        source_ids = result.get("source_ids")
        if (
            not isinstance(source_ids, list)
            or not source_ids
            or not all(isinstance(source_id, str) and source_id.strip() for source_id in source_ids)
        ):
            raise RuntimeError("Retrieval result returned no passages")

    if expected_agent is not None and result["agent"] != expected_agent:
        raise RuntimeError("Specialist result came from an unexpected agent")


def smoke_test(
    client: AIProjectClient, agent_name: str, prompt: str, expected_tool: str | None = None,
    expected_agent: str | None = None,
) -> None:
    if not prompt:
        print("Skipped hosted-agent smoke test")
        return

    with client.get_openai_client(agent_name=agent_name, timeout=180, max_retries=0) as openai_client:
        response = openai_client.responses.create(input=prompt, store=False)

    if response.status != "completed" or not response.output_text.strip():
        raise RuntimeError("Hosted-agent smoke test did not return a completed, nonempty response")
    if expected_tool:
        verify_delegation(response, expected_tool, expected_agent)
    print(f"Smoke test passed: {expected_tool or agent_name}")


def concrete_route(endpoint) -> bool:
    selector = getattr(endpoint, "version_selector", None)
    rules = getattr(selector, "version_selection_rules", None)
    return isinstance(rules, list) and bool(rules) and all(
        isinstance(getattr(rule, "agent_version", None), str)
        and rule.agent_version
        and not rule.agent_version.startswith("@")
        for rule in rules
    )


def endpoint_snapshot(client, agent_name: str):
    from azure.core.exceptions import ResourceNotFoundError

    try:
        endpoint = client.agents.get(agent_name=agent_name).agent_endpoint
    except ResourceNotFoundError:
        return None
    if not concrete_route(endpoint):
        raise RuntimeError(
            "Pin the existing agent route to explicit versions before redeploying; "
            "an unrouted or symbolic route such as @latest is not a safe recovery target"
        )
    return deepcopy(endpoint)


def verify_route(client, agent_name: str, version: str) -> None:
    endpoint = client.agents.get(agent_name=agent_name).agent_endpoint
    rules = getattr(getattr(endpoint, "version_selector", None), "version_selection_rules", None)
    if (
        getattr(getattr(endpoint, "protocol_configuration", None), "responses", None) is None
        or not isinstance(rules, list)
        or len(rules) != 1
        or str(rules[0].agent_version) != str(version)
        or type(rules[0].traffic_percentage) not in (int, float)
        or rules[0].traffic_percentage != 100
    ):
        raise RuntimeError("The promoted Responses route was not confirmed")
    details = client.agents.get_version(agent_name=agent_name, agent_version=version)
    if details["status"] != "active" or getattr(details, "draft", False):
        raise RuntimeError("The promoted agent version is not active")


def cleanup_failed_version(
    client, agent_name: str, version: str, original_endpoint, promotion_attempted: bool
) -> None:
    if promotion_attempted and original_endpoint is not None:
        if not concrete_route(original_endpoint):
            print(f"Warning: recovery route is not concrete; retained version {version}")
            return
        try:
            client.agents.update_details(
                agent_name=agent_name, agent_endpoint=original_endpoint
            )
        except Exception:
            print(f"Warning: rollback failed; retained version {version}")
            return

    try:
        endpoint = client.agents.get(agent_name=agent_name).agent_endpoint
        selector = getattr(endpoint, "version_selector", None)
        rules = getattr(selector, "version_selection_rules", None)
        if not concrete_route(endpoint) or any(str(rule.agent_version) == str(version) for rule in rules):
            print(f"Warning: route not confirmed safe; retained version {version}")
            return
        client.agents.delete_version(
            agent_name=agent_name, agent_version=version, force=True
        )
        print(f"Deleted failed version {version}")
    except Exception:
        print(f"Warning: cleanup incomplete; retained version {version} if present")


def verify_specialist_endpoints(client, profile: AgentProfile, coordinator_name: str) -> None:
    agent_names = sorted({check[2] for check in profile.delegation_checks if len(check) == 3})
    for agent_name in agent_names:
        if agent_name == coordinator_name:
            raise ValueError("A coordinator cannot delegate to its own endpoint")
        endpoint = client.agents.get(agent_name=agent_name).agent_endpoint
        protocols = getattr(endpoint, "protocol_configuration", None)
        selector = getattr(endpoint, "version_selector", None)
        rules = getattr(selector, "version_selection_rules", None)
        if getattr(protocols, "responses", None) is None or not rules:
            raise RuntimeError(f"Specialist {agent_name} has no routed Responses endpoint")
        percentages = [getattr(rule, "traffic_percentage", None) for rule in rules]
        if any(type(value) not in (int, float) or not 0 <= value <= 100 for value in percentages):
            raise RuntimeError(f"Specialist {agent_name} has unsupported traffic rules")
        if not math.isclose(sum(percentages), 100):
            raise RuntimeError(f"Specialist {agent_name} traffic must total 100 percent")
        versions = {str(rule.agent_version) for rule in rules if rule.traffic_percentage > 0 and rule.agent_version}
        if any(not rule.agent_version for rule in rules if rule.traffic_percentage > 0):
            raise RuntimeError(f"Specialist {agent_name} has an unversioned traffic rule")
        for version in sorted(versions):
            details = client.agents.get_version(agent_name=agent_name, agent_version=version)
            if details["status"] != "active":
                raise RuntimeError(f"Specialist {agent_name} version {version} is not active")
        print(f"Specialist preflight passed: {agent_name}")


def report_agent_identity(created) -> None:
    principal = getattr(getattr(created, "instance_identity", None), "principal_id", None)
    if principal:
        print(f"Agent identity principal ID: {principal}")
    else:
        print("No agent instance identity was reported; a legacy agent uses the shared project identity")


def deploy(profile: AgentProfile, args: argparse.Namespace) -> None:
    from azure.ai.projects import AIProjectClient
    from azure.ai.projects.models import (
        AgentEndpointConfig,
        CodeConfiguration,
        CodeDependencyResolution,
        FixedRatioVersionSelectionRule,
        HostedAgentDefinition,
        ProtocolConfiguration,
        ProtocolVersionRecord,
        ResponsesProtocolConfiguration,
        VersionSelector,
    )
    from azure.identity import DefaultAzureCredential

    with tempfile.TemporaryDirectory(prefix="foundry-agent-") as temporary:
        package_path = Path(temporary) / "agent.zip"
        if profile.code_archive is None:
            create_package(profile.source_directory, package_path)
        else:
            package_path.write_bytes(profile.code_archive)
        digest = hashlib.sha256(package_path.read_bytes()).hexdigest()

        with (
            package_path.open("rb") as package,
            DefaultAzureCredential() as credential,
            AIProjectClient(endpoint=args.endpoint, credential=credential, allow_preview=True) as client,
        ):
            verify_specialist_endpoints(client, profile, args.agent_name)
            client.deployments.get(name=args.model)
            original_endpoint = endpoint_snapshot(client, args.agent_name)
            created = client.agents.create_version_from_code(
                agent_name=args.agent_name,
                description=profile.description,
                metadata={"source_sha256": digest},
                definition=HostedAgentDefinition(
                    cpu=args.cpu,
                    memory=args.memory,
                    code_configuration=CodeConfiguration(
                        runtime=args.runtime,
                        entry_point=["python", "main.py"],
                        dependency_resolution=CodeDependencyResolution.REMOTE_BUILD,
                    ),
                    environment_variables={
                        **dict(profile.environment_variables),
                        "FOUNDRY_PROJECT_ENDPOINT": args.endpoint,
                        "FOUNDRY_MODEL_NAME": args.model,
                        "AGENT_NAME": args.agent_name,
                        "AGENT_INSTRUCTIONS": args.instructions,
                        "AGENT_STORE_RESPONSES": "false",
                        "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "false",
                        "ENABLE_SENSITIVE_DATA": "false",
                        "AZURE_TRACING_GEN_AI_CONTENT_RECORDING_ENABLED": "false",
                        "APPLICATIONINSIGHTS_AUTH_MODE": "entra",
                        "APPLICATIONINSIGHTS_STATSBEAT_DISABLED_ALL": "true",
                    },
                    protocol_versions=[
                        ProtocolVersionRecord(protocol="responses", version="2.0.0")
                    ],
                ),
                code=package,
                code_zip_sha256=digest,
            )
            print(f"Created {args.agent_name} version {created.version}")
            report_agent_identity(created)

            promotion_attempted = False
            try:
                wait_until_active(
                    client,
                    args.agent_name,
                    created.version,
                    args.poll_seconds,
                    args.max_polls,
                )
                current_endpoint = client.agents.get(
                    agent_name=args.agent_name,
                ).agent_endpoint
                if original_endpoint is not None and current_endpoint != original_endpoint:
                    raise RuntimeError("The agent route changed during deployment; refusing promotion")
                protocols = deepcopy(getattr(current_endpoint, "protocol_configuration", None))
                if protocols is None:
                    protocols = ProtocolConfiguration()
                protocols.responses = ResponsesProtocolConfiguration()
                endpoint_config = AgentEndpointConfig(
                    version_selector=VersionSelector(
                        version_selection_rules=[
                            FixedRatioVersionSelectionRule(
                                agent_version=created.version,
                                traffic_percentage=100,
                            )
                        ]
                    ),
                    protocol_configuration=protocols,
                )
                authorization = getattr(current_endpoint, "authorization_schemes", None)
                if authorization is not None:
                    endpoint_config.authorization_schemes = deepcopy(authorization)
                promotion_attempted = True
                client.agents.update_details(
                    agent_name=args.agent_name,
                    agent_endpoint=endpoint_config,
                )
                verify_route(client, args.agent_name, created.version)
                smoke_test(client, args.agent_name, args.smoke_test_prompt)
                for check in profile.delegation_checks:
                    smoke_test(client, args.agent_name, *check)
                verify_route(client, args.agent_name, created.version)
            except (Exception, KeyboardInterrupt):
                cleanup_failed_version(
                    client, args.agent_name, created.version,
                    original_endpoint, promotion_attempted,
                )
                raise

            print(
                f"Promoted {args.agent_name} version {created.version} "
                "to 100% of endpoint traffic"
            )


def run(profile: AgentProfile, argv=None) -> None:
    deploy(profile, parse_args(profile, argv))
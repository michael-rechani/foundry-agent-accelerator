from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
import re
import stat
import sys
import tempfile
import time
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

if TYPE_CHECKING:
    from azure.ai.projects import AIProjectClient

SOURCE_FILES = ("main.py", "requirements.txt")
OPTIONAL_SOURCE_FILES = ("instructions.md", "configuration.py")
# Every prebuilt hosted agent under hosted-agents/ (a folder with a main.py), and whether its main.py imports
# SHARED_FILES. bundle.py takes its --sample choices from here, and test_prebuilt_agents.py checks that
# validate.yml and dependabot.yml name each one, so a new agent is added here and in those two files.
PREBUILT_AGENTS = {
    "basic-responses-agent": False,
    "application-review-agent": True,
    "case-review-agent": True,
    "review-coordinator-agent": True,
}
SAMPLES = tuple(PREBUILT_AGENTS)
REVIEW_SAMPLES = frozenset(name for name, uses_shared_files in PREBUILT_AGENTS.items() if uses_shared_files)
# Files beside deployment.py that a review sample's main.py imports, so they ship inside its package.
SHARED_FILES = ("review_output.py", "hosted_runtime.py")
# The same choices as evaluations/run.py. A version create is not safe to replay, so a stalled
# call fails in about 90 seconds and the rollback below runs, instead of retrying with SDK defaults.
FOUNDRY_CLIENT_OPTIONS = {"allow_preview": True, "retry_total": 0, "connection_timeout": 30, "read_timeout": 60}


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
        help="Optional prompt for candidate and post-promotion smoke tests (empty to skip).",
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
            for name in SHARED_FILES:
                zip_entry(archive, name, (Path(__file__).parent / name).read_bytes())


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
        **{name: (shared / name).read_bytes() for name in SHARED_FILES},
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
) -> Mapping[str, object]:
    if not concrete_version(version):
        raise RuntimeError("The candidate version must be explicit")
    for attempt in range(1, max_polls + 1):
        details = client.agents.get_version(
            agent_name=agent_name,
            agent_version=version,
        )
        if not version_identity_matches(details, agent_name, version):
            raise RuntimeError("The polled agent version identity was not confirmed")
        status = details["status"]
        print(f"Version {version}: {status} ({attempt}/{max_polls})")

        if status == "active":
            return details
        if status == "failed":
            raise RuntimeError("Agent version provisioning failed")
        time.sleep(poll_seconds)

    raise TimeoutError(f"Agent version {version} did not become active")


# Fixed words only; the reply text itself is never printed.
RETRIEVED_CLAIM = re.compile(r"\b(?:retriev\w*|searched|looked up)\b", re.IGNORECASE)


class NoToolCall(RuntimeError):
    """The response made no tool call, so the model skipped the tool rather than misusing it."""


def verify_delegation(response, expected_tool: str, expected_agent: str | None = None) -> None:
    items = response.model_dump().get("output", [])
    calls = [item for item in items if item.get("type") == "function_call"]
    if not calls:
        raise NoToolCall(f"Expected exactly one {expected_tool} tool call")
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
    expected_agent: str | None = None, *, agent_session_id: str | None = None,
) -> None:
    if not prompt:
        print("Skipped hosted-agent smoke test")
        return

    from knowledge_retrieval import TOOL_NAME

    # The lookup is optional for the model, so a skipped call gets one more try. Nothing else is retried.
    attempts = 2 if expected_tool == TOOL_NAME else 1
    for attempt in range(1, attempts + 1):
        with client.get_openai_client(agent_name=agent_name, timeout=180, max_retries=0) as openai_client:
            kwargs = {"input": prompt, "store": False}
            if agent_session_id is not None:
                kwargs["extra_body"] = {"agent_session_id": agent_session_id}
            response = openai_client.responses.create(**kwargs)

        if response.status != "completed" or not response.output_text.strip():
            raise RuntimeError("Hosted-agent smoke test did not return a completed, nonempty response")
        try:
            if expected_tool:
                verify_delegation(response, expected_tool, expected_agent)
            break
        except NoToolCall:
            if attempts > 1:
                print(f"Attempt {attempt} of {attempts} made no {expected_tool} call"
                      + ("; retrying once" if attempt < attempts else ""))
                if RETRIEVED_CLAIM.search(response.output_text):
                    print(f"Attempt {attempt}'s reply claims guidance was retrieved although no lookup ran")
            if attempt == attempts:
                raise
    print(f"Smoke test passed: {expected_tool or agent_name}")


def candidate_smoke_test(
    client, agent_name: str, version: str, prompt: str, checks, *, poll_seconds: int = 1, max_polls: int = 60,
) -> None:
    from azure.ai.projects.models import VersionRefIndicator

    if not concrete_version(version):
        raise RuntimeError("The candidate version must be explicit")
    if not prompt and not checks:
        raise RuntimeError("An existing agent requires a candidate smoke check")
    session = client.agents.create_session(
        agent_name=agent_name, version_indicator=VersionRefIndicator(agent_version=version),
    )
    session_id = getattr(session, "agent_session_id", None)
    if not isinstance(session_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", session_id):
        raise RuntimeError("Candidate session has no safe ID; cleanup could not be confirmed")
    try:
        for attempt in range(max_polls):
            indicator = getattr(session, "version_indicator", None)
            if (getattr(session, "agent_session_id", None) != session_id
                    or getattr(indicator, "type", None) != "version_ref"
                    or getattr(indicator, "agent_version", None) != version):
                raise RuntimeError("Candidate session binding or status was not confirmed")
            status = getattr(session, "status", None)
            if status in ("active", "idle"):
                break
            if status not in ("creating", "updating"):
                raise RuntimeError("Candidate session binding or status was not confirmed")
            if attempt + 1 == max_polls:
                raise TimeoutError("Candidate session did not become ready")
            time.sleep(poll_seconds)
            session = client.agents.get_session(agent_name=agent_name, session_id=session_id)
        else:
            raise RuntimeError("Candidate session polling limit is invalid")
        smoke_test(client, agent_name, prompt, agent_session_id=session_id)
        for check in checks:
            smoke_test(client, agent_name, *check, agent_session_id=session_id)
    finally:
        primary_failure = sys.exc_info()[0] is not None
        try:
            client.agents.delete_session(agent_name=agent_name, session_id=session_id)
        except BaseException:
            if not primary_failure:
                raise
            print("Warning: candidate session cleanup failed; manual inspection is required")


def concrete_version(version) -> bool:
    return isinstance(version, str) and bool(version) and version == version.strip() and not version.startswith("@")


def concrete_route(endpoint) -> bool:
    selector = getattr(endpoint, "version_selector", None)
    rules = getattr(selector, "version_selection_rules", None)
    return isinstance(rules, list) and bool(rules) and all(
        concrete_version(getattr(rule, "agent_version", None)) for rule in rules
    )


def validate_traffic_rules(rules, description: str) -> None:
    percentages = [getattr(rule, "traffic_percentage", None) for rule in rules]
    if any(type(value) not in (int, float) or not 0 <= value <= 100 for value in percentages):
        raise RuntimeError(f"{description} has unsupported traffic rules")
    if not math.isclose(sum(percentages), 100):
        raise RuntimeError(f"{description} traffic must total 100 percent")


def version_identity_matches(details, agent_name: str, version: str) -> bool:
    return (
        isinstance(details, Mapping)
        and concrete_version(version)
        and isinstance(details.get("name"), str)
        and details.get("name") == agent_name
        and isinstance(details.get("version"), str)
        and details.get("version") == version
    )


def active_release(details, agent_name: str, version: str) -> bool:
    return (
        version_identity_matches(details, agent_name, version)
        and details.get("status") == "active"
        and details.get("draft", False) is False
    )


def candidate_model_matches(details, model: str) -> bool:
    if not isinstance(details, Mapping) or not isinstance(model, str) or not model:
        return False
    definition = details.get("definition")
    if not isinstance(definition, Mapping) or definition.get("kind") != "hosted":
        return False
    environment = definition.get("environment_variables")
    return (
        isinstance(environment, Mapping)
        and isinstance(environment.get("FOUNDRY_MODEL_NAME"), str)
        and environment.get("FOUNDRY_MODEL_NAME") == model
    )

def has_responses(endpoint) -> bool:
    protocols = getattr(endpoint, "protocol_configuration", None)
    return isinstance(getattr(protocols, "responses", None), Mapping)


def enabled_endpoint(client, agent_name: str):
    details = client.agents.get(agent_name=agent_name)
    for field in ("state", "configuration_state"):
        # SDK 2.6.1 preserves the unmodeled configuration_state wire field in its mapping.
        value = details.get(field) if isinstance(details, Mapping) else getattr(details, field, None)
        if not isinstance(value, str) or value != "enabled":
            raise RuntimeError("Agent operational and administrative states must both be explicitly enabled")
    return getattr(details, "agent_endpoint", None)


def verify_recovery_targets(client, agent_name: str, endpoint) -> None:
    if not concrete_route(endpoint):
        raise RuntimeError(
            "Pin the existing agent route to explicit versions before redeploying; "
            "an unrouted or symbolic route such as @latest is not a safe recovery target"
        )
    if not has_responses(endpoint):
        raise RuntimeError("Recovery route has no Responses endpoint")
    enabled_endpoint(client, agent_name)
    rules = endpoint.version_selector.version_selection_rules
    validate_traffic_rules(rules, "Recovery route")
    versions = {rule.agent_version for rule in rules if rule.traffic_percentage > 0}
    for version in sorted(versions):
        details = client.agents.get_version(agent_name=agent_name, agent_version=version)
        if not active_release(details, agent_name, version):
            raise RuntimeError(f"Recovery version {version} is not an active release")


def endpoint_snapshot(client, agent_name: str):
    from azure.core.exceptions import ResourceNotFoundError

    try:
        endpoint = deepcopy(enabled_endpoint(client, agent_name))
    except ResourceNotFoundError:
        return None
    verify_recovery_targets(client, agent_name, endpoint)
    if enabled_endpoint(client, agent_name) != endpoint:
        raise RuntimeError("The recovery route changed before version creation")
    return deepcopy(endpoint)


def routes_to_version(endpoint, version: str) -> bool:
    rules = getattr(getattr(endpoint, "version_selector", None), "version_selection_rules", None)
    return (
        has_responses(endpoint)
        and isinstance(rules, list)
        and len(rules) == 1
        and concrete_version(version)
        and getattr(rules[0], "agent_version", None) == version
        and type(getattr(rules[0], "traffic_percentage", None)) in (int, float)
        and rules[0].traffic_percentage == 100
    )


def verify_route(client, agent_name: str, version: str, model: str) -> None:
    endpoint = deepcopy(enabled_endpoint(client, agent_name))
    if not routes_to_version(endpoint, version):
        raise RuntimeError("The promoted Responses route was not confirmed")
    details = client.agents.get_version(agent_name=agent_name, agent_version=version)
    if not active_release(details, agent_name, version):
        raise RuntimeError("The promoted agent version is not active")
    if not candidate_model_matches(details, model):
        raise RuntimeError("The promoted hosted definition does not confirm the requested model")
    if enabled_endpoint(client, agent_name) != endpoint:
        raise RuntimeError("The promoted Responses route changed during verification")


def recovery_endpoint(original_endpoint):
    endpoint = deepcopy(original_endpoint)
    protocols = getattr(endpoint, "protocol_configuration", None)
    # Foundry uses merge-patch, so omitted protocol fields would survive the rollback.
    if protocols is None:
        endpoint["protocol_configuration"] = None
    elif getattr(protocols, "responses", None) is None:
        protocols["responses"] = None
    return endpoint


def cleanup_failed_version(
    client, agent_name: str, version: str, original_endpoint, attempted_endpoint
) -> None:
    if not concrete_route(original_endpoint) or (
        attempted_endpoint is not None and not routes_to_version(attempted_endpoint, version)
    ):
        print(f"Warning: recovery route is not confirmed; retained version {version}; manual recovery required")
        return

    try:
        endpoint = deepcopy(enabled_endpoint(client, agent_name))
        if endpoint != original_endpoint and (attempted_endpoint is None or endpoint != attempted_endpoint):
            print(f"Warning: route changed during deployment; retained version {version}; manual recovery required")
            return
        verify_recovery_targets(client, agent_name, original_endpoint)
        if endpoint != original_endpoint:
            if enabled_endpoint(client, agent_name) != endpoint:
                print(f"Warning: route changed during recovery; retained version {version}; manual recovery required")
                return
            try:
                client.agents.update_details(
                    agent_name=agent_name, agent_endpoint=recovery_endpoint(original_endpoint)
                )
            except Exception:
                print(f"Warning: rollback failed; retained version {version}; manual recovery required")
                return
            endpoint = enabled_endpoint(client, agent_name)
            if endpoint != original_endpoint:
                print(f"Warning: restored route was not confirmed; retained version {version}; manual recovery required")
                return
            verify_recovery_targets(client, agent_name, endpoint)
        endpoint = enabled_endpoint(client, agent_name)
        if endpoint != original_endpoint:
            print(f"Warning: route changed during cleanup; retained version {version}; manual recovery required")
            return
        selector = getattr(endpoint, "version_selector", None)
        rules = getattr(selector, "version_selection_rules", None)
        if not concrete_route(endpoint) or any(str(rule.agent_version) == str(version) for rule in rules):
            print(f"Warning: route not confirmed safe; retained version {version}; manual recovery required")
            return
        print(f"Retained failed version {version}; inspect its sessions before deliberate cleanup")
    except Exception:
        print(f"Warning: recovery status or cleanup incomplete; retained version {version} if present; manual recovery required")


def verify_specialist_endpoints(client, profile: AgentProfile, coordinator_name: str) -> None:
    agent_names = sorted({check[2] for check in profile.delegation_checks if len(check) == 3})
    for agent_name in agent_names:
        if agent_name == coordinator_name:
            raise ValueError("A coordinator cannot delegate to its own endpoint")
        endpoint = deepcopy(enabled_endpoint(client, agent_name))
        selector = getattr(endpoint, "version_selector", None)
        rules = getattr(selector, "version_selection_rules", None)
        if not has_responses(endpoint) or not rules:
            raise RuntimeError(f"Specialist {agent_name} has no routed Responses endpoint")
        validate_traffic_rules(rules, f"Specialist {agent_name}")
        if not concrete_route(endpoint):
            raise RuntimeError(f"Specialist {agent_name} requires concrete version traffic rules")
        versions = {rule.agent_version for rule in rules if rule.traffic_percentage > 0}
        for version in sorted(versions):
            details = client.agents.get_version(agent_name=agent_name, agent_version=version)
            if not active_release(details, agent_name, version):
                raise RuntimeError(f"Specialist {agent_name} version {version} is not active")
        if enabled_endpoint(client, agent_name) != endpoint:
            raise RuntimeError(f"Specialist {agent_name} route changed during preflight")
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
            AIProjectClient(endpoint=args.endpoint, credential=credential, **FOUNDRY_CLIENT_OPTIONS) as client,
        ):
            verify_specialist_endpoints(client, profile, args.agent_name)
            client.deployments.get(name=args.model)
            original_endpoint = endpoint_snapshot(client, args.agent_name)
            if original_endpoint is None:
                raise RuntimeError(
                    "First publication is unsupported: a confirmed existing concrete recovery route is required"
                )
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

            attempted_endpoint = None
            candidate_check_in_progress = False
            try:
                candidate = wait_until_active(
                    client,
                    args.agent_name,
                    created.version,
                    args.poll_seconds,
                    args.max_polls,
                )
                if not active_release(candidate, args.agent_name, created.version):
                    raise RuntimeError("The candidate agent version is not an active release")
                if not candidate_model_matches(candidate, args.model):
                    raise RuntimeError("The candidate hosted definition does not confirm the requested model")
                if original_endpoint is not None:
                    if enabled_endpoint(client, args.agent_name) != original_endpoint:
                        raise RuntimeError("The agent route changed during deployment; refusing candidate smoke")
                    candidate_check_in_progress = True
                    candidate_smoke_test(
                        client, args.agent_name, created.version, args.smoke_test_prompt,
                        profile.delegation_checks, poll_seconds=args.poll_seconds, max_polls=args.max_polls,
                    )
                    candidate_check_in_progress = False
                current_endpoint = deepcopy(enabled_endpoint(client, args.agent_name))
                if original_endpoint is not None and current_endpoint != original_endpoint:
                    raise RuntimeError("The agent route changed during deployment; refusing promotion")
                if original_endpoint is not None:
                    verify_recovery_targets(client, args.agent_name, original_endpoint)
                verify_specialist_endpoints(client, profile, args.agent_name)
                protocols = deepcopy(getattr(current_endpoint, "protocol_configuration", None))
                if protocols is None:
                    protocols = ProtocolConfiguration()
                if getattr(protocols, "responses", None) is None:
                    protocols.responses = ResponsesProtocolConfiguration()
                endpoint_config = (
                    deepcopy(current_endpoint) if current_endpoint is not None else AgentEndpointConfig()
                )
                selector = getattr(endpoint_config, "version_selector", None)
                if selector is None:
                    selector = VersionSelector()
                selector.version_selection_rules = [
                    FixedRatioVersionSelectionRule(
                        agent_version=created.version,
                        traffic_percentage=100,
                    )
                ]
                endpoint_config.version_selector = selector
                endpoint_config.protocol_configuration = protocols
                if original_endpoint is not None:
                    verify_recovery_targets(client, args.agent_name, original_endpoint)
                candidate = client.agents.get_version(agent_name=args.agent_name, agent_version=created.version)
                if not active_release(candidate, args.agent_name, created.version):
                    raise RuntimeError("The candidate agent version is not active")
                if not candidate_model_matches(candidate, args.model):
                    raise RuntimeError("The candidate hosted definition does not confirm the requested model")
                if enabled_endpoint(client, args.agent_name) != current_endpoint:
                    raise RuntimeError("The agent route changed during deployment; refusing promotion")
                attempted_endpoint = deepcopy(endpoint_config)
                client.agents.update_details(
                    agent_name=args.agent_name,
                    agent_endpoint=endpoint_config,
                )
                verify_route(client, args.agent_name, created.version, args.model)
                smoke_test(client, args.agent_name, args.smoke_test_prompt)
                for check in profile.delegation_checks:
                    smoke_test(client, args.agent_name, *check)
                verify_route(client, args.agent_name, created.version, args.model)
            except (Exception, KeyboardInterrupt):
                if candidate_check_in_progress:
                    print(f"Warning: candidate check did not finish; retained version {created.version}")
                else:
                    cleanup_failed_version(
                        client, args.agent_name, created.version,
                        original_endpoint, attempted_endpoint,
                    )
                raise

            print(
                f"Promoted {args.agent_name} version {created.version} "
                "to 100% of endpoint traffic"
            )


def run(profile: AgentProfile, argv=None) -> None:
    deploy(profile, parse_args(profile, argv))

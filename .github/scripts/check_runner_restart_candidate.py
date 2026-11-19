"""Offline evidence checks only. No entry point, API calls, or authorization."""

import hashlib
import re
from collections.abc import Mapping

REPOSITORY = "michael-rechani/foundry-agent-accelerator"
WORKFLOW_REF = f"{REPOSITORY}/.github/workflows/start-private-runner-reviewed.yml@refs/heads/main"
UUID = r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}"
VM_UUID = re.compile(UUID, re.IGNORECASE | re.ASCII)
VM_ID = re.compile(
    rf"/subscriptions/{UUID}/resourcegroups/[a-z0-9_-][a-z0-9_.-]{{0,89}}"
    r"/providers/microsoft\.compute/virtualmachines/[a-z0-9][a-z0-9_-]{0,63}",
    re.IGNORECASE | re.ASCII,
)


def check_source(
    context: Mapping[str, object],
    reviewed_main_sha: str,
    main_snapshot: object,
) -> None:
    """Compare fixture or trusted observations; this does not verify their provenance."""
    for key, expected in {
        "repository": REPOSITORY,
        "repository_owner": "michael-rechani",
        "actor_id": "97264614",
        "workflow_ref": WORKFLOW_REF,
        "ref": "refs/heads/main",
        "event_name": "workflow_dispatch",
        "run_number": "1",
        "run_attempt": "1",
    }.items():
        if context.get(key) != expected:
            raise ValueError(f"Unexpected run context: {key}")

    if not re.fullmatch(r"[0-9a-f]{40}", reviewed_main_sha) or any(
        context.get(key) != reviewed_main_sha for key in ("sha", "workflow_sha")
    ):
        raise ValueError("Run and workflow must match the reviewed main commit")

    if (
        not isinstance(main_snapshot, dict)
        or main_snapshot.get("name") != "main"
        or main_snapshot.get("protected") is not True
        or not isinstance(commit := main_snapshot.get("commit"), dict)
        or commit.get("sha") != reviewed_main_sha
    ):
        raise ValueError("Protected main snapshot does not match the reviewed commit")


def _check_fingerprint(value: str, pattern: re.Pattern[str], reviewed: str) -> None:
    if not pattern.fullmatch(value) or not re.fullmatch(r"[0-9a-f]{64}", reviewed):
        raise ValueError("Malformed VM identity or fingerprint")
    if hashlib.sha256(value.lower().encode("ascii")).hexdigest() != reviewed:
        raise ValueError("VM identity does not match the reviewed fingerprint")


def check_configured_vm(configured_id: str, reviewed_arm_sha256: str) -> None:
    """Bind the configured target before any future credential request."""
    _check_fingerprint(configured_id, VM_ID, reviewed_arm_sha256)


def check_observed_vm(
    configured_id: str,
    observed_id: str,
    observed_vm_uuid: str,
    reviewed_arm_sha256: str,
    reviewed_uuid_sha256: str,
) -> None:
    """Require the exact ARM path and VM instance, including after replacement at the same path."""
    check_configured_vm(configured_id, reviewed_arm_sha256)
    if not VM_ID.fullmatch(observed_id) or observed_id.lower() != configured_id.lower():
        raise ValueError("Observed ARM ID differs from the reviewed target")
    _check_fingerprint(observed_vm_uuid, VM_UUID, reviewed_uuid_sha256)


def classify_power_state(states: object) -> str:
    """Model the only allowed start decision; never recycle a running or starting VM."""
    if not isinstance(states, list) or len(states) != 1:
        raise ValueError("Expected exactly one VM power state")
    state = states[0]
    if state in ("PowerState/stopped", "PowerState/deallocated"):
        return "start"
    if state in ("PowerState/running", "PowerState/starting"):
        return "observe"
    raise ValueError("VM power state is unsafe")

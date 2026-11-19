"""Read-only, non-wired Lab image approval evidence verifier.

This module never performs a deployment. The strict mode requires an explicit,
complete empty environment-secret inventory. An opt-in no-reference mode is
disabled by default and requires separate owner acceptance; it reports the
inventory as unverified. Neither mode provides durable single-use semantics.
"""

from __future__ import annotations

import http.client
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, urlsplit

from check_state_backend import CheckError

API_HOST = "api.github.com"
API_VERSION = "2022-11-28"
MAX_RESPONSE_BYTES = 256 * 1024
SHA = re.compile(r"[0-9a-f]{40}")
IMAGE = re.compile(r"[A-Za-z0-9][A-Za-z0-9.-]*/workbench@sha256:[0-9a-f]{64}")
REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
SECRET_MODES = {"require-empty", "no-secret-references"}
NO_SECRET_REFERENCE_ACCEPTANCE = "OWNER_ACCEPTS_NO_SECRET_REFERENCE_MODEL"


def _object_without_duplicate_keys(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate key")
        value[key] = item
    return value


def _invalid_constant(_):
    raise ValueError("invalid JSON constant")


def _positive_id(value):
    return type(value) is int and value > 0


def _path(value):
    if not isinstance(value, str) or not value.startswith("/") or value.startswith("//"):
        raise CheckError("GitHub API path is invalid.")
    try:
        target = urlsplit(value)
    except ValueError:
        raise CheckError("GitHub API path is invalid.") from None
    if (
        target.scheme or target.netloc or target.fragment or "\\" in target.path
        or any(part in (".", "..") for part in target.path.split("/"))
        or target.query not in ("", "per_page=1", "per_page=100")
    ):
        raise CheckError("GitHub API path is invalid.")
    return value


class GitHubReader:
    """Fetch bounded, unpaginated GitHub API JSON without logging response data."""

    def __init__(self, token, *, connection_factory=http.client.HTTPSConnection):
        if not isinstance(token, str) or not token or "\r" in token or "\n" in token:
            raise CheckError("GitHub API token is missing or invalid.")
        self._token = token
        self._connection_factory = connection_factory

    def get_json(self, path, *, kind):
        path = _path(path)
        connection = None
        try:
            connection = self._connection_factory(API_HOST, timeout=15)
            connection.request("GET", path, headers={
                "Authorization": f"Bearer {self._token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": API_VERSION,
                "User-Agent": "lab-image-approval-evidence-reader",
            })
            response = connection.getresponse()
            status = response.status
            if status != 200:
                raise CheckError(f"GitHub {kind} request returned HTTP {status}.")
            if response.headers.get_all("Link"):
                raise CheckError(f"GitHub {kind} response may be paginated.")
            lengths = response.headers.get_all("Content-Length", [])
            encodings = response.headers.get_all("Transfer-Encoding", [])
            if lengths:
                if encodings or len(lengths) != 1 or not re.fullmatch(r"[0-9]{1,9}", lengths[0]):
                    raise CheckError(f"GitHub {kind} response framing is ambiguous.")
                expected_length = int(lengths[0])
                if expected_length > MAX_RESPONSE_BYTES:
                    raise CheckError(f"GitHub {kind} response is too large.")
            elif [value.lower() for value in encodings] == ["chunked"]:
                expected_length = None
            else:
                raise CheckError(f"GitHub {kind} response completeness is unverified.")
            try:
                body = response.read(MAX_RESPONSE_BYTES + 1)
            except http.client.IncompleteRead:
                raise CheckError(f"GitHub {kind} response was truncated.") from None
            if len(body) > MAX_RESPONSE_BYTES or (
                expected_length is not None and len(body) != expected_length
            ):
                raise CheckError(f"GitHub {kind} response was truncated or too large.")
            try:
                data = json.loads(
                    body.decode("utf-8"),
                    object_pairs_hook=_object_without_duplicate_keys,
                    parse_constant=_invalid_constant,
                )
            except (UnicodeError, ValueError, RecursionError):
                raise CheckError(f"GitHub {kind} response was not valid JSON.") from None
            if kind in {"approvals"}:
                valid_root = isinstance(data, list)
            else:
                valid_root = isinstance(data, dict)
            if not valid_root:
                raise CheckError(f"GitHub {kind} response had an unexpected shape.")
            return data
        except CheckError:
            raise
        except (OSError, http.client.HTTPException):
            raise CheckError(f"GitHub {kind} request failed.") from None
        finally:
            if connection is not None:
                connection.close()


@dataclass(frozen=True)
class ApprovalExpectation:
    repository: str
    run_id: int
    attempt: int
    actor_id: int
    reviewer_id: int
    source_sha: str
    recovery_image: str
    environment: str = "lab-image-release-review"
    workflow_path: str = ".github/workflows/deploy-lab.yml"
    max_run_age: timedelta = timedelta(minutes=30)


def _nested(mapping, *keys):
    value = mapping
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _valid_expectation(expected):
    return (
        isinstance(expected, ApprovalExpectation)
        and isinstance(expected.repository, str)
        and bool(REPOSITORY.fullmatch(expected.repository))
        and all(part not in {".", ".."} for part in expected.repository.split("/"))
        and _positive_id(expected.run_id)
        and type(expected.attempt) is int
        and expected.attempt == 1
        and _positive_id(expected.actor_id)
        and _positive_id(expected.reviewer_id)
        and expected.actor_id != expected.reviewer_id
        and isinstance(expected.source_sha, str)
        and bool(SHA.fullmatch(expected.source_sha))
        and isinstance(expected.recovery_image, str)
        and bool(IMAGE.fullmatch(expected.recovery_image))
        and expected.environment == "lab-image-release-review"
        and expected.workflow_path == ".github/workflows/deploy-lab.yml"
        and isinstance(expected.max_run_age, timedelta)
        and timedelta(0) < expected.max_run_age <= timedelta(hours=2)
    )


def _review_comment(expected):
    return (
        f"lab-image-release:v1 repo={expected.repository} run={expected.run_id} "
        f"attempt=1 source={expected.source_sha} recovery={expected.recovery_image}"
    )


def _verify_run(run, jobs_response, expected, now):
    if not isinstance(run, dict):
        raise CheckError("Workflow run evidence is missing.")
    if not (
        type(run.get("id")) is int
        and run.get("id") == expected.run_id
        and run.get("run_attempt") == 1
        and type(run.get("run_attempt")) is int
        and run.get("event") == "workflow_dispatch"
        and run.get("status") == "in_progress"
        and run.get("head_branch") == "main"
        and run.get("head_sha") == expected.source_sha
        and _nested(run, "repository", "full_name") == expected.repository
        and _nested(run, "head_repository", "full_name") == expected.repository
        and _nested(run, "actor", "id") == expected.actor_id
        and type(_nested(run, "actor", "id")) is int
    ):
        raise CheckError("Workflow run identity, first attempt, actor, or source was not confirmed.")
    raw_path = run.get("path")
    if not isinstance(raw_path, str):
        raise CheckError("Workflow path is missing.")
    path, separator, ref = raw_path.partition("@")
    if (
        path != expected.workflow_path
        or not separator
        or ref not in {"main", "refs/heads/main"}
    ):
        raise CheckError("Workflow file or dispatch ref was not confirmed.")
    created = run.get("created_at")
    if not isinstance(created, str):
        raise CheckError("Workflow run creation time is missing.")
    try:
        created_at = datetime.fromisoformat(created.replace("Z", "+00:00"))
    except ValueError:
        raise CheckError("Workflow run creation time is invalid.") from None
    if created_at.tzinfo is None:
        raise CheckError("Workflow run creation time has no timezone.")
    age = now - created_at.astimezone(timezone.utc)
    if not timedelta(0) <= age < expected.max_run_age:
        raise CheckError("Workflow run is stale or its clock evidence is invalid.")

    jobs = jobs_response.get("jobs") if isinstance(jobs_response, dict) else None
    if (
        not isinstance(jobs, list)
        or type(jobs_response.get("total_count")) is not int
        or jobs_response["total_count"] != len(jobs)
        or not jobs
    ):
        raise CheckError("Attempt-specific workflow job inventory is incomplete.")
    matching = []
    expected_run_url = f"https://api.github.com/repos/{expected.repository}/actions/runs/{expected.run_id}"
    for job in jobs:
        if not isinstance(job, dict):
            raise CheckError("Workflow job inventory contains an invalid entry.")
        if job.get("name") == "deploy":
            matching.append(job)
    if len(matching) != 1:
        raise CheckError("The exact deployment job was not uniquely identified.")
    job = matching[0]
    if not (
        _positive_id(job.get("id"))
        and type(job.get("run_id")) is int
        and job.get("run_id") == expected.run_id
        and job.get("run_url") == expected_run_url
        and job.get("head_sha") == expected.source_sha
        and job.get("head_branch") == "main"
        and job.get("status") == "in_progress"
    ):
        raise CheckError("The exact in-progress deployment job was not confirmed.")


def _verify_policy(environment, branch_policy, expected):
    if not isinstance(environment, dict) or not isinstance(branch_policy, dict):
        raise CheckError("Environment policy evidence is missing.")
    rules = environment.get("protection_rules")
    branch_rules = branch_policy.get("branch_policies")
    if not (
        environment.get("name") == expected.environment
        and _positive_id(environment.get("id"))
        and type(environment.get("can_admins_bypass")) is bool
        and environment.get("can_admins_bypass") is False
        and environment.get("deployment_branch_policy") == {
            "protected_branches": False, "custom_branch_policies": True,
        }
        and isinstance(rules, list)
        and len(rules) == 2
        and {rule.get("type") for rule in rules if isinstance(rule, dict)}
        == {"branch_policy", "required_reviewers"}
        and type(branch_policy.get("total_count")) is int
        and branch_policy.get("total_count") == 1
        and isinstance(branch_rules, list)
        and len(branch_rules) == 1
        and isinstance(branch_rules[0], dict)
        and _positive_id(branch_rules[0].get("id"))
        and branch_rules[0].get("name") == "main"
    ):
        raise CheckError("Main-only environment policy or disabled administrator bypass was not confirmed.")
    reviewer_rules = [rule for rule in rules if rule.get("type") == "required_reviewers"]
    reviewer_rule = reviewer_rules[0]
    reviewers = reviewer_rule.get("reviewers")
    if not (
        reviewer_rule.get("prevent_self_review") is True
        and isinstance(reviewers, list)
        and len(reviewers) == 1
        and isinstance(reviewers[0], dict)
        and reviewers[0].get("type") == "User"
        and reviewers[0].get("reviewer", {}).get("id") == expected.reviewer_id
        and type(reviewers[0].get("reviewer", {}).get("id")) is int
        and expected.reviewer_id != expected.actor_id
    ):
        raise CheckError("The independent configured reviewer was not confirmed.")
    return environment["id"]


def _verify_reviews(reviews, environment_id, expected):
    if not isinstance(reviews, list) or len(reviews) != 1:
        raise CheckError("Approval history is ambiguous or incomplete.")
    review = reviews[0]
    environments = review.get("environments") if isinstance(review, dict) else None
    if not isinstance(review, dict) or not (
        review.get("state") == "approved"
        and review.get("comment") == _review_comment(expected)
        and _nested(review, "user", "id") == expected.reviewer_id
        and type(_nested(review, "user", "id")) is int
        and isinstance(environments, list)
        and len(environments) == 1
        and isinstance(environments[0], dict)
        and environments[0].get("id") == environment_id
        and type(environments[0].get("id")) is int
        and environments[0].get("name") == expected.environment
    ):
        raise CheckError("Approval does not bind the independent reviewer, run, source, and recovery image.")


def _verify_secrets(secrets):
    if not (
        isinstance(secrets, dict)
        and type(secrets.get("total_count")) is int
        and secrets["total_count"] == 0
        and secrets.get("secrets") == []
    ):
        raise CheckError("A complete empty environment-secret inventory was not confirmed.")


def verify_evidence(
    evidence, expected, *, now=None, secret_mode="require-empty",
    owner_acceptance=None,
):
    """Verify exact API payloads; omit ``secrets`` only with explicit opt-in.

    The no-secret-reference mode does not imply the environment inventory is
    empty. It is an owner-accepted alternate assumption, not the default gate.
    """
    if not _valid_expectation(expected):
        raise CheckError("Approval evidence expectations are invalid.")
    if secret_mode not in SECRET_MODES:
        raise CheckError("Secret inventory mode is invalid.")
    if secret_mode == "no-secret-references" and owner_acceptance != NO_SECRET_REFERENCE_ACCEPTANCE:
        raise CheckError("No-secret-reference mode requires explicit owner acceptance.")
    if not isinstance(evidence, dict):
        raise CheckError("GitHub approval evidence is incomplete.")
    now = datetime.now(timezone.utc) if now is None else now
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise CheckError("Current time evidence is invalid.")

    _verify_run(evidence.get("run"), evidence.get("jobs"), expected, now.astimezone(timezone.utc))
    main = evidence.get("main")
    ref = evidence.get("main_ref")
    if not (
        isinstance(main, dict)
        and main.get("name") == "main"
        and main.get("protected") is True
        and _nested(main, "commit", "sha") == expected.source_sha
        and isinstance(ref, dict)
        and ref.get("ref") == "refs/heads/main"
        and _nested(ref, "object", "sha") == expected.source_sha
    ):
        raise CheckError("Protected main no longer matches the exact source SHA.")
    environment_id = _verify_policy(
        evidence.get("environment"), evidence.get("branch_policy"), expected,
    )
    _verify_reviews(evidence.get("approvals"), environment_id, expected)

    if secret_mode == "require-empty":
        _verify_secrets(evidence.get("secrets"))
        inventory_state = "verified-empty"
    else:
        if "secrets" in evidence:
            raise CheckError("No-secret-reference mode must not imply a secret inventory result.")
        inventory_state = "not-checked-owner-accepted-no-reference-model"
    return {
        "run_id": expected.run_id,
        "attempt": 1,
        "source_sha": expected.source_sha,
        "recovery_image": expected.recovery_image,
        "secret_inventory": inventory_state,
        "review_timestamp_verified": False,
        "durable_single_use_enforced": False,
    }


def read_evidence(token, expected, *, secret_mode="require-empty", owner_acceptance=None,
                  connection_factory=http.client.HTTPSConnection, now=None):
    """Fetch read-only current evidence. Every missing or partial response fails."""
    if not _valid_expectation(expected):
        raise CheckError("Approval evidence expectations are invalid.")
    if secret_mode not in SECRET_MODES:
        raise CheckError("Secret inventory mode is invalid.")
    if secret_mode == "no-secret-references" and owner_acceptance != NO_SECRET_REFERENCE_ACCEPTANCE:
        raise CheckError("No-secret-reference mode requires explicit owner acceptance.")
    repository = "/".join(quote(part, safe="") for part in expected.repository.split("/"))
    environment = quote(expected.environment, safe="")
    root = f"/repos/{repository}"
    run_id = expected.run_id
    reader = GitHubReader(token, connection_factory=connection_factory)
    evidence = {
        "run": reader.get_json(f"{root}/actions/runs/{run_id}", kind="workflow run"),
        "jobs": reader.get_json(
            f"{root}/actions/runs/{run_id}/attempts/1/jobs?per_page=100",
            kind="attempt jobs",
        ),
        "approvals": reader.get_json(f"{root}/actions/runs/{run_id}/approvals", kind="approvals"),
        "environment": reader.get_json(f"{root}/environments/{environment}", kind="environment"),
        "branch_policy": reader.get_json(
            f"{root}/environments/{environment}/deployment-branch-policies?per_page=100",
            kind="environment branch policy",
        ),
        "main": reader.get_json(f"{root}/branches/main", kind="protected main branch"),
        "main_ref": reader.get_json(f"{root}/git/ref/heads/main", kind="main ref"),
    }
    if secret_mode == "require-empty":
        evidence["secrets"] = reader.get_json(
            f"{root}/environments/{environment}/secrets?per_page=1",
            kind="environment secret inventory",
        )
    return verify_evidence(
        evidence, expected, now=now, secret_mode=secret_mode,
        owner_acceptance=owner_acceptance,
    )

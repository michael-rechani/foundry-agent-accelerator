"""Fixture-only Lab approval contract for #522. Not a deployment gate.

Run on an unprivileged hosted runner with:
    python3 .github/scripts/test_lab_image_approval_contract.py

The inputs model independently obtained GitHub responses, not evidence that
the workflow token can acquire them. GitHub does not document administrator
bypass in the environment response schema. Missing bypass evidence rejects.
The run age bounds the review window; /approvals has no attempt or timestamp.
This contract does not authenticate snapshots or enforce single use within
one attempt. No workflow imports it or changes the live deploy disable.
"""

import unittest
from datetime import datetime, timedelta, timezone

from check_lab_image_release import IMAGE, SHA
from check_state_backend import CheckError


ENVIRONMENT = "lab-image-release-review"
WORKFLOW = ".github/workflows/deploy-lab.yml"


def field(value, *path):
    for key in path:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def valid_id(value):
    return type(value) is int and value > 0


def same_id(value, expected):
    return valid_id(value) and valid_id(expected) and value == expected


def check_fixture(
    *, repository, run_id, attempt, source, previous_image, reviewer_id, now, max_age,
    run, main, environment, branch_rules, secrets, reviews,
):
    """Require exact binding and explicit policy in trusted synthetic snapshots."""
    if not (
        same_id(attempt, 1)
        and same_id(field(run, "run_attempt"), 1)
        and same_id(field(run, "id"), run_id)
        and isinstance(source, str)
        and SHA.fullmatch(source)
        and isinstance(previous_image, str)
        and IMAGE.fullmatch(previous_image)
        and field(run, "head_sha") == source == field(main, "commit", "sha")
        and field(main, "name") == field(run, "head_branch") == "main"
        and field(main, "protected") is True
        and field(run, "repository", "full_name") == field(run, "head_repository", "full_name") == repository
        and field(run, "path") == WORKFLOW
        and field(run, "event") == "workflow_dispatch"
        and field(run, "status") == "in_progress"
    ):
        raise CheckError("Exact first-attempt workflow and protected main were not confirmed.")

    try:
        created_at = datetime.strptime(field(run, "created_at"), "%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError):
        raise CheckError("The workflow run creation time was not confirmed.") from None
    age = now - created_at.replace(tzinfo=timezone.utc)
    if not timedelta(0) <= age < max_age:
        raise CheckError("The workflow run is outside the review window.")

    actor_id = field(run, "actor", "id")
    environment_id = field(environment, "id")
    rules = field(environment, "protection_rules")
    branches = field(branch_rules, "branch_policies")
    if not (
        valid_id(actor_id)
        and valid_id(reviewer_id)
        and actor_id != reviewer_id
        and valid_id(environment_id)
        and field(environment, "name") == ENVIRONMENT
        and field(environment, "can_admins_bypass") is False
        and field(environment, "deployment_branch_policy", "protected_branches") is False
        and field(environment, "deployment_branch_policy", "custom_branch_policies") is True
        and same_id(field(branch_rules, "total_count"), 1)
        and isinstance(branches, list) and len(branches) == 1
        and field(branches[0], "type") == "branch" and field(branches[0], "name") == "main"
        and isinstance(rules, list) and len(rules) == 2
        and {field(rule, "type") for rule in rules if isinstance(field(rule, "type"), str)}
        == {"branch_policy", "required_reviewers"}
        and type(field(secrets, "total_count")) is int
        and field(secrets, "total_count") == 0
        and field(secrets, "secrets") == []
    ):
        raise CheckError("Main-only, no-bypass, secret-free review policy was not confirmed.")

    reviewer_rule = next(rule for rule in rules if field(rule, "type") == "required_reviewers")
    reviewers = field(reviewer_rule, "reviewers")
    if not (
        field(reviewer_rule, "prevent_self_review") is True
        and isinstance(reviewers, list) and len(reviewers) == 1
        and field(reviewers[0], "type") == "User"
        and same_id(field(reviewers[0], "reviewer", "id"), reviewer_id)
    ):
        raise CheckError("The configured independent reviewer was not confirmed.")

    if not isinstance(reviews, list) or len(reviews) != 1:
        raise CheckError("Exactly one unambiguous approval record is required.")
    review = reviews[0]
    environments = field(review, "environments")
    comment = (
        f"lab-image-release:v1 repo={repository} run={run_id} attempt=1 "
        f"source={source} recovery={previous_image}"
    )
    if not (
        field(review, "state") == "approved"
        and same_id(field(review, "user", "id"), reviewer_id)
        and isinstance(environments, list) and len(environments) == 1
        and field(environments[0], "name") == ENVIRONMENT
        and same_id(field(environments[0], "id"), environment_id)
        and field(review, "comment") == comment
    ):
        raise CheckError("The review does not bind this environment, run, source and recovery image.")


def fixture():
    source = "a" * 40
    image = "registry.invalid/workbench@sha256:" + "b" * 64
    return {
        "repository": "example/lab",
        "run_id": 42,
        "attempt": 1,
        "source": source,
        "previous_image": image,
        "reviewer_id": 7,
        "now": datetime(2026, 1, 1, 0, 30, tzinfo=timezone.utc),
        "max_age": timedelta(hours=1),
        "run": {
            "id": 42, "run_attempt": 1, "head_sha": source, "head_branch": "main",
            "repository": {"full_name": "example/lab"}, "head_repository": {"full_name": "example/lab"},
            "path": ".github/workflows/deploy-lab.yml", "event": "workflow_dispatch",
            "status": "in_progress", "actor": {"id": 8}, "created_at": "2026-01-01T00:00:00Z",
        },
        "main": {"name": "main", "protected": True, "commit": {"sha": source}},
        "environment": {
            "name": "lab-image-release-review", "id": 9, "can_admins_bypass": False,
            "deployment_branch_policy": {"protected_branches": False, "custom_branch_policies": True},
            "protection_rules": [
                {"type": "branch_policy"},
                {"type": "required_reviewers", "prevent_self_review": True,
                 "reviewers": [{"type": "User", "reviewer": {"id": 7}}]},
            ],
        },
        "branch_rules": {"total_count": 1, "branch_policies": [{"type": "branch", "name": "main"}]},
        "secrets": {"total_count": 0, "secrets": []},
        "reviews": [{
            "state": "approved", "user": {"id": 7},
            "environments": [{
                "id": 9, "name": "lab-image-release-review", "can_admins_bypass": False,
                "created_at": "2025-01-01T00:00:00Z", "updated_at": "2025-01-01T00:00:00Z",
            }],
            "comment": f"lab-image-release:v1 repo=example/lab run=42 attempt=1 source={source} recovery={image}",
        }],
    }


class ApprovalContractTests(unittest.TestCase):
    def test_exact_fresh_independent_approval(self):
        check_fixture(**fixture())

    def test_review_cannot_transfer_to_a_different_run_source_or_recovery_image(self):
        for field_name in ("run_id", "source", "previous_image"):
            with self.subTest(field=field_name), self.assertRaisesRegex(CheckError, "does not bind"):
                evidence = fixture()
                if field_name == "run_id":
                    evidence["run_id"] = evidence["run"]["id"] = 43
                elif field_name == "source":
                    evidence["source"] = evidence["run"]["head_sha"] = evidence["main"]["commit"]["sha"] = "c" * 40
                else:
                    evidence["previous_image"] = "registry.invalid/workbench@sha256:" + "c" * 64
                check_fixture(**evidence)

    def test_reruns_stale_runs_and_ambiguous_reviews_reject(self):
        for scenario in ("context rerun", "API rerun", "stale", "future", "no review", "duplicate review", "rejection"):
            with self.subTest(scenario=scenario), self.assertRaises(CheckError):
                evidence = fixture()
                if scenario == "context rerun":
                    evidence["attempt"] = 2
                elif scenario == "API rerun":
                    evidence["run"]["run_attempt"] = 2
                elif scenario == "stale":
                    evidence["now"] += timedelta(minutes=30)
                    evidence["reviews"][0]["environments"][0]["updated_at"] = "2026-01-01T00:59:59Z"
                elif scenario == "future":
                    evidence["now"] -= timedelta(minutes=31)
                elif scenario == "no review":
                    evidence["reviews"].clear()
                elif scenario == "duplicate review":
                    evidence["reviews"] *= 2
                else:
                    evidence["reviews"][0]["state"] = "rejected"
                check_fixture(**evidence)

    def test_policy_requires_positive_evidence(self):
        for scenario in ("missing policy", "missing bypass", "enabled bypass", "self-review",
                         "wrong reviewer", "wrong environment",
                         "missing secrets", "nonempty secrets", "extra branch", "moved main"):
            with self.subTest(scenario=scenario), self.assertRaises(CheckError):
                evidence = fixture()
                if scenario == "missing policy":
                    del evidence["environment"]["protection_rules"]
                elif scenario == "missing bypass":
                    del evidence["environment"]["can_admins_bypass"]
                elif scenario == "enabled bypass":
                    evidence["environment"]["can_admins_bypass"] = True
                elif scenario == "self-review":
                    evidence["run"]["actor"]["id"] = 7
                elif scenario == "wrong reviewer":
                    evidence["reviews"][0]["user"]["id"] = 8
                elif scenario == "wrong environment":
                    evidence["reviews"][0]["environments"][0]["id"] = 10
                elif scenario == "missing secrets":
                    evidence["secrets"] = None
                elif scenario == "nonempty secrets":
                    evidence["secrets"] = {"total_count": 1, "secrets": [{"name": "PLACEHOLDER"}]}
                elif scenario == "extra branch":
                    evidence["branch_rules"]["total_count"] = 2
                    evidence["branch_rules"]["branch_policies"].append({"type": "branch", "name": "*"})
                else:
                    evidence["main"]["commit"]["sha"] = "c" * 40
                check_fixture(**evidence)


if __name__ == "__main__":
    unittest.main()

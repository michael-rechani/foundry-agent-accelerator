"""Mocked GitHub API contract tests; never make requests or use credentials."""

import json
import unittest
from datetime import datetime, timedelta, timezone
from email.message import Message
from unittest.mock import Mock, patch

import check_lab_image_approval as approval_reader
from check_state_backend import CheckError
from check_lab_image_approval import (
    ApprovalExpectation,
    CallerContext,
    GitHubReader,
    NO_SECRET_REFERENCE_ACKNOWLEDGEMENT,
    read_evidence,
    verify_evidence,
)

NOW = datetime(2026, 1, 1, 0, 29, tzinfo=timezone.utc)
SHA = "a" * 40
RECOVERY = "registry.invalid/workbench@sha256:" + "b" * 64
REPO = "example/lab"
RUN_ID = 42
ENVIRONMENT_ID = 9
ACTOR_ID = 8
REVIEWER_ID = 7
COMMENT = (
    f"lab-image-release:v1 repo={REPO} run={RUN_ID} attempt=1 "
    f"source={SHA} recovery={RECOVERY}"
)


def expected(**updates):
    values = {
        "repository": REPO, "run_id": RUN_ID, "attempt": 1,
        "actor_id": ACTOR_ID,
        "reviewer_id": REVIEWER_ID, "source_sha": SHA,
        "recovery_image": RECOVERY,
    }
    values.update(updates)
    return ApprovalExpectation(**values)


def caller_context(**updates):
    values = {
        "repository": REPO,
        "ref": "refs/heads/main",
        "workflow_ref": f"{REPO}/.github/workflows/deploy-lab.yml@refs/heads/main",
        "sha": SHA,
        "run_id": str(RUN_ID),
        "run_attempt": "1",
        "event_name": "workflow_dispatch",
        "job": "deploy",
    }
    values.update(updates)
    return CallerContext(**values)


def evidence():
    return {
        "run": {
            "id": RUN_ID, "run_attempt": 1, "event": "workflow_dispatch",
            "status": "in_progress", "head_branch": "main", "head_sha": SHA,
            "path": ".github/workflows/deploy-lab.yml",
            "created_at": "2026-01-01T00:00:00Z",
            "repository": {"full_name": REPO}, "head_repository": {"full_name": REPO},
            "actor": {"id": ACTOR_ID},
        },
        "jobs": {
            "total_count": 1,
            "jobs": [{
                "id": 101, "run_id": RUN_ID,
                "run_url": f"https://api.github.com/repos/{REPO}/actions/runs/{RUN_ID}",
                "head_sha": SHA, "head_branch": "main", "name": "deploy",
                "status": "in_progress",
                "check_run_url": f"https://api.github.com/repos/{REPO}/check-runs/101",
            }],
        },
        "approvals": [{
            "state": "approved", "comment": COMMENT,
            "user": {"id": REVIEWER_ID},
            "environments": [{"id": ENVIRONMENT_ID, "name": "lab-image-release-review"}],
        }],
        "environment": {
            "id": ENVIRONMENT_ID, "name": "lab-image-release-review",
            "can_admins_bypass": False,
            "deployment_branch_policy": {
                "protected_branches": False, "custom_branch_policies": True,
            },
            "protection_rules": [
                {"type": "branch_policy"},
                {"type": "required_reviewers", "prevent_self_review": True,
                 "reviewers": [{"type": "User", "reviewer": {"id": REVIEWER_ID}}]},
            ],
        },
        "branch_policy": {
            "total_count": 1,
            "branch_policies": [{"id": 99, "name": "main", "type": "branch"}],
        },
        "main": {"name": "main", "protected": True, "commit": {"sha": SHA}},
        "main_ref": {"ref": "refs/heads/main", "object": {"sha": SHA}},
        "secrets": {"total_count": 0, "secrets": []},
    }


def api_response(payload, *, status=200, headers=None, raw=None):
    result = Mock()
    result.status = status
    result.headers = headers or Message()
    if raw is None:
        raw = json.dumps(payload).encode()
    result.read.return_value = raw
    return result


def length_headers(payload):
    headers = Message()
    headers["Content-Length"] = str(len(payload))
    return headers


class EvidenceContractTests(unittest.TestCase):
    def test_actual_workflow_run_path_has_no_ref_suffix(self):
        data = evidence()
        self.assertEqual(data["run"]["path"], ".github/workflows/deploy-lab.yml")
        result = verify_evidence(data, expected(), caller_context(), now=NOW)
        self.assertEqual(result["source_sha"], SHA)

    def test_exact_current_response_shapes_pass_in_strict_mode(self):
        result = verify_evidence(evidence(), expected(), caller_context(), now=NOW)
        self.assertEqual(result["secret_inventory"], "verified-empty")
        self.assertFalse(result["review_timestamp_verified"])
        self.assertFalse(result["durable_single_use_enforced"])

    def test_branch_policy_api_shape_requires_branch_type(self):
        data = evidence()
        self.assertEqual(
            data["branch_policy"]["branch_policies"][0],
            {"id": 99, "name": "main", "type": "branch"},
        )
        verify_evidence(data, expected(), caller_context(), now=NOW)
        data["branch_policy"]["branch_policies"][0]["type"] = "tag"
        with self.assertRaises(CheckError):
            verify_evidence(data, expected(), caller_context(), now=NOW)

    def test_caller_context_binds_trusted_ref_workflow_run_and_current_job(self):
        mismatches = (
            {"repository": "other/repo"},
            {"ref": "main"},
            {"workflow_ref": f"{REPO}/.github/workflows/other.yml@refs/heads/main"},
            {"sha": "c" * 40},
            {"run_id": "43"},
            {"run_attempt": "2"},
            {"event_name": "push"},
            {"job": "build"},
            {"job": ["deploy"]},
        )
        for values in mismatches:
            with self.subTest(values=values), self.assertRaises(CheckError):
                verify_evidence(
                    evidence(), expected(), caller_context(**values), now=NOW,
                )

    def test_approval_and_deploy_callers_must_match_their_current_api_job(self):
        for job_name in ("approval", "deploy"):
            with self.subTest(job=job_name):
                data = evidence()
                data["jobs"]["jobs"][0]["name"] = job_name
                result = verify_evidence(
                    data, expected(), caller_context(job=job_name), now=NOW,
                )
                self.assertEqual(result["caller_job"], job_name)
        with self.assertRaises(CheckError):
            verify_evidence(
                evidence(), expected(), caller_context(job="approval"), now=NOW,
            )

    def test_review_is_run_bound_but_attempt_and_timestamp_are_not_claimed(self):
        data = evidence()
        result1 = verify_evidence(data, expected(), caller_context(), now=NOW)
        result2 = verify_evidence(data, expected(), caller_context(), now=NOW)
        self.assertEqual(result1, result2)
        self.assertNotIn("reviewed_at", result1)
        self.assertFalse(result1["durable_single_use_enforced"])
        data["run"]["run_attempt"] = 2
        with self.assertRaises(CheckError):
            verify_evidence(data, expected(attempt=2), caller_context(), now=NOW)

    def test_no_secret_reference_mode_is_disabled_by_default_and_never_claims_empty(self):
        data = evidence()
        del data["secrets"]
        with self.assertRaisesRegex(CheckError, "caller acknowledgment"):
            verify_evidence(
                data, expected(), caller_context(), now=NOW,
                secret_mode="no-secret-references",
            )
        result = verify_evidence(
            data, expected(), caller_context(), now=NOW,
            secret_mode="no-secret-references",
            no_secret_reference_acknowledgement=NO_SECRET_REFERENCE_ACKNOWLEDGEMENT,
        )
        self.assertEqual(result["secret_inventory"], "not-checked-no-reference-model-caller-asserted")
        self.assertNotEqual(result["secret_inventory"], "verified-empty")
        data["secrets"] = {"total_count": 0, "secrets": []}
        with self.assertRaisesRegex(CheckError, "must not imply"):
            verify_evidence(
                data, expected(), caller_context(), now=NOW,
                secret_mode="no-secret-references",
                no_secret_reference_acknowledgement=NO_SECRET_REFERENCE_ACKNOWLEDGEMENT,
            )

    def test_missing_or_nonempty_secret_inventory_rejects_strict_mode(self):
        for value in (None, {"total_count": 1, "secrets": [{"name": "DO_NOT_LOG"}]},
                      {"total_count": 0, "secrets": [{"name": "DO_NOT_LOG"}]}):
            with self.subTest(value=value), self.assertRaises(CheckError):
                data = evidence()
                if value is None:
                    del data["secrets"]
                else:
                    data["secrets"] = value
                verify_evidence(data, expected(), caller_context(), now=NOW)

    def test_run_source_actor_attempt_age_and_identity_are_bound(self):
        mutations = (
            lambda d: d["run"].update(id=43),
            lambda d: d["run"].update(run_attempt=2),
            lambda d: d["run"].update(actor={"id": 7}),
            lambda d: d["run"].update(head_sha="c" * 40),
            lambda d: d["run"].update(event="push"),
            lambda d: d["run"].update(head_branch="feature"),
            lambda d: d["run"].update(repository={"full_name": "other/repo"}),
            lambda d: d["run"].update(path=".github/workflows/other.yml"),
            lambda d: d["run"].update(path=".github/workflows/deploy-lab.yml@refs/heads/main"),
            lambda d: d["run"].update(created_at="not-a-time"),
        )
        for mutate in mutations:
            with self.subTest(mutation=mutate), self.assertRaises(CheckError):
                data = evidence()
                mutate(data)
                verify_evidence(data, expected(), caller_context(), now=NOW)
        with self.assertRaisesRegex(CheckError, "stale"):
            verify_evidence(
                evidence(), expected(), caller_context(),
                now=NOW + timedelta(minutes=31),
            )
        with self.assertRaisesRegex(CheckError, "stale"):
            verify_evidence(
                evidence(), expected(), caller_context(),
                now=NOW + timedelta(minutes=1),
            )
        with self.assertRaises(CheckError):
            verify_evidence(
                evidence(), expected(run_id=43), caller_context(), now=NOW,
            )

    def test_current_main_and_attempt_job_are_bound(self):
        for key, update in (
            ("main SHA", lambda d: d["main_ref"]["object"].update(sha="c" * 40)),
            ("unprotected main", lambda d: d["main"].update(protected=False)),
            ("invalid job id", lambda d: d["jobs"]["jobs"][0].update(id=0)),
            ("wrong job run", lambda d: d["jobs"]["jobs"][0].update(run_id=43)),
            ("duplicate deployment job", lambda d: d["jobs"]["jobs"].append(dict(d["jobs"]["jobs"][0]))),
            ("partial job list", lambda d: d["jobs"].update(total_count=2)),
            ("missing jobs", lambda d: d.update(jobs={})),
        ):
            with self.subTest(key=key), self.assertRaises(CheckError):
                data = evidence()
                update(data)
                verify_evidence(data, expected(), caller_context(), now=NOW)

    def test_review_identity_environment_and_recovery_are_bound(self):
        for key, update in (
            ("wrong reviewer", lambda d: d["approvals"][0]["user"].update(id=ACTOR_ID)),
            ("wrong environment", lambda d: d["approvals"][0]["environments"][0].update(id=10)),
            ("wrong recovery", lambda d: d["approvals"][0].update(comment=COMMENT.replace(RECOVERY, "x"))),
            ("rejected", lambda d: d["approvals"][0].update(state="rejected")),
            ("missing review", lambda d: d.update(approvals=[])),
            ("duplicate review", lambda d: d["approvals"].append(dict(d["approvals"][0]))),
            ("actor is reviewer", lambda d: d["run"].update(actor={"id": REVIEWER_ID})),
        ):
            with self.subTest(key=key), self.assertRaises(CheckError):
                data = evidence()
                update(data)
                verify_evidence(data, expected(), caller_context(), now=NOW)

    def test_policy_requires_single_reviewer_no_bypass_main_only_and_self_review_block(self):
        cases = (
            ("missing bypass", lambda d: d["environment"].pop("can_admins_bypass")),
            ("bypass enabled", lambda d: d["environment"].update(can_admins_bypass=True)),
            ("missing policy", lambda d: d["environment"].pop("protection_rules")),
            ("self-review enabled", lambda d: d["environment"]["protection_rules"][1].update(
                prevent_self_review=False)),
            ("wrong reviewer", lambda d: d["environment"]["protection_rules"][1]["reviewers"][0][
                "reviewer"].update(id=ACTOR_ID)),
            ("null reviewer", lambda d: d["environment"]["protection_rules"][1]["reviewers"][0].update(
                reviewer=None)),
            ("extra reviewer", lambda d: d["environment"]["protection_rules"][1]["reviewers"].append(
                {"type": "User", "reviewer": {"id": 6}})),
            ("wildcard branch", lambda d: d["branch_policy"]["branch_policies"].append(
                {"id": 100, "name": "*"})),
            ("tag policy named main", lambda d: d["branch_policy"]["branch_policies"][0].update(
                type="tag")),
            ("missing branch count", lambda d: d["branch_policy"].update(total_count=2)),
            ("non-main-only", lambda d: d["environment"]["deployment_branch_policy"].update(
                custom_branch_policies=False)),
        )
        for key, mutate in cases:
            with self.subTest(key=key), self.assertRaises(CheckError):
                data = evidence()
                mutate(data)
                verify_evidence(data, expected(), caller_context(), now=NOW)


class ReaderTransportTests(unittest.TestCase):
    def test_unavailable_malformed_partial_redirect_and_paginated_data_reject(self):
        cases = (
            ("forbidden", api_response({}, status=403)),
            ("redirect", api_response({}, status=302)),
            ("malformed", api_response({}, headers=length_headers(b"{"), raw=b"{")),
            ("truncated", api_response({}, raw=b"{}")),
            ("oversize", api_response({}, headers=length_headers(b"x" * (256 * 1024 + 1)),
                                      raw=b"x" * (256 * 1024 + 1))),
            ("pagination", api_response({}, headers=_link_headers())),
            ("wrong root", api_response([], headers=length_headers(b"[]"))),
        )
        for name, response in cases:
            with self.subTest(name=name):
                reader, connection = self._reader(response)
                if name == "truncated":
                    response.headers = length_headers(b"{}" + b"x")
                with self.assertRaises(CheckError):
                    reader.get_json("/repos/example/lab/actions/runs/42", kind="workflow run")
                connection.close.assert_called_once()

    def test_reader_uses_fixed_https_get_and_never_logs_or_returns_response_body(self):
        payload = b'{"name":"copilot","id":9}'
        response = api_response({}, headers=length_headers(payload), raw=payload)
        reader, connection = self._reader(response)
        self.assertEqual(reader.get_json("/repos/example/lab/environments/copilot", kind="environment"),
                         {"name": "copilot", "id": 9})
        args, kwargs = connection.request.call_args
        self.assertEqual(args[:2], ("GET", "/repos/example/lab/environments/copilot"))
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer synthetic-token")
        self.assertNotIn("synthetic-token", repr(response))

    def test_reader_rejects_missing_framing_and_duplicate_json_keys(self):
        for payload, headers in ((b"{}", Message()), (b'{"name":1,"name":2}', length_headers(b'{"name":1,"name":2}'))):
            with self.subTest(payload=payload):
                response = api_response({}, headers=headers, raw=payload)
                reader, _ = self._reader(response)
                with self.assertRaises(CheckError):
                    reader.get_json("/repos/example/lab/environments/copilot", kind="environment")

    def test_reader_accepts_only_runner_queue_and_exact_validate_filters(self):
        paths = (
            "/repos/example/lab/actions/runs?status=queued&per_page=100",
            "/repos/example/lab/actions/workflows/validate.yml/runs?"
            f"head_sha={'a' * 40}&branch=main&event=push&per_page=100",
        )
        for path in paths:
            with self.subTest(path=path):
                payload = b'{"total_count":0,"workflow_runs":[]}'
                response = api_response(
                    {}, headers=length_headers(payload), raw=payload,
                )
                reader, _ = self._reader(response)
                self.assertEqual(
                    reader.get_json(path, kind="workflow runs"),
                    {"total_count": 0, "workflow_runs": []},
                )

    def test_reader_rejects_unapproved_runner_inventory_filters(self):
        for path in (
            "/repos/example/lab/actions/runs?status=completed&per_page=100",
            "/repos/example/lab/actions/runs?status=queued",
            "/repos/example/lab/actions/workflows/validate.yml/runs?"
            f"head_sha={'A' * 40}&branch=main&event=push&per_page=100",
            "/repos/example/lab/actions/workflows/other.yml/runs?"
            f"head_sha={'a' * 40}&branch=main&event=push&per_page=100",
        ):
            with self.subTest(path=path):
                reader, _ = self._reader(api_response({}))
                with self.assertRaises(CheckError):
                    reader.get_json(path, kind="workflow runs")

    def test_connection_failure_is_redacted_and_fails_closed(self):
        reader = GitHubReader(
            "synthetic-token",
            connection_factory=Mock(side_effect=OSError("DO_NOT_LOG")),
        )
        with self.assertRaisesRegex(CheckError, "request failed") as raised:
            reader.get_json("/repos/example/lab/environments/copilot", kind="environment")
        self.assertNotIn("DO_NOT_LOG", str(raised.exception))

    def test_fetch_targets_expected_read_endpoints_and_skips_inventory_only_on_explicit_opt_in(self):
        paths = []

        class FakeReader:
            def __init__(self, _token, **_kwargs):
                pass

            def get_json(self, path, *, kind):
                paths.append(path)
                return _payload_for_kind(kind)

        with patch.object(approval_reader, "GitHubReader", FakeReader):
            strict_result = read_evidence(
                "synthetic-token", expected(), caller_context(), now=NOW,
            )
        self.assertEqual(strict_result["secret_inventory"], "verified-empty")
        self.assertEqual(paths, [
            f"/repos/{REPO}/actions/runs/{RUN_ID}",
            f"/repos/{REPO}/actions/runs/{RUN_ID}/attempts/1/jobs?per_page=100",
            f"/repos/{REPO}/actions/runs/{RUN_ID}/approvals",
            f"/repos/{REPO}/environments/lab-image-release-review",
            f"/repos/{REPO}/environments/lab-image-release-review/deployment-branch-policies?per_page=100",
            f"/repos/{REPO}/branches/main",
            f"/repos/{REPO}/git/ref/heads/main",
            f"/repos/{REPO}/environments/lab-image-release-review/secrets?per_page=1",
        ])

        paths.clear()
        with patch.object(approval_reader, "GitHubReader", FakeReader):
            result = read_evidence(
                "synthetic-token", expected(), caller_context(),
                secret_mode="no-secret-references",
                no_secret_reference_acknowledgement=NO_SECRET_REFERENCE_ACKNOWLEDGEMENT,
                now=NOW,
            )
        self.assertEqual(result["secret_inventory"],
                         "not-checked-no-reference-model-caller-asserted")
        self.assertFalse(any(path.endswith("/secrets?per_page=1") for path in paths))
        self.assertEqual(len(paths), 7)

    @staticmethod
    def _reader(response):
        connection = Mock()
        connection.getresponse.return_value = response
        reader = GitHubReader("synthetic-token", connection_factory=Mock(return_value=connection))
        return reader, connection


def _link_headers():
    headers = Message()
    headers["Content-Length"] = "2"
    headers["Link"] = '<https://api.github.com/?page=2>; rel="next"'
    return headers


def _payload_for_kind(kind):
    data = evidence()
    return {
        "workflow run": data["run"],
        "attempt jobs": data["jobs"],
        "approvals": data["approvals"],
        "environment": data["environment"],
        "environment branch policy": data["branch_policy"],
        "protected main branch": data["main"],
        "main ref": data["main_ref"],
        "environment secret inventory": data["secrets"],
    }[kind]


if __name__ == "__main__":
    unittest.main()

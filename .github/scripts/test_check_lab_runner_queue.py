"""Mocked GitHub Actions queue contract tests; no API calls or credentials."""

import unittest

from check_state_backend import CheckError
from check_lab_runner_queue import (
    ACTIVE_RUN_STATUSES,
    REPOSITORY,
    StartContext,
    WORKFLOW_PATH,
    check_runner_queue,
)

SHA = "a" * 40
RUN_ID = 42


def context(**updates):
    values = {
        "repository": REPOSITORY,
        "ref": "refs/heads/main",
        "workflow_ref": f"{REPOSITORY}/{WORKFLOW_PATH}@refs/heads/main",
        "sha": SHA,
        "run_id": str(RUN_ID),
        "run_number": "1",
        "run_attempt": "1",
        "event_name": "workflow_dispatch",
        "job": "start-runner",
    }
    values.update(updates)
    return StartContext(**values)


def run(run_id, *, status, sha=SHA, attempt=1, number=2):
    return {
        "id": run_id,
        "run_number": number,
        "run_attempt": attempt,
        "event": "workflow_dispatch",
        "status": status,
        "head_branch": "main",
        "head_sha": sha,
        "path": WORKFLOW_PATH,
        "repository": {"full_name": REPOSITORY},
        "actor": {"id": 97264614},
    }


def job(job_id, run_id, name, status, labels):
    return {
        "id": job_id,
        "run_id": run_id,
        "run_url": f"https://api.github.com/repos/{REPOSITORY}/actions/runs/{run_id}",
        "head_sha": SHA,
        "head_branch": "main",
        "name": name,
        "status": status,
        "labels": labels,
    }


def baseline():
    current = run(RUN_ID, status="in_progress", number=1)
    validation = {
        "name": "Validate",
        "path": ".github/workflows/validate.yml",
        "event": "push",
        "head_branch": "main",
        "head_sha": SHA,
        "status": "completed",
        "conclusion": "success",
    }
    jobs = [
        job(101, RUN_ID, "start-runner", "in_progress", ["ubuntu-24.04"]),
        job(102, RUN_ID, "smoke", "queued", ["self-hosted", "linux", "lab-runner"]),
    ]
    return {
        "runs": {
            "queued": [],
            "in_progress": [current],
            "waiting": [],
            "pending": [],
        },
        "validation": {"total_count": 1, "workflow_runs": [validation]},
        "jobs": {RUN_ID: jobs},
    }


class FakeReader:
    def __init__(self, token, state, paths):
        if token != "mock-token":
            raise AssertionError("Unexpected token.")
        self.state = state
        self.paths = paths

    def get_json(self, path, *, kind):
        self.paths.append((path, kind))
        if path.startswith(
            f"/repos/{REPOSITORY}/actions/workflows/validate.yml/runs?"
        ):
            return self.state["validation"]
        for status in ACTIVE_RUN_STATUSES:
            if path == f"/repos/{REPOSITORY}/actions/runs?status={status}&per_page=100":
                runs = self.state["runs"][status]
                return {"total_count": len(runs), "workflow_runs": runs}
        prefix = f"/repos/{REPOSITORY}/actions/runs/"
        if path.startswith(prefix) and path.endswith("/jobs?per_page=100"):
            run_id = int(path[len(prefix):].split("/", 1)[0])
            jobs = self.state["jobs"].get(run_id, [])
            return {"total_count": len(jobs), "jobs": jobs}
        raise AssertionError(f"Unexpected API path: {path}")


class QueueContractTests(unittest.TestCase):
    def setUp(self):
        self.state = baseline()
        self.paths = []

    def check(self, caller=None):
        return check_runner_queue(
            "mock-token", caller or context(),
            reader_factory=lambda token: FakeReader(token, self.state, self.paths),
        )

    def test_exact_current_run_and_only_its_expected_smoke_job_pass(self):
        self.check()
        self.assertIn(
            (f"/repos/{REPOSITORY}/actions/runs?status=waiting&per_page=100",
             "waiting workflow run"),
            self.paths,
        )

    def test_an_active_lab_runner_job_in_any_other_queue_blocks(self):
        for status in ACTIVE_RUN_STATUSES:
            with self.subTest(status=status):
                self.setUp()
                if status == "in_progress":
                    self.state["runs"][status].append(run(43, status=status))
                else:
                    self.state["runs"][status].append(run(43, status=status))
                self.state["jobs"][43] = [
                    job(201, 43, "terraform", "queued", ["self-hosted", "linux", "lab-runner"]),
                ]
                with self.assertRaisesRegex(CheckError, "Another active job"):
                    self.check()

    def test_active_non_runner_job_does_not_block(self):
        self.state["runs"]["queued"] = [run(43, status="queued")]
        self.state["jobs"][43] = [job(201, 43, "validate", "queued", ["ubuntu-latest"])]
        self.check()

    def test_missing_jobs_for_an_active_run_fails_closed(self):
        self.state["runs"]["waiting"] = [run(43, status="waiting")]
        with self.assertRaisesRegex(CheckError, "job inventory"):
            self.check()

    def test_current_job_is_bound_to_exact_run(self):
        for mutation in (
            lambda jobs: jobs[0].update(head_sha="c" * 40),
            lambda jobs: jobs[0].update(head_branch="feature"),
            lambda jobs: jobs[0].update(run_url="https://api.github.com/repos/other/repo/actions/runs/42"),
            lambda jobs: jobs.append(dict(jobs[0], id=103)),
            lambda jobs: jobs.pop(0),
        ):
            with self.subTest(mutation=mutation), self.assertRaises(CheckError):
                self.setUp()
                mutation(self.state["jobs"][RUN_ID])
                self.check()

    def test_current_job_may_still_be_reported_as_queued(self):
        self.state["jobs"][RUN_ID][0]["status"] = "queued"
        self.check()

    def test_other_current_job_states_fail_closed(self):
        for status in ("completed", "waiting", "pending", "unknown", None):
            with self.subTest(status=status), self.assertRaises(CheckError):
                self.state["jobs"][RUN_ID][0]["status"] = status
                self.check()

    def test_dependent_smoke_job_may_not_have_materialized(self):
        self.state["jobs"][RUN_ID].pop()
        self.check()

    def test_one_smoke_job_may_be_queued_waiting_or_pending(self):
        for status in ("queued", "waiting", "pending"):
            with self.subTest(status=status):
                self.state["jobs"][RUN_ID][1]["status"] = status
                self.check()

    def test_duplicate_smoke_jobs_reject(self):
        jobs = self.state["jobs"][RUN_ID]
        jobs.append(dict(jobs[1], id=103))
        with self.assertRaisesRegex(CheckError, "at most one"):
            self.check()

    def test_same_named_jobs_in_other_runs_do_not_get_an_exemption(self):
        self.state["runs"]["queued"] = [run(43, status="queued")]
        for name in ("smoke", "start-runner"):
            with self.subTest(name=name), self.assertRaisesRegex(CheckError, "Another active job"):
                self.state["jobs"][43] = [job(201, 43, name, "queued", ["self-hosted", "linux", "lab-runner"])]
                self.check()

    def test_completed_or_unexpected_smoke_job_states_reject(self):
        for status in ("completed", "in_progress", "unexpected"):
            with self.subTest(status=status), self.assertRaises(CheckError):
                self.state["jobs"][RUN_ID][1]["status"] = status
                self.check()

    def test_smoke_job_requires_exact_runner_labels(self):
        for labels in (
            ["self-hosted", "lab-runner"],
            ["self-hosted", "linux", "lab-runner", "extra"],
            ["self-hosted", "linux", "lab-runner", "linux"],
        ):
            with self.subTest(labels=labels), self.assertRaisesRegex(CheckError, "unexpected status or labels"):
                self.state["jobs"][RUN_ID][1]["labels"] = labels
                self.check()

    def test_consumed_workflow_paths_are_rejected(self):
        for suffix in ("", "-reissued"):
            old_path = f".github/workflows/start-private-runner-once-20261119{suffix}.yml"
            with self.subTest(path=old_path):
                with self.assertRaisesRegex(CheckError, "context"):
                    self.check(context(workflow_ref=f"{REPOSITORY}/{old_path}@refs/heads/main"))
                self.state["runs"]["in_progress"][0]["path"] = old_path
                with self.assertRaisesRegex(CheckError, "current workflow run"):
                    self.check()

    def test_exact_main_validate_success_is_required(self):
        for field, value in (("conclusion", "failure"), ("head_sha", "c" * 40),
                             ("event", "pull_request"), ("path", ".github/workflows/other.yml")):
            with self.subTest(field=field):
                self.setUp()
                self.state["validation"]["workflow_runs"][0][field] = value
                with self.assertRaisesRegex(CheckError, "Validate"):
                    self.check()

    def test_api_query_paths_are_fixed_to_validate_and_active_run_filters(self):
        self.check()
        paths = [path for path, _ in self.paths]
        self.assertEqual(paths[0], (
            f"/repos/{REPOSITORY}/actions/workflows/validate.yml/runs?"
            f"head_sha={SHA}&branch=main&event=push&per_page=100"
        ))
        self.assertEqual(
            [path for path in paths if "/actions/runs?status=" in path],
            [
                f"/repos/{REPOSITORY}/actions/runs?status={status}&per_page=100"
                for status in ACTIVE_RUN_STATUSES
            ],
        )

    def test_incomplete_or_ambiguous_queue_and_job_payloads_reject(self):
        cases = (
            lambda: self.state["runs"]["queued"].append(run(43, status="completed")),
            lambda: self.state["runs"]["queued"].append(run(43, status="queued")),
        )
        for mutation in cases:
            with self.subTest(mutation=mutation), self.assertRaises(CheckError):
                self.setUp()
                mutation()
                self.state["jobs"][43] = []
                self.check()

        self.setUp()
        self.state["runs"]["in_progress"].clear()
        with self.assertRaisesRegex(CheckError, "current workflow run"):
            self.check()

        self.setUp()
        self.state["jobs"][RUN_ID][1]["labels"] = None
        with self.assertRaisesRegex(CheckError, "malformed"):
            self.check()

    def test_only_exact_main_first_attempt_owner_job_context_passes(self):
        mismatches = (
            {"repository": "other/repo"},
            {"ref": "refs/heads/feature"},
            {"workflow_ref": f"{REPOSITORY}/other.yml@refs/heads/main"},
            {"sha": "c" * 40},
            {"run_id": "43"},
            {"run_number": "2"},
            {"run_attempt": "2"},
            {"event_name": "push"},
            {"job": "smoke"},
        )
        for changes in mismatches:
            with self.subTest(changes=changes), self.assertRaises(CheckError):
                self.check(context(**changes))


if __name__ == "__main__":
    unittest.main()

"""Fail closed when another workflow has active work queued for the Lab runner."""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from typing import Callable

from check_lab_image_approval import GitHubReader
from check_state_backend import CheckError

REPOSITORY = "michael-rechani/foundry-agent-accelerator"
WORKFLOW_PATH = ".github/workflows/start-private-runner-once-20261119-api-ready.yml"
ACTIVE_RUN_STATUSES = ("queued", "in_progress", "waiting", "pending")
JOB_STATUSES = {"queued", "in_progress", "waiting", "pending", "completed"}
RUN_ID = re.compile(r"[1-9][0-9]*")


@dataclass(frozen=True)
class StartContext:
    repository: str
    ref: str
    workflow_ref: str
    sha: str
    run_id: str
    run_number: str
    run_attempt: str
    event_name: str
    job: str


def _validate_context(context: StartContext) -> None:
    if not isinstance(context, StartContext) or not all(
        isinstance(value, str) for value in (
            context.repository, context.ref, context.workflow_ref, context.sha,
            context.run_id, context.run_number, context.run_attempt,
            context.event_name, context.job,
        )
    ):
        raise CheckError("Trusted runner-start context is incomplete.")
    if not (
        context.repository == REPOSITORY
        and context.ref == "refs/heads/main"
        and context.workflow_ref
        == f"{REPOSITORY}/{WORKFLOW_PATH}@refs/heads/main"
        and re.fullmatch(r"[0-9a-f]{40}", context.sha)
        and RUN_ID.fullmatch(context.run_id)
        and context.run_number == "1"
        and context.run_attempt == "1"
        and context.event_name == "workflow_dispatch"
        and context.job == "start-runner"
    ):
        raise CheckError("Runner-start context is not the authorized first main run.")


def _collection(
    payload: object, key: str, kind: str, *, allow_empty: bool = False,
) -> list[dict]:
    items = payload.get(key) if isinstance(payload, dict) else None
    total = payload.get("total_count") if isinstance(payload, dict) else None
    if (
        not isinstance(items, list)
        or type(total) is not int
        or total != len(items)
        or (not items and not allow_empty)
    ):
        raise CheckError(f"GitHub {kind} inventory is incomplete.")
    return items


def _verify_job_inventory(payload: object, context: StartContext, run_id: int) -> None:
    jobs = _collection(payload, "jobs", "workflow job")
    seen_ids: set[int] = set()
    current_jobs = []
    smoke_jobs = []
    own_run = run_id == int(context.run_id)
    smoke_labels = {"self-hosted", "linux", "lab-runner"}
    expected_run_url = f"https://api.github.com/repos/{REPOSITORY}/actions/runs/{run_id}"
    for job in jobs:
        if not isinstance(job, dict) or not (
            type(job.get("id")) is int
            and job["id"] > 0
            and job["id"] not in seen_ids
            and type(job.get("run_id")) is int
            and job["run_id"] == run_id
            and isinstance(job.get("name"), str)
            and isinstance(job.get("status"), str)
            and job["status"] in JOB_STATUSES
            and isinstance(job.get("labels"), list)
            and all(isinstance(label, str) for label in job["labels"])
        ):
            raise CheckError("GitHub workflow job evidence is malformed.")
        seen_ids.add(job["id"])
        if own_run and job["name"] == context.job:
            if not (
                job.get("head_sha") == context.sha
                and job.get("head_branch") == "main"
                and job.get("run_url") == expected_run_url
            ):
                raise CheckError("The current runner-start job does not match its run.")
            current_jobs.append(job)
        elif own_run and job["name"] == "smoke":
            if (
                job["status"] not in ("queued", "waiting", "pending")
                or len(job["labels"]) != len(smoke_labels)
                or set(job["labels"]) != smoke_labels
            ):
                raise CheckError("The current runner smoke job has unexpected status or labels.")
            smoke_jobs.append(job)
        elif job["status"] != "completed" and {"self-hosted", "lab-runner"} <= set(job["labels"]):
            raise CheckError("Another active job is queued for the Lab runner.")

    if own_run:
        if (
            len(current_jobs) != 1
            or current_jobs[0]["status"] not in ("queued", "in_progress")
        ):
            raise CheckError("Expected one queued or in-progress runner-start job.")
        if len(smoke_jobs) > 1:
            raise CheckError("Expected at most one runner smoke job.")


def _verify_current_run(run: dict, context: StartContext) -> None:
    repository = run.get("repository")
    actor = run.get("actor")
    if not (
        type(run.get("id")) is int
        and run["id"] == int(context.run_id)
        and type(run.get("run_number")) is int
        and run["run_number"] == 1
        and type(run.get("run_attempt")) is int
        and run["run_attempt"] == 1
        and run.get("event") == "workflow_dispatch"
        and run.get("status") == "in_progress"
        and run.get("head_branch") == "main"
        and run.get("head_sha") == context.sha
        and run.get("path") == WORKFLOW_PATH
        and isinstance(repository, dict)
        and repository.get("full_name") == REPOSITORY
        and isinstance(actor, dict)
        and type(actor.get("id")) is int
        and actor.get("id") == 97264614
    ):
        raise CheckError("The current workflow run is not the authorized first main run.")


def _verify_main_validation(payload: object, context: StartContext) -> None:
    runs = _collection(payload, "workflow_runs", "main Validate run")
    if len(runs) != 1:
        raise CheckError("The exact main Validate run is ambiguous.")
    run = runs[0]
    if not isinstance(run, dict) or not (
        run.get("name") == "Validate"
        and run.get("path") == ".github/workflows/validate.yml"
        and run.get("event") == "push"
        and run.get("head_branch") == "main"
        and run.get("head_sha") == context.sha
        and run.get("status") == "completed"
        and run.get("conclusion") == "success"
    ):
        raise CheckError("The exact current main commit has no successful Validate run.")


def check_runner_queue(
    token: str,
    context: StartContext,
    *,
    reader_factory: Callable[..., GitHubReader] = GitHubReader,
) -> None:
    """Require the exact current run and no other active Lab-runner jobs."""
    _validate_context(context)
    if not isinstance(token, str) or not token:
        raise CheckError("GitHub API token is missing.")
    root = f"/repos/{REPOSITORY}"
    reader = reader_factory(token)
    validation = reader.get_json(
        f"{root}/actions/workflows/validate.yml/runs?"
        f"head_sha={context.sha}&branch=main&event=push&per_page=100",
        kind="main Validate run",
    )
    _verify_main_validation(validation, context)
    current_run_seen = False
    seen_run_ids: set[int] = set()

    for status in ACTIVE_RUN_STATUSES:
        payload = reader.get_json(
            f"{root}/actions/runs?status={status}&per_page=100",
            kind=f"{status} workflow run",
        )
        runs = _collection(
            payload, "workflow_runs", f"{status} workflow run", allow_empty=True,
        )
        for run in runs:
            if not isinstance(run, dict) or type(run.get("id")) is not int or run["id"] <= 0:
                raise CheckError("GitHub workflow run evidence is malformed.")
            if (
                run.get("status") != status
                or type(run.get("run_attempt")) is not int
                or run["run_attempt"] < 1
            ):
                raise CheckError("GitHub workflow run status or attempt is malformed.")
            run_id = run["id"]
            if run_id in seen_run_ids:
                raise CheckError("GitHub workflow run accounting is ambiguous.")
            seen_run_ids.add(run_id)
            if run_id == int(context.run_id):
                if status != "in_progress":
                    raise CheckError("The current workflow run has an unexpected status.")
                _verify_current_run(run, context)
                current_run_seen = True
            jobs = reader.get_json(
                f"{root}/actions/runs/{run_id}/attempts/{run['run_attempt']}/jobs?per_page=100",
                kind="workflow job",
            )
            _verify_job_inventory(jobs, context, run_id)

    if not current_run_seen:
        raise CheckError("The exact current workflow run was not found in the active queue.")


def context_from_environment(environ: dict[str, str] = os.environ) -> StartContext:
    return StartContext(
        repository=environ.get("GITHUB_REPOSITORY", ""),
        ref=environ.get("GITHUB_REF", ""),
        workflow_ref=environ.get("GITHUB_WORKFLOW_REF", ""),
        sha=environ.get("GITHUB_SHA", ""),
        run_id=environ.get("GITHUB_RUN_ID", ""),
        run_number=environ.get("GITHUB_RUN_NUMBER", ""),
        run_attempt=environ.get("GITHUB_RUN_ATTEMPT", ""),
        event_name=environ.get("GITHUB_EVENT_NAME", ""),
        job=environ.get("GITHUB_JOB", ""),
    )


def main(environ: dict[str, str] = os.environ) -> int:
    try:
        check_runner_queue(environ.get("GH_TOKEN", ""), context_from_environment(environ))
    except CheckError as error:
        print(f"::error::{error}", file=sys.stderr)
        return 1
    print("No other active Lab-runner jobs are queued.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

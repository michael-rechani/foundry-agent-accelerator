"""Wait until the recording environment in this workflow run has been approved.

Record library answers runs a billable job behind a required reviewer, on a private
runner that deallocates itself when idle. Its start-runner job runs beside that job and
uses this script to start the runner only once the reviewer has approved the recording:
the runner isn't started for a run that is rejected, and it isn't left to deallocate
while the run waits for an approval.

    python .github/scripts/wait_for_approval.py --job record --environment library-recording

Reads GH_TOKEN, GITHUB_REPOSITORY, GITHUB_RUN_ID and GITHUB_RUN_ATTEMPT, and appends
approved=true or approved=false to GITHUB_OUTPUT. Review history is not scoped to
an attempt, so a rerun must be dispatched as a new workflow instead.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

GH = shutil.which("gh") or "gh"
REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
RUN_ID = re.compile(r"^[0-9]+$")
# A queued job alone is not proof of approval: it can be queued before protection
# rules are evaluated. Require the recording environment's explicit review as well.
RUNNABLE = {"queued", "in_progress"}
FINISHED = {"completed"}
CONFIRMATIONS = 2
MAX_FETCH_ERRORS = 5


class FetchError(RuntimeError):
    pass


def check_context(repository: str, run_id: str) -> None:
    if not REPOSITORY.fullmatch(repository) or not RUN_ID.fullmatch(run_id):
        raise FetchError("GITHUB_REPOSITORY or GITHUB_RUN_ID isn't in the expected form.")


def fetch_jobs(repository: str, run_id: str) -> list[dict]:
    check_context(repository, run_id)
    result = subprocess.run(  # noqa: S603 - fixed arguments; both values were checked above
        [GH, "api", "--paginate", f"repos/{repository}/actions/runs/{run_id}/jobs?per_page=100",
         "--jq", ".jobs[] | {name, status}"],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        raise FetchError(result.stderr.strip() or f"gh api exited {result.returncode}")
    try:
        jobs = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    except ValueError as error:
        raise FetchError(f"The job list wasn't JSON: {error}") from error
    if not all(isinstance(job, dict) for job in jobs):
        raise FetchError("The job list contained an unexpected entry.")
    return jobs


def fetch_reviews(repository: str, run_id: str) -> list[dict]:
    check_context(repository, run_id)
    result = subprocess.run(  # noqa: S603 - fixed arguments; both values were checked above
        [GH, "api", f"repos/{repository}/actions/runs/{run_id}/approvals"],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        raise FetchError(result.stderr.strip() or f"gh api exited {result.returncode}")
    try:
        reviews = json.loads(result.stdout)
    except ValueError as error:
        raise FetchError(f"The review history wasn't JSON: {error}") from error
    if not isinstance(reviews, list):
        raise FetchError("The review history wasn't a list.")
    return reviews


def job_state(jobs: list[dict], name: str) -> str:
    """Return "waiting", "runnable" or "finished" for the named job."""
    job = next((item for item in jobs if item.get("name") == name), None)
    status = job.get("status") if job else None
    if status in FINISHED:
        return "finished"
    if status in RUNNABLE:
        return "runnable"
    return "waiting"


def review_state(reviews: list[dict], environment: str) -> str:
    approved = False
    for review in reviews:
        if not isinstance(review, dict) or not isinstance(review.get("environments"), list):
            raise FetchError("The review history contained an unexpected entry.")
        environments = review["environments"]
        if any(not isinstance(item, dict) or not isinstance(item.get("name"), str) for item in environments):
            raise FetchError("The review history contained an unexpected environment.")
        if not any(item["name"] == environment for item in environments):
            continue
        state = review.get("state")
        if state == "rejected":
            return "rejected"
        if state == "approved":
            approved = True
        else:
            raise FetchError("The recording environment has an unknown review state.")
    return "approved" if approved else "waiting"


def wait(
    fetch: Callable[[], tuple[list[dict], list[dict]]],
    name: str,
    environment: str,
    *,
    timeout: float,
    interval: float,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> str:
    """Poll until the job is approved or finished; raise TimeoutError if it is neither in time.

    A runnable job and its explicit environment approval must hold for CONFIRMATIONS
    polls in a row. A failed poll is retried, and several in a row stop the wait.
    """
    deadline = clock() + timeout
    approved_polls = errors = 0
    while True:
        try:
            jobs, reviews = fetch()
            state = job_state(jobs, name)
            review = review_state(reviews, environment)
            errors = 0
        except FetchError as error:
            errors += 1
            print(f"::warning::Couldn't read the job or review state ({errors} of {MAX_FETCH_ERRORS}): {error}")
            if errors >= MAX_FETCH_ERRORS:
                raise
            state = review = "waiting"
        if state == "finished":
            return "finished"
        if review == "rejected":
            return "rejected"
        approved_polls = approved_polls + 1 if state == "runnable" and review == "approved" else 0
        if approved_polls >= CONFIRMATIONS:
            return "approved"
        if clock() + interval > deadline:
            raise TimeoutError(name)
        sleep(interval)


def write_output(path: str | None, approved: bool) -> None:
    if path:
        with Path(path).open("a", encoding="utf-8") as output:
            output.write(f"approved={'true' if approved else 'false'}\n")


def main(argv: list[str] | None = None, environ: dict[str, str] | None = None, **timing) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--job", required=True, help="id of the approval-gated job to wait for")
    parser.add_argument("--environment", required=True, help="environment whose review authorizes the recording")
    parser.add_argument("--timeout-minutes", type=float, default=120)
    parser.add_argument("--interval-seconds", type=float, default=15)
    args = parser.parse_args(argv)
    environ = os.environ if environ is None else environ
    repository, run_id = environ.get("GITHUB_REPOSITORY", ""), environ.get("GITHUB_RUN_ID", "")
    output = environ.get("GITHUB_OUTPUT")
    if environ.get("GITHUB_RUN_ATTEMPT") != "1":
        print("::error::Runner wake-up requires a fresh workflow dispatch; review history cannot be "
              "matched safely to a rerun attempt. The runner VM was not started.")
        write_output(output, False)
        return 1
    try:
        outcome = wait(
            lambda: (fetch_jobs(repository, run_id), fetch_reviews(repository, run_id)),
            args.job, args.environment,
            timeout=args.timeout_minutes * 60, interval=args.interval_seconds, **timing,
        )
    except TimeoutError:
        print(f"::error::The {args.job} job did not have both an approved review and a runnable job within "
              f"{args.timeout_minutes:g} minutes, so the runner VM was not started. Dispatch a fresh run "
              "or arrange an approved manual start.")
        write_output(output, False)
        return 1
    except FetchError:
        print("::error::The job or review state couldn't be read, so the runner VM was not started.")
        write_output(output, False)
        return 1
    if outcome in {"finished", "rejected"}:
        print(f"::notice::The {args.job} job {outcome}, so this job did not start the runner VM.")
        write_output(output, False)
        return 0
    print(f"The {args.job} job was approved. Starting the runner VM.")
    write_output(output, True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

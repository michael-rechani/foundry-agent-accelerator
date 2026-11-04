"""Wait until a job in this workflow run has been approved, then say so.

Record library answers runs a billable job behind a required reviewer, on a private
runner that deallocates itself when idle. Its start-runner job runs beside that job and
uses this script to start the runner only once the reviewer has approved the recording:
the runner isn't started for a run that is rejected, and it isn't left to deallocate
while the run waits for an approval.

    python .github/scripts/wait_for_approval.py --job record

Reads GH_TOKEN, GITHUB_REPOSITORY and GITHUB_RUN_ID, and appends approved=true or
approved=false to the file named by GITHUB_OUTPUT. It exits 1 if the job isn't
approved within --timeout-minutes, so the run says why the runner wasn't started.
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
# GitHub reports a job that waits for a reviewer as waiting. Once it is approved it is queued until
# a runner takes it, and in progress after that. A status this script doesn't know counts as waiting,
# so it can delay the runner but never start it for a job nobody approved.
RUNNING = {"queued", "in_progress"}
FINISHED = {"completed"}
CONFIRMATIONS = 2
MAX_FETCH_ERRORS = 5


class FetchError(RuntimeError):
    pass


def fetch_jobs(repository: str, run_id: str) -> list[dict]:
    if not REPOSITORY.fullmatch(repository) or not RUN_ID.fullmatch(run_id):
        raise FetchError("GITHUB_REPOSITORY or GITHUB_RUN_ID isn't in the expected form.")
    result = subprocess.run(  # noqa: S603 - fixed arguments; both values were checked above
        [GH, "api", "--paginate", f"repos/{repository}/actions/runs/{run_id}/jobs?per_page=100",
         "--jq", ".jobs[] | {name, status}"],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        raise FetchError(result.stderr.strip() or f"gh api exited {result.returncode}")
    try:
        return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    except ValueError as error:
        raise FetchError(f"The job list wasn't JSON: {error}") from error


def job_state(jobs: list[dict], name: str) -> str:
    """Return "waiting", "approved" or "finished" for the named job."""
    job = next((item for item in jobs if item.get("name") == name), None)
    status = job.get("status") if job else None
    if status in FINISHED:
        return "finished"
    if status in RUNNING:
        return "approved"
    return "waiting"


def wait(
    fetch: Callable[[], list[dict]],
    name: str,
    *,
    timeout: float,
    interval: float,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> str:
    """Poll until the job is approved or finished; raise TimeoutError if it is neither in time.

    An approved state has to hold for CONFIRMATIONS polls in a row, so a job that is only briefly
    queued before it starts waiting for its reviewer can't start the runner. A failed poll is
    retried, and several in a row stop the wait.
    """
    deadline = clock() + timeout
    approved_polls = errors = 0
    while True:
        try:
            state = job_state(fetch(), name)
            errors = 0
        except FetchError as error:
            errors += 1
            print(f"::warning::Couldn't read the job list ({errors} of {MAX_FETCH_ERRORS}): {error}")
            if errors >= MAX_FETCH_ERRORS:
                raise
            state = "waiting"
        if state == "finished":
            return "finished"
        approved_polls = approved_polls + 1 if state == "approved" else 0
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
    parser.add_argument("--timeout-minutes", type=float, default=120)
    parser.add_argument("--interval-seconds", type=float, default=15)
    args = parser.parse_args(argv)
    environ = os.environ if environ is None else environ
    repository, run_id = environ.get("GITHUB_REPOSITORY", ""), environ.get("GITHUB_RUN_ID", "")
    output = environ.get("GITHUB_OUTPUT")
    try:
        outcome = wait(
            lambda: fetch_jobs(repository, run_id), args.job,
            timeout=args.timeout_minutes * 60, interval=args.interval_seconds, **timing,
        )
    except TimeoutError:
        print(f"::error::The {args.job} job wasn't approved within {args.timeout_minutes:g} minutes, so the "
              "runner VM was not started. Start it by hand and approve again, or dispatch the workflow again.")
        write_output(output, False)
        return 1
    except FetchError:
        print("::error::The job list couldn't be read, so the runner VM was not started.")
        write_output(output, False)
        return 1
    if outcome == "finished":
        print(f"::notice::The {args.job} job finished without being approved, so the runner VM was not started.")
        write_output(output, False)
        return 0
    print(f"The {args.job} job was approved. Starting the runner VM.")
    write_output(output, True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

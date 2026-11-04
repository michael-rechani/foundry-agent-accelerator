import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import wait_for_approval as approval


def jobs(**statuses):
    return [{"name": name, "status": status} for name, status in statuses.items()]


class Clock:
    """A clock that only moves when the test sleeps, so no test really waits."""

    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class JobStateTests(unittest.TestCase):
    def test_states_by_status(self):
        for status, expected in [
            ("waiting", "waiting"),
            ("pending", "waiting"),
            ("requested", "waiting"),
            ("queued", "approved"),
            ("in_progress", "approved"),
            ("completed", "finished"),
            ("something-new", "waiting"),
            (None, "waiting"),
        ]:
            with self.subTest(status=status):
                self.assertEqual(approval.job_state(jobs(record=status), "record"), expected)

    def test_a_missing_job_is_still_waiting(self):
        self.assertEqual(approval.job_state([], "record"), "waiting")

    def test_only_the_named_job_counts(self):
        listed = jobs(**{"start-runner": "in_progress"}, record="waiting")
        self.assertEqual(approval.job_state(listed, "record"), "waiting")
        self.assertEqual(approval.job_state(listed, "other"), "waiting")


class WaitTests(unittest.TestCase):
    def run_wait(self, polls, timeout=600, interval=15):
        clock = Clock()
        remaining = list(polls)
        calls = []

        def fetch():
            calls.append(clock.now)
            item = remaining.pop(0) if len(remaining) > 1 else remaining[0]
            if isinstance(item, Exception):
                raise item
            return item

        with contextlib.redirect_stdout(io.StringIO()):
            outcome = approval.wait(fetch, "record", timeout=timeout, interval=interval,
                                    sleep=clock.sleep, clock=clock)
        return outcome, calls

    def test_waits_while_the_reviewer_hasnt_approved(self):
        outcome, calls = self.run_wait(
            [jobs(record="waiting")] * 4 + [jobs(record="queued")] * 2)
        self.assertEqual(outcome, "approved")
        self.assertEqual(len(calls), 6)

    def test_one_approved_poll_isnt_enough(self):
        outcome, calls = self.run_wait(
            [jobs(record="waiting"), jobs(record="queued"), jobs(record="waiting"),
             jobs(record="queued"), jobs(record="in_progress")])
        self.assertEqual(outcome, "approved")
        self.assertEqual(len(calls), 5)

    def test_a_job_that_is_already_running_counts_as_approved(self):
        outcome, _ = self.run_wait([jobs(record="in_progress")])
        self.assertEqual(outcome, "approved")

    def test_a_rejected_or_finished_job_never_starts_the_runner(self):
        outcome, calls = self.run_wait([jobs(record="waiting"), jobs(record="completed")])
        self.assertEqual(outcome, "finished")
        self.assertEqual(len(calls), 2)

    def test_a_job_that_never_appears_times_out(self):
        with self.assertRaises(TimeoutError):
            self.run_wait([[]], timeout=60, interval=15)

    def test_a_job_that_is_never_approved_times_out(self):
        with self.assertRaises(TimeoutError):
            self.run_wait([jobs(record="waiting")], timeout=60, interval=15)

    def test_an_unknown_status_is_never_treated_as_approval(self):
        with self.assertRaises(TimeoutError):
            self.run_wait([jobs(record="mystery")], timeout=60, interval=15)

    def test_the_wait_stops_at_the_timeout_without_sleeping_past_it(self):
        clock = Clock()
        with self.assertRaises(TimeoutError):
            approval.wait(lambda: jobs(record="waiting"), "record", timeout=40, interval=15,
                          sleep=clock.sleep, clock=clock)
        self.assertLessEqual(clock.now, 40)

    def test_a_failed_poll_is_retried(self):
        outcome, calls = self.run_wait(
            [approval.FetchError("rate limited"), jobs(record="queued"), jobs(record="queued")])
        self.assertEqual(outcome, "approved")
        self.assertEqual(len(calls), 3)

    def test_a_failed_poll_resets_the_approval_streak(self):
        outcome, calls = self.run_wait(
            [jobs(record="queued"), approval.FetchError("blip"), jobs(record="queued"), jobs(record="queued")])
        self.assertEqual(outcome, "approved")
        self.assertEqual(len(calls), 4)

    def test_repeated_failures_stop_the_wait(self):
        with self.assertRaises(approval.FetchError):
            self.run_wait([approval.FetchError("down")])


class FetchJobsTests(unittest.TestCase):
    def run_fetch(self, stdout="", returncode=0, stderr="", repository="octo/repo", run_id="123"):
        completed = mock.Mock(returncode=returncode, stdout=stdout, stderr=stderr)
        with mock.patch.object(approval.subprocess, "run", return_value=completed) as run:
            return approval.fetch_jobs(repository, run_id), run

    def test_reads_one_object_per_line(self):
        listed, run = self.run_fetch('{"name":"record","status":"waiting"}\n\n{"name":"start-runner","status":"in_progress"}\n')
        self.assertEqual(listed, jobs(record="waiting", **{"start-runner": "in_progress"}))
        command = run.call_args.args[0]
        self.assertIn("repos/octo/repo/actions/runs/123/jobs?per_page=100", command)
        self.assertIn("--paginate", command)

    def test_no_jobs_is_an_empty_list(self):
        self.assertEqual(self.run_fetch("")[0], [])

    def test_a_failing_gh_is_a_fetch_error(self):
        with self.assertRaisesRegex(approval.FetchError, "boom"):
            self.run_fetch(returncode=1, stderr="boom")

    def test_output_that_isnt_json_is_a_fetch_error(self):
        with self.assertRaises(approval.FetchError):
            self.run_fetch("not json")

    def test_values_that_could_change_the_request_are_refused(self):
        for repository, run_id in [("octo", "1"), ("octo/repo/extra", "1"), ("octo/repo", "1/../2"),
                                   ("octo/repo", ""), ("", "1"), ("octo/repo?x=1", "1")]:
            with self.subTest(repository=repository, run_id=run_id):
                with mock.patch.object(approval.subprocess, "run") as run:
                    with self.assertRaises(approval.FetchError):
                        approval.fetch_jobs(repository, run_id)
                run.assert_not_called()


class MainTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.output = Path(self.temp.name) / "output"
        self.environ = {"GITHUB_REPOSITORY": "octo/repo", "GITHUB_RUN_ID": "9",
                        "GITHUB_OUTPUT": str(self.output)}
        self.addCleanup(self.temp.cleanup)

    def run_main(self, polls, *extra):
        clock = Clock()
        remaining = list(polls)

        def fetch(repository, run_id):
            self.assertEqual((repository, run_id), ("octo/repo", "9"))
            item = remaining.pop(0) if len(remaining) > 1 else remaining[0]
            if isinstance(item, Exception):
                raise item
            return item

        stdout = io.StringIO()
        with mock.patch.object(approval, "fetch_jobs", fetch), contextlib.redirect_stdout(stdout):
            code = approval.main(["--job", "record", "--timeout-minutes", "1", *extra],
                                 self.environ, sleep=clock.sleep, clock=clock)
        written = self.output.read_text(encoding="utf-8") if self.output.exists() else ""
        return code, written, stdout.getvalue()

    def test_approval_is_reported_as_an_output(self):
        code, written, shown = self.run_main([jobs(record="waiting"), jobs(record="queued")])
        self.assertEqual((code, written), (0, "approved=true\n"))
        self.assertIn("was approved", shown)

    def test_a_rejected_run_reports_false_and_still_succeeds(self):
        code, written, shown = self.run_main([jobs(record="completed")])
        self.assertEqual((code, written), (0, "approved=false\n"))
        self.assertIn("::notice::", shown)

    def test_a_timeout_fails_the_job_and_says_why(self):
        code, written, shown = self.run_main([jobs(record="waiting")])
        self.assertEqual((code, written), (1, "approved=false\n"))
        self.assertIn("::error::The record job wasn't approved within 1 minutes", shown)
        self.assertIn("runner VM was not started", shown)

    def test_a_job_list_that_cant_be_read_fails_the_job(self):
        code, written, shown = self.run_main([approval.FetchError("down")])
        self.assertEqual((code, written), (1, "approved=false\n"))
        self.assertIn("runner VM was not started", shown)

    def test_the_job_name_is_required(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as stop:
            approval.main([], self.environ)
        self.assertEqual(stop.exception.code, 2)

    def test_no_output_file_is_fine(self):
        self.environ.pop("GITHUB_OUTPUT")
        code, written, _ = self.run_main([jobs(record="queued")])
        self.assertEqual((code, written), (0, ""))


if __name__ == "__main__":
    unittest.main()

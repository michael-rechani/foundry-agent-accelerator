import contextlib
import io
import os
import signal
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import check_foundry_prerequisites as subject


class PracticalTests(unittest.TestCase):
    def test_workflow_embeds_exact_launcher_and_no_checkout(self):
        workflow = (Path(__file__).parents[1] / "workflows" / "check-foundry-prerequisites.yml").read_text()
        section = workflow.split("            python3 -I - <<'FOUNDATION_PY'\n", 1)[1]
        body = section.split("          FOUNDATION_PY\n", 1)[0]
        self.assertEqual("\n".join(line[10:] for line in body.splitlines()) + "\n",
                         Path(subject.__file__).read_text())
        self.assertNotIn("actions/checkout", workflow)
        self.assertNotIn("rm -rf", workflow)
        self.assertIn("environment: terraform-state", workflow)
        self.assertIn("github.ref == 'refs/heads/main' && github.ref_protected", workflow)
        self.assertNotIn("id-token:", workflow)

    def test_synthetic_success_and_nonzero_never_signal(self):
        with tempfile.TemporaryDirectory() as root:
            for code, expected in (("print('fictional')", 0), ("raise SystemExit(7)", 7)):
                with mock.patch.object(subject.os, "kill") as kill, \
                     mock.patch.object(subject.os, "killpg") as group:
                    result = subject.command([sys.executable, "-c", code], root, {})
                    self.assertEqual(result.returncode, expected)
                    kill.assert_not_called()
                    group.assert_not_called()

    def test_timeout_and_output_limit_leave_owned_state_and_never_signal(self):
        with tempfile.TemporaryDirectory() as root:
            marker = Path(root) / "fictional-owned"
            marker.write_text("retain")
            real = subject.time.monotonic
            start = real()
            with mock.patch.object(subject.time, "monotonic",
                                   side_effect=lambda: start + (real() - start) * 1000), \
                 mock.patch.object(subject.os, "kill") as kill, \
                 mock.patch.object(subject.os, "killpg") as group:
                with self.assertRaises(subprocess.TimeoutExpired):
                    subject.command([sys.executable, "-c", "import time;time.sleep(.4)"], root, {})
                kill.assert_not_called()
                group.assert_not_called()
            self.assertEqual(marker.read_text(), "retain")
            with mock.patch.object(subject, "_CAPTURE_LIMIT", 4):
                with self.assertRaises(subject.CheckError):
                    subject.command([sys.executable, "-c", "print('fictional')"], root, {})

    def test_fixed_failure_and_uncertain_child_notice(self):
        with mock.patch.object(subject, "_PROCESS_STARTED", True):
            output, errors = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
                subject.report_failure(OSError("fictional-private-path"))
            self.assertEqual(output.getvalue(), "failure_stage=unexpected_io\nowned_process_may_be_running=true\n")
            self.assertNotIn("fictional", output.getvalue() + errors.getvalue())

    def test_check_runs_pinned_script_and_postcheck_with_isolated_mock_tools(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            calls = []

            def fake_download(url, digest, path, limit):
                self.assertEqual((url, digest), (subject.SKILL_URL, subject.SKILL_SHA256))
                path.write_bytes(b"fictional")

            def fake_command(args, cwd, env):
                calls.append((args, cwd, env))
                if args[-1] == "version":
                    return subprocess.CompletedProcess(args, 0, "azd version 1.37.3\n", "")
                return subprocess.CompletedProcess(args, 0, subject.READY, "")

            with mock.patch.object(subject, "download", side_effect=fake_download), \
                 mock.patch.object(subject, "validate_upstream_user_agent") as validate, \
                 mock.patch.object(subject, "install_azd") as install, \
                 mock.patch.object(subject, "command", side_effect=fake_command):
                self.assertEqual(subject.check(root, "fixture"), "1.37.3")
            validate.assert_called_once()
            install.assert_called_once_with(root)
            self.assertEqual(len(calls), 2)
            self.assertEqual(calls[0][0][1], str(root / "skill" / "scripts" / "check-and-setup-dependencies.sh"))
            self.assertEqual(calls[1][0], [str(root / "bin" / "azd"), "version"])
            self.assertEqual(calls[0][2]["AZURE_CONFIG_DIR"], str(root / "azure-config"))
            self.assertNotIn("ACTIONS_ID_TOKEN_REQUEST_TOKEN", calls[0][2])

    def test_pipe_closing_grandchild_can_survive_synchronous_success(self):
        with tempfile.TemporaryDirectory() as root:
            marker = str(Path(root) / "late-fictional-write")
            child = ("import os,time,pathlib;os.close(1);os.close(2);"
                     f"time.sleep(.3);pathlib.Path({marker!r}).write_text('finished')")
            parent = ("import subprocess,sys;"
                      f"subprocess.Popen([sys.executable,'-c',{child!r}])")
            with mock.patch.object(subject.os, "kill") as kill, \
                 mock.patch.object(subject.os, "killpg") as group:
                result = subject.command([sys.executable, "-c", parent], root, {})
                self.assertEqual(result.returncode, 0)
                kill.assert_not_called()
                group.assert_not_called()
            time.sleep(.6)
            self.assertEqual(Path(marker).read_text(), "finished")

    def test_run_preserves_owned_directory_and_scopes_result(self):
        with tempfile.TemporaryDirectory() as parent:
            root = Path(parent) / "owned"
            root.mkdir()
            marker = root / "fictional"
            marker.write_text("retain")
            with mock.patch.object(subject, "context"), \
                 mock.patch.object(subject, "invocation_user_agent", return_value="fixture"), \
                 mock.patch.object(subject, "retained_root", return_value=root), \
                 mock.patch.object(subject, "check", return_value="1.37.3"), \
                 mock.patch.object(subject.shutil, "rmtree") as remove:
                self.assertEqual(subject.run(), "1.37.3")
                remove.assert_not_called()
            self.assertEqual(marker.read_text(), "retain")

    def test_retention_rejects_bad_managed_roots_before_mkdtemp(self):
        meta = mock.Mock(st_mode=stat.S_IFDIR | 0o1777, st_uid=0)
        with mock.patch.object(Path, "lstat", return_value=meta), \
             mock.patch.object(Path, "resolve", side_effect=lambda: Path("/var/tmp")), \
             mock.patch.object(Path, "is_dir", return_value=True), \
             mock.patch.dict(os.environ, {"RUNNER_TEMP": "/var/tmp/runner", "GITHUB_WORKSPACE": "/work"}), \
             mock.patch.object(subject.tempfile, "mkdtemp") as create:
            with self.assertRaises(subject.CheckError):
                subject.retained_root()
            create.assert_not_called()


if __name__ == "__main__":
    unittest.main()

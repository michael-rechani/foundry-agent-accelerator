import ast
import contextlib
import fcntl
import hashlib
import io
import json
import os
import resource
import stat
import subprocess
import sys
import tarfile
import tempfile
import textwrap
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib import error, request

import check_foundry_prerequisites as helper
import check_foundry_prerequisites_retained as retained
import test_check_foundry_prerequisites as fixtures


TRACKING = "github_12345678-1234-1234-1234-123456789abc"


class FailingCloseBytesIO(io.BytesIO):
    def close(self):
        if not self.closed:
            super().close()
            raise OSError("private close failure")


class RetainedPrerequisiteTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.home = self.base / "home"
        self.home.mkdir(mode=0o700)
        self.managed = self.base / "runner-work"
        self.temp = self.managed / "_temp"
        self.temp.mkdir(parents=True)
        self.workspace = self.managed / "repo" / "repo"
        self.workspace.mkdir(parents=True)
        self.root = self.base / "state"
        self.root.mkdir(mode=0o700)
        self.assertNotEqual(os.geteuid(), 0, "Hosted tests must run as non-root.")

    def reserve(self, home=None, temp=None, workspace=None, run_id="123", attempt="1"):
        return retained.reserve_state(
            home or self.home,
            temp or self.temp,
            workspace or self.workspace,
            run_id,
            attempt,
        )

    def fake_downloads(self):
        fake_azd = fixtures.FAKE_AZD.replace(
            b"printf '%s\\n' \"$*\" >>",
            b"env > \"$AZD_CONFIG_DIR/environment\"\nprintf '%s\\n' \"$*\" >>",
            1,
        )
        with patch.object(fixtures, "FAKE_AZD", fake_azd):
            archive = fixtures.archive_bytes()
        opener = self.enterContext(patch.object(helper.request, "build_opener")).return_value

        def fake_open(req, timeout):
            self.assertEqual(timeout, 60)
            self.assertEqual(dict(req.header_items()), {"User-agent": "foundry-prerequisite-check"})
            if req.full_url == helper.SKILL_URL:
                body = fixtures.SKILL
            elif req.full_url == helper.AZD_URL:
                body = archive
            else:
                self.fail("An unpinned URL was requested")
            response = io.BytesIO(body)
            response.status = 200
            return response

        opener.open.side_effect = fake_open
        self.enterContext(
            patch.object(helper, "AZD_SHA256", hashlib.sha256(archive).hexdigest())
        )
        return opener

    def test_owner_only_state_is_unique_and_retained(self):
        state = self.reserve()
        self.assertEqual(stat.S_IMODE(state.stat().st_mode), 0o700)
        marker = state / "owned"
        marker.write_text("retained")
        with self.assertRaises(FileExistsError):
            self.reserve()
        self.assertEqual(marker.read_text(), "retained")
        self.assertNotEqual(state, self.reserve(attempt="2"))

    def test_existing_symlink_is_not_followed_or_removed(self):
        external = self.base / "external"
        external.mkdir()
        marker = external / "keep"
        marker.write_text("original")
        link = self.home / ".foundry-prerequisites-123-1"
        link.symlink_to(external, target_is_directory=True)
        with self.assertRaises(FileExistsError):
            self.reserve()
        self.assertTrue(link.is_symlink())
        self.assertEqual(marker.read_text(), "original")

    def test_shared_writable_or_symlink_home_fails_before_reservation(self):
        self.home.chmod(0o770)
        with self.assertRaisesRegex(helper.CheckError, "storage"):
            self.reserve()
        self.assertEqual(list(self.home.iterdir()), [])
        self.home.chmod(0o700)
        link = self.base / "linked-home"
        link.symlink_to(self.home, target_is_directory=True)
        with self.assertRaisesRegex(helper.CheckError, "storage"):
            self.reserve(home=link)

    def test_runner_managed_parent_and_workspace_are_excluded(self):
        managed_temp = self.home / "_temp"
        managed_temp.mkdir()
        with self.assertRaisesRegex(helper.CheckError, "storage"):
            self.reserve(temp=managed_temp)
        with self.assertRaisesRegex(helper.CheckError, "storage"):
            self.reserve(workspace=self.home)
        self.assertFalse((self.home / ".foundry-prerequisites-123-1").exists())

    def test_unknown_temp_layout_and_root_user_are_rejected(self):
        unexpected = self.base / "other-temp"
        unexpected.mkdir()
        with self.assertRaisesRegex(helper.CheckError, "storage"):
            self.reserve(temp=unexpected)
        with patch.object(retained.os, "geteuid", return_value=0):
            with self.assertRaisesRegex(helper.CheckError, "storage"):
                self.reserve()

    def test_invalid_run_identifiers_do_not_create_state(self):
        for value in ("", "0", "12/3", "../1"):
            with self.subTest(value=value), self.assertRaisesRegex(helper.CheckError, "context"):
                self.reserve(run_id=value)
        self.assertEqual(list(self.home.iterdir()), [])

    def test_tracking_marker_is_required_and_preserved_only_when_well_formed(self):
        with patch.dict(os.environ, {"RUNNER_TRACKING_ID": TRACKING}, clear=True):
            self.assertEqual(retained.tracking_id(), TRACKING)
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(helper.CheckError, "tracking"):
                retained.tracking_id()
        for value in ("", "github_bad", "private-token", TRACKING + "\n", "a" * 300):
            with self.subTest(value=value), patch.dict(
                os.environ, {"RUNNER_TRACKING_ID": value}, clear=True
            ):
                with self.assertRaisesRegex(helper.CheckError, "tracking"):
                    retained.tracking_id()

    def test_missing_tracking_marker_refuses_before_state_download_or_spawn(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(
            retained, "context", return_value=(self.temp, self.workspace)
        ), patch.object(
            helper, "invocation_user_agent", return_value=fixtures.UPSTREAM_AGENT
        ), patch.object(
            retained, "reserve_state"
        ) as reserve, patch.object(
            helper, "download"
        ) as download, patch.object(
            retained, "check_pidfd_support"
        ) as pidfd:
            with self.assertRaisesRegex(helper.CheckError, "tracking"):
                retained.run()
            reserve.assert_not_called()
            download.assert_not_called()
            pidfd.assert_not_called()
        with patch.object(helper, "isolated_environment") as environment:
            with self.assertRaisesRegex(helper.CheckError, "tracking"):
                retained.check(self.root, fixtures.UPSTREAM_AGENT, "")
            environment.assert_not_called()

    def test_download_http_errors_close_response_before_sanitized_failure(self):
        for body_type in (io.BytesIO, FailingCloseBytesIO):
            with self.subTest(body=body_type.__name__):
                body = body_type(b"private response content")
                failure = error.HTTPError(helper.SKILL_URL, 403, "private response", {}, body)
                destination = self.root / "not-created"
                with patch.object(helper.request, "build_opener") as opener:
                    opener.return_value.open.side_effect = failure
                    with self.assertRaisesRegex(helper.CheckError, "download") as raised:
                        helper.download(helper.SKILL_URL, helper.SKILL_SHA256, destination, 1024)
                self.assertTrue(body.closed)
                self.assertFalse(destination.exists())
                self.assertNotIn("private", str(raised.exception))

    def test_rejected_redirects_close_response_without_exposing_location(self):
        handler = helper.PublicRedirect()
        for location in (
            "http://github.com/private-location",
            "https://example.invalid/private-location",
            "https://github.com:invalid/private-location",
            "https://[invalid/private-location",
        ):
            for body_type in (io.BytesIO, FailingCloseBytesIO):
                with self.subTest(location=location, body=body_type.__name__):
                    body = body_type(b"private response content")
                    with self.assertRaisesRegex(helper.CheckError, "download") as raised:
                        handler.redirect_request(None, body, 302, "redirect", {}, location)
                    self.assertTrue(body.closed)
                    self.assertNotIn("private", str(raised.exception))

    def test_main_context_requires_exact_protected_workflow_and_runner(self):
        repo = "michael-rechani/foundry-agent-accelerator"
        sha = "a" * 40
        env = {
            "GITHUB_REPOSITORY": repo,
            "GITHUB_SHA": sha,
            "CHECK_WORKFLOW_SHA": sha,
            "CHECK_WORKFLOW_REF": (
                f"{repo}/.github/workflows/check-foundry-prerequisites-retained.yml"
                "@refs/heads/main"
            ),
            "RUNNER_ENVIRONMENT": "self-hosted",
            "GITHUB_WORKSPACE": str(self.workspace),
        }
        with patch.dict(os.environ, env, clear=True), patch.object(
            helper, "context", return_value=(self.temp, "unused")
        ):
            self.assertEqual(retained.context(), (self.temp, self.workspace))
            for key, bad in (
                ("GITHUB_REPOSITORY", "other/repo"),
                ("GITHUB_SHA", "bad"),
                ("CHECK_WORKFLOW_SHA", "b" * 40),
                ("CHECK_WORKFLOW_REF", "other"),
                ("RUNNER_ENVIRONMENT", "github-hosted"),
                ("GITHUB_WORKSPACE", "relative"),
            ):
                with self.subTest(key=key), patch.dict(os.environ, {key: bad}):
                    with self.assertRaisesRegex(helper.CheckError, "context"):
                        retained.context()

    def test_bad_dispatch_input_fails_before_state_or_download(self):
        event = self.base / "event.json"
        env = {
            "GITHUB_EVENT_PATH": str(event),
            "GITHUB_RUN_ID": "123",
            "GITHUB_RUN_ATTEMPT": "1",
        }
        with patch.dict(os.environ, env, clear=True), patch.object(
            retained, "context", return_value=(self.temp, self.workspace)
        ), patch.object(retained, "reserve_state") as reserve, patch.object(
            helper, "download"
        ) as download:
            for value in ("", "bad;command", "bad\nvalue", "x" * 65, None):
                with self.subTest(value=value):
                    event.write_text(json.dumps({"inputs": {"user_agent": value}}))
                    with self.assertRaisesRegex(helper.CheckError, "context"):
                        retained.run()
            reserve.assert_not_called()
            download.assert_not_called()

    def test_exact_pinned_skill_with_fictional_downloads_and_tools(self):
        opener = self.fake_downloads()
        inherited = {
            "GH_TOKEN": "fixture-private-token",
            "AZURE_CLIENT_SECRET": "fixture-private-secret",
            "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "fixture-private-oidc",
            "BASH_ENV": "fixture-private-startup",
            "HTTP_PROXY": "fixture-private-proxy",
        }
        with patch.dict(os.environ, inherited, clear=True):
            version = retained.check(self.root, fixtures.UPSTREAM_AGENT, TRACKING)
        self.assertEqual(version, "1.37.3")
        self.assertEqual(opener.open.call_count, 2)
        self.assertEqual(
            (self.root / "azd-config" / "calls").read_text().splitlines(),
            [
                "extension list --installed --output json",
                "extension install microsoft.foundry",
                "version",
            ],
        )
        environment = (self.root / "azd-config" / "environment").read_text().splitlines()
        for secret in inherited:
            self.assertFalse(any(line.startswith(secret + "=") for line in environment))
        self.assertIn(f"RUNNER_TRACKING_ID={TRACKING}", environment)
        self.assertIn(f"AZD_CONFIG_DIR={self.root / 'azd-config'}", environment)
        self.assertIn("AZURE_DEV_USER_AGENT=microsoft_foundry_skill", environment)
        self.assertTrue((self.root / "skill" / "scripts" / "check-and-setup-dependencies.sh").exists())
        self.assertTrue((self.root / "azd.tar.gz").exists())

    def test_wrong_user_agent_stops_before_tool_install(self):
        opener = self.fake_downloads()
        with self.assertRaisesRegex(helper.CheckError, "context"):
            retained.check(self.root, "wrong-agent", TRACKING)
        self.assertEqual(opener.open.call_count, 1)
        self.assertFalse((self.root / "bin" / "azd").exists())
        self.assertTrue((self.root / "skill" / "scripts" / "check-and-setup-dependencies.sh").exists())

    def test_checksum_failure_stops_before_tool_install(self):
        opener = self.fake_downloads()
        response = io.BytesIO(b"fixture-modified-script")
        response.status = 200
        opener.open.return_value = response
        opener.open.side_effect = None
        with self.assertRaisesRegex(helper.CheckError, "checksum"):
            retained.check(self.root, fixtures.UPSTREAM_AGENT, TRACKING)
        self.assertFalse((self.root / "bin" / "azd").exists())
        self.assertTrue((self.root / "skill" / "scripts" / "check-and-setup-dependencies.sh").exists())

    def test_azd_checksum_failure_never_extracts_or_executes(self):
        self.fake_downloads()
        with patch.object(helper, "AZD_SHA256", "0" * 64), patch.object(
            retained, "command"
        ) as command:
            with self.assertRaisesRegex(helper.CheckError, "checksum"):
                retained.check(self.root, fixtures.UPSTREAM_AGENT, TRACKING)
        command.assert_not_called()
        self.assertFalse((self.root / "bin" / "azd").exists())
        self.assertTrue((self.root / "azd.tar.gz").exists())

    def test_unsafe_azd_archives_never_extract(self):
        cases = (
            fixtures.archive_bytes(name="../escape"),
            fixtures.archive_bytes(kind=tarfile.SYMTYPE),
            fixtures.archive_bytes(duplicate=True),
            fixtures.archive_bytes(mode=0o4755),
        )
        for index, archive in enumerate(cases):
            with self.subTest(index=index):
                root = self.base / f"archive-{index}"
                (root / "bin").mkdir(parents=True)

                def download(_url, _digest, destination, _limit, data=archive):
                    destination.write_bytes(data)

                with patch.object(helper, "download", side_effect=download):
                    with self.assertRaisesRegex(helper.CheckError, "archive"):
                        helper.install_azd(root)
                self.assertFalse((root / "bin" / "azd").exists())
                self.assertTrue((root / "azd.tar.gz").exists())

    def test_invalid_version_and_failed_skill_never_report_success(self):
        self.fake_downloads()
        with patch.object(
            retained, "command", side_effect=[helper.READY.encode(), b"private version data"]
        ):
            with self.assertRaisesRegex(helper.CheckError, "version"):
                retained.check(self.root, fixtures.UPSTREAM_AGENT, TRACKING)

    def test_failed_skill_does_not_run_postcheck(self):
        self.fake_downloads()
        with patch.object(
            retained, "command", side_effect=helper.CheckError("skill")
        ) as command:
            with self.assertRaisesRegex(helper.CheckError, "skill"):
                retained.check(self.root, fixtures.UPSTREAM_AGENT, TRACKING)
        self.assertEqual(command.call_count, 1)
        self.assertTrue((self.root / "azd.tar.gz").exists())

    def test_command_waits_for_real_exit_and_never_uses_signals(self):
        with patch.object(os, "kill", side_effect=AssertionError("unexpected signal")), patch.object(
            os, "killpg", side_effect=AssertionError("unexpected group signal")
        ):
            result = retained.command(
                [sys.executable, "-c", "print('fictional output')"],
                self.root,
                {"PATH": "/usr/bin:/bin"},
                "skill",
                timeout=5,
            )
        self.assertEqual(result, b"fictional output\n")

    def test_child_uses_owned_cwd_and_does_not_inherit_extra_descriptors(self):
        source = os.open(self.root, os.O_RDONLY)
        inherited = fcntl.fcntl(source, fcntl.F_DUPFD, 100)
        os.set_inheritable(inherited, True)
        old_limit = resource.getrlimit(resource.RLIMIT_NOFILE)
        try:
            resource.setrlimit(resource.RLIMIT_NOFILE, (64, old_limit[1]))
            code = (
                "import os,sys;"
                f"assert not os.path.exists('/proc/self/fd/{inherited}');"
                "sys.stdout.write(os.getcwd())"
            )
            result = retained.command(
                [sys.executable, "-c", code],
                self.root,
                {"PATH": "/usr/bin:/bin"},
                "skill",
                timeout=5,
            )
        finally:
            resource.setrlimit(resource.RLIMIT_NOFILE, old_limit)
            os.close(inherited)
            os.close(source)
        self.assertEqual(result.decode(), str(self.root))

    def test_timeout_keeps_unrelated_process_untouched(self):
        sentinel = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(1.0); print('natural exit')"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        with patch.object(os, "kill", side_effect=AssertionError("unexpected signal")), patch.object(
            os, "killpg", side_effect=AssertionError("unexpected group signal")
        ):
            with self.assertRaisesRegex(helper.CheckError, "timeout"):
                retained.command(
                    [sys.executable, "-c", "import time; time.sleep(0.5)"],
                    self.root,
                    {"PATH": "/usr/bin:/bin"},
                    "skill",
                    timeout=0.1,
                )
        self.assertIsNone(sentinel.poll())
        stdout, stderr = sentinel.communicate(timeout=5)
        self.assertEqual((sentinel.returncode, stdout, stderr), (0, b"natural exit\n", b""))

    def test_closed_output_is_not_child_exit(self):
        with self.assertRaisesRegex(helper.CheckError, "timeout"):
            retained.command(
                [
                    sys.executable,
                    "-c",
                    "import os,time; os.close(1); os.close(2); time.sleep(0.5)",
                ],
                self.root,
                {"PATH": "/usr/bin:/bin"},
                "skill",
                timeout=0.1,
            )

    def test_late_descendant_write_is_retained_after_synchronous_success(self):
        marker = self.root / "late-write"
        child = (
            "import os,time;"
            "os.close(1);os.close(2);time.sleep(0.25);"
            f"open({str(marker)!r},'w').write('retained')"
        )
        parent = (
            "import subprocess,sys;"
            f"subprocess.Popen([sys.executable,'-c',{child!r}],close_fds=True);"
            "print('synchronous result')"
        )
        result = retained.command(
            [sys.executable, "-c", parent],
            self.root,
            {"PATH": "/usr/bin:/bin"},
            "skill",
            timeout=5,
        )
        self.assertEqual(result, b"synchronous result\n")
        deadline = time.monotonic() + 2
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertEqual(marker.read_text(), "retained")

    def test_output_limit_and_nonzero_exit_fail_closed(self):
        env = {"PATH": "/usr/bin:/bin"}
        with self.assertRaisesRegex(helper.CheckError, "output"):
            retained.command(
                [sys.executable, "-c", "import os; os.write(1, b'x' * 8192)"],
                self.root,
                env,
                "skill",
                timeout=5,
                limit=1024,
            )
        with self.assertRaisesRegex(helper.CheckError, "skill"):
            retained.command(
                [sys.executable, "-c", "raise SystemExit(4)"],
                self.root,
                env,
                "skill",
                timeout=5,
            )

    def test_missing_pidfd_support_stops_before_process_creation(self):
        with patch.object(
            retained, "check_pidfd_support", side_effect=helper.CheckError("runtime")
        ), patch.object(retained.os, "posix_spawn") as spawn:
            with self.assertRaisesRegex(helper.CheckError, "runtime"):
                retained.command(["unused"], self.root, {}, "skill")
            spawn.assert_not_called()

    def test_missing_exit_status_never_becomes_success(self):
        real_waitid = os.waitid

        def missing_reap(kind, fd, flags):
            if not flags & os.WNOWAIT:
                return None
            return real_waitid(kind, fd, flags)

        with patch.object(retained.os, "waitid", side_effect=missing_reap):
            with self.assertRaisesRegex(helper.CheckError, "runtime"):
                retained.command(
                    [sys.executable, "-c", "pass"],
                    self.root,
                    {"PATH": "/usr/bin:/bin"},
                    "skill",
                    timeout=5,
                )

    def test_early_failure_reserves_nothing_and_reports_only_fixed_category(self):
        out, err = io.StringIO(), io.StringIO()
        with patch.object(
            retained, "context", side_effect=helper.CheckError("context")
        ), patch.object(retained, "reserve_state") as reserve, patch.object(
            sys, "argv", ["check"]
        ), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.assertEqual(retained.main(), 1)
        reserve.assert_not_called()
        self.assertEqual(
            out.getvalue(),
            "failure_stage=context\nowned_process_may_be_running=false\n",
        )
        self.assertEqual(err.getvalue(), "foundry_prerequisites_check_failed\n")

    def test_unexpected_error_is_redacted(self):
        out, err = io.StringIO(), io.StringIO()
        with patch.object(
            retained, "run", side_effect=OSError("private-host-and-token")
        ), patch.object(sys, "argv", ["check"]), contextlib.redirect_stdout(
            out
        ), contextlib.redirect_stderr(err):
            self.assertEqual(retained.main(), 1)
        self.assertEqual(
            out.getvalue(),
            "failure_stage=unexpected_io\nowned_process_may_be_running=false\n",
        )
        self.assertEqual(err.getvalue(), "foundry_prerequisites_check_failed\n")

    def test_success_reports_retained_state_only(self):
        out = io.StringIO()
        with patch.object(retained, "run", return_value="1.37.3"), patch.object(
            sys, "argv", ["check"]
        ), contextlib.redirect_stdout(out):
            self.assertEqual(retained.main(), 0)
        self.assertEqual(
            out.getvalue(),
            "azd_version=1.37.3\nfoundry_prerequisites=ready_retained_state_only\n",
        )

    def test_interruption_during_spawn_reports_possible_running_process(self):
        out, err = io.StringIO(), io.StringIO()

        def partial_spawn(*_args, **_kwargs):
            self.assertTrue(retained._PROCESS_ATTEMPTED)
            raise helper.CheckError("interruption")

        def start_command():
            return retained.command(["unused"], self.root, {}, "skill")

        with patch.object(
            retained, "run", side_effect=start_command
        ), patch.object(
            retained, "check_pidfd_support"
        ), patch.object(
            retained.os, "posix_spawn", side_effect=partial_spawn
        ), patch.object(
            sys, "argv", ["check"]
        ), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.assertEqual(retained.main(), 1)
        self.assertEqual(
            out.getvalue(),
            "failure_stage=interruption\nowned_process_may_be_running=true\n",
        )
        self.assertEqual(err.getvalue(), "foundry_prerequisites_check_failed\n")

    def test_run_retains_state_and_never_uses_old_cleanup(self):
        env = {"GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1", "RUNNER_TRACKING_ID": TRACKING}
        user = type("User", (), {"pw_dir": str(self.home)})()

        def fake_check(root, _agent, _tracking):
            (root / "marker").write_text("retained")
            return "1.37.3"

        with patch.dict(os.environ, env, clear=True), patch.object(
            retained, "context", return_value=(self.temp, self.workspace)
        ), patch.object(
            helper, "invocation_user_agent", return_value=fixtures.UPSTREAM_AGENT
        ), patch.object(
            retained.pwd, "getpwuid", return_value=user
        ), patch.object(
            retained, "check", side_effect=fake_check
        ), patch.object(
            helper, "cleanup", side_effect=AssertionError("cleanup must not run")
        ):
            self.assertEqual(retained.run(), "1.37.3")
        self.assertEqual(
            (self.home / ".foundry-prerequisites-123-1" / "marker").read_text(),
            "retained",
        )


class RetainedWorkflowTests(unittest.TestCase):
    @staticmethod
    def bootstrap(github):
        workflow = (github / "workflows" / "check-foundry-prerequisites-retained.yml").read_text()
        shell = textwrap.dedent(workflow.split("        run: |\n", 1)[1])
        inline = shell.split("<<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
        return workflow, shell, inline

    def test_manual_protected_no_checkout_bootstrap_and_matching_digests(self):
        github = Path(__file__).parents[1]
        workflow, shell, inline = self.bootstrap(github)
        for required in (
            "workflow_dispatch:",
            "contents: read",
            "private-foundry-prerequisites",
            "github.ref == 'refs/heads/main' && github.ref_protected",
            "runs-on: [self-hosted, linux, lab-runner]",
            "environment: terraform-state",
            "exec /usr/bin/env -i",
            "RUNNER_TRACKING_ID=",
            "CHECK_WORKFLOW_SHA=",
            "CHECK_WORKFLOW_REF=",
            "GITHUB_WORKSPACE=",
            "RUNNER_TEMP=",
        ):
            self.assertIn(required, workflow)
        for forbidden in ("actions/checkout", "rm -rf", "id-token:", "secrets.", "killpg", "sudo", "docker"):
            self.assertNotIn(forbidden, workflow)
        for filename in (
            "check_foundry_prerequisites.py",
            "check_foundry_prerequisites_retained.py",
        ):
            digest = hashlib.sha256((github / "scripts" / filename).read_bytes()).hexdigest()
            self.assertIn(digest, workflow)
        parsed = subprocess.run(
            ["/usr/bin/bash", "-n"], input=shell, text=True, capture_output=True, timeout=5
        )
        self.assertEqual((parsed.returncode, parsed.stderr), (0, ""))
        tree = ast.parse(inline)
        guarded = next(node for node in tree.body if isinstance(node, ast.Try))
        self.assertFalse(
            any(
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "main"
                for node in ast.walk(guarded)
            ),
            "Bootstrap failures must not hide a potentially spawned child.",
        )

    def test_exact_bootstrap_loads_only_matching_sources_before_context_refusal(self):
        github = Path(__file__).parents[1]
        _, _, inline = self.bootstrap(github)
        sources = {
            name: (github / "scripts" / name).read_bytes()
            for name in (
                "check_foundry_prerequisites.py",
                "check_foundry_prerequisites_retained.py",
            )
        }
        sha = "a" * 40
        repo = "michael-rechani/foundry-agent-accelerator"
        with tempfile.TemporaryDirectory() as temporary:
            temp = Path(temporary) / "_temp"
            temp.mkdir()
            env = {
                "GITHUB_REPOSITORY": repo,
                "GITHUB_SHA": sha,
                "CHECK_WORKFLOW_SHA": sha,
                "CHECK_WORKFLOW_REF": (
                    f"{repo}/.github/workflows/check-foundry-prerequisites-retained.yml"
                    "@refs/heads/main"
                ),
                "GITHUB_REF": "refs/heads/main",
                "GITHUB_REF_PROTECTED": "true",
                "GITHUB_EVENT_NAME": "workflow_dispatch",
                "GITHUB_RUN_ID": "123",
                "GITHUB_RUN_ATTEMPT": "1",
                "RUNNER_ENVIRONMENT": "github-hosted",
                "RUNNER_TEMP": str(temp),
            }
            original_hook = sys.excepthook
            self.addCleanup(setattr, sys, "excepthook", original_hook)
            for tampered in (False, True):
                with self.subTest(tampered=tampered):
                    out, err = io.StringIO(), io.StringIO()

                    def fake_open(url, timeout, *, is_tampered=tampered):
                        self.assertEqual(timeout, 30)
                        name = url.rsplit("/", 1)[-1]
                        content = sources[name]
                        if is_tampered and name == "check_foundry_prerequisites_retained.py":
                            content += b"# changed\n"
                        response = io.BytesIO(content)
                        response.status = 200
                        return response

                    with patch.dict(sys.modules), patch.dict(
                        os.environ, env, clear=True
                    ), patch.object(
                        request, "build_opener"
                    ) as opener, patch.object(
                        sys, "argv", ["bootstrap"]
                    ), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                        opener.return_value.open.side_effect = fake_open
                        with self.assertRaises(SystemExit) as exit_code:
                            exec(compile(inline, "<workflow-bootstrap>", "exec"), {})
                    self.assertEqual(exit_code.exception.code, 1)
                    expected = "bootstrap" if tampered else "context"
                    self.assertEqual(
                        out.getvalue(),
                        f"failure_stage={expected}\nowned_process_may_be_running=false\n",
                    )
                    self.assertEqual(err.getvalue(), "foundry_prerequisites_check_failed\n")

    def test_bootstrap_http_failure_and_redirect_close_responses(self):
        github = Path(__file__).parents[1]
        _, _, inline = self.bootstrap(github)
        sha = "a" * 40
        repo = "michael-rechani/foundry-agent-accelerator"
        env = {
            "GITHUB_REPOSITORY": repo,
            "GITHUB_SHA": sha,
            "CHECK_WORKFLOW_SHA": sha,
            "CHECK_WORKFLOW_REF": (
                f"{repo}/.github/workflows/check-foundry-prerequisites-retained.yml"
                "@refs/heads/main"
            ),
            "GITHUB_REF": "refs/heads/main",
            "GITHUB_REF_PROTECTED": "true",
            "GITHUB_EVENT_NAME": "workflow_dispatch",
        }
        for body_type in (io.BytesIO, FailingCloseBytesIO):
            with self.subTest(body=body_type.__name__):
                body = body_type(b"private response content")
                failure = error.HTTPError("https://example.invalid/private-url", 403, "private response", {}, body)
                output, stderr, scope = io.StringIO(), io.StringIO(), {}
                with patch.dict(os.environ, env, clear=True), patch.object(
                    request, "build_opener"
                ) as opener, contextlib.redirect_stdout(output), contextlib.redirect_stderr(stderr):
                    opener.return_value.open.side_effect = failure
                    with self.assertRaises(SystemExit) as exit_code:
                        exec(compile(inline, "<workflow-bootstrap>", "exec"), scope)
                self.assertEqual(exit_code.exception.code, 1)
                self.assertTrue(body.closed)
                self.assertEqual(output.getvalue(), "failure_stage=bootstrap\nowned_process_may_be_running=false\n")
                self.assertEqual(stderr.getvalue(), "foundry_prerequisites_check_failed\n")

                redirect_body = body_type(b"private redirect content")
                with self.assertRaisesRegex(ValueError, "redirect"):
                    scope["NoRedirect"]().redirect_request(
                        None, redirect_body, 302, "private", {}, "https://example.invalid",
                    )
                self.assertTrue(redirect_body.closed)


if __name__ == "__main__":
    unittest.main()

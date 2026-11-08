import contextlib
import gzip
import hashlib
import io
import json
import os
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib import error, request

import check_foundry_prerequisites as probe
REAL_WHICH = shutil.which


# Official azure-skills fixture, MIT licensed; its exact content is hash-checked.
SKILL = b"""#!/usr/bin/env bash

set -euo pipefail

if ! command -v azd >/dev/null 2>&1; then
  echo "Azure Developer CLI (azd) is required. Install it from https://learn.microsoft.com/azure/developer/azure-developer-cli/install-azd, then rerun this script." >&2
  exit 1
fi

export AZURE_DEV_USER_AGENT=microsoft_foundry_skill

if ! extension_list="$(azd extension list --installed --output json)"; then
  echo "Failed to list installed azd extensions." >&2
  exit 1
fi

if printf '%s' "$extension_list" | grep -Eq '"id"[[:space:]]*:[[:space:]]*"microsoft\\.foundry"'; then
  echo "Dependencies are ready: azd and the microsoft.foundry extension are ready."
  exit 0
fi

echo "microsoft.foundry is not installed. Installing it now..."
azd extension install microsoft.foundry
echo "Dependencies are ready: azd and the microsoft.foundry extension are ready."
"""
FAKE_AZD = b"""#!/bin/bash
printf '%s\\n' "$*" >> "$AZD_CONFIG_DIR/calls"
[[ "$AZURE_DEV_USER_AGENT" == microsoft_foundry_skill ]] || exit 5
case "$*" in
  'extension list --installed --output json')
    [[ ! -e "$AZD_CONFIG_DIR/fail-list" ]] || exit 6
    if [[ -e "$AZD_CONFIG_DIR/installed" ]]; then
      printf '[{"id": "microsoft.foundry", "version": "0.1.0"}]'
    else
      printf '[]'
    fi ;;
  'extension install microsoft.foundry')
    [[ ! -e "$AZD_CONFIG_DIR/fail-install" ]] || exit 7
    printf true > "$AZD_CONFIG_DIR/installed" ;;
  'version') printf 'azd version 1.37.3 (commit private-machine-identifier)\\n' ;;
  *) exit 8 ;;
esac
"""
FAKE_GREP = b"""#!/bin/bash
text=$(</dev/stdin)
[[ "$text" == *'"id": "microsoft.foundry"'* ]]
"""
UPSTREAM_AGENT = SKILL.split(b"export AZURE_DEV_USER_AGENT=", 1)[1].split(b"\n", 1)[0].decode("ascii")


def archive_bytes(name="azd-linux-amd64", kind=tarfile.REGTYPE, duplicate=False, mode=0o775, extra=None, linkname=None):
    stream = io.BytesIO()
    with gzip.GzipFile(fileobj=stream, mode="wb", mtime=0) as compressed, tarfile.open(fileobj=compressed, mode="w") as package:
        for _ in range(2 if duplicate else 1):
            member = tarfile.TarInfo(name)
            member.type = kind
            member.mode = mode
            member.size = len(FAKE_AZD) if kind == tarfile.REGTYPE else 0
            member.linkname = linkname if linkname is not None else ("/unowned/private-file" if kind != tarfile.REGTYPE else "")
            package.addfile(member, io.BytesIO(FAKE_AZD) if member.size else None)
        # Observed hash-verified official layout: one executable and one notice.
        notice = tarfile.TarInfo("NOTICE.txt")
        notice.mode = 0o775
        notice.size = 6
        package.addfile(notice, io.BytesIO(b"notice"))
        if extra is not None:
            unrelated = tarfile.TarInfo(extra)
            unrelated.size = 6
            package.addfile(unrelated, io.BytesIO(b"ignore"))
    return stream.getvalue()


class PrerequisiteTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.temp = Path(self.temporary.name) / "runtime"
        self.temp.mkdir()
        self.event = Path(self.temporary.name) / "event.json"
        self.event.write_text(json.dumps({"inputs": {"user_agent": UPSTREAM_AGENT}}))
        self.environment = {
            "GITHUB_REF": "refs/heads/main",
            "GITHUB_REF_PROTECTED": "true",
            "GITHUB_EVENT_NAME": "workflow_dispatch",
            "GITHUB_RUN_ID": "12345",
            "GITHUB_RUN_ATTEMPT": "1",
            "RUNNER_TEMP": str(self.temp),
            "GITHUB_EVENT_PATH": str(self.event),
            "PATH": "untrusted-inherited-path",
            "HOME": "private-shared-home",
            "AZD_CONFIG_DIR": "private-shared-extension-state",
            "AZURE_CONFIG_DIR": "private-shared-cloud-state",
            "GH_TOKEN": "fixture-private-token",
            "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "fixture-private-oidc",
            "AZURE_CLIENT_SECRET": "fixture-private-secret",
            "BASH_ENV": "private-startup-script",
            "ENV": "private-startup-script",
            "HTTP_PROXY": "http://fixture-private-proxy",
            "HTTPS_PROXY": "http://fixture-private-proxy",
            "LD_PRELOAD": "private-loader",
        }
        self.start(patch.dict(os.environ, self.environment, clear=True))
        self.start(patch.object(probe.platform, "system", return_value="Linux"))
        self.start(patch.object(probe.platform, "machine", return_value="x86_64"))
        self.start(patch.object(sys, "argv", ["check_foundry_prerequisites.py"]))
        self.archive = archive_bytes()
        self.start(patch.object(probe, "AZD_SHA256", hashlib.sha256(self.archive).hexdigest()))
        self.opener = self.start(patch.object(probe.request, "build_opener")).return_value
        self.downloads = []
        self.opener.open.side_effect = self.fake_open
        self.installed = False
        self.which = self.start(patch.object(probe.shutil, "which", side_effect=self.fake_which))
        self.link = self.start(patch.object(Path, "symlink_to"))
        self.commands = []
        self.executor = self.start(patch.object(probe, "command", side_effect=self.fake_command))

    def start(self, patcher):
        value = patcher.start()
        self.addCleanup(patcher.stop)
        return value

    def fake_open(self, req, timeout):
        self.assertEqual(timeout, 60)
        self.assertEqual(dict(req.header_items()), {"User-agent": "foundry-prerequisite-check"})
        self.assertIsNone(req.data)
        self.assertEqual(req.get_method(), "GET")
        self.downloads.append(req.full_url)
        data = SKILL if req.full_url == probe.SKILL_URL else self.archive
        result = io.BytesIO(data)
        result.status = 200
        return result

    def fake_which(self, name, path=None):
        if name == "bash":
            self.assertEqual(path, "/usr/bin:/bin")
            return "/bin/bash"
        self.assertEqual(name, "azd")
        self.assertEqual(path, probe.SYSTEM_PATH)
        return str(self.temp / "shared-azd") if self.installed else None

    def fake_command(self, args, cwd, env):
        self.commands.append((args, cwd, env))
        root = cwd.parent
        self.assertEqual(cwd, root / "skill")
        self.assertEqual((cwd / "scripts" / "check-and-setup-dependencies.sh").read_bytes(), SKILL)
        self.assertEqual(env["AZURE_DEV_USER_AGENT"], UPSTREAM_AGENT)
        self.assertEqual(env["AZURE_DEV_COLLECT_TELEMETRY"], "no")
        self.assertEqual(env["PATH"], f"{root / 'bin'}:{probe.SYSTEM_PATH}")
        self.assertEqual(set(env), {
            "HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME",
            "XDG_STATE_HOME", "XDG_RUNTIME_DIR", "AZD_CONFIG_DIR", "AZURE_CONFIG_DIR",
            "TMPDIR", "PATH", "LANG", "LC_ALL", "AZURE_DEV_USER_AGENT",
            "AZURE_DEV_COLLECT_TELEMETRY", "AZD_NO_PROMPT",
        })
        for key in (
            "HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME",
            "XDG_STATE_HOME", "XDG_RUNTIME_DIR", "AZD_CONFIG_DIR", "AZURE_CONFIG_DIR", "TMPDIR",
        ):
            directory = Path(env[key])
            self.assertEqual(directory.parent, root)
            self.assertTrue(directory.is_dir())
        if args[-1] == "version":
            return subprocess.CompletedProcess(args, 0, "azd version 1.37.3 (commit private-machine-identifier)\n", "")
        if not self.installed and not (root / "bin" / "azd").exists():
            return subprocess.CompletedProcess(args, 1, "", probe.MISSING_AZD)
        return subprocess.CompletedProcess(args, 0, "private-install-output\n" + probe.READY, "private-stderr")

    def invoke(self, cleanup=False):
        out, err = io.StringIO(), io.StringIO()
        with patch.object(sys, "argv", ["check_foundry_prerequisites.py"] + (["--cleanup"] if cleanup else [])):
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = probe.main()
        return code, out.getvalue(), err.getvalue()

    def assert_failed(self, result, stage=None):
        self.assertEqual(result[0], 1)
        self.assertEqual(result[2], "foundry_prerequisites_check_failed\n")
        self.assertIn(result[1], {f"failure_stage={value}\n" for value in set(probe.FAILURE_STAGES.values()) | {"timeout", "unexpected_io"}})
        if stage is not None:
            self.assertEqual(result[1], f"failure_stage={stage}\n")

    @unittest.skip("Execution and automatic cleanup are disabled pending owned-descendant proof")
    def test_missing_azd_checks_first_then_downloads_and_reruns(self):
        self.assertEqual(self.invoke(), (0, "azd_version=1.37.3\nfoundry_prerequisites=ready\n", ""))
        self.assertEqual(self.downloads, [probe.SKILL_URL, probe.AZD_URL])
        self.assertEqual(len(self.commands), 3)
        self.assertEqual(self.commands[0][0], self.commands[1][0])
        self.assertEqual(self.commands[2][0][-1], "version")
        self.assertEqual(list(self.temp.iterdir()), [])
        self.link.assert_not_called()

    @unittest.skip("Execution and automatic cleanup are disabled pending owned-descendant proof")
    def test_installed_azd_is_reused_without_second_download_or_shared_state(self):
        self.installed = True
        shared = self.temp / "shared-azd"
        shared.write_bytes(b"do-not-change")
        self.assertEqual(self.invoke()[0], 0)
        self.assertEqual(self.downloads, [probe.SKILL_URL])
        self.assertEqual(len(self.commands), 2)
        self.link.assert_called_once_with(shared.resolve())
        self.assertEqual(shared.read_bytes(), b"do-not-change")
        self.assertEqual(list(self.temp.iterdir()), [shared])

    @unittest.skip("Execution and automatic cleanup are disabled pending owned-descendant proof")
    def test_untrusted_inherited_path_never_selects_an_existing_azd(self):
        untrusted = self.temp / "untrusted-bin"
        untrusted.mkdir()
        executable = untrusted / "azd"
        executable.write_bytes(b"untrusted-never-execute")

        def lookup(name, path=None):
            if name == "azd" and path is None:
                return str(executable)
            return self.fake_which(name, path)

        with patch.dict(os.environ, {"PATH": str(untrusted)}):
            self.which.side_effect = lookup
            self.assertEqual(self.invoke()[0], 0)
        self.assertEqual(self.downloads, [probe.SKILL_URL, probe.AZD_URL])
        self.link.assert_not_called()
        self.assertEqual(
            [call.kwargs for call in self.which.call_args_list if call.args == ("azd",)],
            [{"path": probe.SYSTEM_PATH}],
        )
        self.assertEqual(executable.read_bytes(), b"untrusted-never-execute")
        self.assertEqual(list(self.temp.iterdir()), [untrusted])

    @unittest.skip("Execution and automatic cleanup are disabled pending owned-descendant proof")
    def test_invocation_user_agent_is_required_and_rejects_injection_before_work(self):
        for value in (
            "", "a" * 65, " agent", "agent value", "agent\nvalue",
            "$(touch unowned)", "`touch unowned`", "agent;touch unowned",
            "agent=value", "/path/to/agent", "-agent", "\u00e9",
        ):
            self.event.write_text(json.dumps({"inputs": {"user_agent": value}}))
            with self.subTest(value=value):
                self.assert_failed(self.invoke(), "context")
                self.assertEqual(list(self.temp.iterdir()), [])
        with patch.dict(os.environ, clear=True):
            with self.assertRaises(probe.CheckError):
                probe.invocation_user_agent()
        self.opener.open.assert_not_called()
        self.executor.assert_not_called()

    def test_safe_runtime_values_propagate_without_default_or_persistence(self):
        for index, value in enumerate(("caller-agent", "a", "A1_.-", "a" * 64)):
            root = self.temp / f"owned{index}"
            root.mkdir()
            self.event.write_text(json.dumps({"inputs": {"user_agent": value}}))
            env = probe.isolated_environment(root, probe.invocation_user_agent())
            self.assertEqual(env["AZURE_DEV_USER_AGENT"], value)
            self.assertEqual(set(env), {
                "HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME",
                "XDG_STATE_HOME", "XDG_RUNTIME_DIR", "AZD_CONFIG_DIR", "AZURE_CONFIG_DIR",
                "TMPDIR", "PATH", "LANG", "LC_ALL", "AZURE_DEV_USER_AGENT",
                "AZURE_DEV_COLLECT_TELEMETRY", "AZD_NO_PROMPT",
            })
            self.assertTrue(all(not list(path.iterdir()) for path in root.iterdir()))
        source = Path(probe.__file__).read_text()
        self.assertNotIn("microsoft_foundry_skill", source)
        workflow = (Path(__file__).parents[1] / "workflows" / "check-foundry-prerequisites.yml").read_text()
        self.assertNotIn("microsoft_foundry_skill", workflow)
        self.assertNotIn("${{ inputs.user_agent }}", "\n".join(WorkflowTests().blocks()))

    @unittest.skip("Execution and automatic cleanup are disabled pending owned-descendant proof")
    def test_safe_but_wrong_value_fails_before_any_command(self):
        self.event.write_text(json.dumps({"inputs": {"user_agent": "valid_but_wrong"}}))
        self.assert_failed(self.invoke(), "context")
        self.assertEqual(self.downloads, [probe.SKILL_URL])
        self.executor.assert_not_called()
        self.which.assert_not_called()
        self.assertEqual(list(self.temp.iterdir()), [])

    @unittest.skip("Execution and automatic cleanup are disabled pending owned-descendant proof")
    def test_event_input_is_validated_without_reading_or_forwarding_other_fields(self):
        for payload in (
            b"not-json", b"[]", b'{"inputs": null}', b'{"inputs": {}}',
            b'{"inputs": {"user_agent": 1}}', b"x" * (1024 * 1024 + 1),
        ):
            self.event.write_bytes(payload)
            self.assert_failed(self.invoke(), "context")
        self.opener.open.assert_not_called()
        self.executor.assert_not_called()

    def test_upstream_declaration_must_be_single_strict_and_equal(self):
        script = self.temp / "fixture-script"
        for contents in (
            b"", b"export AZURE_DEV_USER_AGENT=wrong\n",
            b"export AZURE_DEV_USER_AGENT=$(command)\n",
            b"export AZURE_DEV_USER_AGENT='quoted'\n",
            SKILL + b"\nexport AZURE_DEV_USER_AGENT=other\n",
            SKILL + b"\nexport AZURE_DEV_USER_AGENT=$(command)\n",
        ):
            script.write_bytes(contents)
            with self.assertRaises(probe.CheckError):
                probe.validate_upstream_user_agent(script, UPSTREAM_AGENT)
        script.write_bytes(SKILL)
        probe.validate_upstream_user_agent(script, UPSTREAM_AGENT)

    @unittest.skip("Execution and automatic cleanup are disabled pending owned-descendant proof")
    def test_pinned_script_and_final_version_use_exact_runtime_agent_with_fake_tools(self):
        bash = REAL_WHICH("bash", path=r"C:\Program Files\Git\bin" if os.name == "nt" else "/usr/bin:/bin")
        self.assertIsNotNone(bash, "Use existing Bash only.")
        calls = []

        def shell_path(path):
            path = Path(path)
            if os.name == "nt":
                return f"/{path.drive[0].lower()}/{path.relative_to(path.anchor).as_posix()}"
            return str(path)

        def execute(args, cwd, env):
            calls.append(args)
            root = cwd.parent
            grep = root / "bin" / "grep"
            grep.write_bytes(FAKE_GREP)
            grep.chmod(0o700)
            isolated = dict(env)
            for key in (
                "HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME",
                "XDG_STATE_HOME", "XDG_RUNTIME_DIR", "AZD_CONFIG_DIR", "AZURE_CONFIG_DIR", "TMPDIR",
            ):
                isolated[key] = shell_path(env[key])
            isolated["PATH"] = shell_path(root / "bin")
            self.assertEqual(isolated["AZURE_DEV_USER_AGENT"], UPSTREAM_AGENT)
            executable = args[1] if args[0] == "/bin/bash" else args[0]
            return subprocess.run(
                [bash, shell_path(executable)] + ([] if args[0] == "/bin/bash" else args[1:]),
                cwd=cwd, env=isolated, stdin=subprocess.DEVNULL,
                capture_output=True, text=True, timeout=10, check=False,
            )

        self.executor.side_effect = execute
        self.assertEqual(self.invoke(), (0, "azd_version=1.37.3\nfoundry_prerequisites=ready\n", ""))
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[-1][-1], "version")
        self.assertEqual(list(self.temp.iterdir()), [])

    @unittest.skip("Execution and automatic cleanup are disabled pending owned-descendant proof")
    def test_skill_checksum_mismatch_never_executes_anything(self):
        with patch.object(probe, "SKILL_SHA256", "0" * 64):
            self.assert_failed(self.invoke(), "checksum")
        self.executor.assert_not_called()
        self.assertEqual(self.downloads, [probe.SKILL_URL])
        self.assertEqual(list(self.temp.iterdir()), [])

    @unittest.skip("Execution and automatic cleanup are disabled pending owned-descendant proof")
    def test_azd_checksum_mismatch_never_extracts_or_reruns(self):
        with patch.object(probe, "AZD_SHA256", "0" * 64), patch.object(probe.tarfile, "open") as extract:
            self.assert_failed(self.invoke(), "checksum")
        extract.assert_not_called()
        self.assertEqual(len(self.commands), 1)
        self.assertEqual(list(self.temp.iterdir()), [])

    @unittest.skip("Execution and automatic cleanup are disabled pending owned-descendant proof")
    def test_installed_azd_error_never_triggers_download_fallback(self):
        self.installed = True
        self.executor.side_effect = lambda *args: subprocess.CompletedProcess([], 1, "", probe.MISSING_AZD)
        self.assert_failed(self.invoke())
        self.assertEqual(self.downloads, [probe.SKILL_URL])
        self.assertEqual(list(self.temp.iterdir()), [])

    @unittest.skip("Execution and automatic cleanup are disabled pending owned-descendant proof")
    def test_unexpected_script_failures_do_not_trigger_fallback(self):
        for result in (
            subprocess.CompletedProcess([], 1, "", "private-failure"),
            subprocess.CompletedProcess([], 2, "", probe.MISSING_AZD),
            subprocess.CompletedProcess([], 1, "private-output", probe.MISSING_AZD),
            subprocess.CompletedProcess([], 0, "unexpected-success", ""),
        ):
            with self.subTest(result=result):
                self.executor.side_effect = None
                self.executor.return_value = result
                self.downloads.clear()
                self.assert_failed(self.invoke())
                self.assertEqual(self.downloads, [probe.SKILL_URL])
                self.assertEqual(list(self.temp.iterdir()), [])

    @unittest.skip("Execution and automatic cleanup are disabled pending owned-descendant proof")
    def test_failure_after_fallback_remains_failure_and_is_cleaned(self):
        self.executor.side_effect = [
            subprocess.CompletedProcess([], 1, "", probe.MISSING_AZD),
            subprocess.CompletedProcess([], 1, "private-output", "private-error"),
        ]
        self.assert_failed(self.invoke())
        self.assertEqual(self.downloads, [probe.SKILL_URL, probe.AZD_URL])
        self.assertEqual(list(self.temp.iterdir()), [])

    @unittest.skip("Execution and automatic cleanup are disabled pending owned-descendant proof")
    def test_invalid_version_never_emits_success_or_private_output(self):
        self.installed = True
        for result in (
            subprocess.CompletedProcess([], 0, "private-machine-path", ""),
            subprocess.CompletedProcess([], 1, "azd version 1.37.3\n", "private-error"),
            subprocess.CompletedProcess([], 0, "azd version 1.37.3\nprivate-machine-path\n", ""),
        ):
            with self.subTest(result=result):
                self.executor.side_effect = [
                    subprocess.CompletedProcess([], 0, probe.READY, ""),
                    result,
                ]
                self.assert_failed(self.invoke())
                self.assertEqual(list(self.temp.iterdir()), [])

    def test_cloud_and_runner_guards_fail_before_files_downloads_or_commands(self):
        for key, value in (
            ("GITHUB_REF", "refs/heads/feature"),
            ("GITHUB_REF_PROTECTED", "false"),
            ("GITHUB_EVENT_NAME", "pull_request"),
            ("GITHUB_RUN_ID", "../unowned"),
            ("GITHUB_RUN_ATTEMPT", "0"),
            ("RUNNER_TEMP", "relative-path"),
        ):
            with self.subTest(key=key), patch.dict(os.environ, {key: value}):
                self.assert_failed(self.invoke())
                self.assertEqual(list(self.temp.iterdir()), [])
        for system, machine in (("Windows", "x86_64"), ("Linux", "aarch64")):
            with patch.object(probe.platform, "system", return_value=system), patch.object(probe.platform, "machine", return_value=machine):
                self.assert_failed(self.invoke())
        self.opener.open.assert_not_called()
        self.executor.assert_not_called()

    @unittest.skip("Execution and automatic cleanup are disabled pending owned-descendant proof")
    def test_failures_and_handled_interruption_cleanup_only_owned_files(self):
        unowned = self.temp / "unowned"
        unowned.write_bytes(b"preserve")
        for failure in (
            probe.CheckError("private-details"),
            OSError("private-details"),
            subprocess.TimeoutExpired("private-command", 1, output="private-output"),
            error.URLError("private-details"),
        ):
            with self.subTest(failure=type(failure).__name__):
                self.executor.side_effect = failure
                self.assert_failed(self.invoke())
                self.assertEqual(list(self.temp.iterdir()), [unowned])
        self.executor.side_effect = lambda *args: probe.interrupted(signal.SIGTERM, None)
        self.assert_failed(self.invoke())
        self.assertEqual(unowned.read_bytes(), b"preserve")
        self.assertEqual(list(self.temp.iterdir()), [unowned])

    @unittest.skip("Execution and automatic cleanup are disabled pending owned-descendant proof")
    def test_cleanup_failure_emits_no_readiness_and_always_can_retry(self):
        original = shutil.rmtree
        with patch.object(probe.shutil, "rmtree", side_effect=OSError("private-path")):
            self.assert_failed(self.invoke(), "cleanup")
        self.assertEqual(len(list(self.temp.iterdir())), 2)
        with patch.object(probe.shutil, "rmtree", side_effect=original):
            self.assertEqual(self.invoke(cleanup=True), (0, "foundry_prerequisites_cleanup=complete\n", ""))
        self.assertEqual(list(self.temp.iterdir()), [])

    def test_existing_receipt_is_not_overwritten_or_deleted(self):
        receipt = self.temp / probe.context()[1]
        receipt.write_bytes(b"unowned")
        self.assert_failed(self.invoke())
        self.assertEqual(receipt.read_bytes(), b"unowned")
        self.opener.open.assert_not_called()

    @unittest.skip("Execution and automatic cleanup are disabled pending owned-descendant proof")
    def test_download_failures_are_sanitized_and_cleaned(self):
        for failure in (error.URLError("private-proxy-path"), OSError("private-certificate-path")):
            self.opener.open.side_effect = failure
            self.assert_failed(self.invoke())
            self.assertEqual(list(self.temp.iterdir()), [])

    def test_download_size_and_http_status_fail_closed(self):
        for status, content, limit in ((403, b"private-response", 100), (200, b"over-limit", 3)):
            response = io.BytesIO(content)
            response.status = status
            self.opener.open.side_effect = None
            self.opener.open.return_value = response
            path = self.temp / "artifact"
            with self.subTest(status=status), self.assertRaises(probe.CheckError):
                probe.download(probe.SKILL_URL, hashlib.sha256(content).hexdigest(), path, limit)
            path.unlink()

    def test_redirects_are_https_public_assets_only_without_authentication(self):
        handler = probe.PublicRedirect()
        req = request.Request(probe.AZD_URL, headers={"User-Agent": "foundry-prerequisite-check"})
        for url in (
            "http://release-assets.githubusercontent.com/file",
            "https://private.invalid/file",
            "https://release-assets.githubusercontent.com:444/file",
            "https://user:password@github.com/file",
            "https://raw.githubusercontent.com/private/file",
        ):
            with self.subTest(url=url), self.assertRaises(probe.CheckError):
                handler.redirect_request(req, None, 302, "", {}, url)
        redirected = handler.redirect_request(req, None, 302, "", {}, "https://release-assets.githubusercontent.com/file")
        self.assertIsNone(redirected.get_header("Authorization"))
        self.assertEqual(redirected.full_url, "https://release-assets.githubusercontent.com/file")
        proxy = probe.request.ProxyHandler({})
        self.assertEqual(proxy.proxies, {})

    def test_download_rejects_any_unpinned_source_before_opening(self):
        for url in ("file:///private-file", "http://github.com/file", "https://private.invalid/file"):
            with self.subTest(url=url), self.assertRaises(probe.CheckError):
                probe.download(url, "0" * 64, self.temp / "artifact", 10)
        self.opener.open.assert_not_called()

    @unittest.skip("Execution and automatic cleanup are disabled pending owned-descendant proof")
    def test_archive_never_extracts_unsafe_or_duplicate_binary_members(self):
        for name, kind, duplicate in (
            ("azd", tarfile.REGTYPE, False),
            ("../azd", tarfile.REGTYPE, False),
            ("../azd-linux-amd64", tarfile.REGTYPE, False),
            ("./azd-linux-amd64", tarfile.REGTYPE, False),
            ("/azd-linux-amd64", tarfile.REGTYPE, False),
            ("nested/azd-linux-amd64", tarfile.REGTYPE, False),
            ("azd-linux-amd64", tarfile.SYMTYPE, False),
            ("azd-linux-amd64", tarfile.LNKTYPE, False),
            ("azd-linux-amd64", tarfile.DIRTYPE, False),
            ("azd-linux-amd64", tarfile.FIFOTYPE, False),
            ("azd-linux-amd64", tarfile.REGTYPE, True),
        ):
            with self.subTest(name=name, kind=kind, duplicate=duplicate):
                self.archive = archive_bytes(name, kind, duplicate)
                probe.AZD_SHA256 = hashlib.sha256(self.archive).hexdigest()
                self.assert_failed(self.invoke(), "archive")
                self.assertEqual(list(self.temp.iterdir()), [])

    def test_observed_official_layout_extracts_only_executable_to_owned_bin(self):
        with tarfile.open(fileobj=io.BytesIO(self.archive), mode="r:gz") as package:
            self.assertEqual([(member.name, member.type, member.mode) for member in package.getmembers()], [
                ("azd-linux-amd64", tarfile.REGTYPE, 0o775),
                ("NOTICE.txt", tarfile.REGTYPE, 0o775),
            ])
        root = self.temp / "owned"
        root.mkdir()
        (root / "bin").mkdir()
        probe.install_azd(root)
        self.assertEqual((root / "bin" / "azd").read_bytes(), FAKE_AZD)
        self.assertEqual(list((root / "bin").iterdir()), [root / "bin" / "azd"])
        self.assertFalse((root / "NOTICE.txt").exists())
        self.assertFalse((root / "azd-linux-amd64").exists())

    @unittest.skip("Execution and automatic cleanup are disabled pending owned-descendant proof")
    def test_unsafe_alternatives_and_modes_fail_before_any_extraction(self):
        for options in (
            {"extra": "../unowned"}, {"extra": "azd"},
            {"extra": "./azd-linux-amd64"}, {"extra": "NOTICE.txt"},
            {"mode": 0o644}, {"mode": 0o4775},
            {"mode": 0o2775}, {"linkname": "/unowned/private-file"},
        ):
            with self.subTest(options=options):
                self.archive = archive_bytes(**options)
                probe.AZD_SHA256 = hashlib.sha256(self.archive).hexdigest()
                with patch.object(probe.tarfile.TarFile, "extractfile") as extract:
                    self.assert_failed(self.invoke(), "archive")
                    extract.assert_not_called()
                self.assertEqual(list(self.temp.iterdir()), [])

    def test_official_fixture_and_release_pins_are_exact(self):
        self.assertEqual(hashlib.sha256(SKILL).hexdigest(), probe.SKILL_SHA256)
        self.assertEqual(archive_bytes(), archive_bytes())
        self.assertEqual(probe.SKILL_SHA256, "bb54d233fe8d0164b083a58dec25d1dc3de2c0d7057fc661c866c27b95c935dd")
        # Read source, not the deliberately overridden fake-archive constant.
        source = Path(probe.__file__).read_text()
        self.assertIn('AZD_SHA256 = "8bf3e7e86f1d5a9bc1ae6f014c792697660cce04f6333a8091c6e08b7f8c7786"', source)
        self.assertIn("azure-dev-cli_1.37.3/azd-linux-amd64.tar.gz", probe.AZD_URL)
        self.assertIn("299b16bf063bdf37c783e08bcae27ca57fface38", probe.SKILL_URL)


class CleanupTests(unittest.TestCase):
    def test_receipts_and_owned_or_unknown_entries_are_retained(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in ("old-receipt.json", "partial.json", "missing.json"):
                if name != "missing.json":
                    (root / name).write_text('{"name":"fictional","owner":"fixture"}')
                with self.subTest(name=name), patch.object(probe.shutil, "rmtree") as remove:
                    with self.assertRaisesRegex(probe.CheckError, "^cleanup$"):
                        probe.cleanup(root, name)
                    remove.assert_not_called()
            self.assertEqual((root / "old-receipt.json").read_text(),
                             '{"name":"fictional","owner":"fixture"}')
            self.assertTrue((root / "partial.json").exists())

class FailureStageTests(unittest.TestCase):
    def test_only_fixed_categories_are_emitted_without_exception_details(self):
        failures = [(probe.CheckError(code), stage) for code, stage in probe.FAILURE_STAGES.items()]
        failures.extend([
            (probe.CheckError("private-url private-token private-path"), "unexpected_io"),
            (OSError("private-url private-token private-path"), "unexpected_io"),
            (ValueError("private-url private-token private-path"), "unexpected_io"),
            (error.URLError("private-url private-token private-path"), "download"),
            (tarfile.ReadError("private-url private-token private-path"), "archive"),
            (subprocess.TimeoutExpired("private-command", 1, output="private-output"), "timeout"),
            (RuntimeError("private-url private-token private-path"), "unexpected_io"),
        ])
        for failure, stage in failures:
            with self.subTest(kind=type(failure).__name__, stage=stage):
                out, err = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    probe.report_failure(failure)
                self.assertEqual((out.getvalue(), err.getvalue()), (f"failure_stage={stage}\n", "foundry_prerequisites_check_failed\n"))
                if not isinstance(failure, RuntimeError):
                    with (
                        patch.object(sys, "argv", ["check_foundry_prerequisites.py"]),
                        patch.object(probe, "run", side_effect=failure),
                        contextlib.redirect_stdout(out := io.StringIO()),
                        contextlib.redirect_stderr(err := io.StringIO()),
                    ):
                        self.assertEqual(probe.main(), 1)
                    self.assertEqual((out.getvalue(), err.getvalue()), (f"failure_stage={stage}\n", "foundry_prerequisites_check_failed\n"))


class ProcessTests(unittest.TestCase):
    def test_command_and_check_refuse_before_process_or_setup(self):
        with (
            patch.object(probe.subprocess, "Popen") as popen,
            patch.object(probe.os, "killpg", create=True) as group,
            patch.object(probe.os, "kill") as numeric,
            patch.object(probe.os, "waitpid", create=True) as wait,
            patch.object(probe.os, "waitid", create=True) as waitid,
            patch.object(probe, "isolated_environment") as environment,
            patch.object(probe, "download") as download,
        ):
            for action in (
                lambda: probe.command(["fictional"], Path("fictional"), {}),
                lambda: probe.check(Path("fictional"), "fictional"),
            ):
                with self.assertRaisesRegex(probe.CheckError, "^supervision$"):
                    action()
            popen.assert_not_called()
            group.assert_not_called()
            numeric.assert_not_called()
            wait.assert_not_called()
            waitid.assert_not_called()
            environment.assert_not_called()
            download.assert_not_called()

    def test_run_refuses_before_context_scratch_download_or_signal(self):
        with (
            patch.object(probe, "context") as context,
            patch.object(probe, "invocation_user_agent") as user_agent,
            patch.object(probe, "check") as check,
            patch.object(probe.subprocess, "Popen") as popen,
            patch.object(probe.os, "killpg", create=True) as group,
            patch.object(probe.shutil, "rmtree") as remove,
        ):
            with self.assertRaisesRegex(probe.CheckError, "^supervision$"):
                probe.run()
            for operation in (context, user_agent, check, popen, group, remove):
                operation.assert_not_called()

    def test_cli_reports_fixed_refusal_without_private_details(self):
        for arguments, expected in (([], "supervision_unverified"), (["--cleanup"], "cleanup")):
            output, errors = io.StringIO(), io.StringIO()
            with (
                patch.object(sys, "argv", ["check_foundry_prerequisites.py", *arguments]),
                patch.object(probe, "context", return_value=(Path("fictional"), "fixture")),
                contextlib.redirect_stdout(output),
                contextlib.redirect_stderr(errors),
            ):
                self.assertEqual(probe.main(), 1)
            self.assertEqual(output.getvalue(), f"failure_stage={expected}\n")
            self.assertEqual(errors.getvalue(), "foundry_prerequisites_check_failed\n")

class OfficialScriptFixtureTests(unittest.TestCase):
    def test_actual_hash_pinned_script_with_fake_commands_only(self):
        bash = shutil.which("bash")
        self.assertIsNotNone(bash, "Offline fixture execution requires an existing Bash; do not install one.")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            script = root / "check-and-setup-dependencies.sh"
            script.write_bytes(SKILL)
            self.assertEqual(hashlib.sha256(script.read_bytes()).hexdigest(), probe.SKILL_SHA256)
            tools = root / "bin"
            tools.mkdir()
            config = root / "azd-config"
            config.mkdir()
            home = root / "home"
            home.mkdir()

            def shell_path(path):
                if os.name == "nt":
                    return f"/{path.drive[0].lower()}/{path.relative_to(path.anchor).as_posix()}"
                return str(path)

            env = {
                "PATH": shell_path(tools),
                "HOME": shell_path(home),
                "AZD_CONFIG_DIR": shell_path(config),
                "AZURE_DEV_USER_AGENT": "microsoft_foundry_skill",
            }

            def execute():
                return subprocess.run(
                    [bash, shell_path(script)], cwd=root, env=env,
                    stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=10, check=False,
                )

            missing = execute()
            self.assertEqual((missing.returncode, missing.stdout, missing.stderr), (1, "", probe.MISSING_AZD))
            for name, fixture in (("azd", FAKE_AZD), ("grep", FAKE_GREP)):
                path = tools / name
                path.write_bytes(fixture)
                path.chmod(0o700)
            ready = execute()
            self.assertEqual(ready.returncode, 0, ready.stderr)
            self.assertTrue(ready.stdout.endswith(probe.READY))
            self.assertEqual((config / "calls").read_text().splitlines(), [
                "extension list --installed --output json",
                "extension install microsoft.foundry",
            ])
            (config / "calls").unlink()
            already_ready = execute()
            self.assertEqual((already_ready.returncode, already_ready.stdout), (0, probe.READY))
            self.assertEqual((config / "calls").read_text().splitlines(), ["extension list --installed --output json"])
            for failure, expected in (("fail-list", "Failed to list installed azd extensions."), ("fail-install", "")):
                (config / "installed").unlink(missing_ok=True)
                marker = config / failure
                marker.write_bytes(b"fixture")
                failed = execute()
                self.assertNotEqual(failed.returncode, 0)
                self.assertNotIn(probe.READY, failed.stdout)
                if expected:
                    self.assertIn(expected, failed.stderr)
                marker.unlink()


class WorkflowTests(unittest.TestCase):
    def blocks(self):
        return [(Path(__file__).parents[1] / "workflows" / "check-foundry-prerequisites.yml").read_text()]

    def test_protected_workflow_refuses_before_checkout_or_scratch(self):
        workflow = self.blocks()[0]
        for required in (
            "workflow_dispatch:", "contents: read", "private-foundry-prerequisites",
            "github.ref == 'refs/heads/main' && github.ref_protected",
            "runs-on: [self-hosted, linux, lab-runner]", "environment: terraform-state",
            "failure_stage=supervision_unverified", "foundry_prerequisites_check_failed", "exit 1",
        ):
            self.assertIn(required, workflow)
        for forbidden in ("actions/checkout", "rm -rf", "--cleanup", "python3 -I",
                          "id-token:", "secrets.", "killpg", "sudo", "docker"):
            self.assertNotIn(forbidden, workflow)
        self.assertEqual(workflow.count("      - name:"), 1)
        bash = REAL_WHICH("bash")
        self.assertIsNotNone(bash, "Offline syntax validation requires existing Bash.")
        script = workflow.split("        run: |\n", 1)[1]
        result = subprocess.run([bash, "-n"], input=script, text=True,
                                capture_output=True, timeout=5, check=False)
        self.assertEqual(result.returncode, 0, "Protected refusal shell is invalid")


if __name__ == "__main__":
    unittest.main()

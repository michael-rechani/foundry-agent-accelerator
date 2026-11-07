import contextlib
import gzip
import hashlib
import io
import json
import os
import select
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import time
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

    def test_missing_azd_checks_first_then_downloads_and_reruns(self):
        self.assertEqual(self.invoke(), (0, "azd_version=1.37.3\nfoundry_prerequisites=ready\n", ""))
        self.assertEqual(self.downloads, [probe.SKILL_URL, probe.AZD_URL])
        self.assertEqual(len(self.commands), 3)
        self.assertEqual(self.commands[0][0], self.commands[1][0])
        self.assertEqual(self.commands[2][0][-1], "version")
        self.assertEqual(list(self.temp.iterdir()), [])
        self.link.assert_not_called()

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

    def test_safe_but_wrong_value_fails_before_any_command(self):
        self.event.write_text(json.dumps({"inputs": {"user_agent": "valid_but_wrong"}}))
        self.assert_failed(self.invoke(), "context")
        self.assertEqual(self.downloads, [probe.SKILL_URL])
        self.executor.assert_not_called()
        self.which.assert_not_called()
        self.assertEqual(list(self.temp.iterdir()), [])

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

    def test_skill_checksum_mismatch_never_executes_anything(self):
        with patch.object(probe, "SKILL_SHA256", "0" * 64):
            self.assert_failed(self.invoke(), "checksum")
        self.executor.assert_not_called()
        self.assertEqual(self.downloads, [probe.SKILL_URL])
        self.assertEqual(list(self.temp.iterdir()), [])

    def test_azd_checksum_mismatch_never_extracts_or_reruns(self):
        with patch.object(probe, "AZD_SHA256", "0" * 64), patch.object(probe.tarfile, "open") as extract:
            self.assert_failed(self.invoke(), "checksum")
        extract.assert_not_called()
        self.assertEqual(len(self.commands), 1)
        self.assertEqual(list(self.temp.iterdir()), [])

    def test_installed_azd_error_never_triggers_download_fallback(self):
        self.installed = True
        self.executor.side_effect = lambda *args: subprocess.CompletedProcess([], 1, "", probe.MISSING_AZD)
        self.assert_failed(self.invoke())
        self.assertEqual(self.downloads, [probe.SKILL_URL])
        self.assertEqual(list(self.temp.iterdir()), [])

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

    def test_failure_after_fallback_remains_failure_and_is_cleaned(self):
        self.executor.side_effect = [
            subprocess.CompletedProcess([], 1, "", probe.MISSING_AZD),
            subprocess.CompletedProcess([], 1, "private-output", "private-error"),
        ]
        self.assert_failed(self.invoke())
        self.assertEqual(self.downloads, [probe.SKILL_URL, probe.AZD_URL])
        self.assertEqual(list(self.temp.iterdir()), [])

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
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.temp = Path(self.temporary.name)
        self.name = "foundry-prerequisites-fixture1"
        self.root = self.temp / self.name
        self.root.mkdir()
        self.owner = "a" * 32
        (self.root / ".run-owned").write_text(self.owner)
        (self.root / "scratch").write_bytes(b"fixture")
        self.receipt_name = "foundry-prerequisites-12345-1.json"
        self.receipt = self.temp / self.receipt_name
        self.write_receipt(self.name, self.owner)
        self.unowned = self.temp / "unowned"
        self.unowned.write_bytes(b"preserve")

    def write_receipt(self, name, owner):
        self.receipt.write_text(json.dumps({"name": name, "owner": owner, "process_teardown": "verified"}))

    def test_missing_partial_or_unverified_state_never_allows_cleanup(self):
        records = [
            json.dumps({"name": self.name, "owner": self.owner}),
            json.dumps({"name": self.name, "owner": self.owner, "process_teardown": "unverified"}),
            json.dumps({"name": self.name, "owner": self.owner, "process_teardown": "unknown"}),
            json.dumps({"name": self.name, "owner": self.owner, "process_teardown": None}),
            '{"name":"' + self.name + '","owner":"' + self.owner + '","process_teardown":',
        ]
        for payload in records:
            with self.subTest(payload=payload), patch.object(probe.shutil, "rmtree") as remove:
                self.receipt.write_text(payload)
                with self.assertRaises((probe.CheckError, ValueError)):
                    probe.cleanup(self.temp, self.receipt_name)
                self.assertEqual(self.receipt.read_text(), payload)
                self.assertTrue(self.root.exists())
                remove.assert_not_called()

    def test_crash_veto_survives_missing_root_and_separate_cleanup(self):
        payload = json.dumps({"name": "foundry-prerequisites-missing1", "owner": self.owner,
                              "process_teardown": "unverified"})
        self.receipt.write_text(payload)
        with patch.object(probe.shutil, "rmtree") as remove:
            with self.assertRaises(probe.CheckError):
                probe.cleanup(self.temp, self.receipt_name)
            self.assertEqual(self.receipt.read_text(), payload)
            remove.assert_not_called()

    def test_retry_removes_only_registered_root_and_is_idempotent(self):
        probe.cleanup(self.temp, self.receipt_name)
        probe.cleanup(self.temp, self.receipt_name)
        self.assertEqual(list(self.temp.iterdir()), [self.unowned])
        self.assertEqual(self.unowned.read_bytes(), b"preserve")

    def test_invalid_receipt_and_ownership_never_delete_unowned_content(self):
        for name, owner in (("..", self.owner), (str(self.temp), self.owner), ("unowned", self.owner), (self.name, "b" * 32)):
            with self.subTest(name=name, owner=owner):
                self.write_receipt(name, owner)
                with self.assertRaises(probe.CheckError):
                    probe.cleanup(self.temp, self.receipt_name)
                self.assertTrue(self.receipt.exists())
                self.assertTrue(self.root.exists())
                self.assertEqual(self.unowned.read_bytes(), b"preserve")

    def test_malformed_records_and_missing_marker_fail_closed(self):
        for payload in ("not-json", "[]", '{"name": null, "owner": null}', '{"name": 1, "owner": 2}'):
            self.receipt.write_text(payload)
            with self.assertRaises((probe.CheckError, ValueError)):
                probe.cleanup(self.temp, self.receipt_name)
            self.assertTrue(self.root.exists())
        self.write_receipt(self.name, self.owner)
        (self.root / ".run-owned").unlink()
        with self.assertRaises(OSError):
            probe.cleanup(self.temp, self.receipt_name)
        self.assertTrue(self.root.exists())

    def test_replaced_root_or_marker_is_never_followed(self):
        original = Path.lstat
        for target in (self.receipt, self.root, self.root / ".run-owned"):
            def status(path, *args, target=target, **kwargs):
                if path == target:
                    return os.stat_result((0o120777, 0, 0, 0, 0, 0, 0, 0, 0, 0))
                return original(path, *args, **kwargs)

            with self.subTest(target=target.name), patch.object(Path, "lstat", status), patch.object(probe.shutil, "rmtree") as remove:
                with self.assertRaises(probe.CheckError):
                    probe.cleanup(self.temp, self.receipt_name)
                remove.assert_not_called()
                self.assertEqual(self.unowned.read_bytes(), b"preserve")


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
    def test_disabled_command_never_launches_signals_or_reaps(self):
        with patch.object(probe.subprocess, "Popen") as popen, \
                patch.object(probe.os, "killpg", create=True) as kill, \
                patch.object(probe.os, "waitid", create=True) as waitid:
            with self.assertRaises(probe.TeardownUnverified):
                probe.command(["synthetic"], Path("synthetic"), {})
            popen.assert_not_called()
            kill.assert_not_called()
            waitid.assert_not_called()

    def test_check_refuses_before_download_setup_or_command(self):
        with patch.object(probe, "download") as download, \
                patch.object(probe, "isolated_environment") as environment, \
                patch.object(probe, "command") as command:
            with self.assertRaises(probe.TeardownUnverified):
                probe.check(Path("synthetic"), "synthetic")
            download.assert_not_called()
            environment.assert_not_called()
            command.assert_not_called()


class ProcessRetentionTests(unittest.TestCase):
    def test_unproven_group_outcomes_never_promote_receipt_or_delete_root(self):
        cases = ("signal delivered", "leader reaped", "both pipes EOF", "timeout",
                 "output limit", "uninterruptible descendant", "ownership loss")
        for outcome in cases:
            with self.subTest(outcome=outcome), tempfile.TemporaryDirectory() as folder:
                temp = Path(folder)
                receipt_name = "foundry-prerequisites-12345-1.json"

                def check(root, _user_agent, outcome=outcome, temp=temp, receipt_name=receipt_name):
                    (root / "synthetic-data").write_bytes(b"fictional")
                    self.assertEqual(json.loads((temp / receipt_name).read_text())["process_teardown"], "unverified")
                    # These mocked observations cannot establish group termination.
                    observed = {"signal_success": True, "leader_returncode": 0, "pipe_eof": True,
                                "group_proof": False, "outcome": outcome}
                    self.assertFalse(observed["group_proof"])
                    raise probe.TeardownUnverified("cleanup")

                with patch.object(probe, "context", return_value=(temp, receipt_name)), \
                        patch.object(probe, "invocation_user_agent", return_value="synthetic"), \
                        patch.object(probe, "check", side_effect=check), \
                        patch.object(probe.shutil, "rmtree") as remove:
                    with self.assertRaises(probe.TeardownUnverified):
                        probe.run()
                    receipt = temp / receipt_name
                    before = receipt.read_bytes()
                    record = json.loads(before)
                    self.assertEqual(record["process_teardown"], "unverified")
                    self.assertEqual((temp / record["name"] / "synthetic-data").read_bytes(), b"fictional")
                    with self.assertRaises(probe.CheckError):
                        probe.cleanup(temp, receipt_name)
                    with patch.object(sys, "argv", ["probe", "--cleanup"]), \
                            contextlib.redirect_stdout(out := io.StringIO()), \
                            contextlib.redirect_stderr(err := io.StringIO()):
                        self.assertEqual(probe.main(), 1)
                    self.assertEqual((out.getvalue(), err.getvalue()),
                                     ("failure_stage=cleanup\n", "foundry_prerequisites_check_failed\n"))
                    self.assertEqual(receipt.read_bytes(), before)
                    remove.assert_not_called()

    def test_real_disabled_check_retains_receipt_without_running_setup(self):
        with tempfile.TemporaryDirectory() as folder:
            temp = Path(folder)
            receipt_name = "foundry-prerequisites-12345-1.json"
            with patch.object(probe, "context", return_value=(temp, receipt_name)), \
                    patch.object(probe, "invocation_user_agent", return_value="synthetic"), \
                    patch.object(probe, "download") as download, \
                    patch.object(probe.subprocess, "Popen") as popen, \
                    patch.object(probe.shutil, "rmtree") as remove:
                with self.assertRaises(probe.TeardownUnverified):
                    probe.run()
                record = json.loads((temp / receipt_name).read_text())
                self.assertEqual(record["process_teardown"], "unverified")
                self.assertTrue((temp / record["name"]).is_dir())
                download.assert_not_called()
                popen.assert_not_called()
                remove.assert_not_called()

    def test_child_closing_both_pipes_can_still_write_and_cannot_authorize_cleanup(self):
        child = None
        pidfd = None
        script = """
import os,select,sys
from pathlib import Path
root = Path(sys.argv[1])
os.close(1)
os.close(2)
(root / "child-ready").write_bytes(b"fictional")
if select.select([0], [], [], 5)[0] and os.read(0, 1) == b"x":
    (root / "pending-write").write_bytes(b"fictional-late-write")
"""
        with tempfile.TemporaryDirectory() as folder:
            temp = Path(folder)
            receipt_name = "foundry-prerequisites-12345-1.json"

            def check(root, _user_agent):
                nonlocal child, pidfd
                child = subprocess.Popen(
                    [sys.executable, "-c", script, str(root)], env={"PATH": probe.SYSTEM_PATH},
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                )
                pidfd = os.pidfd_open(child.pid)
                deadline = time.monotonic() + 3
                while not (root / "child-ready").exists():
                    if time.monotonic() >= deadline:
                        self.fail("synthetic child did not become ready")
                    time.sleep(0.01)
                for stream in (child.stdout, child.stderr):
                    self.assertTrue(select.select([stream], [], [], 1)[0])
                    self.assertEqual(stream.read(), b"")
                self.assertIsNone(os.waitid(os.P_PIDFD, pidfd, os.WEXITED | os.WNOHANG | os.WNOWAIT))
                raise probe.TeardownUnverified("cleanup")

            try:
                with patch.object(probe, "context", return_value=(temp, receipt_name)), \
                        patch.object(probe, "invocation_user_agent", return_value="synthetic"), \
                        patch.object(probe, "check", side_effect=check), \
                        patch.object(probe.shutil, "rmtree") as remove, \
                        patch.object(probe.os, "killpg", create=True) as kill:
                    with self.assertRaises(probe.TeardownUnverified):
                        probe.run()
                    receipt = temp / receipt_name
                    before = receipt.read_bytes()
                    record = json.loads(before)
                    root = temp / record["name"]
                    self.assertEqual(record["process_teardown"], "unverified")
                    with self.assertRaises(probe.CheckError):
                        probe.cleanup(temp, receipt_name)
                    remove.assert_not_called()
                    kill.assert_not_called()
                    child.stdin.write(b"x")
                    child.stdin.flush()
                    self.assertEqual(child.wait(timeout=5), 0)
                    self.assertEqual((root / "pending-write").read_bytes(), b"fictional-late-write")
                    self.assertEqual(receipt.read_bytes(), before)
            finally:
                if child is not None:
                    child.stdin.close()
                    try:
                        child.wait(timeout=7)
                    except subprocess.TimeoutExpired:
                        # Only the test's bound synthetic child may be signaled.
                        signal.pidfd_send_signal(pidfd, signal.SIGKILL)
                        child.wait(timeout=5)
                    child.stdout.close()
                    child.stderr.close()
                if pidfd is not None:
                    os.close(pidfd)

    def test_abrupt_launcher_exit_before_child_launch_leaves_cleanup_veto(self):
        script = """
import os,sys
from pathlib import Path
from unittest.mock import patch
import check_foundry_prerequisites as probe
with patch.object(probe, "context", return_value=(Path(sys.argv[1]), "foundry-prerequisites-12345-1.json")), \
        patch.object(probe, "invocation_user_agent", return_value="synthetic"), \
        patch.object(probe, "check", side_effect=lambda *_args: os._exit(77)):
    probe.run()
"""
        with tempfile.TemporaryDirectory() as folder:
            result = subprocess.run(
                [sys.executable, "-c", script, folder], cwd=Path(probe.__file__).parent,
                env={"PATH": probe.SYSTEM_PATH}, stdin=subprocess.DEVNULL,
                capture_output=True, text=True, timeout=10, check=False,
            )
            self.assertEqual((result.returncode, result.stdout, result.stderr), (77, "", ""))
            temp = Path(folder)
            receipt_name = "foundry-prerequisites-12345-1.json"
            before = (temp / receipt_name).read_bytes()
            self.assertEqual(json.loads(before)["process_teardown"], "unverified")
            with patch.object(probe.shutil, "rmtree") as remove:
                with self.assertRaises(probe.CheckError):
                    probe.cleanup(temp, receipt_name)
                remove.assert_not_called()
            self.assertEqual((temp / receipt_name).read_bytes(), before)

    def test_no_command_failures_preserve_classification_and_normal_cleanup(self):
        for failure, expected in ((probe.CheckError("skill"), "skill_execution"),
                                  (subprocess.TimeoutExpired("synthetic", 180), "timeout"),
                                  (probe.CheckError("interrupted"), "interruption"),
                                  (probe.CheckError("output_limit"), "output_limit")):
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as folder:
                temp = Path(folder)
                with patch.object(probe, "context", return_value=(temp, "foundry-prerequisites-12345-1.json")), \
                        patch.object(probe, "invocation_user_agent", return_value="synthetic"), \
                        patch.object(probe, "check", side_effect=failure):
                    with self.assertRaises(type(failure)) as raised:
                        probe.run()
                    self.assertEqual(probe.failure_stage(raised.exception), expected)
                self.assertEqual(list(temp.iterdir()), [])

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
    @staticmethod
    def workflow():
        return (Path(__file__).parents[1] / "workflows" / "check-foundry-prerequisites.yml").read_text()

    def blocks(self):
        blocks = []
        for part in self.workflow().split("        run: |\n")[1:]:
            lines = []
            for line in part.splitlines():
                if line and not line.startswith("          "):
                    break
                lines.append(line)
            blocks.append(textwrap.dedent("\n".join(lines)) + "\n")
        return blocks

    def test_main_only_approval_gated_read_only_private_runner_contract(self):
        workflow = self.workflow()
        for expected in (
            "workflow_dispatch:", "if: github.ref == 'refs/heads/main' && github.ref_protected",
            "runs-on: [self-hosted, linux, lab-runner]", "environment: terraform-state",
            "contents: read", "cancel-in-progress: false", "timeout-minutes: 10",
            "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
            "persist-credentials: false", "clean: false", "show-progress: false",
            "sparse-checkout: .github/scripts/check_foundry_prerequisites.py",
            "sparse-checkout-cone-mode: false", "--cleanup",
            "if: always() && steps.source.outcome == 'success'",
            'if ! mkdir -- "$source_dir"', '.run-owned',
            'rm -rf -- "$source_dir"', '[[ ! -L "$source_dir"',
        ):
            self.assertIn(expected, workflow)
        for forbidden in (
            "id-token:", "secrets.", "vars.", "pull_request:", "push:",
            "schedule:", "ubuntu-", "start-private-runner", "azure/login", "az login",
            "setup-terraform", "upload-artifact", "GITHUB_TOKEN", "GH_TOKEN", "curl ",
            "sudo ", "setup-azd", "deploy-lab.yml", "check_lab_image_review",
        ):
            self.assertNotIn(forbidden, workflow)
        self.assertEqual(workflow.count("contents: read"), 2)
        self.assertEqual(workflow.count("uses:"), 1)
        self.assertNotIn("${{ inputs.user_agent }}", workflow)
        self.assertNotIn("default:", workflow)
        for expected in ("BASH_ENV: /dev/null", "ENV: /dev/null", "PATH: /usr/local/bin:/usr/bin:/bin"):
            self.assertIn(expected, workflow)
        self.assertIn(
            "    env:\n      PATH: /usr/local/bin:/usr/bin:/bin\n      BASH_ENV: /dev/null\n      ENV: /dev/null\n",
            workflow,
        )

    def test_workflow_shell_syntax_and_exclusive_source_cleanup_offline(self):
        bash = shutil.which("bash")
        self.assertIsNotNone(bash, "Use existing Bash only; no installation is permitted.")
        blocks = self.blocks()
        self.assertEqual(len(blocks), 3)
        for block in blocks:
            result = subprocess.run(
                [bash, "-n"], input=block, capture_output=True, text=True,
                timeout=10, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            unowned = root / "unowned"
            unowned.write_bytes(b"preserve")
            env = {"PATH": "/usr/bin:/bin", "GITHUB_RUN_ID": "12345", "GITHUB_RUN_ATTEMPT": "1"}

            def execute(block):
                return subprocess.run(
                    [bash], input=block, cwd=root, env=env,
                    capture_output=True, text=True, timeout=10, check=False,
                )

            for key in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT"):
                for invalid in ("", "0", "01", "-1", "../unowned", "1/../../unowned", "1\n2", "abc", None):
                    for block in blocks:
                        with self.subTest(key=key, invalid=invalid, block=blocks.index(block)):
                            if invalid is None:
                                env.pop(key, None)
                            else:
                                env[key] = invalid
                            rejected = execute(block)
                            self.assertEqual(
                                (rejected.returncode, rejected.stdout, rejected.stderr),
                                (1, "", "prerequisite_run_context_invalid\n"),
                            )
                            self.assertEqual(list(root.iterdir()), [unowned])
                            self.assertEqual(unowned.read_bytes(), b"preserve")
                env[key] = "12345" if key == "GITHUB_RUN_ID" else "1"

            reserved = execute(blocks[0])
            self.assertEqual((reserved.returncode, reserved.stdout, reserved.stderr), (0, "", ""))
            source = root / "foundry-prerequisite-source-12345-1"
            sentinel = source / "do-not-overwrite"
            sentinel.write_bytes(b"fixture")
            env["GITHUB_RUN_ATTEMPT"] = "../unowned"
            rejected = execute(blocks[2])
            self.assertEqual((rejected.returncode, rejected.stdout, rejected.stderr), (1, "", "prerequisite_run_context_invalid\n"))
            self.assertEqual(sentinel.read_bytes(), b"fixture")
            env["GITHUB_RUN_ATTEMPT"] = "1"
            repeated = execute(blocks[0])
            self.assertEqual((repeated.returncode, repeated.stdout, repeated.stderr), (1, "", "prerequisite_source_reservation_failed\n"))
            self.assertEqual(sentinel.read_bytes(), b"fixture")
            marker = source / ".run-owned"
            marker.write_text("unowned")
            rejected = execute(blocks[2])
            self.assertEqual((rejected.returncode, rejected.stdout, rejected.stderr), (1, "failure_stage=cleanup\n", "prerequisite_cleanup_failed\n"))
            self.assertTrue(sentinel.exists())
            marker.write_text("12345:1\n")
            removed = execute(blocks[2])
            self.assertEqual((removed.returncode, removed.stdout, removed.stderr), (0, "", ""))
            self.assertEqual(list(root.iterdir()), [unowned])

    def test_both_launchers_have_exact_environment_and_isolated_python_offline(self):
        bash = shutil.which("bash")
        self.assertIsNotNone(bash)
        blocks = self.blocks()
        keys = (
            "PATH", "GITHUB_REF", "GITHUB_REF_PROTECTED", "GITHUB_EVENT_NAME",
            "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "RUNNER_TEMP", "GITHUB_EVENT_PATH",
        )
        for block in (blocks[1], blocks[2]):
            launch = block.split("/usr/bin/env -i \\\n", 1)[1].split("python3 -I", 1)[0]
            self.assertEqual(
                tuple(line.strip().split("=", 1)[0] for line in launch.splitlines() if line.strip()),
                keys,
            )
        # Replace only the env executable in the test, never run the live helper.
        fixture = """
fake_env() {
  [[ "$#" == "$EXPECTED_COUNT" && "$1" == -i ]] || return 20
  shift
  [[ "$1" == PATH=/usr/local/bin:/usr/bin:/bin ]] || return 21
  shift
  [[ "$1" == GITHUB_REF=refs/heads/main ]] || return 22
  shift
  [[ "$1" == GITHUB_REF_PROTECTED=true ]] || return 23
  shift
  [[ "$1" == GITHUB_EVENT_NAME=workflow_dispatch ]] || return 24
  shift
  [[ "$1" == GITHUB_RUN_ID=12345 ]] || return 25
  shift
  [[ "$1" == GITHUB_RUN_ATTEMPT=1 ]] || return 26
  shift
  [[ "$1" == RUNNER_TEMP=fixture-temp ]] || return 27
  shift
  [[ "$1" == GITHUB_EVENT_PATH=fixture-event ]] || return 32
  shift
  [[ "$1" == python3 && "$2" == -I ]] || return 28
  shift 2
  [[ "$1" == foundry-prerequisite-source-12345-1/checkout/.github/scripts/check_foundry_prerequisites.py ]] || return 29
  shift
  [[ "${1:-}" == "$EXPECTED_ARGUMENT" ]] || return 30
  if [[ "$FAIL_LAUNCH" == true ]]; then
    printf '%s\\n' "$FAILURE_OUTPUT"
    echo "private-loader-error private-machine-path" >&2
    return 31
  fi
  if [[ "$EXPECTED_ARGUMENT" == --cleanup ]]; then
    echo "foundry_prerequisites_cleanup=complete"
  else
    printf 'azd_version=1.37.3\\nfoundry_prerequisites=ready\\n'
  fi
}
"""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "foundry-prerequisite-source-12345-1"
            script = source / "checkout" / ".github" / "scripts" / "check_foundry_prerequisites.py"
            env = {
                "PATH": "/usr/bin:/bin",
                "BASH_ENV": "/dev/null", "ENV": "/dev/null",
                "PYTHONPATH": "untrusted-pythonpath",
                "PYTHONHOME": "untrusted-pythonhome",
                "GH_TOKEN": "private-token",
                "GITHUB_REF": "refs/heads/main",
                "GITHUB_REF_PROTECTED": "true",
                "GITHUB_EVENT_NAME": "workflow_dispatch",
                "GITHUB_RUN_ID": "12345", "GITHUB_RUN_ATTEMPT": "1",
                "RUNNER_TEMP": "fixture-temp",
                "GITHUB_EVENT_PATH": "fixture-event",
            }
            for index in (1, 2):
                for failure_output in (
                    None, *(f"failure_stage={stage}" for stage in set(probe.FAILURE_STAGES.values()) | {"timeout", "unexpected_io"}),
                    "", "private-loader-error", "failure_stage=download\nprivate-path",
                ):
                    fail = failure_output is not None
                    with self.subTest(index=index, failure_output=failure_output):
                        script.parent.mkdir(parents=True, exist_ok=True)
                        script.write_bytes(b"never-execute-fixture")
                        (source / ".run-owned").write_text("12345:1\n")
                        env.update({
                            "EXPECTED_COUNT": "12" if index == 1 else "13",
                            "EXPECTED_ARGUMENT": "" if index == 1 else "--cleanup",
                            "FAIL_LAUNCH": "true" if fail else "false",
                            "FAILURE_OUTPUT": failure_output or "",
                        })
                        result = subprocess.run(
                            [bash], input=fixture + blocks[index].replace("/usr/bin/env", "fake_env"),
                            cwd=root, env=env, capture_output=True, text=True,
                            timeout=10, check=False,
                        )
                        expected_error = "foundry_prerequisites_check_failed\n" if index == 1 else "prerequisite_cleanup_failed\n"
                        expected_stage = failure_output.split("=", 1)[1] if failure_output and failure_output.startswith("failure_stage=") and "\n" not in failure_output else "launcher"
                        expected_success = "azd_version=1.37.3\nfoundry_prerequisites=ready\n" if index == 1 else "foundry_prerequisites_cleanup=complete\n"
                        self.assertEqual(
                            (result.returncode, result.stdout, result.stderr),
                            (1, f"failure_stage={expected_stage}\n", expected_error) if fail else (0, expected_success, ""),
                        )

    def test_job_environment_neutralizes_bash_startup_hooks_before_launch(self):
        bash = shutil.which("bash")
        self.assertIsNotNone(bash)
        assignments = self.workflow().split("    env:\n", 1)[1].split("    defaults:", 1)[0]
        job_env = dict(line.strip().split(": ", 1) for line in assignments.splitlines() if line.strip())
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            hook = root / "untrusted-startup.sh"
            hook.write_text("echo 'untrusted-startup-executed' >&2\nexit 71\n")
            env = {"BASH_ENV": str(hook), "ENV": str(hook)}
            env.update(job_env)
            result = subprocess.run(
                [bash], input="echo shell_startup=isolated\n", cwd=root, env=env,
                capture_output=True, text=True, timeout=10, check=False,
            )
            self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "shell_startup=isolated\n", ""))

    def test_python_isolated_mode_ignores_poisoned_python_startup_offline(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "sitecustomize.py").write_text("raise RuntimeError('untrusted startup executed')")
            env = {"PATH": probe.SYSTEM_PATH, "PYTHONPATH": str(root), "PYTHONHOME": str(root)}
            result = subprocess.run(
                [sys.executable, "-I", "-c", "import sys; assert sys.flags.isolated == 1; print('isolated_python=ready')"],
                cwd=root, env=env, capture_output=True, text=True, timeout=10, check=False,
            )
            self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "isolated_python=ready\n", ""))


if __name__ == "__main__":
    unittest.main()

"""Run the pinned Foundry dependency script without shared configuration or credentials."""

import hashlib
import selectors
import time
import json
import os
import platform
import re
import shutil
import signal
import stat
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from urllib import error, parse, request


SKILL_URL = (
    "https://raw.githubusercontent.com/microsoft/azure-skills/"
    "299b16bf063bdf37c783e08bcae27ca57fface38/"
    "skills/microsoft-foundry/scripts/check-and-setup-dependencies.sh"
)
SKILL_SHA256 = "bb54d233fe8d0164b083a58dec25d1dc3de2c0d7057fc661c866c27b95c935dd"
AZD_URL = (
    "https://github.com/Azure/azure-dev/releases/download/"
    "azure-dev-cli_1.37.3/azd-linux-amd64.tar.gz"
)
AZD_SHA256 = "8bf3e7e86f1d5a9bc1ae6f014c792697660cce04f6333a8091c6e08b7f8c7786"
MISSING_AZD = (
    "Azure Developer CLI (azd) is required. Install it from "
    "https://learn.microsoft.com/azure/developer/azure-developer-cli/install-azd, "
    "then rerun this script.\n"
)
READY = "Dependencies are ready: azd and the microsoft.foundry extension are ready.\n"
SYSTEM_PATH = "/usr/local/bin:/usr/bin:/bin"
VERSION = r"[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9]+(?:[.-][A-Za-z0-9]+)*)?"
FAILURE_STAGES = {
    "context": "context",
    "arguments": "context",
    "download": "download",
    "checksum": "checksum",
    "archive": "archive",
    "bash": "missing_bash",
    "skill": "skill_execution",
    "version": "version",
    "cleanup": "cleanup",
    "supervision": "supervision_unverified",
    "retention": "retention_prerequisite",
    "interrupted": "interruption",
}


class CheckError(Exception):
    """An operation failed; underlying output must never enter the Actions log."""


class PublicRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = parse.urlsplit(newurl)
        if (
            target.scheme != "https"
            or target.hostname not in {"github.com", "release-assets.githubusercontent.com"}
            or target.username is not None
            or target.password is not None
            or target.port not in (None, 443)
        ):
            raise CheckError("download")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download(url, expected_hash, destination, limit):
    if url not in {SKILL_URL, AZD_URL}:
        raise CheckError("download")
    # No proxy, .netrc, authentication headers, or inherited environment settings.
    opener = request.build_opener(request.ProxyHandler({}), PublicRedirect())
    req = request.Request(url, headers={"User-Agent": "foundry-prerequisite-check"})  # noqa: S310 -- fixed HTTPS URLs; redirect hosts restricted.
    digest = hashlib.sha256()
    size = 0
    with opener.open(req, timeout=60) as response, destination.open("xb") as output:
        if response.status != 200:
            raise CheckError("download")
        while chunk := response.read(1024 * 1024):
            size += len(chunk)
            if size > limit:
                raise CheckError("download")
            digest.update(chunk)
            output.write(chunk)
    if digest.hexdigest() != expected_hash:
        raise CheckError("checksum")


def context():
    if (
        os.environ.get("GITHUB_REF") != "refs/heads/main"
        or os.environ.get("GITHUB_REF_PROTECTED") != "true"
        or os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch"
        or platform.system() != "Linux"
        or platform.machine() != "x86_64"
    ):
        raise CheckError("context")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "")
    if not re.fullmatch(r"[1-9][0-9]*", run_id) or not re.fullmatch(r"[1-9][0-9]*", attempt):
        raise CheckError("context")
    temp = Path(os.environ.get("RUNNER_TEMP", ""))
    if not temp.is_absolute() or not temp.is_dir():
        raise CheckError("context")
    return temp.resolve(), f"foundry-prerequisites-{run_id}-{attempt}.json"


def invocation_user_agent():
    event_path = Path(os.environ.get("GITHUB_EVENT_PATH", ""))
    if not event_path.is_absolute():
        raise CheckError("context")
    try:
        with event_path.open("rb") as event:
            data = event.read(1024 * 1024 + 1)
        if len(data) > 1024 * 1024:
            raise CheckError("context")
        payload = json.loads(data)
        value = payload["inputs"]["user_agent"]
    except (OSError, ValueError, KeyError, TypeError) as failure:
        raise CheckError("context") from failure
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", value):
        raise CheckError("context")
    return value


def validate_upstream_user_agent(script, user_agent):
    content = script.read_bytes()
    declarations = re.findall(
        rb"^export AZURE_DEV_USER_AGENT=([A-Za-z0-9][A-Za-z0-9_.-]{0,63})$",
        content, re.MULTILINE,
    )
    if content.count(b"AZURE_DEV_USER_AGENT") != 1 or len(declarations) != 1 or declarations[0].decode("ascii") != user_agent:
        raise CheckError("context")


def isolated_environment(root, user_agent):
    directories = {
        "HOME": "home",
        "XDG_CONFIG_HOME": "xdg-config",
        "XDG_CACHE_HOME": "xdg-cache",
        "XDG_DATA_HOME": "xdg-data",
        "XDG_STATE_HOME": "xdg-state",
        "XDG_RUNTIME_DIR": "xdg-runtime",
        "AZD_CONFIG_DIR": "azd-config",
        "AZURE_CONFIG_DIR": "azure-config",
        "TMPDIR": "tmp",
    }
    env = {}
    for key, name in directories.items():
        directory = root / name
        directory.mkdir(mode=0o700)
        env[key] = str(directory)
    env.update({
        "PATH": f"{root / 'bin'}:{SYSTEM_PATH}",
        "LANG": "C",
        "LC_ALL": "C",
        "AZURE_DEV_USER_AGENT": user_agent,
        "AZURE_DEV_COLLECT_TELEMETRY": "no",
        "AZD_NO_PROMPT": "true",
        "RUNNER_TRACKING_ID": os.environ.get("RUNNER_TRACKING_ID", ""),
    })
    return env


_PROCESS_STARTED = False
_CAPTURE_LIMIT = 1024 * 1024


def command(args, cwd, env):
    global _PROCESS_STARTED
    if not all(hasattr(os, name) for name in ("pidfd_open", "P_PIDFD", "waitid", "WEXITED", "WNOHANG")):
        raise CheckError("supervision")
    process = subprocess.Popen(  # noqa: S603 -- pinned inputs and private environment.
        args, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, close_fds=True,
    )
    _PROCESS_STARTED = True
    fd = None
    streams = {process.stdout: bytearray(), process.stderr: bytearray()}
    deadline = time.monotonic() + 180
    status = None
    try:
        # Fresh single-threaded launcher assumes default SIGCHLD and no external reaper.
        fd = os.pidfd_open(process.pid, 0)
        with selectors.DefaultSelector() as selector:
            for stream in streams:
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ)
            while selector.get_map() or status is None:
                if time.monotonic() >= deadline:
                    raise subprocess.TimeoutExpired("prerequisite", 180)
                if status is None:
                    info = os.waitid(os.P_PIDFD, fd, os.WEXITED | os.WNOHANG)
                    if info is not None:
                        if info.si_code not in (os.CLD_EXITED, os.CLD_KILLED, os.CLD_DUMPED):
                            raise CheckError("supervision")
                        status = info.si_status if info.si_code == os.CLD_EXITED else -info.si_status
                        process.returncode = status
                for key, _ in selector.select(min(.05, max(0, deadline - time.monotonic()))):
                    data = os.read(key.fd, 8192)
                    if not data:
                        selector.unregister(key.fileobj)
                    else:
                        streams[key.fileobj].extend(data)
                        if sum(map(len, streams.values())) > _CAPTURE_LIMIT:
                            raise CheckError("supervision")
        return subprocess.CompletedProcess(args, status, streams[process.stdout].decode(),
                                           streams[process.stderr].decode())
    finally:
        if fd is not None:
            os.close(fd)
        for stream in streams:
            stream.close()


def install_azd(root):
    archive = root / "azd.tar.gz"
    download(AZD_URL, AZD_SHA256, archive, 256 * 1024 * 1024)
    with tarfile.open(archive, "r:gz") as package:
        members = package.getmembers()
        if (
            len(members) != 2
            or {member.name for member in members} != {"azd-linux-amd64", "NOTICE.txt"}
            or any(
                member.type != tarfile.REGTYPE
                or member.linkname
                or member.sparse is not None
                or not 0 < member.size <= 256 * 1024 * 1024
                or member.mode & 0o7000
                for member in members
            )
        ):
            raise CheckError("archive")
        executable = next(member for member in members if member.name == "azd-linux-amd64")
        if not executable.mode & 0o100:
            raise CheckError("archive")
        binary = package.extractfile(executable)
        if binary is None:
            raise CheckError("archive")
        with binary, (root / "bin" / "azd").open("xb") as output:
            shutil.copyfileobj(binary, output)
    (root / "bin" / "azd").chmod(0o700)


def check(root, user_agent):
    env = isolated_environment(root, user_agent)
    (root / "bin").mkdir(mode=0o700)
    skill_root = root / "skill"
    scripts = skill_root / "scripts"
    scripts.mkdir(parents=True, mode=0o700)
    script = scripts / "check-and-setup-dependencies.sh"
    download(SKILL_URL, SKILL_SHA256, script, 64 * 1024)
    validate_upstream_user_agent(script, user_agent)
    install_azd(root)
    bash = shutil.which("bash", path="/usr/bin:/bin")
    if bash is None:
        raise CheckError("bash")
    result = command([bash, str(script)], skill_root, env)
    if result.returncode != 0 or not result.stdout.endswith(READY):
        raise CheckError("skill")
    version = command([str(root / "bin" / "azd"), "version"], skill_root, env)
    match = re.fullmatch(rf"azd version ({VERSION})(?: \([^\r\n]*\))?\n?", version.stdout)
    if version.returncode != 0 or not match:
        raise CheckError("version")
    return match.group(1)


def cleanup(temp, receipt_name):
    raise CheckError("cleanup")


def retained_root():
    parent = Path("/var/tmp")
    meta = parent.lstat()
    if (not stat.S_ISDIR(meta.st_mode) or meta.st_uid != 0
            or meta.st_mode & 0o7777 != 0o1777 or parent.resolve() != parent):
        raise CheckError("retention")
    for key in ("RUNNER_TEMP", "GITHUB_WORKSPACE", "RUNNER_WORKSPACE"):
        raw = os.environ.get(key, "")
        if key == "RUNNER_WORKSPACE" and not raw:
            continue
        value = Path(raw)
        if not value.is_absolute() or not value.is_dir():
            raise CheckError("retention")
        managed = value.resolve()
        if parent == managed or parent in managed.parents or managed in parent.parents:
            raise CheckError("retention")
    root = Path(tempfile.mkdtemp(prefix="foundry-prerequisites-", dir=parent))
    if root.parent != parent or root.stat().st_mode & 0o777 != 0o700:
        raise CheckError("retention")
    return root


def run():
    context()
    user_agent = invocation_user_agent()
    tracking = os.environ.get("RUNNER_TRACKING_ID", "")
    if tracking and not re.fullmatch(r"github_[0-9a-fA-F-]{36}", tracking):
        raise CheckError("context")
    root = retained_root()
    return check(root, user_agent)


def interrupted(signum, frame):
    raise CheckError("interrupted")


def failure_stage(failure):
    if isinstance(failure, CheckError):
        return FAILURE_STAGES.get(str(failure), "unexpected_io")
    if isinstance(failure, subprocess.TimeoutExpired):
        return "timeout"
    if isinstance(failure, error.URLError):
        return "download"
    if isinstance(failure, tarfile.TarError):
        return "archive"
    return "unexpected_io"


def report_failure(failure):
    print(f"failure_stage={failure_stage(failure)}")
    print("owned_process_may_be_running=true" if _PROCESS_STARTED else "owned_process_may_be_running=false")
    print("foundry_prerequisites_check_failed", file=sys.stderr)


def main():
    previous_handlers = {}
    try:
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous_handlers[signum] = signal.signal(signum, interrupted)
        if sys.argv[1:] == ["--cleanup"]:
            temp, receipt_name = context()
            try:
                cleanup(temp, receipt_name)
            except (OSError, ValueError) as failure:
                raise CheckError("cleanup") from failure
            print("foundry_prerequisites_cleanup=complete")
        elif not sys.argv[1:]:
            version = run()
            print(f"azd_version={version}")
            print("foundry_prerequisites=ready_retained_state_only")
        else:
            raise CheckError("arguments")
        return 0
    except (CheckError, OSError, ValueError, error.URLError, tarfile.TarError, subprocess.SubprocessError) as failure:
        report_failure(failure)
        return 1
    finally:
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)


if __name__ == "__main__":
    sys.excepthook = lambda _kind, failure, _traceback: report_failure(failure)
    raise SystemExit(main())

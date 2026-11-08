"""Run the pinned prerequisite check with retained, isolated tool state."""

import os
import platform
import pwd
import re
import selectors
import signal
import stat
import subprocess
import sys
import tarfile
import time
from pathlib import Path
from urllib import error

import check_foundry_prerequisites as helper


TRACKING_ID = re.compile(
    r"github_[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
OUTPUT_LIMIT = 128 * 1024
COMMAND_TIMEOUT = 180
_PROCESS_ATTEMPTED = False
STAGES = {
    "context",
    "storage",
    "tracking",
    "download",
    "checksum",
    "archive",
    "bash",
    "runtime",
    "timeout",
    "output",
    "skill",
    "version",
    "interruption",
}


def fail(stage):
    raise helper.CheckError(stage)


def context():
    temp, _ = helper.context()
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    sha = os.environ.get("GITHUB_SHA", "")
    workflow_sha = os.environ.get("CHECK_WORKFLOW_SHA", "")
    workflow_ref = os.environ.get("CHECK_WORKFLOW_REF", "")
    if (
        repo != "michael-rechani/foundry-agent-accelerator"
        or os.environ.get("RUNNER_ENVIRONMENT") != "self-hosted"
        or not re.fullmatch(r"[0-9a-f]{40}", sha)
        or workflow_sha != sha
        or workflow_ref
        != f"{repo}/.github/workflows/check-foundry-prerequisites-retained.yml@refs/heads/main"
        or platform.system() != "Linux"
        or platform.machine() != "x86_64"
    ):
        fail("context")
    workspace = Path(os.environ.get("GITHUB_WORKSPACE", ""))
    if not workspace.is_absolute() or not workspace.is_dir():
        fail("context")
    return temp, workspace


def tracking_id():
    value = os.environ.get("RUNNER_TRACKING_ID", "")
    if value and not TRACKING_ID.fullmatch(value):
        fail("tracking")
    return value


def reserve_state(home, temp, workspace, run_id, attempt):
    if os.geteuid() == 0:
        fail("storage")
    home = Path(home)
    if not home.is_absolute() or home.is_symlink():
        fail("storage")
    home = home.resolve(strict=True)
    temp = Path(temp).resolve(strict=True)
    workspace = Path(workspace).resolve(strict=True)
    if temp.name != "_temp" or not temp.is_dir() or not workspace.is_dir():
        fail("storage")
    if not re.fullmatch(r"[1-9][0-9]*", run_id) or not re.fullmatch(
        r"[1-9][0-9]*", attempt
    ):
        fail("context")
    name = f".foundry-prerequisites-{run_id}-{attempt}"
    candidate = home / name
    if candidate.is_relative_to(temp.parent) or candidate.is_relative_to(workspace):
        fail("storage")
    base = os.open(home, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        info = os.fstat(base)
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.geteuid()
            or info.st_mode & 0o022
        ):
            fail("storage")
        os.mkdir(name, mode=0o700, dir_fd=base)
        child = os.open(
            name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=base
        )
        try:
            opened = os.fstat(child)
            named = os.stat(name, dir_fd=base, follow_symlinks=False)
            if (
                not stat.S_ISDIR(opened.st_mode)
                or opened.st_uid != os.geteuid()
                or stat.S_IMODE(opened.st_mode) != 0o700
                or (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino)
            ):
                fail("storage")
        finally:
            os.close(child)
    finally:
        os.close(base)
    return candidate


def check_pidfd_support():
    if (
        not hasattr(os, "pidfd_open")
        or not hasattr(os, "P_PIDFD")
        or not hasattr(os, "WNOWAIT")
        or signal.getsignal(signal.SIGCHLD) != signal.SIG_DFL
    ):
        fail("runtime")
    try:
        fd = os.pidfd_open(os.getpid(), 0)
        os.close(fd)
    except OSError as failure:
        raise helper.CheckError("runtime") from failure


def command(args, cwd, env, stage, timeout=COMMAND_TIMEOUT, limit=OUTPUT_LIMIT):
    global _PROCESS_ATTEMPTED
    check_pidfd_support()
    _PROCESS_ATTEMPTED = True
    process = subprocess.Popen(  # noqa: S603 -- arguments are fixed trusted paths.
        args,
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        close_fds=True,
    )
    pidfd = None
    try:
        pidfd = os.pidfd_open(process.pid, 0)
        output = bytearray()
        observed = None
        ended = False
        deadline = time.monotonic() + timeout
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ, "output")
            selector.register(pidfd, selectors.EVENT_READ, "process")
            while not ended or observed is None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    fail("timeout")
                for key, _ in selector.select(remaining):
                    if key.data == "output":
                        chunk = os.read(key.fd, min(65536, limit + 1 - len(output)))
                        if chunk:
                            output.extend(chunk)
                            if len(output) > limit:
                                fail("output")
                        else:
                            selector.unregister(key.fileobj)
                            ended = True
                    else:
                        observed = os.waitid(
                            os.P_PIDFD,
                            pidfd,
                            os.WEXITED | os.WNOHANG | os.WNOWAIT,
                        )
                        if observed is not None:
                            selector.unregister(pidfd)
        if observed.si_pid != process.pid:
            fail("runtime")
        reaped = os.waitid(os.P_PIDFD, pidfd, os.WEXITED | os.WNOHANG)
        if reaped is None or reaped.si_pid != process.pid:
            fail("runtime")
        if reaped.si_code == os.CLD_EXITED:
            process.returncode = reaped.si_status
        else:
            process.returncode = -reaped.si_status
        if process.returncode != 0:
            fail(stage)
        return bytes(output)
    finally:
        if pidfd is not None:
            os.close(pidfd)
        if process.stdout is not None:
            process.stdout.close()


def check(root, user_agent, tracking):
    env = helper.isolated_environment(root, user_agent)
    if tracking:
        env["RUNNER_TRACKING_ID"] = tracking
    (root / "bin").mkdir(mode=0o700)
    skill_root = root / "skill"
    scripts = skill_root / "scripts"
    scripts.mkdir(parents=True, mode=0o700)
    script = scripts / "check-and-setup-dependencies.sh"
    helper.download(helper.SKILL_URL, helper.SKILL_SHA256, script, 64 * 1024)
    helper.validate_upstream_user_agent(script, user_agent)
    helper.install_azd(root)
    bash = Path("/usr/bin/bash")
    if not bash.is_file():
        fail("bash")
    output = command([str(bash), str(script)], skill_root, env, "skill")
    if not output.endswith(helper.READY.encode("ascii")):
        fail("skill")
    version = command([str(root / "bin" / "azd"), "version"], skill_root, env, "version")
    try:
        text = version.decode("ascii")
    except UnicodeDecodeError as failure:
        raise helper.CheckError("version") from failure
    match = re.fullmatch(rf"azd version ({helper.VERSION})(?: \([^\r\n]*\))?\n?", text)
    if not match:
        fail("version")
    return match.group(1)


def run():
    temp, workspace = context()
    user_agent = helper.invocation_user_agent()
    tracking = tracking_id()
    check_pidfd_support()
    try:
        home = pwd.getpwuid(os.geteuid()).pw_dir
        root = reserve_state(
            home,
            temp,
            workspace,
            os.environ.get("GITHUB_RUN_ID", ""),
            os.environ.get("GITHUB_RUN_ATTEMPT", ""),
        )
    except (OSError, ValueError, KeyError) as failure:
        raise helper.CheckError("storage") from failure
    return check(root, user_agent, tracking)


def interrupted(_signum, _frame):
    fail("interruption")


def report_failure(failure):
    if isinstance(failure, helper.CheckError) and str(failure) in STAGES:
        stage = str(failure)
    elif isinstance(failure, error.URLError):
        stage = "download"
    elif isinstance(failure, tarfile.TarError):
        stage = "archive"
    else:
        stage = "unexpected_io"
    print(f"failure_stage={stage}")
    print(f"owned_process_may_be_running={str(_PROCESS_ATTEMPTED).lower()}")
    print("foundry_prerequisites_check_failed", file=sys.stderr)


def main():
    global _PROCESS_ATTEMPTED
    _PROCESS_ATTEMPTED = False
    previous_handlers = {}
    try:
        if sys.argv[1:]:
            fail("context")
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous_handlers[signum] = signal.signal(signum, interrupted)
        version = run()
        print(f"azd_version={version}")
        print("foundry_prerequisites=ready_retained_state_only")
        return 0
    except (helper.CheckError, OSError, ValueError, error.URLError, tarfile.TarError) as failure:
        report_failure(failure)
        return 1
    finally:
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)


if __name__ == "__main__":
    sys.excepthook = lambda _kind, failure, _traceback: report_failure(failure)
    raise SystemExit(main())

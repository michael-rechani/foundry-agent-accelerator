"""Run the pinned Foundry dependency script without shared configuration or credentials."""

import contextlib
import hashlib
import json
import os
import platform
import re
import selectors
import shutil
import signal
import stat
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import uuid
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
MAX_CAPTURE_BYTES = 1024 * 1024
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
    "output_limit": "output_limit",
    "interrupted": "interruption",
}


class CheckError(Exception):
    """An operation failed; underlying output must never enter the Actions log."""


class TeardownUnverified(CheckError):
    """Child teardown was not verified; owned scratch must remain quarantined."""


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
    })
    return env


def _require_process_supervision():
    if (sys.platform != "linux" or not hasattr(os, "pidfd_open")
            or not hasattr(os, "P_PIDFD") or not hasattr(os, "WNOWAIT")
            or signal.getsignal(signal.SIGCHLD) != signal.SIG_DFL
            or threading.active_count() != 1):
        raise CheckError("cleanup")


def _owned_child_status(process, pidfd):
    if process.returncode is not None:
        raise CheckError("cleanup")
    try:
        status = os.waitid(os.P_PIDFD, pidfd, os.WEXITED | os.WNOHANG | os.WNOWAIT)
    except OSError:
        raise CheckError("cleanup") from None
    if status is not None and (status.si_pid != process.pid or status.si_code not in (
            os.CLD_EXITED, os.CLD_KILLED, os.CLD_DUMPED)):
        raise CheckError("cleanup")
    return status


def _signal_owned_group(process, pidfd):
    _require_process_supervision()
    _owned_child_status(process, pidfd)
    try:
        group = os.getpgid(process.pid)
    except OSError:
        raise CheckError("cleanup") from None
    if group != process.pid:
        raise CheckError("cleanup")
    # WNOWAIT retains the owned leader (including its zombie) until after signaling.
    _owned_child_status(process, pidfd)
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        # Absence is acceptable only for an exited, still-owned leader.
        if _owned_child_status(process, pidfd) is None:
            raise CheckError("cleanup") from None

def command(args, cwd, env):
    _require_process_supervision()
    try:
        process = subprocess.Popen(  # noqa: S603 -- pinned script or selected executable, fixed arguments and isolated environment.
            args, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, start_new_session=True,
        )
    except BaseException:
        # No returned handle means child creation/teardown cannot be certified here.
        raise TeardownUnverified("cleanup") from None
    teardown_verified = False
    try:
        with contextlib.ExitStack() as handles:
            handles.callback(process.stdout.close)
            handles.callback(process.stderr.close)
            # Failure to acquire a binding must not fall back to numeric signaling.
            pidfd = os.pidfd_open(process.pid)
            handles.callback(os.close, pidfd)
            output = {process.stdout: bytearray(), process.stderr: bytearray()}
            captured = 0
            group_stopped = False
            deadline = time.monotonic() + 180
            try:
                with selectors.DefaultSelector() as selector:
                    for stream in output:
                        os.set_blocking(stream.fileno(), False)
                        selector.register(stream, selectors.EVENT_READ)
                    while True:
                        if _owned_child_status(process, pidfd) is not None and not group_stopped:
                            _signal_owned_group(process, pidfd)
                            group_stopped = True
                        if group_stopped and not selector.get_map():
                            break
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise subprocess.TimeoutExpired(args, 180)
                        for key, _events in selector.select(min(remaining, 0.05)):
                            chunk = os.read(key.fd, 32768)
                            if chunk:
                                if captured + len(chunk) > MAX_CAPTURE_BYTES:
                                    raise CheckError("output_limit")
                                output[key.fileobj].extend(chunk)
                                captured += len(chunk)
                            else:
                                selector.unregister(key.fileobj)
            finally:
                if not group_stopped:
                    _signal_owned_group(process, pidfd)
                # This is the first reaping operation. Never signal the group afterward.
                process.wait(timeout=5)
                teardown_verified = True
            stdout, stderr = (
                bytes(output[stream]).decode(stream.encoding, stream.errors)
                .replace("\r\n", "\n").replace("\r", "\n")
                for stream in (process.stdout, process.stderr)
            )
        return subprocess.CompletedProcess(args, process.returncode, stdout, stderr)
    except BaseException:
        if not teardown_verified:
            raise TeardownUnverified("cleanup") from None
        raise

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
    installed_azd = shutil.which("azd", path=SYSTEM_PATH)
    if installed_azd is not None:
        (root / "bin" / "azd").symlink_to(Path(installed_azd).resolve())
    bash = shutil.which("bash", path="/usr/bin:/bin")
    if bash is None:
        raise CheckError("bash")
    result = command([bash, str(script)], skill_root, env)
    if result.returncode != 0:
        if installed_azd is not None or result.returncode != 1 or result.stdout or result.stderr != MISSING_AZD:
            raise CheckError("skill")
        install_azd(root)
        result = command([bash, str(script)], skill_root, env)
    if result.returncode != 0 or not result.stdout.endswith(READY):
        raise CheckError("skill")
    version = command([str(root / "bin" / "azd"), "version"], skill_root, env)
    match = re.fullmatch(rf"azd version ({VERSION})(?: \([^\r\n]*\))?\n?", version.stdout)
    if version.returncode != 0 or not match:
        raise CheckError("version")
    # Only the numeric version is published, never the commit or extension command output.
    return match.group(1)


def cleanup(temp, receipt_name):
    receipt = temp / receipt_name
    if not receipt.exists() and not receipt.is_symlink():
        return
    if not stat.S_ISREG(receipt.lstat().st_mode):
        raise CheckError("cleanup")
    record = json.loads(receipt.read_text())
    if (
        not isinstance(record, dict)
        or set(record) != {"name", "owner", "process_teardown"}
        or record["process_teardown"] != "verified"
        or not isinstance(record["name"], str)
        or not re.fullmatch(r"foundry-prerequisites-[a-z0-9_]{8}", record["name"])
        or not isinstance(record["owner"], str)
        or not re.fullmatch(r"[0-9a-f]{32}", record["owner"])
    ):
        raise CheckError("cleanup")
    root = temp / record["name"]
    if root.exists() or root.is_symlink():
        marker = root / ".run-owned"
        if (
            not stat.S_ISDIR(root.lstat().st_mode)
            or not stat.S_ISREG(marker.lstat().st_mode)
            or marker.read_text() != record["owner"]
        ):
            raise CheckError("cleanup")
        shutil.rmtree(root)
    receipt.unlink()


def run():
    temp, receipt_name = context()
    user_agent = invocation_user_agent()
    receipt = temp / receipt_name
    # Reserve the receipt exclusively: retries must not overwrite another invocation.
    registration = os.fdopen(os.open(receipt, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), "w")
    root = None
    retain_scratch = False
    record = None
    try:
        root = Path(tempfile.mkdtemp(prefix="foundry-prerequisites-", dir=temp))
        owner = uuid.uuid4().hex
        (root / ".run-owned").write_text(owner)
        # Persist the veto before any command can launch; a later failure need not rewrite it.
        record = {"name": root.name, "owner": owner, "process_teardown": "unverified"}
        json.dump(record, registration)
        registration.close()
        version = check(root, user_agent)
    except TeardownUnverified:
        retain_scratch = True
        raise
    finally:
        registration.close()
        if not retain_scratch:
            if root is not None:
                try:
                    if record is not None:
                        record["process_teardown"] = "verified"
                        with receipt.open("w") as output:
                            json.dump(record, output)
                    shutil.rmtree(root)
                    receipt.unlink()
                except OSError as failure:
                    raise CheckError("cleanup") from failure
            else:
                receipt.unlink()
    return version

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
            print("foundry_prerequisites=ready")
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

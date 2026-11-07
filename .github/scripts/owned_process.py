"""Disconnected Linux owned-process supervision experiment; not a security boundary."""

import ctypes
import json
import os
import selectors
import signal
import subprocess  # noqa: S404
import sys
import time
from dataclasses import dataclass

_REQUEST_LIMIT = 4096
_RESPONSE_LIMIT = 256
_OUTCOMES = frozenset({"success", "nonzero", "timeout", "output_limit"})


@dataclass(frozen=True)
class Result:
    verified: bool
    outcome: str


def _unverified():
    return Result(False, "unverified")


def supervise(argv, *, timeout=2.0, grace=2.0, output_limit=65536):
    """Run a bounded command; never treat an unverified result as teardown proof."""
    if (
        sys.platform != "linux"
        or not isinstance(argv, list)
        or not argv
        or any(not isinstance(arg, str) or "\x00" in arg for arg in argv)
        or not os.path.isabs(argv[0])
        or not isinstance(timeout, (int, float))
        or not isinstance(grace, (int, float))
        or not 0 < timeout <= 30
        or not 0 < grace <= 30
        or type(output_limit) is not int
        or not 0 <= output_limit <= 1048576
    ):
        return _unverified()
    try:
        request = json.dumps(
            {"argv": argv, "timeout": timeout, "grace": grace, "output_limit": output_limit},
            separators=(",", ":"),
            allow_nan=False,
        ).encode() + b"\n"
    except (ValueError, UnicodeError, OverflowError):
        return _unverified()
    if len(request) > _REQUEST_LIMIT:
        return _unverified()
    deadline = time.monotonic() + timeout + grace + 2
    try:
        proc = subprocess.Popen(  # noqa: S603
            [sys.executable, "-I", os.path.abspath(__file__), "--supervise"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
    except (OSError, ValueError):
        return _unverified()
    data = bytearray()
    valid = True
    try:
        proc.stdin.write(request)
        proc.stdin.close()
        os.set_blocking(proc.stdout.fileno(), False)
        with selectors.DefaultSelector() as selector:
            selector.register(proc.stdout, selectors.EVENT_READ)
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    valid = False
                    break
                events = selector.select(remaining)
                if not events:
                    valid = False
                    break
                chunk = os.read(proc.stdout.fileno(), _RESPONSE_LIMIT + 1)
                if not chunk:
                    break
                data.extend(chunk)
                if len(data) > _RESPONSE_LIMIT:
                    valid = False
                    break
        if valid:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                valid = False
            else:
                try:
                    valid = proc.wait(timeout=remaining) == 0
                except subprocess.TimeoutExpired:
                    valid = False
    except (OSError, ValueError):
        valid = False
    finally:
        if not valid:
            try:
                proc.kill()
                proc.wait(timeout=0.2)
            except (OSError, subprocess.TimeoutExpired):
                pass
        proc.stdout.close()
    if not valid:
        return _unverified()
    # One exact terminal frame, with no trailing or duplicate bytes.
    for outcome in _OUTCOMES:
        expected = ('{"verified":true,"outcome":"' + outcome + '"}\n').encode()
        if data == expected:
            return Result(True, outcome)
    return _unverified()


def _has_no_children():
    try:
        os.waitpid(-1, os.WNOHANG)
    except ChildProcessError:
        return True
    return False


def _set_subreaper():
    libc = ctypes.CDLL(None, use_errno=True)
    prctl = libc.prctl
    prctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong]
    prctl.restype = ctypes.c_int
    if prctl(36, 1, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), "prctl failed")


def _supervisor(request):
    """Return a terminal result only after group signaling and ECHILD."""
    if (
        sys.platform != "linux"
        or not hasattr(os, "pidfd_open")
        or not hasattr(os, "P_PIDFD")
        or not hasattr(os, "WNOWAIT")
        or signal.getsignal(signal.SIGCHLD) not in (signal.SIG_DFL, signal.SIG_IGN)
    ):
        return None
    # An ignored SIGCHLD is abnormal: do not normalize an auto-reaping process.
    if signal.getsignal(signal.SIGCHLD) != signal.SIG_DFL:
        return None
    signal.signal(signal.SIGCHLD, signal.SIG_DFL)
    _set_subreaper()
    if not _has_no_children():
        return None
    timeout = request["timeout"]
    grace = request["grace"]
    limit = request["output_limit"]
    start = time.monotonic()
    proc = subprocess.Popen(  # noqa: S603
        request["argv"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        close_fds=True,
        start_new_session=True,
        env={"PATH": os.defpath},
    )
    fd = None
    try:
        fd = os.pidfd_open(proc.pid, 0)
        if os.getpgrp() == proc.pid:
            return None
        count = 0
        outcome = None
        with selectors.DefaultSelector() as selector:
            for stream in (proc.stdout, proc.stderr):
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ)
            while outcome is None:
                info = os.waitid(os.P_PIDFD, fd, os.WEXITED | os.WNOHANG | os.WNOWAIT)
                if info is not None:
                    outcome = "success" if info.si_code == os.CLD_EXITED and info.si_status == 0 else "nonzero"
                    break
                if time.monotonic() >= start + timeout:
                    outcome = "timeout"
                    break
                for key, _ in selector.select(min(0.02, max(0, start + timeout - time.monotonic()))):
                    chunk = os.read(key.fd, 8192)
                    if not chunk:
                        selector.unregister(key.fileobj)
                    else:
                        count += len(chunk)
                        if count > limit:
                            outcome = "output_limit"
                            break
            # Retained pidfd-bound leader is never reaped before this signal.
            os.waitid(os.P_PIDFD, fd, os.WEXITED | os.WNOHANG | os.WNOWAIT)
            if os.getpgid(proc.pid) != proc.pid or os.getsid(proc.pid) != proc.pid:
                return None
            os.killpg(proc.pid, signal.SIGKILL)
            end = start + timeout + grace
            no_children = False
            while time.monotonic() < end:
                # Count bytes still queued when the leader exited, too.
                for key, _ in selector.select(0):
                    chunk = os.read(key.fd, 8192)
                    if not chunk:
                        selector.unregister(key.fileobj)
                    else:
                        count += len(chunk)
                        if count > limit and outcome not in ("timeout", "output_limit"):
                            outcome = "output_limit"
                if not no_children:
                    try:
                        pid, status = os.waitpid(-1, os.WNOHANG)
                    except ChildProcessError:
                        no_children = True
                    else:
                        if pid == proc.pid:
                            proc.returncode = os.waitstatus_to_exitcode(status)
                if no_children and not selector.get_map():
                    return outcome
                time.sleep(0.01)
        return None
    finally:
        if fd is not None:
            os.close(fd)
        proc.stdout.close()
        proc.stderr.close()


def _main():
    try:
        raw = sys.stdin.buffer.readline(_REQUEST_LIMIT + 1)
        if len(raw) > _REQUEST_LIMIT or not raw.endswith(b"\n") or sys.stdin.buffer.read(1):
            return 1
        request = json.loads(raw)
        if (
            type(request) is not dict
            or set(request) != {"argv", "timeout", "grace", "output_limit"}
            or type(request["argv"]) is not list
            or not request["argv"]
            or any(type(arg) is not str or "\x00" in arg for arg in request["argv"])
            or not os.path.isabs(request["argv"][0])
            or type(request["timeout"]) not in (int, float)
            or type(request["grace"]) not in (int, float)
            or not 0 < request["timeout"] <= 30
            or not 0 < request["grace"] <= 30
            or type(request["output_limit"]) is not int
            or not 0 <= request["output_limit"] <= 1048576
        ):
            return 1
        outcome = _supervisor(request)
        if outcome not in _OUTCOMES:
            return 1
        sys.stdout.write('{"verified":true,"outcome":"' + outcome + '"}\n')
        sys.stdout.flush()
        return 0
    except (OSError, ValueError, TypeError, KeyError, AttributeError, ImportError):
        return 1


if __name__ == "__main__":
    if sys.argv[1:] != ["--supervise"]:
        sys.exit(1)
    sys.exit(_main())

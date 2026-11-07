"""Worker-free Linux birth-bound transport experiment, not public supervision.

Trust requires a private inherited channel and an immutable trusted interpreter
and this file. No host/same-UID security boundary or descendant proof is claimed.
"""

import array
import fcntl
import math
import os
import secrets
import signal
import socket
import struct
import sys
import time
from dataclasses import dataclass

_FD = 3
_NONCE_SIZE = 32
_FRAME_LIMIT = 128
_ANCILLARY_LIMIT = socket.CMSG_SPACE(253 * array.array("i").itemsize) + socket.CMSG_SPACE(12)


@dataclass(frozen=True)
class BootstrapResult:
    verified: bool
    outcome: str


def _refused():
    return BootstrapResult(False, "unverified")


def _release(*, channels=(), fds=()):
    error = None
    for channel in channels:
        if channel is not None:
            try:
                channel.close()
            except OSError as exc:
                error = exc
    for fd in set(fds) - {None}:
        try:
            os.close(fd)
        except OSError as exc:
            error = exc
    if error is not None:
        raise error


def _remaining(channel, deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("bootstrap deadline")
    channel.settimeout(remaining)


def _supported():
    return (
        sys.platform == "linux"
        and all(hasattr(os, name) for name in (
            "posix_spawn", "POSIX_SPAWN_CLOSEFROM", "POSIX_SPAWN_DUP2",
            "pidfd_open", "P_PIDFD", "WNOWAIT", "WNOHANG",
        ))
        and hasattr(signal, "pidfd_send_signal")
        and all(hasattr(socket, name) for name in (
            "SCM_CREDENTIALS", "SO_PASSCRED", "SOCK_SEQPACKET", "MSG_CMSG_CLOEXEC",
        ))
    )


def _receive(channel, frame, *, expected_pid=None, want_fd=False):
    """Take exactly one frame; close every delivered fd on every rejection."""
    data, ancillary, flags, _ = channel.recvmsg(
        _FRAME_LIMIT, _ANCILLARY_LIMIT, socket.MSG_CMSG_CLOEXEC,
    )
    received = []
    credentials = []
    rights_messages = 0
    invalid = False
    try:
        for level, kind, raw in ancillary:
            if level == socket.SOL_SOCKET and kind == socket.SCM_RIGHTS:
                rights_messages += 1
                values = array.array("i")
                size = values.itemsize
                values.frombytes(raw[:len(raw) // size * size])
                received.extend(values)
                invalid |= len(raw) % size != 0
            elif level == socket.SOL_SOCKET and kind == socket.SCM_CREDENTIALS:
                if len(raw) != 12:
                    invalid = True
                else:
                    credentials.append(struct.unpack("3i", raw))
            else:
                invalid = True
        if (
            invalid
            or flags & (socket.MSG_TRUNC | socket.MSG_CTRUNC)
            or (frame is not None and data != frame)
            or len(received) != int(want_fd)
            or rights_messages != int(want_fd)
            or credentials != (
                [(expected_pid, os.getuid(), os.getgid())] if expected_pid is not None else []
            )
        ):
            raise ValueError("invalid private bootstrap frame")
        for fd in received:
            if not fcntl.fcntl(fd, fcntl.F_GETFD) & fcntl.FD_CLOEXEC:
                raise ValueError("received descriptor lacks CLOEXEC")
        result = received[0] if want_fd else None
        received.clear()
        return data, result
    finally:
        _release(fds=received)


def _send(channel, frame, ancillary=()):
    if channel.sendmsg([frame], ancillary) != len(frame):
        raise ValueError("short bootstrap send")


def _terminal(fd, deadline, grace):
    timed_out = False
    end = deadline
    while True:
        # The fd, never a numeric PID, selects the only child we can consume.
        info = os.waitid(os.P_PIDFD, fd, os.WEXITED | os.WNOHANG)
        if info is not None:
            if info.si_code not in (os.CLD_EXITED, os.CLD_KILLED, os.CLD_DUMPED):
                return _refused()
            outcome = (
                "timeout" if timed_out else
                "success" if info.si_code == os.CLD_EXITED and info.si_status == 0 else "nonzero"
            )
            return BootstrapResult(True, outcome)
        now = time.monotonic()
        if now >= end:
            if timed_out:
                return _refused()
            # Only after the complete authenticated handshake and pidfd type check.
            signal.pidfd_send_signal(fd, signal.SIGKILL)
            timed_out = True
            end = now + grace
        time.sleep(0.005)


def bootstrap_probe(*, exit_code=0, timeout=2.0, grace=1.0):
    """Test the reusable private transfer component with a worker-free child.

    This deliberately accepts no command, plugin, worker, or inner supervisor.
    verified means the bootstrap child's explicit kernel terminal status only.
    """
    return _launch(exit_code=exit_code, delay=0.0, early_exit=False, timeout=timeout, grace=grace)


def _launch(*, exit_code, delay, early_exit, timeout, grace):
    if (
        not _supported()
        or type(exit_code) is not int or not 0 <= exit_code <= 125
        or type(early_exit) is not bool
        or any(type(value) not in (int, float) or not math.isfinite(value)
               or not 0 < value <= 3 for value in (timeout, grace))
        or type(delay) not in (int, float) or not math.isfinite(delay) or not 0 <= delay <= .3
        or not os.path.isabs(sys.executable)
    ):
        return _refused()
    parent = child = None
    channel_source = null_source = null_fd = pidfd = None
    try:
        deadline = time.monotonic() + timeout
        parent, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        parent.setsockopt(socket.SOL_SOCKET, socket.SO_PASSCRED, 1)
        parent.settimeout(timeout)
        # Sources >=4 cannot be overwritten by ordered standard-fd actions.
        channel_source = fcntl.fcntl(child.fileno(), fcntl.F_DUPFD_CLOEXEC, 4)
        null_fd = os.open(os.devnull, os.O_RDWR | os.O_CLOEXEC)
        null_source = fcntl.fcntl(null_fd, fcntl.F_DUPFD_CLOEXEC, 4)
        actions = [(os.POSIX_SPAWN_DUP2, null_source, number) for number in (0, 1, 2)]
        actions += [
            (os.POSIX_SPAWN_DUP2, channel_source, _FD),
            (os.POSIX_SPAWN_CLOSEFROM, 4),
        ]
        # No Popen bookkeeping/destructor, numeric wait, or post-spawn pidfd_open.
        expected_pid = os.posix_spawn(
            sys.executable,
            [sys.executable, "-I", "-S", os.path.realpath(__file__),
             "--bootstrap-child", str(exit_code), str(delay), str(int(early_exit))],
            {}, file_actions=actions,
        )  # noqa: S606 -- fixed trusted interpreter/helper, never a caller command
        child.close()
        child = None
        local_fds = (channel_source, null_source, null_fd)
        channel_source = null_source = null_fd = None
        _release(fds=local_fds)
        nonce = secrets.token_bytes(_NONCE_SIZE)
        _remaining(parent, deadline)
        _send(parent, b"B1C" + nonce)
        _remaining(parent, deadline)
        _, pidfd = _receive(parent, b"B1P" + nonce, expected_pid=expected_pid, want_fd=True)
        # Kernel validates descriptor type and direct-child waitability, without
        # reopening proc paths or binding any numeric PID. ECHILD is unverified.
        os.waitid(os.P_PIDFD, pidfd, os.WEXITED | os.WNOHANG | os.WNOWAIT)
        _remaining(parent, deadline)
        _send(parent, b"B1A" + nonce)
        _remaining(parent, deadline)
        _receive(parent, b"B1D" + nonce, expected_pid=expected_pid)
        _remaining(parent, deadline)
        _receive(parent, b"")
        parent.close()
        parent = None
        return _terminal(pidfd, deadline, grace)
    except (OSError, ValueError, OverflowError, KeyboardInterrupt):
        # Even a plausible fd from a malformed/partial handshake cannot signal.
        # A prebind survivor independently times out; missing status is not zero.
        return _refused()
    finally:
        _release(channels=(parent, child), fds=(channel_source, null_source, null_fd, pidfd))


def _child(exit_code, delay, early_exit):
    if early_exit:
        return 71
    fd = None
    with socket.socket(fileno=_FD) as channel:
        os.set_inheritable(_FD, False)
        # Independent bound even if parent crashes before challenge or ACK.
        channel.settimeout(1.0)
        try:
            challenge, _ = _receive(channel, None)
            if len(challenge) != 3 + _NONCE_SIZE or not challenge.startswith(b"B1C"):
                return 72
            nonce = challenge[3:]
            # Only self-open while alive, before any possible worker creation.
            fd = os.pidfd_open(os.getpid(), 0)
            _send(channel, b"B1P" + nonce, [
                (socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", [fd])),
            ])
            _receive(channel, b"B1A" + nonce)
            _send(channel, b"B1D" + nonce)
        except (OSError, ValueError):
            return 73
        finally:
            if fd is not None:
                os.close(fd)
    # No worker exists: the private channel is already closed, not inherited.
    time.sleep(delay)
    return exit_code


if __name__ == "__main__":
    if len(sys.argv) != 5 or sys.argv[1] != "--bootstrap-child":
        sys.exit(74)
    sys.exit(_child(int(sys.argv[2]), float(sys.argv[3]), bool(int(sys.argv[4]))))

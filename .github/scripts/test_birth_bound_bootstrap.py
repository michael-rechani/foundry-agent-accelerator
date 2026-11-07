import array
import contextlib
import errno
import fcntl
import os
import signal
import socket
import struct
import sys
import types
import unittest
from unittest import mock

import birth_bound_bootstrap as subject
import owned_process


def status(code=0):
    return types.SimpleNamespace(si_code=os.CLD_EXITED, si_status=code)


def credentials(pid=123):
    return (socket.SOL_SOCKET, socket.SCM_CREDENTIALS, struct.pack("3i", pid, os.getuid(), os.getgid()))


def rights(*fds):
    return (socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", fds).tobytes())


class FrameTests(unittest.TestCase):
    def test_strict_rejections_close_all_delivered_descriptors_without_signals(self):
        cases = [
            (b"wrong", [credentials(), rights(7)], 0),
            (b"frame", [rights(7)], 0),
            (b"frame", [credentials(456), rights(7)], 0),
            (b"frame", [credentials(), credentials(), rights(7)], 0),
            (b"frame", [credentials(), rights(7, 8)], 0),
            (b"frame", [credentials(), rights(7), rights(8)], 0),
            (b"frame", [credentials(), rights(7)], socket.MSG_TRUNC),
            (b"frame", [credentials(), rights(7)], socket.MSG_CTRUNC),
            (b"frame", [credentials(), rights(7), (999, 999, b"bad")], 0),
            (b"frame", [credentials(), (socket.SOL_SOCKET, socket.SCM_RIGHTS,
                                      array.array("i", [7]).tobytes() + b"x")], 0),
            (b"frame", [(socket.SOL_SOCKET, socket.SCM_CREDENTIALS, b"x"), rights(7)], 0),
            (b"frame", [credentials()], 0),
        ]
        for data, ancillary, flags in cases:
            with self.subTest(ancillary=ancillary, flags=flags), \
                    mock.patch.object(subject.os, "close") as close, \
                    mock.patch.object(subject.signal, "pidfd_send_signal") as send:
                channel = mock.Mock()
                channel.recvmsg.return_value = data, ancillary, flags, None
                with self.assertRaises(ValueError):
                    subject._receive(channel, b"frame", expected_pid=123, want_fd=True)
                expected = {7, 8} if any(item == rights(7, 8) or item == rights(8)
                                        for item in ancillary) else {7}
                if ancillary == [credentials()]:
                    expected = set()
                self.assertEqual({call.args[0] for call in close.call_args_list}, expected)
                send.assert_not_called()

    def test_atomic_cloexec_required_and_verified(self):
        channel = mock.Mock()
        channel.recvmsg.return_value = b"frame", [credentials(), rights(7)], 0, None
        with mock.patch.object(subject.fcntl, "fcntl", return_value=0), \
                mock.patch.object(subject.os, "close") as close:
            with self.assertRaises(ValueError):
                subject._receive(channel, b"frame", expected_pid=123, want_fd=True)
            close.assert_called_once_with(7)
        self.assertEqual(channel.recvmsg.call_args.args[2], socket.MSG_CMSG_CLOEXEC)
        with mock.patch.object(subject.fcntl, "fcntl", side_effect=OSError(errno.EBADF, "bad")), \
                mock.patch.object(subject.os, "close") as close:
            with self.assertRaises(OSError):
                subject._receive(channel, b"frame", expected_pid=123, want_fd=True)
            close.assert_called_once_with(7)

    def test_real_rejected_rights_do_not_leak(self):
        before = len(os.listdir("/proc/self/fd"))
        # Use explicit ownership for both ends (no discarded socket destructor).
        left, right = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        try:
            left.setsockopt(socket.SOL_SOCKET, socket.SO_PASSCRED, 1)
            right.sendmsg([b"bad"], [rights(right.fileno(), right.fileno())])
            with self.assertRaises(ValueError):
                subject._receive(left, b"frame", expected_pid=os.getpid(), want_fd=True)
        finally:
            left.close()
            right.close()
        self.assertEqual(len(os.listdir("/proc/self/fd")), before)

    def test_closure_failure_still_attempts_every_descriptor_and_is_not_success(self):
        with mock.patch.object(subject.os, "close", side_effect=[OSError("close"), None]) as close:
            with self.assertRaises(OSError):
                subject._release(fds=(7, 8))
            self.assertEqual({call.args[0] for call in close.call_args_list}, {7, 8})


class MockLaunchTests(unittest.TestCase):
    def launch_model(self, receives=None, wait_error=None, terminal=None, spawn_error=None):
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        parent, child = mock.Mock(), mock.Mock()
        child.fileno.return_value = 20
        stack.enter_context(mock.patch.object(subject, "_supported", return_value=True))
        stack.enter_context(mock.patch.object(subject.socket, "socketpair", return_value=(parent, child)))
        stack.enter_context(mock.patch.object(subject.fcntl, "fcntl", side_effect=[21, 23]))
        stack.enter_context(mock.patch.object(subject.os, "open", return_value=22))
        stack.enter_context(mock.patch.object(subject, "_send"))
        close = stack.enter_context(mock.patch.object(subject.os, "close"))
        spawn = stack.enter_context(mock.patch.object(
            subject.os, "posix_spawn", return_value=123, side_effect=spawn_error))
        receive = stack.enter_context(mock.patch.object(
            subject, "_receive", side_effect=receives or [(b"", 7), (b"", None), (b"", None)]))
        wait = stack.enter_context(mock.patch.object(subject.os, "waitid", side_effect=wait_error))
        finish = stack.enter_context(mock.patch.object(
            subject, "_terminal", return_value=terminal or subject.BootstrapResult(True, "success")))
        forbidden = [stack.enter_context(mock.patch.object(owner, name)) for owner, name in (
            (subject.os, "pidfd_open"), (subject.os, "waitpid"), (subject.os, "kill"),
            (subject.os, "killpg"), (subject.signal, "pidfd_send_signal"),
        )]
        result = subject.bootstrap_probe()
        for operation in forbidden:
            operation.assert_not_called()
        parent.close.assert_called_once()
        child.close.assert_called_once()
        return result, close, spawn, receive, wait, finish

    def test_ordered_spawn_and_exact_environment(self):
        result, close, spawn, _, wait, _ = self.launch_model()
        self.assertTrue(result.verified)
        self.assertEqual(spawn.call_args.args[2], {})
        self.assertEqual(spawn.call_args.args[1][1:3], ["-I", "-S"])
        self.assertEqual(spawn.call_args.kwargs["file_actions"], [
            (os.POSIX_SPAWN_DUP2, 23, 0), (os.POSIX_SPAWN_DUP2, 23, 1),
            (os.POSIX_SPAWN_DUP2, 23, 2), (os.POSIX_SPAWN_DUP2, 21, 3),
            (os.POSIX_SPAWN_CLOSEFROM, 4),
        ])
        wait.assert_called_once_with(os.P_PIDFD, 7, os.WEXITED | os.WNOHANG | os.WNOWAIT)
        self.assertEqual({call.args[0] for call in close.call_args_list}, {21, 23, 22, 7})
        self.assertEqual(close.call_count, 4)

    def test_invalid_type_missing_status_and_competing_reaper_never_signal(self):
        for error in (OSError(errno.EINVAL, "not pidfd"), OSError(errno.EBADF, "closed"),
                      ChildProcessError(errno.ECHILD, "external reaper/PID reuse")):
            with self.subTest(error=error):
                result, close, _, _, _, finish = self.launch_model(wait_error=error)
                self.assertFalse(result.verified)
                finish.assert_not_called()
                self.assertEqual(close.call_args_list[-1], mock.call(7))

    def test_pretransfer_timeout_interrupt_and_early_exit(self):
        for error in (TimeoutError(), KeyboardInterrupt(), ValueError("EOF before transfer")):
            with self.subTest(error=type(error)):
                result, close, _, _, wait, finish = self.launch_model(receives=[error])
                self.assertFalse(result.verified)
                wait.assert_not_called()
                finish.assert_not_called()
                self.assertEqual({call.args[0] for call in close.call_args_list}, {21, 23, 22})

    def test_posttransfer_duplicate_spoof_or_timeout_never_signals(self):
        for error in (ValueError("extra rights/frame"), TimeoutError(), KeyboardInterrupt()):
            with self.subTest(error=type(error)):
                result, close, _, _, _, finish = self.launch_model(receives=[(b"", 7), error])
                self.assertFalse(result.verified)
                finish.assert_not_called()
                self.assertEqual(close.call_args_list[-1], mock.call(7))

    def test_spawn_error_closes_every_local_descriptor(self):
        result, close, _, receive, _, _ = self.launch_model(spawn_error=OSError("spawn"))
        self.assertFalse(result.verified)
        receive.assert_not_called()
        self.assertEqual({call.args[0] for call in close.call_args_list}, {21, 22, 23})

    def test_unsupported_closefrom_refuses_before_spawn(self):
        with mock.patch.dict(subject.os.__dict__):
            subject.os.__dict__.pop("POSIX_SPAWN_CLOSEFROM", None)
            with mock.patch.object(subject.os, "posix_spawn") as spawn, \
                    mock.patch.object(subject.socket, "socketpair") as pair:
                self.assertFalse(subject.bootstrap_probe().verified)
                spawn.assert_not_called()
                pair.assert_not_called()

    def test_input_refusal_before_spawn(self):
        with mock.patch.object(subject.os, "posix_spawn") as spawn:
            for kwargs in ({"exit_code": -1}, {"exit_code": True}, {"timeout": float("nan")},
                           {"grace": 0}, {"timeout": float("inf")}):
                self.assertFalse(subject.bootstrap_probe(**kwargs).verified)
            spawn.assert_not_called()


class TerminalTests(unittest.TestCase):
    def test_lost_exit_status_and_external_reaper_never_fabricate_zero(self):
        with mock.patch.object(subject.os, "waitid", side_effect=ChildProcessError()), \
                mock.patch.object(subject.signal, "pidfd_send_signal") as send:
            with self.assertRaises(ChildProcessError):
                subject._terminal(7, 10, 1)
            send.assert_not_called()

    def test_timeout_consumes_explicit_status_only_via_fd(self):
        with mock.patch.object(subject.os, "waitid", side_effect=[None, status(9)]) as wait, \
                mock.patch.object(subject.time, "monotonic", return_value=10), \
                mock.patch.object(subject.time, "sleep"), \
                mock.patch.object(subject.signal, "pidfd_send_signal") as send:
            self.assertEqual(subject._terminal(7, 9, 1), subject.BootstrapResult(True, "timeout"))
            send.assert_called_once_with(7, signal.SIGKILL)
            self.assertEqual(wait.call_args_list, [
                mock.call(os.P_PIDFD, 7, os.WEXITED | os.WNOHANG),
                mock.call(os.P_PIDFD, 7, os.WEXITED | os.WNOHANG),
            ])

    def test_no_terminal_status_after_grace_and_unknown_status_refuse(self):
        with mock.patch.object(subject.os, "waitid", return_value=None), \
                mock.patch.object(subject.time, "monotonic", side_effect=[10, 12]), \
                mock.patch.object(subject.time, "sleep"), \
                mock.patch.object(subject.signal, "pidfd_send_signal") as send:
            self.assertFalse(subject._terminal(7, 9, 1).verified)
            send.assert_called_once()
        with mock.patch.object(subject.os, "waitid", return_value=types.SimpleNamespace(si_code=-1)):
            self.assertFalse(subject._terminal(7, 10, 1).verified)


@unittest.skipUnless(subject._supported(), "Linux self-pidfd/CLOSEFROM primitives unavailable")
class RealTransportTests(unittest.TestCase):
    def test_real_success_and_nonzero_self_transfer_no_numeric_operations(self):
        with contextlib.ExitStack() as stack:
            forbidden = [stack.enter_context(mock.patch.object(owner, name, side_effect=AssertionError(name)))
                         for owner, name in ((subject.os, "pidfd_open"), (subject.os, "waitpid"),
                                             (subject.os, "kill"), (subject.os, "killpg"))]
            # The fresh child imports its own os, so parent pidfd_open stays forbidden.
            for code, outcome in ((0, "success"), (7, "nonzero")):
                self.assertEqual(subject.bootstrap_probe(exit_code=code),
                                 subject.BootstrapResult(True, outcome))
            for operation in forbidden:
                operation.assert_not_called()

    def test_real_timeout_selfterminating_child(self):
        self.assertEqual(subject._launch(exit_code=0, delay=.3, early_exit=False,
                                         timeout=.15, grace=1),
                         subject.BootstrapResult(True, "timeout"))

    def test_real_descriptor_lifetimes_and_secret_environment_not_inherited(self):
        before = len(os.listdir("/proc/self/fd"))
        # Known inheritable fd cannot bypass CLOSEFROM; inspect only this trusted
        # interpreter's /proc fd directory in this synthetic test, not identity.
        original = os.open(os.devnull, os.O_RDWR)
        inherited = fcntl.fcntl(original, fcntl.F_DUPFD, 200)
        os.set_inheritable(inherited, True)
        try:
            real_spawn = subject.os.posix_spawn
            def audited_spawn(path, argv, env, **kwargs):
                self.assertEqual(env, {})
                # Trusted synthetic child audits environment/fd before transfer.
                audit = (
                    "import os,fcntl,errno,runpy,sys;"
                    "assert 'BOOTSTRAP_FAKE_SECRET' not in os.environ;"
                    f"fd={inherited};"
                    "\ntry: fcntl.fcntl(fd,fcntl.F_GETFD)\n"
                    "except OSError as e: assert e.errno==errno.EBADF\n"
                    "else: raise SystemExit(90)\n"
                    "sys.argv=" + repr(argv[3:]) + ";runpy.run_path(sys.argv[0],run_name='__main__')"
                )
                return real_spawn(path, [path, "-I", "-S", "-c", audit], env, **kwargs)
            with mock.patch.dict(os.environ, {"BOOTSTRAP_FAKE_SECRET": "fictional-not-a-secret"}), \
                    mock.patch.object(subject.os, "posix_spawn", side_effect=audited_spawn):
                self.assertTrue(subject.bootstrap_probe().verified)
        finally:
            os.close(inherited)
            os.close(original)
        self.assertEqual(len(os.listdir("/proc/self/fd")), before)

    def test_real_exit_before_transfer_is_unverified_no_numeric_recovery(self):
        with mock.patch.object(subject.os, "waitpid", side_effect=AssertionError("numeric wait")), \
                mock.patch.object(subject.signal, "pidfd_send_signal") as send:
            self.assertFalse(subject._launch(exit_code=0, delay=0, early_exit=True,
                                            timeout=1, grace=1).verified)
            send.assert_not_called()
        # This intentionally leaves a dead prebind child unreaped until this test
        # interpreter exits. No survivor, unrelated wait, or unsafe recovery.

    def test_unrelated_owned_sibling_is_not_reaped_or_signaled(self):
        # Cooperative sibling self-opens too; keep its explicit fd and own wait.
        left, right = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        sibling_fd = None
        try:
            left.setsockopt(socket.SOL_SOCKET, socket.SO_PASSCRED, 1)
            source = fcntl.fcntl(right.fileno(), fcntl.F_DUPFD_CLOEXEC, 4)
            try:
                code = (
                    "import os,socket,array,time;"
                    "s=socket.socket(fileno=3);f=os.pidfd_open(os.getpid());"
                    "s.sendmsg([b'sibling'],[(socket.SOL_SOCKET,socket.SCM_RIGHTS,array.array('i',[f]))]);"
                    "os.close(f);s.close();time.sleep(.2)"
                )
                sibling_pid = os.posix_spawn(sys.executable, [sys.executable, "-I", "-S", "-c", code], {},
                                            file_actions=[(os.POSIX_SPAWN_DUP2, source, 3),
                                                          (os.POSIX_SPAWN_CLOSEFROM, 4)])
            finally:
                os.close(source)
            right.close()
            left.settimeout(1)
            _, sibling_fd = subject._receive(left, b"sibling", expected_pid=sibling_pid, want_fd=True)
            self.assertTrue(subject.bootstrap_probe().verified)
            # Wait only our separate explicitly transferred sibling fd.
            info = os.waitid(os.P_PIDFD, sibling_fd, os.WEXITED)
            self.assertEqual((info.si_code, info.si_status), (os.CLD_EXITED, 0))
        finally:
            left.close()
            right.close()
            if sibling_fd is not None:
                os.close(sibling_fd)

    def test_public_supervise_still_disabled(self):
        with mock.patch.object(subject, "bootstrap_probe") as launch:
            self.assertEqual(owned_process.supervise([sys.executable, "-c", "pass"]),
                             owned_process.Result(False, "unverified"))
            launch.assert_not_called()


if __name__ == "__main__":
    unittest.main()

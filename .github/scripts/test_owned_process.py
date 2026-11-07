import contextlib
import io
import json
import os
import selectors
import signal
import subprocess
import sys
import time
import unittest
from unittest import mock

import owned_process as subject


def command(code):
    return [sys.executable, "-c", code]


class OwnedProcessTests(unittest.TestCase):
    def assert_refused(self, argv=None, **kwargs):
        """Even a plausible reused-PID handle or zero status must be unreachable."""
        proc = mock.Mock(pid=123, returncode=0)
        proc.wait.return_value = 0
        with contextlib.ExitStack() as stack:
            forbidden = [
                stack.enter_context(mock.patch.object(owner, name, create=True))
                for owner, name in (
                    (subject.subprocess, "Popen"),
                    (subject.os, "pidfd_open"),
                    (subject.signal, "pidfd_send_signal"),
                    (subject.os, "kill"),
                    (subject.os, "killpg"),
                    (subject.os, "waitid"),
                    (subject.os, "waitpid"),
                    (subject, "_experimental_supervisor"),
                    (subject, "_main"),
                    (subject.json, "dumps"),
                    (subject.selectors, "DefaultSelector"),
                )
            ]
            forbidden[0].return_value = proc
            forbidden[1].return_value = 7
            self.assertEqual(
                subject.supervise(command("pass") if argv is None else argv, **kwargs),
                subject.Result(False, "unverified"),
            )
            for operation in forbidden:
                operation.assert_not_called()
        proc.wait.assert_not_called()
        proc.kill.assert_not_called()
        proc.terminate.assert_not_called()
        proc.stdin.write.assert_not_called()

    def test_valid_workers_refused_before_any_launch_binding_signal_or_proof(self):
        for code in (
            "pass",
            "raise SystemExit(7)",
            "import time;time.sleep(.2)",
            "print('{\"verified\":true,\"outcome\":\"success\"}')",
        ):
            with self.subTest(code=code):
                self.assert_refused(command(code))

    def test_invalid_inputs_and_limits_are_also_side_effect_free(self):
        for argv in ([], ["relative"], ["/bin/echo", "\x00"], object(),
                     [sys.executable] * 129, [sys.executable, "x" * 4097]):
            with self.subTest(argv_type=type(argv)):
                self.assert_refused(argv)
        for kwargs in ({"timeout": 0}, {"timeout": float("nan")}, {"grace": 0},
                       {"output_limit": -1}, {"timeout": .001, "grace": .001}):
            self.assert_refused(**kwargs)

    def test_auto_reaping_and_external_waiter_conditions_do_not_enable_launch(self):
        for disposition in (signal.SIG_DFL, signal.SIG_IGN, mock.Mock()):
            with mock.patch.object(subject.signal, "getsignal", return_value=disposition):
                self.assert_refused()
        with mock.patch.object(subject.sys, "platform", "unsupported"):
            self.assert_refused()

    def test_historical_postspawn_binding_can_signal_reused_pid_on_interrupt(self):
        # A model of the removed caller, with no real process or kernel operation.
        events = []
        proc = mock.Mock(pid=123)
        spawn = mock.Mock(return_value=proc)
        bind = mock.Mock(side_effect=lambda pid, flags: events.append(
            ("bind-reused-unrelated", pid, flags)) or 7)
        send = mock.Mock(side_effect=lambda fd, sig: events.append(("wrong-signal", fd, sig)))
        reaper = mock.Mock(side_effect=lambda: events.append(("reap-original", proc.pid)))
        launched = spawn()
        reaper()  # The original child is gone; the numeric PID is now reused.
        fd = bind(launched.pid, 0)
        with self.assertRaises(KeyboardInterrupt):
            try:
                raise KeyboardInterrupt()
            finally:
                send(fd, signal.SIGKILL)
        self.assertEqual(events, [("reap-original", 123), ("bind-reused-unrelated", 123, 0),
                                  ("wrong-signal", 7, signal.SIGKILL)])
        self.assert_refused()

    def test_cpython_echild_zero_can_accept_exact_frame_after_abnormal_exit(self):
        # No child is launched: exercise CPython 3.14's actual POSIX _try_wait.
        proc = object.__new__(subprocess.Popen)
        proc.pid = 123
        proc.returncode = None
        proc._child_created = False
        external_reaper = mock.Mock(return_value=(123, 7 << 8))
        self.assertEqual(os.waitstatus_to_exitcode(external_reaper()[1]), 7)
        with mock.patch.object(os, "waitpid", side_effect=ChildProcessError) as reap:
            pid, status = proc._try_wait(0)
        reap.assert_called_once_with(123, 0)
        self.assertEqual((pid, status), (123, 0))
        frame = b'{"verified":true,"outcome":"success"}\n'
        # Historical exact-frame + Python-zero acceptance lost the real exit 7.
        self.assertTrue(frame == b'{"verified":true,"outcome":"success"}\n' and status == 0)
        self.assert_refused()

    def test_timeout_interrupt_missing_status_and_external_waitid_are_unreachable(self):
        for failure in (KeyboardInterrupt(), subprocess.TimeoutExpired("fictional", .1),
                        ChildProcessError(), PermissionError()):
            with (
                mock.patch.object(subject.os, "waitid", side_effect=failure),
                mock.patch.object(subject.signal, "pidfd_send_signal", side_effect=failure),
            ):
                self.assert_refused(timeout=.01, grace=.01)


class ExperimentalInterpreterTests(unittest.TestCase):
    def invoke(self, code, *, timeout=1, grace=2, output_limit=65536):
        """Test-only launch, no outer signals/binding or Popen status-as-proof.

        All real workers below are fictional and self-terminating. This fresh
        test interpreter has default SIGCHLD and no installed/external waiters.
        It does not establish a safe subprocess primitive for arbitrary callers.
        """
        request = {"argv": command(code), "timeout": timeout,
                   "grace": grace, "output_limit": output_limit}
        proc = subprocess.Popen(
            [sys.executable, "-I", os.path.abspath(subject.__file__), "--experimental-supervise"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            close_fds=True,
        )
        data = bytearray()
        info = None
        deadline = time.monotonic() + 5
        try:
            proc.stdin.write((json.dumps(request) + "\n").encode())
            proc.stdin.close()
            os.set_blocking(proc.stdout.fileno(), False)
            eof = False
            with selectors.DefaultSelector() as selector:
                selector.register(proc.stdout, selectors.EVENT_READ)
                while time.monotonic() < deadline and (not eof or info is None):
                    if info is None:
                        # ECHILD propagates as a failing test, not a success status.
                        info = os.waitid(os.P_PID, proc.pid, os.WEXITED | os.WNOHANG)
                        if info is not None:
                            self.assertIn(info.si_code, (os.CLD_EXITED, os.CLD_KILLED, os.CLD_DUMPED))
                            proc.returncode = (
                                info.si_status if info.si_code == os.CLD_EXITED else -info.si_status
                            )
                    for key, _ in selector.select(.01):
                        chunk = os.read(key.fd, 257)
                        if not chunk:
                            selector.unregister(key.fileobj)
                            eof = True
                        else:
                            data.extend(chunk)
                            self.assertLessEqual(len(data), 256)
                self.assertTrue(eof, "experimental protocol did not close within test bound")
                self.assertIsNotNone(info, "explicit terminal status was not obtained")
            if info.si_code != os.CLD_EXITED or info.si_status != 0:
                self.assertEqual(data, b"")
                return None
            for outcome in subject._OUTCOMES:
                if data == ('{"verified":true,"outcome":"' + outcome + '"}\n').encode():
                    return outcome
            self.fail("experimental interpreter returned an invalid terminal frame")
        finally:
            proc.stdin.close()
            proc.stdout.close()

    def test_ordinary_leader_status_and_rapid_exit(self):
        self.assertEqual(self.invoke("pass"), "success")
        self.assertEqual(self.invoke("raise SystemExit(7)"), "nonzero")
        for _ in range(10):
            self.assertEqual(self.invoke("pass"), "success")

    def test_worker_frame_is_not_supervisor_status(self):
        code = "print('{\"verified\":true,\"outcome\":\"success\"}',flush=True);raise SystemExit(7)"
        self.assertEqual(self.invoke(code), "nonzero")

    def test_aggregate_output_exact_limit_and_timeout(self):
        code = "import os;os.write(1,b'abc');os.write(2,b'def')"
        self.assertEqual(self.invoke(code, output_limit=6), "success")
        self.assertEqual(self.invoke(code, output_limit=5), "output_limit")
        self.assertEqual(self.invoke("import os;os.write(1,b'x'*100000)", output_limit=64),
                         "output_limit")
        self.assertEqual(self.invoke("import time;time.sleep(.8)", timeout=.15, grace=1),
                         "timeout")

    def test_ordinary_and_escaped_adopted_children(self):
        for escape in ("pass", "os.setsid()", "os.setpgid(0,0)"):
            child = (f"import os,time;{escape};print('ready',flush=True);"
                     "os.close(1);os.close(2);time.sleep(.5)")
            parent = ("import subprocess,sys;"
                      f"p=subprocess.Popen([sys.executable,'-c',{child!r}],stdout=subprocess.PIPE);"
                      "p.stdout.readline()")
            with self.subTest(escape=escape):
                start = time.monotonic()
                self.assertEqual(self.invoke(parent), "success")
                if escape != "pass":
                    self.assertGreaterEqual(time.monotonic() - start, .4)

    def test_escape_past_grace_does_not_certify(self):
        child = ("import os,time;os.setsid();print('ready',flush=True);"
                 "os.close(1);os.close(2);time.sleep(.9)")
        parent = ("import subprocess,sys;"
                  f"p=subprocess.Popen([sys.executable,'-c',{child!r}],stdout=subprocess.PIPE);"
                  "p.stdout.readline()")
        try:
            self.assertIsNone(self.invoke(parent, timeout=.2, grace=.2))
        finally:
            time.sleep(1)  # Bounded escaped fictional child terminates on its own.

    def test_test_harness_fails_echild_instead_of_using_popen_wait(self):
        proc = mock.Mock(pid=123, stdin=io.BytesIO())
        proc.stdout.fileno.return_value = 9
        selector = mock.MagicMock()
        selector.__enter__.return_value = selector
        with (
            mock.patch.object(subprocess, "Popen", return_value=proc),
            mock.patch.object(os, "set_blocking"),
            mock.patch.object(os, "waitid", side_effect=ChildProcessError),
            mock.patch.object(selectors, "DefaultSelector", return_value=selector),
        ):
            with self.assertRaises(ChildProcessError):
                self.invoke("pass")
        proc.wait.assert_not_called()
        proc.kill.assert_not_called()
        proc.terminate.assert_not_called()


class OwnershipFailureTests(unittest.TestCase):
    def request(self, **kwargs):
        return {"argv": command("pass"), "timeout": 1, "grace": 1,
                "output_limit": 0, **kwargs}

    def flow(self, *, fail=None, chunks=(), limit=0, abnormal=False):
        """Only mocked ownership/signals: no real unrelated process control."""
        events = []
        stdout = mock.Mock()
        stdout.fileno.return_value = 9
        stderr = mock.Mock()
        stderr.fileno.return_value = 10
        proc = mock.Mock(pid=123, stdout=stdout, stderr=stderr)
        selector = mock.MagicMock()
        selector.__enter__.return_value = selector
        queued = list(chunks)

        def select(_timeout):
            return [(mock.Mock(fd=9), 1)] if queued else []

        def observe(_kind, _fd, flags):
            consuming = not flags & subject.os.WNOWAIT
            events.append("consume" if consuming else "observe")
            if (fail == "waitid" or
                    fail == "external_waitid_race" and events.count("observe") == 2 or
                    fail == "lost_terminal_status" and consuming):
                raise ChildProcessError()
            if fail == "no_terminal_status" and consuming:
                return None
            return mock.Mock(si_code=subject.os.CLD_EXITED, si_status=7 if abnormal else 0)

        def group(_pid, _signal):
            events.append("signal")
            if fail == "signal":
                raise PermissionError()

        def reap(*_args):
            events.append("reap")
            if fail == "reap":
                raise PermissionError()
            raise ChildProcessError()

        selector.select.side_effect = select
        selector.get_map.side_effect = lambda: bool(queued)
        with (
            mock.patch.object(subject, "_set_subreaper"),
            mock.patch.object(subject, "_has_no_children", return_value=True),
            mock.patch.object(subject.time, "monotonic", side_effect=iter(
                (0, 0, 3) if fail == "no_terminal_status" else [0] * 100)),
            mock.patch.object(subject.time, "sleep"),
            mock.patch.object(subject.subprocess, "Popen", return_value=proc),
            mock.patch.object(subject.os, "pidfd_open", return_value=7),
            mock.patch.object(subject.os, "close"),
            mock.patch.object(subject.os, "set_blocking"),
            mock.patch.object(subject.os, "getpgrp", return_value=456),
            mock.patch.object(subject.os, "getpgid", return_value=456 if fail == "pgid" else 123),
            mock.patch.object(subject.os, "getsid", return_value=456 if fail == "sid" else 123),
            mock.patch.object(subject.os, "waitid", side_effect=observe),
            mock.patch.object(subject.os, "waitpid", side_effect=reap),
            mock.patch.object(subject.os, "killpg", side_effect=group),
            mock.patch.object(subject.os, "kill") as numeric_signal,
            mock.patch.object(subject.signal, "pidfd_send_signal") as signal_fd,
            mock.patch.object(subject.os, "read", side_effect=lambda _fd, _size: queued.pop(0)),
            mock.patch.object(subject.selectors, "DefaultSelector", return_value=selector),
        ):
            if fail in ("waitid", "external_waitid_race", "lost_terminal_status", "signal", "reap"):
                with self.assertRaises(OSError):
                    subject._experimental_supervisor(self.request(output_limit=limit))
                result = None
            else:
                result = subject._experimental_supervisor(self.request(output_limit=limit))
            numeric_signal.assert_not_called()
            signal_fd.assert_not_called()
            proc.wait.assert_not_called()
        return result, events

    def test_retained_leader_signal_then_explicit_status_then_echild(self):
        result, events = self.flow()
        self.assertEqual(result, "success")
        self.assertEqual(events, ["observe", "observe", "signal", "consume", "reap"])
        self.assertEqual(self.flow(abnormal=True)[0], "nonzero")

    def test_ownership_signal_reap_and_external_waitid_errors_never_certify(self):
        for failure in ("waitid", "pgid", "sid", "signal", "reap",
                        "external_waitid_race", "lost_terminal_status"):
            with self.subTest(failure=failure):
                result, events = self.flow(fail=failure)
                self.assertIsNone(result)
                if failure in ("waitid", "pgid", "sid", "external_waitid_race"):
                    self.assertNotIn("signal", events)
                    self.assertNotIn("reap", events)
                if failure == "lost_terminal_status":
                    self.assertNotIn("reap", events)

    def test_no_terminal_waitid_status_cannot_certify_before_deadline(self):
        result, events = self.flow(fail="no_terminal_status")
        self.assertIsNone(result)
        self.assertEqual(events, ["observe", "observe", "signal", "consume"])

    def test_queued_output_exact_boundary_and_aggregate(self):
        for chunks, limit, expected in (([b"abc", b"def", b""], 6, "success"),
                                        ([b"abc", b"def", b""], 5, "output_limit")):
            self.assertEqual(self.flow(chunks=chunks, limit=limit)[0], expected)

    def test_preexisting_children_are_observed_not_reaped(self):
        for observed in (None, mock.Mock(si_pid=99)):
            with (
                mock.patch.object(subject.os, "waitid", return_value=observed),
                mock.patch.object(subject.os, "waitpid") as reap,
            ):
                self.assertFalse(subject._has_no_children())
                reap.assert_not_called()
        with mock.patch.object(subject.os, "waitid", side_effect=ChildProcessError):
            self.assertTrue(subject._has_no_children())
        with (
            mock.patch.object(subject, "_set_subreaper"),
            mock.patch.object(subject, "_has_no_children", return_value=False),
            mock.patch.object(subject.subprocess, "Popen") as spawn,
        ):
            self.assertIsNone(subject._experimental_supervisor(self.request()))
            spawn.assert_not_called()

    def test_support_binding_and_sigchld_failures(self):
        with mock.patch.object(subject.signal, "getsignal", return_value=signal.SIG_IGN):
            self.assertIsNone(subject._experimental_supervisor(self.request()))
        with mock.patch.object(subject, "_set_subreaper", side_effect=OSError):
            with self.assertRaises(OSError):
                subject._experimental_supervisor(self.request())
        proc = mock.Mock(pid=123, stdout=io.BytesIO(), stderr=io.BytesIO())
        with (
            mock.patch.object(subject, "_set_subreaper"),
            mock.patch.object(subject, "_has_no_children", return_value=True),
            mock.patch.object(subject.subprocess, "Popen", return_value=proc),
            mock.patch.object(subject.os, "pidfd_open", side_effect=OSError),
            mock.patch.object(subject.os, "killpg") as group,
        ):
            with self.assertRaises(OSError):
                subject._experimental_supervisor(self.request())
        group.assert_not_called()
        self.assertTrue(proc.stdout.closed)
        self.assertTrue(proc.stderr.closed)

    def test_experimental_main_emits_nothing_on_failure_or_interrupt(self):
        for failure in (OSError(), ChildProcessError(), KeyboardInterrupt()):
            raw = io.BytesIO((json.dumps(self.request()) + "\n").encode())
            output = io.StringIO()
            with (
                mock.patch.object(subject.sys, "stdin", io.TextIOWrapper(raw)),
                mock.patch.object(subject.sys, "stdout", output),
                mock.patch.object(subject, "_experimental_supervisor", side_effect=failure),
            ):
                if isinstance(failure, KeyboardInterrupt):
                    with self.assertRaises(KeyboardInterrupt):
                        subject._main()
                else:
                    self.assertEqual(subject._main(), 1)
                self.assertEqual(output.getvalue(), "")


if __name__ == "__main__":
    unittest.main()

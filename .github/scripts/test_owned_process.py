import io
import json
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
    def invoke(self, code, **kwargs):
        return subject.supervise(command(code), timeout=1, grace=2, **kwargs)

    def test_success_and_nonzero(self):
        self.assertEqual(self.invoke("pass"), subject.Result(True, "success"))
        self.assertEqual(self.invoke("raise SystemExit(7)"), subject.Result(True, "nonzero"))
        start = time.monotonic()
        self.assertEqual(self.invoke("import time;time.sleep(.2)"), subject.Result(True, "success"))
        self.assertGreaterEqual(time.monotonic() - start, .18)

    def test_rapid_exit_race(self):
        for _ in range(20):
            self.assertEqual(self.invoke("pass"), subject.Result(True, "success"))

    def test_closed_pipe_adopted_grandchild_is_not_left_running(self):
        child = "import os,time;print('ready',flush=True);os.close(1);os.close(2);time.sleep(.7)"
        parent = (
            "import subprocess,sys;"
            f"p=subprocess.Popen([sys.executable,'-c',{child!r}],stdout=subprocess.PIPE);"
            "p.stdout.readline()"
        )
        self.assertEqual(self.invoke(parent), subject.Result(True, "success"))

    def test_escaped_adopted_child_is_waited_for_without_numeric_signal(self):
        for escape in ("os.setsid()", "os.setpgid(0,0)"):
            child = (
                f"import os,time;{escape};print('ready',flush=True);"
                "os.close(1);os.close(2);time.sleep(.5)"
            )
            parent = (
                "import subprocess,sys;"
                f"p=subprocess.Popen([sys.executable,'-c',{child!r}],stdout=subprocess.PIPE);"
                "p.stdout.readline()"
            )
            with self.subTest(escape=escape):
                start = time.monotonic()
                self.assertEqual(self.invoke(parent), subject.Result(True, "success"))
                self.assertGreaterEqual(time.monotonic() - start, .4)

    def test_output_budget_and_timeout(self):
        self.assertEqual(self.invoke("import os;os.write(1,b'x'*100000)", output_limit=64),
                         subject.Result(True, "output_limit"))
        result = subject.supervise(command("import time;time.sleep(.8)"), timeout=.15, grace=1)
        self.assertEqual(result, subject.Result(True, "timeout"))

    def test_unrelated_owned_sibling_untouched(self):
        sibling = subprocess.Popen(command("import time;time.sleep(.8)"))  # noqa: S603
        try:
            self.assertEqual(self.invoke("pass"), subject.Result(True, "success"))
            self.assertIsNone(sibling.poll())
        finally:
            sibling.wait(timeout=2)

    def test_escaped_child_longer_than_grace_is_unverified(self):
        child = (
            "import os,time;os.setsid();print('ready',flush=True);"
            "os.close(1);os.close(2);time.sleep(.9)"
        )
        parent = (
            "import subprocess,sys;"
            f"p=subprocess.Popen([sys.executable,'-c',{child!r}],stdout=subprocess.PIPE);"
            "p.stdout.readline()"
        )
        self.assertEqual(subject.supervise(command(parent), timeout=.2, grace=.2),
                         subject.Result(False, "unverified"))
        time.sleep(1)

    def fake_supervisor(self, code, timeout=.2, worker="pass"):
        real = subprocess.Popen

        def fake(_argv, **kwargs):
            return real(command(code), **kwargs)

        with mock.patch.object(subject.subprocess, "Popen", side_effect=fake):
            return subject.supervise(command(worker), timeout=timeout, grace=.2)

    def test_crash_before_and_after_spawn(self):
        self.assertEqual(self.fake_supervisor("raise SystemExit(3)"), subject.Result(False, "unverified"))
        code = (
            "import subprocess,sys;"
            "subprocess.Popen([sys.executable,'-c','import time;time.sleep(.4)'],"
            "stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,"
            "start_new_session=True);raise SystemExit(3)"
        )
        self.assertEqual(self.fake_supervisor(code), subject.Result(False, "unverified"))
        time.sleep(.5)

    def test_real_supervisor_crash_after_worker_spawn(self):
        code = (
            "import os,owned_process;"
            "owned_process.os.pidfd_open=lambda *args:os._exit(7);"
            "raise SystemExit(owned_process._main())"
        )
        self.assertEqual(self.fake_supervisor(code, worker="import time;time.sleep(.5)"),
                         subject.Result(False, "unverified"))
        time.sleep(.7)

    def test_actual_supervisor_support_failures(self):
        for injection in (
            "del owned_process.os.pidfd_open",
            "owned_process._set_subreaper=lambda:(_ for _ in ()).throw(OSError())",
            "signal.signal(signal.SIGCHLD,signal.SIG_IGN)",
            "owned_process.os.pidfd_open=lambda *args:(_ for _ in ()).throw(OSError())",
        ):
            code = (
                "import os,signal,owned_process;"
                f"{injection};"
                "raise SystemExit(owned_process._main())"
            )
            with self.subTest(injection=injection):
                self.assertEqual(self.fake_supervisor(code, worker="import time;time.sleep(.3)"),
                                 subject.Result(False, "unverified"))
        time.sleep(.5)

    def test_terminal_frame_without_exit_cannot_certify(self):
        code = "import time;print('{\"verified\":true,\"outcome\":\"success\"}',flush=True);time.sleep(4)"
        start = time.monotonic()
        self.assertEqual(self.fake_supervisor(code), subject.Result(False, "unverified"))
        self.assertLess(time.monotonic() - start, 3.5)

    def test_protocol_rejects_malformed_duplicate_truncated_and_nonzero(self):
        frame = '{"verified":true,"outcome":"success"}\\n'
        for code in (
            "print('junk')",
            f"print({frame!r},end='')",
            "print('{\"verified\":true',end='')",
            "print('{\"verified\":true,\"outcome\":\"success\"}') ; raise SystemExit(1)",
            "print('{\"verified\":true,\"outcome\":\"success\"}');print('extra')",
            "print('x'*300)",
        ):
            with self.subTest(code=code):
                self.assertEqual(self.fake_supervisor(code), subject.Result(False, "unverified"))

    def test_missing_support_and_abnormal_sigchld_fail_closed(self):
        request = {"argv": command("pass"), "timeout": 1, "grace": 1, "output_limit": 0}
        with mock.patch.object(subject.os, "pidfd_open", None):
            with mock.patch.object(subject, "_set_subreaper"):
                with mock.patch.object(subject, "_has_no_children", return_value=True):
                    with mock.patch.object(subject.subprocess, "Popen", side_effect=OSError):
                        with self.assertRaises(OSError):
                            subject._supervisor(request)
        with mock.patch.object(subject.signal, "getsignal", return_value=signal.SIG_IGN):
            self.assertIsNone(subject._supervisor(request))
        with mock.patch.object(subject, "_set_subreaper", side_effect=OSError):
            with self.assertRaises(OSError):
                subject._supervisor(request)
        with mock.patch.object(subject, "_has_no_children", return_value=False):
            with mock.patch.object(subject, "_set_subreaper"):
                self.assertIsNone(subject._supervisor(request))
        raw = io.BytesIO((json.dumps(request) + "\n").encode())
        with mock.patch.object(subject.sys, "stdin", io.TextIOWrapper(raw)):
            with mock.patch.object(subject, "_supervisor", side_effect=OSError):
                self.assertEqual(subject._main(), 1)

    def test_partial_spawn_failure_is_not_certified(self):
        request = {"argv": command("pass"), "timeout": 1, "grace": 1, "output_limit": 0}
        proc = mock.Mock(pid=123, stdout=io.BytesIO(), stderr=io.BytesIO())
        with mock.patch.object(subject, "_set_subreaper"):
            with mock.patch.object(subject, "_has_no_children", return_value=True):
                with mock.patch.object(subject.subprocess, "Popen", return_value=proc):
                    with mock.patch.object(subject.os, "pidfd_open", side_effect=OSError):
                        with self.assertRaises(OSError):
                            subject._supervisor(request)
        self.assertTrue(proc.stdout.closed)

    def test_invalid_inputs_fail_closed(self):
        for argv in ([], ["relative"], ["/bin/echo", "\x00"]):
            self.assertEqual(subject.supervise(argv), subject.Result(False, "unverified"))
        self.assertEqual(subject.supervise(command("pass"), timeout=0), subject.Result(False, "unverified"))



class OwnershipFailureTests(unittest.TestCase):
    def request(self, **kwargs):
        return {"argv": command("pass"), "timeout": 1, "grace": 1,
                "output_limit": 0, **kwargs}

    def flow(self, *, fail=None, chunks=(), limit=0):
        """Mock only OS ownership operations; execute the real supervision loop."""
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
            if not queued:
                return []
            key = mock.Mock(fd=9)
            return [(key, 1)]

        def read(_fd, _size):
            return queued.pop(0)

        def observe(*_args):
            events.append("observe")
            if fail == "waitid":
                raise ChildProcessError()
            return mock.Mock(si_code=subject.os.CLD_EXITED, si_status=0)

        def group(_pid, _signal):
            events.append("signal")
            if fail == "signal":
                raise PermissionError()

        def reap(*_args):
            events.append("reap")
            if fail == "reap":
                raise PermissionError()
            if events.count("reap") == 1:
                return 123, 0
            raise ChildProcessError()

        selector.select.side_effect = select
        selector.get_map.side_effect = lambda: bool(queued)
        with (
            mock.patch.object(subject, "_set_subreaper"),
            mock.patch.object(subject, "_has_no_children", return_value=True),
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
            mock.patch.object(subject.os, "read", side_effect=read),
            mock.patch.object(subject.selectors, "DefaultSelector", return_value=selector),
        ):
            if fail in ("waitid", "signal", "reap"):
                with self.assertRaises(OSError):
                    subject._supervisor(self.request(output_limit=limit))
                result = None
            else:
                result = subject._supervisor(self.request(output_limit=limit))
        return result, events

    def test_signal_precedes_every_reap_and_echild_is_required(self):
        result, events = self.flow()
        self.assertEqual(result, "success")
        self.assertEqual(events, ["observe", "observe", "signal", "reap", "reap"])

    def test_ownership_and_signal_reap_errors_never_certify(self):
        for failure in ("waitid", "pgid", "sid", "signal", "reap"):
            with self.subTest(failure=failure):
                result, events = self.flow(fail=failure)
                self.assertIsNone(result)
                if failure in ("waitid", "pgid", "sid"):
                    self.assertNotIn("signal", events)
                    self.assertNotIn("reap", events)
                elif failure == "signal":
                    self.assertNotIn("reap", events)
                else:
                    self.assertLess(events.index("signal"), events.index("reap"))
                    self.assertEqual(events.count("signal"), 1)

    def test_queued_output_exact_boundary_and_aggregate(self):
        for chunks, limit, expected in (
            ([b"abc", b"def", b""], 6, "success"),
            ([b"abc", b"def", b""], 5, "output_limit"),
        ):
            with self.subTest(limit=limit):
                result, _ = self.flow(chunks=chunks, limit=limit)
                self.assertEqual(result, expected)

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
            self.assertIsNone(subject._supervisor(self.request()))
            spawn.assert_not_called()

    def test_outer_interrupt_uses_bound_pidfd_not_numeric_signal(self):
        stdout = mock.Mock()
        stdout.fileno.return_value = 9
        proc = mock.Mock(stdin=io.BytesIO(), stdout=stdout)
        selector = mock.MagicMock()
        selector.__enter__.return_value = selector
        selector.select.side_effect = KeyboardInterrupt()
        with (
            mock.patch.object(subject.subprocess, "Popen", return_value=proc),
            mock.patch.object(subject.os, "pidfd_open", return_value=7),
            mock.patch.object(subject.os, "set_blocking"),
            mock.patch.object(subject.os, "close") as close,
            mock.patch.object(subject.signal, "pidfd_send_signal") as signal_fd,
            mock.patch.object(subject.selectors, "DefaultSelector", return_value=selector),
        ):
            self.assertEqual(subject.supervise(command("pass")), subject.Result(False, "unverified"))
        signal_fd.assert_called_once_with(7, signal.SIGKILL)
        close.assert_called_once_with(7)
        proc.kill.assert_not_called()
        proc.wait.assert_called_once_with(timeout=.2)

    def test_outer_missing_binding_does_not_signal(self):
        proc = mock.Mock(stdin=io.BytesIO(), stdout=io.BytesIO())
        with (
            mock.patch.object(subject.subprocess, "Popen", return_value=proc),
            mock.patch.object(subject.os, "pidfd_open", side_effect=OSError),
            mock.patch.object(subject.signal, "pidfd_send_signal") as signal_fd,
        ):
            self.assertEqual(subject.supervise(command("pass")), subject.Result(False, "unverified"))
        signal_fd.assert_not_called()
        proc.kill.assert_not_called()
        proc.wait.assert_not_called()
        self.assertTrue(proc.stdin.closed)

    def test_input_allocation_bound_before_serialization(self):
        with mock.patch.object(subject.json, "dumps") as serialize:
            for argv in ([sys.executable] * 129, [sys.executable, "x" * 4097]):
                self.assertEqual(subject.supervise(argv), subject.Result(False, "unverified"))
            serialize.assert_not_called()

if __name__ == "__main__":
    unittest.main()

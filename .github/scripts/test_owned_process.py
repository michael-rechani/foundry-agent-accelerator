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
        child = (
            "import os,time;os.setsid();print('ready',flush=True);"
            "os.close(1);os.close(2);time.sleep(.5)"
        )
        parent = (
            "import subprocess,sys;"
            f"p=subprocess.Popen([sys.executable,'-c',{child!r}],stdout=subprocess.PIPE);"
            "p.stdout.readline()"
        )
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

    def fake_supervisor(self, code, timeout=.2):
        real = subprocess.Popen

        def fake(_argv, **kwargs):
            return real(command(code), **kwargs)

        with mock.patch.object(subject.subprocess, "Popen", side_effect=fake):
            return subject.supervise(command("pass"), timeout=timeout, grace=.2)

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


if __name__ == "__main__":
    unittest.main()

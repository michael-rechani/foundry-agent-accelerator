import io
import logging
import unittest
from contextlib import redirect_stderr

from log_capture import LAB_LOGGER_NAME, CapturedLabLogs

LOGGER = logging.getLogger(LAB_LOGGER_NAME)
EVENT = '{"event": "workbench_request", "status": 504, "outcome": "timeout"}'


def run_case(body, mixins=(CapturedLabLogs,)):
    """Run `body(test)` as a one-test case, returning its result and what it wrote to stderr."""

    class Inner(*mixins, unittest.TestCase):
        def runTest(self):
            body(self)

    result, stderr = unittest.TestResult(), io.StringIO()
    with redirect_stderr(stderr):
        Inner().run(result)
    return result, stderr.getvalue()


class CapturedLabLogsTests(unittest.TestCase):
    def skip_if_root_handler(self):
        if logging.getLogger().handlers:
            self.skipTest("a root handler is installed, so the last-resort stderr handler stays silent")

    def test_clean_run_prints_nothing(self):
        result, stderr = run_case(lambda test: (LOGGER.warning(EVENT), LOGGER.error(EVENT)))
        self.assertTrue(result.wasSuccessful())
        self.assertEqual(stderr, "")

    def test_the_same_log_is_noisy_without_the_helper(self):
        self.skip_if_root_handler()
        _, stderr = run_case(lambda test: LOGGER.warning(EVENT), mixins=())
        self.assertIn(EVENT, stderr)

    def test_slow_callback_warnings_are_dropped_but_other_asyncio_warnings_print(self):
        self.skip_if_root_handler()
        asyncio_logger = logging.getLogger("asyncio")

        def body(test):
            asyncio_logger.warning("Executing %s took %.3f seconds", "<Task>", 0.2)
            asyncio_logger.warning("Task was destroyed but it is pending!")

        result, stderr = run_case(body)
        self.assertTrue(result.wasSuccessful())
        self.assertNotIn("took", stderr)
        self.assertIn("Task was destroyed but it is pending!", stderr)

    def test_failing_test_reports_the_captured_log(self):
        def body(test):
            LOGGER.info('{"event": "started"}')
            LOGGER.warning(EVENT)
            test.fail("boom")

        result, stderr = run_case(body)
        self.assertEqual(stderr, "")
        self.assertEqual(len(result.failures), 1)
        report = result.failures[0][1]
        self.assertIn("boom", report)
        self.assertIn("Captured Lab log:", report)
        self.assertIn('INFO {"event": "started"}', report)
        self.assertIn(f"WARNING {EVENT}", report)

    def test_erroring_test_reports_the_captured_log(self):
        def body(test):
            LOGGER.error(EVENT)
            raise RuntimeError("broken")

        result, _ = run_case(body)
        self.assertEqual(len(result.errors), 1)
        self.assertIn(f"ERROR {EVENT}", result.errors[0][1])

    def test_passing_test_keeps_its_log_out_of_the_result(self):
        result, _ = run_case(lambda test: LOGGER.warning(EVENT))
        self.assertEqual((result.failures, result.errors), ([], []))

    def test_only_the_failing_tests_log_is_attached(self):
        result = unittest.TestResult()

        class Inner(CapturedLabLogs, unittest.TestCase):
            def test_a_noisy_pass(self):
                LOGGER.warning('{"event": "from_the_passing_test"}')

            def test_b_failing(self):
                LOGGER.warning('{"event": "from_the_failing_test"}')
                self.fail("boom")

        with redirect_stderr(io.StringIO()):
            unittest.defaultTestLoader.loadTestsFromTestCase(Inner).run(result)
        report = result.failures[0][1]
        self.assertIn("from_the_failing_test", report)
        self.assertNotIn("from_the_passing_test", report)

    def test_assert_logs_still_sees_the_log_line(self):
        def body(test):
            with test.assertLogs(LAB_LOGGER_NAME, level="WARNING") as logs:
                LOGGER.warning(EVENT)
            test.assertEqual(logs.output, [f"WARNING:{LAB_LOGGER_NAME}:{EVENT}"])

        result, stderr = run_case(body)
        self.assertTrue(result.wasSuccessful(), result.failures + result.errors)
        self.assertEqual(stderr, "")

    def test_logger_is_restored_after_the_run(self):
        handlers, level = list(LOGGER.handlers), LOGGER.level
        run_case(lambda test: LOGGER.warning(EVENT))
        self.assertEqual((LOGGER.handlers, LOGGER.level), (handlers, level))


if __name__ == "__main__":
    unittest.main()

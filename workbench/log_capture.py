"""Test support: keep log noise out of the test run output.

The Lab logs every request outcome as one JSON line on the ``uvicorn.error`` logger.
With no handler attached, Python's last-resort handler prints each warning to
stderr, which buries the test summary. ``CapturedLabLogs`` collects those lines
instead and appends them to the report of a test that fails or errors.

It also drops asyncio's slow-callback warnings. ``IsolatedAsyncioTestCase`` runs
its loop in debug mode, so any step over 100 ms is reported, which is machine
timing rather than a finding. Every other asyncio warning still prints.

Usage: ``class MyTests(CapturedLabLogs, unittest.TestCase)`` (or
``unittest.IsolatedAsyncioTestCase``). ``assertLogs("uvicorn.error")`` keeps
working inside a test because it swaps in its own handler for the block.
"""

import logging

LAB_LOGGER_NAME = "uvicorn.error"
FAILURE_KINDS = ("failures", "errors")


class _Collector(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
        self.lines = []

    def emit(self, record):
        self.lines.append(self.format(record))


class _SlowCallbackFilter(logging.Filter):
    def filter(self, record):
        return not (isinstance(record.msg, str) and record.msg.startswith("Executing ") and " took " in record.msg)


class CapturedLabLogs:
    def run(self, result=None):
        logger, asyncio_logger = logging.getLogger(LAB_LOGGER_NAME), logging.getLogger("asyncio")
        collector, slow_callbacks = _Collector(), _SlowCallbackFilter()
        previous_level = logger.level
        logger.addHandler(collector)
        asyncio_logger.addFilter(slow_callbacks)
        # Record info events too, so a failure shows the whole request trail.
        if logger.getEffectiveLevel() > logging.INFO:
            logger.setLevel(logging.INFO)
        counts = {kind: len(getattr(result, kind, ())) for kind in FAILURE_KINDS}
        try:
            result = super().run(result)
        finally:
            logger.removeHandler(collector)
            logger.setLevel(previous_level)
            asyncio_logger.removeFilter(slow_callbacks)
        if collector.lines:
            _attach_to_failures(result, counts, collector.lines)
        return result


def _attach_to_failures(result, counts, lines):
    captured = "\nCaptured Lab log:\n" + "\n".join(lines) + "\n"
    for kind in FAILURE_KINDS:
        entries = getattr(result, kind, ())
        for index in range(counts[kind], len(entries)):
            test, text = entries[index]
            entries[index] = (test, text + captured)

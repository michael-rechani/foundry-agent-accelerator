import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from request_guard import (
    BodyReadTimeout, MAX_CONVERSATION_BYTES, MAX_REQUEST_BYTES, MAX_SETUP_BYTES,
    read_bounded_body, record_request_failure,
)
from log_capture import CapturedLabLogs


class BodyTests(CapturedLabLogs, unittest.IsolatedAsyncioTestCase):
    def request(self, chunks):
        async def stream():
            for chunk in chunks:
                yield chunk
        return SimpleNamespace(stream=stream)

    async def test_empty_and_exact_boundary_bodies_are_accepted(self):
        self.assertEqual(await read_bounded_body(self.request([]), 10), b"")
        for limit in (MAX_SETUP_BYTES, MAX_REQUEST_BYTES, MAX_CONVERSATION_BYTES):
            with self.subTest(limit=limit):
                body = await read_bounded_body(self.request([b"x" * (limit - 1), b"x"]), limit)
                self.assertEqual(body, b"x" * limit)

    async def test_single_and_chunked_overflow_stop_reading(self):
        for chunks in ([b"x" * 11], [b"x" * 5, b"x" * 6]):
            async def stream(chunks=chunks):
                for chunk in chunks:
                    yield chunk
                self.fail("Must not drain an oversized request")
            with self.assertRaises(OverflowError):
                await read_bounded_body(SimpleNamespace(stream=stream), 10)

    async def test_limits_count_bytes_not_characters(self):
        with self.assertRaises(OverflowError):
            await read_bounded_body(self.request([("\u00e9" * 6).encode("utf-8")]), 10)

    async def test_stalled_upload_has_one_deadline_and_is_cancelled(self):
        cancelled = []

        async def stream():
            yield b"x"
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.append(True)

        timeout = asyncio.timeout
        with patch("request_guard.asyncio.timeout", side_effect=lambda seconds: timeout(0.01)) as clock:
            with self.assertRaises(BodyReadTimeout):
                await read_bounded_body(SimpleNamespace(stream=stream), 10)
        clock.assert_called_once_with(5)
        self.assertEqual(cancelled, [True])

    async def test_disconnect_and_cancellation_are_not_converted_to_upload_errors(self):
        for problem in (ConnectionError("disconnected"), asyncio.CancelledError()):
            async def stream(problem=problem):
                raise problem
                yield b""
            with self.assertRaises(type(problem)):
                await read_bounded_body(SimpleNamespace(stream=stream), 10)

    def test_failure_metadata_never_contains_exception_messages(self):
        request = SimpleNamespace(state=SimpleNamespace())
        record_request_failure(request, RuntimeError("sensitive body, token, and endpoint"), "foundry")
        self.assertEqual(request.state.failure, {"error_type": "RuntimeError", "dependency": "foundry"})


if __name__ == "__main__":
    unittest.main()

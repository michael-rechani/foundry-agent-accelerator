import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from request_guard import (
    BodyReadTimeout, MAX_CONVERSATION_BYTES, MAX_REQUEST_BYTES, MAX_SETUP_BYTES,
    RateGate, RequestRejected, api_error, is_json, read_bounded_body, read_json_body, record_request_failure,
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


class AdmissionHelperTests(unittest.TestCase):
    def test_json_content_type_is_case_insensitive_and_ignores_parameters(self):
        for value in ("application/json", "Application/JSON", " application/json ; charset=utf-8", "APPLICATION/JSON;charset=UTF-8"):
            with self.subTest(value=value):
                self.assertTrue(is_json(SimpleNamespace(headers={"content-type": value})))

    def test_other_or_missing_content_types_are_not_json(self):
        for headers in ({}, {"content-type": ""}, {"content-type": "text/plain"}, {"content-type": "application/jsonp"},
                        {"content-type": "application/json-seq"}, {"content-type": "multipart/form-data; boundary=application/json"}):
            with self.subTest(headers=headers):
                self.assertFalse(is_json(SimpleNamespace(headers=headers)))

    def test_error_body_status_and_logged_code(self):
        request = SimpleNamespace(state=SimpleNamespace(request_id="abc"))
        response = api_error(request, 415, "json_required")
        self.assertEqual((response.status_code, response.body), (415, b'{"error":"json_required","request_id":"abc"}'))
        self.assertEqual(request.state.error_code, "json_required")
        self.assertNotIn("retry-after", response.headers)

    def test_retry_after_and_extra_fields_are_added_only_when_given(self):
        request = SimpleNamespace(state=SimpleNamespace(request_id="abc"))
        response = api_error(request, 429, "agents_busy", retry_after=60, reason="slots")
        self.assertEqual(response.headers["retry-after"], "60")
        self.assertEqual(response.body, b'{"error":"agents_busy","request_id":"abc","reason":"slots"}')
        self.assertEqual(api_error(request, 429, "busy", retry_after=7).headers["retry-after"], "7")


if __name__ == "__main__":
    unittest.main()


class RateGateTests(unittest.IsolatedAsyncioTestCase):
    def test_a_full_window_refuses_and_counts_nothing_until_it_expires(self):
        gate = RateGate(2, 4)
        self.assertTrue(gate.try_admit(now=100))
        self.assertTrue(gate.try_admit(now=130))
        self.assertFalse(gate.try_admit(now=159.9))
        self.assertEqual(list(gate.recent), [100, 130])
        self.assertTrue(gate.try_admit(now=160))
        self.assertEqual(list(gate.recent), [130, 160])

    def test_the_window_length_is_a_parameter(self):
        gate = RateGate(1, 4, window_seconds=10)
        self.assertTrue(gate.try_admit(now=0))
        self.assertFalse(gate.try_admit(now=9.9))
        self.assertTrue(gate.try_admit(now=10))

    async def test_every_slot_busy_refuses_without_using_the_budget(self):
        gate = RateGate(10, 2)
        await gate.slots.acquire()
        await gate.slots.acquire()
        self.assertFalse(gate.try_admit(now=1))
        self.assertEqual(len(gate.recent), 0)
        gate.slots.release()
        self.assertTrue(gate.try_admit(now=1))

    def test_without_a_time_the_clock_is_monotonic(self):
        gate = RateGate(1, 4)
        with patch("request_guard.time.monotonic", return_value=500):
            self.assertTrue(gate.try_admit())
            self.assertFalse(gate.try_admit())
        self.assertEqual(list(gate.recent), [500])


class ReadJsonBodyTests(unittest.IsolatedAsyncioTestCase):
    def request(self, chunks, content_type="application/json"):
        async def stream():
            for chunk in chunks:
                yield chunk
        return SimpleNamespace(stream=stream, headers={"content-type": content_type})

    async def rejection(self, request, limit=10, **options):
        with self.assertRaises(RequestRejected) as caught:
            await read_json_body(request, limit, **options)
        return caught.exception.status, caught.exception.code

    async def test_a_json_body_within_the_limit_is_returned(self):
        self.assertEqual(await read_json_body(self.request([b"{", b"}"], "Application/JSON; charset=utf-8"), 10), b"{}")

    async def test_a_wrong_content_type_is_415_unless_the_router_says_otherwise(self):
        wrong = self.request([b"{}"], "text/plain")
        self.assertEqual(await self.rejection(wrong), (415, "json_required"))
        self.assertEqual(await self.rejection(wrong, wrong_type=(400, "invalid_setup")), (400, "invalid_setup"))

    async def test_a_wrong_content_type_is_refused_before_the_body_is_read(self):
        async def stream():
            self.fail("Must not read a body that is not JSON")
            yield b""
        wrong = SimpleNamespace(stream=stream, headers={})
        self.assertEqual(await self.rejection(wrong), (415, "json_required"))

    async def test_too_much_data_is_413_with_the_routers_own_code(self):
        large = self.request([b"x" * 11])
        self.assertEqual(await self.rejection(large), (413, "request_too_large"))
        self.assertEqual(await self.rejection(large, too_large="conversation_too_large"), (413, "conversation_too_large"))

    async def test_a_stalled_upload_is_408(self):
        async def stream():
            await asyncio.Event().wait()
            yield b""
        timeout = asyncio.timeout
        stalled = SimpleNamespace(stream=stream, headers={"content-type": "application/json"})
        with patch("request_guard.asyncio.timeout", side_effect=lambda seconds: timeout(0.01)):
            self.assertEqual(await self.rejection(stalled), (408, "request_timeout"))

    async def test_a_disconnect_is_not_turned_into_a_rejection(self):
        async def stream():
            raise ConnectionError("disconnected")
            yield b""
        with self.assertRaises(ConnectionError):
            await read_json_body(SimpleNamespace(stream=stream, headers={"content-type": "application/json"}), 10)

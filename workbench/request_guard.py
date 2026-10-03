import asyncio
import time
from collections import deque

from fastapi.responses import JSONResponse


MAX_REQUEST_BYTES = 65536
MAX_CONVERSATION_BYTES = 524288
MAX_SETUP_BYTES = 32768


class BodyReadTimeout(TimeoutError):
    pass


async def read_bounded_body(request, limit):
    """Bound uploads before parsing, including chunked bodies without Content-Length."""
    body = bytearray()
    try:
        async with asyncio.timeout(5):
            async for chunk in request.stream():
                if len(chunk) > limit - len(body):
                    raise OverflowError("Request too large")
                body.extend(chunk)
    except TimeoutError as problem:
        raise BodyReadTimeout("Upload timed out") from problem
    return body


def record_request_failure(request, problem, dependency):
    # Exception messages, URLs and tracebacks may contain submitted content or credentials.
    request.state.failure = {"error_type": type(problem).__name__, "dependency": dependency}


def request_allowed(request, origins):
    """Require the Lab header (which forces a CORS preflight this app never grants), no cross-site fetch, and an allowed origin."""
    return (
        request.headers.get("x-workbench-request") == "1"
        and request.headers.get("sec-fetch-site") != "cross-site"
        and request.headers.get("origin") in (None, *origins)
    )


def is_json(request):
    """True for an application/json body; media types are case-insensitive and may carry parameters."""
    return request.headers.get("content-type", "").split(";")[0].strip().lower() == "application/json"


def api_error(request, status, code, *, retry_after=None, **extra):
    """Build the API's error body and record its code for the request log. The correlation header comes from the app's middleware."""
    request.state.error_code = code
    return JSONResponse(
        {"error": code, "request_id": request.state.request_id, **extra}, status_code=status,
        headers=None if retry_after is None else {"Retry-After": str(retry_after)},
    )


class RateGate:
    """A request budget per window plus a cap on requests running at once; a full gate means a 429."""

    def __init__(self, per_minute, concurrent=4, window_seconds=60.0):
        self.per_minute, self.window_seconds = per_minute, window_seconds
        self.slots = asyncio.Semaphore(concurrent)
        self.recent = deque()

    def try_admit(self, now=None):
        """Count this request and return True, or return False (counting nothing) when the window or every slot is full."""
        now = time.monotonic() if now is None else now
        while self.recent and self.recent[0] <= now - self.window_seconds:
            self.recent.popleft()
        if len(self.recent) >= self.per_minute or self.slots.locked():
            return False
        self.recent.append(now)
        return True


class RequestRejected(Exception):
    """A request the router must answer with this status and error code."""

    def __init__(self, status, code):
        super().__init__(code)
        self.status, self.code = status, code


async def read_json_body(request, limit, *, too_large="request_too_large", wrong_type=(415, "json_required")):
    """Return the bounded body of a JSON request, or raise RequestRejected for a wrong type (default 415), too much data (413) or a stalled upload (408)."""
    if not is_json(request):
        raise RequestRejected(*wrong_type)
    try:
        return await read_bounded_body(request, limit)
    except OverflowError as problem:
        raise RequestRejected(413, too_large) from problem
    except BodyReadTimeout as problem:
        raise RequestRejected(408, "request_timeout") from problem

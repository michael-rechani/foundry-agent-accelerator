import asyncio


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

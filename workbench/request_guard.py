def request_allowed(request, origins):
    """Require the Lab header (which forces a CORS preflight this app never grants), no cross-site fetch, and an allowed origin."""
    return (
        request.headers.get("x-workbench-request") == "1"
        and request.headers.get("sec-fetch-site") != "cross-site"
        and request.headers.get("origin") in (None, *origins)
    )

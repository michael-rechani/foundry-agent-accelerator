import argparse
import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import UUID, uuid4


APPLICATION_PROMPT = (
    "Review this synthetic application. CRIT-1 requires a budget. APP-1 describes a twelve-week workshop "
    "but supplies no budget. Cite APP-1 and identify missing evidence."
)
CASE_PROMPT = (
    "Review this synthetic case. CASE-1 records intake on June 1, 2027; CASE-2 records intake "
    "on June 3, 2027. Summarize the conflict and cite the source identifiers."
)
CUSTOMER_REVIEW_SPECIALISTS = (
    ("inspect_application", "application-review-agent", APPLICATION_PROMPT),
    ("inspect_case", "case-review-agent", CASE_PROMPT),
)


class CheckError(Exception):
    pass


def require(condition, message):
    if not condition:
        raise CheckError(message)


def valid_etag(value):
    return (isinstance(value, str) and bool(value.strip()) and value == value.strip()
            and value != "*" and "," not in value
            and not any(ord(character) < 0x20 or 0x7F <= ord(character) <= 0x9F for character in value))


def unique_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field")
        result[key] = value
    return result


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, file, code, message, headers, new_url):
        raise CheckError("Unexpected redirect; use the verified Lab origin")


class PrivateClient:
    def __init__(self, base_url=None, loopback=False):
        if loopback:
            host = os.getenv("WORKBENCH_ALLOWED_HOSTS", "")
            require(os.getenv("WORKBENCH_MODE") == "private" and host and "," not in host,
                    "Loopback verification requires private mode and one allowed host in the environment")
            self.base_url, self.origin = "http://127.0.0.1:8080", f"https://{host}"
            self.host = host
        else:
            origin = base_url or ""
            origin_error = "Supply the exact HTTPS origin, not a path, query, fragment, or credentials"
            require(not any(ord(character) <= 0x20 or 0x7F <= ord(character) <= 0x9F for character in origin),
                    origin_error)
            try:
                parsed = urlsplit(origin)
                hostname, port = parsed.hostname, parsed.port
            except ValueError:
                raise CheckError(origin_error) from None
            require(parsed.scheme == "https" and hostname
                    and parsed.username is None and parsed.password is None
                    and (port is not None or not parsed.netloc.endswith(":"))
                    and parsed.path in {"", "/"} and not parsed.query and not parsed.fragment
                    and "?" not in origin and "#" not in origin, origin_error)
            self.base_url = origin.rstrip("/")
            self.origin, self.host = self.base_url, parsed.netloc
        self.opener = build_opener(NoRedirects)

    def call(self, method, path, body=None, etag=None, expected=200):
        if method in {"PUT", "DELETE"}:
            require(valid_etag(etag), "Conditional mutation requires a valid nonempty version ETag")
        headers = {"X-Workbench-Request": "1", "Origin": self.origin, "Host": self.host}
        if etag:
            headers["If-Match"] = etag
        if body is not None:
            headers["Content-Type"] = "application/json"
        # The constructor restricts base_url to HTTPS or the fixed loopback origin.
        request = Request(self.base_url + path, method=method, headers=headers,  # noqa: S310
                          data=json.dumps(body).encode() if body is not None else None)
        expected_error = ({("PUT", 409): "conversation_changed", ("GET", 404): "conversation_not_found"}
                          .get((method, expected)) if path.startswith("/api/conversations/") else None)
        try:
            try:
                response = self.opener.open(request, timeout=200 if path == "/api/reviews" else 45)
            except HTTPError as problem:
                if problem.code != expected or expected_error is None:
                    raise CheckError(f"{method} {path}: HTTP {problem.code}; no automatic retry performed") from problem
                response = problem
            with response:
                require(response.status == expected, f"{method} {path}: unexpected HTTP status")
                data = json.load(response, object_pairs_hook=unique_json_object)
        except (URLError, TimeoutError) as problem:
            raise CheckError(f"{method} {path}: connection unavailable or timed out") from problem
        except (ValueError, UnicodeError) as problem:
            raise CheckError(f"{method} {path}: invalid JSON response") from problem
        require(isinstance(data, dict), f"{method} {path}: expected a JSON object")
        if expected_error is not None:
            require(isinstance(data.get("error"), str) and data["error"] == expected_error,
                    f"{method} {path}: expected conversation error code was not confirmed")
            return {}
        return data


def check_agent_response(client, agent, prompt, expected_tool=None):
    result = client.call("POST", "/api/reviews", {"agent_id": agent["id"], "input": prompt})
    require(result.get("status") == "completed" and isinstance(result.get("text"), str) and result["text"].strip(),
            "Agent response is incomplete")
    require(result.get("agent") == agent["agent"], "Response did not identify the configured agent")
    bindings = agent.get("tools", {})
    require(isinstance(bindings, dict), "Agent tool bindings are invalid")
    if bindings or expected_tool:
        receipts = result.get("receipts")
        valid = isinstance(receipts, list) and len(receipts) == 1 and isinstance(receipts[0], dict)
        if valid:
            receipt = receipts[0]
            tool, call_id = receipt.get("tool"), receipt.get("call_id")
            valid = (
                receipt.get("verified") is True
                and isinstance(call_id, str) and bool(call_id.strip())
                and isinstance(tool, str) and tool in bindings
                and (expected_tool is None or tool == expected_tool)
                and receipt.get("agent") == bindings[tool]
                and isinstance(receipt.get("output"), str) and bool(receipt["output"].strip())
            )
        suffix = f" for {expected_tool}" if expected_tool else ""
        require(valid, f"Expected one verified specialist receipt{suffix}, not just a nonempty model answer")
    return result


def verify_storage(client, body):
    try:
        saved = client.call("POST", "/api/conversations", body)
    except CheckError as problem:
        raise CheckError("Storage create outcome is unconfirmed; inspect synthetic records before retrying; "
                         "no cleanup or automatic retry performed") from problem
    try:
        identifier = saved["id"]
        require(isinstance(identifier, str) and str(UUID(identifier)) == identifier,
                "Storage create did not identify a canonical synthetic conversation")
    except (CheckError, KeyError, ValueError, TypeError) as problem:
        raise CheckError("Storage create did not return a usable conversation ID; inspect synthetic records "
                         "before retrying; no cleanup or automatic retry performed") from problem

    phase = "create version confirmation"
    try:
        owned_etag = saved.get("_etag")
        require(valid_etag(owned_etag), "Create did not confirm the synthetic version")
        phase = "initial record verification"
        read = client.call("GET", "/api/conversations/" + identifier)
        require(isinstance(read, dict) and read.get("id") == identifier
                and valid_etag(read.get("_etag")) and read["_etag"] == owned_etag,
                "Initial record identity or version was not confirmed")
        turns = read.get("turns")
        require(isinstance(turns, list) and len(turns) == 1 and isinstance(turns[0], dict)
                and isinstance(turns[0].get("result"), dict), "Saved transcript structure did not match")
        expected_turn = body["turns"][0]
        require(read.get("agent_id") == body["agent_id"]
                and turns[0].get("question") == expected_turn["question"]
                and all(field in expected_turn["result"] and turns[0]["result"].get(field) == expected_turn["result"][field]
                        for field in ("request_id", "agent", "text")), "Saved transcript did not match")
        path = "/api/conversations/" + identifier
        created_etag = owned_etag
        phase = "conditional update confirmation"
        updated = client.call("PUT", path, body, etag=owned_etag)
        require(isinstance(updated, dict) and updated.get("id") == identifier
                and valid_etag(updated.get("_etag")) and updated["_etag"] != owned_etag,
                "Conditional update did not confirm the same record and a new version")
        owned_etag = updated["_etag"]
        phase = "stale-update conflict confirmation"
        conflict = client.call("PUT", path, body, etag=created_etag, expected=409)
        require(conflict == {}, "Stale update did not confirm the expected conflict")
        phase = "cleanup version confirmation"
        current = client.call("GET", path)
        require(isinstance(current, dict) and current.get("id") == identifier
                and valid_etag(current.get("_etag")) and current["_etag"] == owned_etag,
                "Cleanup record identity or owned version was not confirmed")
        phase = "conditional deletion confirmation"
        deleted = client.call("DELETE", path, etag=owned_etag)
        require(isinstance(deleted, dict) and deleted.get("deleted") is True,
                "Conditional deletion was not confirmed")
        phase = "deletion absence verification"
        require(client.call("GET", path, expected=404) == {}, "Deleted record absence was not confirmed")
    except CheckError as problem:
        deletion_started = phase in {"conditional deletion confirmation", "deletion absence verification"}
        disposition = "deletion may already have completed" if deletion_started else "record retained when present"
        raise CheckError(f"Storage {phase} failed; synthetic conversation {identifier}: {disposition}; "
                         "ownership or mutation outcome is unconfirmed; inspect before retrying; "
                         "no further mutations or automatic retry performed") from problem
    return ["cosmos_create_read_update_conflict", "synthetic_record_deleted"]


def verify(client, *, check_storage=False, run_agent=False, check_review_specialists=False):
    require(not (run_agent and check_review_specialists), "Choose one agent verification mode")
    config = client.call("GET", "/api/config")
    require(config.get("mode") == "private" and config.get("history_enabled"), "Expected the private Cosmos-backed Lab")
    health = client.call("GET", "/api/health/dependencies")
    require(all(health.get(name) == value for name, value in
                {"status": "ready", "foundry": "ready", "cosmos": "ready"}.items()), "Foundry or Cosmos dependency checks are not ready")
    agents = [item for item in config.get("agents", []) if item.get("id") == config.get("default_agent")]
    require(len(agents) == 1, "Default agent is not uniquely configured")
    agent = agents[0]
    prompt = APPLICATION_PROMPT
    result = {"request_id": str(uuid4()), "status": "completed", "agent": agent["agent"],
              "text": "Synthetic storage verification only; no agent was invoked.", "receipts": [], "elapsed_ms": 0}
    checks = ["private_configuration", "cached_dependencies"]
    if check_review_specialists:
        bindings = agent.get("tools")
        require(
            agent.get("id") == "customer-review" and agent.get("agent") == "customer-review-coordinator"
            and isinstance(bindings, dict)
            and all(bindings.get(tool) == target for tool, target, _ in CUSTOMER_REVIEW_SPECIALISTS),
            "Default coordinator does not have the expected application and case specialist bindings",
        )
        for tool, _, prompt in CUSTOMER_REVIEW_SPECIALISTS:
            result = check_agent_response(client, agent, prompt, expected_tool=tool)
            checks.append(f"customer_review_{tool}_receipt")
    elif run_agent:
        result = check_agent_response(client, agent, prompt)
        checks.append("agent_and_specialist_receipt" if agent.get("tools") else "agent_execution")
    if check_storage:
        body = {"agent_id": agent["id"], "turns": [{"question": prompt, "result": result}]}
        checks.extend(verify_storage(client, body))
    return checks


def main(argv=None):
    parser = argparse.ArgumentParser(description="Check Lab API responses without deploying resources or logging review content.")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--base-url", help="HTTPS origin; API success does not verify private ingress")
    target.add_argument("--loopback", action="store_true",
                        help="Check fixed loopback HTTP; this does not verify ingress or container isolation")
    parser.add_argument("--check-storage", action="store_true", help="Create, read, update, and delete one fictional conversation")
    agent_check = parser.add_mutually_exclusive_group()
    agent_check.add_argument("--run-agent", action="store_true",
                             help="Make one explicitly approved, billable synthetic agent call")
    agent_check.add_argument("--check-review-specialists", action="store_true",
                             help="Make up to two explicitly approved, billable coordinator requests to verify both specialists")
    arguments = parser.parse_args(argv)
    try:
        checks = verify(PrivateClient(arguments.base_url, arguments.loopback),
                        check_storage=arguments.check_storage, run_agent=arguments.run_agent,
                        check_review_specialists=arguments.check_review_specialists)
    except CheckError as problem:
        print(json.dumps({"status": "failed", "error": str(problem)}), file=sys.stderr)
        return 1
    print(json.dumps({"status": "passed", "path": "loopback_http" if arguments.loopback else "https_origin",
                      "checks": checks, "https_origin_reached": not arguments.loopback,
                      "ingress_verified": False, "private_network_verified": False,
                      "rendered_ui_verified": False, "container_isolation_verified": False,
                      "model_quality_verified": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

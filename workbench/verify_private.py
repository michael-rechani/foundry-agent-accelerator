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
            parsed = urlsplit(origin)
            require(parsed.scheme == "https" and parsed.hostname and not parsed.username and not parsed.password
                    and parsed.path in {"", "/"} and not parsed.query and not parsed.fragment
                    and "?" not in origin and "#" not in origin,
                    "Supply the exact HTTPS origin, not a path, query, fragment, or credentials")
            self.base_url = origin.rstrip("/")
            self.origin, self.host = self.base_url, parsed.netloc
        self.opener = build_opener(NoRedirects)

    def call(self, method, path, body=None, etag=None, expected=200):
        headers = {"X-Workbench-Request": "1", "Origin": self.origin, "Host": self.host}
        if etag:
            headers["If-Match"] = etag
        if body is not None:
            headers["Content-Type"] = "application/json"
        # The constructor restricts base_url to HTTPS or the fixed loopback origin.
        request = Request(self.base_url + path, method=method, headers=headers,  # noqa: S310
                          data=json.dumps(body).encode() if body is not None else None)
        try:
            with self.opener.open(request, timeout=200 if path == "/api/reviews" else 45) as response:
                require(response.status == expected, f"{method} {path}: unexpected HTTP status")
                data = json.load(response)
        except HTTPError as problem:
            if problem.code == expected:
                return {}
            raise CheckError(f"{method} {path}: HTTP {problem.code}; no automatic retry performed") from problem
        except (URLError, TimeoutError) as problem:
            raise CheckError(f"{method} {path}: connection unavailable or timed out") from problem
        except (ValueError, UnicodeError) as problem:
            raise CheckError(f"{method} {path}: invalid JSON response") from problem
        require(isinstance(data, dict), f"{method} {path}: expected a JSON object")
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
        saved = client.call("POST", "/api/conversations", body)
        try:
            identifier = str(UUID(saved["id"]))
            require(identifier == saved["id"], "Storage returned an invalid conversation identifier")
        except (KeyError, ValueError, TypeError) as problem:
            raise CheckError("Storage did not return a usable conversation ID; inspect before retrying") from problem
        path = "/api/conversations/" + identifier
        try:
            read = client.call("GET", path)
            require(read.get("turns") and read["turns"][0]["result"]["text"] == result["text"], "Saved transcript did not match")
            updated = client.call("PUT", path, body, etag=read.get("_etag"))
            require(updated.get("_etag") and updated["_etag"] != read.get("_etag"), "Conditional update did not advance its ETag")
            client.call("PUT", path, body, etag=read["_etag"], expected=409)
            checks.append("cosmos_create_read_update_conflict")
        finally:
            current = client.call("GET", path)
            require(current.get("_etag"), f"Cleanup needs the current ETag for synthetic conversation {identifier}")
            deleted = client.call("DELETE", path, etag=current["_etag"])
            require(deleted.get("deleted") is True, f"Cleanup was not confirmed for synthetic conversation {identifier}")
            client.call("GET", path, expected=404)
        checks.append("synthetic_record_deleted")
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

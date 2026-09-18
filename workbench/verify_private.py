import argparse
import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import UUID, uuid4


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
                    "Loopback verification must run inside the configured private Lab container")
            self.base_url, self.origin = "http://127.0.0.1:8080", f"https://{host}"
            self.host = host
        else:
            parsed = urlsplit(base_url or "")
            require(parsed.scheme == "https" and parsed.hostname and not parsed.username and not parsed.password
                    and parsed.path in {"", "/"} and not parsed.query and not parsed.fragment,
                    "Supply the exact private HTTPS origin, not a path or credentials")
            self.base_url = base_url.rstrip("/")
            self.origin, self.host = self.base_url, parsed.netloc
        self.opener = build_opener(NoRedirects)

    def call(self, method, path, body=None, etag=None, expected=200):
        headers = {"X-Workbench-Request": "1", "Origin": self.origin, "Host": self.host}
        if etag:
            headers["If-Match"] = etag
        if body is not None:
            headers["Content-Type"] = "application/json"
        request = Request(self.base_url + path, method=method, headers=headers,
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
            raise CheckError(f"{method} {path}: private connection unavailable or timed out") from problem
        except (ValueError, UnicodeError) as problem:
            raise CheckError(f"{method} {path}: invalid JSON response") from problem
        require(isinstance(data, dict), f"{method} {path}: expected a JSON object")
        return data


def verify(client, *, check_storage=False, run_agent=False):
    config = client.call("GET", "/api/config")
    require(config.get("mode") == "private" and config.get("history_enabled"), "Expected the private Cosmos-backed Lab")
    health = client.call("GET", "/api/health/dependencies")
    require(all(health.get(name) == value for name, value in
                {"status": "ready", "foundry": "ready", "cosmos": "ready"}.items()), "Foundry or Cosmos dependency checks are not ready")
    agents = [item for item in config.get("agents", []) if item.get("id") == config.get("default_agent")]
    require(len(agents) == 1, "Default agent is not uniquely configured")
    agent = agents[0]
    prompt = ("Review this synthetic application. CRIT-1 requires a budget. APP-1 describes a twelve-week workshop "
              "but supplies no budget. Cite APP-1 and identify missing evidence.")
    result = {"request_id": str(uuid4()), "status": "completed", "agent": agent["agent"],
              "text": "Synthetic storage verification only; no agent was invoked.", "receipts": [], "elapsed_ms": 0}
    checks = ["private_configuration", "cached_dependencies"]
    if run_agent:
        result = client.call("POST", "/api/reviews", {"agent_id": agent["id"], "input": prompt})
        require(result.get("status") == "completed" and isinstance(result.get("text"), str) and result["text"].strip(),
                "Agent response is incomplete")
        require(result.get("agent") == agent["agent"], "Response did not identify the configured agent")
        bindings, receipts = agent.get("tools", {}), result.get("receipts", [])
        if bindings:
            require(len(receipts) == 1 and all(
                receipt.get("verified") is True and receipt.get("call_id") and receipt.get("tool") in bindings
                and receipt.get("agent") == bindings[receipt["tool"]]
                and isinstance(receipt.get("output"), str) and receipt["output"].strip()
                for receipt in receipts
            ), "Expected one verified specialist receipt, not just a nonempty model answer")
        checks.append("agent_and_specialist_receipt" if bindings else "agent_execution")
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
    parser = argparse.ArgumentParser(description="Verify the existing Lab without deploying resources or logging review content.")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--base-url", help="Verified private HTTPS origin")
    target.add_argument("--loopback", action="store_true", help="Existing-container runtime check only; not an ingress test")
    parser.add_argument("--check-storage", action="store_true", help="Create, read, update, and delete one fictional conversation")
    parser.add_argument("--run-agent", action="store_true", help="Make one explicitly approved, billable synthetic agent call")
    arguments = parser.parse_args(argv)
    try:
        checks = verify(PrivateClient(arguments.base_url, arguments.loopback),
                        check_storage=arguments.check_storage, run_agent=arguments.run_agent)
    except CheckError as problem:
        print(json.dumps({"status": "failed", "error": str(problem)}), file=sys.stderr)
        return 1
    print(json.dumps({"status": "passed", "path": "container_loopback" if arguments.loopback else "private_https",
                      "checks": checks, "ingress_verified": not arguments.loopback,
                      "model_quality_verified": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Public graph inspection plus explicitly projected real-modtm Linux Read tests.

Never runs the infrastructure root's plan, test/apply, or refresh. Only the
telemetry-only projection accepts fictional state and plan commands.
"""
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

import hcl2
import check_platform_router_plan as diagnostic

PROVIDER = "registry.terraform.io/azure/modtm"
FICTIVE_TAGS = {
    "subscription_id": "11111111-1111-1111-1111-111111111111",
    "tenant_id": "22222222-2222-2222-2222-222222222222",
    "random_id": "33333333-3333-3333-3333-333333333333",
    "location": "fictional-location",
}


def checked_process(binary, root, home, args, endpoint=None):
    ordinary = (
        ["version", "-json"],
        ["init", "-backend=false", "-get=false", "-lockfile=readonly", "-input=false", "-no-color"],
        ["graph", "-type=plan"],
    )
    projection = args in (
        ["init", "-backend=false", "-input=false", "-no-color"],
        ["plan", "-input=false", "-refresh=true", "-lock=true", "-no-color", "-out=read.tfplan"],
        ["show", "-json", "read.tfplan"],
    )
    if args not in ordinary and not (endpoint and projection):
        raise RuntimeError("Command outside telemetry experiment allowlist.")
    if endpoint and not re.fullmatch(r"http://127\.0\.0\.1:[0-9]+/telemetry", endpoint):
        raise RuntimeError("Only fictional loopback endpoint is allowed.")
    env = {"PATH": os.environ["PATH"], "HOME": str(home), "LANG": "C.UTF-8",
           "TF_CLI_CONFIG_FILE": str(home / "terraform.rc"), "TF_INPUT": "0",
           "TF_IN_AUTOMATION": "true", "CHECKPOINT_DISABLE": "1"}
    if endpoint:
        env["MODTM_ENDPOINT"] = endpoint
    try:
        result = subprocess.run([binary, f"-chdir={root}", *args], env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                check=False, timeout=90)
    except subprocess.TimeoutExpired:
        raise RuntimeError("Telemetry experiment subprocess timed out; output withheld.") from None
    if result.returncode:
        categories = (b"Invalid provider configuration", b"Invalid provider configuration reference",
                      b"Missing required provider configuration", b"Invalid character", b"Duplicate provider configuration")
        category = next((value.decode() for value in categories if value in result.stdout + result.stderr), "unclassified")
        raise RuntimeError("Telemetry experiment subprocess failed: " + args[0] + "; " + category + "; output withheld.")
    return result.stdout


def cli_config(home, mirror):
    home.mkdir(mode=0o700)
    (home / "terraform.rc").write_text('disable_checkpoint = true\nprovider_installation {\n filesystem_mirror {\n path = '
                                       + json.dumps(str(mirror)) + '\n }\n}\n')


def inspect_graph(bundle, binary):
    manifest = json.loads((bundle / "manifest.json").read_bytes())
    if manifest["source_sha"] != diagnostic.DIAGNOSTIC_SOURCE_SHA or manifest["terraform"] != "1.16.4":
        raise RuntimeError("Public fixture source/runtime mismatch.")
    if manifest["providers"].get(PROVIDER) != "0.4.0":
        raise RuntimeError("This experiment requires real Azure/modtm 0.4.0.")
    records = []
    for module in manifest["modules"]:
        folder = bundle / "root" / module["Dir"]
        for path in sorted(folder.glob("*.tf")):
            with path.open() as stream:
                content = hcl2.load(stream)
            for block in content.get("provider", []):
                if "modtm" in block:
                    records.append({"kind": "provider", "module": module["Key"], "file": path.name,
                                    "configuration": block["modtm"]})
            for block in content.get("resource", []):
                for resource_type, names in block.items():
                    if resource_type == "modtm_telemetry":
                        for name, config in names.items():
                            records.append({"kind": "resource", "module": module["Key"], "name": name,
                                            "file": path.name, "provider": config.get("provider", "implicit-default"),
                                            "count": config.get("count"), "source": module["Source"],
                                            "version": module.get("Version", "local")})
            for block in content.get("module", []):
                for name, config in block.items():
                    if "providers" in config:
                        records.append({"kind": "module-mapping", "module": module["Key"], "name": name,
                                        "file": path.name, "providers": config["providers"]})
            for block in content.get("terraform", []):
                for requirements in block.get("required_providers", []):
                    if "modtm" in requirements:
                        records.append({"kind": "requirement", "module": module["Key"], "file": path.name,
                                        "requirement": requirements["modtm"]})
    telemetry = [item for item in records if item["kind"] == "resource"]
    if not telemetry or any(item["provider"] != "implicit-default" for item in telemetry):
        raise RuntimeError("Unreviewed explicit telemetry provider wiring.")
    if any(item["kind"] == "provider" for item in records):
        raise RuntimeError("Module-local modtm provider configuration needs separate review.")
    for item in records:
        if item["kind"] == "requirement":
            req = item["requirement"]
            if req.get("source", "").lower() != "azure/modtm" or req.get("configuration_aliases"):
                raise RuntimeError("Unreviewed telemetry source/alias requirement.")
        if item["kind"] == "module-mapping" and "modtm" in json.dumps(item["providers"]):
            raise RuntimeError("Explicit modtm module mapping requires separate review.")
    with tempfile.TemporaryDirectory() as folder:
        base = Path(folder)
        root = base / "root"
        shutil.copytree(bundle / "root", root)
        diagnostic.write_backend(root)
        # Graph inspection cannot initialize Azure state; remove only backend in this test copy.
        overlay = json.loads((root / diagnostic.DIAGNOSTIC_OVERLAY).read_bytes())
        if overlay["terraform"].pop("backend") != {"azurerm": {}}:
            raise RuntimeError("Unexpected tested overlay backend.")
        (root / diagnostic.DIAGNOSTIC_OVERLAY).write_text(json.dumps(overlay))
        home = base / "home"
        cli_config(home, bundle / "mirror")
        checked_process(binary, root, home, ["init", "-backend=false", "-get=false", "-lockfile=readonly", "-input=false", "-no-color"])
        graph = checked_process(binary, root, home, ["graph", "-type=plan"]).decode()
    provider_nodes = sorted(set(re.findall(r'provider\["registry\.terraform\.io/azure/modtm"\](?:\.[A-Za-z0-9_]+)?', graph.replace('\"', '"'))))
    references = [line.strip() for line in graph.splitlines() if "modtm_telemetry" in line and "provider" in line]
    if len(references) != len(telemetry) or provider_nodes != ['provider["' + PROVIDER + '"]']:
        raise RuntimeError("Missing or aliased resolved telemetry graph edges.")
    print("PUBLIC ACTUAL-ROOT SOURCE WIRING:", json.dumps(records, sort_keys=True))
    print("PUBLIC ACTUAL-ROOT MODTM GRAPH:", json.dumps(references, sort_keys=True))
    return telemetry, records, graph


def projected_read(bundle, binary, telemetry, enabled, alias=False):
    requests = []
    class Listener(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append({"method": "GET", "path": self.path})
            self.send_response(200)
            self.end_headers()
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
            requests.append({"method": "POST", "path": self.path, "body": body})
            self.send_response(200)
            self.end_headers()
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Listener)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    endpoint = f"http://127.0.0.1:{server.server_port}/telemetry"
    try:
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            root = base / "root"
            root.mkdir()
            home = base / "home"
            cli_config(home, bundle / "mirror")
            if not enabled:
                with tempfile.TemporaryDirectory() as reviewed:
                    exact_root = Path(reviewed) / "root"
                    shutil.copytree(bundle / "root", exact_root)
                    diagnostic.write_backend(exact_root)
                    tested_provider = json.loads((exact_root / diagnostic.DIAGNOSTIC_OVERLAY).read_bytes())["provider"]
                if tested_provider != {"modtm": {"enabled": False}}:
                    raise RuntimeError("Reviewed diagnostic telemetry configuration differs.")
                provider = tested_provider
            else:
                provider = {"modtm": {"enabled": True}}
            if alias:
                provider["modtm"] = [{"enabled": False}, {"alias": "escape", "enabled": True}]
            config = {"terraform": {"required_providers": {"modtm": {"source": "azure/modtm", "version": "= 0.4.0"}}},
                      "provider": provider, "module": {}}
            resources = []
            expected_addresses = []
            # Flatten ACTUAL module keys into nested equivalent module calls, not the infrastructure root.
            module_configs = {"": config}
            for index, item in enumerate(telemetry):
                key = item["module"]
                parent = ""
                for part in key.split(".") if key else []:
                    child_key = parent + "." + part if parent else part
                    if child_key not in module_configs:
                        relative = "projection/" + child_key.replace(".", "_")
                        module_configs[parent].setdefault("module", {})[part] = {"source": "./" + relative if not parent else "../" + child_key.replace(".", "_")}
                        module_configs[child_key] = {"terraform": {"required_providers": {"modtm": {"source": "azure/modtm"}}}}
                        (root / relative).mkdir(parents=True)
                    parent = child_key
                tags = dict(FICTIVE_TAGS, module_source=item["source"], module_version=item["version"])
                module_configs[key].setdefault("resource", {}).setdefault("modtm_telemetry", {})[item["name"]] = {
                    "count": 1, "tags": dict(tags, location="fictional-changed-location")}
                if alias:
                    # Explicit module remapping demonstrates a root default is NOT alias isolation.
                    first = key.split(".")[0] if key else None
                    if first:
                        config["module"][first]["providers"] = {"modtm": "modtm.escape"}
                address = "".join("module." + part + "." for part in key.split(".")) if key else ""
                address += "modtm_telemetry." + item["name"] + "[0]"
                expected_addresses.append(address)
                resources.append({"module": "".join("module." + part + "." for part in key.split("."))[:-1] if key else "",
                                  "mode": "managed", "type": "modtm_telemetry", "name": item["name"],
                                  "provider": 'provider["' + PROVIDER + '"]' + (".escape" if alias else ""),
                                  "instances": [{"index_key": 0, "schema_version": 0, "attributes": {
                                      "id": f"44444444-4444-4444-4444-{index:012d}", "tags": tags,
                                      "endpoint": None, "nonce": None, "ephemeral_number": None}, "sensitive_attributes": []}]})
            for key, value in module_configs.items():
                directory = root if not key else root / "projection" / key.replace(".", "_")
                (directory / "main.tf.json").write_text(json.dumps(value))
            state = {"version": 4, "terraform_version": "1.16.4", "serial": 1,
                     "lineage": "55555555-5555-5555-5555-555555555555", "outputs": {}, "resources": resources}
            state_path = root / "terraform.tfstate"
            state_path.write_text(json.dumps(state))
            before = state_path.read_bytes()
            checked_process(binary, root, home, ["init", "-backend=false", "-input=false", "-no-color"], endpoint)
            checked_process(binary, root, home, ["plan", "-input=false", "-refresh=true", "-lock=true", "-no-color", "-out=read.tfplan"], endpoint)
            plan = json.loads(checked_process(binary, root, home, ["show", "-json", "read.tfplan"], endpoint))
            if state_path.read_bytes() != before:
                raise RuntimeError("Projected local source state changed during plan.")
            changes = plan.get("resource_changes")
            if not changes or sorted(change["address"] for change in changes) != sorted(expected_addresses):
                raise RuntimeError("Projection hid or added telemetry resource changes.")
            if any(change["change"]["actions"] != ["update"] for change in changes):
                raise RuntimeError("Projection did not preserve intentional resource updates.")
            if plan.get("resource_drift") or not plan.get("complete"):
                raise RuntimeError("Incomplete or unexpected projection plan.")
            evidence = {"case": "alias-escape" if alias else ("enabled" if enabled else "disabled"),
                        "requests": requests, "resource_changes": changes,
                        "resource_changes_sha256": hashlib.sha256(json.dumps(changes, sort_keys=True).encode()).hexdigest()}
            return evidence
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


class TelemetryTests(unittest.TestCase):
    def test_failed_timeout_and_forbidden_processes_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for args in (["apply"], ["test"], ["refresh"], ["state", "push"], ["plan", "-refresh=false"]):
                with self.assertRaises(RuntimeError):
                    checked_process("terraform", root, root, args)
            with patch.object(subprocess, "run") as run:
                run.return_value.returncode = 1
                with self.assertRaises(RuntimeError):
                    checked_process("terraform", root, root, ["version", "-json"])
            with patch.object(subprocess, "run", side_effect=subprocess.TimeoutExpired("terraform", 90)):
                with self.assertRaises(RuntimeError):
                    checked_process("terraform", root, root, ["version", "-json"])
            with patch.object(subprocess, "run") as run:
                run.return_value.returncode = 0
                run.return_value.stdout = b"{}"
                with patch.dict(os.environ, {"ARM_CLIENT_SECRET": "fictional", "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "fictional"}):
                    checked_process("terraform", root, root, ["version", "-json"])
                self.assertNotIn("ARM_CLIENT_SECRET", run.call_args.kwargs["env"])
                self.assertNotIn("ACTIONS_ID_TOKEN_REQUEST_TOKEN", run.call_args.kwargs["env"])

    def test_actual_graph_and_projected_real_provider_read(self):
        bundle = Path(os.environ["TELEMETRY_PUBLIC_BUNDLE"])
        binary = os.environ["TELEMETRY_TERRAFORM"]
        telemetry, records, graph = inspect_graph(bundle, binary)
        enabled = projected_read(bundle, binary, telemetry, True)
        disabled = projected_read(bundle, binary, telemetry, False)
        escape = projected_read(bundle, binary, telemetry, False, alias=True)
        for case in (enabled, escape):
            posts = [request for request in case["requests"] if request["method"] == "POST"]
            self.assertEqual(len(posts), len(telemetry))
            self.assertTrue(any(request["method"] == "GET" for request in case["requests"]))
            for request in posts:
                self.assertEqual(request["body"]["event"], "read")
                self.assertEqual(request["body"]["subscription_id"], FICTIVE_TAGS["subscription_id"])
        self.assertEqual(disabled["requests"], [])
        self.assertEqual(enabled["resource_changes"], disabled["resource_changes"])
        for case in (enabled, disabled, escape):
            print("PROJECTED LINUX REAL MODTM READ:", json.dumps({key: value for key, value in case.items() if key != "resource_changes"}, sort_keys=True))
        evidence = Path(os.environ["TELEMETRY_EVIDENCE"])
        evidence.write_text(json.dumps({"scope": "actual-source-graph-and-telemetry-only-projection-not-full-root-runtime",
                                        "source_sha": diagnostic.DIAGNOSTIC_SOURCE_SHA,
                                        "wiring": records, "graph_sha256": hashlib.sha256(graph.encode()).hexdigest(),
                                        "cases": [enabled, disabled, escape]}, indent=2) + "\n")


if __name__ == "__main__":
    if os.name != "posix":
        raise SystemExit("Linux required.")
    unittest.main()

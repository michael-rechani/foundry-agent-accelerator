"""Offline source/configuration bundles; only the deploy subcommand calls Azure."""

import argparse
import hashlib
import io
import json
import re
import runpy
import stat
import sys
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlparse
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile, ZipInfo

from deployment import AgentProfile, create_package, deploy, parse_args


HERE = Path(__file__).resolve().parent
SAMPLES = ("basic-responses-agent", "application-review-agent", "case-review-agent", "review-coordinator-agent")
MAX_BYTES = 2 * 1024 * 1024
MAX_FILE_BYTES = 256 * 1024
NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_-]{0,63}")
MODEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
SHA256 = re.compile(r"[a-f0-9]{64}")
FIELDS = {
    "schema_version", "kind", "name", "description", "instructions", "model",
    "runtime", "cpu", "memory", "environment", "smoke_test_prompt",
    "delegation_checks", "code_sha256", "files",
}


def digest(content):
    return hashlib.sha256(content).hexdigest()


def json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON field: {key}")
        result[key] = value
    return result


def read_json(content):
    return json.loads(content, object_pairs_hook=json_object)


def read_bounded(path):
    with path.open("rb") as source:
        content = source.read(MAX_BYTES + 1)
    if len(content) > MAX_BYTES:
        raise ValueError("Input exceeds the 2 MiB bundle limit")
    return content


def zip_contents(content, *, max_file_bytes=MAX_FILE_BYTES):
    if len(content) > MAX_BYTES:
        raise ValueError("Archive exceeds the 2 MiB bundle limit")
    with ZipFile(io.BytesIO(content)) as archive:
        entries = archive.infolist()
        names = [entry.filename for entry in entries]
        if len(entries) > 5 or len(set(names)) != len(names):
            raise ValueError("Archive has duplicate or excessive entries")
        if sum(entry.file_size for entry in entries) > MAX_BYTES:
            raise ValueError("Expanded archive exceeds the 2 MiB bundle limit")
        for entry in entries:
            if (not re.fullmatch(r"[A-Za-z0-9_.-]+", entry.filename)
                    or entry.file_size > max_file_bytes
                    or entry.flag_bits & 1
                    or entry.compress_type not in (0, ZIP_DEFLATED)
                    or not stat.S_ISREG(entry.external_attr >> 16)):
                raise ValueError("Archive contains an unsupported path, file type, or size")
        return {entry.filename: archive.read(entry) for entry in entries}


def zip_bytes(files):
    output = io.BytesIO()
    with ZipFile(output, "w") as archive:
        for name, content in files.items():
            info = ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, content)
    return output.getvalue()


def nonempty(value, maximum=32768):
    return isinstance(value, str) and 0 < len(value.strip()) <= maximum


def validate_fields(manifest):
    if not isinstance(manifest, dict) or set(manifest) != FIELDS:
        raise ValueError("Bundle manifest has missing or unknown fields")
    if type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1:
        raise ValueError("Unsupported bundle schema version")
    if manifest["kind"] not in ("prebuilt", "lab-created"):
        raise ValueError("Unsupported bundle kind")
    if not isinstance(manifest["name"], str) or not NAME.fullmatch(manifest["name"]):
        raise ValueError("Invalid bundled agent name")
    if any(not nonempty(manifest[key]) for key in ("description", "instructions")):
        raise ValueError("Description and instructions must be nonempty and bounded")
    model = manifest["model"]
    if model is not None and (not isinstance(model, str) or not MODEL.fullmatch(model)):
        raise ValueError("Invalid source model deployment name")
    if (manifest["runtime"] != "python_3_14"
            or not isinstance(manifest["cpu"], str)
            or {"0.5": "1Gi", "1": "2Gi", "2": "4Gi"}.get(manifest["cpu"]) != manifest["memory"]):
        raise ValueError("Unsupported runtime or CPU/memory allocation")
    if not isinstance(manifest["smoke_test_prompt"], str) or len(manifest["smoke_test_prompt"]) > 32768:
        raise ValueError("Invalid smoke-test prompt")


def validate_archive(manifest, code):
    if not isinstance(manifest["code_sha256"], str) or manifest["code_sha256"] != digest(code):
        raise ValueError("Runtime archive hash does not match the manifest")
    files = zip_contents(code)
    required = {"main.py", "requirements.txt"}
    allowed = required | {"instructions.md", "configuration.py", "review_output.py"}
    if manifest["kind"] == "lab-created":
        required = allowed = required | {"demo_tools.py"}
    if not required <= files.keys() <= allowed:
        raise ValueError("Runtime archive has missing or unsupported files")
    if manifest["files"] != {name: digest(content) for name, content in files.items()}:
        raise ValueError("Source/dependency hashes do not match the manifest")
    return files


def validate_lab_environment(manifest, environment, checks):
    if (set(environment) != {"DEMO_TEMPLATE_ID"} or checks
            or not isinstance(environment["DEMO_TEMPLATE_ID"], str)
            or not re.fullmatch(r"[a-z][a-z-]{0,63}", environment["DEMO_TEMPLATE_ID"])):
        raise ValueError("Lab bundles require one template ID and no specialist bindings")
    if not 10 <= len(manifest["instructions"].strip()) <= 6000:
        raise ValueError("Lab instructions must contain 10 to 6000 characters")
    if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", manifest["name"]):
        raise ValueError("Invalid Lab runtime name")


def specialist_bindings(manifest, environment):
    if set(environment) != {"SPECIALIST_CONFIG"} or not isinstance(environment["SPECIALIST_CONFIG"], str):
        raise ValueError("Only reviewed specialist configuration may travel with a prebuilt bundle")
    specialists = read_json(environment["SPECIALIST_CONFIG"])
    if not isinstance(specialists, list) or not 1 <= len(specialists) <= 16:
        raise ValueError("Invalid specialist registry")
    bindings = {}
    for specialist in specialists:
        if not isinstance(specialist, dict) or set(specialist) != {"tool", "agent", "description"}:
            raise ValueError("Invalid specialist binding")
        if any(not isinstance(specialist[key], str) or not NAME.fullmatch(specialist[key])
               for key in ("tool", "agent")) or not nonempty(specialist["description"]):
            raise ValueError("Invalid specialist name or description")
        if specialist["tool"] in bindings or specialist["agent"] == manifest["name"]:
            raise ValueError("Duplicate tool or self-delegation")
        bindings[specialist["tool"]] = specialist["agent"]
    return bindings


def validate_delegation(manifest, environment, checks, files):
    bindings = specialist_bindings(manifest, environment)
    covered = set()
    for check in checks:
        if (not isinstance(check, list) or len(check) != 3 or not nonempty(check[0])
                or not isinstance(check[1], str) or bindings.get(check[1]) != check[2]):
            raise ValueError("Delegation checks must match the bundled specialists")
        covered.add(check[1])
    if covered != set(bindings) or "configuration.py" not in files:
        raise ValueError("Every bundled specialist requires its runtime configuration and a check")


def validate_manifest(manifest, code):
    validate_fields(manifest)
    files = validate_archive(manifest, code)
    environment = manifest["environment"]
    checks = manifest["delegation_checks"]
    if not isinstance(environment, dict) or not isinstance(checks, list):
        raise ValueError("Invalid environment or delegation checks")
    if manifest["kind"] == "lab-created":
        validate_lab_environment(manifest, environment, checks)
    elif environment:
        validate_delegation(manifest, environment, checks, files)
    elif checks:
        raise ValueError("Delegation checks require explicit specialist bindings")
    return manifest


def make_bundle(profile, code, *, kind="prebuilt", model=None, cpu="0.5", memory="1Gi"):
    manifest = {
        "schema_version": 1, "kind": kind, "name": profile.name,
        "description": profile.description, "instructions": profile.instructions, "model": model,
        "runtime": "python_3_14", "cpu": cpu, "memory": memory,
        "environment": dict(profile.environment_variables),
        "smoke_test_prompt": profile.smoke_test_prompt,
        "delegation_checks": [list(check) for check in profile.delegation_checks],
        "code_sha256": digest(code),
        "files": {name: digest(content) for name, content in zip_contents(code).items()},
    }
    validate_manifest(manifest, code)
    content = zip_bytes({
        "manifest.json": json.dumps(manifest, sort_keys=True, indent=2).encode("utf-8"),
        "agent.zip": code,
    })
    zip_contents(content, max_file_bytes=MAX_BYTES)
    return content


def read_bundle(path):
    content = read_bounded(path)
    files = zip_contents(content, max_file_bytes=MAX_BYTES)
    if set(files) != {"manifest.json", "agent.zip"}:
        raise ValueError("A bundle must contain only manifest.json and agent.zip")
    manifest = validate_manifest(read_json(files["manifest.json"]), files["agent.zip"])
    return manifest, files["agent.zip"], digest(content)


def export_sample(sample, profile_path=None, instructions_path=None, **options):
    if sample not in SAMPLES:
        raise ValueError("Select a repository sample")
    if profile_path is not None and sample != "review-coordinator-agent":
        raise ValueError("Profiles apply only to the review coordinator")
    if profile_path is not None and instructions_path is not None:
        raise ValueError("Set instructions in the coordinator profile")
    source = HERE / sample
    previous_path = sys.path[:]
    try:
        sys.path.insert(0, str(source))
        module = runpy.run_path(str(source / "deploy.py"))
        profile = module["profile_from_file"](profile_path) if profile_path else module["default_profile"]()
    finally:
        sys.path[:] = previous_path
    if instructions_path is not None:
        profile = replace(profile, instructions=read_bounded(instructions_path).decode("utf-8-sig"))
    output = io.BytesIO()
    create_package(source, output)
    return make_bundle(profile, output.getvalue(), **options)


def export_created(record_path, runtime_directory=None):
    record = read_json(read_bounded(record_path))
    if not isinstance(record, dict) or record.get("status") != "ready":
        raise ValueError("Export requires a ready saved Lab agent record")
    required = {"runtime_name", "instructions", "template_id", "model", "runtime_hash"}
    if not required <= record.keys() or not isinstance(record["runtime_hash"], str):
        raise ValueError("Saved record is missing its configuration or runtime_hash; refresh it from the Lab")
    if not SHA256.fullmatch(record["runtime_hash"]):
        raise ValueError("Invalid saved runtime hash")
    previous_path = sys.path[:]
    try:
        sys.path.insert(0, str(HERE.parent / "workbench"))
        from agent_package import RUNTIME_DIRECTORY, runtime_package
        code, runtime_hash = runtime_package(runtime_directory or RUNTIME_DIRECTORY)
    finally:
        sys.path[:] = previous_path
    if runtime_hash != record["runtime_hash"]:
        raise ValueError("Runtime changed: supply the original runtime source; exporting newer code is not a backup")
    profile = AgentProfile(
        HERE, record["runtime_name"], "Portable Lab demonstration agent",
        record["instructions"], "",
        environment_variables=(("DEMO_TEMPLATE_ID", record["template_id"]),),
    )
    return make_bundle(profile, code, kind="lab-created", model=record["model"])


def deployment_profile(manifest, code, name, mappings):
    manifest = deepcopy(manifest)
    manifest["name"] = name
    mapping = {}
    for item in mappings:
        old, separator, new = item.partition("=")
        if not separator or not NAME.fullmatch(old) or not NAME.fullmatch(new) or old in mapping:
            raise ValueError("Use distinct --specialist OLD=NEW mappings")
        mapping[old] = new
    environment = manifest["environment"]
    if mapping:
        if "SPECIALIST_CONFIG" not in environment:
            raise ValueError("This bundle has no specialists to remap")
        specialists = read_json(environment["SPECIALIST_CONFIG"])
        if mapping.keys() - {item["agent"] for item in specialists}:
            raise ValueError("A specialist mapping names an agent absent from the bundle")
        for specialist in specialists:
            specialist["agent"] = mapping.get(specialist["agent"], specialist["agent"])
        environment["SPECIALIST_CONFIG"] = json.dumps(specialists)
        for check in manifest["delegation_checks"]:
            check[2] = mapping.get(check[2], check[2])
    validate_manifest(manifest, code)
    return AgentProfile(
        HERE, name, manifest["description"], manifest["instructions"],
        manifest["smoke_test_prompt"],
        tuple(tuple(check) for check in manifest["delegation_checks"]),
        tuple(environment.items()), code,
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)
    source = commands.add_parser("export", allow_abbrev=False, help="Export reviewed repository source, not live overrides")
    source.add_argument("--sample", choices=SAMPLES, required=True)
    source.add_argument("--profile", type=Path)
    source.add_argument("--instructions-file", type=Path)
    source.add_argument("--model", help="Record a source model name; deployment still requires an explicit target model")
    source.add_argument("--cpu", default="0.5")
    source.add_argument("--memory", default="1Gi")
    source.add_argument("--output", type=Path, required=True)
    created = commands.add_parser("export-created", allow_abbrev=False, help="Export a saved Lab record with matching runtime source")
    created.add_argument("--record", type=Path, required=True)
    created.add_argument("--runtime-directory", type=Path)
    created.add_argument("--output", type=Path, required=True)
    inspect = commands.add_parser("inspect", allow_abbrev=False)
    inspect.add_argument("bundle", type=Path)
    publish = commands.add_parser("deploy", allow_abbrev=False, help="Create a billable version and promote its route")
    publish.add_argument("bundle", type=Path)
    publish.add_argument("--endpoint", required=True)
    publish.add_argument("--model", required=True)
    publish.add_argument("--agent-name", required=True, help="Explicit destination agent name; an existing name is updated")
    publish.add_argument("--specialist", action="append", default=[], metavar="OLD=NEW")
    publish.add_argument("--poll-seconds", type=int, default=10)
    publish.add_argument("--max-polls", type=int, default=120)
    args = parser.parse_args(argv)
    try:
        if args.command in ("export", "export-created"):
            if args.command == "export":
                content = export_sample(
                    args.sample, args.profile, args.instructions_file,
                    model=args.model, cpu=args.cpu, memory=args.memory,
                )
            else:
                content = export_created(args.record, args.runtime_directory)
            with args.output.open("xb") as output:
                output.write(content)
            print(f"Exported {args.output}; SHA-256 {digest(content)}")
            return
        manifest, code, bundle_hash = read_bundle(args.bundle)
        if args.command == "inspect":
            print(json.dumps({
                "schema_version": manifest["schema_version"], "kind": manifest["kind"],
                "name": manifest["name"], "source_model": manifest["model"],
                "runtime": manifest["runtime"], "cpu": manifest["cpu"], "memory": manifest["memory"],
                "files": manifest["files"], "code_sha256": manifest["code_sha256"],
                "bundle_sha256": bundle_hash,
                "specialists": sorted({check[2] for check in manifest["delegation_checks"]}),
            }, indent=2))
            return
        endpoint = urlparse(args.endpoint)
        if (endpoint.scheme != "https" or not (endpoint.hostname or "").endswith(".services.ai.azure.com")
                or endpoint.username or endpoint.port not in (None, 443) or endpoint.query or endpoint.fragment
                or not re.fullmatch(r"/api/projects/[A-Za-z0-9_-]+", endpoint.path)):
            raise ValueError("Supply the verified destination Foundry HTTPS project endpoint")
        if not MODEL.fullmatch(args.model):
            raise ValueError("Invalid destination model deployment name")
        profile = deployment_profile(manifest, code, args.agent_name, args.specialist)
        options = parse_args(profile, [
            "--endpoint", args.endpoint, "--model", args.model, "--agent-name", args.agent_name,
            "--cpu", manifest["cpu"], "--memory", manifest["memory"], "--runtime", manifest["runtime"],
            "--poll-seconds", str(args.poll_seconds), "--max-polls", str(args.max_polls),
        ])
        deploy(profile, options)
    except (OSError, ValueError, BadZipFile) as error:
        parser.exit(1, f"Bundle operation failed: {error}\n")


if __name__ == "__main__":
    main()

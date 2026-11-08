"""Prepare and verify exact-comment reviews for a staged hosted-agent release.

Live publication is deliberately disabled pending separately reviewed identity,
host, dependency-provenance and workflow activation prerequisites.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import replace
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import HTTPRedirectHandler, Request, build_opener

LIVE_PUBLICATION_ENABLED = False
WORKFLOW = ".github/workflows/publish-profiled-agents.yml"
ENVIRONMENTS = {
    "prepare": "agent-release-preparation",
    "application": "agent-release-application",
    "case": "agent-release-case",
    "coordinator": "agent-release-coordinator",
}
STEPS = ("application", "case", "coordinator")
TARGETS = ("application-review-agent", "case-review-agent", "customer-review-coordinator")
PACKAGE_DIRECTORIES = ("application-review-agent", "case-review-agent", "review-coordinator-agent")
PACKAGE_FILES = ("main.py", "requirements.txt", "instructions.md", "configuration.py")
PACKAGE_SHARED_FILES = ("review_output.py", "hosted_runtime.py")
JOBS = {"prepare": "prepare", **{step: f"publish-{step}" for step in STEPS}}
SHA = re.compile(r"[0-9a-f]{40}")
DIGEST = re.compile(r"[0-9a-f]{64}")
UUID = re.compile(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}")
INPUT_KEYS = {
    "release_id", "endpoint", "model", "credential_mode", "client_id", "tenant_id",
    "profile_path", "profile_sha256", "targets", "cpu", "memory", "runtime",
    "model_choice",
}


class ReleaseError(RuntimeError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        raise ReleaseError("GitHub metadata redirects are not permitted")


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def digest(value) -> str:
    return hashlib.sha256(canonical(value).encode("ascii")).hexdigest()


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ReleaseError("Duplicate JSON field in release data")
        result[key] = value
    return result


def document(value: str):
    try:
        return json.loads(value, object_pairs_hook=unique_object)
    except (ValueError, TypeError) as error:
        raise ReleaseError("Invalid release JSON") from error


class GitHub:
    def __init__(self, repository: str, token: str):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) or not token:
            raise ReleaseError("Authenticated GitHub review metadata access is required")
        self.repository = repository
        self.token = token

    def get(self, suffix: str):
        request = Request(
            f"https://api.github.com/repos/{self.repository}{suffix}",
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with build_opener(NoRedirect()).open(request, timeout=30) as response:
                return document(response.read().decode("utf-8"))
        except HTTPError as error:
            try:
                error.close()
            except OSError:
                raise ReleaseError("GitHub metadata error response could not be closed") from None
            raise ReleaseError(f"GitHub metadata request failed with HTTP {error.code}") from None
        except (URLError, UnicodeError) as error:
            raise ReleaseError("GitHub metadata could not be verified") from error


def context(environ):
    source = environ.get("REVIEWED_SOURCE_SHA", "")
    run_id = environ.get("GITHUB_RUN_ID", "")
    if (
        environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch"
        or environ.get("GITHUB_REF") != "refs/heads/main"
        or environ.get("GITHUB_REF_PROTECTED") != "true"
        or environ.get("GITHUB_RUN_ATTEMPT") != "1"
        or not SHA.fullmatch(source)
        or environ.get("GITHUB_SHA") != source
        or environ.get("RELEASE_WORKFLOW_SHA") != source
        or not re.fullmatch(r"[1-9][0-9]*", run_id)
        or environ.get("GITHUB_WORKFLOW_REF") != f"{environ.get('GITHUB_REPOSITORY')}/{WORKFLOW}@refs/heads/main"
    ):
        raise ReleaseError("A fresh reviewed protected-main dispatch and matching workflow source are required")
    return {"repository": environ["GITHUB_REPOSITORY"], "source_sha": source, "run_id": run_id, "attempt": 1}


def environment_policy(value, name, owner_id):
    if not isinstance(value, dict) or type(value.get("id")) is not int or value["id"] <= 0:
        raise ReleaseError("Required environment is missing or ambiguous")
    rules = value.get("protection_rules")
    reviewers = [rule for rule in rules if isinstance(rule, dict) and rule.get("type") == "required_reviewers"] if isinstance(rules, list) else []
    if (
        value.get("name") != name
        or value.get("can_admins_bypass") is not False
        or value.get("deployment_branch_policy") != {"protected_branches": True, "custom_branch_policies": False}
        or len(reviewers) != 1
        or type(reviewers[0].get("prevent_self_review")) is not bool
        or reviewers[0].get("reviewers") != [{"type": "User", "reviewer": {"id": owner_id}}]
    ):
        # The API supplies a full user object; normalize it before this comparison.
        raise ReleaseError("Existing required-reviewer, no-bypass and protected-branch policy is not verified")
    return {
        "id": value["id"], "name": name, "owner_id": owner_id,
        "can_admins_bypass": False,
        "deployment_branch_policy": value["deployment_branch_policy"],
        "protection_rules": rules,
    }


def policies(api, ctx):
    repository = api.get("")
    branch = api.get("/branches/main")
    if not isinstance(repository, dict) or not isinstance(repository.get("owner"), dict) or not isinstance(branch, dict) or not isinstance(branch.get("commit"), dict):
        raise ReleaseError("Malformed repository or branch metadata")
    owner_id = repository["owner"].get("id")
    if type(owner_id) is not int or owner_id <= 0 or branch.get("protected") is not True or branch.get("commit", {}).get("sha") != ctx["source_sha"]:
        raise ReleaseError("Current protected main and repository owner could not be verified")
    run = api.get(f"/actions/runs/{ctx['run_id']}")
    if (
        not isinstance(run, dict) or type(run.get("run_attempt")) is not int
        or run.get("run_attempt") != 1 or run.get("head_sha") != ctx["source_sha"]
        or run.get("head_branch") != "main" or run.get("event") != "workflow_dispatch"
        or not isinstance(run.get("path"), str) or run["path"].split("@", 1)[0] != WORKFLOW
    ):
        raise ReleaseError("Authenticated workflow run does not match the release context")
    result = {}
    for step, name in ENVIRONMENTS.items():
        suffix = f"/environments/{quote(name, safe='')}"
        raw = api.get(suffix)
        if not isinstance(raw, dict) or not isinstance(raw.get("protection_rules"), list):
            raise ReleaseError("Required environment or protection metadata is missing")
        if any(not isinstance(rule, dict) or not isinstance(rule.get("type"), str) for rule in raw["protection_rules"]):
            raise ReleaseError("Malformed environment protection rules")
        value = document(canonical(raw))
        for rule in value.get("protection_rules", []):
            if isinstance(rule, dict) and rule.get("type") == "required_reviewers":
                entries = rule.get("reviewers")
                if isinstance(entries, list):
                    if any(not isinstance(item, dict) or not isinstance(item.get("reviewer"), dict) for item in entries):
                        raise ReleaseError("Ambiguous environment reviewers")
                    rule["reviewers"] = [
                        {"type": item.get("type"), "reviewer": {"id": item["reviewer"].get("id")}}
                        for item in entries
                    ]
                    if len(rule["reviewers"]) != len(entries):
                        raise ReleaseError("Ambiguous environment reviewers")
        result[step] = environment_policy(value, name, owner_id)
        secrets = api.get(f"{suffix}/secrets?per_page=100")
        if (
            not isinstance(secrets, dict) or type(secrets.get("total_count")) is not int
            or not 0 <= secrets["total_count"] <= 100 or not isinstance(secrets.get("secrets"), list)
            or len(secrets["secrets"]) != secrets["total_count"]
            or len([item for item in secrets["secrets"] if isinstance(item, dict) and item.get("name") == "AGENT_RELEASE_INPUTS"]) != 1
        ):
            raise ReleaseError("Required protected release-input secret is missing or cannot be inventoried")
    if len({item["id"] for item in result.values()}) != len(ENVIRONMENTS):
        raise ReleaseError("Release environments must have distinct IDs")
    return result


def inputs(environ):
    value = document(environ.get("AGENT_RELEASE_INPUTS", ""))
    if not isinstance(value, dict) or set(value) != INPUT_KEYS:
        raise ReleaseError("Protected release inputs require the exact documented schema")
    if (
        not all(isinstance(value[key], str) and value[key] for key in INPUT_KEYS - {"targets"})
        or not UUID.fullmatch(value["release_id"]) or not UUID.fullmatch(value["client_id"])
        or not UUID.fullmatch(value["tenant_id"])
        or value["credential_mode"] not in ("ManagedIdentityCredential", "WorkloadIdentityCredential")
        or not re.fullmatch(r"https://[A-Za-z0-9.-]+/api/projects/[A-Za-z0-9_-]+", value["endpoint"])
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", value["model"])
        or not DIGEST.fullmatch(value["profile_sha256"])
        or value["targets"] != list(TARGETS)
        or value["model_choice"] not in ("router", "fixed_recovery")
        or environ.get("RELEASE_MODEL_CHOICE") != value["model_choice"]
        or environ.get("REVIEWED_MODEL_SHA256") != digest(value["model"])
        or value["runtime"] != "python_3_14"
        or value["memory"] != "1Gi" or value["cpu"] != "0.5"
    ):
        raise ReleaseError("Protected endpoint, model, identity, profile or release inputs are invalid")
    return value


def checkout(root, source):
    package_paths = [
        f"hosted-agents/{directory}/{filename}"
        for directory in PACKAGE_DIRECTORIES for filename in PACKAGE_FILES
    ] + [f"hosted-agents/{filename}" for filename in PACKAGE_SHARED_FILES]
    commands = (
        (["rev-parse", "HEAD"], source),
        (["status", "--porcelain", "--untracked-files=all"], ""),
        (["ls-files", "--others", "--ignored", "--exclude-standard", "--", *package_paths], ""),
    )
    git_environment = {
        "PATH": "/usr/bin:/bin",
        "LC_ALL": "C",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_OPTIONAL_LOCKS": "0",
    }
    for arguments, expected in commands:
        try:
            result = subprocess.run(  # noqa: S603 - fixed Git commands use an absolute executable and no shell.
                ["/usr/bin/git", "-c", "core.fsmonitor=false", "-C", str(root), *arguments],
                capture_output=True, text=True, check=False, env=git_environment, timeout=15,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ReleaseError("Release checkout could not be verified") from error
        if result.returncode != 0 or result.stdout.strip() != expected:
            raise ReleaseError("Release checkout does not match the reviewed clean source")


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ReleaseError("Release profile module is unavailable")
    loaded = importlib.util.module_from_spec(spec)
    previous_path = sys.path[:]
    sys.path.insert(0, str(path.parent))
    try:
        spec.loader.exec_module(loaded)
    except ImportError:
        raise ReleaseError("Release profile dependencies are unavailable") from None
    finally:
        sys.path[:] = previous_path
    return loaded


def release_plan(root, ctx, values, policy):
    if "FOUNDRY_HOSTED_AGENT_NAME" in os.environ or os.getenv("KNOWLEDGE_RETRIEVAL_ENABLED") not in (None, "false"):
        raise ReleaseError("Profile name overrides and knowledge-retrieval opt-ins are not part of this release")
    source = root / "hosted-agents"
    sys.path.insert(0, str(source))
    import deployment

    if (*deployment.SOURCE_FILES, *deployment.OPTIONAL_SOURCE_FILES) != PACKAGE_FILES or (
        deployment.SHARED_FILES != PACKAGE_SHARED_FILES
    ):
        raise ReleaseError("Release package source list changed and requires review")
    relative = Path(values["profile_path"])
    profile_path = (root / relative).resolve()
    if relative.is_absolute() or profile_path == root or root not in profile_path.parents:
        raise ReleaseError("Profile must be an explicit repository-relative file")
    application = module(source / "application-review-agent/deploy.py", "release_application").default_profile()
    case = module(source / "case-review-agent/deploy.py", "release_case").default_profile()
    coordinator = module(source / "review-coordinator-agent/deploy.py", "release_coordinator").profile_from_file(
        profile_path, values["profile_sha256"],
    )
    profiles = (application, case, coordinator)
    if tuple(profile.name for profile in profiles) != TARGETS:
        raise ReleaseError("Release profile targets do not match the reviewed publication order")
    if tuple(profile.source_directory for profile in profiles) != tuple(
        source / directory for directory in PACKAGE_DIRECTORIES
    ):
        raise ReleaseError("Release profile source directories changed and require review")
    packed = []
    descriptors = []
    with tempfile.TemporaryDirectory(prefix="agent-release-review-") as temporary:
        for index, profile in enumerate(profiles):
            archive = Path(temporary) / f"{index}.zip"
            deployment.create_package(profile.source_directory, archive)
            content = archive.read_bytes()
            packed.append(replace(profile, code_archive=content))
            descriptors.append({
                "stage": STEPS[index], "target": profile.name,
                "archive_sha256": hashlib.sha256(content).hexdigest(),
                "instructions_sha256": hashlib.sha256(profile.instructions.encode("utf-8")).hexdigest(),
                "environment_variables": list(profile.environment_variables),
                "delegation_checks": list(profile.delegation_checks),
            })
    manifest = {**ctx, "release_inputs": values, "environments": policy, "profiles": descriptors}
    return manifest, packed


def approval_comment(step, ctx, manifest_digest):
    return f"publish {step} run {ctx['run_id']} source {ctx['source_sha']} manifest {manifest_digest}"


def verify_review(api, step, ctx, policy, manifest_digest):
    reviews = api.get(f"/actions/runs/{ctx['run_id']}/approvals")
    if not isinstance(reviews, list):
        raise ReleaseError("Approval history is unavailable")
    expected = policy[step]
    matching = []
    for review in reviews:
        if not isinstance(review, dict) or not isinstance(review.get("environments"), list):
            raise ReleaseError("Malformed approval history")
        if any(not isinstance(env, dict) for env in review["environments"]):
            raise ReleaseError("Malformed approval environment")
        if any(isinstance(env, dict) and env.get("id") == expected["id"] for env in review["environments"]):
            matching.append(review)
    if (
        len(matching) != 1 or matching[0].get("state") != "approved"
        or not isinstance(matching[0].get("user"), dict)
        or type(matching[0]["user"].get("id")) is not int
        or matching[0]["user"].get("id") != expected["owner_id"]
        or matching[0].get("comment") != approval_comment(step, ctx, manifest_digest)
        or [{"id": env.get("id"), "name": env.get("name")} for env in matching[0]["environments"]] != [{"id": expected["id"], "name": expected["name"]}]
    ):
        raise ReleaseError("One exact authenticated stage/source/manifest review is required")


def verify_predecessors(api, step, ctx):
    jobs = api.get(f"/actions/runs/{ctx['run_id']}/attempts/1/jobs?per_page=100")
    if (
        not isinstance(jobs, dict) or type(jobs.get("total_count")) is not int
        or not 0 <= jobs["total_count"] <= 100 or not isinstance(jobs.get("jobs"), list)
        or len(jobs["jobs"]) != jobs["total_count"]
        or any(not isinstance(job, dict) for job in jobs["jobs"])
    ):
        raise ReleaseError("Attempt-specific job history is unavailable")
    required = ("prepare", *STEPS[:STEPS.index(step)])
    for name in required:
        matches = [job for job in jobs["jobs"] if isinstance(job, dict) and job.get("name") == JOBS[name]]
        if len(matches) != 1 or matches[0].get("status") != "completed" or matches[0].get("conclusion") != "success":
            raise ReleaseError("Successful sequential publication predecessors are required")
    current = [job for job in jobs["jobs"] if isinstance(job, dict) and job.get("name") == JOBS[step]]
    if len(current) != 1 or current[0].get("status") != "in_progress":
        raise ReleaseError("Exactly one active publication job is required")


def output(environ, key, value):
    path = environ.get("GITHUB_OUTPUT")
    if not path:
        raise ReleaseError("GitHub job output channel is unavailable")
    with Path(path).open("a", encoding="utf-8") as destination:
        destination.write(f"{key}={value}\n")


def main(argv=None, environ=None, *, api=None, root=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("operation", choices=("preflight", "prepare", "publish"))
    parser.add_argument("--step", choices=STEPS)
    args = parser.parse_args(argv)
    environ = os.environ if environ is None else environ
    root = Path(__file__).resolve().parents[2] if root is None else Path(root).resolve()
    saved = {key: os.environ.get(key) for key in ("AZURE_TOKEN_CREDENTIALS", "AZURE_CLIENT_ID", "AZURE_TENANT_ID")}
    try:
        ctx = context(environ)
        api = GitHub(ctx["repository"], environ.get("AGENT_RELEASE_REVIEW_TOKEN", "")) if api is None else api
        current = policies(api, ctx)
        if args.operation == "preflight":
            output(environ, "policy", canonical(current))
            for step, name in ENVIRONMENTS.items():
                output(environ, f"{step}_environment", name)
            return 0
        baseline = document(environ.get("RELEASE_ENVIRONMENT_POLICY", ""))
        if current != baseline:
            raise ReleaseError("Environment IDs or current protection policy changed")
        checkout(root, ctx["source_sha"])
        values = inputs(environ)
        manifest, profiles = release_plan(root, ctx, values, current)
        reviewed_digest = digest(manifest)
        if args.operation == "prepare":
            output(environ, "manifest_digest", reviewed_digest)
            summary = environ.get("GITHUB_STEP_SUMMARY")
            if not summary:
                raise ReleaseError("Pre-approval review summary is unavailable")
            with Path(summary).open("a", encoding="utf-8") as destination:
                destination.write(f"## Agent release manifest `{reviewed_digest}`\n\nSource `{ctx['source_sha']}`; run `{ctx['run_id']}`.\n\n")
                destination.write(f"Reviewed choice: `{values['model_choice']}`; exact model label is hash-bound, with no fallback.\n\n")
                for key in ("endpoint", "model", "credential_mode", "client_id", "tenant_id", "release_id"):
                    destination.write(f"- {key} SHA-256: `{digest(values[key])}`\n")
                for step, target in zip(STEPS, TARGETS, strict=True):
                    destination.write(f"\n{target}: approve only its environment, with exact comment:\n\n`{approval_comment(step, ctx, reviewed_digest)}`\n")
                destination.write("\nOwner self-review is permitted if configured; this is not independent review. Live publication remains disabled.\n")
            return 0
        if args.step is None or environ.get("GITHUB_JOB") != JOBS[args.step]:
            raise ReleaseError("A publication job must select exactly its own single stage")
        if environ.get("RELEASE_MANIFEST_DIGEST") != reviewed_digest:
            raise ReleaseError("Actual release inputs or profile bytes differ from the pre-approval manifest")

        def before_mutation():
            fresh_ctx = context(environ)
            fresh_policy = policies(api, fresh_ctx)
            checkout(root, fresh_ctx["source_sha"])
            fresh_values = inputs(environ)
            fresh_manifest, _ = release_plan(root, fresh_ctx, fresh_values, fresh_policy)
            if fresh_ctx != ctx or fresh_policy != baseline or digest(fresh_manifest) != reviewed_digest:
                raise ReleaseError("Reviewed source, policy or release inputs changed")
            verify_predecessors(api, args.step, fresh_ctx)
            verify_review(api, args.step, fresh_ctx, fresh_policy, reviewed_digest)
            for key, field in (("AZURE_TOKEN_CREDENTIALS", "credential_mode"), ("AZURE_CLIENT_ID", "client_id"), ("AZURE_TENANT_ID", "tenant_id")):
                if os.environ.get(key) != fresh_values[field]:
                    raise ReleaseError("Selected publication identity changed")

        for key, field in (("AZURE_TOKEN_CREDENTIALS", "credential_mode"), ("AZURE_CLIENT_ID", "client_id"), ("AZURE_TENANT_ID", "tenant_id")):
            os.environ[key] = values[field]
        before_mutation()
        if not LIVE_PUBLICATION_ENABLED:
            raise ReleaseError("Live publication is disabled pending separately reviewed role/FIC, host, dependency provenance and workflow activation")
        import deployment

        profile = profiles[STEPS.index(args.step)]
        arguments = [
            "--endpoint", values["endpoint"], "--model", values["model"],
            "--credential-mode", values["credential_mode"], "--credential-client-id", values["client_id"],
            "--cpu", values["cpu"], "--memory", values["memory"], "--runtime", values["runtime"],
        ]
        parsed = deployment.parse_args(profile, arguments)
        if parsed.agent_name != profile.name or parsed.instructions != profile.instructions:
            raise ReleaseError("Publication name or instructions override is incompatible")
        # The generic publisher reports resource identities. Keep that output
        # private in memory; Actions receives only a sanitized outcome.
        with io.StringIO() as private_output, redirect_stdout(private_output), redirect_stderr(private_output):
            try:
                deployment.deploy(profile, parsed, before_mutation=before_mutation)
            except Exception:
                raise ReleaseError("Publication failed; inspect version/route status privately before any recovery or retry") from None
        print(f"Reviewed {args.step} publication completed; verify private routed-version and budget metadata separately.")
        return 0
    except (ReleaseError, ValueError, OSError) as error:
        # Avoid including release values or response bodies in Actions logs.
        message = str(error) if isinstance(error, ReleaseError) else "Release inputs/profile/source could not be validated"
        print(f"::error::{message}", file=sys.stderr)
        return 1
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


if __name__ == "__main__":
    raise SystemExit(main())

import hashlib
import io
import json
import os
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from pathlib import Path
from unittest.mock import MagicMock, patch

import reviewed_agent_release as release

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "hosted-agents"))
import deployment


class Metadata:
    def __init__(self, environ):
        self.data = {
            "": {"owner": {"id": 17}},
            "/branches/main": {"protected": True, "commit": {"sha": environ["GITHUB_SHA"]}},
            "/actions/runs/91": {
                "run_attempt": 1, "head_sha": environ["GITHUB_SHA"], "head_branch": "main",
                "event": "workflow_dispatch", "path": release.WORKFLOW,
            },
            "/actions/runs/91/approvals": [],
            "/actions/runs/91/attempts/1/jobs?per_page=100": {"total_count": 4, "jobs": []},
        }
        for index, (_step, name) in enumerate(release.ENVIRONMENTS.items(), 1):
            self.data[f"/environments/{name}"] = {
                "id": index, "name": name, "can_admins_bypass": False,
                "deployment_branch_policy": {"protected_branches": True, "custom_branch_policies": False},
                "protection_rules": [{
                    "id": index + 10, "type": "required_reviewers", "prevent_self_review": False,
                    "reviewers": [{"type": "User", "reviewer": {"id": 17, "login": "fictional-owner"}}],
                }],
            }
            self.data[f"/environments/{name}/secrets?per_page=100"] = {
                "total_count": 1, "secrets": [{"name": "AGENT_RELEASE_INPUTS"}],
            }
        self.calls = []

    def get(self, suffix):
        self.calls.append(suffix)
        if suffix not in self.data:
            raise release.ReleaseError("GitHub metadata request failed with HTTP 404")
        value = self.data[suffix]
        if isinstance(value, Exception):
            raise value
        return deepcopy(value)


class Node(dict):
    def __getattr__(self, key):
        return self.get(key)

    def __setattr__(self, key, value):
        self[key] = value


class FixedRule(Node):
    def __init__(self, **values):
        super().__init__(type="FixedRatio", **values)


def external_sdk(model, mutations):
    """Fictional external SDK only; real packaging/promotion/recovery stays intact."""
    client = MagicMock()
    client.__enter__.return_value = client
    routes = {}

    def endpoint(name):
        return routes.setdefault(name, Node(
            version_selector=Node(version_selection_rules=[
                FixedRule(agent_version="1", traffic_percentage=100),
            ]),
            protocol_configuration=Node(responses=Node()),
        ))

    client.agents.get.side_effect = lambda agent_name: Node(
        name=agent_name, state="enabled", configuration_state="enabled", agent_endpoint=endpoint(agent_name),
    )
    client.agents.get_version.side_effect = lambda agent_name, agent_version: {
        "name": agent_name, "version": agent_version, "status": "active", "draft": False,
        "definition": {"kind": "hosted", "environment_variables": {"FOUNDRY_MODEL_NAME": model}},
    }

    def create(**kwargs):
        mutations.append(("create", kwargs["agent_name"]))
        return Node(version="2")

    def update(agent_name, agent_endpoint):
        mutations.append(("route", agent_name))
        routes[agent_name] = deepcopy(agent_endpoint)

    client.agents.create_version_from_code.side_effect = create
    client.agents.update_details.side_effect = update
    models = types.ModuleType("azure.ai.projects.models")
    for name in (
        "AgentEndpointConfig", "CodeConfiguration", "HostedAgentDefinition", "ProtocolConfiguration",
        "ProtocolVersionRecord", "ResponsesProtocolConfiguration", "VersionSelector",
    ):
        setattr(models, name, Node)
    models.FixedRatioVersionSelectionRule = FixedRule
    models.CodeDependencyResolution = types.SimpleNamespace(REMOTE_BUILD="fictional-remote-build")
    projects = types.ModuleType("azure.ai.projects")
    projects.AIProjectClient = MagicMock(return_value=client)
    exceptions = types.ModuleType("azure.core.exceptions")
    exceptions.ResourceNotFoundError = type("ResourceNotFoundError", (Exception,), {})
    modules = {
        "azure": types.ModuleType("azure"), "azure.ai": types.ModuleType("azure.ai"),
        "azure.ai.projects": projects, "azure.ai.projects.models": models,
        "azure.core": types.ModuleType("azure.core"), "azure.core.exceptions": exceptions,
    }
    credential = MagicMock()
    credential.__enter__.return_value = credential
    return modules, client, credential


class ReviewedReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        scratch = Path(self.temporary.name)
        self.environ = {
            "GITHUB_REPOSITORY": "fictional-owner/fictional-repository",
            "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_REF": "refs/heads/main",
            "GITHUB_REF_PROTECTED": "true", "GITHUB_RUN_ATTEMPT": "1", "GITHUB_RUN_ID": "91",
            "GITHUB_SHA": "a" * 40, "REVIEWED_SOURCE_SHA": "a" * 40, "RELEASE_WORKFLOW_SHA": "a" * 40,
            "GITHUB_WORKFLOW_REF": f"fictional-owner/fictional-repository/{release.WORKFLOW}@refs/heads/main",
            "GITHUB_OUTPUT": str(scratch / "output"), "GITHUB_STEP_SUMMARY": str(scratch / "summary"),
            "RELEASE_MODEL_CHOICE": "router", "REVIEWED_MODEL_SHA256": release.digest("fictional-router"),
        }
        self.values = {
            "release_id": "12345678-1234-1234-1234-123456789abc",
            "endpoint": "https://fictional.services.ai.azure.com/api/projects/fictional",
            "model": "fictional-router", "model_choice": "router",
            "credential_mode": "ManagedIdentityCredential",
            "client_id": "22345678-1234-1234-1234-123456789abc",
            "tenant_id": "32345678-1234-1234-1234-123456789abc",
            "profile_path": "hosted-agents/review-coordinator-agent/profiles/evidence-review.example.json",
            "targets": list(release.TARGETS), "cpu": "0.5", "memory": "1Gi", "runtime": "python_3_14",
        }
        self.values["profile_sha256"] = hashlib.sha256((ROOT / self.values["profile_path"]).read_bytes()).hexdigest()
        self.environ["AGENT_RELEASE_INPUTS"] = release.canonical(self.values)
        self.api = Metadata(self.environ)
        self.real_checkout = release.checkout
        self.checkout = patch.object(release, "checkout")
        self.checkout_mock = self.checkout.start()
        self.addCleanup(self.checkout.stop)
        self.published = []

    def invoke(self, operation, step=None):
        stdout, stderr = io.StringIO(), io.StringIO()
        argv = [operation] + (["--step", step] if step else [])
        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = release.main(argv, self.environ, api=self.api, root=ROOT)
        output = stdout.getvalue() + stderr.getvalue()
        for sensitive in ("endpoint", "model", "client_id", "tenant_id", "release_id"):
            self.assertNotIn(self.values[sensitive], output)
        return result, output

    def prepare(self):
        self.assertEqual(0, self.invoke("preflight")[0])
        self.environ["RELEASE_ENVIRONMENT_POLICY"] = release.canonical(
            release.policies(self.api, release.context(self.environ)),
        )
        self.assertEqual(0, self.invoke("prepare")[0])
        ctx = release.context(self.environ)
        manifest, _ = release.release_plan(ROOT, ctx, release.inputs(self.environ), json.loads(self.environ["RELEASE_ENVIRONMENT_POLICY"]))
        self.environ["RELEASE_MANIFEST_DIGEST"] = release.digest(manifest)
        return ctx

    def approve(self, step, ctx):
        policy = json.loads(self.environ["RELEASE_ENVIRONMENT_POLICY"])[step]
        self.environ["GITHUB_JOB"] = release.JOBS[step]
        self.api.data["/actions/runs/91/approvals"] = [{
            "environments": [{"id": policy["id"], "name": policy["name"], "url": "https://api.github.com/fictional"}],
            "state": "approved", "user": {"id": 17},
            "comment": release.approval_comment(step, ctx, self.environ["RELEASE_MANIFEST_DIGEST"]),
        }]
        self.api.data["/actions/runs/91/attempts/1/jobs?per_page=100"]["jobs"] = [
            {"name": release.JOBS[name], "status": "completed", "conclusion": "success"}
            for name in ("prepare", *release.STEPS[:release.STEPS.index(step)])
        ] + [{"name": release.JOBS[step], "status": "in_progress"}]
        self.api.data["/actions/runs/91/attempts/1/jobs?per_page=100"]["total_count"] = len(
            self.api.data["/actions/runs/91/attempts/1/jobs?per_page=100"]["jobs"],
        )

    def test_preparation_uses_actual_profile_and_only_hashed_private_values(self):
        self.prepare()
        summary = Path(self.environ["GITHUB_STEP_SUMMARY"]).read_text()
        for value in (self.values["endpoint"], self.values["model"], self.values["client_id"], self.values["tenant_id"]):
            self.assertNotIn(value, summary)
        for step in release.STEPS:
            self.assertIn(release.approval_comment(step, release.context(self.environ), self.environ["RELEASE_MANIFEST_DIGEST"]), summary)
        self.assertIn("not independent review", summary)
        _, profiles = release.release_plan(ROOT, release.context(self.environ), self.values, json.loads(self.environ["RELEASE_ENVIRONMENT_POLICY"]))
        self.assertEqual(release.TARGETS, tuple(profile.name for profile in profiles))
        registry = json.loads(dict(profiles[2].environment_variables)["SPECIALIST_CONFIG"])
        from configuration import validate_specialists
        self.assertEqual(registry, validate_specialists(registry))
        self.assertEqual(
            [("inspect_application", "application-review-agent"), ("inspect_case", "case-review-agent")],
            [(item["tool"], item["agent"]) for item in registry],
        )

    def test_missing_or_unprotected_environment_or_secret_prevents_preparation(self):
        name = release.ENVIRONMENTS["application"]
        original = deepcopy(self.api.data)
        for change in ("missing", "reviewers", "bypass", "self-field", "branch", "secret", "permission"):
            with self.subTest(change=change):
                self.api.data = deepcopy(original)
                item = self.api.data[f"/environments/{name}"]
                if change == "missing":
                    del self.api.data[f"/environments/{name}"]
                elif change == "reviewers":
                    item["protection_rules"] = []
                elif change == "bypass":
                    item["can_admins_bypass"] = True
                elif change == "self-field":
                    del item["protection_rules"][0]["prevent_self_review"]
                elif change == "branch":
                    item["deployment_branch_policy"] = None
                elif change == "secret":
                    self.api.data[f"/environments/{name}/secrets?per_page=100"] = {"total_count": 0, "secrets": []}
                else:
                    self.api.data[f"/environments/{name}/secrets?per_page=100"] = release.ReleaseError("GitHub metadata request failed with HTTP 403")
                self.assertEqual(1, self.invoke("preflight")[0])
        self.checkout_mock.assert_not_called()

    def test_changed_source_or_attempt_rejects_before_metadata_or_publication(self):
        for key, value in (("GITHUB_RUN_ATTEMPT", "2"), ("GITHUB_SHA", "b" * 40), ("GITHUB_REF_PROTECTED", "false")):
            with self.subTest(key=key), patch.dict(self.environ, {key: value}):
                self.assertEqual(1, self.invoke("preflight")[0])
        self.assertEqual([], self.api.calls)

    def test_checkout_verifies_actual_head_and_tracked_changes(self):
        for head, status, ignored, accepted in (
            ("a" * 40, "", "", True),
            ("b" * 40, "", "", False),
            ("a" * 40, " M hosted-agents/deployment.py", "", False),
            ("a" * 40, "?? untracked.py", "", False),
            ("a" * 40, "", "!! hosted-agents/application-review-agent/configuration.py", False),
        ):
            with self.subTest(head=head, status=status, ignored=ignored), patch.object(release.subprocess, "run") as run:
                run.side_effect = [
                    types.SimpleNamespace(returncode=0, stdout=head),
                    types.SimpleNamespace(returncode=0, stdout=status),
                    types.SimpleNamespace(returncode=0, stdout=ignored),
                ]
                # The normal fixture suppresses checkout; exercise its original
                # function with only the external git subprocess mocked here.
                function = self.real_checkout
                if accepted:
                    function(ROOT, "a" * 40)
                else:
                    with self.assertRaises(release.ReleaseError):
                        function(ROOT, "a" * 40)
                for call in run.call_args_list:
                    self.assertEqual(call.args[0][:5], ["/usr/bin/git", "-c", "core.fsmonitor=false", "-C", str(ROOT)])
                    self.assertEqual(call.kwargs["timeout"], 15)
                    self.assertEqual(call.kwargs["env"]["GIT_CONFIG_GLOBAL"], "/dev/null")
                    self.assertNotIn("GIT_DIR", call.kwargs["env"])
                    self.assertNotIn("GITHUB_TOKEN", call.kwargs["env"])

    def test_checkout_timeout_is_reported_without_traceback_details(self):
        failure = release.subprocess.TimeoutExpired("fictional-sensitive-command", 15)
        with patch.object(release.subprocess, "run", side_effect=failure):
            with self.assertRaisesRegex(release.ReleaseError, "Release checkout could not be verified"):
                self.real_checkout(ROOT, "a" * 40)

    def test_release_refuses_packaging_contract_drift(self):
        context = release.context(self.environ)
        with patch.object(deployment, "OPTIONAL_SOURCE_FILES", ("instructions.md", "configuration.py", "extra.py")):
            with self.assertRaisesRegex(release.ReleaseError, "package source list changed"):
                release.release_plan(ROOT, context, self.values, {})
        with patch.object(release, "PACKAGE_DIRECTORIES", ("other", *release.PACKAGE_DIRECTORIES[1:])):
            with self.assertRaisesRegex(release.ReleaseError, "source directories changed"):
                release.release_plan(ROOT, context, self.values, {})

    def test_checkout_uses_real_git_and_rejects_ignored_packaged_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            environment = {
                "PATH": "/usr/bin:/bin", "LC_ALL": "C",
                "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
            }

            def git(*args):
                return release.subprocess.run(
                    ["/usr/bin/git", "-C", str(root), *args], env=environment,
                    capture_output=True, text=True, check=True, timeout=15,
                )

            git("init", "-q")
            (root / ".gitignore").write_text(
                "hosted-agents/application-review-agent/configuration.py\n"
                "hosted-agents/case-review-agent/\n__pycache__/\n", encoding="utf-8",
            )
            (root / "tracked.txt").write_text("fictional source\n", encoding="utf-8")
            git("add", ".gitignore", "tracked.txt")
            git(
                "-c", "user.name=Fictional Test", "-c", "user.email=fictional@example.invalid",
                "-c", "commit.gpgsign=false", "commit", "-qm", "fictional source",
            )
            source = git("rev-parse", "HEAD").stdout.strip()
            poisoned = {
                "GIT_DIR": str(root / "not-a-repository"),
                "GIT_WORK_TREE": str(root / "wrong-worktree"),
                "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "core.fsmonitor",
                "GIT_CONFIG_VALUE_0": "/bin/false", "GITHUB_TOKEN": "fictional-token",
            }
            with patch.dict(os.environ, poisoned):
                self.real_checkout(root, source)
                ignored = root / "hosted-agents" / "application-review-agent" / "configuration.py"
                ignored.parent.mkdir(parents=True)
                ignored.write_text("fictional ignored package input\n", encoding="utf-8")
                with self.assertRaisesRegex(release.ReleaseError, "reviewed clean source"):
                    self.real_checkout(root, source)
                ignored.unlink()
                ignored_directory_file = root / "hosted-agents" / "case-review-agent" / "requirements.txt"
                ignored_directory_file.parent.mkdir(parents=True)
                ignored_directory_file.write_text("fictional ignored package input\n", encoding="utf-8")
                with self.assertRaisesRegex(release.ReleaseError, "reviewed clean source"):
                    self.real_checkout(root, source)
                ignored_directory_file.unlink()
                cache = root / "hosted-agents" / "application-review-agent" / "__pycache__" / "fictional.pyc"
                cache.parent.mkdir(parents=True)
                cache.write_bytes(b"fictional cache")
                self.real_checkout(root, source)
                (root / "untracked.txt").write_text("fictional\n", encoding="utf-8")
                with self.assertRaisesRegex(release.ReleaseError, "reviewed clean source"):
                    self.real_checkout(root, source)

    def test_live_remains_disabled_even_for_exact_owner_self_review(self):
        ctx = self.prepare()
        self.approve("application", ctx)
        with patch.object(deployment, "deploy") as publish:
            result, output = self.invoke("publish", "application")
        self.assertEqual(1, result)
        self.assertIn("Live publication is disabled", output)
        publish.assert_not_called()

    def test_wrong_missing_duplicate_or_replayed_approval_fails_closed(self):
        ctx = self.prepare()
        for change in ("missing", "duplicate", "comment", "reviewer", "state", "environment", "multiple"):
            with self.subTest(change=change):
                self.approve("application", ctx)
                review = self.api.data["/actions/runs/91/approvals"][0]
                if change == "missing":
                    self.api.data["/actions/runs/91/approvals"] = []
                elif change == "duplicate":
                    self.api.data["/actions/runs/91/approvals"].append(deepcopy(review))
                elif change == "comment":
                    review["comment"] = review["comment"].replace("run 91", "run 90")
                elif change == "reviewer":
                    review["user"]["id"] = 18
                elif change == "state":
                    review["state"] = "rejected"
                elif change == "environment":
                    review["environments"][0]["id"] = 99
                else:
                    review["environments"].append({"id": 8, "name": "other"})
                result, output = self.invoke("publish", "application")
                self.assertEqual(1, result)
                self.assertIn("review", output)

    def test_changed_actual_release_inputs_and_environment_ids_reject_after_approval(self):
        ctx = self.prepare()
        for field, value in (
            ("endpoint", "https://other.services.ai.azure.com/api/projects/other"),
            ("model", "other-router"), ("client_id", "42345678-1234-1234-1234-123456789abc"),
            ("tenant_id", "52345678-1234-1234-1234-123456789abc"),
            ("profile_sha256", "0" * 64), ("targets", list(reversed(release.TARGETS))),
            ("credential_mode", "EnvironmentCredential"), ("client_id", "invalid"),
            ("credential_mode", ""), ("cpu", "4"),
        ):
            with self.subTest(field=field):
                self.approve("application", ctx)
                altered = {**self.values, field: value}
                with patch.dict(self.environ, {"AGENT_RELEASE_INPUTS": release.canonical(altered)}):
                    self.assertEqual(1, self.invoke("publish", "application")[0])
        name = release.ENVIRONMENTS["case"]
        self.api.data[f"/environments/{name}"]["id"] = 92
        self.assertIn("policy changed", self.invoke("publish", "application")[1])

    def test_one_step_and_successful_predecessors_are_required(self):
        ctx = self.prepare()
        self.approve("case", ctx)
        self.api.data["/actions/runs/91/attempts/1/jobs?per_page=100"]["jobs"][1]["conclusion"] = "failure"
        self.assertIn("predecessors", self.invoke("publish", "case")[1])
        self.assertIn("single stage", self.invoke("publish", "application")[1])

    def test_router_is_exact_and_fixed_recovery_is_a_new_review_choice(self):
        self.prepare()
        altered = {**self.values, "model": "fictional-fixed", "model_choice": "fixed_recovery"}
        with patch.dict(self.environ, {"AGENT_RELEASE_INPUTS": release.canonical(altered)}):
            with self.assertRaises(release.ReleaseError):
                release.inputs(self.environ)
            self.environ["REVIEWED_MODEL_SHA256"] = release.digest("fictional-fixed")
            self.environ["RELEASE_MODEL_CHOICE"] = "fixed_recovery"
            self.assertEqual(altered, release.inputs(self.environ))
            self.assertNotEqual(
                self.environ["RELEASE_MANIFEST_DIGEST"],
                release.digest(release.release_plan(ROOT, release.context(self.environ), altered, json.loads(self.environ["RELEASE_ENVIRONMENT_POLICY"]))[0]),
            )

    def test_actual_publisher_rechecks_each_mutation_and_preserves_router_promotion(self):
        ctx = self.prepare()
        for step, target in zip(release.STEPS, release.TARGETS, strict=True):
            self.approve(step, ctx)
            mutations = []
            modules, client, credential = external_sdk(self.values["model"], mutations)
            with (
                patch.dict(sys.modules, modules),
                patch.object(deployment, "publication_credential", return_value=credential),
                patch.object(deployment, "candidate_smoke_test") as candidate,
                patch.object(deployment, "smoke_test"),
                patch.object(release, "LIVE_PUBLICATION_ENABLED", True),
            ):
                self.assertEqual(0, self.invoke("publish", step)[0])
            self.assertEqual([("create", target), ("route", target)], mutations)
            self.assertEqual(self.values["model"], client.agents.create_version_from_code.call_args.kwargs["definition"].environment_variables["FOUNDRY_MODEL_NAME"])
            self.assertEqual("2", candidate.call_args.args[2])
            if step == "coordinator":
                self.assertEqual({"application-review-agent", "case-review-agent"}, {check[2] for check in candidate.call_args.args[4]})

    def test_policy_change_after_candidate_creation_prevents_route_and_recovery_updates(self):
        ctx = self.prepare()
        self.approve("application", ctx)
        mutations = []
        modules, client, credential = external_sdk(self.values["model"], mutations)
        create = client.agents.create_version_from_code.side_effect

        def change(**kwargs):
            result = create(**kwargs)
            self.api.data[f"/environments/{release.ENVIRONMENTS['application']}"]["can_admins_bypass"] = True
            return result

        client.agents.create_version_from_code.side_effect = change
        with (
            patch.dict(sys.modules, modules),
            patch.object(deployment, "publication_credential", return_value=credential),
            patch.object(deployment, "candidate_smoke_test"),
            patch.object(deployment, "smoke_test"),
            patch.object(release, "LIVE_PUBLICATION_ENABLED", True),
        ):
            self.assertEqual(1, self.invoke("publish", "application")[0])
        self.assertEqual([("create", "application-review-agent")], mutations)
        client.agents.update_details.assert_not_called()

    def test_selected_identity_change_after_creation_prevents_promotion(self):
        ctx = self.prepare()
        self.approve("application", ctx)
        mutations = []
        modules, client, credential = external_sdk(self.values["model"], mutations)
        create = client.agents.create_version_from_code.side_effect

        def change(**kwargs):
            result = create(**kwargs)
            os.environ["AZURE_TOKEN_CREDENTIALS"] = "EnvironmentCredential"
            return result

        client.agents.create_version_from_code.side_effect = change
        with (
            patch.dict(sys.modules, modules),
            patch.object(deployment, "publication_credential", return_value=credential),
            patch.object(deployment, "candidate_smoke_test"),
            patch.object(deployment, "smoke_test"),
            patch.object(release, "LIVE_PUBLICATION_ENABLED", True),
        ):
            self.assertEqual(1, self.invoke("publish", "application")[0])
        self.assertEqual([("create", "application-review-agent")], mutations)
        client.agents.update_details.assert_not_called()

    def test_missing_authentication_and_http_failures_do_not_accept_metadata(self):
        with self.assertRaises(release.ReleaseError):
            release.GitHub("fictional-owner/fictional-repository", "")
        from urllib.error import HTTPError
        opener = MagicMock()
        opener.open.side_effect = HTTPError("https://api.github.com", 403, "private response", {}, None)
        with patch.object(release, "build_opener", return_value=opener):
            with self.assertRaisesRegex(release.ReleaseError, "HTTP 403"):
                release.GitHub("fictional-owner/fictional-repository", "fictional-read-only-token").get("")

    def test_workflow_keeps_sequential_gates_and_no_oidc_or_approval_bypass(self):
        workflow = (ROOT / release.WORKFLOW).read_text()
        self.assertIn("needs: [preflight, prepare, publish-application, publish-case]", workflow)
        self.assertIn("needs.preflight.outputs.prepare_environment", workflow)
        self.assertIn("persist-credentials: false", workflow)
        for unsafe in ("id-token: write", "--yes", "echo apply", "sudo", "pip install", "terraform "):
            self.assertNotIn(unsafe, workflow)


if __name__ == "__main__":
    unittest.main()

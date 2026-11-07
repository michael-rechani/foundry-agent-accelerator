"""Offline safety contracts: never call GitHub, Azure, or the OIDC endpoint."""

import contextlib
import copy
import hashlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import reviewed_private_runner_restart as restart

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = (ROOT / ".github" / "workflows" / "reviewed-private-runner-restart.yml").read_text()
SHA = "a" * 40
UUID = "11111111-1111-1111-1111-111111111111"
VM_ID = (f"/subscriptions/{UUID}/resourcegroups/runner-rg"
         "/providers/microsoft.compute/virtualmachines/runner-vm")
DIGEST = hashlib.sha256(VM_ID.encode()).hexdigest()


def fixture():
    env = {
        "GITHUB_REPOSITORY": restart.REPOSITORY, "GITHUB_REF": "refs/heads/main",
        "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_RUN_ID": "123", "GITHUB_SHA": SHA, "REVIEWED_COMMIT": SHA,
        "REVIEWED_VM_SHA256": DIGEST, "AZURE_CLIENT_ID": UUID, "AZURE_TENANT_ID": UUID,
        "AZURE_SUBSCRIPTION_ID": UUID, "LAB_RUNNER_RESOURCE_GROUP": "runner-rg",
        "LAB_RUNNER_VM": "runner-vm",
    }
    owner = {"id": 7, "login": restart.OWNER, "type": "User"}
    data = {
        "": {"full_name": restart.REPOSITORY, "owner": owner},
        "branches/main": {"protected": True, "commit": {"sha": SHA}},
        "actions/runs/123": {
            "id": 123, "run_attempt": 1, "event": "workflow_dispatch",
            "head_branch": "main", "head_sha": SHA, "path": restart.WORKFLOW,
            "repository": {"full_name": restart.REPOSITORY},
        },
        f"environments/{restart.GATE}": {
            "id": 20, "name": restart.GATE, "can_admins_bypass": False,
            "deployment_branch_policy": {"protected_branches": False, "custom_branch_policies": True},
            "protection_rules": [{
                "id": 30, "type": "required_reviewers", "prevent_self_review": False,
                "reviewers": [{"type": "User", "reviewer": owner}],
            }, {"id": 31, "type": "branch_policy"}],
        },
        f"environments/{restart.GATE}/deployment-branch-policies?per_page=100": {
            "total_count": 1, "branch_policies": [{"id": 40, "name": "main", "type": "branch"}],
        },
        f"environments/{restart.GATE}/secrets?per_page=100": {"total_count": 0, "secrets": []},
        "actions/runs/123/approvals": [{
            "state": "approved", "user": owner,
            "environments": [{"id": 20, "name": restart.GATE}],
            "comment": restart.approval_comment("123", SHA, DIGEST),
        }],
    }
    gate_id, _, config = restart.verify_gate(data.__getitem__)
    env["EXPECTED_GATE_ID"] = str(gate_id)
    env["EXPECTED_GATE_CONFIGURATION_SHA256"] = config
    return env, copy.deepcopy(data)


class Guards(unittest.TestCase):
    def setUp(self):
        self.env, self.data = fixture()

    def rejected(self, *, env=None, data=None):
        calls = []

        def token(_):
            calls.append("oidc")
            return "offline-token"

        def execute(arguments):
            calls.append(arguments)
            return ""

        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(restart.GuardError):
            restart.start_vm(env or self.env, (data or self.data).__getitem__, execute, token)
        self.assertEqual(calls, [], "Authorization failures must precede all credential/Azure calls")

    def test_exact_fresh_dispatch_is_authorized(self):
        restart.verify_approval(self.env, self.data.__getitem__)

    def test_invalid_context_and_injection(self):
        for field, values in {
            "GITHUB_REPOSITORY": ["other/repo", restart.REPOSITORY + "; echo injected"],
            "GITHUB_REF": ["refs/heads/feature", "refs/tags/main"],
            "GITHUB_EVENT_NAME": ["push", "pull_request"],
            "GITHUB_RUN_ATTEMPT": ["2", "01", "", "$(echo 1)"],
            "GITHUB_RUN_ID": ["0", "-1", "", "123/approvals"],
            "REVIEWED_COMMIT": ["b" * 40, SHA.upper(), SHA + "\n"],
            "REVIEWED_VM_SHA256": ["0" * 64, DIGEST.upper(), "$(touch injected)", ""],
            "AZURE_CLIENT_ID": ["", UUID + "\n", "--help"],
            "AZURE_TENANT_ID": ["invalid"],
            "AZURE_SUBSCRIPTION_ID": ["invalid", "22222222-2222-2222-2222-222222222222"],
            "LAB_RUNNER_VM": ["other", "--help", "vm;echo injected", "vm/name", ""],
            "LAB_RUNNER_RESOURCE_GROUP": ["other", "rg.", "rg/other", "rg$(id)", ""],
        }.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    self.rejected(env={**self.env, field: value})

    def test_live_run_changes_and_reruns(self):
        for field, value in {
            "id": 124, "run_attempt": 2, "event": "push", "head_branch": "feature",
            "head_sha": "b" * 40, "path": ".github/workflows/other.yml",
            "repository": {"full_name": "other/repo"},
        }.items():
            with self.subTest(field=field):
                data = copy.deepcopy(self.data)
                data["actions/runs/123"][field] = value
                self.rejected(data=data)
        for branch in ({}, {"protected": False, "commit": {"sha": SHA}},
                       {"protected": True, "commit": {"sha": "b" * 40}}):
            data = copy.deepcopy(self.data)
            data["branches/main"] = branch
            self.rejected(data=data)

    def test_missing_unprotected_or_bypass_unknown_environment(self):
        key = f"environments/{restart.GATE}"
        for value in (None, {}, {"id": 20, "name": restart.GATE}):
            data = copy.deepcopy(self.data)
            data[key] = value
            self.rejected(data=data)
        for bypass in (None, True, 0, "false"):
            data = copy.deepcopy(self.data)
            data[key]["can_admins_bypass"] = bypass
            self.rejected(data=data)
        data = copy.deepcopy(self.data)
        del data[key]["can_admins_bypass"]
        self.rejected(data=data)

    def test_reviewer_rule_is_exact_and_owner_identity_verified(self):
        key = f"environments/{restart.GATE}"
        base = self.data[key]["protection_rules"][0]
        branch_rule = self.data[key]["protection_rules"][1]
        for rules in ([], None, [base, base], [{**base, "type": "wait_timer"}],
                      [{**base, "reviewers": []}],
                      [{**base, "reviewers": [{"type": "Team", "reviewer": {"id": 7}}]}],
                      [{**base, "reviewers": [base["reviewers"][0]] * 2}],
                      [{**base, "reviewers": []}, branch_rule],
                      [{**base, "reviewers": [{"type": "Team", "reviewer": {"id": 7}}]}, branch_rule],
                      [{**base, "reviewers": [base["reviewers"][0]] * 2}, branch_rule]):
            data = copy.deepcopy(self.data)
            data[key]["protection_rules"] = rules
            self.rejected(data=data)
        for field, value in (("id", 8), ("login", "unauthorized"), ("type", "Organization")):
            data = copy.deepcopy(self.data)
            data[""]["owner"][field] = value
            self.rejected(data=data)

    def test_complete_real_protection_shape_is_order_independent(self):
        restart.verify_approval(self.env, self.data.__getitem__)
        data = copy.deepcopy(self.data)
        data[f"environments/{restart.GATE}"]["protection_rules"].reverse()
        restart.verify_approval(self.env, data.__getitem__)

    def test_unknown_duplicate_missing_or_invalid_rule_shapes_fail(self):
        key = f"environments/{restart.GATE}"
        reviewer, branch = self.data[key]["protection_rules"]
        cases = (
            [reviewer], [branch], [reviewer, reviewer], [branch, branch],
            [reviewer, branch, {"id": 32, "type": "wait_timer"}],
            [reviewer, {"id": 31, "type": "wait_timer"}],
            [reviewer, {"id": 31, "type": "unknown"}],
            [reviewer, {"id": 31, "type": []}],
            [reviewer, {"id": 0, "type": "branch_policy"}],
            [reviewer, {"id": True, "type": "branch_policy"}],
            [reviewer, {"type": "branch_policy"}],
            [{**reviewer, "id": 0}, branch],
            [reviewer, {**branch, "id": reviewer["id"]}],
        )
        for rules in cases:
            with self.subTest(rules=rules):
                data = copy.deepcopy(self.data)
                data[key]["protection_rules"] = rules
                self.rejected(data=data)

    def test_both_protection_rule_ids_are_bound_to_snapshot(self):
        key = f"environments/{restart.GATE}"
        for index in (0, 1):
            data = copy.deepcopy(self.data)
            data[key]["protection_rules"][index]["id"] += 100
            self.rejected(data=data)

    def test_main_only_restrictions_and_no_secrets(self):
        key = f"environments/{restart.GATE}"
        for policy in (None, {}, {"protected_branches": True, "custom_branch_policies": False}):
            data = copy.deepcopy(self.data)
            data[key]["deployment_branch_policy"] = policy
            self.rejected(data=data)
        branch_key = key + "/deployment-branch-policies?per_page=100"
        for branches in (
            {"total_count": 0, "branch_policies": []},
            {"total_count": 2, "branch_policies": [{"id": 40, "name": "main", "type": "branch"}]},
            {"total_count": 1, "branch_policies": [{"id": 40, "name": "*", "type": "branch"}]},
            {"total_count": 1, "branch_policies": [{"id": 40, "name": "main", "type": "tag"}]},
        ):
            data = copy.deepcopy(self.data)
            data[branch_key] = branches
            self.rejected(data=data)
        for secrets in ({}, {"total_count": 1, "secrets": [{"name": "ANY_SECRET"}]},
                        {"total_count": 0, "secrets": [{}]}):
            data = copy.deepcopy(self.data)
            data[key + "/secrets?per_page=100"] = secrets
            self.rejected(data=data)

    def test_environment_recreation_or_configuration_change(self):
        key = f"environments/{restart.GATE}"
        for field, value in (("id", 21), ("name", "different")):
            data = copy.deepcopy(self.data)
            data[key][field] = value
            self.rejected(data=data)
        data = copy.deepcopy(self.data)
        data[key]["protection_rules"][0]["prevent_self_review"] = True
        self.rejected(data=data)

    def test_review_history_unavailable_rejected_ambiguous_or_wrong_scope(self):
        key = "actions/runs/123/approvals"
        base = self.data[key][0]
        cases = [
            None, {}, [], [base, base], [{}],
            [{**base, "state": "rejected"}], [{**base, "state": "pending"}],
            [{**base, "comment": ""}], [{**base, "comment": base["comment"] + "\n"}],
            [{**base, "comment": base["comment"].replace("123", "124")}],
            [{**base, "comment": base["comment"].replace(SHA, "b" * 40)}],
            [{**base, "comment": base["comment"].replace(DIGEST, "0" * 64)}],
            [{**base, "environments": [{"id": 21, "name": restart.GATE}]}],
            [{**base, "environments": [{"id": 20, "name": "lab-deploy"}]}],
            [{**base, "environments": [{"id": 20, "name": restart.GATE},
                                     {"id": 21, "name": "lab-deploy"}]}],
            [{**base, "user": {"id": 8, "login": restart.OWNER, "type": "User"}}],
            [{**base, "user": {"id": 7, "login": "other", "type": "User"}}],
            [{**base, "user": {"id": 7, "login": restart.OWNER, "type": "Bot"}}],
        ]
        for reviews in cases:
            with self.subTest(reviews=reviews):
                data = copy.deepcopy(self.data)
                data[key] = reviews
                self.rejected(data=data)

    def test_previous_run_approval_cannot_authorize_a_new_dispatch(self):
        env = {**self.env, "GITHUB_RUN_ID": "124"}
        data = copy.deepcopy(self.data)
        data["actions/runs/124"] = {**data["actions/runs/123"], "id": 124}
        data["actions/runs/124/approvals"] = data["actions/runs/123/approvals"]
        self.rejected(env=env, data=data)

    def test_normalization_and_masking(self):
        env = {**self.env, "LAB_RUNNER_VM": "RUNNER-VM", "LAB_RUNNER_RESOURCE_GROUP": "RUNNER-RG"}
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(restart.target(env), VM_ID)
        self.assertIn(f"::add-mask::{VM_ID}", output.getvalue())
        self.assertIn("::add-mask::RUNNER-VM", output.getvalue())

    def test_each_github_read_failure_precedes_credentials(self):
        for endpoint in self.data:
            with self.subTest(endpoint=endpoint):
                def get(path, endpoint=endpoint):
                    if path == endpoint:
                        raise restart.GuardError("GitHub read unavailable.")
                    return self.data[path]
                with patch.object(restart, "oidc_token") as token:
                    with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(restart.GuardError):
                        restart.start_vm(self.env, get, token_request=token)
                    token.assert_not_called()


class AzureExecution(unittest.TestCase):
    def execute(self, initial="PowerState/deallocated", final="PowerState/running", fail=None,
                actual=VM_ID):
        env, data = fixture()
        calls, elapsed = [], [0]

        def token(_):
            calls.append(["oidc"])
            return "offline-token"

        def command(args):
            calls.append(args)
            operation = " ".join(args[:3])
            if fail == operation:
                raise restart.GuardError("Offline simulated CLI failure.")
            if args[:3] == ["az", "vm", "show"]:
                return actual
            if args[:3] == ["az", "vm", "get-instance-view"]:
                return final if elapsed[0] else initial
            return ""

        def sleep(seconds):
            elapsed[0] += seconds

        error = None
        with contextlib.redirect_stdout(io.StringIO()):
            try:
                restart.start_vm(env, data.__getitem__, command, token, lambda: elapsed[0], sleep)
            except restart.GuardError as caught:
                error = caught
        return calls, elapsed[0], error

    def test_stopped_and_deallocated_start_once_and_confirm(self):
        for state in ("PowerState/deallocated", "PowerState/stopped"):
            calls, elapsed, error = self.execute(initial=state)
            self.assertIsNone(error)
            starts = [call for call in calls if call[:3] == ["az", "vm", "start"]]
            self.assertEqual(starts, [["az", "vm", "start", "--ids", VM_ID, "--no-wait",
                                      "--output", "none"]])
            self.assertEqual(elapsed, 10)
            self.assertEqual(calls[0], ["oidc"])
            allowed = {("az", "login", "--service-principal"), ("az", "account", "set"),
                       ("az", "vm", "show"), ("az", "vm", "get-instance-view"), ("az", "vm", "start")}
            self.assertTrue(all(tuple(call[:3]) in allowed for call in calls[1:]))

    def test_running_and_starting_are_not_started(self):
        for initial in ("PowerState/running", "PowerState/starting"):
            calls, _, error = self.execute(initial=initial)
            self.assertIsNone(error)
            self.assertFalse(any(call[:3] == ["az", "vm", "start"] for call in calls))

    def test_wrong_azure_identity_blocks_state_read_and_start(self):
        for actual in ("", VM_ID + "/other", VM_ID.replace("runner-vm", "other")):
            calls, _, error = self.execute(actual=actual)
            self.assertIsNotNone(error)
            self.assertFalse(any(call[:3] in (["az", "vm", "start"],
                                             ["az", "vm", "get-instance-view"]) for call in calls))
        self.assertIsNone(self.execute(actual=VM_ID.upper())[2])

    def test_cli_failures_do_not_retry_or_run_other_writes(self):
        for operation in ("az login --service-principal", "az account set", "az vm show",
                          "az vm get-instance-view", "az vm start"):
            with self.subTest(operation=operation):
                calls, _, error = self.execute(fail=operation)
                self.assertIsNotNone(error)
                starts = sum(call[:3] == ["az", "vm", "start"] for call in calls)
                self.assertEqual(starts, int(operation == "az vm start"))

    def test_oidc_failure_precedes_all_azure_calls(self):
        env, data = fixture()
        with patch.object(restart, "command") as command, \
                contextlib.redirect_stdout(io.StringIO()), self.assertRaises(restart.GuardError):
            restart.start_vm(env, data.__getitem__, command,
                             token_request=unittest.mock.Mock(side_effect=restart.GuardError("OIDC failed.")))
        command.assert_not_called()

    def test_running_confirmation_after_deadline_is_not_success(self):
        env, data = fixture()
        elapsed = [0]

        def execute(args):
            if args[:3] == ["az", "vm", "show"]:
                return VM_ID
            if args[:3] == ["az", "vm", "get-instance-view"]:
                if elapsed[0]:
                    elapsed[0] = 301
                    return "PowerState/running"
                return "PowerState/starting"
            return ""

        def sleep(seconds):
            elapsed[0] += seconds

        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(restart.GuardError):
            restart.start_vm(env, data.__getitem__, execute, lambda _: "offline-token",
                             lambda: elapsed[0], sleep)

    def test_ambiguous_or_unsafe_state_and_bounded_poll(self):
        for state in ("", "PowerState/unknown", "PowerState/deallocating",
                      "PowerState/running\nPowerState/stopped"):
            calls, _, error = self.execute(initial=state)
            self.assertIsNotNone(error)
            self.assertFalse(any(call[:3] == ["az", "vm", "start"] for call in calls))
            self.assertIsNotNone(self.execute(final=state)[2])
        calls, elapsed, error = self.execute(final="PowerState/starting")
        self.assertIsNotNone(error)
        self.assertEqual(elapsed, 300)
        self.assertEqual(sum(call[:3] == ["az", "vm", "start"] for call in calls), 1)


class NetworkAndWorkflowContracts(unittest.TestCase):
    def test_github_only_reads_no_privileged_token(self):
        with patch.object(restart, "command", return_value="HTTP/2.0 200 OK\n\n{}") as command:
            self.assertEqual(restart.github_get("branches/main"), {})
        args = command.call_args.args[0]
        self.assertIn("--include", args)
        self.assertEqual(args[args.index("--method") + 1], "GET")
        self.assertEqual(args[args.index("--hostname") + 1], "github.com")

    def test_invalid_paginated_and_duplicate_json_responses_fail_closed(self):
        for response in ("{}", "HTTP/2.0 403 Forbidden\n\n{}",
                         "HTTP/2.0 200 OK\nLink: <next>; rel=\"next\"\n\n{}",
                         "HTTP/2.0 200 OK\n\nnot-json",
                         'HTTP/2.0 200 OK\n\n{"can_admins_bypass":true,"can_admins_bypass":false}'):
            with patch.object(restart, "command", return_value=response), self.assertRaises(restart.GuardError):
                restart.github_get("")

    def test_cli_timeout_and_failure_do_not_echo_private_output(self):
        for outcome in (subprocess.CompletedProcess(["gh"], 1, UUID, UUID),
                        OSError(UUID), subprocess.TimeoutExpired(["gh"], 45)):
            with patch.object(restart.subprocess, "run") as run:
                if isinstance(outcome, Exception):
                    run.side_effect = outcome
                else:
                    run.return_value = outcome
                with self.assertRaises(restart.GuardError) as error:
                    restart.command(["gh", "api"])
                self.assertNotIn(UUID, str(error.exception))

    def test_oidc_invalid_endpoints_never_connect(self):
        for url in ("http://pipelines.actions.githubusercontent.com/token",
                    "https://evil.invalid/token", "https://actions.githubusercontent.com.evil.invalid/",
                    "https://user@pipelines.actions.githubusercontent.com/token",
                    "https://pipelines.actions.githubusercontent.com:invalid/token",
                    "https://pipelines.actions.githubusercontent.com/token?audience=other"):
            with patch.object(restart, "build_opener") as opener, self.assertRaises(restart.GuardError):
                restart.oidc_token({"ACTIONS_ID_TOKEN_REQUEST_URL": url})
            opener.assert_not_called()

    def test_oidc_request_exact_audience_and_masks_token(self):
        response = unittest.mock.MagicMock()
        response.__enter__.return_value.status = 200
        response.__enter__.return_value.read.return_value = json.dumps({"value": "offline-token"}).encode()
        with patch.object(restart, "build_opener") as opener, contextlib.redirect_stdout(io.StringIO()) as log:
            opener.return_value.open.return_value = response
            self.assertEqual(restart.oidc_token({
                "ACTIONS_ID_TOKEN_REQUEST_URL": "https://pipelines.actions.githubusercontent.com/token?x=1",
                "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "offline-request",
            }), "offline-token")
        request = opener.return_value.open.call_args.args[0]
        self.assertIn("audience=api%3A%2F%2FAzureADTokenExchange", request.full_url)
        self.assertEqual(request.get_header("Authorization"), "bearer offline-request")
        self.assertIn("::add-mask::offline-token", log.getvalue())

    def test_workflow_is_manual_main_only_and_environment_ordered(self):
        preflight, review, start = WORKFLOW.split("\n  review:\n")[0], \
            WORKFLOW.split("\n  review:\n")[1].split("\n  start:\n")[0], \
            WORKFLOW.split("\n  start:\n")[1]
        self.assertIn("workflow_dispatch:", preflight)
        for trigger in ("push:", "pull_request:", "schedule:", "workflow_call:"):
            self.assertNotIn(trigger, WORKFLOW)
        self.assertEqual(WORKFLOW.count("github.run_attempt == 1"), 3)
        self.assertEqual(WORKFLOW.count("github.ref == 'refs/heads/main'"), 3)
        self.assertNotIn("environment:", preflight)
        self.assertNotIn("id-token:", preflight + review)
        self.assertIn("needs: preflight", review)
        self.assertIn("permissions: {}", review)
        self.assertNotIn("secrets.", WORKFLOW)
        self.assertNotIn("github.token", review)
        self.assertNotIn("checkout@", review)
        self.assertIn("environment: private-runner-restart-review", review)
        self.assertIn("needs: [preflight, review]", start)
        self.assertIn("environment: lab-deploy", start)
        self.assertEqual(WORKFLOW.count("id-token: write"), 1)
        self.assertNotIn("actions: write", WORKFLOW)
        self.assertNotIn("self-hosted", WORKFLOW)
        self.assertIn("cancel-in-progress: false", WORKFLOW)

    def test_checkout_only_exact_sha_and_no_shell_input_interpolation(self):
        self.assertEqual(WORKFLOW.count("ref: ${{ github.sha }}"), 2)
        self.assertEqual(WORKFLOW.count("persist-credentials: false"), 2)
        before_checkout = WORKFLOW.split("- uses: actions/checkout@", 1)[0]
        self.assertIn("select(.protected == true) | .commit.sha", before_checkout)
        self.assertIn('"$REVIEWED_COMMIT" == "$GITHUB_SHA"', before_checkout)
        inline = before_checkout.split("        run: |\n", 1)[1]
        self.assertNotIn("${{", inline)
        self.assertNotIn("workbench/", WORKFLOW)
        for mode in ("preflight", "start"):
            self.assertIn(f"reviewed_private_runner_restart.py {mode}", WORKFLOW)

    def test_new_files_do_not_trigger_lab_image_deploy(self):
        deploy = (ROOT / ".github" / "workflows" / "deploy-lab.yml").read_text()
        push = deploy.split("  push:\n", 1)[1].split("  workflow_dispatch:", 1)[0]
        self.assertIn("- 'workbench/**'", push)
        for file in ("reviewed-private-runner-restart.yml",
                     "reviewed_private_runner_restart.py", "test_reviewed_private_runner_restart.py"):
            self.assertNotIn(file, push)

    def test_main_reports_failure_without_private_values(self):
        env, _ = fixture()
        with patch.dict(os.environ, env, clear=True), \
                patch.object(restart, "github_get", side_effect=restart.GuardError("Read unavailable.")), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(restart.main(["preflight"]), 1)
        self.assertIn("::error::Read unavailable.", output.getvalue())
        self.assertNotIn(UUID, output.getvalue())

    def test_preflight_outputs_and_summary_exact_binding_without_identifiers(self):
        env, data = fixture()
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "outputs"
            summary_path = Path(directory) / "summary"
            env.update(GITHUB_OUTPUT=str(output_path), GITHUB_STEP_SUMMARY=str(summary_path))
            with patch.dict(os.environ, env, clear=True), \
                    patch.object(restart, "github_get", side_effect=data.__getitem__):
                self.assertEqual(restart.main(["preflight"]), 0)
            self.assertEqual(output_path.read_text(),
                             f"gate_id=20\ngate_configuration_sha256={env['EXPECTED_GATE_CONFIGURATION_SHA256']}\n")
            summary = summary_path.read_text()
            self.assertIn(restart.approval_comment("123", SHA, DIGEST), summary)
            self.assertNotIn(UUID, summary)
            self.assertNotIn(VM_ID, summary)
            self.assertIn("registry-push", summary)


if __name__ == "__main__":
    unittest.main()

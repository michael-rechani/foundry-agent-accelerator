import contextlib
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

import apply_lab_terraform as apply
import check_lab_terraform_plan as diagnostic
import reconcile_runner_state as reconcile
from test_check_lab_terraform_plan import DIGEST, REVISION, environment, plan, state_object, values

NEW_REVISION = REVISION + "-new"
TAGS = {"workload": "private-workload", "managed-by": "private-manager"}
SECRET_REFERENCE = "private-secret-reference"
FIXTURE_PRIVATE = ("private-workload", "private-manager", "private-flag", SECRET_REFERENCE, "203.0.113.10")


def waf_resource(match_values, tags, **extra):
    return {
        "custom_rule": [{
            "name": "BlockUnlistedClients",
            "match_condition": [{
                "match_variable": "SocketAddr", "operator": "IPMatch",
                "negation_condition": True, "match_values": match_values,
            }],
        }],
        "tags": tags, **extra,
    }


def app_resource(entries):
    return {"template": [{"container": [{"name": "workbench", "env": entries}]}]}


def creation_key(value):
    return {"name": apply.CREATION_KEY, "secret_name": SECRET_REFERENCE, "value": value}


def flag():
    return {"name": apply.UNFINISHED_FLAG, "value": "private-flag"}


def approved_plan(waf_tags=True, app_environment=True):
    value = plan()
    if waf_tags:
        value["resource_changes"][0]["change"] = {
            "actions": ["update"],
            "before": waf_resource(["203.0.113.10/32"], None),
            "after": waf_resource(["203.0.113.10/32"], dict(TAGS)),
        }
    if app_environment:
        value["resource_changes"].append({
            "address": "azurerm_container_app.this[0]", "type": "azurerm_container_app", "mode": "managed",
            "change": {
                "actions": ["update"],
                "before": app_resource([creation_key("")]),
                "after": app_resource([creation_key(None), flag()]),
            },
        })
    return value


def summarize(value):
    return diagnostic.summarize_plan(value, 0 if value == plan() else 2, values())


def app_change(value):
    return value["resource_changes"][-1]["change"]


def app_env(change, side):
    return change[side]["template"][0]["container"][0]["env"]


class GuardAcceptanceTests(unittest.TestCase):
    def test_empty_and_exactly_the_reviewed_changes_are_accepted(self):
        for waf_tags, app_environment, expected in (
            (False, False, []),
            (True, False, ["waf_tags"]),
            (False, True, ["container_app_environment"]),
            (True, True, ["waf_tags", "container_app_environment"]),
        ):
            with self.subTest(waf=waf_tags, app=app_environment):
                summary = summarize(approved_plan(waf_tags, app_environment))
                self.assertEqual(apply.approved_changes(summary), expected)
                self.assertFalse(any(private in json.dumps(summary) for private in FIXTURE_PRIVATE))

    def test_one_existing_tag_and_only_the_creation_key_difference_are_accepted(self):
        value = approved_plan()
        value["resource_changes"][0]["change"]["before"]["tags"] = {"workload": TAGS["workload"]}
        app_change(value)["after"] = app_resource([creation_key(None)])
        self.assertEqual(apply.approved_changes(summarize(value)), ["waf_tags", "container_app_environment"])


class GuardRejectionTests(unittest.TestCase):
    def rejected(self, value):
        with self.assertRaises(diagnostic.CheckError) as raised:
            apply.approved_changes(summarize(value))
        self.assertIn("outside the reviewed set", str(raised.exception))
        self.assertFalse(any(private in str(raised.exception) for private in FIXTURE_PRIVATE))

    def test_waf_changes_beyond_the_two_tags_are_rejected(self):
        def added_entry(value):
            value["resource_changes"][0]["change"]["after"] = waf_resource(
                ["203.0.113.10/32", "203.0.113.11/32"], dict(TAGS),
            )

        def removed_entry(value):
            value["resource_changes"][0]["change"]["before"] = waf_resource(
                ["203.0.113.10/32", "203.0.113.11/32"], None,
            )

        def another_field(value):
            value["resource_changes"][0]["change"]["after"]["mode"] = "Prevention"

        def another_tag(value):
            value["resource_changes"][0]["change"]["after"]["tags"]["owner"] = "private-owner"

        def changed_tag(value):
            value["resource_changes"][0]["change"]["before"]["tags"] = {"workload": "private-old"}

        def removed_tag(value):
            change = value["resource_changes"][0]["change"]
            change["before"]["tags"] = dict(TAGS)
            change["after"]["tags"] = {"workload": TAGS["workload"]}

        def replaced(value):
            value["resource_changes"][0]["change"]["actions"] = ["delete", "create"]

        def unknown(value):
            value["resource_changes"][0]["change"]["after_unknown"] = {"tags": True}

        for mutate in (added_entry, removed_entry, another_field, another_tag, changed_tag, removed_tag,
                       replaced, unknown):
            with self.subTest(mutate=mutate.__name__):
                value = approved_plan(app_environment=False)
                mutate(value)
                self.rejected(value)

    def test_alert_or_other_resource_changes_are_rejected(self):
        def alert(value):
            value["resource_changes"][1]["change"] = {
                "actions": ["update"], "before": {"criteria": [{"query": "a"}]},
                "after": {"criteria": [{"query": "b"}]},
            }

        def other_resource(value):
            value["resource_changes"].append({
                "address": "azapi_resource.logs", "type": "azapi_resource", "mode": "managed",
                "change": {"actions": ["update"], "before": {"tags": {}}, "after": {"tags": {"a": "b"}}},
            })

        def second_app_entry(value):
            value["resource_changes"].append(deepcopy(value["resource_changes"][-1]))

        def data_read(value):
            value["resource_changes"].append({
                "address": "data.azurerm_client_config.current", "mode": "data",
                "change": {"actions": ["read"], "before": None, "after": {}},
            })

        for mutate in (alert, other_resource, second_app_entry, data_read):
            with self.subTest(mutate=mutate.__name__):
                value = approved_plan()
                mutate(value)
                self.rejected(value)

    def test_container_app_changes_beyond_the_reviewed_environment_are_rejected(self):
        def image(value):
            change = app_change(value)
            change["before"]["template"][0]["container"][0]["image"] = "private-old-image"
            change["after"]["template"][0]["container"][0]["image"] = "private-new-image"

        def other_setting(value):
            change = app_change(value)
            app_env(change, "before").append({"name": "WORKBENCH_MODE", "value": "private-old"})
            app_env(change, "after").append({"name": "WORKBENCH_MODE", "value": "private-new"})

        def dynamic_setting(value):
            app_env(app_change(value), "after").append({"name": "PRIVATE_DYNAMIC_NAME", "value": "private"})

        def removed_setting(value):
            app_env(app_change(value), "before").append({"name": "WORKBENCH_MODE", "value": "private-old"})

        def secret_reference(value):
            app_env(app_change(value), "after")[0]["secret_name"] = "other-reference"

        def literal_creation_key(value):
            app_env(app_change(value), "after")[0]["value"] = "private-literal"

        def flag_changed(value):
            app_env(app_change(value), "before").append({"name": apply.UNFINISHED_FLAG, "value": "private-old"})

        def reordered(value):
            change = app_change(value)
            change["before"] = app_resource([flag(), creation_key("")])
            change["after"] = app_resource([creation_key(None), flag()])

        def deleted(value):
            app_change(value)["actions"] = ["delete"]

        def replaced(value):
            app_change(value)["actions"] = ["delete", "create"]

        def unknown(value):
            app_change(value)["after_unknown"] = {"template": [{"container": [{"env": True}]}]}

        for mutate in (image, other_setting, dynamic_setting, removed_setting, secret_reference,
                       literal_creation_key, flag_changed, reordered, deleted, replaced, unknown):
            with self.subTest(mutate=mutate.__name__):
                value = approved_plan(waf_tags=False)
                mutate(value)
                self.rejected(value)

    def test_imports_outputs_and_non_passing_checks_are_rejected(self):
        def imported(value):
            value["resource_changes"][0]["change"]["importing"] = {"id": "private-id"}

        def output(value):
            value["output_changes"] = {"private-output": {
                "actions": ["update"], "before": "a", "after": "b", "after_unknown": False,
            }}

        def failing_check(value):
            value["checks"] = [{"status": "fail", "address": {"to_display": "private-check"}}]

        def unknown_check(value):
            value["checks"] = [{"status": "unknown"}]

        for mutate in (imported, output, failing_check, unknown_check):
            with self.subTest(mutate=mutate.__name__):
                value = approved_plan()
                mutate(value)
                self.rejected(value)


class ApplyCommandTests(unittest.TestCase):
    @staticmethod
    def terraform(scratch="scratch"):
        terraform = object.__new__(apply.ApplyTerraform)
        terraform.scratch = Path(scratch)
        terraform.inputs = terraform.scratch / "inputs.tfvars"
        return terraform

    def test_only_the_exact_saved_plan_can_be_applied(self):
        terraform = self.terraform()
        saved = str(terraform.scratch / "lab.tfplan")
        good = ("apply", "-input=false", "-lock=true", "-lock-timeout=5m", saved)
        with patch.object(reconcile.Terraform, "command", return_value=b"safe") as command:
            self.assertEqual(terraform.command(*good), b"safe")
            command.assert_called_once()
            for bad in (
                ("apply", saved), ("apply", "-auto-approve", saved),
                ("apply", "-input=false", "-lock=false", "-lock-timeout=5m", saved),
                ("apply", "-input=false", "-lock=true", "-lock-timeout=5m", "other.tfplan"),
                good + ("-target=resource.secret",), ("destroy", "-input=false"),
                ("apply", "-input=false", "-lock=true", "-lock-timeout=5m", "-var=bootstrap_only=true", saved),
            ):
                with self.subTest(bad=bad), self.assertRaises(diagnostic.CheckError):
                    terraform.command(*bad)
            with self.assertRaises(diagnostic.CheckError):
                terraform.command(*good, allowed=(0, 2))
            with self.assertRaises(diagnostic.CheckError):
                terraform.command(*good, input_data=b"yes\n")
            command.assert_called_once()

    def test_planning_commands_keep_their_existing_restrictions(self):
        with patch.object(reconcile.Terraform, "command", return_value=b"safe") as command:
            with self.assertRaises(diagnostic.CheckError):
                self.terraform().command("plan", "-refresh=false")
            command.assert_not_called()

    def test_a_changed_saved_plan_is_never_applied(self):
        with tempfile.TemporaryDirectory() as folder:
            terraform = self.terraform(folder)
            saved = terraform.scratch / "lab.tfplan"
            saved.write_bytes(b"reviewed")
            digest = terraform.saved_plan_digest()
            self.assertEqual(digest, hashlib.sha256(b"reviewed").digest())
            with patch.object(reconcile.Terraform, "command", return_value=b"") as command:
                terraform.apply_saved_plan(digest)
                command.assert_called_once()
                saved.write_bytes(b"changed")
                with self.assertRaises(diagnostic.CheckError):
                    terraform.apply_saved_plan(digest)
                command.assert_called_once()


class RunTests(unittest.TestCase):
    def run_fixture(self, operation="apply", plans=None, **failure):
        events, sleeps = [], []
        live = {"serial": 12, "revision": REVISION, "digest": DIGEST, "applied": False, "polls": 0}
        plans = list(plans if plans is not None else [approved_plan(), approved_plan(False, False)])
        ticks = iter(range(0, 1_000_000, 100))
        clock = SimpleNamespace(monotonic=lambda: next(ticks), sleep=sleeps.append)

        class FakeBlobs:
            def __init__(self, _environment):
                pass

            def snapshot(self, name):
                events.append(("snapshot", name))
                if name == diagnostic.LAB_STATE:
                    body = {**state_object(), "serial": live["serial"]}
                    if failure.get("concurrent_state") and ("plan",) in events and not live["applied"]:
                        body["serial"] += 1
                    if failure.get("lineage") and live["applied"]:
                        body["lineage"] = "other-lineage"
                    return json.dumps(body).encode(), f"state-{body['serial']}", {}
                changed = failure.get("input_change") and live["applied"]
                return (b"changed-input" if changed else b"private-input"), "v1", {}

        class FakeTerraform:
            def __init__(self, root, scratch, _environment, inputs):
                self.scratch = scratch
                if inputs != b"private-input":
                    raise AssertionError("Only the canonical inputs may be used.")

            def inputs_resolved(self):
                return values()

            def full_plan(self):
                events.append(("plan",))
                value = plans.pop(0)
                (self.scratch / "lab.tfplan").write_bytes(json.dumps(value).encode())
                return value, 0 if value == plan() else 2

            def saved_plan_digest(self):
                return hashlib.sha256((self.scratch / "lab.tfplan").read_bytes()).digest()

            def apply_saved_plan(self, digest):
                events.append(("apply",))
                if failure.get("apply_error"):
                    raise diagnostic.CheckError("Terraform apply failed (exit 1; private provider diagnostics withheld).")
                live["applied"] = True
                if not failure.get("state_not_recorded"):
                    live["serial"] += 1
                if failure.get("image_changed"):
                    live["digest"] = "sha256:" + "c" * 64

        def fake_image(_environment, _app):
            events.append(("image",))
            if live["applied"]:
                live["polls"] += 1
                ready = live["polls"] > failure.get("slow_revision", 0) and not failure.get("never_ready")
                return (NEW_REVISION if ready else REVISION), live["digest"]
            if failure.get("image_moves") and ("plan",) in events:
                return NEW_REVISION, DIGEST
            return REVISION, DIGEST

        def fake_stage(scratch, _environment):
            root = scratch / "staged"
            root.mkdir()
            return root

        with tempfile.TemporaryDirectory() as folder:
            with (patch.object(diagnostic, "validate_backend"),
                  patch.object(apply, "LabBlobs", FakeBlobs),
                  patch.object(apply, "ApplyTerraform", FakeTerraform),
                  patch.object(apply, "stage_sources", side_effect=fake_stage),
                  patch.object(apply, "configure_platform_oidc"),
                  patch.object(apply, "write_supplemental_files"),
                  patch.object(apply, "current_image", side_effect=fake_image),
                  patch.object(apply, "time", clock),
                  contextlib.redirect_stdout(io.StringIO()) as output,
                  contextlib.redirect_stderr(io.StringIO()) as errors):
                env = {**environment(folder), "TF_LAB_APPLY_OPERATION": operation}
                try:
                    apply.run(env)
                    error = None
                except diagnostic.CheckError as exc:
                    error = exc
            self.assertEqual(list(Path(folder).iterdir()), [])
        everything = output.getvalue() + errors.getvalue() + str(error or "")
        self.assertFalse(any(private in everything for private in FIXTURE_PRIVATE))
        return events, output.getvalue(), errors.getvalue(), error, sleeps

    @staticmethod
    def applied(events):
        return [event for event in events if event == ("apply",)]

    def test_check_plans_and_applies_nothing(self):
        events, output, errors, error, _ = self.run_fixture("check", plans=[approved_plan()])
        self.assertIsNone(error)
        self.assertEqual(self.applied(events), [])
        self.assertIn("Check only; nothing was applied.", output)

    def test_an_unchanged_lab_has_nothing_to_apply(self):
        events, output, errors, error, _ = self.run_fixture(plans=[plan()])
        self.assertIsNone(error)
        self.assertEqual(self.applied(events), [])
        self.assertIn("nothing to apply", output)

    def test_the_reviewed_changes_are_applied_once_then_verified_with_a_follow_up_plan(self):
        events, output, errors, error, sleeps = self.run_fixture()
        self.assertIsNone(error)
        kinds = [event[0] for event in events]
        self.assertEqual(kinds.count("apply"), 1)
        self.assertEqual(kinds.count("plan"), 2)
        self.assertEqual(kinds.index("plan", kinds.index("apply")) > kinds.index("apply"), True)
        self.assertIn("Reviewed changes: waf_tags, container_app_environment.", output)
        self.assertIn("Verified: state advanced", output)
        self.assertEqual((errors, sleeps), ("", []))

    def test_an_app_update_waits_for_the_new_ready_revision(self):
        events, output, errors, error, sleeps = self.run_fixture(slow_revision=2)
        self.assertIsNone(error)
        self.assertEqual(len(sleeps), 2)

    def test_a_waf_only_apply_does_not_wait_for_a_new_revision(self):
        events, output, errors, error, sleeps = self.run_fixture(
            plans=[approved_plan(app_environment=False), plan()], never_ready=True,
        )
        self.assertIsNone(error)
        self.assertEqual((len(self.applied(events)), sleeps), (1, []))

    def test_nothing_is_applied_when_the_guard_rejects_the_plan(self):
        value = approved_plan()
        value["resource_changes"][0]["change"]["after"]["mode"] = "Prevention"
        events, output, errors, error, _ = self.run_fixture(plans=[value])
        self.assertIsInstance(error, diagnostic.CheckError)
        self.assertEqual(self.applied(events), [])
        self.assertIn("Nothing was applied.", errors)

    def test_nothing_is_applied_when_state_or_the_revision_moves_during_planning(self):
        for failure in ("concurrent_state", "image_moves"):
            with self.subTest(failure=failure):
                events, output, errors, error, _ = self.run_fixture(**{failure: True})
                self.assertIsInstance(error, diagnostic.CheckError)
                self.assertEqual(self.applied(events), [])
                self.assertIn("Nothing was applied.", errors)

    def test_failures_after_the_apply_started_are_reported_as_such(self):
        for failure in ("apply_error", "state_not_recorded", "lineage", "input_change", "image_changed",
                        "never_ready"):
            with self.subTest(failure=failure):
                events, output, errors, error, _ = self.run_fixture(**{failure: True})
                self.assertIsInstance(error, diagnostic.CheckError)
                self.assertEqual(len(self.applied(events)), 1)
                self.assertIn("The apply was started", errors)

    def test_a_follow_up_plan_outside_the_reviewed_set_is_a_failure(self):
        follow_up = approved_plan(False, False)
        follow_up["resource_changes"].append({
            "address": "azapi_resource.logs", "type": "azapi_resource", "mode": "managed",
            "change": {"actions": ["update"], "before": {"tags": {}}, "after": {"tags": {"a": "b"}}},
        })
        events, output, errors, error, _ = self.run_fixture(plans=[approved_plan(), follow_up])
        self.assertIsInstance(error, diagnostic.CheckError)
        self.assertIn("The apply was started", errors)

    def test_only_check_or_apply_is_accepted(self):
        for operation in ("", "destroy", "plan"):
            with self.subTest(operation=operation), self.assertRaises(diagnostic.CheckError):
                apply.run({**environment(), "TF_LAB_APPLY_OPERATION": operation})


class WorkflowContractTests(unittest.TestCase):
    def test_protected_workflow_contract(self):
        workflow = (diagnostic.ROOT / ".github" / "workflows" / "apply-lab-terraform.yml").read_text()
        for required in (
            "workflow_dispatch:", "github.ref == 'refs/heads/main'", "terraform-state-access",
            "group: deploy-lab", "cancel-in-progress: false", "[self-hosted, linux, lab-runner]",
            "environment: terraform-state", "id-token: write", "persist-credentials: false",
            "terraform_wrapper: false", "secrets.TF_LAB_PLAN_CONFIG", "TF_LAB_APPLY_OPERATION",
            "if: always()", "--cleanup", "options: [check, apply]", "default: check",
        ):
            self.assertIn(required, workflow)
        for forbidden in ("upload-artifact", "-target", "-refresh=false", "-lock=false", "-auto-approve",
                          "pull_request", "push:", "schedule:"):
            self.assertNotIn(forbidden, workflow)


if __name__ == "__main__":
    unittest.main()

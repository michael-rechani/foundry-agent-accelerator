import contextlib
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import check_lab_router_plan as diagnostic
import check_lab_terraform_plan as lab
import check_platform_router_plan as platform_diagnostic
from test_check_lab_terraform_plan import (
    APP_ID,
    DIGEST,
    REVISION,
    SUBSCRIPTION,
    environment,
    plan as lab_plan,
    platform as lab_platform,
    protected_config,
    state as lab_state,
    values as lab_values,
)
from test_check_platform_router_plan import ACCOUNT, state_object as platform_state_object

PROJECT = "private-project"
PROJECT_ID = ACCOUNT + "/projects/" + PROJECT
ENDPOINT = f"https://foundry-private.services.ai.azure.com/api/projects/{PROJECT}"
APP = {"app_id": APP_ID, "app_name": "lab-fixture"}


def platform_state():
    state = platform_state_object()
    state["outputs"].update({
        "foundry_account_name": {"value": "foundry-private"},
        "foundry_project_name": {"value": PROJECT},
        "foundry_project_id": {"value": PROJECT_ID},
        "foundry_project_endpoint": {"value": ENDPOINT},
        "model_deployment_name": {"value": "gpt-4.1"},
        "model_router_deployment_name": {"value": "model-router"},
        "model_deployment_names": {"value": ["gpt-4.1", "model-router"]},
    })
    return state


def context():
    return diagnostic.platform_context(json.dumps(platform_state()).encode(), SUBSCRIPTION)


def router_response():
    return {
        "id": ACCOUNT + "/deployments/model-router",
        "sku": {"name": "GlobalStandard", "capacity": 10},
        "properties": {
            "provisioningState": "Succeeded",
            "model": {"format": "OpenAI", "name": "model-router", "version": "2025-11-18"},
            "routing": {"mode": "balanced", "models": deepcopy(platform_diagnostic.ROUTER_MODELS)},
        },
    }


def plan(action="update"):
    values = lab_values(lab_platform())
    result = lab_plan(values)
    entries = [
        {"name": "FOUNDRY_PROJECT_ENDPOINT", "value": ENDPOINT},
        {"name": "WORKBENCH_AGENT_CREATION_MODEL", "value": "gpt-4.1"},
        {"name": "WORKBENCH_FOUNDRY_PROJECT_ID", "value": PROJECT_ID},
        {"name": "WORKBENCH_MODE", "value": "private"},
    ]
    before = {"id": APP_ID, "template": [{"container": [{
        "name": "workbench", "image": "fixture.azurecr.io/workbench@" + DIGEST, "env": entries,
    }]}]}
    after = deepcopy(before)
    after["template"][0]["container"][0]["env"][1]["value"] = "model-router"
    if action == "no-op":
        before = deepcopy(after)
    result["resource_changes"].append({
        "address": diagnostic.APP, "type": "azurerm_container_app", "mode": "managed",
        "change": {"actions": [action], "before": before, "after": after, "after_unknown": {}},
    })
    return result


class PlatformAndReadbackTests(unittest.TestCase):
    def test_platform_state_requires_the_same_project_and_deployed_router(self):
        self.assertEqual(context()["project_id"], PROJECT_ID)
        alterations = (
            lambda item: item["outputs"]["foundry_account_name"].update(value="other"),
            lambda item: item["outputs"]["foundry_project_name"].update(value="../other"),
            lambda item: item["outputs"]["foundry_project_id"].update(value=PROJECT_ID + "/other"),
            lambda item: item["outputs"]["foundry_project_endpoint"].update(value="https://other.invalid"),
            lambda item: item["outputs"]["model_deployment_name"].update(value="model-router"),
            lambda item: item["outputs"]["model_router_deployment_name"].update(value=None),
            lambda item: item["outputs"]["model_deployment_names"].update(value=["gpt-4.1"]),
            lambda item: item["outputs"]["model_deployment_names"].update(value=["gpt-4.1", {}, "model-router"]),
            lambda item: item["outputs"]["model_deployment_names"].update(
                value=["gpt-4.1", "model-router", "model-router"],
            ),
        )
        for change in alterations:
            item = platform_state()
            change(item)
            with self.subTest(change=change), self.assertRaises(diagnostic.CheckError) as raised:
                diagnostic.platform_context(json.dumps(item).encode(), SUBSCRIPTION)
            self.assertNotIn(ACCOUNT, str(raised.exception))

    def test_live_readback_checks_the_exact_resource_sku_and_routing(self):
        with (patch.object(diagnostic, "azure_token", return_value="fixture-token") as token,
              patch.object(diagnostic, "json_response", return_value=router_response()) as request):
            result = diagnostic.live_router({}, context())
        self.assertEqual(result[1:5], ("2025-11-18", "GlobalStandard", 10, "balanced"))
        token.assert_called_once_with({}, scope="https://management.azure.com/.default")
        self.assertEqual(
            request.call_args.args[0],
            "https://management.azure.com" + ACCOUNT + "/deployments/model-router?api-version=2025-12-01",
        )
        self.assertEqual(request.call_args.kwargs["headers"], {"Authorization": "Bearer fixture-token"})

    def test_live_readback_rejects_unexpected_or_malformed_routing(self):
        alterations = (
            lambda item: item.update(id=ACCOUNT + "/deployments/other"),
            lambda item: item["sku"].update(capacity=20),
            lambda item: item["sku"].update(name="Standard"),
            lambda item: item["properties"].update(provisioningState="Failed"),
            lambda item: item["properties"]["model"].update(version="other"),
            lambda item: item["properties"]["routing"].update(mode="quality"),
            lambda item: item["properties"]["routing"].update(models=[]),
            lambda item: item["properties"]["routing"]["models"][0].update(version=None),
            lambda item: item["properties"]["routing"]["models"][0].update(name={"private": "value"}),
            lambda item: item["properties"]["routing"]["models"].append(
                deepcopy(item["properties"]["routing"]["models"][0]),
            ),
        )
        for change in alterations:
            item = router_response()
            change(item)
            with (self.subTest(change=change),
                  patch.object(diagnostic, "azure_token", return_value="fixture-token"),
                  patch.object(diagnostic, "json_response", return_value=item),
                  self.assertRaises(diagnostic.CheckError) as raised):
                diagnostic.live_router({}, context())
            self.assertNotIn(ACCOUNT, str(raised.exception))
            self.assertNotIn("fixture-token", str(raised.exception))


class PlanTests(unittest.TestCase):
    def review(self, value, exit_code=2):
        return diagnostic.review_plan(value, exit_code, lab_values(lab_platform()), APP, context())

    def test_only_the_fixed_model_to_router_update_is_accepted(self):
        self.assertEqual(self.review(plan()), "model-update")
        self.assertEqual(self.review(plan("no-op"), 0), "already-configured")

    def test_rejects_other_environment_or_resource_changes(self):
        def append_environment(item):
            item["resource_changes"][-1]["change"]["after"]["template"][0]["container"][0]["env"].append(
                {"name": "PRIVATE_OTHER_SETTING", "value": "private-value"},
            )

        def change_project(item):
            item["resource_changes"][-1]["change"]["after"]["template"][0]["container"][0]["env"][0]["value"] = (
                "https://other.invalid"
            )

        def change_model_source(item):
            item["resource_changes"][-1]["change"]["before"]["template"][0]["container"][0]["env"][1]["value"] = (
                "custom-model"
            )

        def change_profile(item):
            item["resource_changes"][-1]["change"]["after"]["template"][0]["container"][0]["env"].append(
                {"name": "WORKBENCH_AGENT_CREATION_MODELS", "value": '{"reasoning":"other"}'},
            )

        def add_unrelated_change(item):
            item["resource_changes"].append({
                "address": "azurerm_subnet.this", "type": "azurerm_subnet", "mode": "managed",
                "change": {"actions": ["update"], "before": {"name": "old"}, "after": {"name": "new"}},
            })

        def image_not_active(item):
            for side in ("before", "after"):
                item["resource_changes"][-1]["change"][side]["template"][0]["container"][0]["image"] = (
                    "fixture.azurecr.io/workbench@sha256:" + "b" * 64
                )

        alterations = (
            append_environment,
            change_project,
            change_model_source,
            change_profile,
            add_unrelated_change,
            image_not_active,
            lambda item: item["resource_changes"][0]["change"].update(actions=["update"], after={"enabled": False}),
            lambda item: item.update(resource_drift=[deepcopy(item["resource_changes"][-1])]),
            lambda item: item["resource_changes"][-1]["change"].update(after_unknown={"template": True}),
            lambda item: item["resource_changes"][-1]["change"].update(importing={"id": "private-value"}),
            lambda item: item.update(checks=[{"status": "unknown"}]),
            lambda item: item.update(output_changes={"private": {"actions": ["update"]}}),
            lambda item: item["variables"]["platform_state"].update(value=None),
            lambda item: item["resource_changes"][-1]["change"]["after"].update(id=APP_ID + "-other"),
            lambda item: item["resource_changes"].append(deepcopy(item["resource_changes"][-1])),
            lambda item: item["resource_changes"][-1].update(type="other"),
            lambda item: item["resource_changes"][-1].update(mode="data"),
        )
        for change in alterations:
            item = plan()
            change(item)
            with self.subTest(change=change), self.assertRaises(diagnostic.CheckError) as raised:
                self.review(item)
            self.assertNotIn("private-value", str(raised.exception))
            self.assertNotIn(ACCOUNT, str(raised.exception))

    def test_noop_must_be_consistent_and_preview_must_be_enabled(self):
        bad_noop = plan("no-op")
        bad_noop["resource_changes"][-1]["change"]["before"]["tags"] = {"private": "old"}
        with self.assertRaises(diagnostic.CheckError):
            self.review(bad_noop, 0)
        bad_target = plan()
        bad_target["resource_changes"][0]["change"]["after"]["enabled"] = False
        with self.assertRaises(diagnostic.CheckError):
            self.review(bad_target)
        disabled = plan()
        for side in ("before", "after"):
            disabled["resource_changes"][-1]["change"][side]["template"][0]["container"][0]["env"].append(
                {"name": "WORKBENCH_LIBRARY_PREVIEW_ENABLED", "value": "false"},
            )
        with self.assertRaises(diagnostic.CheckError):
            self.review(disabled)
        with self.assertRaises(diagnostic.CheckError):
            self.review(plan(), 0)


class RunAndWorkflowTests(unittest.TestCase):
    def run_fixture(self, failure=None):
        seen, counts = [], {}
        values = lab_values(lab_platform())
        if failure == "no-platform":
            values = lab_values()

        class FakeBlobs:
            def __init__(self, _environment):
                pass

            def snapshot(self, name):
                seen.append(name)
                counts[name] = counts.get(name, 0) + 1
                body = {
                    lab.LAB_STATE: lab_state(),
                    lab.LAB_INPUTS: b"private-input",
                    lab.PLATFORM_STATE: json.dumps(platform_state()).encode(),
                }[name]
                tag, metadata = "v1", {}
                if counts[name] > 1 and failure == "input" and name == lab.LAB_INPUTS:
                    body = b"different-input"
                if counts[name] > 1 and failure == "platform" and name == lab.PLATFORM_STATE:
                    tag = "v2"
                if counts[name] > 1 and failure == "metadata" and name == lab.LAB_STATE:
                    metadata = {"x-ms-meta-test": "changed"}
                return body, tag, metadata

        class FakeTerraform:
            def __init__(self, root, scratch, _environment, inputs):
                self.scratch = scratch
                if inputs != b"private-input" or json.loads(
                    (root / "diagnostic.auto.tfvars.json").read_text(),
                ) != {"image_digest": DIGEST}:
                    raise AssertionError("The diagnostic must use the protected inputs and active image.")
                if "use_oidc             = true" not in (root / "platform.tf").read_text():
                    raise AssertionError("The staged platform state must use OIDC.")
                (scratch / "private-plan").write_text("private")

            def inputs_resolved(self):
                return values

            def full_plan(self):
                if failure == "plan":
                    raise diagnostic.CheckError("Provider diagnostics withheld.")
                return plan(), 2

        def fake_stage(scratch, _environment):
            root = scratch / "staged"
            root.mkdir()
            (root / "platform.tf").write_text("    use_azuread_auth     = true\n    use_cli              = true\n")
            return root

        revisions = [(REVISION, DIGEST), (REVISION + "-new", DIGEST) if failure == "revision" else (REVISION, DIGEST)]
        readbacks = [("router",), ("changed",) if failure == "router" else ("router",)]
        with tempfile.TemporaryDirectory() as folder:
            runtime = {**environment(folder), **protected_config()}
            with (patch.object(diagnostic, "configuration", return_value=runtime),
                  patch.object(diagnostic, "LabBlobs", FakeBlobs),
                  patch.object(diagnostic, "LabTerraform", FakeTerraform),
                  patch.object(diagnostic, "stage_sources", side_effect=fake_stage),
                  patch.object(diagnostic, "current_image", side_effect=revisions),
                  patch.object(diagnostic, "live_router", side_effect=readbacks),
                  contextlib.redirect_stdout(io.StringIO()) as output):
                if failure:
                    with self.assertRaises(diagnostic.CheckError):
                        diagnostic.run(environment(folder))
                else:
                    diagnostic.run(environment(folder))
            self.assertEqual(list(Path(folder).iterdir()), [])
        self.assertGreaterEqual(counts[lab.LAB_STATE], 2)
        if failure != "metadata":
            self.assertGreaterEqual(counts[lab.LAB_INPUTS], 2)
        self.assertNotIn("private-input", output.getvalue())
        self.assertNotIn(ACCOUNT, output.getvalue())
        if not failure:
            self.assertIn("model-update", output.getvalue())
            self.assertIn("No infrastructure apply ran", output.getvalue())
            self.assertEqual(counts[lab.PLATFORM_STATE], 2)

    def test_run_is_check_only_and_cleans_private_scratch(self):
        self.run_fixture()

    def test_failures_invalidate_the_result_and_clean_private_scratch(self):
        for failure in ("input", "platform", "metadata", "no-platform", "plan", "revision", "router"):
            with self.subTest(failure=failure):
                self.run_fixture(failure)

    def test_workflow_is_manual_private_main_only_and_has_no_apply(self):
        workflow = (lab.ROOT / ".github" / "workflows" / "check-lab-router-plan.yml").read_text()
        for required in (
            "workflow_dispatch:", "github.ref == 'refs/heads/main'", "terraform-state-access",
            "runs-on: [self-hosted, linux, lab-runner]", "environment: terraform-state",
            "TF_LAB_PLAN_CONFIG", "check_lab_router_plan.py", "--cleanup",
        ):
            self.assertIn(required, workflow)
        for forbidden in ("pull_request:", "workflow_call:", "terraform apply", "upload-artifact"):
            self.assertNotIn(forbidden, workflow)


if __name__ == "__main__":
    unittest.main()

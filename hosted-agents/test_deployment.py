import io
import json
import stat
import tempfile
import unittest
from contextlib import redirect_stdout
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from zipfile import ZipFile

from deployment import (
    KNOWLEDGE_CHECK_PROMPT, AgentProfile, active_release, candidate_model_matches, cleanup_failed_version, create_package, smoke_test,
    verify_delegation, verify_specialist_endpoints, concrete_route, verify_recovery_targets, verify_route,
)

def invalid_rules(version="1"):
    valid = {"type": "FixedRatio", "agent_version": version, "traffic_percentage": 100}
    return [
        [],
        [{"agent_version": version, "traffic_percentage": 100}],
        [{**valid, "type": "Other"}],
        [{**valid, "type": "fixedratio"}],
        [{**valid, "type": None}],
        [{**valid, "type": True}],
        [{**valid, "type": {}}],
        [{"type": "FixedRatio", "agent_version": version}],
        [{**valid, "traffic_percentage": None}],
        [{**valid, "traffic_percentage": True}],
        [{**valid, "traffic_percentage": "100"}],
        [{**valid, "traffic_percentage": 100.0}],
        [{**valid, "traffic_percentage": -1}],
        [{**valid, "traffic_percentage": 101}],
        [{**valid, "traffic_percentage": 50}, {**valid, "agent_version": "3", "traffic_percentage": 50}],
        [valid, {**valid, "agent_version": "3", "traffic_percentage": 0}],
    ]

class DeploymentPackageTests(unittest.TestCase):
    def test_packages_are_deterministic_with_portable_regular_file_permissions(self):
        source = Path(__file__).parent / "case-review-agent"
        with tempfile.TemporaryDirectory() as temporary:
            first, second = Path(temporary) / "first.zip", Path(temporary) / "second.zip"
            create_package(source, first)
            create_package(source, second)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            with ZipFile(first) as archive:
                for info in archive.infolist():
                    self.assertEqual(info.create_system, 3)
                    self.assertTrue(stat.S_ISREG(info.external_attr >> 16))

    def test_package_includes_reviewed_instructions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source"
            source.mkdir()
            (source / "main.py").write_text("print('ready')\n", encoding="utf-8")
            (source / "requirements.txt").write_text("example==1\n", encoding="utf-8")
            (source / "instructions.md").write_text("Use supplied facts.\n", encoding="utf-8")
            destination = Path(temporary) / "agent.zip"

            create_package(source, destination)

            with ZipFile(destination) as archive:
                self.assertEqual(
                    set(archive.namelist()),
                    {"main.py", "requirements.txt", "instructions.md"},
                )

    def test_package_requires_runtime_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary)
            destination = source / "agent.zip"

            with self.assertRaisesRegex(FileNotFoundError, "main.py"):
                create_package(source, destination)

    def test_coordinator_package_contains_runtime_and_instructions(self) -> None:
        source = Path(__file__).parent / "review-coordinator-agent"

        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "coordinator.zip"
            create_package(source, destination)

            with ZipFile(destination) as archive:
                self.assertEqual(
                    set(archive.namelist()),
                    {"main.py", "requirements.txt", "instructions.md", "configuration.py", "review_output.py",
                     "hosted_runtime.py"},
                )

    def test_review_samples_ship_their_shared_files_and_basic_responses_stays_standalone(self) -> None:
        shared = Path(__file__).parent
        for name in ("case-review-agent", "application-review-agent", "review-coordinator-agent"):
            with self.subTest(agent=name), tempfile.TemporaryDirectory() as temporary:
                destination = Path(temporary) / "agent.zip"
                create_package(shared / name, destination)
                with ZipFile(destination) as archive:
                    for file in ("review_output.py", "hosted_runtime.py"):
                        self.assertEqual(archive.read(file), (shared / file).read_bytes())
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "agent.zip"
            create_package(shared / "basic-responses-agent", destination)
            with ZipFile(destination) as archive:
                self.assertEqual(set(archive.namelist()), {"main.py", "requirements.txt", "instructions.md"})

    def test_demo_agents_package_the_reviewed_scenario_instructions(self) -> None:
        for name in ("case-review-agent", "application-review-agent"):
            with self.subTest(agent=name), tempfile.TemporaryDirectory() as temporary:
                source = Path(__file__).parent / name
                destination = Path(temporary) / "agent.zip"
                create_package(source, destination)
                with ZipFile(destination) as archive:
                    self.assertEqual(
                        archive.read("instructions.md"),
                        (source / "instructions.md").read_bytes(),
                    )


class DelegationTests(unittest.TestCase):
    def response(self, items):
        response = MagicMock()
        response.model_dump.return_value = {"output": items}
        return response

    def items(self, tool="review_application", call_id="call-1", output=None):
        return [
            {"type": "function_call", "name": tool, "call_id": "call-1"},
            {"type": "function_call_output", "call_id": call_id, "output": output or json.dumps(
                {"status": "succeeded", "agent": "application-review-agent", "output": "finding"}
            )},
        ]

    def test_requires_matching_successful_execution_for_each_tool(self):
        for tool in ("review_application", "review_case"):
            verify_delegation(self.response(self.items(tool=tool)), tool)

    def test_rejects_unverified_delegation(self):
        for items in (
            [], self.items(tool="wrong"), self.items(call_id="unrelated"),
            self.items(output="Tool failed"), self.items(output='{"status":"failed"}'),
            self.items(output='[]'), self.items()[:1], self.items() * 2,
        ):
            with self.subTest(items=items), self.assertRaises(RuntimeError):
                verify_delegation(self.response(items), "review_application")

    def test_nonempty_failed_response_does_not_pass_smoke_test(self):
        client = MagicMock()
        response = SimpleNamespace(status="failed", output_text="Something went wrong")
        client.get_openai_client.return_value.__enter__.return_value.responses.create.return_value = response
        with self.assertRaisesRegex(RuntimeError, "completed"):
            smoke_test(client, "agent", "review")

    def test_checks_expected_agent_when_configured(self):
        response = self.response(self.items())
        verify_delegation(response, "review_application", "application-review-agent")
        with self.assertRaisesRegex(RuntimeError, "unexpected agent"):
            verify_delegation(response, "review_application", "different-agent")


class LookupRetryTests(unittest.TestCase):
    TOOL = "search_policy_guidance"
    REPLY = "UNIQUE-REPLY-TEXT"
    GOOD = {"status": "succeeded", "agent": "case-review-agent", "output": "passage", "retrieval": True,
            "source_ids": ["POL-EVID-001"]}

    def response(self, items=None, text=REPLY, status="completed"):
        return SimpleNamespace(
            status=status, output_text=text, model_dump=lambda: {"output": [] if items is None else items},
        )

    def lookup(self, receipt=None, tool=TOOL, call_id="call-1"):
        items = [{"type": "function_call", "name": tool, "call_id": "call-1"}]
        if receipt is not False:
            items.append({"type": "function_call_output", "call_id": call_id,
                          "output": json.dumps(self.GOOD if receipt is None else receipt)})
        return self.response(items)

    def run_check(self, *responses, tool=TOOL, agent=None):
        client = MagicMock()
        create = client.get_openai_client.return_value.__enter__.return_value.responses.create
        create.side_effect = list(responses)
        output = io.StringIO()
        error = None
        with redirect_stdout(output):
            try:
                smoke_test(client, "case-review-agent", KNOWLEDGE_CHECK_PROMPT, tool, agent)
            except RuntimeError as raised:
                error = raised
        return create.call_count, output.getvalue(), error

    def test_a_skipped_lookup_is_retried_once_and_the_retry_is_reported(self):
        calls, output, error = self.run_check(self.response(), self.lookup())
        self.assertIsNone(error)
        self.assertEqual(calls, 2)
        self.assertIn(f"Attempt 1 of 2 made no {self.TOOL} call; retrying once", output)
        self.assertIn(f"Smoke test passed: {self.TOOL}", output)
        self.assertNotIn(self.REPLY, output)

    def test_a_first_attempt_lookup_passes_without_a_retry(self):
        calls, output, error = self.run_check(self.lookup())
        self.assertIsNone(error)
        self.assertEqual(calls, 1)
        self.assertNotIn("Attempt", output)

    def test_two_skips_fail_with_the_existing_message_after_one_retry(self):
        calls, output, error = self.run_check(self.response(), self.response(), self.lookup())
        self.assertEqual(str(error), f"Expected exactly one {self.TOOL} tool call")
        self.assertEqual(calls, 2)
        self.assertIn("Attempt 1 of 2 made no", output)
        self.assertIn("Attempt 2 of 2 made no", output)
        self.assertEqual(output.count("retrying once"), 1)
        self.assertNotIn("Smoke test passed", output)

    def test_other_failures_are_not_retried(self):
        two_calls = self.lookup()
        two_calls = self.response(two_calls.model_dump()["output"] * 2)
        failures = {
            "wrong tool": self.lookup(tool="other_tool"),
            "two calls": two_calls,
            "no receipt": self.lookup(receipt=False),
            "unmatched receipt": self.lookup(call_id="unrelated"),
            "invalid receipt": self.lookup(receipt={"status": "failed"}),
            "no passages": self.lookup({**self.GOOD, "source_ids": []}),
            "not completed": self.response(status="failed"),
            "empty reply": self.response(text=" "),
        }
        for name, first in failures.items():
            with self.subTest(failure=name):
                calls, output, error = self.run_check(first, self.lookup())
                self.assertIsInstance(error, RuntimeError)
                self.assertEqual(calls, 1)
                self.assertNotIn("Attempt", output)
                self.assertNotIn("retrying", output)

    def test_wrong_agent_is_not_retried(self):
        calls, _, error = self.run_check(self.lookup(), self.lookup(), agent="different-agent")
        self.assertRegex(str(error), "unexpected agent")
        self.assertEqual(calls, 1)

    def test_only_the_lookup_check_gets_a_retry(self):
        for tool, agent in (("review_application", "application-review-agent"), ("review_case", None)):
            with self.subTest(tool=tool):
                calls, output, error = self.run_check(self.response(), self.lookup(), tool=tool, agent=agent)
                self.assertIsInstance(error, RuntimeError)
                self.assertEqual(calls, 1)
                self.assertNotIn("Attempt", output)

    def test_a_retrieved_claim_without_a_lookup_is_flagged_without_printing_the_reply(self):
        for text in ("Guidance was RETRIEVED: see POL-EVID-001.", "I retrieved the policy.", "I searched the index."):
            with self.subTest(text=text):
                _, output, error = self.run_check(self.response(text=text), self.lookup())
                self.assertIsNone(error)
                self.assertIn("Attempt 1's reply claims guidance was retrieved although no lookup ran", output)
                self.assertNotIn(text, output)

    def test_a_reply_that_makes_no_claim_is_not_flagged(self):
        _, output, _ = self.run_check(self.response(text="Nothing to report."), self.lookup())
        self.assertIn("made no", output)
        self.assertNotIn("claims", output)

    def test_a_claim_on_the_final_skipped_attempt_is_flagged_before_failing(self):
        _, output, error = self.run_check(self.response(), self.response(text="Guidance retrieved."))
        self.assertIsInstance(error, RuntimeError)
        self.assertNotIn("Attempt 1's reply claims", output)
        self.assertIn("Attempt 2's reply claims guidance was retrieved", output)


class SpecialistPreflightTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = MagicMock()
        self.profile = AgentProfile(Path("."), "coordinator", "description", "instructions", "", (
            ("review", "inspect", "specialist"),
            ("review again", "inspect", "specialist"),
        ))
        self.rule = SimpleNamespace(type="FixedRatio", agent_version="1", traffic_percentage=100)
        self.endpoint = SimpleNamespace(
            protocol_configuration=SimpleNamespace(responses={}),
            version_selector=SimpleNamespace(version_selection_rules=[self.rule]),
        )
        self.client.agents.get.return_value.name = "specialist"
        self.client.agents.get.return_value.state = "enabled"
        self.client.agents.get.return_value.configuration_state = "enabled"
        self.client.agents.get.return_value.agent_endpoint = self.endpoint
        self.client.agents.get_version.return_value = {"name": "specialist", "version": "1", "status": "active"}

    def test_parent_states_and_symbolic_routes_refuse_specialists(self):
        for field in ("state", "configuration_state"):
            for value in (None, "disabled", "unknown", True, {}, 1):
                with self.subTest(field=field, value=value):
                    setattr(self.client.agents.get.return_value, field, value)
                    with self.assertRaisesRegex(RuntimeError, "explicitly enabled"):
                        verify_specialist_endpoints(self.client, self.profile, "coordinator")
                    self.client.agents.get_version.assert_not_called()
                    self.client.agents.enable.assert_not_called()
                    self.client.agents.update_details.assert_not_called()
                    setattr(self.client.agents.get.return_value, field, "enabled")
        self.rule.agent_version = "@latest"
        with self.assertRaisesRegex(RuntimeError, "concrete"):
            verify_specialist_endpoints(self.client, self.profile, "coordinator")
        self.client.agents.get_version.assert_not_called()

    def test_refuses_specialist_version_identity_mismatch(self):
        for name, version in (("other", "1"), ("specialist", "2"), (None, "1"), ("specialist", None)):
            with self.subTest(name=name, version=version):
                self.client.agents.get_version.return_value = {"name": name, "version": version, "status": "active"}
                with self.assertRaisesRegex(RuntimeError, "not active"):
                    verify_specialist_endpoints(self.client, self.profile, "coordinator")
                self.client.agents.update_details.assert_not_called()
                self.client.agents.delete_version.assert_not_called()
                self.client.agents.enable.assert_not_called()

    def test_checks_each_dependency_with_consistent_state_without_mutations(self) -> None:
        verify_specialist_endpoints(self.client, self.profile, "coordinator")
        self.assertEqual([call[0] for call in self.client.agents.mock_calls], ["get", "get_version", "get"])
        self.assertEqual(self.client.agents.get.call_count, 2)
        self.client.agents.get.assert_called_with(agent_name="specialist")
        self.client.agents.get_version.assert_called_once_with(agent_name="specialist", agent_version="1")

    def test_rechecks_specialist_state_and_route_after_version_read(self):
        for change in ("state", "configuration_state", "route"):
            with self.subTest(change=change):
                self.setUp()

                def read_version(*, agent_name, agent_version, change=change):
                    if change == "route":
                        self.rule.agent_version = "2"
                    else:
                        setattr(self.client.agents.get.return_value, change, "disabled")
                    return {"name": agent_name, "version": agent_version, "status": "active"}

                self.client.agents.get_version.side_effect = read_version
                with self.assertRaises(RuntimeError):
                    verify_specialist_endpoints(self.client, self.profile, "coordinator")
                self.client.agents.create_version_from_code.assert_not_called()
                self.client.agents.update_details.assert_not_called()
                self.client.agents.delete_version.assert_not_called()
                self.client.agents.enable.assert_not_called()

    def test_rejects_missing_or_unrouted_responses_endpoint(self) -> None:
        for endpoint in (None, SimpleNamespace(), SimpleNamespace(
            protocol_configuration=SimpleNamespace(responses=None),
            version_selector=self.endpoint.version_selector,
        )):
            with self.subTest(endpoint=endpoint), self.assertRaisesRegex(RuntimeError, "Responses endpoint"):
                self.client.agents.get.return_value.state = "enabled"
                self.client.agents.get.return_value.configuration_state = "enabled"
                self.client.agents.get.return_value.agent_endpoint = endpoint
                verify_specialist_endpoints(self.client, self.profile, "coordinator")

    def test_rejects_malformed_responses_protocol(self) -> None:
        for responses in (False, True, 0, "responses", []):
            with self.subTest(responses=responses), self.assertRaisesRegex(RuntimeError, "Responses endpoint"):
                self.endpoint.protocol_configuration.responses = responses
                verify_specialist_endpoints(self.client, self.profile, "coordinator")
        self.client.agents.get_version.assert_not_called()
        self.client.agents.update_details.assert_not_called()
        self.client.agents.delete_version.assert_not_called()
        self.client.agents.enable.assert_not_called()

    def test_rejects_invalid_traffic_rules(self) -> None:
        for percentage in (None, True, -1, 0, 50, 101, float("nan")):
            with self.subTest(percentage=percentage), self.assertRaises(RuntimeError):
                self.rule.traffic_percentage = percentage
                verify_specialist_endpoints(self.client, self.profile, "coordinator")

    def test_rejects_inactive_or_missing_versions(self) -> None:
        self.client.agents.get_version.return_value = {"name": "specialist", "version": "1", "status": "creating"}
        with self.assertRaisesRegex(RuntimeError, "not active"):
            verify_specialist_endpoints(self.client, self.profile, "coordinator")
        self.client.agents.get_version.return_value = {"name": "specialist", "version": "1", "status": "active", "draft": True}
        with self.assertRaisesRegex(RuntimeError, "not active"):
            verify_specialist_endpoints(self.client, self.profile, "coordinator")
        self.rule.agent_version = None
        with self.assertRaisesRegex(RuntimeError, "concrete"):
            verify_specialist_endpoints(self.client, self.profile, "coordinator")

    def test_rejects_unsupported_and_split_rules_before_version_reads(self):
        for rules in invalid_rules():
            with self.subTest(rules=rules):
                self.endpoint.version_selector.version_selection_rules = rules
                with self.assertRaises(RuntimeError):
                    verify_specialist_endpoints(self.client, self.profile, "coordinator")
        self.client.agents.get_version.assert_not_called()
        self.client.agents.create_version_from_code.assert_not_called()
        self.client.agents.update_details.assert_not_called()
        self.client.agents.delete_version.assert_not_called()
        self.client.agents.enable.assert_not_called()

    def test_rejects_self_delegation_and_propagates_read_failure(self) -> None:
        with self.assertRaisesRegex(ValueError, "own endpoint"):
            verify_specialist_endpoints(self.client, self.profile, "specialist")
        self.client.agents.get.assert_not_called()
        self.client.agents.get.side_effect = RuntimeError("access denied")
        with self.assertRaisesRegex(RuntimeError, "access denied"):
            verify_specialist_endpoints(self.client, self.profile, "coordinator")


class RecoveryPreflightTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = MagicMock()
        self.client.agents.get.return_value.name = "agent"
        self.client.agents.get.return_value.state = "enabled"
        self.client.agents.get.return_value.configuration_state = "enabled"
        self.client.agents.get_version.return_value = {"name": "agent", "version": "1", "status": "active"}
        self.rule = SimpleNamespace(type="FixedRatio", agent_version="1", traffic_percentage=100)
        self.endpoint = SimpleNamespace(
            version_selector=SimpleNamespace(version_selection_rules=[self.rule]),
            protocol_configuration=SimpleNamespace(responses={}),
        )

    def test_refuses_mismatched_missing_or_malformed_version_identity(self):
        for details in (
            {"name": "other", "version": "1", "status": "active"},
            {"name": "agent", "version": "2", "status": "active"},
            {"version": "1", "status": "active"},
            {"name": "agent", "status": "active"},
            {"name": "agent", "version": 1, "status": "active"},
            {"name": "agent", "version": "@latest", "status": "active"},
        ):
            with self.subTest(details=details):
                self.client.agents.get_version.return_value = details
                with self.assertRaisesRegex(RuntimeError, "not an active release"):
                    verify_recovery_targets(self.client, "agent", self.endpoint)
                self.client.agents.create_version_from_code.assert_not_called()
                self.client.agents.update_details.assert_not_called()
                self.client.agents.delete_version.assert_not_called()
                self.client.agents.enable.assert_not_called()

    def test_rejects_unsupported_and_split_rules_before_version_reads(self):
        for rules in invalid_rules():
            with self.subTest(rules=rules):
                self.endpoint.version_selector.version_selection_rules = rules
                with self.assertRaises(RuntimeError):
                    verify_recovery_targets(self.client, "agent", self.endpoint)
        self.client.agents.get_version.assert_not_called()
        self.client.agents.create_version_from_code.assert_not_called()
        self.client.agents.update_details.assert_not_called()
        self.client.agents.delete_version.assert_not_called()
        self.client.agents.enable.assert_not_called()

    def test_rejects_inactive_draft_or_malformed_version_details(self):
        for details in ({"status": "creating"}, {"status": "failed"}, {}, {"status": "active", "draft": True},
                        {"status": "active", "draft": None}, {"status": "active", "draft": "false"}):
            with self.subTest(details=details), self.assertRaisesRegex(RuntimeError, "not an active release"):
                self.client.agents.get_version.return_value = {"name": "agent", "version": "1", **details}
                verify_recovery_targets(self.client, "agent", self.endpoint)

    def test_rejects_absent_or_malformed_responses_protocol(self):
        for responses in (None, False, True, 0, "responses", []):
            with self.subTest(responses=responses), self.assertRaisesRegex(RuntimeError, "no Responses endpoint"):
                self.endpoint.protocol_configuration.responses = responses
                verify_recovery_targets(self.client, "agent", self.endpoint)
        self.client.agents.get_version.assert_not_called()
        self.client.agents.create_version_from_code.assert_not_called()
        self.client.agents.update_details.assert_not_called()
        self.client.agents.delete_version.assert_not_called()
        self.client.agents.enable.assert_not_called()

    def test_rejects_unsupported_or_incomplete_traffic_rules(self):
        for percentage in (None, True, -1, 0, 50, 101, float("nan"), float("inf")):
            with self.subTest(percentage=percentage), self.assertRaisesRegex(RuntimeError, "Recovery route"):
                self.rule.traffic_percentage = percentage
                verify_recovery_targets(self.client, "agent", self.endpoint)
        self.client.agents.get_version.assert_not_called()

    def test_rejects_symbolic_or_missing_routes_before_version_reads(self):
        for version in ("@latest", None, ""):
            with self.subTest(version=version), self.assertRaisesRegex(RuntimeError, "Pin the existing"):
                self.rule.agent_version = version
                verify_recovery_targets(self.client, "agent", self.endpoint)
        self.client.agents.get_version.assert_not_called()

    def test_version_read_failures_are_not_treated_as_usable_recovery(self):
        self.client.agents.get_version.side_effect = RuntimeError("unavailable")
        with self.assertRaisesRegex(RuntimeError, "unavailable"):
            verify_recovery_targets(self.client, "agent", self.endpoint)


class DeploymentRollbackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = MagicMock()
        self.client.agents.get_version.return_value = {"name": "agent", "version": "1", "status": "active"}
        self.original = self.route("1")
        self.attempted = self.route("2")
        self.client.agents.get.return_value.name = "agent"
        self.client.agents.get.return_value.state = "enabled"
        self.client.agents.get.return_value.configuration_state = "enabled"
        self.client.agents.get.return_value.agent_endpoint = self.attempted
        self.client.agents.update_details.side_effect = self.restore

    def route(self, version):
        return SimpleNamespace(
            version_selector=SimpleNamespace(
                version_selection_rules=[SimpleNamespace(type="FixedRatio", agent_version=version, traffic_percentage=100)]
            ),
            protocol_configuration=SimpleNamespace(responses={}),
            authorization_schemes=["original"],
        )

    def restore(self, **kwargs):
        self.client.agents.get.return_value.state = "enabled"
        self.client.agents.get.return_value.configuration_state = "enabled"
        self.client.agents.get.return_value.agent_endpoint = kwargs["agent_endpoint"]

    def test_unsupported_original_or_attempted_route_never_authorizes_rollback(self):
        for target in ("original", "attempted"):
            for rules in invalid_rules("1" if target == "original" else "2"):
                with self.subTest(target=target, rules=rules):
                    self.setUp()
                    route = self.original if target == "original" else self.attempted
                    route.version_selector.version_selection_rules = rules
                    self.client.agents.get.return_value.agent_endpoint = self.attempted
                    output = io.StringIO()
                    with redirect_stdout(output):
                        cleanup_failed_version(self.client, "agent", "2", self.original, self.attempted)
                    self.assertIn("manual recovery required", output.getvalue())
                    self.client.agents.update_details.assert_not_called()
                    self.client.agents.delete_version.assert_not_called()
                    self.client.agents.enable.assert_not_called()

    def test_restores_route_without_deleting_candidate(self) -> None:
        cleanup_failed_version(self.client, "agent", "2", self.original, self.attempted)
        self.assertEqual(
            [call[0] for call in self.client.agents.mock_calls],
            ["get", "get", "get_version", "get", "update_details", "get", "get", "get_version", "get"],
        )
        self.assertEqual(self.client.agents.get.return_value.agent_endpoint, self.original)

    def test_parent_state_flip_during_recovery_never_changes_route(self):
        for field in ("state", "configuration_state"):
            for value in ("disabled", None, "unknown", True):
                with self.subTest(field=field, value=value):
                    self.client.reset_mock()
                    self.client.agents.get.return_value.state = "enabled"
                    self.client.agents.get.return_value.configuration_state = "enabled"
                    self.client.agents.get.return_value.agent_endpoint = self.attempted

                    def read_version(*, agent_name, agent_version, field=field, value=value):
                        setattr(self.client.agents.get.return_value, field, value)
                        return {"name": agent_name, "version": agent_version, "status": "active"}

                    self.client.agents.get_version.side_effect = read_version
                    output = io.StringIO()
                    with redirect_stdout(output):
                        cleanup_failed_version(self.client, "agent", "2", self.original, self.attempted)
                    self.assertIn("manual recovery required", output.getvalue())
                    self.client.agents.update_details.assert_not_called()
                    self.client.agents.delete_version.assert_not_called()
                    self.client.agents.delete_session.assert_not_called()
                    self.client.agents.enable.assert_not_called()

    def test_restored_route_retains_sessions_and_reports_retention(self):
        self.client.agents.list_sessions.return_value = [SimpleNamespace(status="active")]
        with redirect_stdout(io.StringIO()) as output:
            cleanup_failed_version(self.client, "agent", "2", self.original, self.attempted)
        self.assertEqual(self.client.agents.get.return_value.agent_endpoint, self.original)
        self.client.agents.delete_version.assert_not_called()
        self.client.agents.delete_session.assert_not_called()
        self.assertIn("Retained failed version 2", output.getvalue())
        self.assertNotIn("Deleted", output.getvalue())

    def test_before_promotion_failure_reports_retention_without_deletion(self):
        self.client.agents.get.return_value.state = "enabled"
        self.client.agents.get.return_value.configuration_state = "enabled"
        self.client.agents.get.return_value.agent_endpoint = self.original
        with redirect_stdout(io.StringIO()) as output:
            cleanup_failed_version(self.client, "agent", "2", self.original, None)
        self.client.agents.update_details.assert_not_called()
        self.client.agents.delete_version.assert_not_called()
        self.assertIn("Retained failed version 2", output.getvalue())

    def test_failed_restore_retains_candidate(self) -> None:
        self.client.agents.update_details.side_effect = RuntimeError("unavailable")
        cleanup_failed_version(self.client, "agent", "2", self.original, self.attempted)
        self.client.agents.delete_version.assert_not_called()

    def test_stale_route_retains_candidate(self) -> None:
        self.original.version_selector.version_selection_rules[0].agent_version = "2"
        cleanup_failed_version(self.client, "agent", "2", self.original, self.attempted)
        self.client.agents.delete_version.assert_not_called()

    def test_failed_route_read_retains_candidate(self) -> None:
        self.client.agents.get.side_effect = RuntimeError("unavailable")
        cleanup_failed_version(self.client, "agent", "2", self.original, self.attempted)
        self.client.agents.update_details.assert_not_called()
        self.client.agents.delete_version.assert_not_called()

    def test_first_deployment_without_route_retains_candidate(self) -> None:
        self.client.agents.get.return_value.state = "enabled"
        self.client.agents.get.return_value.configuration_state = "enabled"
        self.client.agents.get.return_value.agent_endpoint = self.original
        cleanup_failed_version(self.client, "agent", "2", None, self.attempted)
        self.client.agents.update_details.assert_not_called()
        self.client.agents.delete_version.assert_not_called()

    def test_failed_build_preserves_existing_route(self) -> None:
        self.client.agents.get.return_value.state = "enabled"
        self.client.agents.get.return_value.configuration_state = "enabled"
        self.client.agents.get.return_value.agent_endpoint = self.original
        cleanup_failed_version(self.client, "agent", "2", self.original, None)
        self.client.agents.update_details.assert_not_called()
        self.client.agents.get_version.assert_called_once_with(agent_name="agent", agent_version="1")
        self.client.agents.delete_version.assert_not_called()

    def test_failed_first_build_without_previous_route_retains_candidate(self):
        self.client.agents.get.return_value.state = "enabled"
        self.client.agents.get.return_value.configuration_state = "enabled"
        self.client.agents.get.return_value.agent_endpoint = self.original
        cleanup_failed_version(self.client, "agent", "2", None, None)
        self.client.agents.update_details.assert_not_called()
        self.client.agents.delete_version.assert_not_called()

    def test_changed_route_before_promotion_retains_candidate(self):
        self.client.agents.get.return_value.state = "enabled"
        self.client.agents.get.return_value.configuration_state = "enabled"
        self.client.agents.get.return_value.agent_endpoint = self.route("3")
        cleanup_failed_version(self.client, "agent", "2", self.original, None)
        self.client.agents.update_details.assert_not_called()
        self.client.agents.delete_version.assert_not_called()

    def test_failed_promotion_that_left_original_route_does_not_restore_it(self):
        self.client.agents.get.return_value.state = "enabled"
        self.client.agents.get.return_value.configuration_state = "enabled"
        self.client.agents.get.return_value.agent_endpoint = self.original
        cleanup_failed_version(self.client, "agent", "2", self.original, self.attempted)
        self.client.agents.update_details.assert_not_called()
        self.client.agents.delete_version.assert_not_called()

    def test_changed_route_or_endpoint_configuration_is_not_overwritten(self):
        changed_authorization = deepcopy(self.attempted)
        changed_authorization.authorization_schemes = ["different"]
        changed_protocol = deepcopy(self.attempted)
        changed_protocol.protocol_configuration.responses = {"extra": True}
        for endpoint in (self.route("3"), self.route("@latest"), changed_authorization, changed_protocol):
            with self.subTest(endpoint=endpoint):
                self.client.reset_mock()
                self.client.agents.get.return_value.state = "enabled"
                self.client.agents.get.return_value.configuration_state = "enabled"
                self.client.agents.get.return_value.agent_endpoint = endpoint
                cleanup_failed_version(self.client, "agent", "2", self.original, self.attempted)
                self.client.agents.update_details.assert_not_called()
                self.client.agents.delete_version.assert_not_called()

    def test_restore_must_read_back_the_exact_original_endpoint(self):
        for endpoint in (self.attempted, self.route("3")):
            with self.subTest(endpoint=endpoint):
                self.client.reset_mock()
                self.client.agents.get.return_value.state = "enabled"
                self.client.agents.get.return_value.configuration_state = "enabled"
                self.client.agents.get.return_value.agent_endpoint = self.attempted
                self.client.agents.update_details.side_effect = (
                    lambda endpoint=endpoint, **kwargs: setattr(
                        self.client.agents.get.return_value, "agent_endpoint", endpoint,
                    )
                )
                cleanup_failed_version(self.client, "agent", "2", self.original, self.attempted)
                self.client.agents.update_details.assert_called_once()
                self.client.agents.delete_version.assert_not_called()

    def test_unexpected_attempted_route_never_authorizes_restoration(self):
        cleanup_failed_version(self.client, "agent", "2", self.original, self.route("3"))
        self.client.agents.get.assert_not_called()
        self.client.agents.update_details.assert_not_called()
        self.client.agents.delete_version.assert_not_called()

    def test_inactive_or_unconfirmed_recovery_never_overwrites_the_candidate(self):
        for details in ({"status": "failed"}, {"status": "active", "draft": True}, {}):
            with self.subTest(details=details):
                self.client.reset_mock()
                self.client.agents.get.return_value.state = "enabled"
                self.client.agents.get.return_value.configuration_state = "enabled"
                self.client.agents.get.return_value.agent_endpoint = self.attempted
                self.client.agents.get_version.return_value = details
                output = io.StringIO()
                with redirect_stdout(output):
                    cleanup_failed_version(self.client, "agent", "2", self.original, self.attempted)
                self.assertIn("recovery status or cleanup incomplete", output.getvalue())
                self.client.agents.update_details.assert_not_called()
                self.client.agents.delete_version.assert_not_called()

    def test_route_changed_while_checking_recovery_is_not_overwritten(self):
        self.client.agents.get.side_effect = [
            SimpleNamespace(name="agent", state="enabled", configuration_state="enabled", agent_endpoint=self.attempted),
            SimpleNamespace(name="agent", state="enabled", configuration_state="enabled", agent_endpoint=self.route("3")),
        ]
        cleanup_failed_version(self.client, "agent", "2", self.original, self.attempted)
        self.client.agents.update_details.assert_not_called()
        self.client.agents.delete_version.assert_not_called()

    def test_route_changed_after_recovery_status_checks_prevents_candidate_deletion(self):
        self.client.agents.get.side_effect = [
            SimpleNamespace(name="agent", state="enabled", configuration_state="enabled", agent_endpoint=self.attempted),
            SimpleNamespace(name="agent", state="enabled", configuration_state="enabled", agent_endpoint=self.attempted),
            SimpleNamespace(name="agent", state="enabled", configuration_state="enabled", agent_endpoint=self.attempted),
            SimpleNamespace(name="agent", state="enabled", configuration_state="enabled", agent_endpoint=self.original),
            SimpleNamespace(name="agent", state="enabled", configuration_state="enabled", agent_endpoint=self.attempted),
        ]
        cleanup_failed_version(self.client, "agent", "2", self.original, self.attempted)
        self.client.agents.update_details.assert_called_once()
        self.client.agents.delete_version.assert_not_called()

    def test_route_changed_after_unpromoted_cleanup_check_prevents_candidate_deletion(self):
        self.client.agents.get.side_effect = [
            SimpleNamespace(name="agent", state="enabled", configuration_state="enabled", agent_endpoint=self.original),
            SimpleNamespace(name="agent", state="enabled", configuration_state="enabled", agent_endpoint=self.attempted),
        ]
        cleanup_failed_version(self.client, "agent", "2", self.original, None)
        self.client.agents.update_details.assert_not_called()
        self.client.agents.delete_version.assert_not_called()

    def test_recovery_that_becomes_inactive_after_restore_retains_the_candidate(self):
        self.client.agents.get_version.side_effect = [
            {"name": "agent", "version": "1", "status": "active"},
            {"name": "agent", "version": "1", "status": "failed"},
        ]
        cleanup_failed_version(self.client, "agent", "2", self.original, self.attempted)
        self.assertEqual(self.client.agents.get.return_value.agent_endpoint, self.original)
        self.client.agents.update_details.assert_called_once()
        self.client.agents.delete_version.assert_not_called()

    def test_failed_recovery_status_read_retains_candidate_without_exposing_error(self):
        self.client.agents.get_version.side_effect = RuntimeError("private service detail")
        output = io.StringIO()
        with redirect_stdout(output):
            cleanup_failed_version(self.client, "agent", "2", self.original, self.attempted)
        self.assertIn("recovery status or cleanup incomplete", output.getvalue())
        self.assertNotIn("private service detail", output.getvalue())
        self.client.agents.update_details.assert_not_called()
        self.client.agents.delete_version.assert_not_called()

    def test_symbolic_routes_never_authorize_candidate_deletion(self):
        for version in ("@latest", "@unknown", None, ""):
            with self.subTest(version=version):
                self.original.version_selector.version_selection_rules[0].agent_version = version
                self.client.agents.delete_version.reset_mock()
                self.assertFalse(concrete_route(self.original))
                cleanup_failed_version(self.client, "agent", "2", self.original, self.attempted)
                self.client.agents.update_details.assert_not_called()
                self.client.agents.delete_version.assert_not_called()

class ActiveReleaseTests(unittest.TestCase):
    def test_rejects_draft_form_even_with_missing_or_false_draft_flag(self):
        for version in ("draft-1719600000000", "draft-custom", "draft-"):
            for field in ({}, {"draft": False}, {"draft": True}):
                with self.subTest(version=version, field=field):
                    details = {"name": "agent", "version": version, "status": "active", **field}
                    self.assertFalse(active_release(details, "agent", version))
        for version in ("1", "42", "release-v1"):
            for field in ({}, {"draft": False}):
                details = {"name": "agent", "version": version, "status": "active", **field}
                self.assertTrue(active_release(details, "agent", version))

class CandidateModelTests(unittest.TestCase):
    def test_requires_exact_hosted_model_configuration(self):
        for definition in (
            None, {}, {"kind": "prompt", "environment_variables": {"FOUNDRY_MODEL_NAME": "model"}},
            {"kind": "hosted"}, {"kind": "hosted", "environment_variables": None},
            {"kind": "hosted", "environment_variables": []},
            {"kind": "hosted", "environment_variables": {}},
            {"kind": "hosted", "environment_variables": {"FOUNDRY_MODEL_NAME": True}},
            {"kind": "hosted", "environment_variables": {"FOUNDRY_MODEL_NAME": "other"}},
        ):
            with self.subTest(definition=definition):
                self.assertFalse(candidate_model_matches({"definition": definition}, "model"))
        self.assertTrue(candidate_model_matches(
            {"definition": {"kind": "hosted", "environment_variables": {"FOUNDRY_MODEL_NAME": "model"}}},
            "model",
        ))

class RouteVerificationTests(unittest.TestCase):
    def test_promoted_route_rejects_unsupported_discriminators_and_percentages(self):
        client = MagicMock()
        endpoint = SimpleNamespace(
            version_selector=SimpleNamespace(version_selection_rules=[]),
            protocol_configuration=SimpleNamespace(responses={}),
        )
        client.agents.get.return_value.name = "agent"
        client.agents.get.return_value.state = "enabled"
        client.agents.get.return_value.configuration_state = "enabled"
        client.agents.get.return_value.agent_endpoint = endpoint
        for rules in invalid_rules("2"):
            with self.subTest(rules=rules):
                endpoint.version_selector.version_selection_rules = rules
                with self.assertRaisesRegex(RuntimeError, "route was not confirmed"):
                    verify_route(client, "agent", "2", "model")
        client.agents.get_version.assert_not_called()
        client.agents.update_details.assert_not_called()
        client.agents.delete_version.assert_not_called()
        client.agents.enable.assert_not_called()

    def test_refuses_unsafe_parent_states_and_version_identity(self):
        client = MagicMock()
        rule = SimpleNamespace(type="FixedRatio", agent_version="2", traffic_percentage=100)
        client.agents.get.return_value.agent_endpoint = SimpleNamespace(
            version_selector=SimpleNamespace(version_selection_rules=[rule]),
            protocol_configuration=SimpleNamespace(responses={}),
        )
        client.agents.get.return_value.name = "agent"
        client.agents.get.return_value.state = "enabled"
        client.agents.get.return_value.configuration_state = "enabled"
        client.agents.get_version.return_value = {
            "name": "agent", "version": "2", "status": "active",
            "definition": {"kind": "hosted", "environment_variables": {"FOUNDRY_MODEL_NAME": "model"}},
        }
        verify_route(client, "agent", "2", "model")
        for field in ("state", "configuration_state"):
            for value in (None, "disabled", "unknown", True, {}):
                with self.subTest(field=field, value=value):
                    setattr(client.agents.get.return_value, field, value)
                    with self.assertRaisesRegex(RuntimeError, "explicitly enabled"):
                        verify_route(client, "agent", "2", "model")
                    setattr(client.agents.get.return_value, field, "enabled")
        for response in (
            {"name": "other", "version": "2", "status": "active"},
            {"name": "agent", "version": "3", "status": "active"},
            {"name": "agent", "version": 2, "status": "active"},
        ):
            with self.subTest(response=response):
                client.agents.get_version.return_value = response
                with self.assertRaisesRegex(RuntimeError, "not active"):
                    verify_route(client, "agent", "2", "model")
        client.agents.get_version.return_value = {
            "name": "agent", "version": "2", "status": "active",
            "definition": {"kind": "hosted", "environment_variables": {"FOUNDRY_MODEL_NAME": "different"}},
        }
        with self.assertRaisesRegex(RuntimeError, "does not confirm the requested model"):
            verify_route(client, "agent", "2", "model")
        client.agents.update_details.assert_not_called()
        client.agents.delete_version.assert_not_called()
        client.agents.enable.assert_not_called()

    def test_rechecks_promoted_state_and_route_after_version_read(self):
        for change in ("state", "configuration_state", "route"):
            with self.subTest(change=change):
                client = MagicMock()
                rule = SimpleNamespace(type="FixedRatio", agent_version="2", traffic_percentage=100)
                endpoint = SimpleNamespace(
                    version_selector=SimpleNamespace(version_selection_rules=[rule]),
                    protocol_configuration=SimpleNamespace(responses={}),
                )
                client.agents.get.return_value.name = "agent"
                client.agents.get.return_value.state = "enabled"
                client.agents.get.return_value.configuration_state = "enabled"
                client.agents.get.return_value.agent_endpoint = endpoint

                def read_version(*, agent_name, agent_version, change=change, rule=rule, client=client):
                    if change == "route":
                        rule.agent_version = "3"
                    else:
                        setattr(client.agents.get.return_value, change, "disabled")
                    return {
                        "name": agent_name, "version": agent_version, "status": "active",
                        "definition": {"kind": "hosted", "environment_variables": {"FOUNDRY_MODEL_NAME": "model"}},
                    }

                client.agents.get_version.side_effect = read_version
                with self.assertRaises(RuntimeError):
                    verify_route(client, "agent", "2", "model")
                client.agents.update_details.assert_not_called()
                client.agents.delete_version.assert_not_called()
                client.agents.enable.assert_not_called()

    def test_requires_exact_active_responses_route(self):
        client = MagicMock()
        rule = SimpleNamespace(type="FixedRatio", agent_version="2", traffic_percentage=100)
        endpoint = SimpleNamespace(
            version_selector=SimpleNamespace(version_selection_rules=[rule]),
            protocol_configuration=SimpleNamespace(responses={}),
        )
        client.agents.get.return_value.name = "agent"
        client.agents.get.return_value.state = "enabled"
        client.agents.get.return_value.configuration_state = "enabled"
        client.agents.get.return_value.agent_endpoint = endpoint
        client.agents.get_version.return_value = {
            "name": "agent", "version": "2", "status": "active",
            "definition": {"kind": "hosted", "environment_variables": {"FOUNDRY_MODEL_NAME": "model"}},
        }
        verify_route(client, "agent", "2", "model")
        for responses in (None, False, True, 0, "responses", []):
            with self.subTest(responses=responses), self.assertRaisesRegex(RuntimeError, "route was not confirmed"):
                endpoint.protocol_configuration.responses = responses
                verify_route(client, "agent", "2", "model")
        endpoint.protocol_configuration.responses = {}
        for version, percentage in (("@latest", 100), ("1", 100), ("2", 50), ("2", True)):
            with self.subTest(version=version, percentage=percentage), self.assertRaises(RuntimeError):
                rule.agent_version, rule.traffic_percentage = version, percentage
                verify_route(client, "agent", "2", "model")
        rule.agent_version, rule.traffic_percentage = "2", 100
        client.agents.get_version.return_value = {"name": "agent", "version": "2", "status": "creating"}
        with self.assertRaisesRegex(RuntimeError, "not active"):
            verify_route(client, "agent", "2", "model")
        client.agents.get_version.return_value = {"name": "agent", "version": "2", "status": "active", "draft": True}
        with self.assertRaisesRegex(RuntimeError, "not active"):
            verify_route(client, "agent", "2", "model")


if __name__ == "__main__":
    unittest.main()

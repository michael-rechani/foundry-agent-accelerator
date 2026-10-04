import io
import json
import stat
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from zipfile import ZipFile

from deployment import (
    KNOWLEDGE_CHECK_PROMPT, AgentProfile, cleanup_failed_version, create_package, smoke_test,
    verify_delegation, verify_specialist_endpoints, concrete_route, verify_route,
)


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
        self.rule = SimpleNamespace(agent_version="1", traffic_percentage=100)
        self.endpoint = SimpleNamespace(
            protocol_configuration=SimpleNamespace(responses=SimpleNamespace()),
            version_selector=SimpleNamespace(version_selection_rules=[self.rule]),
        )
        self.client.agents.get.return_value.agent_endpoint = self.endpoint
        self.client.agents.get_version.return_value = {"status": "active"}

    def test_checks_each_dependency_once_without_mutations(self) -> None:
        verify_specialist_endpoints(self.client, self.profile, "coordinator")
        self.assertEqual([call[0] for call in self.client.agents.mock_calls], ["get", "get_version"])
        self.client.agents.get.assert_called_once_with(agent_name="specialist")
        self.client.agents.get_version.assert_called_once_with(agent_name="specialist", agent_version="1")

    def test_rejects_missing_or_unrouted_responses_endpoint(self) -> None:
        for endpoint in (None, SimpleNamespace(), SimpleNamespace(
            protocol_configuration=SimpleNamespace(responses=None),
            version_selector=self.endpoint.version_selector,
        )):
            with self.subTest(endpoint=endpoint), self.assertRaisesRegex(RuntimeError, "Responses endpoint"):
                self.client.agents.get.return_value.agent_endpoint = endpoint
                verify_specialist_endpoints(self.client, self.profile, "coordinator")

    def test_rejects_invalid_traffic_rules(self) -> None:
        for percentage in (None, True, -1, 0, 50, 101, float("nan")):
            with self.subTest(percentage=percentage), self.assertRaises(RuntimeError):
                self.rule.traffic_percentage = percentage
                verify_specialist_endpoints(self.client, self.profile, "coordinator")

    def test_rejects_inactive_or_missing_versions(self) -> None:
        self.client.agents.get_version.return_value = {"status": "creating"}
        with self.assertRaisesRegex(RuntimeError, "not active"):
            verify_specialist_endpoints(self.client, self.profile, "coordinator")
        self.rule.agent_version = None
        with self.assertRaisesRegex(RuntimeError, "unversioned"):
            verify_specialist_endpoints(self.client, self.profile, "coordinator")

    def test_checks_all_routed_versions_but_not_unrouted_versions(self) -> None:
        self.rule.traffic_percentage = 60
        self.endpoint.version_selector.version_selection_rules.extend([
            SimpleNamespace(agent_version="2", traffic_percentage=40),
            SimpleNamespace(agent_version="3", traffic_percentage=0),
        ])
        verify_specialist_endpoints(self.client, self.profile, "coordinator")
        self.assertEqual(self.client.agents.get_version.call_count, 2)

    def test_rejects_self_delegation_and_propagates_read_failure(self) -> None:
        with self.assertRaisesRegex(ValueError, "own endpoint"):
            verify_specialist_endpoints(self.client, self.profile, "specialist")
        self.client.agents.get.assert_not_called()
        self.client.agents.get.side_effect = RuntimeError("access denied")
        with self.assertRaisesRegex(RuntimeError, "access denied"):
            verify_specialist_endpoints(self.client, self.profile, "coordinator")


class DeploymentRollbackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = MagicMock()
        self.original = SimpleNamespace(
            version_selector=SimpleNamespace(
                version_selection_rules=[SimpleNamespace(agent_version="1")]
            )
        )
        self.client.agents.get.return_value.agent_endpoint = self.original

    def test_deletes_only_after_restoration_and_route_read(self) -> None:
        cleanup_failed_version(self.client, "agent", "2", self.original, True)
        self.assertEqual(
            [call[0] for call in self.client.agents.mock_calls],
            ["update_details", "get", "delete_version"],
        )

    def test_failed_restore_retains_candidate(self) -> None:
        self.client.agents.update_details.side_effect = RuntimeError("unavailable")
        cleanup_failed_version(self.client, "agent", "2", self.original, True)
        self.client.agents.delete_version.assert_not_called()

    def test_stale_route_retains_candidate(self) -> None:
        self.original.version_selector.version_selection_rules[0].agent_version = "2"
        cleanup_failed_version(self.client, "agent", "2", self.original, True)
        self.client.agents.delete_version.assert_not_called()

    def test_failed_route_read_retains_candidate(self) -> None:
        self.client.agents.get.side_effect = RuntimeError("unavailable")
        cleanup_failed_version(self.client, "agent", "2", self.original, True)
        self.client.agents.delete_version.assert_not_called()

    def test_first_deployment_without_route_retains_candidate(self) -> None:
        self.client.agents.get.return_value.agent_endpoint = None
        cleanup_failed_version(self.client, "agent", "1", None, True)
        self.client.agents.delete_version.assert_not_called()

    def test_failed_build_preserves_existing_route(self) -> None:
        cleanup_failed_version(self.client, "agent", "2", None, False)
        self.client.agents.update_details.assert_not_called()
        self.client.agents.delete_version.assert_called_once()

    def test_symbolic_routes_never_authorize_candidate_deletion(self):
        for version in ("@latest", "@unknown", None, ""):
            with self.subTest(version=version):
                self.original.version_selector.version_selection_rules[0].agent_version = version
                self.client.agents.delete_version.reset_mock()
                self.assertFalse(concrete_route(self.original))
                cleanup_failed_version(self.client, "agent", "2", self.original, True)
                self.client.agents.delete_version.assert_not_called()


class RouteVerificationTests(unittest.TestCase):
    def test_requires_exact_active_responses_route(self):
        client = MagicMock()
        rule = SimpleNamespace(agent_version="2", traffic_percentage=100)
        endpoint = SimpleNamespace(
            version_selector=SimpleNamespace(version_selection_rules=[rule]),
            protocol_configuration=SimpleNamespace(responses=SimpleNamespace()),
        )
        client.agents.get.return_value.agent_endpoint = endpoint
        client.agents.get_version.return_value = {"status": "active"}
        verify_route(client, "agent", "2")
        for version, percentage in (("@latest", 100), ("1", 100), ("2", 50), ("2", True)):
            with self.subTest(version=version, percentage=percentage), self.assertRaises(RuntimeError):
                rule.agent_version, rule.traffic_percentage = version, percentage
                verify_route(client, "agent", "2")
        rule.agent_version, rule.traffic_percentage = "2", 100
        client.agents.get_version.return_value = {"status": "creating"}
        with self.assertRaisesRegex(RuntimeError, "not active"):
            verify_route(client, "agent", "2")


if __name__ == "__main__":
    unittest.main()
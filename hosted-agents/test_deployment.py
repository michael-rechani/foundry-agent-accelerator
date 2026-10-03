import json
import stat
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from zipfile import ZipFile

from deployment import (
    AgentProfile, cleanup_failed_version, create_package, smoke_test,
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
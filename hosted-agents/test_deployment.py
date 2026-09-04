import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from zipfile import ZipFile

from deployment import cleanup_failed_version, create_package, smoke_test, verify_delegation


class DeploymentPackageTests(unittest.TestCase):
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
                    {"main.py", "requirements.txt", "instructions.md"},
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


if __name__ == "__main__":
    unittest.main()
import importlib.util
import io
import json
import sys
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import requests
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import VersionRefIndicator
from azure.core.credentials import AccessToken

from deployment import candidate_smoke_test, smoke_test


class CandidateSessionTests(unittest.TestCase):
    def setUp(self):
        self.client = Mock()
        self.client.agents.create_session.return_value = SimpleNamespace(
            agent_session_id="session-1", status="active",
            version_indicator=SimpleNamespace(type="version_ref", agent_version="2"),
        )
        self.smoke = self.enterContext(patch("deployment.smoke_test"))

    def run_candidate(self, prompt="hello", checks=()):
        candidate_smoke_test(self.client, "customer-review-coordinator", "2", prompt, checks)

    def test_create_exact_version_then_checks_and_cleanup(self):
        checks = (("application", "inspect_application", "application-review-agent"),
                  ("case", "inspect_case", "case-review-agent"))
        self.run_candidate("", checks)
        create = self.client.agents.create_session.call_args.kwargs
        self.assertEqual(create["agent_name"], "customer-review-coordinator")
        self.assertEqual(create["version_indicator"].as_dict(),
                         {"type": "version_ref", "agent_version": "2"})
        self.assertEqual(self.smoke.call_count, 3)
        for call in self.smoke.call_args_list:
            self.assertEqual(call.kwargs["agent_session_id"], "session-1")
        self.assertEqual(self.smoke.call_args_list[1].args[2:], checks[0])
        self.assertEqual(self.smoke.call_args_list[2].args[2:], checks[1])
        self.client.agents.delete_session.assert_called_once_with(
            agent_name="customer-review-coordinator", session_id="session-1")

    def test_binding_and_status_fail_closed_and_cleanup(self):
        for indicator, status in ((SimpleNamespace(type="version_ref", agent_version="3"), "active"),
                                  (SimpleNamespace(type="version_label", agent_version="2"), "active"),
                                  (SimpleNamespace(type="version_ref", agent_version="2"), "failed"),
                                  (None, "active")):
            with self.subTest(indicator=indicator, status=status):
                session = self.client.agents.create_session.return_value
                session.version_indicator, session.status = indicator, status
                self.client.agents.delete_session.reset_mock()
                with self.assertRaisesRegex(RuntimeError, "binding or status"):
                    self.run_candidate()
                self.client.agents.delete_session.assert_called_once()
                self.smoke.assert_not_called()

    def test_missing_or_unsafe_id_fails_without_unsafe_deletion(self):
        for session_id in (None, "", "../other"):
            self.client.agents.create_session.return_value.agent_session_id = session_id
            with self.assertRaisesRegex(RuntimeError, "cleanup could not be confirmed"):
                self.run_candidate()
            self.client.agents.delete_session.assert_not_called()

    def test_primary_failure_survives_cleanup_failure(self):
        self.smoke.side_effect = RuntimeError("primary smoke failure")
        self.client.agents.delete_session.side_effect = RuntimeError("cleanup failure")
        with redirect_stdout(io.StringIO()) as output:
            with self.assertRaisesRegex(RuntimeError, "primary smoke failure"):
                self.run_candidate()
        self.assertIn("cleanup failed", output.getvalue())
        self.assertNotIn("cleanup failure", output.getvalue())

    def test_cleanup_failure_prevents_promotion(self):
        self.client.agents.delete_session.side_effect = RuntimeError("cleanup failed")
        with self.assertRaisesRegex(RuntimeError, "cleanup failed"):
            self.run_candidate()

    def test_interrupt_still_cleans_up(self):
        self.smoke.side_effect = KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            self.run_candidate()
        self.client.agents.delete_session.assert_called_once()

    def test_empty_checks_or_symbolic_versions_are_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "requires a candidate smoke"):
            self.run_candidate("")
        with self.assertRaisesRegex(RuntimeError, "must be explicit"):
            candidate_smoke_test(self.client, "agent", "@latest", "test", ())
        self.client.agents.create_session.assert_not_called()


class SmokeTransportTests(unittest.TestCase):
    def test_response_is_bound_to_session_and_not_stored(self):
        client = MagicMock()
        response = SimpleNamespace(status="completed", output_text="fictional answer")
        create = client.get_openai_client.return_value.__enter__.return_value.responses.create
        create.return_value = response
        smoke_test(client, "agent", "fictional", agent_session_id="session-1")
        create.assert_called_once_with(input="fictional", store=False,
                                       extra_body={"agent_session_id": "session-1"})

    def test_real_sdk_serializes_version_reference_and_session_delete(self):
        requests_sent = []
        def respond(adapter, request, **kwargs):
            requests_sent.append((request.method, request.url, request.body))
            response = requests.Response()
            response.status_code = 201 if request.method == "POST" else 204
            response._content = (json.dumps({"agent_session_id": "session-1", "status": "active",
                "version_indicator": {"type": "version_ref", "agent_version": "2"}}).encode()
                if request.method == "POST" else b"")
            response.raw = io.BytesIO(response._content)
            response.headers["Content-Type"] = "application/json"
            response.request = request
            return response
        class Credential:
            def get_token(self, *args, **kwargs):
                return AccessToken("fictional", int(time.time()) + 3600)
        with patch.object(requests.adapters.HTTPAdapter, "send", respond):
            with AIProjectClient(endpoint="https://fictional.services.ai.azure.com/api/projects/demo",
                                 credential=Credential(), allow_preview=True, retry_total=0) as client:
                session = client.agents.create_session(agent_name="agent",
                    version_indicator=VersionRefIndicator(agent_version="2"))
                self.assertEqual(session.version_indicator.agent_version, "2")
                client.agents.delete_session(agent_name="agent", session_id=session.agent_session_id)
        self.assertEqual(requests_sent[0][0], "POST")
        self.assertEqual(json.loads(requests_sent[0][2])["version_indicator"],
                         {"type": "version_ref", "agent_version": "2"})
        self.assertEqual(requests_sent[1][0], "DELETE")
        self.assertIn("session-1", requests_sent[1][1])

    def test_real_customer_profile_supplies_required_delegation_checks(self):
        source = Path(__file__).parent / "review-coordinator-agent" / "deploy.py"
        spec = importlib.util.spec_from_file_location("candidate_customer_deploy", source)
        module = importlib.util.module_from_spec(spec)
        with patch.object(sys, "path", [str(source.parent), *sys.path]):
            spec.loader.exec_module(module)
        profile = module.profile_from_file(source.parent / "profiles" / "evidence-review.example.json")
        self.assertEqual(profile.name, "customer-review-coordinator")
        self.assertEqual(profile.smoke_test_prompt, "")
        self.assertEqual([item[1] for item in profile.delegation_checks],
                         ["inspect_application", "inspect_case", "inspect_case"])
        client = Mock()
        client.agents.create_session.return_value = SimpleNamespace(
            agent_session_id="session-1", status="active",
            version_indicator=SimpleNamespace(type="version_ref", agent_version="7"),
        )
        with patch("deployment.smoke_test") as check:
            candidate_smoke_test(client, profile.name, "7", profile.smoke_test_prompt,
                                 profile.delegation_checks)
        self.assertEqual(check.call_count, 4)
        self.assertEqual([call.args[3] for call in check.call_args_list[1:]],
                         ["inspect_application", "inspect_case", "inspect_case"])
        self.assertTrue(all(call.kwargs["agent_session_id"] == "session-1"
                            for call in check.call_args_list))
        client.agents.delete_session.assert_called_once()


if __name__ == "__main__":
    unittest.main()

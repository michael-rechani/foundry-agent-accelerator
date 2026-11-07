import contextlib
from email.message import Message
import io
import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

import check_platform_input as probe


class CandidateCheckTests(unittest.TestCase):
    def setUp(self):
        self.runtime = {"TF_STATE_CONTAINER": "private-container"}
        self.configuration = patch.object(probe.lab, "configuration", return_value=self.runtime)
        self.backend = patch.object(probe.backend, "validate_backend", return_value="private-account.blob.core.windows.net")
        self.token = patch.object(probe.backend, "azure_token", return_value="private-token")
        self.opener = patch.object(probe.backend.request, "build_opener")
        self.configuration.start()
        self.backend.start()
        self.token.start()
        self.build_opener = self.opener.start()
        self.open = self.build_opener.return_value.open
        self.addCleanup(self.configuration.stop)
        self.addCleanup(self.backend.stop)
        self.addCleanup(self.token.stop)
        self.addCleanup(self.opener.stop)

    @staticmethod
    def headers(**values):
        result = Message()
        for key, value in values.items():
            result[key.replace("_", "-")] = value
        return result

    def test_present_uses_one_fixed_head(self):
        response = MagicMock()
        response.status = 200
        response.headers = self.headers(ETag='"example"', x_ms_blob_type="BlockBlob")
        self.open.return_value.__enter__.return_value = response
        self.assertEqual(probe.candidate_status({}), "present")
        self.open.assert_called_once()
        req = self.open.call_args.args[0]
        self.assertEqual(req.full_url, "https://private-account.blob.core.windows.net/private-container/ai-foundry/dev.tfvars.json")
        self.assertEqual(req.method, "HEAD")
        self.assertIsNone(req.data)
        self.assertEqual(req.get_header("Authorization"), "Bearer private-token")
        self.build_opener.assert_called_once_with(probe.backend.NoRedirect)
        response.read.assert_not_called()

    def test_expected_and_unexpected_http_errors(self):
        for code, error_code, expected in (
            (404, "BlobNotFound", "absent"),
            (404, "ContainerNotFound", None),
            (404, None, None),
            (403, "AuthorizationFailure", None),
            (500, "InternalError", None),
        ):
            with self.subTest(code=code, error_code=error_code):
                headers = self.headers(**({"x_ms_error_code": error_code} if error_code else {}))
                self.open.side_effect = HTTPError("https://private.invalid/private-path", code, "sensitive", headers, None)
                if expected:
                    self.assertEqual(probe.candidate_status({}), expected)
                else:
                    with self.assertRaises(probe.backend.CheckError):
                        probe.candidate_status({})

    def test_ambiguous_success_fails_closed(self):
        response = self.open.return_value.__enter__.return_value
        response.status = 200
        for headers in (
            self.headers(),
            self.headers(ETag='"example"'),
            self.headers(x_ms_blob_type="BlockBlob"),
            self.headers(ETag='"example"', x_ms_blob_type="PageBlob"),
            self.headers(x_ms_error_code="BlobNotFound"),
        ):
            with self.subTest(headers=list(headers)):
                response.headers = headers
                with self.assertRaises(probe.backend.CheckError):
                    probe.candidate_status({})

    def test_unexpected_status_never_becomes_present(self):
        response = self.open.return_value.__enter__.return_value
        response.status = 204
        response.headers = self.headers(ETag='"example"', x_ms_blob_type="BlockBlob")
        with self.assertRaises(probe.backend.CheckError):
            probe.candidate_status({})

    def test_workflow_is_protected_and_has_no_unmasked_backend_settings(self):
        workflow = (Path(__file__).parents[1] / "workflows" / "check-platform-input.yml").read_text()
        for expected in (
            "workflow_dispatch:", "if: github.ref == 'refs/heads/main'",
            "runs-on: [self-hosted, linux, lab-runner]", "environment: terraform-state",
            "id-token: write", "contents: read", "group: terraform-state-access",
            "TF_LAB_PLAN_CONFIG: ${{ secrets.TF_LAB_PLAN_CONFIG }}",
        ):
            self.assertIn(expected, workflow)
        for forbidden in ("pull_request:", "vars.TF_STATE_", "setup-terraform", "upload-artifact"):
            self.assertNotIn(forbidden, workflow)

    def test_output_is_generic_even_for_sensitive_exception(self):
        for result in ("present", "absent", URLError("private-account private-container private-token ai-foundry/dev.tfvars.json")):
            with self.subTest(result=result):
                out, err = io.StringIO(), io.StringIO()
                with patch.object(probe, "candidate_status", side_effect=result if isinstance(result, Exception) else None,
                                  return_value=result), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    code = probe.main()
                if isinstance(result, Exception):
                    self.assertEqual((code, out.getvalue(), err.getvalue()), (1, "", "candidate_platform_input_check_failed\n"))
                else:
                    self.assertEqual((code, out.getvalue(), err.getvalue()), (0, f"candidate_platform_input={result}\n", ""))


class ConfigurationIntegrationTests(unittest.TestCase):
    def test_masked_configuration_and_oidc_are_used_in_process(self):
        protected = {
            "AZURE_CLIENT_ID": "11111111-2222-3333-4444-555555555555",
            "AZURE_TENANT_ID": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "AZURE_SUBSCRIPTION_ID": "11111111-2222-3333-4444-555555555555",
            "TF_STATE_ACCOUNT": "privateaccount",
            "TF_STATE_CONTAINER": "private-container",
            "TF_STATE_PREFIX": "ai-foundry/",
            "TF_STATE_PRIVATE_ENDPOINT": "10.1.2.3",
        }
        environ = {
            "TF_LAB_PLAN_CONFIG": json.dumps(protected),
            "GITHUB_REF": "refs/heads/main",
            "GITHUB_SHA": "a" * 40,
            "ACTIONS_ID_TOKEN_REQUEST_URL": "https://fixture.actions.githubusercontent.com/token",
            "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "private-oidc-token",
        }
        response = MagicMock()
        response.status = 200
        response.headers = CandidateCheckTests.headers(ETag='"example"', x_ms_blob_type="BlockBlob")
        with patch.object(probe.backend.socket, "getaddrinfo", return_value=[
            (2, 1, 6, "", ("10.1.2.3", 443)),
        ]), patch.object(probe.backend, "json_response", side_effect=[
            {"value": "private-assertion"}, {"access_token": "private-access-token"},
        ]), patch.object(probe.request, "build_opener") as opener:
            opener.return_value.open.return_value.__enter__.return_value = response
            self.assertEqual(probe.candidate_status(environ), "present")
            req = opener.return_value.open.call_args.args[0]
            self.assertEqual(req.method, "HEAD")
            self.assertEqual(req.get_header("Authorization"), "Bearer private-access-token")
            response.read.assert_not_called()


if __name__ == "__main__":
    unittest.main()

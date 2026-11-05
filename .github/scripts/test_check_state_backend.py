import contextlib
import io
import unittest
from unittest.mock import patch

import check_state_backend as probe


class BackendCheckTests(unittest.TestCase):
    def setUp(self):
        self.env = {
            "GITHUB_REF": "refs/heads/main",
            "AZURE_CLIENT_ID": "11111111-2222-3333-4444-555555555555",
            "AZURE_TENANT_ID": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "TF_STATE_ACCOUNT": "stfixture",
            "TF_STATE_CONTAINER": "tfstate",
            "TF_STATE_PREFIX": "ai-foundry/",
            "TF_STATE_PRIVATE_ENDPOINT": "10.42.0.23",
            "ACTIONS_ID_TOKEN_REQUEST_URL": "https://fixture.actions.githubusercontent.com/token?api=1",
            "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "github-secret",
        }
        self.calls = []
        self.dns = patch.object(probe.socket, "getaddrinfo", return_value=[
            (2, 1, 6, "", ("10.42.0.23", 443)),
        ])
        self.dns.start()
        self.addCleanup(self.dns.stop)

    def transport(self, url, **kwargs):
        self.calls.append((url, kwargs))
        hostname = probe.parse.urlsplit(url).hostname
        if hostname == "fixture.actions.githubusercontent.com":
            return b'{"value":"oidc-secret"}', {}
        if hostname == "login.microsoftonline.com":
            return b'{"access_token":"azure-secret"}', {}
        return b"", {}

    def run_check(self, side_effect=None):
        with patch.object(probe, "send", side_effect=side_effect or self.transport):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                probe.check(self.env)
        return output.getvalue()

    def test_scoped_probe_and_cleanup_without_state_content(self):
        output = self.run_check()
        self.assertNotIn("secret", output)
        blob_calls = self.calls[4:]
        self.assertEqual(len(blob_calls), 5)
        for url, _ in blob_calls:
            self.assertIn("/ai-foundry/.access-probe/", url)
            self.assertNotIn(".tfstate", url)
        self.assertEqual(blob_calls[0][1]["headers"]["If-None-Match"], "*")
        self.assertEqual(blob_calls[1][1]["headers"]["x-ms-lease-duration"], "15")
        self.assertEqual(blob_calls[2][1]["expected"], (409,))
        self.assertEqual(blob_calls[-1][1]["method"], "DELETE")
        self.assertEqual(self.calls[2][1].get("method", "GET"), "GET")
        self.assertIn("prefix=ai-foundry%2F", self.calls[2][0])
        self.assertIn("/.access-probe-forbidden/", self.calls[3][0])
        self.assertEqual(self.calls[3][1]["expected"], (403,))

    def test_fails_closed_before_authentication(self):
        cases = [
            ("GITHUB_REF", "refs/heads/feature"),
            ("TF_STATE_ACCOUNT", "other.example/path"),
            ("TF_STATE_CONTAINER", "../state"),
            ("TF_STATE_PREFIX", ""),
            ("TF_STATE_PREFIX", "other/"),
            ("TF_STATE_PRIVATE_ENDPOINT", "8.8.8.8"),
            ("TF_STATE_PRIVATE_ENDPOINT", "::1"),
            ("ACTIONS_ID_TOKEN_REQUEST_URL", "https://attacker.example/token"),
        ]
        for key, value in cases:
            with self.subTest(key=key, value=value):
                original = self.env[key]
                self.env[key] = value
                with self.assertRaises(probe.CheckError):
                    self.run_check()
                self.assertEqual(self.calls, [])
                self.env[key] = original

    def test_public_or_mixed_dns_is_rejected(self):
        for answers in (["20.1.1.1"], ["10.42.0.23", "20.1.1.1"]):
            with self.subTest(answers=answers):
                with patch.object(probe.socket, "getaddrinfo", return_value=[
                    (2, 1, 6, "", (ip, 443)) for ip in answers
                ]):
                    with self.assertRaisesRegex(probe.CheckError, "DNS"):
                        self.run_check()
                self.assertEqual(self.calls, [])

    def test_cleanup_after_lease_failure(self):
        def transport(url, **kwargs):
            if kwargs.get("headers", {}).get("x-ms-lease-action") == "acquire":
                raise probe.CheckError("acquire failed")
            return self.transport(url, **kwargs)
        with self.assertRaisesRegex(probe.CheckError, "acquire failed"):
            self.run_check(transport)
        self.assertEqual(self.calls[-1][1]["method"], "DELETE")

    def test_cleanup_after_exclusivity_failure_uses_owned_lease(self):
        def transport(url, **kwargs):
            if kwargs.get("expected") == (409,):
                raise probe.CheckError("lock was not exclusive")
            return self.transport(url, **kwargs)
        with self.assertRaisesRegex(probe.CheckError, "not exclusive"):
            self.run_check(transport)
        self.assertIn("x-ms-lease-id", self.calls[-1][1]["headers"])

    def test_cleanup_failure_is_not_silenced(self):
        def transport(url, **kwargs):
            if kwargs.get("method") == "DELETE":
                raise probe.CheckError("cleanup failed")
            return self.transport(url, **kwargs)
        with self.assertRaisesRegex(probe.CheckError, "cleanup failed"):
            self.run_check(transport)

    def test_workflow_is_manual_main_only_and_approval_gated(self):
        from pathlib import Path
        workflow = (Path(__file__).parents[1] / "workflows" / "check-state-backend.yml").read_text()
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("if: github.ref == 'refs/heads/main'", workflow)
        self.assertIn("environment: terraform-state", workflow)
        self.assertIn("id-token: write", workflow)
        self.assertNotIn("pull_request", workflow)
        self.assertNotIn("terraform apply", workflow)
        self.assertNotIn("upload-artifact", workflow)

    def test_transport_refuses_non_https_before_opening(self):
        for url in ("file:///tmp/token", "http://example.test", "https://user:pass@example.test"):
            with self.subTest(url=url):
                with patch.object(probe.request, "build_opener") as opener:
                    with self.assertRaises(probe.CheckError):
                        probe.send(url)
                    opener.assert_not_called()

    def test_transport_does_not_follow_redirects_or_log_error_bodies(self):
        redirect = probe.NoRedirect()
        self.assertIsNone(redirect.redirect_request(None, None, 302, "", {}, "https://other.test"))
        exc = probe.error.HTTPError("https://example.test", 403, "sensitive body", {}, None)
        with patch.object(probe.request, "build_opener") as opener:
            opener.return_value.open.side_effect = exc
            with self.assertRaisesRegex(probe.CheckError, "^GET failed with HTTP 403.$"):
                probe.send("https://example.test")


if __name__ == "__main__":
    unittest.main()

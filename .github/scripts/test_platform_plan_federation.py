import base64
import contextlib
from email.message import Message
import io
import json
from pathlib import Path
import subprocess
import sys
import textwrap
import unittest
from unittest.mock import Mock, patch
from urllib import parse, request


ROOT = Path(__file__).parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "check-platform-plan-federation.yml"
REPOSITORY = "michael-rechani/foundry-agent-accelerator"
SHA = "a" * 40
SENTINEL = "synthetic-private-exception-content"
AUDIENCE = "urn:platform-plan-claim-preview:" + "a" * 64
CONTEXT = {
    "GITHUB_REPOSITORY": REPOSITORY,
    "GITHUB_EVENT_NAME": "workflow_dispatch",
    "GITHUB_REF": "refs/heads/main",
    "GITHUB_SHA": SHA,
    "VERIFIED_WORKFLOW_SHA": SHA,
    "VERIFIED_WORKFLOW_REF": REPOSITORY + "/.github/workflows/"
                             "check-platform-plan-federation.yml@refs/heads/main",
    "ACTIONS_ID_TOKEN_REQUEST_URL": "https://pipelines.actions.githubusercontent.com/oidc?audience=old&v=1",
    "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "synthetic-request-token",
}
CLAIMS = {
    "iss": "https://token.actions.githubusercontent.com",
    "aud": AUDIENCE,
    "sub": "repo:michael-rechani@123/foundry-agent-accelerator@456:environment:platform-plan-read",
    "repository": REPOSITORY,
    "repository_owner_id": "123",
    "repository_id": "456",
    "ref": "refs/heads/main",
    "environment": "platform-plan-read",
    "event_name": "workflow_dispatch",
    "exp": 1100,
    "nbf": 900,
}


def source():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    marker = "          python3 -I - <<'PY'\n"
    begin = workflow.index(marker) + len(marker)
    end = workflow.index("\n          PY", begin)
    return textwrap.dedent(workflow[begin:end])


def bootstrap():
    namespace = {"__name__": "plan_oidc_test"}
    exec(compile(source(), "<plan-oidc>", "exec"), namespace)
    return namespace


def token(payload):
    def encode(raw):
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

    return ".".join((encode(b'{"alg":"RS256"}'), encode(payload), encode(b"synthetic-signature")))


class Response:
    def __init__(self, url, body, status=200, target=None):
        self.url = url if target is None else target
        self.body = body
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def geturl(self):
        return self.url

    def read(self, size):
        return self.body[:size]


class PlanOidcTests(unittest.TestCase):
    def setUp(self):
        self.ns = bootstrap()

    def test_workflow_is_manual_private_and_oidc_only(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        for expected in ("workflow_dispatch:", "permissions: {}", "if: github.ref == 'refs/heads/main'",
                         "runs-on: [self-hosted, linux, lab-runner]", "environment: platform-plan-read",
                         "id-token: write", "python3 -I - <<'PY'"):
            self.assertIn(expected, workflow)
        for forbidden in ("actions/checkout", "upload-artifact", "pull_request:", "${{ secrets.", "AZURE_", "api://AzureADTokenExchange"): 
            self.assertNotIn(forbidden, workflow)

    def test_context_requires_exact_protected_workflow(self):
        self.ns["verify_context"](CONTEXT)
        for key in ("GITHUB_REPOSITORY", "GITHUB_EVENT_NAME", "GITHUB_REF", "GITHUB_SHA",
                    "VERIFIED_WORKFLOW_SHA", "VERIFIED_WORKFLOW_REF"):
            for value in (None, "wrong"):
                env = dict(CONTEXT)
                if value is None:
                    env.pop(key)
                else:
                    env[key] = value
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    self.ns["verify_context"](env)

    def test_success_uses_direct_https_and_prints_fixed_categories(self):
        calls = []
        ns = self.ns

        class Opener:
            def open(self, req, *, timeout):
                calls.append((req, timeout))
                if req.full_url == ns["REPOSITORY_URL"]:
                    body = {"full_name": REPOSITORY, "id": 456, "owner": {"login": "michael-rechani", "id": 123}}
                else:
                    body = {"value": token(json.dumps(CLAIMS).encode())}
                return Response(req.full_url, json.dumps(body).encode())

        output, errors = io.StringIO(), io.StringIO()
        with patch.object(request, "build_opener", return_value=Opener()) as builder, \
                patch.object(ns["time"], "time", return_value=1000), \
                patch.object(ns["secrets"], "token_hex", return_value="a" * 64), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            self.assertEqual(ns["main"](CONTEXT), 0)
        self.assertEqual(errors.getvalue(), "")
        self.assertEqual(output.getvalue().splitlines(), [
            "plan_oidc_issuer=matched", "plan_oidc_audience=matched", "plan_oidc_subject=id_qualified",
            "plan_oidc_binding=matched", "plan_oidc_lifetime=valid",
        ])
        self.assertEqual(builder.call_args.args[0].proxies, {})
        redirect = builder.call_args.args[1]
        self.assertIsInstance(redirect, ns["NoRedirect"])
        self.assertIsNone(redirect.redirect_request(None, None, 302, "", Message(), "https://example.invalid"))
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0][0].full_url, ns["REPOSITORY_URL"])
        query = parse.parse_qs(parse.urlsplit(calls[1][0].full_url).query)
        self.assertEqual(query["audience"], [AUDIENCE])
        self.assertEqual(calls[1][0].get_header("Authorization"), "Bearer synthetic-request-token")
        self.assertTrue(all(timeout == 15 for _, timeout in calls))

    def test_oidc_endpoint_rejects_untrusted_hosts_and_credentials(self):
        for url in ("http://pipelines.actions.githubusercontent.com/oidc",
                    "https://evil.example/oidc",
                    "https://x.actions.githubusercontent.com.evil.example/oidc",
                    "https://user@x.actions.githubusercontent.com/oidc",
                    "https://x.actions.githubusercontent.com:444/oidc",
                    "https://x.actions.githubusercontent.com/oidc#fragment"):
            env = dict(CONTEXT, ACTIONS_ID_TOKEN_REQUEST_URL=url)
            with self.subTest(url=url), self.assertRaises(ValueError):
                self.ns["request_assertion"](None, env, AUDIENCE)
        with self.assertRaises(ValueError):
            self.ns["request_assertion"](None, dict(CONTEXT, ACTIONS_ID_TOKEN_REQUEST_TOKEN="bad\nvalue"), AUDIENCE)

    def test_responses_reject_redirects_oversize_and_invalid_json(self):
        ns = self.ns
        url = "https://api.github.com/example"
        for response, limit in ((Response(url, b"{}", status=302), 100),
                                (Response(url, b"{}", target=url + "/other"), 100),
                                (Response(url, b"x" * 12), 10),
                                (Response(url, b'{"a":1,"a":2}'), 100),
                                (Response(url, b'{"a":NaN}'), 100)):
            opener = Mock()
            opener.open.return_value = response
            with self.subTest(response=response), self.assertRaises(ValueError):
                ns["read_json"](opener, url, {}, limit)

    def test_repository_ids_require_exact_public_metadata(self):
        opener = Mock()
        body = {"full_name": REPOSITORY, "id": 456, "owner": {"login": "wrong", "id": 123}}
        opener.open.return_value = Response(self.ns["REPOSITORY_URL"], json.dumps(body).encode())
        with self.assertRaises(ValueError):
            self.ns["repository_ids"](opener)

    def test_jwt_parser_rejects_malformed_and_duplicate_claims(self):
        decode = self.ns["decode_claims"]
        self.assertEqual(decode(token(json.dumps(CLAIMS).encode())), CLAIMS)
        for value in ("", "a.b", "a.!.c", token(b'{"sub":"a","sub":"b"}'), token(b'{"exp":NaN}')):
            with self.subTest(value=value), self.assertRaises(ValueError):
                decode(value)

    def test_classification_rejects_legacy_wrong_binding_and_expiry(self):
        classify = self.ns["classify_claims"]
        self.assertEqual(classify(CLAIMS, "123", "456", AUDIENCE, 1000), (True, True, "id_qualified", True, True))
        legacy = dict(CLAIMS, sub="repo:" + REPOSITORY + ":environment:platform-plan-read")
        self.assertEqual(classify(legacy, "123", "456", AUDIENCE, 1000)[2], "name_only")
        wrong = dict(CLAIMS, repository_id="999", aud="wrong", exp=999)
        self.assertEqual(classify(wrong, "123", "456", AUDIENCE, 1000), (True, False, "id_qualified", False, False))
        future = dict(CLAIMS, nbf=1061)
        self.assertFalse(classify(future, "123", "456", AUDIENCE, 1000)[4])

    def test_context_failure_never_fetches_metadata(self):
        lookup = Mock()
        errors = io.StringIO()
        with patch.dict(self.ns, {"repository_ids": lookup}), contextlib.redirect_stderr(errors):
            self.assertEqual(self.ns["main"](dict(CONTEXT, GITHUB_REF="refs/heads/other")), 1)
        lookup.assert_not_called()
        self.assertEqual(errors.getvalue(), "plan_oidc_check_failed=context\n")

    def test_expected_failure_is_redacted(self):
        def fail(_opener):
            raise ValueError(SENTINEL)

        errors = io.StringIO()
        with patch.object(request, "build_opener", return_value=object()), \
                patch.dict(self.ns, {"repository_ids": fail}), contextlib.redirect_stderr(errors):
            self.assertEqual(self.ns["main"](CONTEXT), 1)
        self.assertEqual(errors.getvalue(), "plan_oidc_check_failed=repository_lookup\n")
        self.assertNotIn(SENTINEL, errors.getvalue())

    def test_unexpected_exceptions_are_redacted_and_nonzero(self):
        before, after = source().split('if __name__ == "__main__":', 1)
        for exception in ("RuntimeError", "SystemExit", "KeyboardInterrupt"):
            program = before + f'\ndef main():\n    raise {exception}("{SENTINEL}")\n\n' + \
                'if __name__ == "__main__":' + after
            result = subprocess.run([sys.executable, "-I", "-c", program], capture_output=True, text=True, check=False)
            with self.subTest(exception=exception):
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, "")
                self.assertEqual(result.stderr, "plan_oidc_check_failed=unexpected\n")
                self.assertNotIn(SENTINEL, result.stderr)


if __name__ == "__main__":
    unittest.main()

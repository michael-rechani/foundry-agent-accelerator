import contextlib
from copy import deepcopy
from email.message import Message
import hashlib
import io
import os
from pathlib import Path
import subprocess
import sys
import textwrap
import unittest
from unittest.mock import patch
from urllib import request

import test_check_platform_input_authority as authority_tests


ROOT = Path(__file__).parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "check-platform-input-authority.yml"
SHA = "a" * 40
EXPECTED_NAMES = ("check_state_backend", "reconcile_runner_state", "check_lab_terraform_plan",
                  "check_platform_input_authority")
CONTEXT = {
    "GITHUB_REPOSITORY": "michael-rechani/foundry-agent-accelerator",
    "GITHUB_EVENT_NAME": "workflow_dispatch",
    "GITHUB_REF": "refs/heads/main",
    "GITHUB_SHA": SHA,
    "VERIFIED_WORKFLOW_SHA": SHA,
    "VERIFIED_WORKFLOW_REF": "michael-rechani/foundry-agent-accelerator/.github/workflows/"
                             "check-platform-input-authority.yml@refs/heads/main",
}


def bootstrap_source():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    begin = workflow.index("          python3 -I - <<'PY'\n") + len("          python3 -I - <<'PY'\n")
    end = workflow.index("\n          PY", begin)
    return textwrap.dedent(workflow[begin:end])


def bootstrap():
    namespace = {"__name__": "bootstrap_test"}
    exec(compile(bootstrap_source(), "<bootstrap>", "exec"), namespace)
    return namespace


def local_sources(names):
    return {name: (ROOT / ".github" / "scripts" / (name + ".py")).read_bytes().replace(b"\r\n", b"\n")
            for name in names}


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


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.ns = bootstrap()
        self.names = self.ns["NAMES"]
        self.sources = local_sources(self.names)

    def test_hashes_match_all_four_committed_sources(self):
        self.assertEqual(self.names, EXPECTED_NAMES)
        self.assertEqual(tuple(self.ns["SOURCES"]), self.names)
        for name in self.names:
            with self.subTest(name=name):
                self.assertEqual(hashlib.sha256(self.sources[name]).hexdigest(), self.ns["SOURCES"][name])

    def test_workflow_removes_checkout_and_keeps_protected_contract(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        for expected in ("workflow_dispatch:", "if: github.ref == 'refs/heads/main'",
                         "runs-on: [self-hosted, linux, lab-runner]", "environment: terraform-state",
                         "id-token: write", "contents: read", "group: terraform-state-access",
                         "VERIFIED_WORKFLOW_SHA: ${{ github.workflow_sha }}",
                         "VERIFIED_WORKFLOW_REF: ${{ github.workflow_ref }}",
                         "python3 -I - <<'PY'"):
            self.assertIn(expected, workflow)
        for forbidden in ("actions/checkout", "upload-artifact", "pull_request:", "setup-terraform"):
            self.assertNotIn(forbidden, workflow)

    def test_only_exact_context_is_accepted(self):
        self.assertEqual(self.ns["verify_context"](CONTEXT), SHA)
        for key in CONTEXT:
            for value in (None, "private-value"):
                env = deepcopy(CONTEXT)
                if value is None:
                    env.pop(key)
                else:
                    env[key] = value
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    self.ns["verify_context"](env)

    def test_fixed_source_urls_no_proxy_and_no_redirects(self):
        calls = []

        class Opener:
            def open(inner, req, *, timeout):
                calls.append((req.full_url, req.method, timeout))
                name = req.full_url.rsplit("/", 1)[1][:-3]
                return Response(req.full_url, self.sources[name])

        with patch.object(request, "build_opener", return_value=Opener()) as builder:
            self.assertEqual(self.ns["fetch_sources"](SHA), self.sources)
        handlers = builder.call_args.args
        self.assertEqual(handlers[0].proxies, {})
        self.assertIsInstance(handlers[1], self.ns["NoRedirect"])
        self.assertIsNone(handlers[1].redirect_request(None, None, 302, "", Message(), "https://other.invalid"))
        self.assertEqual(calls, [
            ("https://raw.githubusercontent.com/michael-rechani/foundry-agent-accelerator/"
             + SHA + "/.github/scripts/" + name + ".py", "GET", 30) for name in self.names
        ])

    def test_changed_missing_oversized_and_redirected_sources_fail(self):
        for position, name in enumerate(self.names):
            for mode in ("changed", "missing", "oversized", "redirect", "status"):
                class Opener:
                    def open(inner, req, *, timeout, selected=name, failure=mode):
                        current = req.full_url.rsplit("/", 1)[1][:-3]
                        if current != selected:
                            return Response(req.full_url, self.sources[current])
                        if failure == "missing":
                            raise OSError("private-error")
                        body = self.sources[current]
                        if failure == "changed":
                            body += b" "
                        if failure == "oversized":
                            body = b"x" * (self.ns["LIMIT"] + 1)
                        return Response(req.full_url, body, 403 if failure == "status" else 200,
                                        "https://other.invalid" if failure == "redirect" else None)

                with self.subTest(position=position, mode=mode), \
                        patch.object(request, "build_opener", return_value=Opener()), \
                        self.assertRaises((ValueError, OSError)):
                    self.ns["fetch_sources"](SHA)

    def test_missing_extra_or_existing_modules_are_rejected(self):
        for sources in ({}, {**self.sources, "extra": b"private"},
                        {name: body for name, body in self.sources.items() if name != self.names[0]}):
            with self.subTest(sources=tuple(sources)), self.assertRaises(ValueError):
                self.ns["load_sources"](sources)
        with patch.dict(sys.modules, {self.names[0]: object()}), self.assertRaises(ValueError):
            self.ns["load_sources"](self.sources)
        with patch.dict(self.ns["SOURCES"], {"extra": "private"}), self.assertRaises(ValueError):
            self.ns["fetch_sources"](SHA)

    def test_all_sources_compile_before_any_execute(self):
        broken = dict(self.sources)
        broken[self.names[-1]] = b"invalid syntax !"
        with patch.dict(sys.modules):
            for name in self.names:
                sys.modules.pop(name, None)
            with self.assertRaises(SyntaxError):
                self.ns["load_sources"](broken)
            self.assertTrue(all(name not in sys.modules for name in self.names))

    def test_load_validates_context_before_fetch_and_does_not_invoke_main(self):
        events = []
        class Module:
            def main(self):
                events.append("main")
                return 0
        def fetch(sha):
            self.assertEqual(sha, SHA)
            events.append("fetch")
            return self.sources
        def load(sources):
            self.assertEqual(sources, self.sources)
            events.append("load")
            return Module()
        with patch.dict(os.environ, CONTEXT), patch.dict(self.ns, {"fetch_sources": fetch, "load_sources": load}):
            self.assertIsInstance(self.ns["load_verified_module"](), Module)
        self.assertEqual(events, ["fetch", "load"])
        events.clear()
        with patch.dict(os.environ, {**CONTEXT, "GITHUB_REF": "refs/heads/other"}), \
                patch.dict(self.ns, {"fetch_sources": fetch, "load_sources": load}), \
                self.assertRaises(ValueError):
            self.ns["load_verified_module"]()
        self.assertEqual(events, [])

    def test_verified_sources_run_existing_comparison_with_mocked_io(self):
        inputs, state = authority_tests.fixture()
        send_results = [(authority_tests.encode(inputs), authority_tests.headers()),
                        (authority_tests.encode(state), authority_tests.headers()),
                        (authority_tests.encode(state), authority_tests.headers()),
                        (authority_tests.encode(inputs), authority_tests.headers())]
        with patch.dict(sys.modules):
            for name in self.names:
                sys.modules.pop(name, None)
            probe = self.ns["load_sources"](self.sources)
            blobs = type("Blobs", (), {"base": "https://private.invalid/", "headers": {}})()
            out, err = io.StringIO(), io.StringIO()
            with patch.object(probe.lab, "configuration", return_value={
                "AZURE_SUBSCRIPTION_ID": authority_tests.SUB,
            }), patch.object(probe, "Blobs", return_value=blobs), \
                    patch.object(probe.backend, "send", side_effect=send_results) as send, \
                    contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                self.assertEqual(probe.main(), 0)
            self.assertEqual(len(send.call_args_list), 4)
            self.assertEqual(err.getvalue(), "")
            self.assertEqual(out.getvalue(), "candidate_platform_comparison=matched\n"
                             "candidate_router_override=absent\n" + authority_tests.ABSENT_OUTPUT)

    def test_bootstrap_exception_is_redacted_in_isolated_process(self):
        code = ("import urllib.request\n"
                "def fail(*args, **kwargs): raise RuntimeError('private-token private-url')\n"
                "urllib.request.build_opener = fail\n" + bootstrap_source())
        env = {**os.environ, **CONTEXT}
        result = subprocess.run([sys.executable, "-I", "-c", code], env=env,
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "candidate_platform_comparison_failed=source_verification\n")

    def test_verified_source_loading_and_execution_failures_are_separately_redacted(self):
        definitions, entrypoint = bootstrap_source().split('if __name__ == "__main__":', 1)
        sensitive = "synthetic-secret private-token https://private.invalid/sensitive"
        for phase in ("compile", "load", "main"):
            for exception in ("RuntimeError", "SystemExit", "KeyboardInterrupt"):
                if phase == "compile":
                    failure_source = f"invalid syntax ! {sensitive}"
                elif phase == "load":
                    failure_source = f"raise {exception}({sensitive!r})"
                else:
                    failure_source = f"def main():\n    raise {exception}({sensitive!r})"
                setup = (
                    f"\nsources = {{name: b'' for name in NAMES}}\n"
                    f"sources[NAMES[-1]] = {failure_source.encode()!r}\n"
                    "SOURCES = {name: hashlib.sha256(body).hexdigest() for name, body in sources.items()}\n"
                    "class Response:\n"
                    "    status = 200\n"
                    "    def __init__(self, url): self.url = url\n"
                    "    def __enter__(self): return self\n"
                    "    def __exit__(self, *args): pass\n"
                    "    def geturl(self): return self.url\n"
                    "    def read(self, size): return sources[self.url.rsplit('/', 1)[1][:-3]][:size]\n"
                    "class Opener:\n"
                    "    def open(self, req, *, timeout): return Response(req.full_url)\n"
                    "request.build_opener = lambda *args: Opener()\n"
                )
                code = definitions + setup + 'if __name__ == "__main__":' + entrypoint
                with self.subTest(phase=phase, exception=exception):
                    result = subprocess.run([sys.executable, "-I", "-c", code],
                                            env={**os.environ, **CONTEXT},
                                            capture_output=True, text=True, check=False)
                    self.assertEqual(result.returncode, 1)
                    self.assertEqual(result.stdout, "")
                    category = "unexpected" if phase == "main" else "source_verification"
                    self.assertEqual(result.stderr, f"candidate_platform_comparison_failed={category}\n")


if __name__ == "__main__":
    unittest.main()

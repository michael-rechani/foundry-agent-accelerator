"""Checks the hosted-agent bundle the Agent designer's spec card downloads.

The Lab builds the bundle itself because the image can't see hosted-agents/. These tests keep that copy honest:
hosted-agents/bundle.py must accept the file, the file must match what `bundle.py export --sample
basic-responses-agent --instructions-file ...` writes, and the agent code must still equal the sample's.
"""
import io
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock
from zipfile import ZipFile

from fastapi.testclient import TestClient

import agent_bundle
from agent_creation import CreationSettings
from app import Settings, create_app
from log_capture import CapturedLabLogs
from test_rule_copies import ROOT, load

reference = load("agent_bundle_reference", "hosted-agents/bundle.py", "hosted-agents")
SAMPLE = ROOT / "hosted-agents" / "basic-responses-agent"

NAME = "hours-notice-helper"
DESCRIPTION = "Explains a change in opening hours."
INSTRUCTIONS = "Explain the notice in plain words.\nDon’t guess a time the notice doesn't give.\n"
SPEC = {"name": NAME, "description": DESCRIPTION, "instructions": INSTRUCTIONS}
# Hashes depend on the line endings of the checkout, which differ between a Windows worktree and CI.
HASHES = ("code_sha256", "files")


def unpack(content):
    with ZipFile(io.BytesIO(content)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def source_files(content):
    """The agent code in a bundle's agent.zip, with line endings normalized."""
    return {name: text.replace(b"\r\n", b"\n") for name, text in unpack(unpack(content)["agent.zip"]).items()}


def manifest_of(content):
    return json.loads(unpack(content)["manifest.json"])


class AgentBundleTests(CapturedLabLogs, unittest.TestCase):
    def setUp(self):
        self.gateway = AsyncMock()
        self.settings = Settings("private", "https://example.services.ai.azure.com/api/projects/test",
                                 ("testserver",), ("https://testserver",),
                                 creation=CreationSettings(False, "test-model", models={"reasoning": "reason-model"}))
        self.client = TestClient(create_app(self.settings, self.gateway))
        self.headers = {"X-Workbench-Request": "1", "Origin": "https://testserver"}

    def post(self, body=None, client=None, headers=None, **changes):
        return (client or self.client).post("/api/agent-bundles", json={**SPEC, **changes} if body is None else body,
                                            headers=self.headers if headers is None else headers)

    def check_rejected(self, response, status=400, error="invalid_bundle"):
        self.assertEqual((response.status_code, response.json()["error"]), (status, error))

    def test_the_deployment_tool_accepts_the_download(self):
        response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "application/zip")
        self.assertEqual(response.headers["content-disposition"], f'attachment; filename="{NAME}.agent-bundle.zip"')
        self.assertEqual(response.headers["cache-control"], "no-store")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / f"{NAME}.agent-bundle.zip"
            path.write_bytes(response.content)
            manifest, code, _ = reference.read_bundle(path)
        self.assertEqual((manifest["kind"], manifest["name"], manifest["model"], manifest["environment"]),
                         ("prebuilt", NAME, None, {}))
        self.assertEqual((manifest["description"], manifest["instructions"]), (DESCRIPTION, INSTRUCTIONS.strip()))
        self.assertEqual(set(unpack(code)), {"main.py", "requirements.txt", "instructions.md"})

    def test_it_matches_what_the_export_command_writes(self):
        with tempfile.TemporaryDirectory() as folder:
            instructions = Path(folder) / "instructions.md"
            instructions.write_bytes(INSTRUCTIONS.strip().encode("utf-8"))
            expected = reference.export_sample("basic-responses-agent", instructions_path=instructions)
        ours = self.post().content
        self.assertEqual(
            {key: value for key, value in manifest_of(ours).items() if key not in HASHES},
            {key: value for key, value in {**manifest_of(expected), "name": NAME, "description": DESCRIPTION}.items()
             if key not in HASHES})
        self.assertEqual(list(unpack(ours)), list(unpack(expected)))
        self.assertEqual(list(source_files(ours).items()), list(source_files(expected).items()))

    def test_the_agent_code_is_the_samples_code(self):
        for name in agent_bundle.SOURCE_FILES:
            copy = (agent_bundle.SOURCE_DIRECTORY / name).read_bytes().replace(b"\r\n", b"\n")
            original = (SAMPLE / name).read_bytes().replace(b"\r\n", b"\n")
            self.assertEqual(copy, original, f"workbench/basic_agent_source/{name} differs from "
                                             f"hosted-agents/basic-responses-agent/{name}. Copy the sample's file over it.")

    def test_a_download_is_reproducible(self):
        self.assertEqual(self.post().content, self.post().content)

    def test_it_makes_no_model_call(self):
        self.post()
        self.gateway.preview.assert_not_called()

    def test_a_name_must_start_with_a_letter_inside_the_bundle(self):
        for slug, expected in (("2025-hours", "agent-2025-hours"), ("7", "agent-7"), ("a", "a"), (NAME, NAME)):
            response = self.post(name=slug)
            self.assertEqual(response.status_code, 200, slug)
            self.assertEqual(manifest_of(response.content)["name"], expected)
            self.assertIn(f'filename="{slug}.agent-bundle.zip"', response.headers["content-disposition"])
        longest = "9" + "a" * 47
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "longest.zip"
            path.write_bytes(self.post(name=longest).content)
            self.assertEqual(reference.read_bundle(path)[0]["name"], f"agent-{longest}")

    def test_surrounding_space_is_dropped(self):
        manifest = manifest_of(self.post(description="  Explains hours.  ", instructions=f"\n\n{INSTRUCTIONS}\n\n").content)
        self.assertEqual((manifest["description"], manifest["instructions"]), ("Explains hours.", INSTRUCTIONS.strip()))

    def test_bad_requests_are_rejected(self):
        for changes in ({"name": ""}, {"name": "Hours"}, {"name": "hours notice"}, {"name": "-hours"}, {"name": "hours-"},
                        {"name": "hours--notice"}, {"name": "hours_notice"}, {"name": "../hours"}, {"name": "a" * 49},
                        {"name": "hours\n"}, {"name": 7},
                        {"description": ""}, {"description": "   "}, {"description": "x" * 501}, {"description": "a\x00b"},
                        {"instructions": "short"}, {"instructions": " " * 20}, {"instructions": "x" * 6001},
                        {"instructions": "Explain the notice.\x00"}, {"instructions": None},
                        {"extra": 1}):
            self.check_rejected(self.post(**changes))
        for missing in SPEC:
            self.check_rejected(self.post(body={key: value for key, value in SPEC.items() if key != missing}))
        self.check_rejected(self.post(body=[SPEC]))

    def test_the_longest_allowed_text_is_accepted(self):
        response = self.post(description="d" * 500, instructions="i" * 6000, name="a" * 48)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(manifest_of(response.content)["instructions"]), 6000)

    def test_origin_and_header_are_required(self):
        for headers in ({"Origin": "https://testserver"}, {"X-Workbench-Request": "1", "Origin": "https://evil.example"}):
            self.check_rejected(self.post(headers=headers), 403, "request_not_allowed")

    def test_a_non_json_or_oversized_body_is_rejected(self):
        self.check_rejected(self.client.post("/api/agent-bundles", content="nope", headers=self.headers))
        self.check_rejected(self.client.post("/api/agent-bundles", content="{not json",
                                             headers={**self.headers, "Content-Type": "application/json"}))
        self.check_rejected(self.post(instructions="x" * 70000), 413, "request_too_large")

    def test_it_needs_the_library_preview(self):
        disabled = TestClient(create_app(replace(self.settings, library_preview=False), self.gateway))
        self.check_rejected(self.post(client=disabled), 503, "library_preview_disabled")


if __name__ == "__main__":
    unittest.main()

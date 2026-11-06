"""Builds a portable hosted-agent bundle from an Agent designer spec, with no model call and nothing published.

The bundle is the file that `hosted-agents/bundle.py export --sample basic-responses-agent --instructions-file ...`
writes: the generic basic Responses agent carrying the spec's instructions. The person checks it with
`bundle.py inspect` and publishes it to a Foundry project of their own choosing with `bundle.py deploy`.
The Lab only builds the file. The agent code is a copy of hosted-agents/basic-responses-agent in
basic_agent_source/, and test_agent_bundle.py fails when the two differ or when bundle.py stops accepting the file.
"""

import hashlib
import io
import json
import re
import stat
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from fastapi import APIRouter, Request
from fastapi.responses import Response
from pydantic import Field, ValidationError, field_validator

from history import StrictModel
from request_guard import MAX_REQUEST_BYTES, RequestRejected, api_error, read_json_body, request_allowed

SOURCE_DIRECTORY = Path(__file__).with_name("basic_agent_source")
# The order hosted-agents/deployment.py packages them in.
SOURCE_FILES = ("main.py", "requirements.txt", "instructions.md")
SMOKE_TEST_PROMPT = "Reply with a short confirmation that the hosted agent is ready."
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def bundle_name(slug):
    """The agent name a bundle carries: bundle.py needs it to start with a letter."""
    return slug if slug[0].isalpha() else f"agent-{slug}"


def zip_entry(archive, name, content):
    info = ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
    info.compress_type = ZIP_DEFLATED
    # Foundry's remote build requires the Unix regular-file type bit.
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | 0o644) << 16
    archive.writestr(info, content)


def agent_package(directory=SOURCE_DIRECTORY):
    """The agent code as the zip a hosted agent is built from, and the hash of each file in it."""
    files = {name: (directory / name).read_bytes() for name in SOURCE_FILES}
    output = io.BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for name, content in files.items():
            zip_entry(archive, name, content)
    return output.getvalue(), {name: hashlib.sha256(content).hexdigest() for name, content in files.items()}


def build_bundle(name, description, instructions, directory=SOURCE_DIRECTORY):
    code, hashes = agent_package(directory)
    manifest = {
        "schema_version": 1, "kind": "prebuilt", "name": name, "description": description,
        "instructions": instructions, "model": None, "runtime": "python_3_14", "cpu": "0.5", "memory": "1Gi",
        "environment": {}, "smoke_test_prompt": SMOKE_TEST_PROMPT, "delegation_checks": [],
        "code_sha256": hashlib.sha256(code).hexdigest(), "files": hashes,
    }
    output = io.BytesIO()
    with ZipFile(output, "w") as archive:
        zip_entry(archive, "manifest.json", json.dumps(manifest, sort_keys=True, indent=2).encode("utf-8"))
        zip_entry(archive, "agent.zip", code)
    return output.getvalue()


class BundleInput(StrictModel):
    name: str = Field(min_length=1, max_length=48)
    description: str = Field(min_length=1, max_length=500)
    instructions: str = Field(min_length=10, max_length=6000)

    @field_validator("name")
    @classmethod
    def slug(cls, value):
        if not SLUG.fullmatch(value):
            raise ValueError("Use lowercase letters, digits and single hyphens")
        return value

    @field_validator("description", "instructions")
    @classmethod
    def text(cls, value, info):
        if "\x00" in value or len(value.strip()) < (10 if info.field_name == "instructions" else 1):
            raise ValueError("Describe the agent")
        return value.strip()


class AgentBundles:
    """POST /api/agent-bundles answers a designer spec with a hosted-agent bundle file. It makes no model call and publishes nothing."""

    def __init__(self, settings):
        self.settings = settings
        self.router = APIRouter()
        self.router.add_api_route("/api/agent-bundles", self.export, methods=["POST"])

    async def export(self, request: Request):
        if not request_allowed(request, self.settings.origins):
            return api_error(request, 403, "request_not_allowed")
        if not self.settings.library_preview_enabled:
            return api_error(request, 503, "library_preview_disabled")
        try:
            body = await read_json_body(request, MAX_REQUEST_BYTES, wrong_type=(400, "invalid_bundle"))
            data = BundleInput.model_validate_json(body)
        except RequestRejected as problem:
            return api_error(request, problem.status, problem.code)
        except ValidationError:
            return api_error(request, 400, "invalid_bundle")
        return Response(
            build_bundle(bundle_name(data.name), data.description, data.instructions),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{data.name}.agent-bundle.zip"'},
        )

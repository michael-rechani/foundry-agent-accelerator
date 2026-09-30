"""Load, verify, and remove the sample policy guidance index for the knowledge-search pilot.

Only ``plan`` is offline. ``load`` and ``remove`` change shared Azure AI Search
data and need ``--confirm``; ``verify`` only reads. See
docs/knowledge-retrieval.md for the approvals, roles, and network path each
command needs.
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence, TextIO

import knowledge_retrieval as kr

API_VERSION = "2025-09-01"
SEARCH_SCOPE = "https://search.azure.com/.default"
CORPUS_PATH = Path(__file__).with_name("knowledge-sample") / "policy-guidance.json"
# The deploy smoke check looks up this query, so the sample set must answer it.
SMOKE_QUERY = "missing evidence"
SMOKE_ID = "POL-EVID-001"
VERSION_MARKER = "sample-"
CORPUS_VERSION = re.compile(r"sample-[a-z0-9.-]{1,32}")
DOCUMENT_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")
DOCUMENT_FIELDS = ("id", "title", "section", "content")
STORED_FIELDS = (*DOCUMENT_FIELDS, "version")
MAX_DOCUMENTS = 25
LIST_LIMIT = 100
REQUEST_TIMEOUT_SECONDS = 30
MAX_RESPONSE_BYTES = 1_000_000
ACCESS_HINT = (
    "Check that the signed-in account has the Search roles this step needs "
    "(see Identity and RBAC in docs/knowledge-retrieval.md) and that this machine "
    "can reach the private endpoint."
)
VERIFY_ATTEMPTS = 10
VERIFY_INTERVAL_SECONDS = 3
FIELDS = (
    {"name": "id", "type": "Edm.String", "key": True, "searchable": False, "filterable": True, "retrievable": True},
    {"name": "title", "type": "Edm.String", "key": False, "searchable": True, "filterable": False, "retrievable": True},
    {"name": "section", "type": "Edm.String", "key": False, "searchable": True, "filterable": False, "retrievable": True},
    {"name": "content", "type": "Edm.String", "key": False, "searchable": True, "filterable": False, "retrievable": True},
    {"name": "version", "type": "Edm.String", "key": False, "searchable": False, "filterable": True, "retrievable": True},
)
COMPARED_ATTRIBUTES = ("type", "key", "searchable", "filterable", "retrievable")

Transport = Callable[[str, str, str, Mapping[str, str], bytes | None], tuple[int, bytes]]


class OperatorError(RuntimeError):
    """A failure whose message is safe to print."""


@dataclass(frozen=True)
class Corpus:
    version: str
    documents: tuple[Mapping[str, str], ...]

    def stored(self) -> list[dict[str, str]]:
        return [{**document, "version": self.version} for document in self.documents]

    def digest(self) -> str:
        canonical = json.dumps(self.stored(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_corpus(path: Path = CORPUS_PATH) -> Corpus:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or set(data) != {"version", "documents"}:
        raise ValueError("The sample set must contain exactly version and documents.")
    version, documents = data["version"], data["documents"]
    if not isinstance(version, str) or not CORPUS_VERSION.fullmatch(version):
        raise ValueError(f"The sample set version must look like {VERSION_MARKER}v1.")
    if not isinstance(documents, list) or not 1 <= len(documents) <= MAX_DOCUMENTS:
        raise ValueError(f"The sample set must hold 1 to {MAX_DOCUMENTS} passages.")
    seen: set[str] = set()
    for document in documents:
        if not isinstance(document, dict) or set(document) != set(DOCUMENT_FIELDS):
            raise ValueError("Each passage needs exactly id, title, section, and content.")
        for field in DOCUMENT_FIELDS:
            value = document[field]
            if not isinstance(value, str) or not value or value != value.strip() or kr.clean_text(value) != value:
                raise ValueError(
                    f"Passage field {field} must be 1-{kr.MAX_FIELD_CHARACTERS} printable characters "
                    "with no leading or trailing space."
                )
        if not DOCUMENT_ID.fullmatch(document["id"]) or document["id"] in seen:
            raise ValueError("Passage ids must be unique letters, digits, dashes, or underscores.")
        seen.add(document["id"])
    smoke = next((document for document in documents if document["id"] == SMOKE_ID), None)
    if smoke is None or SMOKE_QUERY not in smoke["content"].lower():
        raise ValueError(f"Passage {SMOKE_ID} must answer the query \"{SMOKE_QUERY}\".")
    return Corpus(version, tuple(documents))


def index_name(value: str | None) -> str:
    if not value or not kr.INDEX_NAME.fullmatch(value):
        raise ValueError(
            "Set --index or KNOWLEDGE_SEARCH_INDEX to a dedicated index name "
            "of 1-128 lowercase letters, digits, or dashes."
        )
    return value


def endpoint_url(value: str | None) -> str:
    if not value:
        raise ValueError("Set --endpoint or KNOWLEDGE_SEARCH_ENDPOINT to https://<service>.search.windows.net.")
    return kr.search_endpoint(value)


def https_transport(host: str, method: str, path: str, headers: Mapping[str, str], body: bytes | None):
    connection = http.client.HTTPSConnection(host, timeout=REQUEST_TIMEOUT_SECONDS)
    try:
        connection.request(method, path, body=body, headers=dict(headers))
        response = connection.getresponse()
        return response.status, response.read(MAX_RESPONSE_BYTES)
    finally:
        connection.close()


def default_credential():
    try:
        from azure.identity import DefaultAzureCredential
    except ImportError as error:
        raise OperatorError(
            "Install azure-identity first: pip install -r case-review-agent/requirements-deploy.txt"
        ) from error
    return DefaultAzureCredential()


def as_object(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise OperatorError("Search returned an unexpected response.")
    return payload


def error_message(payload: Any) -> str:
    detail = payload.get("error") if isinstance(payload, dict) else None
    message = detail.get("message") if isinstance(detail, dict) else None
    return kr.clean_text(message)[:300] if isinstance(message, str) and message else "no details"


class SearchAdmin:
    def __init__(self, endpoint: str, index: str, credential: Any, transport: Transport = https_transport):
        self.host = kr.search_endpoint(endpoint).removeprefix("https://")
        self.index = index_name(index)
        self.credential = credential
        self.transport = transport

    def call(
        self, method: str, resource: str, body: Mapping[str, Any] | None = None, ok: Sequence[int] = (200,)
    ) -> tuple[int, Any]:
        try:
            token = self.credential.get_token(SEARCH_SCOPE).token
        except Exception as error:
            raise OperatorError(
                f"Couldn't get an Azure token for Search ({type(error).__name__}). "
                "Sign in (for example az login) with the approved account."
            ) from None
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        payload = None
        if body is not None:
            payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf-8"
        try:
            status, raw = self.transport(self.host, method, f"{resource}?api-version={API_VERSION}", headers, payload)
        except (OSError, http.client.HTTPException) as error:
            raise OperatorError(
                "Couldn't reach the Search service. Run this from a network that can reach its private endpoint."
            ) from error
        try:
            parsed = json.loads(raw) if raw else None
        except ValueError:
            parsed = None
        if status not in ok:
            message = f"Search returned HTTP {status}: {error_message(parsed)}"
            if status in (401, 403):
                message += f"\n{ACCESS_HINT}"
            raise OperatorError(message)
        return status, parsed

    def resource(self, suffix: str = "") -> str:
        return f"/indexes('{self.index}'){suffix}"

    def get_index(self) -> dict[str, Any] | None:
        status, payload = self.call("GET", self.resource(), ok=(200, 404))
        return None if status == 404 else as_object(payload)

    def create_index(self) -> None:
        fields = [{**field, "sortable": False, "facetable": False} for field in FIELDS]
        self.call("POST", "/indexes", {"name": self.index, "fields": fields}, ok=(201,))

    def delete_index(self) -> None:
        self.call("DELETE", self.resource(), ok=(204, 404))

    def search(self, query: Mapping[str, Any]) -> list[dict[str, Any]]:
        _, payload = self.call("POST", self.resource("/docs/search.post.search"), query)
        found = as_object(payload).get("value")
        if not isinstance(found, list) or not all(isinstance(item, dict) for item in found):
            raise OperatorError("Search returned an unexpected response.")
        return found

    def documents(self, fields: Sequence[str]) -> list[dict[str, Any]] | None:
        found = self.search(
            {"search": "*", "select": ",".join(fields), "top": LIST_LIMIT + 1, "queryType": "simple"}
        )
        if not all(isinstance(document.get("id"), str) for document in found):
            raise OperatorError("Search returned a document without an id.")
        return None if len(found) > LIST_LIMIT else found

    def write(self, actions: Sequence[Mapping[str, Any]]) -> None:
        if not actions:
            return
        _, payload = self.call(
            "POST", self.resource("/docs/search.index"), {"value": list(actions)}, ok=(200, 207)
        )
        results = as_object(payload).get("value")
        if (
            not isinstance(results, list)
            or len(results) != len(actions)
            or not all(isinstance(result, dict) and result.get("status") is True for result in results)
        ):
            raise OperatorError("Search didn't accept every passage. Run verify to see what was stored.")


def schema_problems(definition: Mapping[str, Any]) -> list[str]:
    fields = definition.get("fields")
    if not isinstance(fields, list):
        return ["The index definition has no fields."]
    actual = {field.get("name"): field for field in fields if isinstance(field, dict)}
    expected_names = {field["name"] for field in FIELDS}
    problems = []
    extra = sorted(str(name) for name in actual if name not in expected_names)
    if extra:
        problems.append(f"Unexpected fields: {', '.join(extra)}.")
    for expected in FIELDS:
        found = actual.get(expected["name"])
        if found is None:
            problems.append(f"Missing field {expected['name']}.")
            continue
        for attribute in COMPARED_ATTRIBUTES:
            if attribute in found and found[attribute] != expected[attribute]:
                problems.append(
                    f"Field {expected['name']}: {attribute} is {found[attribute]!r}, expected {expected[attribute]!r}."
                )
    return problems


def owned(documents: Sequence[Mapping[str, Any]]) -> bool:
    return all(
        isinstance(document.get("version"), str) and document["version"].startswith(VERSION_MARKER)
        for document in documents
    )


def inspect_owned(admin: SearchAdmin, definition: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return the stored documents, or stop if this isn't a dedicated sample index."""
    problems = schema_problems(definition)
    if problems:
        raise OperatorError(
            f"Stopped without changing anything: index {admin.index} doesn't have the sample schema. "
            f"{' '.join(problems)}"
        )
    stored = admin.documents(("id", "version"))
    if stored is None or not owned(stored):
        raise OperatorError(
            f"Stopped without changing anything: index {admin.index} holds documents this script didn't "
            f"load (or more than {LIST_LIMIT}), so it isn't a dedicated sample index."
        )
    return stored


def check(admin: SearchAdmin, corpus: Corpus) -> list[str]:
    definition = admin.get_index()
    if definition is None:
        return [f"Index {admin.index} doesn't exist."]
    problems = schema_problems(definition)
    if problems:
        return problems
    stored = admin.documents(STORED_FIELDS)
    if stored is None:
        return [f"The index holds more than {LIST_LIMIT} documents, so it isn't a dedicated sample index."]
    actual = {str(document.get("id")): document for document in stored}
    expected = {document["id"]: document for document in corpus.stored()}
    problems += [f"Missing passage {key}." for key in sorted(expected.keys() - actual.keys())]
    problems += [f"Unexpected passage {key}." for key in sorted(actual.keys() - expected.keys())]
    for key in sorted(expected.keys() & actual.keys()):
        differing = [field for field in STORED_FIELDS if actual[key].get(field) != expected[key][field]]
        if differing:
            problems.append(f"Passage {key} differs from the approved text ({', '.join(differing)}).")
    found = admin.search(
        {
            "search": SMOKE_QUERY,
            "top": kr.DEFAULT_TOP_K,
            "select": ",".join(kr.DEFAULT_SELECT_FIELDS),
            "queryType": "simple",
            "count": False,
        }
    )
    if SMOKE_ID not in {document.get("id") for document in found}:
        problems.append(f"The query \"{SMOKE_QUERY}\" didn't return {SMOKE_ID}.")
    return problems


def verify(
    admin: SearchAdmin, corpus: Corpus, out: TextIO, sleep: Callable[[float], None] = time.sleep, attempts: int = 1
) -> int:
    problems: list[str] = []
    for attempt in range(attempts):
        problems = check(admin, corpus)
        if not problems:
            break
        if attempt + 1 < attempts:
            sleep(VERIFY_INTERVAL_SECONDS)
    if problems:
        print("Verification failed:", file=out)
        for problem in problems:
            print(f"  - {problem}", file=out)
        return 1
    print(
        f"Verified: {admin.index} holds the {len(corpus.documents)} approved passages "
        f"(version {corpus.version}, digest {corpus.digest()[:16]}), "
        f"and the query \"{SMOKE_QUERY}\" returns {SMOKE_ID}.",
        file=out,
    )
    return 0


def load(admin: SearchAdmin, corpus: Corpus, out: TextIO, sleep: Callable[[float], None] = time.sleep) -> int:
    definition = admin.get_index()
    if definition is None:
        admin.create_index()
        print(f"Created index {admin.index}.", file=out)
        stored: list[dict[str, Any]] = []
    else:
        stored = inspect_owned(admin, definition)
        print(f"Index {admin.index} already exists with the sample schema.", file=out)
    wanted = {document["id"] for document in corpus.documents}
    stale = sorted(str(document.get("id")) for document in stored if document.get("id") not in wanted)
    actions: list[dict[str, Any]] = [{"@search.action": "mergeOrUpload", **document} for document in corpus.stored()]
    actions += [{"@search.action": "delete", "id": key} for key in stale]
    admin.write(actions)
    print(f"Uploaded {len(corpus.documents)} passages and removed {len(stale)} stale sample passages.", file=out)
    return verify(admin, corpus, out, sleep, attempts=VERIFY_ATTEMPTS)


def remove(admin: SearchAdmin, keep_index: bool, out: TextIO) -> int:
    definition = admin.get_index()
    if definition is None:
        print(f"Index {admin.index} doesn't exist. Nothing to remove.", file=out)
        return 0
    stored = inspect_owned(admin, definition)
    if keep_index:
        admin.write([{"@search.action": "delete", "id": document["id"]} for document in stored])
        print(f"Deleted {len(stored)} sample passages and kept the empty index {admin.index}.", file=out)
    else:
        admin.delete_index()
        print(f"Deleted index {admin.index} with its {len(stored)} sample passages.", file=out)
    return 0


def plan(corpus: Corpus, endpoint: str | None, index: str | None, out: TextIO) -> int:
    print("Sample policy guidance for the Case notes summarizer", file=out)
    print(f"  Passages: {len(corpus.documents)} (version {corpus.version}, digest {corpus.digest()[:16]})", file=out)
    print(f"  Index:    {index or 'not set (use --index or KNOWLEDGE_SEARCH_INDEX)'}", file=out)
    print(f"  Endpoint: {endpoint or 'not set (use --endpoint or KNOWLEDGE_SEARCH_ENDPOINT)'}", file=out)
    print("", file=out)
    width = max(len(document["id"]) for document in corpus.documents) + 2
    for document in corpus.documents:
        print(f"  {document['id']:<{width}}{document['section']:<6}{document['title']}", file=out)
    print(
        f"""
Nothing was sent anywhere. With --confirm, load would:
  1. Read the index definition, and create the index only if it doesn't exist.
  2. Stop if the index has another schema or holds documents this script didn't load.
  3. Upload the passages above and delete sample passages that are no longer in the set.
  4. Check the index against the set and look up "{SMOKE_QUERY}".
verify only reads. remove --confirm deletes the index when everything in it is a
sample passage; --keep-index deletes just the passages.

Before load or remove, get approval for the index, the passages, and the temporary
operator roles, and run from a network that can reach the Search endpoint. See
docs/knowledge-retrieval.md.""",
        file=out,
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="knowledge_index.py",
        description="Plan, load, verify, or remove the sample policy guidance index.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    summaries = {
        "plan": "Show what load would do. Offline; never contacts Azure.",
        "load": "Create the index if needed and upload the sample passages. Needs --confirm.",
        "verify": "Check the index against the approved passages. Read-only.",
        "remove": "Delete the sample index, or only its passages. Needs --confirm.",
    }
    for name, summary in summaries.items():
        command = commands.add_parser(name, help=summary, description=summary)
        command.add_argument("--endpoint", help="https://<service>.search.windows.net (default KNOWLEDGE_SEARCH_ENDPOINT)")
        command.add_argument("--index", help="dedicated index name (default KNOWLEDGE_SEARCH_INDEX)")
        if name in ("load", "remove"):
            command.add_argument("--confirm", action="store_true", help="change shared Search data")
        if name == "remove":
            command.add_argument("--keep-index", action="store_true", help="delete the passages but keep the index")
        if name == "verify":
            command.add_argument("--wait", type=int, default=0, metavar="SECONDS", help="retry while indexing catches up")
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    transport: Transport = https_transport,
    credential: Any = None,
    sleep: Callable[[float], None] = time.sleep,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    environ = os.environ if environ is None else environ
    out = stdout if stdout is not None else sys.stdout
    err = stderr if stderr is not None else sys.stderr
    args = build_parser().parse_args(argv)
    try:
        corpus = load_corpus()
        endpoint_text = args.endpoint or environ.get("KNOWLEDGE_SEARCH_ENDPOINT")
        index_text = args.index or environ.get("KNOWLEDGE_SEARCH_INDEX")
        if args.command == "plan":
            endpoint = endpoint_url(endpoint_text) if endpoint_text else None
            index = index_name(index_text) if index_text else None
            return plan(corpus, endpoint, index, out)
        endpoint = endpoint_url(endpoint_text)
        index = index_name(index_text)
    except (OSError, ValueError) as error:
        print(f"Error: {error}", file=err)
        return 2
    if args.command in ("load", "remove") and not args.confirm:
        print(
            "This changes shared Azure AI Search data. Run plan to review it, get the approvals listed in "
            "docs/knowledge-retrieval.md, then repeat with --confirm.",
            file=err,
        )
        return 2
    try:
        admin = SearchAdmin(endpoint, index, credential or default_credential(), transport)
        if args.command == "load":
            return load(admin, corpus, out, sleep)
        if args.command == "remove":
            return remove(admin, args.keep_index, out)
        attempts = 1 + max(0, args.wait) // VERIFY_INTERVAL_SECONDS
        return verify(admin, corpus, out, sleep, attempts)
    except OperatorError as error:
        print(f"Error: {error}", file=err)
        return 1


if __name__ == "__main__":
    sys.exit(main())

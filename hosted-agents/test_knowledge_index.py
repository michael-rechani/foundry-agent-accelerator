"""Offline tests for the sample knowledge index script. Nothing here contacts Azure."""

import asyncio
import contextlib
import http.client
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import deployment
import knowledge_index as ki
import knowledge_retrieval as kr

HERE = Path(__file__).resolve().parent
HOST = "sample-search.search.windows.net"
ENDPOINT = f"https://{HOST}"
INDEX = "policy-guidance-sample"
TOKEN = "test-token-value"
ARGS = ["--endpoint", ENDPOINT, "--index", INDEX]
CORPUS = ki.load_corpus()
EXPECTED = {document["id"]: document for document in CORPUS.stored()}
STALE = {"id": "POL-OLD-001", "title": "Old", "section": "9.9", "content": "Old text.", "version": "sample-v0"}
FOREIGN = {"id": "DOC-1", "title": "Other", "section": "1", "content": "Other text.", "version": "2024"}
UNMARKED = {"id": "DOC-2", "title": "Other", "section": "1", "content": "Other text."}
WORDS = re.compile(r"[a-z0-9]+")


class FakeSearch:
    """In-memory stand-in for the Search REST calls that knowledge_index makes."""

    def __init__(self):
        self.indexes = {}
        self.requests = []
        self.forced = {}
        self.rejected_ids = set()
        self.hidden_searches = 0

    def __call__(self, host, method, path, headers, body):
        route, _, query = path.partition("?")
        payload = json.loads(body) if body else None
        kind, name = self.classify(method, route)
        self.requests.append(
            {
                "host": host,
                "method": method,
                "route": route,
                "query": query,
                "headers": dict(headers),
                "body": payload,
                "kind": kind,
            }
        )
        if kind in self.forced:
            status, content = self.forced[kind]
            return status, content if isinstance(content, bytes) else json.dumps(content).encode("utf-8")
        if kind == "unknown":
            return self.reply(400, {"error": {"message": "Unknown route."}})
        return getattr(self, f"handle_{kind}")(name, payload)

    @staticmethod
    def classify(method, route):
        if method == "POST" and route == "/indexes":
            return "create", None
        match = re.fullmatch(r"/indexes\('([^']+)'\)(/docs/search\.index|/docs/search\.post\.search)?", route)
        if match:
            name, docs = match.groups()
            kinds = {
                (None, "GET"): "get",
                (None, "DELETE"): "delete",
                ("/docs/search.index", "POST"): "write",
                ("/docs/search.post.search", "POST"): "search",
            }
            if (docs, method) in kinds:
                return kinds[(docs, method)], name
        return "unknown", None

    @staticmethod
    def reply(status, payload=None):
        return status, b"" if payload is None else json.dumps(payload).encode("utf-8")

    def missing(self):
        return self.reply(404, {"error": {"message": "No index with that name."}})

    def handle_create(self, _, payload):
        if payload["name"] in self.indexes:
            return self.reply(409, {"error": {"message": "The index already exists."}})
        self.indexes[payload["name"]] = {"fields": payload["fields"], "docs": {}}
        return self.reply(201, payload)

    def handle_get(self, name, _):
        index = self.indexes.get(name)
        if index is None:
            return self.missing()
        return self.reply(200, {"name": name, "fields": index["fields"]})

    def handle_delete(self, name, _):
        if self.indexes.pop(name, None) is None:
            return self.missing()
        return self.reply(204)

    def handle_write(self, name, payload):
        index = self.indexes.get(name)
        if index is None:
            return self.missing()
        allowed = {field["name"] for field in index["fields"]}
        results = []
        for action in payload["value"]:
            document = {key: value for key, value in action.items() if key != "@search.action"}
            accepted = (
                action["@search.action"] in ("mergeOrUpload", "delete")
                and "id" in document
                and set(document) <= allowed
                and document["id"] not in self.rejected_ids
            )
            if accepted and action["@search.action"] == "delete":
                index["docs"].pop(document["id"], None)
            elif accepted:
                index["docs"][document["id"]] = {**index["docs"].get(document["id"], {}), **document}
            results.append({"key": document.get("id"), "status": accepted, "statusCode": 200 if accepted else 400})
        return self.reply(200 if all(result["status"] for result in results) else 207, {"value": results})

    def handle_search(self, name, payload):
        index = self.indexes.get(name)
        if index is None:
            return self.missing()
        names = {field["name"] for field in index["fields"]}
        selected = payload["select"].split(",") if payload.get("select") else sorted(names)
        if (
            not set(selected) <= names
            or not 0 < payload["top"] <= 1000
            or payload.get("queryType", "simple") != "simple"
        ):
            return self.reply(400, {"error": {"message": "Invalid search request."}})
        if self.hidden_searches > 0:
            self.hidden_searches -= 1
            documents = []
        else:
            documents = self.match(index, payload["search"], payload.get("searchMode", "any"))
        value = [
            {"@search.score": 1.0, **{field: document[field] for field in selected if field in document}}
            for document in documents[: payload["top"]]
        ]
        return self.reply(200, {"value": value})

    @staticmethod
    def match(index, query, mode="any"):
        documents = sorted(index["docs"].values(), key=lambda document: document["id"])
        if query == "*":
            return documents
        terms = WORDS.findall(query.lower())
        scored = []
        for document in documents:
            words = WORDS.findall(" ".join(document.get(field, "") for field in ("title", "section", "content")).lower())
            counts = [words.count(term) for term in terms]
            if all(counts) if mode == "all" else any(counts):
                scored.append((-sum(counts), document["id"], document))
        return [document for _, _, document in sorted(scored, key=lambda item: item[:2])]

    def kinds(self):
        return [request["kind"] for request in self.requests]

    def changes(self):
        return [kind for kind in self.kinds() if kind in ("create", "write", "delete")]


class FakeCredential:
    def __init__(self, error=None):
        self.error = error
        self.scopes = []

    def get_token(self, scope):
        self.scopes.append(scope)
        if self.error is not None:
            raise self.error
        return SimpleNamespace(token=TOKEN)


def run(args, *, service=None, credential=None, environ=None):
    service = service if service is not None else FakeSearch()
    credential = credential if credential is not None else FakeCredential()
    out, err, sleeps = io.StringIO(), io.StringIO(), []
    code = ki.main(
        args,
        environ={} if environ is None else environ,
        transport=service,
        credential=credential,
        sleep=sleeps.append,
        stdout=out,
        stderr=err,
    )
    return SimpleNamespace(
        code=code, out=out.getvalue(), err=err.getvalue(), sleeps=sleeps, service=service, credential=credential
    )


def sample_fields():
    return [{**field, "sortable": False, "facetable": False} for field in ki.FIELDS]


def seed(service, *, fields=None, documents=()):
    service.indexes[INDEX] = {
        "fields": fields if fields is not None else sample_fields(),
        "docs": {document["id"]: dict(document) for document in documents},
    }
    return service


def loaded():
    result = run(["load", "--confirm", *ARGS])
    assert result.code == 0, result.out + result.err
    return result.service


def corpus_data(change=None):
    data = json.loads(ki.CORPUS_PATH.read_text(encoding="utf-8"))
    if change is not None:
        change(data)
    return data


def smoke(data):
    return next(document for document in data["documents"] if document["id"] == ki.SMOKE_ID)


class CorpusTests(unittest.TestCase):
    def test_shipped_corpus_is_valid(self):
        self.assertEqual(CORPUS.version, "sample-v1")
        self.assertEqual(len(CORPUS.documents), 10)
        self.assertTrue(all(document["content"].strip() for document in CORPUS.documents))

    def test_smoke_query_matches_the_publish_check(self):
        self.assertEqual(ki.SMOKE_QUERY, "missing evidence")
        self.assertIn(f'the query "{ki.SMOKE_QUERY}"', deployment.KNOWLEDGE_CHECK_PROMPT)

    def test_only_the_smoke_passage_contains_the_query_words(self):
        for document in CORPUS.documents:
            if document["id"] == ki.SMOKE_ID:
                continue
            words = set(WORDS.findall(" ".join(document.values()).lower()))
            with self.subTest(document=document["id"]):
                self.assertFalse(words & set(WORDS.findall(ki.SMOKE_QUERY)))

    def test_passages_avoid_words_the_lab_never_shows(self):
        text = ki.CORPUS_PATH.read_text(encoding="utf-8").lower()
        for word in ("fictional", "made-up", "simulated", "fake", "contoso"):
            with self.subTest(word=word):
                self.assertNotIn(word, text)

    def test_digest_ignores_line_endings_and_changes_with_content(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "corpus.json"
            path.write_bytes(json.dumps(corpus_data(), indent=2).replace("\n", "\r\n").encode("utf-8"))
            self.assertEqual(ki.load_corpus(path).digest(), CORPUS.digest())
            changed = corpus_data(lambda data: smoke(data).update(content=smoke(data)["content"] + " More."))
            path.write_text(json.dumps(changed), encoding="utf-8")
            self.assertNotEqual(ki.load_corpus(path).digest(), CORPUS.digest())
        self.assertRegex(CORPUS.digest(), r"[0-9a-f]{64}")

    def test_invalid_corpora_are_rejected(self):
        def extra_passage(index):
            return {
                "id": f"POL-X-{index}",
                "title": "Extra",
                "section": "9",
                "content": "Extra passage.",
            }

        cases = {
            "version without marker": lambda data: data.update(version="v1"),
            "version in capitals": lambda data: data.update(version="sample-V1"),
            "version not text": lambda data: data.update(version=1),
            "extra top-level key": lambda data: data.update(extra=1),
            "no passages": lambda data: data.update(documents=[]),
            "too many passages": lambda data: data["documents"].extend(extra_passage(i) for i in range(20)),
            "duplicate id": lambda data: data["documents"].append(dict(data["documents"][1])),
            "id with a space": lambda data: data["documents"][1].update(id="POL 1"),
            "id too long": lambda data: data["documents"][1].update(id="P" * 65),
            "extra passage key": lambda data: data["documents"][1].update(url="https://example.com"),
            "missing passage key": lambda data: data["documents"][1].pop("section"),
            "empty field": lambda data: data["documents"][1].update(content=""),
            "padded field": lambda data: data["documents"][1].update(title=" Padded"),
            "control character": lambda data: data["documents"][1].update(content="Bell\u0007 character."),
            "field too long": lambda data: data["documents"][1].update(content="x" * 2001),
            "field not text": lambda data: data["documents"][1].update(section=1.1),
            "smoke passage removed": lambda data: data["documents"].remove(smoke(data)),
            "smoke passage off topic": lambda data: smoke(data).update(content="Something else entirely."),
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "corpus.json"
            for name, change in cases.items():
                with self.subTest(name):
                    path.write_text(json.dumps(corpus_data(change)), encoding="utf-8")
                    with self.assertRaises(ValueError):
                        ki.load_corpus(path)

    def test_corpus_that_is_not_an_object_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "corpus.json"
            path.write_text("[]", encoding="utf-8")
            with self.assertRaises(ValueError):
                ki.load_corpus(path)


class SchemaTests(unittest.TestCase):
    def test_schema_serves_the_retrieval_defaults(self):
        self.assertEqual([field["name"] for field in ki.FIELDS], ["id", "title", "section", "content", "version"])
        self.assertEqual([field["name"] for field in ki.FIELDS if field["key"]], ["id"])
        self.assertTrue(all(field["type"] == "Edm.String" and field["retrievable"] for field in ki.FIELDS))
        self.assertLessEqual(set(kr.DEFAULT_SELECT_FIELDS), {field["name"] for field in ki.FIELDS})
        self.assertEqual(
            {field["name"] for field in ki.FIELDS if field["searchable"]}, {"title", "section", "content"}
        )

    def test_matching_definition_has_no_problems(self):
        self.assertEqual(ki.schema_problems({"fields": sample_fields()}), [])

    def test_attributes_the_service_omits_are_not_compared(self):
        definition = {"fields": [{"name": field["name"], "type": field["type"]} for field in ki.FIELDS]}
        self.assertEqual(ki.schema_problems(definition), [])

    def test_differences_are_reported(self):
        def fields(change):
            result = sample_fields()
            change(result)
            return {"fields": result}

        cases = {
            "Unexpected fields: embedding": fields(lambda f: f.append({"name": "embedding", "type": "Edm.String"})),
            "Missing field version": fields(lambda f: f.pop()),
            "type is 'Edm.Int32'": fields(lambda f: f[1].update(type="Edm.Int32")),
            "Field id: key is False": fields(lambda f: f[0].update(key=False)),
            "Field content: searchable is False": fields(lambda f: f[3].update(searchable=False)),
            "Field content: retrievable is False": fields(lambda f: f[3].update(retrievable=False)),
            "no fields": {"name": INDEX},
        }
        for expected, definition in cases.items():
            with self.subTest(expected):
                self.assertIn(expected, " ".join(ki.schema_problems(definition)))

    def test_only_passages_with_the_sample_marker_are_owned(self):
        self.assertTrue(ki.owned([]))
        self.assertTrue(ki.owned([{"version": "sample-v1"}, {"version": "sample-v0"}]))
        for version in ("v1", "Sample-v1", "", None, 1):
            with self.subTest(version=version):
                self.assertFalse(ki.owned([{"version": version}]))
        self.assertFalse(ki.owned([{"id": "no-version"}]))


class PlanTests(unittest.TestCase):
    def test_plan_is_offline_and_describes_the_work(self):
        service, credential = FakeSearch(), FakeCredential()
        result = run(["plan", *ARGS], service=service, credential=credential)
        self.assertEqual(result.code, 0, result.err)
        self.assertEqual(service.requests, [])
        self.assertEqual(credential.scopes, [])
        self.assertIn("Nothing was sent anywhere", result.out)
        self.assertIn(f"{len(CORPUS.documents)} (version {CORPUS.version}, digest {CORPUS.digest()[:16]})", result.out)
        self.assertIn(INDEX, result.out)
        for document in CORPUS.documents:
            row = re.compile(
                rf"^  {re.escape(document['id'])} +{re.escape(document['section'])} +{re.escape(document['title'])}$",
                re.MULTILINE,
            )
            self.assertRegex(result.out, row)

    def test_plan_works_before_anything_is_configured(self):
        result = run(["plan"])
        self.assertEqual(result.code, 0, result.err)
        self.assertIn("not set", result.out)
        self.assertEqual(result.service.requests, [])

    def test_plan_reads_the_environment_defaults(self):
        result = run(
            ["plan"], environ={"KNOWLEDGE_SEARCH_ENDPOINT": ENDPOINT, "KNOWLEDGE_SEARCH_INDEX": INDEX}
        )
        self.assertEqual(result.code, 0, result.err)
        self.assertIn(ENDPOINT, result.out)
        self.assertIn(INDEX, result.out)

    def test_plan_rejects_a_bad_endpoint(self):
        result = run(["plan", "--endpoint", "http://sample-search.search.windows.net"])
        self.assertEqual(result.code, 2)
        self.assertIn("search.windows.net", result.err)


class SafetyTests(unittest.TestCase):
    def test_changes_need_confirm(self):
        for command in (["load"], ["remove"], ["remove", "--keep-index"]):
            with self.subTest(command=command):
                service, credential = FakeSearch(), FakeCredential()
                result = run([*command, *ARGS], service=service, credential=credential)
                self.assertEqual(result.code, 2)
                self.assertIn("--confirm", result.err)
                self.assertEqual(service.requests, [])
                self.assertEqual(credential.scopes, [])

    def test_bad_endpoints_are_refused_before_any_request(self):
        for endpoint in (
            "http://sample-search.search.windows.net",
            "https://example.com",
            "https://sample-search.search.windows.net:8443",
            "https://user:password@sample-search.search.windows.net",
            "https://sample-search.search.windows.net/indexes",
            "https://sample-search.search.windows.net?x=1",
            "https://.search.windows.net",
            "",
        ):
            for command in (["load", "--confirm"], ["verify"], ["remove", "--confirm"]):
                with self.subTest(endpoint=endpoint, command=command[0]):
                    service = FakeSearch()
                    result = run([*command, "--endpoint", endpoint, "--index", INDEX], service=service)
                    self.assertEqual(result.code, 2)
                    self.assertEqual(service.requests, [])

    def test_bad_index_names_are_refused_before_any_request(self):
        for name in ("Policy_Guidance", "-policy", "policy-", "policy guidance", "a" * 129, ""):
            with self.subTest(name=name):
                service = FakeSearch()
                result = run(["load", "--confirm", "--endpoint", ENDPOINT, f"--index={name}"], service=service)
                self.assertEqual(result.code, 2)
                self.assertEqual(service.requests, [])

    def test_missing_settings_are_explained(self):
        result = run(["verify"])
        self.assertEqual(result.code, 2)
        self.assertIn("--endpoint", result.err)
        result = run(["verify", "--endpoint", ENDPOINT])
        self.assertEqual(result.code, 2)
        self.assertIn("--index", result.err)

    def test_flags_override_the_environment(self):
        service = FakeSearch()
        environ = {
            "KNOWLEDGE_SEARCH_ENDPOINT": "https://other-search.search.windows.net",
            "KNOWLEDGE_SEARCH_INDEX": "other-index",
        }
        result = run(["load", "--confirm", *ARGS], service=service, environ=environ)
        self.assertEqual(result.code, 0, result.err)
        self.assertEqual({request["host"] for request in service.requests}, {HOST})
        self.assertEqual(list(service.indexes), [INDEX])

    def test_environment_defaults_are_used(self):
        environ = {"KNOWLEDGE_SEARCH_ENDPOINT": ENDPOINT, "KNOWLEDGE_SEARCH_INDEX": INDEX}
        result = run(["load", "--confirm"], environ=environ)
        self.assertEqual(result.code, 0, result.err)
        self.assertEqual(list(result.service.indexes), [INDEX])

    def test_token_is_attached_to_every_request_and_never_printed(self):
        service, credential = FakeSearch(), FakeCredential()
        results = [
            run(["load", "--confirm", *ARGS], service=service, credential=credential),
            run(["verify", *ARGS], service=service, credential=credential),
            run(["remove", "--confirm", *ARGS], service=service, credential=credential),
        ]
        self.assertTrue(all(result.code == 0 for result in results), [r.err for r in results])
        self.assertEqual(ki.SEARCH_SCOPE, "https://search.azure.com/.default")
        self.assertEqual(set(credential.scopes), {ki.SEARCH_SCOPE})
        for request in service.requests:
            self.assertEqual(request["headers"]["Authorization"], f"Bearer {TOKEN}")
            self.assertEqual(request["host"], HOST)
            self.assertEqual(request["query"], f"api-version={ki.API_VERSION}")
            self.assertNotIn(TOKEN, json.dumps(request["body"]))
        for result in results:
            self.assertNotIn(TOKEN, result.out + result.err)

    def test_requests_stay_with_the_named_index(self):
        service = loaded()
        run(["remove", "--confirm", *ARGS], service=service)
        for request in service.requests:
            if request["kind"] == "create":
                self.assertEqual(request["body"]["name"], INDEX)
            else:
                self.assertTrue(request["route"].startswith(f"/indexes('{INDEX}')"), request["route"])

    def test_credential_failure_is_reported_without_its_details(self):
        credential = FakeCredential(RuntimeError("tenant 0000 details"))
        result = run(["verify", *ARGS], credential=credential)
        self.assertEqual(result.code, 1)
        self.assertIn("RuntimeError", result.err)
        self.assertIn("az login", result.err)
        self.assertNotIn("tenant 0000", result.err)
        self.assertEqual(result.service.requests, [])

    def test_missing_identity_library_is_explained(self):
        with patch.dict(sys.modules, {"azure.identity": None}):
            with self.assertRaisesRegex(ki.OperatorError, "azure-identity"):
                ki.default_credential()

    def test_unreachable_service_is_reported_without_network_details(self):
        for error in (ConnectionRefusedError("10.0.0.4 refused"), TimeoutError("10.0.0.4 timed out"),
                      http.client.RemoteDisconnected("10.0.0.4 closed")):
            with self.subTest(error=type(error).__name__):
                stdout, stderr = io.StringIO(), io.StringIO()

                def transport(*_, error=error):
                    raise error

                code = ki.main(
                    ["verify", *ARGS], environ={}, transport=transport, credential=FakeCredential(),
                    sleep=lambda _: None, stdout=stdout, stderr=stderr,
                )
                self.assertEqual(code, 1)
                self.assertIn("Couldn't reach the Search service", stderr.getvalue())
                self.assertIn("private endpoint", stderr.getvalue())
                self.assertNotIn("10.0.0.4", stderr.getvalue())

    def test_service_errors_show_a_short_clean_message(self):
        service = FakeSearch()
        service.forced["get"] = (403, {"error": {"message": "Forbidden\x1b[31m " + "x" * 600}})
        result = run(["load", "--confirm", *ARGS], service=service)
        self.assertEqual(result.code, 1)
        self.assertIn("HTTP 403", result.err)
        self.assertIn(ki.ACCESS_HINT, result.err)
        self.assertNotIn("\x1b", result.err)
        self.assertLess(len(result.err), 600)
        self.assertEqual(service.changes(), [])

    def test_service_errors_without_details_are_reported(self):
        service = FakeSearch()
        service.forced["get"] = (502, b"<html>bad gateway</html>")
        result = run(["verify", *ARGS], service=service)
        self.assertEqual(result.code, 1)
        self.assertIn("HTTP 502: no details", result.err)
        self.assertNotIn(ki.ACCESS_HINT, result.err)

    def test_sign_in_errors_point_to_roles_and_network(self):
        service = loaded()
        service.forced["get"] = (401, {"error": {"message": "Unauthorized."}})
        result = run(["verify", *ARGS], service=service)
        self.assertEqual(result.code, 1)
        self.assertIn("HTTP 401: Unauthorized.", result.err)
        self.assertIn(ki.ACCESS_HINT, result.err)

    def test_unexpected_responses_are_reported(self):
        service = loaded()
        service.forced["search"] = (200, {"value": "oops"})
        self.assertIn("unexpected response", run(["verify", *ARGS], service=service).err)
        service.forced["search"] = (200, {"value": [{"title": "no id"}]})
        self.assertIn("without an id", run(["verify", *ARGS], service=service).err)
        service.forced.pop("search")
        service.forced["get"] = (200, [])
        self.assertIn("unexpected response", run(["verify", *ARGS], service=service).err)


class LoadTests(unittest.TestCase):
    def test_load_creates_the_index_and_uploads_the_passages(self):
        service = FakeSearch()
        result = run(["load", "--confirm", *ARGS], service=service)
        self.assertEqual(result.code, 0, result.err)
        self.assertEqual(service.kinds(), ["get", "create", "write", "get", "search", "search"])
        self.assertEqual(service.indexes[INDEX]["docs"], EXPECTED)
        created = next(request["body"] for request in service.requests if request["kind"] == "create")
        self.assertEqual(created["name"], INDEX)
        self.assertEqual([field["name"] for field in created["fields"]], [field["name"] for field in ki.FIELDS])
        self.assertIn("Created index", result.out)
        self.assertIn("Uploaded 10 passages", result.out)
        self.assertIn(f"Verified: {INDEX} holds the 10 approved passages", result.out)
        self.assertIn(CORPUS.digest()[:16], result.out)

    def test_load_twice_changes_nothing(self):
        service = loaded()
        before = json.dumps(service.indexes, sort_keys=True)
        service.requests.clear()
        result = run(["load", "--confirm", *ARGS], service=service)
        self.assertEqual(result.code, 0, result.err)
        self.assertIn("already exists", result.out)
        self.assertNotIn("create", service.kinds())
        self.assertEqual(json.dumps(service.indexes, sort_keys=True), before)

    def test_load_replaces_edited_passages_and_removes_stale_ones(self):
        service = seed(FakeSearch(), documents=[STALE, {**EXPECTED["POL-DATE-001"], "content": "Edited text."}])
        result = run(["load", "--confirm", *ARGS], service=service)
        self.assertEqual(result.code, 0, result.err)
        self.assertEqual(service.indexes[INDEX]["docs"], EXPECTED)
        self.assertIn("removed 1 stale sample passages", result.out)
        self.assertNotIn("create", service.kinds())
        self.assertNotIn("delete", service.kinds())

    def test_load_refuses_passages_it_did_not_load(self):
        for foreign in (FOREIGN, UNMARKED):
            with self.subTest(foreign=foreign["id"]):
                service = seed(FakeSearch(), documents=[EXPECTED["POL-DATE-001"], foreign])
                result = run(["load", "--confirm", *ARGS], service=service)
                self.assertEqual(result.code, 1)
                self.assertIn("Stopped without changing anything", result.err)
                self.assertIn("isn't a dedicated sample index", result.err)
                self.assertEqual(service.changes(), [])
                self.assertIn(foreign["id"], service.indexes[INDEX]["docs"])

    def test_load_refuses_a_large_index(self):
        documents = [{**STALE, "id": f"POL-OLD-{number:03}"} for number in range(ki.LIST_LIMIT + 1)]
        service = seed(FakeSearch(), documents=documents)
        result = run(["load", "--confirm", *ARGS], service=service)
        self.assertEqual(result.code, 1)
        self.assertIn(f"more than {ki.LIST_LIMIT}", result.err)
        self.assertEqual(service.changes(), [])

    def test_load_refuses_a_different_schema(self):
        extra = [*sample_fields(), {"name": "embedding", "type": "Collection(Edm.Single)", "key": False}]
        for name, fields in (
            ("extra field", extra),
            ("missing field", sample_fields()[:-1]),
            ("no key", [{**field, "key": False} for field in sample_fields()]),
        ):
            with self.subTest(name):
                service = seed(FakeSearch(), fields=fields, documents=[STALE])
                result = run(["load", "--confirm", *ARGS], service=service)
                self.assertEqual(result.code, 1)
                self.assertIn("doesn't have the sample schema", result.err)
                self.assertEqual(service.kinds(), ["get"])

    def test_load_reports_passages_the_service_rejects(self):
        service = FakeSearch()
        service.rejected_ids = {"POL-ESC-001"}
        result = run(["load", "--confirm", *ARGS], service=service)
        self.assertEqual(result.code, 1)
        self.assertIn("didn't accept every passage", result.err)

    def test_load_reports_a_reply_that_omits_results(self):
        service = FakeSearch()
        service.forced["write"] = (200, {"value": []})
        result = run(["load", "--confirm", *ARGS], service=service)
        self.assertEqual(result.code, 1)
        self.assertIn("didn't accept every passage", result.err)

    def test_load_reports_index_creation_errors(self):
        service = FakeSearch()
        service.forced["create"] = (403, {"error": {"message": "Not authorized to create indexes."}})
        result = run(["load", "--confirm", *ARGS], service=service)
        self.assertEqual(result.code, 1)
        self.assertIn("HTTP 403: Not authorized to create indexes.", result.err)
        self.assertEqual(service.changes(), ["create"])

    def test_load_waits_for_indexing_to_catch_up(self):
        service = FakeSearch()
        service.hidden_searches = 4
        result = run(["load", "--confirm", *ARGS], service=service)
        self.assertEqual(result.code, 0, result.err)
        self.assertEqual(result.sleeps, [ki.VERIFY_INTERVAL_SECONDS] * 2)
        self.assertIn("Verified", result.out)

    def test_load_fails_when_indexing_never_catches_up(self):
        service = FakeSearch()
        service.hidden_searches = 1000
        result = run(["load", "--confirm", *ARGS], service=service)
        self.assertEqual(result.code, 1)
        self.assertEqual(len(result.sleeps), ki.VERIFY_ATTEMPTS - 1)
        self.assertIn("Verification failed", result.out)

    def test_load_never_deletes_the_index(self):
        for service in (FakeSearch(), seed(FakeSearch(), documents=[STALE])):
            run(["load", "--confirm", *ARGS], service=service)
            self.assertNotIn("delete", service.kinds())


class VerifyTests(unittest.TestCase):
    def test_verify_passes_after_load_and_only_reads(self):
        service = loaded()
        service.requests.clear()
        result = run(["verify", *ARGS], service=service)
        self.assertEqual(result.code, 0, result.out + result.err)
        self.assertEqual(service.kinds(), ["get", "search", "search"])
        self.assertIn(f"returns {ki.SMOKE_ID}", result.out)
        self.assertIn(CORPUS.digest()[:16], result.out)

    def test_verify_fails_when_the_index_is_missing(self):
        result = run(["verify", *ARGS])
        self.assertEqual(result.code, 1)
        self.assertIn("doesn't exist", result.out)

    def test_verify_fails_on_drift(self):
        def missing(docs):
            del docs["POL-ESC-001"]

        def extra(docs):
            docs["POL-NEW-001"] = {**STALE, "id": "POL-NEW-001", "version": CORPUS.version}

        def edited(docs):
            docs["POL-DATE-001"]["content"] = "Edited text."

        def unmarked(docs):
            docs["POL-DATE-001"]["version"] = "2024"

        cases = {
            "Missing passage POL-ESC-001": missing,
            "Unexpected passage POL-NEW-001": extra,
            "Passage POL-DATE-001 differs from the approved text (content)": edited,
            "Passage POL-DATE-001 differs from the approved text (version)": unmarked,
        }
        for expected, change in cases.items():
            with self.subTest(expected):
                service = loaded()
                change(service.indexes[INDEX]["docs"])
                result = run(["verify", *ARGS], service=service)
                self.assertEqual(result.code, 1)
                self.assertIn(expected, result.out)

    def test_verify_fails_when_the_pinned_query_misses_the_smoke_passage(self):
        service = loaded()
        del service.indexes[INDEX]["docs"][ki.SMOKE_ID]
        result = run(["verify", *ARGS], service=service)
        self.assertEqual(result.code, 1)
        self.assertIn(f'The query "{ki.SMOKE_QUERY}" didn\'t return {ki.SMOKE_ID}', result.out)

    def test_verify_fails_on_a_large_index(self):
        service = loaded()
        for number in range(ki.LIST_LIMIT):
            service.indexes[INDEX]["docs"][f"POL-X-{number:03}"] = {**STALE, "id": f"POL-X-{number:03}"}
        result = run(["verify", *ARGS], service=service)
        self.assertEqual(result.code, 1)
        self.assertIn(f"more than {ki.LIST_LIMIT}", result.out)

    def test_verify_fails_on_a_different_schema(self):
        service = seed(FakeSearch(), fields=sample_fields()[:-1])
        result = run(["verify", *ARGS], service=service)
        self.assertEqual(result.code, 1)
        self.assertIn("Missing field version", result.out)

    def test_verify_waits_only_when_asked(self):
        service = loaded()
        service.hidden_searches = 2
        self.assertEqual(run(["verify", *ARGS], service=service).code, 1)
        service.hidden_searches = 4
        result = run(["verify", "--wait", "6", *ARGS], service=service)
        self.assertEqual(result.code, 0, result.out)
        self.assertEqual(result.sleeps, [ki.VERIFY_INTERVAL_SECONDS] * 2)

    def test_verify_wait_is_bounded_by_the_requested_seconds(self):
        service = loaded()
        service.hidden_searches = 1000
        result = run(["verify", "--wait", "9", *ARGS], service=service)
        self.assertEqual(result.code, 1)
        self.assertEqual(len(result.sleeps), 3)
        self.assertEqual(len(run(["verify", "--wait", "-5", *ARGS], service=service).sleeps), 0)


class RemoveTests(unittest.TestCase):
    def test_remove_deletes_the_index_by_default(self):
        service = loaded()
        service.requests.clear()
        result = run(["remove", "--confirm", *ARGS], service=service)
        self.assertEqual(result.code, 0, result.err)
        self.assertEqual(service.kinds(), ["get", "search", "delete"])
        self.assertNotIn(INDEX, service.indexes)
        self.assertIn(f"Deleted index {INDEX} with its 10 sample passages", result.out)
        self.assertEqual(run(["verify", *ARGS], service=service).code, 1)

    def test_remove_can_keep_the_index(self):
        service = loaded()
        service.requests.clear()
        result = run(["remove", "--confirm", "--keep-index", *ARGS], service=service)
        self.assertEqual(result.code, 0, result.err)
        self.assertEqual(service.kinds(), ["get", "search", "write"])
        self.assertEqual(service.indexes[INDEX]["docs"], {})
        self.assertIn("kept the empty index", result.out)

    def test_remove_keeps_going_after_a_partial_failure_is_reported(self):
        service = loaded()
        service.rejected_ids = {"POL-ESC-001"}
        result = run(["remove", "--confirm", "--keep-index", *ARGS], service=service)
        self.assertEqual(result.code, 1)
        self.assertIn("didn't accept every passage", result.err)

    def test_remove_does_nothing_when_the_index_is_gone(self):
        service = FakeSearch()
        result = run(["remove", "--confirm", *ARGS], service=service)
        self.assertEqual(result.code, 0)
        self.assertIn("Nothing to remove", result.out)
        self.assertEqual(service.kinds(), ["get"])

    def test_remove_refuses_an_index_it_did_not_load(self):
        for foreign in (FOREIGN, UNMARKED):
            for flags in ([], ["--keep-index"]):
                with self.subTest(foreign=foreign["id"], flags=flags):
                    service = seed(FakeSearch(), documents=[EXPECTED["POL-DATE-001"], foreign])
                    result = run(["remove", "--confirm", *flags, *ARGS], service=service)
                    self.assertEqual(result.code, 1)
                    self.assertIn("Stopped without changing anything", result.err)
                    self.assertEqual(service.changes(), [])
                    self.assertEqual(len(service.indexes[INDEX]["docs"]), 2)

    def test_remove_refuses_a_different_schema(self):
        service = seed(FakeSearch(), fields=sample_fields()[:-1])
        result = run(["remove", "--confirm", *ARGS], service=service)
        self.assertEqual(result.code, 1)
        self.assertIn("doesn't have the sample schema", result.err)
        self.assertEqual(service.changes(), [])

    def test_remove_refuses_a_large_index(self):
        documents = [{**STALE, "id": f"POL-OLD-{number:03}"} for number in range(ki.LIST_LIMIT + 1)]
        service = seed(FakeSearch(), documents=documents)
        result = run(["remove", "--confirm", *ARGS], service=service)
        self.assertEqual(result.code, 1)
        self.assertEqual(service.changes(), [])


class RetrievalContractTests(unittest.TestCase):
    """The loaded sample index answers the retrieval tool the way the publish check expects."""

    class Client:
        def __init__(self, service):
            self.service = service

        def search(self, *, search_text, search_mode, top, select, query_type, include_total_count):
            payload = {
                "search": search_text,
                "searchMode": search_mode,
                "top": top,
                "select": ",".join(select),
                "queryType": query_type,
                "count": include_total_count,
            }
            status, raw = self.service.handle_search(INDEX, payload)
            assert status == 200, raw
            return iter(json.loads(raw)["value"])

    def lookup(self, service, query):
        settings = kr.read_settings(
            {
                "KNOWLEDGE_RETRIEVAL_ENABLED": "true",
                "KNOWLEDGE_SEARCH_ENDPOINT": ENDPOINT,
                "KNOWLEDGE_SEARCH_INDEX": INDEX,
            }
        )
        [tool] = kr.create_knowledge_tools(settings, object(), "case-review-agent", lambda *_: self.Client(service))
        return json.loads(asyncio.run(tool(query)))

    def test_pinned_query_returns_the_smoke_passage(self):
        result = self.lookup(loaded(), ki.SMOKE_QUERY)
        self.assertEqual(result["status"], "succeeded")
        self.assertIn(ki.SMOKE_ID, result["source_ids"])
        passages = json.loads(result["output"].split("\n", 1)[1])["passages"]
        smoke_passage = next(passage for passage in passages if passage["source_id"] == ki.SMOKE_ID)
        self.assertEqual(smoke_passage["content"], EXPECTED[ki.SMOKE_ID]["content"])
        self.assertEqual(set(smoke_passage), {"source_id", "title", "section", "content"})

    def test_unrelated_query_finds_nothing(self):
        result = self.lookup(loaded(), "quarterly rainfall totals")
        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(result["source_ids"], [])
        self.assertEqual(result["output"], kr.NO_MATCH)

    def test_query_with_one_matching_word_finds_nothing(self):
        # "staff" appears in three passages, but none has all three words. The live check on 1 Oct 2026
        # returned those three passages before the lookup required every word.
        result = self.lookup(loaded(), "staff parking permit")
        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(result["source_ids"], [])
        self.assertEqual(result["output"], kr.NO_MATCH)

    def test_reordered_words_still_find_the_passage(self):
        result = self.lookup(loaded(), "evidence missing")
        self.assertEqual(result["source_ids"], [ki.SMOKE_ID])

    def test_a_synonym_for_a_passage_word_finds_nothing(self):
        # The accepted cost of requiring every word: "proof" doesn't match "evidence".
        result = self.lookup(loaded(), "missing proof")
        self.assertEqual(result["source_ids"], [])

    def test_every_passage_fits_the_tool_limits(self):
        for document in CORPUS.documents:
            for field in ki.DOCUMENT_FIELDS:
                with self.subTest(document=document["id"], field=field):
                    self.assertEqual(kr.clean_text(document[field]), document[field])
        sizes = sorted((len(json.dumps(document, ensure_ascii=False)) for document in CORPUS.documents), reverse=True)
        self.assertLess(len(kr.UNTRUSTED_HEADER) + sum(sizes[: kr.DEFAULT_TOP_K]), kr.MAX_OUTPUT_CHARACTERS)


class TransportTests(unittest.TestCase):
    class Connection:
        instances = []
        fail = None

        def __init__(self, host, **kwargs):
            self.host, self.kwargs, self.closed, self.sent, self.limit = host, kwargs, False, None, None
            type(self).instances.append(self)

        def request(self, method, path, body=None, headers=None):
            if self.fail is not None:
                raise self.fail
            self.sent = (method, path, body, headers)

        def getresponse(self):
            connection = self

            class Response:
                status = 201

                def read(self, limit=None):
                    connection.limit = limit
                    return b'{"ok": true}'

            return Response()

        def close(self):
            self.closed = True

    def setUp(self):
        self.Connection.instances = []
        self.Connection.fail = None

    def test_request_uses_a_verified_bounded_connection(self):
        with patch.object(http.client, "HTTPSConnection", self.Connection):
            status, body = ki.https_transport(HOST, "POST", "/indexes?api-version=1", {"A": "b"}, b"{}")
        [connection] = self.Connection.instances
        self.assertEqual((status, body), (201, b'{"ok": true}'))
        self.assertEqual(connection.host, HOST)
        self.assertEqual(connection.kwargs, {"timeout": ki.REQUEST_TIMEOUT_SECONDS})
        self.assertEqual(connection.sent, ("POST", "/indexes?api-version=1", b"{}", {"A": "b"}))
        self.assertEqual(connection.limit, ki.MAX_RESPONSE_BYTES)
        self.assertTrue(connection.closed)

    def test_connection_closes_when_the_request_fails(self):
        self.Connection.fail = ConnectionResetError("reset")
        with patch.object(http.client, "HTTPSConnection", self.Connection):
            with self.assertRaises(ConnectionResetError):
                ki.https_transport(HOST, "GET", "/indexes('x')?api-version=1", {}, None)
        self.assertTrue(self.Connection.instances[0].closed)


class ScriptTests(unittest.TestCase):
    def run_script(self, *arguments):
        environment = {key: value for key, value in os.environ.items() if not key.startswith("KNOWLEDGE_")}
        return subprocess.run(
            [sys.executable, str(HERE / "knowledge_index.py"), *arguments],
            capture_output=True,
            text=True,
            timeout=60,
            env=environment,
            check=False,
        )

    def test_plan_runs_from_the_command_line_without_azure(self):
        completed = self.run_script("plan")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("Nothing was sent anywhere", completed.stdout)

    def test_load_without_confirm_stops_before_contacting_azure(self):
        completed = self.run_script("load", *ARGS)
        self.assertEqual(completed.returncode, 2)
        self.assertIn("--confirm", completed.stderr)

    def test_default_streams_are_used_when_none_are_given(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.assertEqual(ki.main(["plan"], environ={}), 0)
            self.assertEqual(ki.main(["verify"], environ={}), 2)
        self.assertIn("Nothing was sent anywhere", out.getvalue())
        self.assertIn("--endpoint", err.getvalue())


if __name__ == "__main__":
    unittest.main()

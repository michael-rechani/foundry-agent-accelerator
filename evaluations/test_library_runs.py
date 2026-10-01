"""Offline tests for library_runs.py. Nothing here calls Foundry, the network or the Azure SDK."""
import asyncio
import contextlib
import copy
import datetime
import inspect
import io
import json
import os
import re
import shutil
import socket
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest import mock

import library_runs as lr
import scorecards
# library_runs puts workbench/ on sys.path, which these imports need.
from agent_runtime.main import DEMO_POLICY
from agent_templates import TEMPLATE_METADATA, TEMPLATES

TODAY = "2026-10-02"
RECORDED = "2026-09-01"
ENDPOINT = "https://lab.services.ai.azure.com/api/projects/lab"
ENV = {lr.ENV_ENDPOINT: ENDPOINT}
DOC, FLOW = "document-analyst", "workflow-coordinator"
CASE_IDS = {
    DOC: ["document-analyst-sample", "document-analyst-missing-version"],
    FLOW: ["workflow-coordinator-grounded-access", "workflow-coordinator-missing-request"],
}
MODELS = {DOC: "gpt-5.4", FLOW: "gpt-4.1"}
USAGE = {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150,
         "input_tokens_details": {"cached_tokens": 20}, "output_tokens_details": {"reasoning_tokens": 0}}
LOOKUP = {"type": "function_call", "name": "lookup_demo_request", "call_id": "call-1",
          "arguments": json.dumps({"request_id": "REQ-101"})}


class FakeClock:
    """Time the tests control: sleeping moves it forward and costs nothing."""

    def __init__(self):
        self.now, self.slept = 1000.0, []

    def __call__(self):
        return self.now

    async def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds


class HttpError(Exception):
    def __init__(self, status, headers=None):
        super().__init__(f"HTTP {status}")
        self.status_code = status
        self.response = SimpleNamespace(headers=headers or {})


class APIConnectionError(Exception):
    """Named like the OpenAI SDK's error, which retry_delay recognizes by its name."""


class Response:
    def __init__(self, output, text="", status="completed", usage=USAGE):
        self.output, self.output_text, self.status, self.usage = output, text, status, usage

    def model_dump(self, exclude_none=False):
        return {"output": [dict(item) for item in self.output]}


def message(text="Answer", **changes):
    return Response([{"type": "message"}], text=text, **changes)


class FakeFoundry:
    """Stands in for Foundry. It remembers each request and when it came, takes 1.5 s to answer, and
    raises or returns what the script says before falling back to a plain answer."""

    def __init__(self, clock, script=(), start=0):
        self.clock, self.script, self.start = clock, list(script), start
        self.calls, self.times = [], []

    async def send(self, options):
        self.calls.append(copy.deepcopy(options))
        self.times.append(self.clock())
        self.clock.now += 1.5
        step = self.script.pop(0) if self.script else None
        if isinstance(step, BaseException):
            raise step
        return step or self.answer(options)

    def answer(self, options):
        if options.get("tools") and options["input"][-1].get("type") != "function_call_output":
            return Response([LOOKUP])
        return message(f"Answer {self.start + len(self.calls)}")


def run_row(template_id, case_id, run, **changes):
    """One recorded run, the way the runner saves it, on the Lab's current instructions."""
    row = {"case_id": case_id, "run": run, "text": f"Recorded answer for {case_id}, run {run}.", "receipts": [],
           "model": MODELS[template_id], "seconds": 1.5, "input_tokens": 100, "cached_tokens": 20,
           "output_tokens": 50, "instructions_sha256": scorecards.instructions_digest(template_id),
           "recorded_on": RECORDED}
    row.update(changes)
    return row


def recorded_rows(template_id):
    """An agent's rows in the answers, metrics and repeats files."""
    runs = [run_row(template_id, case_id, run) for case_id in CASE_IDS[template_id] for run in range(1, 6)]
    return ([lr.project(row, lr.ANSWER_ROW) for row in runs if row["run"] == 1],
            [lr.project(row, lr.METRICS_ROW) for row in runs if row["run"] == 1],
            [lr.project(row, lr.RUN_ROW) for row in runs if row["run"] > 1])


def mini_cases():
    """The real cases of the two agents the tests use."""
    data = lr.load_cases(lr.CASES_PATH)
    keep = {case_id for ids in CASE_IDS.values() for case_id in ids}
    return {**data, "cases": [case for case in data["cases"] if case["id"] in keep]}


def write_rows(path, rows, newline="\n"):
    path.write_bytes("".join(json.dumps(row) + newline for row in rows).encode("utf-8"))


@contextlib.contextmanager
def no_network():
    """Fail the test if anything tries to connect. Not for tests that run asyncio: on Windows the
    event loop connects a local socket pair."""
    def refuse(*args, **kwargs):
        raise AssertionError("the network was used")

    with (mock.patch("socket.getaddrinfo", refuse), mock.patch("socket.create_connection", refuse),
          mock.patch.object(socket.socket, "connect", refuse)):
        yield


@contextlib.contextmanager
def edited(template_id):
    """The Lab changes an agent's instructions."""
    with mock.patch.dict(TEMPLATES[template_id], {"instructions": TEMPLATES[template_id]["instructions"] + " One more rule."}):
        yield


class Scratch(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)

    def assertStops(self, code, call, *args, **kwargs):
        with self.assertRaises(lr.Stop) as caught:
            call(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)
        return str(caught.exception)


class LabFiles(Scratch):
    """A scratch copy of the evidence for two agents, and a way to run the command against it."""

    def setUp(self):
        super().setUp()
        for agent in CASE_IDS:
            self.enterContext(mock.patch.dict(TEMPLATE_METADATA[agent], {"readiness": "sample"}))
        self.clock = FakeClock()
        self.files = lr.Files(
            cases=self.root / "cases.json", answers=self.root / "answers.jsonl", metrics=self.root / "metrics.jsonl",
            repeats=self.root / "repeats.jsonl", prices=self.root / "prices.json", signoffs=self.root / "signoffs.json",
            journals=self.root / "journals")
        self.files.cases.write_text(json.dumps(mini_cases()), encoding="utf-8")
        shutil.copyfile(scorecards.PRICES, self.files.prices)
        self.write_evidence()

    @property
    def evidence_paths(self):
        return self.files.answers, self.files.metrics, self.files.repeats

    def write_evidence(self, replace=None):
        """Write both agents' recorded rows. `replace` gives an agent's (answers, metrics, repeats) instead."""
        parts = {agent: recorded_rows(agent) for agent in CASE_IDS}
        parts.update(replace or {})
        for index, path in enumerate(self.evidence_paths):
            write_rows(path, [row for agent in CASE_IDS for row in parts[agent][index]])

    def snapshot(self):
        paths = (*self.evidence_paths, self.files.signoffs)
        return {path.name: path.read_bytes() if path.exists() else None for path in paths}

    def item(self, template_id, model=None):
        cases = [case for case in lr.load_cases(self.files.cases)["cases"] if case["template_id"] == template_id]
        return lr.Item(template_id, TEMPLATES[template_id]["model_profile"], cases,
                       scorecards.instructions_digest(template_id), model or MODELS[template_id], "--model")

    def prompt(self, case_id):
        return lr.case_input(next(case for case in lr.load_cases(self.files.cases)["cases"] if case["id"] == case_id))

    def journal(self, template_id, rows=(), tail=b""):
        path = self.files.journal(template_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"".join(lr.dump(row).encode("utf-8") + b"\n" for row in rows) + tail)
        return path

    def saved(self, template_id, count, case=0):
        """The first `count` runs of one case, as an interrupted recording would have saved them."""
        return [run_row(template_id, CASE_IDS[template_id][case], run) for run in range(1, count + 1)]

    def foundry(self, script=(), start=0):
        return FakeFoundry(self.clock, script, start)

    def sign_off(self, *template_ids):
        scorecards.record_signoff("Reviewer One", "2026-09-30", list(template_ids), path=self.files.signoffs,
                                  cases_path=self.files.cases, runs=(("direct", self.files.answers),))

    def run_main(self, *argv, foundry=None, environ=None, today=TODAY):
        foundry = foundry or self.foundry()
        opened = []

        @contextlib.contextmanager
        def open_client(endpoint):
            opened.append(endpoint)
            yield foundry.send

        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = lr.main(list(argv), files=self.files, open_client=open_client, clock=self.clock,
                           sleep=self.clock.sleep, today=today, environ=ENV if environ is None else environ)
        return SimpleNamespace(code=code, out=out.getvalue(), err=err.getvalue(), opened=opened, foundry=foundry)

    def build(self):
        return scorecards.build(cases_path=self.files.cases, runs=(("direct", self.files.answers),),
                                metrics_path=self.files.metrics, prices_path=self.files.prices,
                                signoffs_path=self.files.signoffs, repeats_path=self.files.repeats)

    def dates(self):
        return {card["template_id"]: card["tested_on"] for card in self.build()["scorecards"]}


class SettingsTests(Scratch):
    def test_limits_are_read_from_json(self):
        for empty in (None, "", "{}"):
            self.assertEqual(lr.parse_limits(empty), {})
        text = '{"gpt-5.4": {"tokens": 30000, "requests": 30}, "gpt-4.1": {"tokens": 5}, "gpt-x": {"requests": 7}}'
        self.assertEqual(lr.parse_limits(text), {"gpt-5.4": {"tokens": 30000, "requests": 30},
                                                 "gpt-4.1": {"tokens": 5}, "gpt-x": {"requests": 7}})

    def test_bad_limits_are_refused(self):
        for text in ("nope", "null", "5", "[]", '{"m": 5}', '{"m": {}}', '{"m": {"tokens": 0}}',
                     '{"m": {"tokens": -5}}', '{"m": {"tokens": 1.5}}', '{"m": {"tokens": true}}',
                     '{"m": {"tokens": "5"}}', '{"m": {"minutes": 5}}', '{"bad name": {"tokens": 5}}'):
            with self.subTest(text=text):
                self.assertIn("--limits must look like", self.assertStops(2, lr.parse_limits, text))

    def models(self, ids=(DOC,), **kwargs):
        return lr.resolve_models(list(ids), model=kwargs.get("model"), models=kwargs.get("models"),
                                 environ=kwargs.get("environ", {}), recorded=kwargs.get("recorded", {}))

    def test_a_model_is_chosen_in_a_fixed_order(self):
        settings = dict(model="m1", models='{"reasoning": "m2"}', recorded={DOC: "m5"},
                        environ={lr.ENV_MODELS: '{"reasoning": "m3"}', lr.ENV_MODEL: "m4"})
        self.assertEqual(self.models(**settings), {DOC: ("m1", "--model")})
        del settings["model"]
        self.assertEqual(self.models(**settings), {DOC: ("m2", "--models")})
        del settings["models"]
        self.assertEqual(self.models(**settings), {DOC: ("m3", lr.ENV_MODELS)})
        settings["environ"] = {lr.ENV_MODEL: "m4"}
        self.assertEqual(self.models(**settings), {DOC: ("m4", lr.ENV_MODEL)})
        settings["environ"] = {}
        self.assertEqual(self.models(**settings), {DOC: ("m5", "its last recording")})
        del settings["recorded"]
        self.assertIn("No model deployment for document-analyst (reasoning)", self.assertStops(2, self.models, **settings))

    def test_a_models_map_applies_only_to_its_profile(self):
        chosen = self.models((DOC, FLOW), models='{"reasoning": "gpt-y"}', recorded={FLOW: "gpt-4.1"})
        self.assertEqual(chosen, {DOC: ("gpt-y", "--models"), FLOW: ("gpt-4.1", "its last recording")})
        self.assertEqual(self.models(models="", model="gpt-z"), {DOC: ("gpt-z", "--model")})

    def test_bad_model_settings_are_refused(self):
        for settings in ({"models": "nope"}, {"models": '["a"]'}, {"models": '{"reasoning": 5}'},
                         {"models": '{"imaginary": "gpt"}'}, {"models": '{"reasoning": "has space"}'},
                         {"environ": {lr.ENV_MODELS: "{"}}, {"model": "has space"},
                         {"environ": {lr.ENV_MODEL: "-lead"}}):
            with self.subTest(settings=settings):
                self.assertStops(2, self.models, **settings)

    def test_endpoints_must_be_https_foundry_projects(self):
        for good in (ENDPOINT, "https://lab.services.ai.azure.com:443/api/projects/lab",
                     "https://LAB.services.ai.azure.com/api/projects/my_project-1"):
            self.assertEqual(lr.validate_endpoint(good), good)
        for bad in (ENDPOINT + "/", ENDPOINT + "?x=1", ENDPOINT + "#frag", "http://lab.services.ai.azure.com/api/projects/lab",
                    "https://lab.services.ai.azure.com:8443/api/projects/lab",
                    "https://lab.services.ai.azure.com:99999/api/projects/lab", "https:///api/projects/lab",
                    "https://lab.services.ai.azure.com/api/projects/", "https://lab.services.ai.azure.com/api/projects/a/b",
                    "https://lab.services.ai.azure.com/api/projects/la b",
                    "https://user:secret@lab.services.ai.azure.com/api/projects/lab"):
            with self.subTest(endpoint=bad):
                reason = self.assertStops(2, lr.validate_endpoint, bad)
                self.assertIn("HTTPS Foundry project URL", reason)
                self.assertNotIn("secret", reason)
        for missing in ("", None):
            self.assertIn("Say which Foundry project", self.assertStops(2, lr.validate_endpoint, missing))

    def test_agents_are_picked_by_name_without_repeats(self):
        grouped = {"a": [1], "b": [2], "c": [3]}
        self.assertEqual(lr.pick_templates(grouped, None), ["a", "b", "c"])
        self.assertEqual(lr.pick_templates(grouped, ["c", "a", "c"]), ["c", "a"])
        reason = self.assertStops(2, lr.pick_templates, grouped, ["a", "nope", "also-not"])
        self.assertIn("No test cases for: also-not, nope", reason)


class PacerTests(unittest.TestCase):
    def pacer(self, limits=None):
        clock = FakeClock()
        return clock, lr.Pacer(limits or {}, clock, clock.sleep)

    def test_requests_wait_for_the_oldest_to_leave_the_minute(self):
        clock, pacer = self.pacer({"m": {"requests": 3, "tokens": 10**9}})

        async def go():
            for _ in range(4):
                await pacer.acquire("m")

        asyncio.run(go())
        self.assertEqual(clock.slept, [60.0])

    def test_tokens_wait_for_enough_of_the_minute_to_pass(self):
        clock, pacer = self.pacer({"m": {"tokens": 100, "requests": 1000}})

        async def go():
            for _ in range(3):
                entry = await pacer.acquire("m")
                pacer.release("m", entry, 60)

        asyncio.run(go())
        self.assertEqual(clock.slept, [60.0, 60.0])

    def test_each_model_deployment_has_its_own_limits(self):
        clock, pacer = self.pacer({"a": {"requests": 1, "tokens": 10**9}, "b": {"requests": 1, "tokens": 10**9}})
        waited = []

        async def go():
            await pacer.acquire("a")
            await pacer.acquire("b")
            waited.append(list(clock.slept))
            await pacer.acquire("a")

        asyncio.run(go())
        self.assertEqual(waited, [[]])
        self.assertEqual(clock.slept, [60.0])

    def test_reported_tokens_replace_the_guess(self):
        _, pacer = self.pacer()

        async def go():
            entry = await pacer.acquire("m")
            self.assertEqual(entry[1], lr.FIRST_ESTIMATE)
            pacer.release("m", entry, None)
            self.assertEqual((entry[1], pacer.observed), (lr.FIRST_ESTIMATE, {}))
            pacer.release("m", entry, 700)
            self.assertEqual((entry[1], pacer.observed["m"]), (700, [700]))

        asyncio.run(go())

    def test_only_the_last_ten_counts_are_remembered(self):
        _, pacer = self.pacer()
        for tokens in range(12):
            pacer.release("m", [0, 0], tokens)
        self.assertEqual(pacer.observed["m"], list(range(2, 12)))

    def test_the_first_guess_never_exceeds_the_limit(self):
        _, pacer = self.pacer({"m": {"tokens": 1000}})
        self.assertEqual(asyncio.run(pacer.acquire("m"))[1], 1000)

    def test_a_request_bigger_than_the_limit_still_goes_through(self):
        clock, pacer = self.pacer({"m": {"tokens": 1000, "requests": 100}})

        async def go():
            for _ in range(2):
                entry = await pacer.acquire("m")
                pacer.release("m", entry, 5000)

        asyncio.run(go())
        self.assertEqual(clock.slept, [60.0])


class RetryTests(unittest.TestCase):
    def test_retry_after_headers_are_read(self):
        for headers, expected in (({"retry-after-ms": "2500"}, 2.5), ({"retry-after": "7"}, 7.0),
                                  ({"retry-after-ms": "1500", "retry-after": "9"}, 1.5),
                                  ({"retry-after-ms": "abc", "retry-after": "4"}, 4.0), ({}, None),
                                  ({"retry-after": "Wed, 21 Oct 2026 07:28:00 GMT"}, None),
                                  ({"retry-after": "-3"}, None), ({"retry-after": "nan"}, None),
                                  ({"retry-after": "inf"}, None)):
            with self.subTest(headers=headers):
                self.assertEqual(lr.retry_after(headers), expected)

    def test_rate_limits_wait_as_long_as_foundry_asks(self):
        for headers, expected in (({"retry-after-ms": "2500"}, 2.5), ({"retry-after": "7"}, 7.0),
                                  ({"retry-after-ms": "100"}, 1.0), ({"retry-after": "500"}, 120.0),
                                  ({}, 60.0), ({"retry-after": "junk"}, 60.0)):
            with self.subTest(headers=headers):
                self.assertEqual(lr.retry_delay(HttpError(429, headers), 1), expected)
        self.assertEqual(lr.retry_delay(SimpleNamespace(status_code=429), 1), 60.0)

    def test_server_errors_back_off_up_to_thirty_seconds(self):
        self.assertEqual([lr.retry_delay(HttpError(500), attempt) for attempt in range(1, 7)],
                         [2.0, 4.0, 8.0, 16.0, 30.0, 30.0])

    def test_other_temporary_failures_are_retried(self):
        for error in (HttpError(408), HttpError(409), HttpError(503), TimeoutError(), ConnectionResetError(),
                      APIConnectionError()):
            with self.subTest(error=type(error).__name__):
                self.assertEqual(lr.retry_delay(error, 2), 4.0)

    def test_errors_that_waiting_cannot_fix_are_not_retried(self):
        for error in (HttpError(400), HttpError(401), HttpError(403), HttpError(404), ValueError(), KeyError("x")):
            with self.subTest(error=type(error).__name__):
                self.assertIsNone(lr.retry_delay(error, 1))

    def test_a_failure_is_described_in_one_short_line(self):
        self.assertEqual(lr.describe(HttpError(500)), "HttpError (HTTP 500): HTTP 500")
        self.assertEqual(lr.describe(ValueError()), "ValueError")
        self.assertEqual(lr.describe(ValueError("a\n   b")), "ValueError: a b")
        self.assertLessEqual(len(lr.describe(ValueError("x" * 500))), 220)
        self.assertNotIn("secret", lr.describe(HttpError(429, {"authorization": "Bearer secret"})))


class PacedClientTests(unittest.TestCase):
    def paced(self, script=()):
        clock = FakeClock()
        foundry = FakeFoundry(clock, script)
        pacer = lr.Pacer({"m": {"tokens": 10**9, "requests": 10**9}}, clock, clock.sleep)
        logs = []
        client = lr.PacedClient(foundry.send, pacer, clock=clock, sleep=clock.sleep, log=logs.append)
        return clock, foundry, pacer, client, logs

    def create(self, client):
        return asyncio.run(client.create(model="m", input=[{"role": "user", "content": "hi"}]))

    def test_a_rate_limit_is_waited_out_and_the_request_sent_again(self):
        clock, foundry, _, client, logs = self.paced([HttpError(429, {"retry-after-ms": "2500"})])
        self.create(client)
        self.assertEqual(clock.slept, [2.5])
        self.assertEqual(len(foundry.calls), 2)
        self.assertEqual(client.seconds, 1.5)
        self.assertEqual(len(logs), 1)
        self.assertIn("HTTP 429", logs[0])
        self.assertIn("try 1 of 6", logs[0])

    def test_it_gives_up_after_six_tries(self):
        clock, foundry, _, client, _ = self.paced([HttpError(500) for _ in range(6)])
        with self.assertRaises(lr.Stop) as caught:
            self.create(client)
        self.assertEqual(caught.exception.code, 1)
        self.assertEqual(str(caught.exception), "Foundry request failed after 6 tries: HttpError (HTTP 500): HTTP 500")
        self.assertEqual(clock.slept, [2.0, 4.0, 8.0, 16.0, 30.0])
        self.assertEqual(len(foundry.calls), 6)

    def test_a_request_that_cannot_work_is_not_repeated(self):
        clock, foundry, _, client, _ = self.paced([HttpError(400)])
        with self.assertRaises(lr.Stop) as caught:
            self.create(client)
        self.assertIn("failed after 1 try: HttpError (HTTP 400)", str(caught.exception))
        self.assertEqual((clock.slept, len(foundry.calls)), ([], 1))

    def test_the_pacer_learns_the_tokens_a_request_used(self):
        for usage, expected in ((USAGE, 150), ({"input_tokens": 60, "output_tokens": 40}, 100),
                                (None, lr.FIRST_ESTIMATE)):
            with self.subTest(usage=usage):
                _, _, pacer, client, _ = self.paced([message(usage=usage)])
                self.create(client)
                self.assertEqual(pacer.sent["m"][0][1], expected)

    def test_dropped_connections_and_timeouts_are_retried(self):
        clock, foundry, _, client, logs = self.paced([ConnectionResetError(), TimeoutError()])
        response = self.create(client)
        self.assertEqual(response.output_text, "Answer 3")
        self.assertEqual(clock.slept, [2.0, 4.0])
        self.assertEqual(len(logs), 2)
        self.assertEqual(client.seconds, 1.5)
        self.assertEqual(len(foundry.calls), 3)


class RowFileTests(Scratch):
    DATA = b'{"case_id": "a", "n": 1}\n{"case_id": "b", "n": 2}\n\n{"case_id": "a", "n": 3}\n{"case_id": "c", "n": 4}\n'

    def test_each_row_stays_on_one_line(self):
        row = {"text": "a\u2028b\u2029c\x85d caf\u00e9"}
        line = lr.dump(row)
        self.assertEqual(len(line.splitlines()), 1)
        self.assertEqual(json.loads(line), row)
        self.assertIn("caf\u00e9", line)
        self.assertIn("\\u2028", line)
        self.assertIn("\\u0085", line)

    def test_new_rows_take_the_place_of_the_old_ones_and_nothing_else_moves(self):
        a9 = {"case_id": "a", "n": 9}
        self.assertEqual(lr.replace_rows(self.DATA, {"a"}, [a9], "x.jsonl"),
                         b'{"case_id": "a", "n": 9}\n{"case_id": "b", "n": 2}\n\n{"case_id": "c", "n": 4}\n')
        self.assertEqual(lr.replace_rows(self.DATA, {"b"}, [{"case_id": "b", "n": 8}, {"case_id": "b", "n": 9}], "x.jsonl"),
                         b'{"case_id": "a", "n": 1}\n{"case_id": "b", "n": 8}\n{"case_id": "b", "n": 9}\n\n'
                         b'{"case_id": "a", "n": 3}\n{"case_id": "c", "n": 4}\n')
        self.assertEqual(lr.replace_rows(self.DATA, {"c"}, [{"case_id": "c", "n": 7}], "x.jsonl"),
                         b'{"case_id": "a", "n": 1}\n{"case_id": "b", "n": 2}\n\n{"case_id": "a", "n": 3}\n'
                         b'{"case_id": "c", "n": 7}\n')

    def test_rows_for_a_new_case_go_at_the_end(self):
        self.assertEqual(lr.replace_rows(self.DATA, {"z"}, [{"case_id": "z"}], "x.jsonl"),
                         self.DATA + b'{"case_id": "z"}\n')
        self.assertEqual(lr.replace_rows(b"", {"a"}, [{"case_id": "a"}], "x.jsonl"), b'{"case_id": "a"}\n')
        self.assertEqual(lr.replace_rows(b"", {"a"}, [], "x.jsonl"), b"")

    def test_a_file_with_windows_line_endings_keeps_them(self):
        data = b'{"case_id": "a", "n": 1}\r\n{"case_id": "b", "n": 2}\r\n\r\n'
        self.assertEqual(lr.replace_rows(data, {"a"}, [{"case_id": "a", "n": 9}, {"case_id": "a", "n": 8}], "x.jsonl"),
                         b'{"case_id": "a", "n": 9}\r\n{"case_id": "a", "n": 8}\r\n{"case_id": "b", "n": 2}\r\n\r\n')

    def test_lines_that_are_not_rows_are_kept_as_they_are(self):
        data = b'[1]\n{"case_id": "a"}\n7\n'
        self.assertEqual(lr.replace_rows(data, {"a"}, [{"case_id": "a", "n": 1}], "x.jsonl"),
                         b'[1]\n{"case_id": "a", "n": 1}\n7\n')

    def test_a_damaged_file_is_not_touched(self):
        reason = self.assertStops(2, lr.replace_rows, b'{"case_id": "a"}\nnot json\n', {"a"}, [], "answers.jsonl")
        self.assertIn("answers.jsonl, line 2: not valid JSON", reason)

    def test_rows_are_read_without_the_blank_lines(self):
        path = self.root / "rows.jsonl"
        path.write_bytes(b'{"a": 1}\n\n  \n{"a": 2}\r\n')
        self.assertEqual(lr.read_rows(path), [{"a": 1}, {"a": 2}])
        self.assertEqual(lr.read_rows(self.root / "missing.jsonl"), [])

    def test_a_file_that_is_not_rows_cannot_be_read(self):
        path = self.root / "rows.jsonl"
        for data, expected in ((b'{"a": 1}\nnot json\n', "rows.jsonl, line 2: not valid JSON"),
                               (b'{"a": 1}\n{"a"', "rows.jsonl, line 2: not valid JSON"),
                               (b"[1]\n", "rows.jsonl, line 1: expected a JSON object")):
            path.write_bytes(data)
            with self.subTest(data=data):
                self.assertIn(expected, self.assertStops(2, lr.read_rows, path))

    def test_lines_are_appended_one_at_a_time(self):
        path = self.root / "journals" / "x.jsonl"
        lr.append_line(path, "one")
        lr.append_line(path, "two")
        self.assertEqual(path.read_bytes(), b"one\ntwo\n")

    def test_files_are_written_into_new_folders_too(self):
        first, second = self.root / "a.jsonl", self.root / "new" / "deeper" / "b.jsonl"
        lr.write_atomic([(first, b"A\n"), (second, b"B\n")])
        self.assertEqual((first.read_bytes(), second.read_bytes()), (b"A\n", b"B\n"))
        self.assertEqual([path.name for path in self.root.rglob("*.tmp")], [])

    def test_a_failed_write_changes_no_file_and_leaves_nothing_behind(self):
        first, second = self.root / "a.jsonl", self.root / "b.jsonl"
        first.write_bytes(b"old a\n")
        second.write_bytes(b"old b\n")
        with mock.patch("os.fsync", side_effect=[None, OSError("disk full")]), self.assertRaises(OSError):
            lr.write_atomic([(first, b"new a\n"), (second, b"new b\n")])
        self.assertEqual((first.read_bytes(), second.read_bytes()), (b"old a\n", b"old b\n"))
        self.assertEqual(sorted(path.name for path in self.root.iterdir()), ["a.jsonl", "b.jsonl"])

    def test_a_failed_swap_leaves_no_temporary_file(self):
        paths = [self.root / name for name in ("a.jsonl", "b.jsonl", "c.jsonl")]
        for path in paths:
            path.write_bytes(b"old\n")
        real, swaps = os.replace, []

        def flaky(source, target):
            swaps.append(target)
            if len(swaps) == 2:
                raise OSError("disk full")
            real(source, target)

        with mock.patch("os.replace", flaky), self.assertRaises(OSError):
            lr.write_atomic([(path, b"new\n") for path in paths])
        self.assertEqual([path.read_bytes() for path in paths], [b"new\n", b"old\n", b"old\n"])
        self.assertEqual(sorted(path.name for path in self.root.iterdir()), ["a.jsonl", "b.jsonl", "c.jsonl"])


class JournalTests(LabFiles):
    def load(self, rows=(), tail=b"", model=MODELS[DOC]):
        path = self.journal(DOC, rows, tail)
        return lr.load_journal(path, CASE_IDS[DOC], scorecards.instructions_digest(DOC), model)

    def test_whole_runs_are_kept(self):
        rows = self.saved(DOC, 5) + self.saved(DOC, 2, case=1)
        self.assertEqual(self.load(rows), (rows, True))

    def test_no_journal_means_no_saved_runs(self):
        self.assertEqual(lr.load_journal(self.files.journal(DOC), CASE_IDS[DOC], "any"), ([], True))

    def test_unusable_rows_are_dropped(self):
        good = self.saved(DOC, 1)[0]
        base = run_row(DOC, CASE_IDS[DOC][0], 2)

        def variant(**changes):
            return {**base, **changes}

        bad = {
            "another case": variant(case_id="no-such-case"), "run 0": variant(run=0), "run 6": variant(run=6),
            "run as text": variant(run="2"), "run as boolean": variant(run=True),
            "other instructions": variant(instructions_sha256="0" * 64), "other model": variant(model="gpt-other"),
            "empty text": variant(text=""), "blank text": variant(text="  "), "text as number": variant(text=5),
            "receipts as text": variant(receipts="x"), "negative tokens": variant(input_tokens=-1),
            "fractional tokens": variant(output_tokens=1.5), "cached more than input": variant(cached_tokens=101),
            "no cached count": variant(cached_tokens=None), "negative seconds": variant(seconds=-1),
            "seconds as boolean": variant(seconds=True), "bad date": variant(recorded_on="soon"),
            "date as number": variant(recorded_on=20261002), "extra key": variant(extra=1),
            "missing key": {name: value for name, value in base.items() if name != "text"},
        }
        for label, row in bad.items():
            with self.subTest(label):
                self.assertEqual(self.load([good, row]), ([good], False))
        self.assertEqual(self.load([good, good]), ([good], False))

    def test_any_model_is_accepted_when_none_is_asked_for(self):
        other = run_row(DOC, CASE_IDS[DOC][0], 2, model="gpt-other")
        self.assertEqual(self.load([other], model=None), ([other], True))
        self.assertEqual(self.load([other]), ([], False))

    def test_a_line_cut_short_by_a_crash_is_ignored(self):
        rows = self.saved(DOC, 2)
        self.assertEqual(self.load(rows, tail=b'{"case_id": "document-an'), (rows, False))

    def test_blank_and_non_object_lines_are_dropped(self):
        first, second = (lr.dump(row).encode("utf-8") for row in self.saved(DOC, 2))
        path = self.files.journal(DOC)
        path.parent.mkdir(parents=True)
        path.write_bytes(first + b"\n\n[1]\n7\nnull\n" + second + b"\n")
        loaded, clean = lr.load_journal(path, CASE_IDS[DOC], scorecards.instructions_digest(DOC), MODELS[DOC])
        self.assertEqual((len(loaded), clean), (2, False))

    def test_damage_anywhere_else_stops_the_run(self):
        first, second = (lr.dump(row).encode("utf-8") for row in self.saved(DOC, 2))
        path = self.files.journal(DOC)
        path.parent.mkdir(parents=True)
        for label, data in (("middle", first + b"\nnot json\n" + second + b"\n"),
                            ("last complete line", first + b"\nnot json\n")):
            path.write_bytes(data)
            with self.subTest(label):
                reason = self.assertStops(2, lr.load_journal, path, CASE_IDS[DOC], scorecards.instructions_digest(DOC))
                self.assertIn("line 2 is damaged", reason)
                self.assertIn("Delete the file", reason)

    def test_resume_cleans_up_a_journal_that_held_anything_unusable(self):
        rows = self.saved(DOC, 2)
        stale = run_row(DOC, CASE_IDS[DOC][0], 2, instructions_sha256="0" * 64)
        path = self.journal(DOC, [rows[0], stale, rows[1]], tail=b'{"case_id": "doc')
        done = lr.resume(self.files, self.item(DOC))
        self.assertEqual(done, {(CASE_IDS[DOC][0], 1): rows[0], (CASE_IDS[DOC][0], 2): rows[1]})
        self.assertEqual(path.read_bytes(), b"".join(lr.dump(row).encode("utf-8") + b"\n" for row in rows))

    def test_resume_leaves_a_clean_journal_alone(self):
        self.journal(DOC, self.saved(DOC, 2))
        with mock.patch.object(lr, "write_atomic") as writer:
            done = lr.resume(self.files, self.item(DOC))
        writer.assert_not_called()
        self.assertEqual(len(done), 2)


class StatusTests(LabFiles):
    def status(self, *argv, **kwargs):
        with no_network():
            return self.run_main("status", *argv, **kwargs)

    def test_agents_whose_answers_match_are_current(self):
        result = self.status()
        self.assertEqual((result.code, result.err, result.opened), (0, "", []))
        self.assertRegex(result.out, r"(?m)^Agent +State +Recorded +Model$")
        self.assertRegex(result.out, r"(?m)^document-analyst +current +2026-09-01 +gpt-5\.4$")
        self.assertRegex(result.out, r"(?m)^workflow-coordinator +current +2026-09-01 +gpt-4\.1$")
        self.assertIn("All 2 agents' recorded answers match their instructions.", result.out)

    def test_changed_instructions_make_an_agent_stale(self):
        with edited(DOC):
            result = self.status()
        self.assertEqual((result.code, result.err), (1, ""))
        self.assertRegex(result.out, r"(?m)^document-analyst +stale +2026-09-01 +gpt-5\.4$")
        self.assertRegex(result.out, r"(?m)^workflow-coordinator +current ")
        self.assertIn("    12 of 12 recorded rows came from other instructions", result.out)
        self.assertIn("1 of 2 agents need their test answers recorded again.", result.out)
        self.assertIn("To see the plan (nothing is sent): python evaluations/library_runs.py record "
                      "--templates document-analyst\n", result.out)
        self.assertIn("Add --yes to record them. That calls Foundry and costs money.", result.out)

    def test_missing_or_doubled_rows_make_an_agent_incomplete(self):
        answers, metrics, repeats = recorded_rows(DOC)
        sample = CASE_IDS[DOC][0]
        needs = "; it needs 1, 1 and 2 to 5"
        dated = copy.deepcopy(answers)
        dated[0]["recorded_on"] = "soon"
        mixed = copy.deepcopy(repeats)
        mixed[0]["model"] = "gpt-4.1"
        for label, rows, reason in (
                ("no answer row", (answers[1:], metrics, repeats),
                 f"{sample}: 0 answer rows, 1 metrics rows, repeat runs 2, 3, 4, 5{needs}"),
                ("no metrics row", (answers, metrics[1:], repeats),
                 f"{sample}: 1 answer rows, 0 metrics rows, repeat runs 2, 3, 4, 5{needs}"),
                ("a repeat is missing", (answers, metrics, repeats[:3] + repeats[4:]),
                 f"{sample}: 1 answer rows, 1 metrics rows, repeat runs 2, 3, 4{needs}"),
                ("a repeat is doubled", (answers, metrics, repeats + repeats[:1]),
                 f"{sample}: 1 answer rows, 1 metrics rows, repeat runs 2, 2, 3, 4, 5{needs}"),
                ("an answer is doubled", (answers + answers[:1], metrics, repeats),
                 f"{sample}: 2 answer rows, 1 metrics rows, repeat runs 2, 3, 4, 5{needs}"),
                ("a bad date", (dated, metrics, repeats), "1 rows have no valid recorded_on date"),
                ("two models", (answers, metrics, mixed), "more than one model was used: gpt-4.1, gpt-5.4")):
            with self.subTest(label):
                self.write_evidence(replace={DOC: rows})
                result = self.status()
                self.assertEqual(result.code, 1)
                self.assertRegex(result.out, r"(?m)^document-analyst +incomplete ")
                self.assertIn(reason, result.out)

    def test_two_models_show_as_mixed(self):
        answers, metrics, repeats = recorded_rows(DOC)
        repeats[0]["model"] = "gpt-4.1"
        self.write_evidence(replace={DOC: (answers, metrics, repeats)})
        self.assertRegex(self.status().out, r"(?m)^document-analyst +incomplete +2026-09-01 +mixed$")

    def test_an_agent_with_no_rows_is_missing(self):
        self.write_evidence(replace={DOC: ([], [], [])})
        result = self.status()
        self.assertEqual(result.code, 1)
        self.assertRegex(result.out, r"(?m)^document-analyst +missing +- +-$")
        self.assertIn("no answers are recorded for this agent", result.out)

    def test_only_the_first_three_reasons_are_listed(self):
        answers, metrics, repeats = recorded_rows(DOC)
        metrics[0]["recorded_on"] = "soon"
        self.write_evidence(replace={DOC: (answers[1:], metrics, repeats[:7])})
        with edited(DOC):
            result = self.status()
        self.assertIn("10 of 10 recorded rows came from other instructions", result.out)
        self.assertIn("document-analyst-sample: 0 answer rows", result.out)
        self.assertIn("document-analyst-missing-version: 1 answer rows, 1 metrics rows, repeat runs 2, 3, 4;", result.out)
        self.assertIn("and 1 more", result.out)
        self.assertNotIn("no valid recorded_on date", result.out)

    def test_agents_can_be_picked_by_name(self):
        result = self.status("--templates", FLOW)
        self.assertEqual(result.code, 0)
        self.assertNotIn(DOC, result.out)
        self.assertIn("All 1 agents' recorded answers match their instructions.", result.out)
        result = self.status("--templates", "nope")
        self.assertEqual(result.code, 2)
        self.assertIn("Stopped: No test cases for: nope", result.err)

    def test_it_mentions_an_interrupted_recording(self):
        with edited(DOC):
            self.journal(DOC, self.saved(DOC, 3))
            result = self.status()
        self.assertIn("interrupted recording: 3 of 10 runs saved; `record` picks up from there", result.out)

    def test_it_mentions_a_damaged_saved_runs_file(self):
        with edited(DOC):
            path = self.journal(DOC, self.saved(DOC, 1), tail=b"junk\n")
            result = self.status()
        self.assertIn("its saved-runs file is damaged; delete", result.out)
        self.assertIn(path.name, result.out)

    def test_an_evidence_file_that_is_not_rows_stops_it(self):
        self.files.answers.write_bytes(b"not json\n")
        result = self.status()
        self.assertEqual((result.code, result.out), (2, ""))
        self.assertIn("Stopped: answers.jsonl, line 1: not valid JSON", result.err)


def as_input(prompt):
    """What the Lab's preview sends for a prompt."""
    return [{"role": "user", "content": prompt}] if isinstance(prompt, str) else [dict(item) for item in prompt]


class PlanTests(LabFiles):
    def plan(self, *argv, templates=(DOC,), **kwargs):
        with no_network():
            return self.run_main("record", "--templates", *templates, *argv, environ=kwargs.pop("environ", {}), **kwargs)

    def test_the_plan_is_printed_and_nothing_is_sent(self):
        before = self.snapshot()
        result = self.plan()
        self.assertEqual((result.code, result.err, result.opened, result.foundry.calls), (2, "", [], []))
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.files.journals.exists())
        self.assertEqual(re.sub(r"\$\d+\.\d\d", "$X", result.out), "\n".join([
            "Plan to record test answers again (nothing has been sent):",
            "",
            "document-analyst (reasoning)",
            "  2 cases x 5 runs = 10 runs on gpt-5.4 (model from its last recording)",
            "  recorded now: current",
            "  its answers already match its instructions; recording again only refreshes them",
            "  its last recording used 1,500 tokens, about $X; at 10,000 tokens a minute that takes at least 1 min",
            "",
            "Pacing, for each model deployment:",
            "  gpt-5.4: up to 10,000 tokens and 10 requests a minute",
            "",
            "Nothing was sent. Recording calls Foundry and costs money; add --yes to go ahead.",
            ""]))

    def test_a_model_from_the_command_line_has_no_estimate(self):
        result = self.plan("--model", "gpt-other")
        self.assertIn("10 runs on gpt-other (model from --model)", result.out)
        self.assertIn("  no earlier recording on this model, so no cost or time estimate", result.out)
        self.assertIn("  gpt-other: up to 10,000 tokens and 10 requests a minute", result.out)

    def test_limits_change_the_pacing_and_the_time_estimate(self):
        result = self.plan("--limits", '{"gpt-5.4": {"tokens": 30000, "requests": 30}}')
        self.assertIn("at 30,000 tokens a minute", result.out)
        self.assertIn("  gpt-5.4: up to 30,000 tokens and 30 requests a minute", result.out)

    def test_a_limit_that_names_one_value_keeps_the_default_for_the_other(self):
        result = self.plan("--limits", '{"gpt-5.4": {"tokens": 30000}}')
        self.assertIn("  gpt-5.4: up to 30,000 tokens and 10 requests a minute", result.out)

    def test_runs_saved_by_an_interrupted_recording_are_counted(self):
        with edited(DOC):
            self.journal(DOC, self.saved(DOC, 3))
            result = self.plan()
        self.assertIn("  3 of 10 runs are already saved by an interrupted recording and won't be sent again", result.out)
        self.assertIn("recorded now: stale", result.out)
        self.assertNotIn("recording again only refreshes them", result.out)

    def test_a_signed_off_agent_is_warned_about(self):
        warning = "its sign-off or Reviewed label will no longer match the new answers; a person must read them and sign off again"
        self.assertNotIn(warning, self.plan(templates=(DOC, FLOW)).out)
        self.sign_off(DOC)
        out = self.plan(templates=(DOC, FLOW)).out
        self.assertEqual(out.count(warning), 1)
        self.assertLess(out.index(warning), out.index(f"{FLOW} ("))

    def test_a_reviewed_label_is_warned_about_without_a_sign_off_file(self):
        with mock.patch.dict(TEMPLATE_METADATA[FLOW], {"readiness": "reviewed"}):
            out = self.plan(templates=(DOC, FLOW)).out
        self.assertEqual(out.count("its sign-off or Reviewed label"), 1)
        self.assertGreater(out.index("its sign-off or Reviewed label"), out.index(f"{FLOW} ("))

    def test_an_unreadable_sign_off_file_is_mentioned_and_does_not_stop_the_plan(self):
        self.files.signoffs.write_text("not json", encoding="utf-8")
        result = self.plan()
        self.assertEqual(result.code, 2)
        self.assertRegex(result.out, r"(?m)^Note: .*signoffs\.json can't be read\. "
                                     r"Fix or remove it before rebuilding the scorecards\.$")

    def test_each_model_deployment_is_listed_once(self):
        out = self.plan(templates=(DOC, FLOW)).out
        self.assertIn("  gpt-4.1: up to 10,000 tokens and 10 requests a minute", out)
        self.assertIn("  gpt-5.4: up to 10,000 tokens and 10 requests a minute", out)
        self.assertLess(out.index("gpt-4.1: up to"), out.index("gpt-5.4: up to"))
        out = self.plan("--model", "gpt-x", templates=(DOC, FLOW)).out
        self.assertEqual(out.count("up to 10,000 tokens and 10 requests a minute"), 1)

    def test_an_agent_with_no_recording_needs_a_model_named(self):
        self.write_evidence(replace={DOC: ([], [], [])})
        result = self.plan()
        self.assertEqual((result.code, result.out), (2, ""))
        self.assertIn("Stopped: No model deployment for document-analyst (reasoning)", result.err)
        result = self.plan("--model", "gpt-5.4")
        self.assertIn("recorded now: missing", result.out)
        self.assertIn("no earlier recording on this model", result.out)

    def test_an_unknown_agent_is_refused(self):
        result = self.plan(templates=("nope",))
        self.assertEqual((result.code, result.out), (2, ""))
        self.assertIn("Stopped: No test cases for: nope", result.err)


class Recording(LabFiles):
    def record(self, *argv, templates=(DOC,), **kwargs):
        return self.run_main("record", "--templates", *templates, "--yes", *argv, **kwargs)

    def rows(self, path, template_id):
        return [row for row in lr.read_rows(path) if row["case_id"] in CASE_IDS[template_id]]


class RecordTests(Recording):
    def test_recording_sends_every_run_and_replaces_that_agents_rows_only(self):
        before = self.snapshot()
        tails = {path.name: b"".join(line for line in before[path.name].splitlines(keepends=True) if FLOW.encode() in line)
                 for path in self.evidence_paths}
        with edited(DOC):
            result = self.record()
            digest = scorecards.instructions_digest(DOC)
            instructions = DEMO_POLICY + TEMPLATES[DOC]["instructions"]
            dates = self.dates()
        self.assertEqual((result.code, result.err, result.opened), (0, "", [ENDPOINT]))
        self.assertIn("Recording 10 runs.", result.out)
        calls = result.foundry.calls
        self.assertEqual(len(calls), 10)
        for call in calls:
            self.assertEqual((call["model"], call["instructions"], call["store"], call["stream"]),
                             ("gpt-5.4", instructions, False, False))
            self.assertNotIn("tools", call)
            self.assertNotIn("include", call)
        self.assertEqual(calls[0]["input"], as_input(self.prompt(CASE_IDS[DOC][0])))
        self.assertEqual(calls[5]["input"], as_input(self.prompt(CASE_IDS[DOC][1])))
        answers, metrics, repeats = (self.rows(path, DOC) for path in self.evidence_paths)
        self.assertEqual([row["text"] for row in answers], ["Answer 1", "Answer 6"])
        self.assertEqual([(row["case_id"], row["run"], row["text"]) for row in repeats],
                         [(CASE_IDS[DOC][0], run, f"Answer {run}") for run in range(2, 6)]
                         + [(CASE_IDS[DOC][1], run, f"Answer {run + 5}") for run in range(2, 6)])
        for rows, keys in ((answers, lr.ANSWER_ROW), (metrics, lr.METRICS_ROW), (repeats, lr.RUN_ROW)):
            for row in rows:
                self.assertEqual(tuple(row), keys)
                self.assertEqual((row["instructions_sha256"], row["recorded_on"]), (digest, TODAY))
        for row in metrics + repeats:
            self.assertEqual((row["model"], row["seconds"], row["input_tokens"], row["cached_tokens"], row["output_tokens"]),
                             ("gpt-5.4", 1.5, 100, 20, 50))
        for path in self.evidence_paths:
            self.assertTrue(path.read_bytes().endswith(tails[path.name]), path.name)
        self.assertFalse(self.files.journal(DOC).exists())
        self.assertFalse(self.files.signoffs.exists())
        self.assertEqual(dates, {DOC: TODAY, FLOW: RECORDED})
        self.assertIn("document-analyst: recording 10 runs on gpt-5.4", result.out)
        self.assertIn("  document-analyst: 10 of 10 runs saved (document-analyst-missing-version run 5, 1.5 s, 150 tokens)",
                      result.out)
        self.assertIn("document-analyst: done. Its rows in the three evidence files were replaced. "
                      "Used 1,500 tokens, about $0.01.", result.out)
        self.assertIn("Next steps:", result.out)
        self.assertIn('python evaluations/scorecards.py signoff --reviewer "Name" document-analyst', result.out)

    def test_a_tool_agent_is_recorded_with_its_simulated_lookups(self):
        result = self.record(templates=(FLOW,))
        self.assertEqual((result.code, result.err), (0, ""))
        calls = result.foundry.calls
        self.assertEqual(len(calls), 20)
        self.assertEqual({call["model"] for call in calls}, {"gpt-4.1"})
        self.assertIn("lookup_demo_request", [tool["name"] for tool in calls[0]["tools"]])
        self.assertNotIn("include", calls[0])
        self.assertEqual(calls[1]["input"][-1]["type"], "function_call_output")
        answers = self.rows(self.files.answers, FLOW)
        self.assertEqual((answers[0]["text"], answers[0]["receipts"]), ("Answer 2", [{"tool": "lookup_demo_request"}]))
        metrics = self.rows(self.files.metrics, FLOW)[0]
        self.assertEqual((metrics["seconds"], metrics["input_tokens"], metrics["cached_tokens"], metrics["output_tokens"]),
                         (3.0, 200, 40, 100))

    def busiest_minute(self, times):
        return max(sum(1 for other in times if moment - 60 < other <= moment) for moment in times)

    def test_requests_are_paced_within_the_default_limits(self):
        result = self.record(templates=(FLOW,))
        self.assertLessEqual(self.busiest_minute(result.foundry.times), 10)
        self.assertTrue(self.clock.slept)

    def test_limits_from_the_command_line_are_kept_to(self):
        result = self.record("--limits", '{"gpt-4.1": {"tokens": 450, "requests": 100}}', templates=(FLOW,))
        self.assertEqual(result.code, 0)
        self.assertLessEqual(self.busiest_minute(result.foundry.times), 3)
        self.assertTrue(self.clock.slept)

    def test_a_model_can_be_chosen_on_the_command_line(self):
        result = self.record("--model", "gpt-x")
        self.assertEqual({call["model"] for call in result.foundry.calls}, {"gpt-x"})
        self.assertEqual({row["model"] for row in self.rows(self.files.metrics, DOC)}, {"gpt-x"})
        self.assertIn("no price for its model, so no cost", result.out)

    def test_a_models_map_chooses_by_profile(self):
        result = self.record("--models", '{"reasoning": "gpt-y"}', templates=(DOC, FLOW))
        self.assertEqual(result.code, 0)
        self.assertEqual({call["model"] for call in result.foundry.calls[:10]}, {"gpt-y"})
        self.assertEqual({call["model"] for call in result.foundry.calls[10:]}, {"gpt-4.1"})

    def test_the_endpoint_option_beats_the_environment(self):
        other = "https://other.services.ai.azure.com/api/projects/other"
        result = self.record("--endpoint", other)
        self.assertEqual((result.code, result.opened), (0, [other]))

    def test_an_agent_with_no_rows_yet_gets_them_after_the_others(self):
        self.write_evidence(replace={DOC: ([], [], [])})
        before = self.snapshot()
        result = self.record("--model", "gpt-5.4")
        self.assertEqual((result.code, result.err), (0, ""))
        for path in self.evidence_paths:
            self.assertTrue(path.read_bytes().startswith(before[path.name]), path.name)
        self.assertEqual([row["case_id"] for row in lr.read_rows(self.files.answers)],
                         CASE_IDS[FLOW] + CASE_IDS[DOC])

    def test_evidence_files_that_do_not_exist_yet_are_created(self):
        for path in self.evidence_paths:
            path.unlink()
        result = self.record("--model", "gpt-5.4")
        self.assertEqual((result.code, result.err), (0, ""))
        self.assertEqual([len(lr.read_rows(path)) for path in self.evidence_paths], [2, 2, 8])

    def test_recording_an_agent_that_is_already_current_refreshes_its_rows(self):
        result = self.record()
        self.assertEqual(result.code, 0)
        self.assertEqual(self.dates(), {DOC: TODAY, FLOW: RECORDED})

    def test_the_date_comes_from_the_clock_when_none_is_given(self):
        earliest = datetime.datetime.now(datetime.timezone.utc).date()
        result = self.record(today=None)
        latest = datetime.datetime.now(datetime.timezone.utc).date()
        stamped = {row["recorded_on"] for row in self.rows(self.files.answers, DOC)}
        self.assertEqual((result.code, len(stamped)), (0, 1))
        self.assertIn(datetime.date.fromisoformat(stamped.pop()), {earliest, latest})


class ResumeTests(Recording):
    def test_an_interrupted_recording_is_picked_up_where_it_stopped(self):
        before = self.snapshot()
        with edited(DOC):
            first = self.record(foundry=self.foundry([None, None, None, ValueError("boom")]))
            self.assertEqual(first.code, 1)
            self.assertIn("Stopped: Foundry request failed after 1 try: ValueError: boom", first.err)
            self.assertEqual(len(lr.read_rows(self.files.journal(DOC))), 3)
            self.assertEqual(self.snapshot(), before)
            self.assertNotIn("Next steps", first.out)
            second = self.record(foundry=self.foundry(start=3))
        self.assertEqual((second.code, second.err), (0, ""))
        self.assertEqual(len(second.foundry.calls), 7)
        self.assertIn("Recording 7 runs.", second.out)
        self.assertEqual(second.foundry.calls[2]["input"], as_input(self.prompt(CASE_IDS[DOC][1])))
        self.assertEqual([row["text"] for row in self.rows(self.files.answers, DOC)], ["Answer 1", "Answer 6"])
        self.assertEqual([row["text"] for row in self.rows(self.files.repeats, DOC)],
                         [f"Answer {number}" for number in (2, 3, 4, 5, 7, 8, 9, 10)])
        self.assertFalse(self.files.journal(DOC).exists())

    def test_a_line_cut_short_by_a_crash_is_not_counted(self):
        with edited(DOC):
            self.journal(DOC, self.saved(DOC, 2), tail=b'{"case_id": "document-an')
            result = self.record()
        self.assertEqual((result.code, result.err, len(result.foundry.calls)), (0, "", 8))

    def test_saved_runs_from_older_instructions_are_not_reused(self):
        self.journal(DOC, self.saved(DOC, 3))
        with edited(DOC):
            result = self.record()
        self.assertEqual((result.code, len(result.foundry.calls)), (0, 10))

    def test_saved_runs_from_another_model_are_not_reused(self):
        with edited(DOC):
            self.journal(DOC, [run_row(DOC, CASE_IDS[DOC][0], run, model="gpt-other") for run in range(1, 4)])
            result = self.record()
        self.assertEqual((result.code, len(result.foundry.calls)), (0, 10))

    def test_a_complete_journal_is_committed_without_calling_foundry(self):
        with edited(DOC):
            self.journal(DOC, [run_row(DOC, case_id, run, recorded_on="2026-10-01")
                               for case_id in CASE_IDS[DOC] for run in range(1, 6)])
            result = self.record(environ={})
            dates = self.dates()
        self.assertEqual((result.code, result.err, result.opened, result.foundry.calls), (0, "", [], []))
        self.assertIn("Recording 0 runs.", result.out)
        self.assertEqual(dates[DOC], "2026-10-01")
        self.assertFalse(self.files.journal(DOC).exists())

    def test_a_reply_that_did_not_finish_is_not_saved(self):
        before = self.snapshot()
        with edited(DOC):
            result = self.record(foundry=self.foundry([None, message("Half an answ", status="incomplete")]))
        self.assertEqual(result.code, 1)
        self.assertIn("document-analyst-sample run 2: the model's reply was 'incomplete', so it wasn't saved. "
                      "Run the same command again to retry.", result.err)
        self.assertEqual(len(lr.read_rows(self.files.journal(DOC))), 1)
        self.assertEqual(self.snapshot(), before)

    def test_a_reply_without_usable_token_counts_is_not_saved(self):
        too_much_cached = {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15,
                           "input_tokens_details": {"cached_tokens": 50}}
        for usage, reason in ((None, "Foundry didn't report token counts, so its cost can't be recorded."),
                              (too_much_cached, "Foundry reported more cached tokens than input tokens.")):
            with self.subTest(reason=reason):
                result = self.record(foundry=self.foundry([message("Answer", usage=usage)]))
                self.assertEqual(result.code, 1)
                self.assertIn(reason, result.err)
                self.assertFalse(self.files.journal(DOC).exists())

    def test_a_missing_cached_count_is_recorded_as_zero(self):
        usage = {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150}
        result = self.record(foundry=self.foundry([message(f"Answer {number}", usage=usage) for number in range(1, 11)]))
        self.assertEqual((result.code, result.err), (0, ""))
        rows = self.rows(self.files.metrics, DOC) + self.rows(self.files.repeats, DOC)
        self.assertEqual({row["cached_tokens"] for row in rows}, {0})


class SafetyTests(Recording):
    def test_a_write_failure_keeps_the_finished_runs_for_the_next_try(self):
        before = self.snapshot()
        with edited(DOC):
            with mock.patch.object(lr, "write_atomic", side_effect=OSError("disk full")):
                first = self.record()
            self.assertEqual(first.code, 1)
            self.assertIn("Stopped: Couldn't write the evidence files (OSError: disk full).", first.err)
            self.assertTrue(self.files.journal(DOC).exists())
            self.assertEqual(self.snapshot(), before)
            second = self.record()
            dates = self.dates()
        self.assertEqual((second.code, second.opened, second.foundry.calls), (0, [], []))
        self.assertEqual(dates[DOC], TODAY)

    def test_a_swap_that_fails_midway_is_repaired_by_running_again(self):
        real, swaps = os.replace, []

        def flaky(source, target):
            swaps.append(target)
            if len(swaps) == 2:
                raise OSError("disk full")
            real(source, target)

        with edited(DOC):
            with mock.patch("os.replace", flaky):
                first = self.record()
            self.assertEqual(first.code, 1)
            self.assertIn("Couldn't write the evidence files", first.err)
            self.assertEqual(list(self.root.rglob("*.tmp")), [])
            self.assertTrue(self.files.journal(DOC).exists())
            second = self.record()
            dates = self.dates()
        self.assertEqual((second.code, second.foundry.calls), (0, []))
        self.assertEqual(dates[DOC], TODAY)

    def test_a_replacement_that_does_not_check_out_is_reported(self):
        with edited(DOC), mock.patch.object(lr, "commit", side_effect=lambda files, item, done: list(done.values())):
            result = self.record()
        self.assertEqual(result.code, 1)
        self.assertIn("document-analyst: the evidence files don't look right after the replacement", result.err)

    def test_a_sign_off_is_left_alone_and_the_next_scorecard_build_says_so(self):
        self.sign_off(DOC)
        signed = self.files.signoffs.read_bytes()
        with edited(DOC), mock.patch.object(scorecards, "record_signoff", side_effect=AssertionError("never signs off")):
            result = self.record()
            self.assertEqual((result.code, result.err), (0, ""))
            self.assertEqual(self.files.signoffs.read_bytes(), signed)
            with self.assertRaisesRegex(ValueError, "the answers changed after the sign-off"):
                self.build()

    def test_agents_are_committed_one_by_one(self):
        result = self.record(templates=(DOC, FLOW), foundry=self.foundry([None] * 10 + [ValueError("boom")]))
        self.assertEqual(result.code, 1)
        self.assertIn("Stopped: Foundry request failed after 1 try: ValueError: boom", result.err)
        self.assertEqual(self.dates(), {DOC: TODAY, FLOW: RECORDED})
        after = result.out.split("Next steps:")[1]
        self.assertIn(DOC, after)
        self.assertNotIn(FLOW, after)

    def test_recording_never_runs_in_ci(self):
        for variable in ({"CI": "true"}, {"GITHUB_ACTIONS": "true"}):
            with self.subTest(variable=variable):
                result = self.record(environ={**ENV, **variable})
                self.assertEqual((result.code, result.opened, result.foundry.calls), (2, [], []))
                self.assertIn("never runs in CI", result.err)
                self.assertFalse(self.files.journals.exists())
        self.assertEqual(self.run_main("status", environ={**ENV, "CI": "true"}).code, 0)

    def test_it_will_not_guess_which_project_to_use(self):
        result = self.record(environ={})
        self.assertEqual((result.code, result.opened, result.foundry.calls), (2, [], []))
        self.assertIn("Say which Foundry project to use", result.err)
        self.assertFalse(self.files.journals.exists())

    def test_a_bad_endpoint_is_refused_without_repeating_it(self):
        for argv, environ in ((("--endpoint", "https://user:secret@lab.services.ai.azure.com/api/projects/lab"), ENV),
                              ((), {lr.ENV_ENDPOINT: "http://secret.example.com/api/projects/lab"})):
            with self.subTest(argv=argv):
                result = self.record(*argv, environ=environ)
                self.assertEqual((result.code, result.opened, result.foundry.calls), (2, [], []))
                self.assertIn("HTTPS Foundry project URL", result.err)
                self.assertNotIn("secret", result.out + result.err)

    def test_an_unknown_agent_is_refused_even_with_yes(self):
        result = self.record(templates=("nope",))
        self.assertEqual((result.code, result.opened, result.foundry.calls), (2, [], []))
        self.assertIn("No test cases for: nope", result.err)


class CommandLineTests(LabFiles):
    def test_bad_command_lines_are_refused(self):
        for argv in ([], ["record"], ["record", "--templates", DOC, "--model", "m", "--models", "{}"],
                     ["record", "--templates", DOC, "--ye"], ["status", "--yes"]):
            with self.subTest(argv=argv), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as caught:
                    lr.main(argv, files=self.files, environ={})
                self.assertEqual(caught.exception.code, 2)

    def test_ctrl_c_ends_the_run_politely(self):
        with mock.patch.object(lr, "command_status", side_effect=KeyboardInterrupt):
            result = self.run_main("status")
        self.assertEqual(result.code, 130)
        self.assertIn("Interrupted. Finished runs are saved; run the same command again to continue.", result.err)

    def test_text_a_console_cannot_show_is_replaced(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            lr.say("caf\u00e9 \u2713")
        self.assertEqual(out.getvalue(), "caf? ?\n")

    def test_tests_and_scripts_get_the_real_client_unless_they_pass_another(self):
        self.assertIs(inspect.signature(lr.main).parameters["open_client"].default, lr.open_live_client)

    def test_ci_is_recognised_from_the_usual_variables(self):
        for environ, expected in (({}, False), ({"CI": "true"}, True), ({"CI": "1"}, True), ({"CI": "True"}, True),
                                  ({"CI": " TRUE "}, True), ({"CI": "false"}, False), ({"CI": "0"}, False),
                                  ({"CI": "no"}, False), ({"CI": ""}, False), ({"GITHUB_ACTIONS": "true"}, True),
                                  ({"CI": "false", "GITHUB_ACTIONS": "true"}, True)):
            with self.subTest(environ=environ):
                self.assertIs(lr.in_ci(environ), expected)


class FakeSdk:
    """Stands in for the Azure SDK and notes how it was used."""

    def __init__(self):
        self.closed, self.project_kwargs, self.openai_kwargs, self.requests = [], None, None, []

    def modules(self):
        sdk = self

        class Scope:
            def __init__(self, name):
                self.name = name

            def __enter__(self):
                return self

            def __exit__(self, *details):
                sdk.closed.append(self.name)

        class OpenAI(Scope):
            def __init__(self):
                super().__init__("openai")
                self.responses = SimpleNamespace(create=self.create)

            def create(self, **options):
                sdk.requests.append(options)
                return "reply"

        class Credential(Scope):
            def __init__(self):
                super().__init__("credential")

        class Project(Scope):
            def __init__(self, **kwargs):
                super().__init__("project")
                sdk.project_kwargs = kwargs

            def get_openai_client(self, **kwargs):
                sdk.openai_kwargs = kwargs
                return OpenAI()

        projects, identity = ModuleType("azure.ai.projects"), ModuleType("azure.identity")
        projects.AIProjectClient, identity.DefaultAzureCredential = Project, Credential
        return {"azure": ModuleType("azure"), "azure.ai": ModuleType("azure.ai"),
                "azure.ai.projects": projects, "azure.identity": identity}


class LiveClientTests(Scratch):
    def test_the_project_is_opened_without_hidden_retries_and_closed_in_order(self):
        sdk = FakeSdk()

        async def send_one():
            with lr.open_live_client(ENDPOINT) as send:
                return await send({"model": "m", "input": []})

        with mock.patch.dict(sys.modules, sdk.modules()):
            reply = asyncio.run(send_one())
        self.assertEqual(reply, "reply")
        kwargs = dict(sdk.project_kwargs)
        self.assertIsNotNone(kwargs.pop("credential"))
        self.assertEqual(kwargs, {"endpoint": ENDPOINT, "allow_preview": True, "retry_total": 0,
                                  "connection_timeout": 30, "read_timeout": 60})
        self.assertEqual(sdk.openai_kwargs, {"timeout": 240, "max_retries": 0})
        self.assertEqual(sdk.requests, [{"model": "m", "input": []}])
        self.assertEqual(sdk.closed, ["openai", "project", "credential"])

    def test_a_missing_azure_sdk_is_explained(self):
        with mock.patch.dict(sys.modules, {"azure.ai.projects": None, "azure.identity": None}):
            reason = self.assertStops(2, lr.open_live_client(ENDPOINT).__enter__)
        self.assertIn("pip install -r evaluations/requirements.txt", reason)


class RepositoryTests(unittest.TestCase):
    def test_every_agent_with_test_cases_has_answers_that_match_its_instructions(self):
        out, err = io.StringIO(), io.StringIO()
        with no_network(), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = lr.main(["status"], environ={})
        agents = len({case["template_id"] for case in lr.load_cases(lr.CASES_PATH)["cases"]})
        self.assertEqual(code, 0, out.getvalue() + err.getvalue())
        self.assertIn(f"All {agents} agents' recorded answers match their instructions.", out.getvalue())

    def test_the_evidence_rows_have_the_shape_the_runner_writes(self):
        files = lr.Files()
        for path, keys in ((files.answers, lr.ANSWER_ROW), (files.metrics, lr.METRICS_ROW), (files.repeats, lr.RUN_ROW)):
            rows = lr.read_rows(path)
            self.assertTrue(rows, path.name)
            for row in rows:
                self.assertEqual(tuple(row), keys, path.name)

    def test_a_plan_for_real_agents_changes_nothing_and_calls_nobody(self):
        files = lr.Files()
        paths = (files.answers, files.metrics, files.repeats)
        before, had_journals = [path.read_bytes() for path in paths], files.journals.exists()

        def refuse(endpoint):
            raise AssertionError("a plan must not open Foundry")

        with no_network(), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            code = lr.main(["record", "--templates", DOC, FLOW], open_client=refuse, environ={})
        self.assertEqual(code, 2)
        self.assertEqual([path.read_bytes() for path in paths], before)
        self.assertEqual(files.journals.exists(), had_journals)

    def test_no_workflow_runs_the_recorder(self):
        workflows = sorted((Path(__file__).resolve().parent.parent / ".github" / "workflows").glob("*.y*ml"))
        self.assertTrue(workflows)
        for path in workflows:
            self.assertNotRegex(path.read_text(encoding="utf-8"), r"library_runs\S*\s+record", path.name)


if __name__ == "__main__":
    unittest.main()

"""Re-record an agent's test answers after its instructions change.

Every recorded answer carries a fingerprint of the instructions its agent had when it ran, and
scorecards.py refuses to build when the Lab's instructions no longer match. This finds the agents
that need new answers and records them again:

    python library_runs.py status                      # offline: which agents need new answers
    python library_runs.py record --templates ID       # offline: show the plan for those agents
    python library_runs.py record --templates ID --yes # BILLABLE: record them, five runs per case

`status` and `record` without --yes never call the network. `record --yes` sends each of an agent's
cases to the Lab's Foundry project five times, on the same code the Lab's Chat preview uses, so
the answers are the ones the Lab would give. It never creates an agent and stores nothing in
Foundry. It refuses to run in CI.

Each finished run is saved at once under results/library-runs/, so an interrupted recording
resumes where it stopped. Only when all of an agent's runs are saved does it replace that agent's
rows, and no one else's, in the three evidence files, stamping every row with the instructions
fingerprint and the date it was recorded. Rows from two versions of an agent's instructions never
mix. Record one agent at a time per project, and one recording at a time.

Recording changes the answers, so an agent's sign-off stops matching. A person must read the new
answers and sign off again; this never records a sign-off.
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import datetime
import json
import math
import os
import re
import sys
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import scorecards
from library_checks import CASES_PATH, case_input, load_cases
# library_checks puts workbench/ on sys.path, which these two imports need.
from agent_templates import MODEL_PROFILES, TEMPLATE_METADATA, TEMPLATES
from library_preview import run_preview, summarize_usage, usage_record

HERE = Path(__file__).resolve().parent
JOURNALS = HERE / "results" / "library-runs"
RUNS_PER_CASE = 5
ENV_ENDPOINT = "FOUNDRY_PROJECT_ENDPOINT"
ENV_MODEL = "WORKBENCH_AGENT_CREATION_MODEL"
ENV_MODELS = "WORKBENCH_AGENT_CREATION_MODELS"
DEPLOYMENT_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")

# A capacity-10 deployment allows 10,000 tokens and 10 requests a minute (see README.md). Pass
# --limits for a deployment with more.
DEFAULT_LIMITS = {"tokens": 10_000, "requests": 10}
WINDOW_SECONDS = 60.0
FIRST_ESTIMATE = 4_000
MAX_ATTEMPTS = 6
TRANSIENT_ERRORS = {"APIConnectionError", "APITimeoutError", "ServiceRequestError", "ServiceResponseError"}

# The keys of each evidence file's rows, in the order the files already use. A saved run holds all
# of them: the first run becomes an answer row and a metrics row, runs 2 and up become repeat rows.
ANSWER_ROW = ("case_id", "text", "receipts", "instructions_sha256", "recorded_on")
METRICS_ROW = ("case_id", "model", "seconds", "input_tokens", "cached_tokens", "output_tokens",
               "instructions_sha256", "recorded_on")
RUN_ROW = ("case_id", "run", "text", "receipts", "model", "seconds", "input_tokens", "cached_tokens",
           "output_tokens", "instructions_sha256", "recorded_on")
COUNT_KEYS = ("input_tokens", "cached_tokens", "output_tokens")


class Stop(Exception):
    """A plain reason to stop. Code 2 means nothing was run; code 1 means a run was cut short."""

    def __init__(self, message, code=1):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Files:
    """Where the evidence lives. The defaults are the repository's; tests point these elsewhere."""

    cases: Path = CASES_PATH
    answers: Path = scorecards.ANSWERS
    metrics: Path = scorecards.METRICS
    repeats: Path = scorecards.REPEATS
    prices: Path = scorecards.PRICES
    signoffs: Path = scorecards.SIGNOFFS
    journals: Path = JOURNALS

    def journal(self, template_id):
        return self.journals / f"{template_id}.jsonl"


@dataclass(frozen=True)
class Item:
    """One agent to record: its cases, the instructions fingerprint, and the model to run on."""

    template_id: str
    profile: str
    cases: list
    digest: str
    model: str
    source: str


@dataclass(frozen=True)
class Assessment:
    state: str
    reasons: list
    model: str | None
    recorded_on: str | None


def dump(row):
    """One evidence line. scorecards.py splits lines with splitlines(), which also breaks at U+2028,
    U+2029 and U+0085, so those three are written as escapes."""
    text = json.dumps(row, ensure_ascii=False)
    return text.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029").replace("\x85", "\\u0085")


def project(row, keys):
    return {key: row[key] for key in keys}


def write_atomic(updates):
    """Write each file in full beside its target first, then swap them in one after another.

    A failed write changes nothing. A failed swap leaves the files already swapped new and the rest old."""
    pending = []
    try:
        for path, data in updates:
            path.parent.mkdir(parents=True, exist_ok=True)
            temp = path.with_name(path.name + ".tmp")
            pending.append((temp, path))
            with temp.open("wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
        while pending:
            os.replace(*pending[0])
            pending.pop(0)
    finally:
        for temp, _ in pending:
            temp.unlink(missing_ok=True)


def append_line(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as handle:
        handle.write(text.encode("utf-8") + b"\n")
        handle.flush()
        os.fsync(handle.fileno())


def read_rows(path):
    """The JSON rows of an evidence file. A file that doesn't exist has none."""
    path = Path(path)
    if not path.exists():
        return []
    rows = []
    for number, raw in enumerate(path.read_bytes().split(b"\n"), 1):
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except ValueError:
            raise Stop(f"{path.name}, line {number}: not valid JSON. Restore the file from Git first.", 2) from None
        if not isinstance(row, dict):
            raise Stop(f"{path.name}, line {number}: expected a JSON object. Restore the file from Git first.", 2)
        rows.append(row)
    return rows


def replace_rows(data, case_ids, new_rows, name):
    """Return an evidence file's bytes with the rows of these cases replaced by new_rows.

    Every other line is kept exactly as it was. The new block goes where the first old row was, or at
    the end when there were none, and uses the file's own line endings.
    """
    lines = data.split(b"\n")
    if lines[-1] == b"":
        lines.pop()
    crlf = data.count(b"\r\n") * 2 > data.count(b"\n")
    block = [dump(row).encode("utf-8") + (b"\r" if crlf else b"") for row in new_rows]
    kept, placed = [], False
    for number, raw in enumerate(lines, 1):
        if raw.strip():
            try:
                row = json.loads(raw)
            except ValueError:
                raise Stop(f"{name}, line {number}: not valid JSON. Restore the file from Git first.", 2) from None
            if isinstance(row, dict) and row.get("case_id") in case_ids:
                if not placed:
                    kept.extend(block)
                    placed = True
                continue
        kept.append(raw)
    if not placed:
        kept.extend(block)
    return b"\n".join(kept) + b"\n" if kept else b""


def parse_limits(text):
    """Read --limits: {"deployment": {"tokens": N, "requests": N}}, per minute, for a deployment whose
    quota isn't the default."""
    if not text:
        return {}
    try:
        limits = json.loads(text)
    except ValueError:
        limits = None
    if not isinstance(limits, dict) or any(
            not DEPLOYMENT_NAME.fullmatch(model) or not isinstance(entry, dict) or not entry
            or set(entry) - set(DEFAULT_LIMITS) or any(type(value) is not int or value < 1 for value in entry.values())
            for model, entry in limits.items()):
        raise Stop('--limits must look like {"gpt-5.4": {"tokens": 30000, "requests": 30}}', 2)
    return limits


class Pacer:
    """Keeps each model deployment under its per-minute token and request limits.

    It remembers when each request was sent and how many tokens it used, and waits until the oldest
    ones have left the last 60 seconds. A request still in flight holds a guess at its tokens: the
    largest of the last ten requests, until Foundry reports the real count.
    """

    def __init__(self, limits, clock, sleep):
        self.limits, self.clock, self.sleep = limits, clock, sleep
        self.sent = {}
        self.observed = {}

    def limit(self, model):
        return {**DEFAULT_LIMITS, **self.limits.get(model, {})}

    async def acquire(self, model):
        limit = self.limit(model)
        window = self.sent.setdefault(model, [])
        while True:
            now = self.clock()
            while window and window[0][0] <= now - WINDOW_SECONDS:
                window.pop(0)
            reserve = min(limit["tokens"], max(self.observed.get(model, [FIRST_ESTIMATE])))
            wait = 0.0
            if len(window) >= limit["requests"]:
                wait = window[len(window) - limit["requests"]][0] + WINDOW_SECONDS - now
            used = sum(tokens for _, tokens in window)
            if used + reserve > limit["tokens"]:
                for sent_at, tokens in window:
                    used -= tokens
                    if used + reserve <= limit["tokens"]:
                        wait = max(wait, sent_at + WINDOW_SECONDS - now)
                        break
            if wait <= 0:
                entry = [now, reserve]
                window.append(entry)
                return entry
            await self.sleep(wait)

    def release(self, model, entry, tokens):
        """Swap a finished request's guess for the tokens Foundry reported."""
        if tokens is None:
            return
        entry[1] = tokens
        recent = self.observed.setdefault(model, [])
        recent.append(tokens)
        del recent[:-10]


def _seconds(value, scale):
    try:
        seconds = float(value) / scale
    except (TypeError, ValueError):
        return None
    return seconds if math.isfinite(seconds) and seconds >= 0 else None


def retry_after(headers):
    """Seconds Foundry asked us to wait, from its retry-after-ms or retry-after header, or None."""
    for name, scale in (("retry-after-ms", 1000.0), ("retry-after", 1.0)):
        seconds = _seconds(headers.get(name), scale)
        if seconds is not None:
            return seconds
    return None


def retry_delay(error, attempt):
    """Seconds to wait before sending a request again, or None when waiting can't help."""
    status = getattr(error, "status_code", None)
    if status == 429:
        hint = retry_after(getattr(getattr(error, "response", None), "headers", None) or {})
        return 60.0 if hint is None else min(120.0, max(1.0, hint))
    if (status in (408, 409) or (type(status) is int and status >= 500) or type(error).__name__ in TRANSIENT_ERRORS
            or isinstance(error, (TimeoutError, ConnectionError))):
        return min(30.0, 2.0 ** attempt)
    return None


def describe(error):
    """One short line about a failed request. Never includes headers or credentials."""
    status = getattr(error, "status_code", None)
    text = " ".join(str(error).split())[:200]
    return type(error).__name__ + (f" (HTTP {status})" if status else "") + (f": {text}" if text else "")


class PacedClient:
    """Stands in for the Responses client: paces each request, retries what can be retried, and
    times what succeeds. `seconds` adds up the successful requests since it was last reset."""

    def __init__(self, send, pacer, *, clock, sleep, log):
        self.responses = self
        self.send, self.pacer, self.clock, self.sleep, self.log = send, pacer, clock, sleep, log
        self.seconds = 0.0

    async def create(self, **options):
        model, attempt = options["model"], 0
        while True:
            attempt += 1
            entry = await self.pacer.acquire(model)
            started = self.clock()
            try:
                response = await self.send(options)
            except Exception as error:
                delay = retry_delay(error, attempt)
                if delay is None or attempt >= MAX_ATTEMPTS:
                    raise Stop(f"Foundry request failed after {attempt} "
                               f"{'try' if attempt == 1 else 'tries'}: {describe(error)}") from None
                self.log(f"  {describe(error)}; waiting {delay:.0f} s, then trying again (try {attempt} of {MAX_ATTEMPTS})")
                await self.sleep(delay)
                continue
            self.seconds += self.clock() - started
            reported = usage_record(response)
            total = reported["total_tokens"]
            if total is None and reported["input_tokens"] is not None and reported["output_tokens"] is not None:
                total = reported["input_tokens"] + reported["output_tokens"]
            self.pacer.release(model, entry, total)
            return response


def cases_by_template(files):
    grouped = {}
    for case in load_cases(files.cases)["cases"]:
        grouped.setdefault(case["template_id"], []).append(case)
    return grouped


def pick_templates(grouped, wanted):
    """The agents to work on: those named (each must have test cases), or all that do."""
    if not wanted:
        return list(grouped)
    unknown = sorted(set(wanted) - set(grouped))
    if unknown:
        raise Stop("No test cases for: " + ", ".join(unknown) + ". Agents with test cases: " + ", ".join(grouped), 2)
    return list(dict.fromkeys(wanted))


def load_evidence(files):
    return {"answers": read_rows(files.answers), "metrics": read_rows(files.metrics),
            "repeats": read_rows(files.repeats)}


def _dated(row):
    value = row.get("recorded_on")
    # scorecards.py already knows what a valid date looks like.
    return value if isinstance(value, str) and scorecards._valid_date(value) else None


def assess(template_id, cases, evidence):
    """Say whether an agent's recorded answers are current, stale (recorded on other instructions),
    incomplete, or missing."""
    ids = [case["id"] for case in cases]
    mine = {kind: [row for row in rows if row.get("case_id") in ids] for kind, rows in evidence.items()}
    every = [row for rows in mine.values() for row in rows]
    if not every:
        return Assessment("missing", ["no answers are recorded for this agent"], None, None)
    digest = scorecards.instructions_digest(template_id)
    old = sum(row.get("instructions_sha256") != digest for row in every)
    problems = []
    for case_id in ids:
        answers = sum(row["case_id"] == case_id for row in mine["answers"])
        metrics = sum(row["case_id"] == case_id for row in mine["metrics"])
        runs = Counter(row["run"] if type(row.get("run")) is int else None
                       for row in mine["repeats"] if row["case_id"] == case_id)
        if answers != 1 or metrics != 1 or runs != Counter(range(2, RUNS_PER_CASE + 1)):
            listed = ", ".join(str(run) for run in sorted(runs.elements(), key=str)) or "none"
            problems.append(f"{case_id}: {answers} answer rows, {metrics} metrics rows, repeat runs {listed}; "
                            f"it needs 1, 1 and 2 to {RUNS_PER_CASE}")
    undated = sum(_dated(row) is None for row in every)
    if undated:
        problems.append(f"{undated} rows have no valid recorded_on date")
    models = sorted({str(row.get("model")) for row in mine["metrics"] + mine["repeats"]})
    if len(models) > 1:
        problems.append("more than one model was used: " + ", ".join(models))
    reasons = ([f"{old} of {len(every)} recorded rows came from other instructions"] if old else []) + problems
    state = "stale" if old else "incomplete" if problems else "current"
    model = models[0] if len(models) == 1 else "mixed" if models else None
    return Assessment(state, reasons, model, max(filter(None, map(_dated, every)), default=None))


def usable(row, ids, digest, model):
    """Whether a journal row is a whole, well-formed run of these cases on these instructions."""
    if not isinstance(row, dict) or set(row) != set(RUN_ROW):
        return False
    counts = [row[key] for key in COUNT_KEYS]
    return (row["case_id"] in ids and type(row["run"]) is int and 1 <= row["run"] <= RUNS_PER_CASE
            and row["instructions_sha256"] == digest and (model is None or row["model"] == model)
            and isinstance(row["text"], str) and bool(row["text"].strip()) and isinstance(row["receipts"], list)
            and all(type(count) is int and count >= 0 for count in counts) and row["cached_tokens"] <= row["input_tokens"]
            and isinstance(row["seconds"], (int, float)) and not isinstance(row["seconds"], bool) and row["seconds"] >= 0
            and _dated(row) is not None)


def load_journal(path, ids, digest, model=None):
    """The usable saved runs of an interrupted recording, and whether the file holds nothing else.

    A line cut short by a crash, a run from other instructions or another model, and repeats are
    left out. A damaged line anywhere else means something else wrote to the file.
    """
    path = Path(path)
    if not path.exists():
        return [], True
    data = path.read_bytes()
    lines = data.split(b"\n")
    clean = lines[-1] == b""
    if clean:
        lines.pop()
    kept, seen = [], set()
    for number, raw in enumerate(lines, 1):
        if not raw.strip():
            clean = False
            continue
        try:
            row = json.loads(raw)
        except ValueError:
            if number == len(lines) and not clean:
                clean = False
                continue
            raise Stop(f"{path}: line {number} is damaged. Delete the file to start this agent over; "
                       "nothing else depends on it.", 2) from None
        key = (row["case_id"], row["run"]) if usable(row, ids, digest, model) else None
        if key is None or key in seen:
            clean = False
            continue
        seen.add(key)
        kept.append(row)
    return kept, clean


def resolve_models(template_ids, *, model, models, environ, recorded):
    """Pick each agent's model deployment the way the Lab does: its profile's deployment, else the default.

    In order: --model, --models, the Lab's WORKBENCH_AGENT_CREATION_MODELS, the Lab's
    WORKBENCH_AGENT_CREATION_MODEL, then the model of the agent's last recording.
    """
    def profiles(text, what):
        try:
            value = json.loads(text) if text else {}
        except ValueError:
            value = None
        if not isinstance(value, dict) or any(
                profile not in MODEL_PROFILES or not isinstance(name, str) or not DEPLOYMENT_NAME.fullmatch(name)
                for profile, name in value.items()):
            raise Stop(f"{what} must map model profiles ({', '.join(MODEL_PROFILES)}) to deployment names, "
                       'like {"reasoning": "gpt-5.4"}', 2)
        return value

    from_flag, from_env = profiles(models, "--models"), profiles(environ.get(ENV_MODELS), ENV_MODELS)
    chosen = {}
    for template_id in template_ids:
        profile = TEMPLATES[template_id]["model_profile"]
        candidates = ((model, "--model"), (from_flag.get(profile), "--models"), (from_env.get(profile), ENV_MODELS),
                      (environ.get(ENV_MODEL), ENV_MODEL), (recorded.get(template_id), "its last recording"))
        name, source = next(((name, source) for name, source in candidates if name), (None, None))
        if name is None:
            raise Stop(f"No model deployment for {template_id} ({profile}). Pass --model, or --models like "
                       f'{{"{profile}": "gpt-5.4"}}, or set {ENV_MODELS} as the Lab does.', 2)
        if not DEPLOYMENT_NAME.fullmatch(name):
            raise Stop(f"{source} gives an invalid deployment name for {template_id}: {name!r}", 2)
        chosen[template_id] = (name, source)
    return chosen


def validate_endpoint(value):
    """Accept only an HTTPS Foundry project URL, with the rules evaluations/run.py uses."""
    if not value:
        raise Stop(f"Say which Foundry project to use: pass --endpoint or set {ENV_ENDPOINT}.", 2)
    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError:
        parts = port = None
    if (parts is None or parts.scheme != "https" or not parts.hostname or parts.username or parts.password
            or parts.query or parts.fragment or port not in (None, 443)
            or not re.fullmatch(r"/api/projects/[A-Za-z0-9_-]+", parts.path)):
        raise Stop("The endpoint must be an HTTPS Foundry project URL, like "
                   "https://<account>.services.ai.azure.com/api/projects/<project>, "
                   "without credentials, query or fragment.", 2)
    return value


def last_recording(evidence, ids, model, prices):
    """(tokens, dollars) an agent's last recording used, when it ran on this model and can be priced."""
    rows = [row for kind in ("metrics", "repeats") for row in evidence[kind] if row.get("case_id") in ids]
    try:
        if not rows or {row.get("model") for row in rows} != {model}:
            return None
        return (sum(row["input_tokens"] + row["output_tokens"] for row in rows),
                sum(scorecards.token_cost(prices, model, row["input_tokens"], row["cached_tokens"],
                                          row["output_tokens"]) for row in rows))
    except (KeyError, TypeError, ValueError):
        return None


def load_prices(files):
    try:
        return json.loads(files.prices.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def load_signed(files):
    """The agents with a recorded sign-off, or None when the sign-off file can't be read."""
    try:
        return scorecards.load_signoffs(files.signoffs)
    except (OSError, ValueError):
        return None


def plan_lines(items, files, evidence, pacer):
    """What `record` would do. Reads files only."""
    prices, signed = load_prices(files), load_signed(files)
    lines, pending = ["Plan to record test answers again (nothing has been sent):", ""], 0
    if signed is None:
        lines += [f"Note: {shown(files.signoffs)} can't be read. Fix or remove it before rebuilding the scorecards.", ""]
    for item in items:
        ids = [case["id"] for case in item.cases]
        total, limit = len(ids) * RUNS_PER_CASE, pacer.limit(item.model)
        saved, _ = load_journal(files.journal(item.template_id), ids, item.digest, item.model)
        pending += total - len(saved)
        state = assess(item.template_id, item.cases, evidence).state
        lines += [f"{item.template_id} ({item.profile})",
                  f"  {len(ids)} cases x {RUNS_PER_CASE} runs = {total} runs on {item.model} (model from {item.source})",
                  f"  recorded now: {state}"]
        if state == "current":
            lines.append("  its answers already match its instructions; recording again only refreshes them")
        if saved:
            lines.append(f"  {len(saved)} of {total} runs are already saved by an interrupted recording "
                         "and won't be sent again")
        used = last_recording(evidence, ids, item.model, prices)
        if used:
            tokens, dollars = used
            lines.append(f"  its last recording used {tokens:,} tokens, about ${dollars:.2f}; "
                         f"at {limit['tokens']:,} tokens a minute that takes at least {math.ceil(tokens / limit['tokens'])} min")
        else:
            lines.append("  no earlier recording on this model, so no cost or time estimate")
        if item.template_id in (signed or {}) or TEMPLATE_METADATA.get(item.template_id, {}).get("readiness") == "reviewed":
            lines.append("  its sign-off or Reviewed label will no longer match the new answers; "
                         "a person must read them and sign off again")
        lines.append("")
    lines.append("Pacing, for each model deployment:")
    for model in sorted({item.model for item in items}):
        limit = pacer.limit(model)
        lines.append(f"  {model}: up to {limit['tokens']:,} tokens and {limit['requests']} requests a minute")
    return lines, pending


async def record_run(item, case, run, client, today):
    """One run of one case, on the same code the Lab's Chat preview uses. Returns the row to save."""
    client.seconds = 0.0
    usage = []
    outcome = await run_preview(client, template_id=item.template_id, model=item.model, prompt=case_input(case),
                                reasoning=item.profile != "tool_calling", usage=usage)
    return finish_run(item, case, run, outcome, usage, client.seconds, today)


def finish_run(item, case, run, outcome, usage, seconds, today):
    status, text, transcript = outcome
    where = f"{case['id']} run {run}"
    if status != "completed" or not isinstance(text, str) or not text.strip():
        raise Stop(f"{where}: the model's reply was {status!r}, so it wasn't saved. Run the same command again to retry.")
    total = summarize_usage(usage)
    if total is None or total["input_tokens"] is None or total["output_tokens"] is None:
        raise Stop(f"{where}: Foundry didn't report token counts, so its cost can't be recorded.")
    # A cached count the service left out is taken as 0, which can only overstate the cost.
    cached = total["cached_tokens"] or 0
    if cached > total["input_tokens"]:
        raise Stop(f"{where}: Foundry reported more cached tokens than input tokens.")
    return {
        "case_id": case["id"], "run": run, "text": text,
        "receipts": [{"tool": call.get("name", "unknown")} for call in transcript if call.get("type") == "function_call"],
        "model": item.model, "seconds": round(seconds, 1), "input_tokens": total["input_tokens"],
        "cached_tokens": cached, "output_tokens": total["output_tokens"],
        "instructions_sha256": item.digest, "recorded_on": today,
    }


def resume(files, item):
    """The saved runs of an interrupted recording, with anything unusable removed from the journal."""
    path = files.journal(item.template_id)
    saved, clean = load_journal(path, [case["id"] for case in item.cases], item.digest, item.model)
    if not clean:
        write_atomic([(path, b"".join(dump(row).encode("utf-8") + b"\n" for row in saved))])
    return {(row["case_id"], row["run"]): row for row in saved}


def save_run(files, item, row):
    append_line(files.journal(item.template_id), dump(row))


def commit(files, item, done):
    """Replace this agent's rows in the three evidence files, then drop its journal."""
    rows = [done[(case["id"], run)] for case in item.cases for run in range(1, RUNS_PER_CASE + 1)]
    first, later = [row for row in rows if row["run"] == 1], [row for row in rows if row["run"] > 1]
    ids, updates = [case["id"] for case in item.cases], []
    for path, keys, chosen in ((files.answers, ANSWER_ROW, first), (files.metrics, METRICS_ROW, first),
                               (files.repeats, RUN_ROW, later)):
        current = path.read_bytes() if path.exists() else b""
        updates.append((path, replace_rows(current, ids, [project(row, keys) for row in chosen], path.name)))
    try:
        write_atomic(updates)
    except OSError as error:
        raise Stop(f"Couldn't write the evidence files ({describe(error)}). The finished runs are saved in "
                   f"{files.journal(item.template_id)}; run the same command again to finish.") from None
    files.journal(item.template_id).unlink(missing_ok=True)
    return rows


async def record_agent(item, files, client, today, log):
    """Record the runs of an agent that aren't saved yet, then replace its rows in the evidence."""
    done = resume(files, item)
    total = len(item.cases) * RUNS_PER_CASE
    for case in item.cases:
        for run in range(1, RUNS_PER_CASE + 1):
            if (case["id"], run) in done:
                continue
            row = await record_run(item, case, run, client, today)
            save_run(files, item, row)
            done[(case["id"], run)] = row
            log(f"  {item.template_id}: {len(done)} of {total} runs saved ({case['id']} run {run}, "
                f"{row['seconds']:.1f} s, {row['input_tokens'] + row['output_tokens']:,} tokens)")
    return commit(files, item, done)


async def record_all(items, files, client, today, committed):
    """Record the agents one after another. Each is committed on its own, so a later failure never
    undoes an earlier agent."""
    prices = load_prices(files)
    for item in items:
        say("")
        say(f"{item.template_id}: recording {len(item.cases) * RUNS_PER_CASE} runs on {item.model}")
        rows = await record_agent(item, files, client, today, say)
        committed.append(item)
        say(f"{item.template_id}: done. Its rows in the three evidence files were replaced. Used {used_text(rows, prices)}.")
        after = assess(item.template_id, item.cases, load_evidence(files))
        if after.state != "current":
            raise Stop(f"{item.template_id}: the evidence files don't look right after the replacement: "
                       + "; ".join(after.reasons) + ". Check them with git diff before going on.")


def used_text(rows, prices):
    tokens = sum(row["input_tokens"] + row["output_tokens"] for row in rows)
    try:
        dollars = sum(scorecards.token_cost(prices, row["model"], row["input_tokens"], row["cached_tokens"],
                                            row["output_tokens"]) for row in rows)
    except (KeyError, TypeError, ValueError):
        return f"{tokens:,} tokens (no price for its model, so no cost)"
    return f"{tokens:,} tokens, about ${dollars:.2f}"


def next_steps(items):
    ids = " ".join(item.template_id for item in items)
    say("")
    say("Next steps:")
    say("  1. Rebuild the Lab's scorecards:  python evaluations/scorecards.py write")
    say("     It stops with 'the answers changed after the sign-off' for an agent that had a sign-off.")
    say("  2. A person reads the new answers for: " + ids)
    say("     Then they run: python evaluations/scorecards.py signoff --reviewer \"Name\" " + ids)
    say("     This never records a sign-off. Until then, set the agent's readiness back to sample in")
    say("     workbench/agent_templates.py if it says reviewed.")
    say("  3. The Lab shows the new results after the next deploy.")


def command_record(args, files, *, open_client, clock, sleep, today, environ):
    if in_ci(environ):
        raise Stop("Recording calls Foundry and costs money, so it never runs in CI.", 2)
    grouped = cases_by_template(files)
    chosen = pick_templates(grouped, args.templates)
    evidence = load_evidence(files)
    earlier = {template_id: assess(template_id, grouped[template_id], evidence).model for template_id in chosen}
    models = resolve_models(chosen, model=args.model, models=args.models, environ=environ,
                            recorded={key: value for key, value in earlier.items() if value not in (None, "mixed")})
    pacer = Pacer(parse_limits(args.limits), clock, sleep)
    items = [Item(template_id, TEMPLATES[template_id]["model_profile"], grouped[template_id],
                  scorecards.instructions_digest(template_id), *models[template_id]) for template_id in chosen]
    lines, pending = plan_lines(items, files, evidence, pacer)
    for line in lines:
        say(line)
    if not args.yes:
        say("")
        say("Nothing was sent. Recording calls Foundry and costs money; add --yes to go ahead.")
        return 2
    endpoint = validate_endpoint(args.endpoint or environ.get(ENV_ENDPOINT)) if pending else None
    say("")
    say(f"Recording {pending} runs. If this stops, run the same command again; finished runs are kept.")
    committed = []
    try:
        with (open_client(endpoint) if pending else contextlib.nullcontext()) as send:
            client = PacedClient(send, pacer, clock=clock, sleep=sleep, log=say) if pending else None
            asyncio.run(record_all(items, files, client, today, committed))
    finally:
        if committed:
            next_steps(committed)
    return 0


def command_status(args, files):
    grouped = cases_by_template(files)
    chosen = pick_templates(grouped, args.templates)
    evidence = load_evidence(files)
    width = max(map(len, chosen), default=5)
    say(f"{'Agent':<{width}}  {'State':<10}  {'Recorded':<10}  Model")
    behind = []
    for template_id in chosen:
        result = assess(template_id, grouped[template_id], evidence)
        say(f"{template_id:<{width}}  {result.state:<10}  {result.recorded_on or '-':<10}  {result.model or '-'}")
        if result.state == "current":
            continue
        behind.append(template_id)
        notes = result.reasons[:3] + ([f"and {len(result.reasons) - 3} more"] if len(result.reasons) > 3 else [])
        for note in notes + [saved_note(files, template_id, grouped[template_id])]:
            if note:
                say(f"{'':<{width}}    {note}")
    say("")
    if not behind:
        say(f"All {len(chosen)} agents' recorded answers match their instructions.")
        return 0
    say(f"{len(behind)} of {len(chosen)} agents need their test answers recorded again.")
    say("To see the plan (nothing is sent): python evaluations/library_runs.py record --templates " + " ".join(behind))
    say("Add --yes to record them. That calls Foundry and costs money.")
    return 1


def saved_note(files, template_id, cases):
    """What an interrupted recording left behind, for status."""
    path = files.journal(template_id)
    if not path.exists():
        return None
    try:
        saved, _ = load_journal(path, [case["id"] for case in cases], scorecards.instructions_digest(template_id))
    except Stop:
        return f"its saved-runs file is damaged; delete {shown(path)} to start this agent over"
    total = len(cases) * RUNS_PER_CASE
    return f"interrupted recording: {len(saved)} of {total} runs saved; `record` picks up from there" if saved else None


def shown(path):
    try:
        return path.relative_to(HERE.parent).as_posix()
    except ValueError:
        return str(path)


def say(text="", *, error=False):
    """Print one line. Characters a legacy Windows console can't show become '?'."""
    print(text.encode("ascii", "replace").decode("ascii"), file=sys.stderr if error else sys.stdout, flush=True)


def in_ci(environ):
    return any(environ.get(name, "").strip().lower() not in ("", "0", "false", "no") for name in ("CI", "GITHUB_ACTIONS"))


@contextlib.contextmanager
def open_live_client(endpoint):
    """Open the Foundry project and yield an async function that sends one Responses API request.

    The Azure SDK is imported here so that status, the plan and the tests need no Azure packages.
    The client is the blocking one, as in run.py; each request runs in a thread.
    """
    try:
        from azure.ai.projects import AIProjectClient
        from azure.identity import DefaultAzureCredential
    except ImportError:
        raise Stop("Recording needs the Azure SDK: pip install -r evaluations/requirements.txt", 2) from None
    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(endpoint=endpoint, credential=credential, allow_preview=True,
                        retry_total=0, connection_timeout=30, read_timeout=60) as project,
        project.get_openai_client(timeout=240, max_retries=0) as client,
    ):
        async def send(options):
            return await asyncio.to_thread(client.responses.create, **options)

        yield send


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0], allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)
    status = commands.add_parser("status", allow_abbrev=False,
                                 help="show which agents need new test answers (offline, free)")
    status.add_argument("--templates", nargs="+", metavar="ID", help="only these agents (default: all with test cases)")
    record = commands.add_parser("record", allow_abbrev=False,
                                 help="show the plan to record agents again; with --yes, do it (billable)")
    record.add_argument("--templates", nargs="+", required=True, metavar="ID", help="the agents to record again")
    record.add_argument("--yes", action="store_true",
                        help="BILLABLE: send the requests to Foundry. Without it, only the plan is shown.")
    record.add_argument("--endpoint", help=f"Foundry project URL (default: {ENV_ENDPOINT})")
    choice = record.add_mutually_exclusive_group()
    choice.add_argument("--model", help="one model deployment for every agent named")
    choice.add_argument("--models", help='JSON mapping model profiles to deployments, like {"reasoning": "gpt-5.4"}')
    record.add_argument("--limits", help='JSON per-minute limits for deployments with more quota than the default, '
                                         'like {"gpt-5.4": {"tokens": 30000, "requests": 30}}')
    return parser


def main(argv=None, *, files=None, open_client=open_live_client, clock=time.monotonic, sleep=asyncio.sleep,
         today=None, environ=None):
    args = build_parser().parse_args(argv)
    files = files or Files()
    environ = os.environ if environ is None else environ
    today = today or datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    try:
        if args.command == "status":
            return command_status(args, files)
        return command_record(args, files, open_client=open_client, clock=clock, sleep=sleep, today=today,
                              environ=environ)
    except Stop as stop:
        say(f"Stopped: {stop}", error=True)
        return stop.code
    except KeyboardInterrupt:
        say("Interrupted. Finished runs are saved; run the same command again to continue.", error=True)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())

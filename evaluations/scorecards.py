"""Build the agent library's test-result scorecards from recorded acceptance answers.

Offline only: it screens answers already in evidence/ with library_checks, adds the recorded
response times and token counts, and prices those tokens with a saved list-price table. The
Lab serves the result from workbench/agent_scorecards.json.

Each case has one recorded answer (run 1, the one a person reads) and, in the repeat file, more
runs of the same request. A case passes only when every run passes, because a model that gets a
case right once can still get it wrong the next time.

Every recorded row carries a fingerprint of the instructions its agent had when it was run, and the
date it was recorded. The build fails if the Lab's instructions for an agent have changed since, so
the test results can't describe instructions the Lab no longer uses; library_runs.py re-records an
agent's answers. An agent's test date is the latest date on its rows.

    python scorecards.py write   # regenerate the Lab's copy
    python scorecards.py check   # fail if the Lab's copy is out of date
    python scorecards.py signoff --reviewer "Name" --all   # record that a person read the answers

Run `signoff` only after a person has read the answers. It writes evidence/signoffs.json, which
ties each sign-off to a fingerprint of the recorded answers that were read. If a recorded answer
changes later, the build fails until someone reads the answers again.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import re
import statistics
import sys
from pathlib import Path

from library_checks import CASES_PATH, TEMPLATES, case_input, load_cases, score

HERE = Path(__file__).resolve().parent
EVIDENCE = HERE / "evidence"
OUTPUT = HERE.parent / "workbench" / "agent_scorecards.json"
ANSWERS_DATASET = "library-v4"
ANSWERS = EVIDENCE / "library-acceptance-2026-09-29.jsonl"
# Later runs replace earlier answers for the same case. The direct run sent each case with the
# template's current instructions straight to the Lab's Foundry project and timed it from the
# machine that ran it, so its times can differ slightly from the live Lab.
RUNS = (("direct", ANSWERS),)
METRICS = EVIDENCE / "library-acceptance-2026-09-29-metrics.jsonl"
# Runs 2 and up of the same cases, each row carrying its own answer and metrics.
REPEATS = EVIDENCE / "library-repeat-2026-09-29.jsonl"
PRICES = EVIDENCE / "model-prices-2026-09.json"
SIGNOFFS = EVIDENCE / "signoffs.json"
METRIC_KEYS = ("seconds", "input_tokens", "cached_tokens", "output_tokens")


def _lines(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def token_cost(prices, model, input_tokens, cached_tokens, output_tokens):
    rate = prices["models"][model]
    uncached = input_tokens - cached_tokens
    if uncached < 0:
        raise ValueError(f"{model}: cached tokens exceed input tokens")
    total = uncached * rate["input"] + cached_tokens * rate["cached_input"] + output_tokens * rate["output"]
    return total / 1_000_000


def load_answers(cases, runs):
    answers = {}
    for run, path in runs:
        seen = set()
        for record in _lines(path):
            case_id = record["case_id"]
            if case_id not in cases:
                raise ValueError(f"{path.name}: unknown case_id {case_id!r}")
            if case_id in seen:
                raise ValueError(f"{path.name}: {case_id} has an answer more than once")
            seen.add(case_id)
            answers[case_id] = (run, record)
    return answers


def load_repeats(path, cases):
    """Runs 2 and up of each case: {case_id: {run number: row}}. A missing file means no repeats."""
    repeats = {}
    if path is None or not Path(path).exists():
        return repeats
    name = Path(path).name
    for record in _lines(path):
        case_id, run = record.get("case_id"), record.get("run")
        if case_id not in cases:
            raise ValueError(f"{name}: unknown case_id {case_id!r}")
        if isinstance(run, bool) or not isinstance(run, int) or run < 2:
            raise ValueError(f"{name}: {case_id} needs a run number of 2 or more, not {run!r}")
        if run in repeats.setdefault(case_id, {}):
            raise ValueError(f"{name}: {case_id} has run {run} more than once")
        repeats[case_id][run] = record
    return repeats


def _measured(record, where):
    """The model and metrics of one run, checked so a bad row can't silently skew the averages."""
    if not str(record.get("model", "")).strip():
        raise ValueError(f"{where}: no model recorded")
    for key in METRIC_KEYS:
        value = record.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            raise ValueError(f"{where}: {key} must be a number of 0 or more, not {value!r}")
    return record


def _whole_number(value):
    return int(value + 0.5)


def instructions_digest(template_id):
    """Fingerprint of the instructions the Lab serves for an agent."""
    return hashlib.sha256(TEMPLATES[template_id]["instructions"].encode("utf-8")).hexdigest()


def _check_fingerprint(record, case, run, what="answer"):
    recorded = record.get("instructions_sha256")
    if not recorded:
        raise ValueError(f"{case['id']} run {run}: no instructions fingerprint was recorded with this {what}")
    if recorded != instructions_digest(case["template_id"]):
        raise ValueError(f"{case['id']} run {run}: the instructions of {case['template_id']} changed after this "
                         f"{what} was recorded; record its test answers again with: "
                         f"python evaluations/library_runs.py record --templates {case['template_id']} --yes")


def _recorded_on(record, where):
    value = record.get("recorded_on")
    if not isinstance(value, str) or not _valid_date(value):
        raise ValueError(f"{where}: no recorded date; every row needs recorded_on as YYYY-MM-DD")
    return value


def template_digests(cases, answers):
    """Fingerprint each agent's recorded answers, so a sign-off covers only what the person read."""
    texts = {}
    for case_id, (_, record) in answers.items():
        texts.setdefault(cases[case_id]["template_id"], []).append((case_id, record.get("text", "")))
    return {
        template_id: hashlib.sha256(
            json.dumps(sorted(items), ensure_ascii=False).encode("utf-8")).hexdigest()
        for template_id, items in texts.items()
    }


def _valid_date(value):
    value = str(value)
    try:
        datetime.date.fromisoformat(value)
    except ValueError:
        return False
    return re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is not None


def load_signoffs(path):
    path = Path(path)
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or data.get("answers_dataset") != ANSWERS_DATASET:
        raise ValueError(f"{path.name}: sign-offs are for a different set of answers; read them again")
    signoffs = {}
    for item in data.get("signoffs", []):
        template_id = item.get("template_id")
        if (not str(item.get("reviewer", "")).strip() or not _valid_date(item.get("reviewed_on"))
                or not item.get("answers_sha256") or template_id in signoffs):
            raise ValueError(f"{path.name}: invalid or repeated sign-off for {template_id!r}")
        signoffs[template_id] = item
    return signoffs


def record_signoff(reviewer, reviewed_on, template_ids, path=SIGNOFFS, cases_path=CASES_PATH, runs=RUNS):
    reviewer = reviewer.strip()
    if not reviewer:
        raise ValueError("A named reviewer is required")
    if not _valid_date(reviewed_on):
        raise ValueError("The review date must look like 2026-09-30")
    cases = {case["id"]: case for case in load_cases(cases_path)["cases"]}
    digests = template_digests(cases, load_answers(cases, runs))
    unknown = sorted(set(template_ids) - set(digests))
    if not template_ids or unknown:
        raise ValueError("Name agents with recorded answers: " + (", ".join(unknown) or "none given"))
    path = Path(path)
    existing = load_signoffs(path)
    for template_id in template_ids:
        existing[template_id] = {
            "template_id": template_id, "reviewer": reviewer, "reviewed_on": reviewed_on,
            "answers_sha256": digests[template_id],
        }
    record = {"schema_version": 1, "answers_dataset": ANSWERS_DATASET,
              "signoffs": [existing[key] for key in sorted(existing)]}
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8", newline="\n")
    return sorted(template_ids)


def build(cases_path=CASES_PATH, runs=RUNS, metrics_path=METRICS, prices_path=PRICES, signoffs_path=SIGNOFFS,
          repeats_path=REPEATS, verify_instructions=True):
    data = load_cases(cases_path)
    prices = json.loads(Path(prices_path).read_text(encoding="utf-8"))
    cases = {case["id"]: case for case in data["cases"]}
    answers = load_answers(cases, runs)
    metrics = {}
    for record in _lines(metrics_path):
        if record["case_id"] in metrics:
            raise ValueError(f"{Path(metrics_path).name}: {record['case_id']} has a metrics row more than once")
        metrics[record["case_id"]] = record
    missing = sorted(set(answers) - set(metrics))
    if missing:
        raise ValueError("no recorded metrics for " + ", ".join(missing))
    repeats = load_repeats(repeats_path, cases)
    stray = sorted(set(repeats) - set(answers))
    if stray:
        raise ValueError("repeat runs for cases with no recorded answer: " + ", ".join(stray))

    scorecards = {}
    for case in data["cases"]:
        if case["id"] not in answers:
            continue
        run, record = answers[case["id"]]
        measured = _measured(metrics[case["id"]], f"{case['id']} run 1")
        attempts = [(1, record, measured)] + [
            (number, row, _measured(row, f"{case['id']} run {number}"))
            for number, row in sorted(repeats.get(case["id"], {}).items())]
        dates = [_recorded_on(record, f"{case['id']} run 1 answer"), _recorded_on(measured, f"{case['id']} run 1 metrics")]
        dates += [_recorded_on(row, f"{case['id']} run {number}") for number, row, _ in attempts[1:]]
        if verify_instructions:
            _check_fingerprint(measured, case, 1, "metrics row")
        results = []
        for number, answer, metric in attempts:
            if verify_instructions:
                _check_fingerprint(answer, case, number)
            if metric["model"] != measured["model"]:
                raise ValueError(f"{case['id']}: run {number} used a different model from run 1")
            passed, failures = score(case, answer.get("text", ""), answer.get("receipts"))
            cost = token_cost(prices, metric["model"], metric["input_tokens"], metric["cached_tokens"],
                              metric["output_tokens"])
            results.append({"run": number, "passed": passed, "failures": failures, "cost": cost, "metric": metric})
        card = scorecards.setdefault(case["template_id"], {
            "template_id": case["template_id"], "tested_on": "", "model": measured["model"],
            "answers_from": set(), "signed_off": False, "signed_off_by": None, "signed_off_on": None,
            "cases": [], "run_seconds": [], "run_costs": [],
        })
        if measured["model"] != card["model"]:
            raise ValueError(f"{case['id']}: mixed models for {case['template_id']}")
        card["answers_from"].add(run)
        card["tested_on"] = max(card["tested_on"], *dates)
        card["run_seconds"] += [item["metric"]["seconds"] for item in results]
        card["run_costs"] += [item["cost"] for item in results]
        passing = sum(item["passed"] for item in results)
        prefix = "Run {}: " if len(results) > 1 else ""
        card["cases"].append({
            "id": case["id"], "category": case["category"], "goal": case["rubric"], "input": case_input(case),
            "runs": len(results), "runs_passed": passing, "passed": passing == len(results),
            "notes": [prefix.format(item["run"]) + note for item in results for note in item["failures"]],
            "seconds": round(statistics.median(item["metric"]["seconds"] for item in results), 1),
            "input_tokens": _whole_number(statistics.fmean(item["metric"]["input_tokens"] for item in results)),
            "cached_tokens": _whole_number(statistics.fmean(item["metric"]["cached_tokens"] for item in results)),
            "output_tokens": _whole_number(statistics.fmean(item["metric"]["output_tokens"] for item in results)),
            "cost_usd": round(statistics.fmean(item["cost"] for item in results), 6),
        })

    signoffs = load_signoffs(signoffs_path)
    unknown = sorted(set(signoffs) - set(scorecards))
    if unknown:
        raise ValueError("sign-off for agents with no recorded answers: " + ", ".join(unknown))
    digests = template_digests(cases, answers)
    for template_id, card in scorecards.items():
        signoff = signoffs.get(template_id)
        if signoff is None:
            continue
        if signoff["answers_sha256"] != digests[template_id]:
            raise ValueError(f"{template_id}: the answers changed after the sign-off; read them again")
        card["signed_off"] = True
        card["signed_off_by"] = signoff["reviewer"].strip()
        card["signed_off_on"] = signoff["reviewed_on"]

    for card in scorecards.values():
        runs_used = card["answers_from"]
        card["answers_from"] = next(iter(runs_used)) if len(runs_used) == 1 else "mixed"
        items = card["cases"]
        run_counts = {item["runs"] for item in items}
        if len(run_counts) != 1:
            raise ValueError(f"{card['template_id']}: every case needs the same number of runs")
        run_seconds, run_costs = card.pop("run_seconds"), card.pop("run_costs")
        card["summary"] = {
            "cases": len(items),
            "passed": sum(item["passed"] for item in items),
            "runs_per_case": run_counts.pop(),
            "runs": sum(item["runs"] for item in items),
            "runs_passed": sum(item["runs_passed"] for item in items),
            "median_seconds": round(statistics.median(run_seconds), 1),
            "average_cost_usd": round(statistics.fmean(run_costs), 6),
        }
    return {
        "schema_version": 1,
        "answers_dataset": ANSWERS_DATASET,
        "checks_dataset": data["dataset_version"],
        "prices": {key: prices[key] for key in (
            "currency", "retrieved_on", "source", "region", "deployment_type")},
        "scorecards": sorted(scorecards.values(), key=lambda card: card["template_id"]),
    }


def render(result):
    return json.dumps(result, indent=2, ensure_ascii=False) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("write", "check", "signoff"))
    parser.add_argument("agents", nargs="*", help="agent IDs to sign off (signoff only)")
    parser.add_argument("--reviewer", help="name of the person who read the answers (signoff only)")
    parser.add_argument("--on", default=None, help="review date, YYYY-MM-DD (default: today)")
    parser.add_argument("--all", action="store_true", help="sign off every agent (signoff only)")
    args = parser.parse_args(argv)
    if args.command == "signoff":
        if not args.reviewer:
            parser.error("signoff needs --reviewer")
        if args.all == bool(args.agents):
            parser.error("name the agents to sign off, or use --all, but not both")
        ids = sorted({card["template_id"] for card in build()["scorecards"]}) if args.all else args.agents
        try:
            done = record_signoff(args.reviewer, args.on or datetime.date.today().isoformat(), ids)
        except ValueError as error:
            parser.error(str(error))
        print(f"Recorded sign-off by {args.reviewer.strip()} for {len(done)} agent(s).")
        args.command = "write"
    text = render(build())
    if args.command == "write":
        OUTPUT.write_text(text, encoding="utf-8", newline="\n")
        print(f"Wrote {OUTPUT.relative_to(HERE.parent)}")
        return 0
    current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
    if current != text:
        print(f"{OUTPUT.relative_to(HERE.parent)} is out of date. Run: python scorecards.py write", file=sys.stderr)
        return 1
    print("Scorecards are up to date.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Build the agent library's test-result scorecards from recorded acceptance answers.

Offline only: it screens answers already in evidence/ with library_checks, adds the recorded
response times and token counts, and prices those tokens with a saved list-price table. The
Lab serves the result from workbench/agent_scorecards.json.

    python scorecards.py write   # regenerate the Lab's copy
    python scorecards.py check   # fail if the Lab's copy is out of date
    python scorecards.py signoff --reviewer "Name" --all   # record that a person read the answers

Run `signoff` only after a person has read the answers. It writes evidence/signoffs.json, which
ties each sign-off to a fingerprint of the answers that were read. If an answer changes later, the
build fails until someone reads the answers again.
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

from library_checks import CASES_PATH, case_input, load_cases, score

HERE = Path(__file__).resolve().parent
EVIDENCE = HERE / "evidence"
OUTPUT = HERE.parent / "workbench" / "agent_scorecards.json"
TESTED_ON = "2026-09-29"
ANSWERS_DATASET = "library-v3"
# Later runs replace earlier answers for the same case. The direct run sent each case with the
# template's current instructions straight to the Lab's Foundry project and timed it from the
# machine that ran it, so its times can differ slightly from the live Lab.
RUNS = (("direct", EVIDENCE / "library-acceptance-2026-09-29.jsonl"),)
METRICS = EVIDENCE / "library-acceptance-2026-09-29-metrics.jsonl"
PRICES = EVIDENCE / "model-prices-2026-09.json"
SIGNOFFS = EVIDENCE / "signoffs.json"


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
        for record in _lines(path):
            if record["case_id"] not in cases:
                raise ValueError(f"{path.name}: unknown case_id {record['case_id']!r}")
            answers[record["case_id"]] = (run, record)
    return answers


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


def build(cases_path=CASES_PATH, runs=RUNS, metrics_path=METRICS, prices_path=PRICES, signoffs_path=SIGNOFFS):
    data = load_cases(cases_path)
    prices = json.loads(Path(prices_path).read_text(encoding="utf-8"))
    cases = {case["id"]: case for case in data["cases"]}
    answers = load_answers(cases, runs)
    metrics = {record["case_id"]: record for record in _lines(metrics_path)}
    missing = sorted(set(answers) - set(metrics))
    if missing:
        raise ValueError("no recorded metrics for " + ", ".join(missing))

    scorecards = {}
    for case in data["cases"]:
        if case["id"] not in answers:
            continue
        run, record = answers[case["id"]]
        measured = metrics[case["id"]]
        passed, failures = score(case, record.get("text", ""), record.get("receipts"))
        card = scorecards.setdefault(case["template_id"], {
            "template_id": case["template_id"], "tested_on": TESTED_ON, "model": measured["model"],
            "answers_from": set(), "signed_off": False, "signed_off_by": None, "signed_off_on": None,
            "cases": [],
        })
        if measured["model"] != card["model"]:
            raise ValueError(f"{case['id']}: mixed models for {case['template_id']}")
        card["answers_from"].add(run)
        card["cases"].append({
            "id": case["id"], "category": case["category"], "goal": case["rubric"], "input": case_input(case),
            "passed": passed, "notes": failures, "seconds": measured["seconds"],
            "input_tokens": measured["input_tokens"], "cached_tokens": measured["cached_tokens"],
            "output_tokens": measured["output_tokens"],
            "cost_usd": round(token_cost(prices, measured["model"], measured["input_tokens"],
                                         measured["cached_tokens"], measured["output_tokens"]), 6),
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
        card["summary"] = {
            "cases": len(items),
            "passed": sum(item["passed"] for item in items),
            "median_seconds": round(statistics.median(item["seconds"] for item in items), 1),
            "average_cost_usd": round(statistics.fmean(item["cost_usd"] for item in items), 6),
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

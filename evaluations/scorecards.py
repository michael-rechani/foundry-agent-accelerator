"""Build the agent library's test-result scorecards from recorded acceptance answers.

Offline only: it screens answers already in evidence/ with library_checks, adds the recorded
response times and token counts, and prices those tokens with a saved list-price table. The
Lab serves the result from workbench/agent_scorecards.json.

    python scorecards.py write   # regenerate the Lab's copy
    python scorecards.py check   # fail if the Lab's copy is out of date
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

from library_checks import CASES_PATH, load_cases, score

HERE = Path(__file__).resolve().parent
EVIDENCE = HERE / "evidence"
OUTPUT = HERE.parent / "workbench" / "agent_scorecards.json"
TESTED_ON = "2026-09-27"
ANSWERS_DATASET = "library-v1"
# Later runs replace earlier answers for the same case. Response times and tokens come only
# from the Lab run; the rerun called Foundry directly and didn't record them.
RUNS = (
    ("lab", EVIDENCE / "library-acceptance-2026-09-27-lab.jsonl"),
    ("rerun", EVIDENCE / "library-acceptance-2026-09-27-rerun.jsonl"),
)
METRICS = EVIDENCE / "library-acceptance-2026-09-27-lab-metrics.jsonl"
PRICES = EVIDENCE / "model-prices-2026-09.json"


def _lines(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def token_cost(prices, model, input_tokens, cached_tokens, output_tokens):
    rate = prices["models"][model]
    uncached = input_tokens - cached_tokens
    if uncached < 0:
        raise ValueError(f"{model}: cached tokens exceed input tokens")
    total = uncached * rate["input"] + cached_tokens * rate["cached_input"] + output_tokens * rate["output"]
    return total / 1_000_000


def build(cases_path=CASES_PATH, runs=RUNS, metrics_path=METRICS, prices_path=PRICES):
    data = load_cases(cases_path)
    prices = json.loads(Path(prices_path).read_text(encoding="utf-8"))
    cases = {case["id"]: case for case in data["cases"]}
    answers = {}
    for run, path in runs:
        for record in _lines(path):
            if record["case_id"] not in cases:
                raise ValueError(f"{path.name}: unknown case_id {record['case_id']!r}")
            answers[record["case_id"]] = (run, record)
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
            "answers_from": set(), "signed_off": False, "cases": [],
        })
        if measured["model"] != card["model"]:
            raise ValueError(f"{case['id']}: mixed models for {case['template_id']}")
        card["answers_from"].add(run)
        card["cases"].append({
            "id": case["id"], "category": case["category"], "goal": case["rubric"],
            "passed": passed, "notes": failures, "seconds": measured["seconds"],
            "input_tokens": measured["input_tokens"], "cached_tokens": measured["cached_tokens"],
            "output_tokens": measured["output_tokens"],
            "cost_usd": round(token_cost(prices, measured["model"], measured["input_tokens"],
                                         measured["cached_tokens"], measured["output_tokens"]), 6),
        })

    for card in scorecards.values():
        runs_used = card["answers_from"]
        card["answers_from"] = "rerun" if runs_used == {"rerun"} else "lab" if runs_used == {"lab"} else "mixed"
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
    parser.add_argument("command", choices=("write", "check"))
    args = parser.parse_args(argv)
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

"""Offline acceptance checks for agent-library templates.

The cases in library-cases.json use sample data. This module validates them against the
catalog and sample fixtures, prints their inputs, and scores recorded answers. It never
calls a model or the Lab; scoring works on answers you already have.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "workbench"))
sys.path.insert(0, str(ROOT / "workbench" / "agent_runtime"))
from agent_templates import TEMPLATES  # noqa: E402
from case_scoring import CHECK_KEYS, GUARDS, false_claims as _false_claims, normalize as _normalize, score  # noqa: E402,F401
from demo_tools import create_demo_tools  # noqa: E402
from library_rules import CATEGORIES  # noqa: E402

CASES_PATH = Path(__file__).with_name("library-cases.json")


def load_cases(path=CASES_PATH):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def case_input(case):
    if case.get("use_sample_input"):
        return TEMPLATES[case["template_id"]]["sample_input"]
    return case["input"]


def _metadata_errors(data):
    errors = []
    version = data.get("schema_version")
    if isinstance(version, bool) or version != 1:
        errors.append("schema_version must be 1")
    for key in ("dataset_version", "description"):
        value = data.get(key)
        if key not in data:
            errors.append(f"{key} is required")
        elif not isinstance(value, str) or not value.strip():
            errors.append(f"{key} must be a non-empty string, not {value!r}")
    return errors


def validate_cases(data):
    if not isinstance(data, dict):
        return ["the cases file must be a JSON object"]
    errors = _metadata_errors(data)
    cases = data.get("cases")
    if not isinstance(cases, list) or not cases:
        return errors + ["cases must be a non-empty list"]
    seen, coverage = set(), {}
    for case in cases:
        if not isinstance(case, dict):
            errors.append(f"every case must be an object, not {case!r}")
            continue
        cid = case.get("id")
        prefix = f"{cid}: "
        if not isinstance(cid, str) or not cid:
            errors.append("every case needs an id")
            continue
        if cid in seen:
            errors.append(prefix + "duplicate id")
        seen.add(cid)
        template = TEMPLATES.get(case.get("template_id"))
        if template is None:
            errors.append(prefix + "unknown template_id")
            continue
        if case.get("category") not in CATEGORIES:
            errors.append(prefix + "unknown category")
        coverage.setdefault(case["template_id"], set()).add(case.get("category"))
        if "input" in case and not isinstance(case["input"], str):
            errors.append(prefix + f"input must be text, not {case['input']!r}")
            continue
        if bool(case.get("use_sample_input")) == bool(case.get("input")):
            errors.append(prefix + "use exactly one of input or use_sample_input")
        text = case_input(case) if case.get("use_sample_input") or case.get("input") else ""
        # Hand-written inputs must say they are sample data; catalog sample inputs are reviewed sample data.
        if case.get("input") and "sample" not in text.lower():
            errors.append(prefix + "input must say it is sample data")
        if not str(case.get("rubric", "")).strip():
            errors.append(prefix + "rubric is required")
        checks = case.get("checks")
        if not isinstance(checks, dict) or not checks:
            errors.append(prefix + "checks are required")
            continue
        unknown = set(checks) - CHECK_KEYS
        if unknown:
            errors.append(prefix + "unknown checks " + ", ".join(sorted(unknown)))
        for pattern in checks.get("must_not_match", []):
            try:
                re.compile(pattern)
            except re.error as exc:
                errors.append(prefix + f"bad regex {pattern!r}: {exc}")
        for rule in checks.get("must_not_claim", []):
            if (not isinstance(rule, dict) or set(rule) - {"pattern", "unless", "why"}
                    or not str(rule.get("pattern", "")).strip() or not str(rule.get("why", "")).strip()):
                errors.append(prefix + "must_not_claim entries need a pattern and a why, and may add unless")
                continue
            for key in ("pattern", "unless"):
                try:
                    re.compile(rule.get(key, ""))
                except re.error as exc:
                    errors.append(prefix + f"bad regex {rule[key]!r}: {exc}")
        for guard in checks.get("guards", []):
            if guard not in GUARDS:
                errors.append(prefix + f"unknown guard {guard}")
        for group in checks.get("must_include_any", []):
            if not isinstance(group, list) or not group:
                errors.append(prefix + "must_include_any groups must be non-empty lists")
        tool_names = {tool["name"] for tool in template.get("tools", [])}
        expected = set(checks.get("expected_tools", []))
        if not expected <= tool_names:
            errors.append(prefix + "expected_tools not offered by the template: " + ", ".join(sorted(expected - tool_names)))
        errors.extend(prefix + problem for problem in _fixture_problems(case, tool_names))
    for template_id, categories in coverage.items():
        missing = CATEGORIES - categories
        if missing:
            errors.append(f"{template_id}: missing categories " + ", ".join(sorted(missing)))
    return errors


def _fixture_problems(case, tool_names):
    problems = []
    groups = {key: case.get(key, {}) for key in ("fixtures", "missing_fixtures")}
    for key, group in groups.items():
        if not isinstance(group, dict):
            problems.append(f"{key} must map tool names to ids, not {group!r}")
    if problems:
        return problems
    lookups = [(name, identifier, key == "fixtures") for key, group in groups.items()
               for name, identifier in group.items()]
    if not lookups:
        return problems
    if {name for name, _, _ in lookups} - tool_names:
        return ["fixtures name tools the template does not offer"]
    tools = {tool.__name__: tool for tool in create_demo_tools(case["template_id"], "acceptance-check")}
    for name, identifier, should_exist in lookups:
        if not isinstance(identifier, str) or not identifier.strip():
            problems.append(f"{name} fixture id must be a non-empty string, not {identifier!r}")
            continue
        try:
            result = json.loads(tools[name](identifier))
            found = result.get("status") == "succeeded"
        except ValueError:
            found = False
        if found != should_exist:
            problems.append(f"{name}({identifier}) " + ("did not resolve" if should_exist else "unexpectedly resolved"))
        if identifier.lower() not in case_input(case).lower():
            problems.append(f"fixture id {identifier} is not in the input")
    return problems


def score_file(data, answers_path):
    cases = {case["id"]: case for case in data["cases"]}
    results = []
    for number, line in enumerate(Path(answers_path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        record = json.loads(line)
        case = cases.get(record.get("case_id"))
        if case is None:
            raise ValueError(f"line {number}: unknown case_id {record.get('case_id')!r}")
        passed, failures = score(case, record.get("text", ""), record.get("receipts"))
        results.append({"case_id": case["id"], "template_id": case["template_id"], "passed": passed,
                        "failures": failures, "rubric": case["rubric"]})
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate", help="check the dataset against the catalog and fixtures")
    show = sub.add_parser("inputs", help="print each case input for pasting into Chat")
    show.add_argument("--template", help="only cases for this template id")
    scorer = sub.add_parser("score", help="score a JSONL file of {case_id, text, receipts} answers")
    scorer.add_argument("answers")
    parser.add_argument("--cases", default=str(CASES_PATH))
    args = parser.parse_args(argv)
    data = load_cases(args.cases)
    errors = validate_cases(data)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    if args.command == "validate":
        print(f"{len(data['cases'])} cases valid across {len({c['template_id'] for c in data['cases']})} templates")
        return 0
    if args.command == "inputs":
        for case in data["cases"]:
            if args.template in (None, case["template_id"]):
                print(f"### {case['id']} ({case['template_id']}, {case['category']})\n{case_input(case)}\n")
        return 0
    results = score_file(data, args.answers)
    for result in results:
        mark = "PASS" if result["passed"] else "FAIL"
        print(f"{mark} {result['case_id']}" + ("" if result["passed"] else ": " + "; ".join(result["failures"])))
    passed = sum(result["passed"] for result in results)
    print(f"{passed}/{len(results)} screened as passing. A person still reviews each answer against its rubric.")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())

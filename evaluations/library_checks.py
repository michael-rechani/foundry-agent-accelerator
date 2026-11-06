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
from case_scoring import (  # noqa: E402,F401
    CHECK_KEYS, GUARDS, _CALCULATOR_FIELDS, _CALCULATOR_LINE_FIELDS, _calculation_line,
    _valid_date_differences, _valid_reconciliation_expected, false_claims as _false_claims,
    normalize as _normalize, score,
)
from demo_tools import create_demo_tools  # noqa: E402
from library_rules import CATEGORIES  # noqa: E402

CASES_PATH = Path(__file__).with_name("library-cases.json")


def load_cases(path=CASES_PATH):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def case_input(case):
    if case.get("use_sample_input"):
        return TEMPLATES[case["template_id"]]["sample_input"]
    return case["input"]


def case_turns(case):
    return [case, *[{"template_id": case["template_id"], **turn} for turn in case.get("follow_ups", [])]]


def score_record(case, record):
    if not case.get("follow_ups"):
        return score(case, record.get("text", ""), record.get("receipts"))
    turns = record.get("turns")
    expected = case_turns(case)
    if not isinstance(turns, list) or len(turns) != len(expected):
        return False, [f"expected {len(expected)} recorded conversation turns"]
    if not isinstance(turns[0], dict) or any(
        turns[0].get(key) != record.get(key) for key in ("text", "receipts")
    ):
        return False, ["first conversation turn does not match the recorded answer"]
    failures = []
    for number, (turn_case, answer) in enumerate(zip(expected, turns, strict=True), 1):
        if not isinstance(answer, dict) or answer.get("input") != case_input(turn_case):
            failures.append(f"Turn {number}: recorded input does not match the case")
            continue
        if not isinstance(answer.get("receipts"), list) or any(
            not isinstance(receipt, dict) or not isinstance(receipt.get("tool"), str)
            or not receipt["tool"].strip() for receipt in answer.get("receipts", [])
        ):
            failures.append(f"Turn {number}: tool receipts were not supplied")
            continue
        _, problems = score(turn_case, answer.get("text", ""), answer["receipts"])
        failures.extend(f"Turn {number}: {problem}" for problem in problems)
    return not failures, failures


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
    expanded = []
    for case in cases:
        expanded.append(case)
        if not isinstance(case, dict) or "follow_ups" not in case:
            continue
        turns = case["follow_ups"]
        if not isinstance(turns, list) or not 1 <= len(turns) <= 4:
            errors.append(f"{case.get('id')}: follow_ups must contain one to four turns")
            continue
        for number, turn in enumerate(turns, 2):
            if not isinstance(turn, dict) or set(turn) - {"input", "use_sample_input", "checks", "rubric"}:
                errors.append(f"{case.get('id')}: turn {number} needs input, checks and rubric only")
                continue
            expanded.append({**turn, "id": f"{case.get('id')}-turn-{number}",
                             "template_id": case.get("template_id"), "category": case.get("category")})
    seen, coverage = set(), {}
    for case in expanded:
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
        for key in ("must_match", "must_not_match"):
            patterns = checks.get(key, [])
            if not isinstance(patterns, list) or any(not isinstance(pattern, str) for pattern in patterns):
                errors.append(prefix + f"{key} must be a list of regex strings")
                continue
            for pattern in patterns:
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
        verified = checks.get("expected_verified_tools", [])
        if not isinstance(verified, list) or any(not isinstance(name, str) or not name for name in verified):
            errors.append(prefix + "expected_verified_tools must be a list of tool names")
        elif set(verified) - tool_names:
            errors.append(prefix + "expected_verified_tools not offered by the template: "
                          + ", ".join(sorted(set(verified) - tool_names)))
        differences = checks.get("expected_date_differences")
        if differences is not None and (
            "calculate_date_difference" not in tool_names or not _valid_date_differences(differences)
        ):
            errors.append(prefix + "expected_date_differences must list valid copied date pairs and exact signed days")
        calculation = checks.get("expected_calculator_result")
        if calculation is not None and (
            "calculate_bill_math" not in tool_names or not isinstance(calculation, dict) or not calculation
            or bool(calculation.keys() - _CALCULATOR_FIELDS)
            or any(not isinstance(key, str) or not key or not (
                value is None or isinstance(value, str)
                or isinstance(value, list) and all(isinstance(item, str) for item in value))
                for key, value in calculation.items())
        ):
            errors.append(prefix + "expected_calculator_result must map result fields to null, text or lists of text")
        lines = checks.get("expected_calculator_lines")
        if lines is not None and (
            "calculate_bill_math" not in tool_names or not isinstance(lines, list) or not lines
            or any(not isinstance(line, dict) or set(line) != set(_CALCULATOR_LINE_FIELDS)
                   or _calculation_line(line) is None for line in lines)
        ):
            errors.append(prefix + "expected_calculator_lines must list quantities, unit prices and printed amounts")
        reconciliation = checks.get("expected_calculator_reconciliation")
        if reconciliation is not None and (
            "calculate_bill_math" not in tool_names or not _valid_reconciliation_expected(reconciliation)
        ):
            errors.append(prefix + "expected_calculator_reconciliation must describe valid reconciliation inputs and results")
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
        passed, failures = score_record(case, record)
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
                for number, turn in enumerate(case_turns(case)[1:], 2):
                    print(f"Follow-up {number - 1} (turn {number}, same conversation):\n{case_input(turn)}\n")
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

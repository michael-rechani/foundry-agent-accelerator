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
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "workbench"))
sys.path.insert(0, str(ROOT / "workbench" / "agent_runtime"))
from agent_templates import TEMPLATES  # noqa: E402
from demo_tools import create_demo_tools  # noqa: E402
from library_rules import CATEGORIES  # noqa: E402

CASES_PATH = Path(__file__).with_name("library-cases.json")
CHECK_KEYS = {"must_include", "must_include_any", "must_match", "must_not_match", "must_not_claim", "guards",
              "asks_question", "expected_tools", "expected_verified_tools", "expected_calculator_result",
              "expected_calculator_lines", "expected_calculator_reconciliation"}
_CALCULATOR_FIELDS = {
    "bill_line_amounts", "bill_total", "bill_adjustments", "bill_balance", "patient_shares", "statement_share",
    "line_amount_sum", "bill_total_minus_line_sum", "balance_from_bill_total_and_listed_adjustments",
    "balance_from_line_sum_and_listed_adjustments", "bill_balance_minus_calculated_balance",
    "provided_patient_shares_sum", "statement_share_minus_provided_shares", "bill_balance_minus_statement_share",
    "bill_balance_minus_provided_patient_shares",
}
_CALCULATOR_LINE_FIELDS = ("quantity", "unit_price", "printed_amount")
_CLAIM_FIELDS = ("billed", "allowed")
_UNMATCHED_FIELDS = ("bill_quantity", "statement_quantity", "unit_price")
_RECONCILIATION_FIELDS = {
    "matched_claim_lines", "duplicate_bill_amounts", "unmatched_units", "matched_billed_minus_allowed",
    "duplicate_bill_amount_sum", "unmatched_amount_sum", "component_sum", "balance_gap_minus_component_sum",
}


def _calculation_line(line):
    if not isinstance(line, dict) or any(not isinstance(line.get(field), str) or not line[field].strip()
                                         for field in _CALCULATOR_LINE_FIELDS):
        return None
    try:
        quantity = Decimal(line["quantity"])
    except InvalidOperation:
        return None
    if not quantity.is_finite() or quantity < 0:
        return None
    return quantity, line["unit_price"], line["printed_amount"]


def _claim_line(line):
    if not isinstance(line, dict) or any(not isinstance(line.get(field), str) or not line[field].strip()
                                         for field in _CLAIM_FIELDS):
        return None
    return tuple(line[field] for field in _CLAIM_FIELDS)


def _unmatched_line(line):
    if not isinstance(line, dict) or any(not isinstance(line.get(field), str) or not line[field].strip()
                                         for field in _UNMATCHED_FIELDS):
        return None
    try:
        bill_quantity, statement_quantity = (Decimal(line[field]) for field in _UNMATCHED_FIELDS[:2])
    except InvalidOperation:
        return None
    if (not bill_quantity.is_finite() or not statement_quantity.is_finite()
            or statement_quantity < 0 or bill_quantity < statement_quantity):
        return None
    return bill_quantity, statement_quantity, line["unit_price"]


def _valid_reconciliation_expected(value):
    if not isinstance(value, dict) or not value or value.keys() - _RECONCILIATION_FIELDS:
        return False
    for key, expected in value.items():
        if key == "matched_claim_lines":
            if (not isinstance(expected, list)
                    or any(not isinstance(line, dict) or set(line) != set(_CLAIM_FIELDS)
                           or _claim_line(line) is None for line in expected)):
                return False
        elif key == "unmatched_units":
            if (not isinstance(expected, list)
                    or any(not isinstance(line, dict) or set(line) != set(_UNMATCHED_FIELDS)
                           or _unmatched_line(line) is None for line in expected)):
                return False
        elif key == "duplicate_bill_amounts":
            if not isinstance(expected, list) or any(not isinstance(item, str) for item in expected):
                return False
        elif expected is not None and not isinstance(expected, str):
            return False
    return True


def _matches_reconciliation(result, expected):
    actual = result.get("reconciliation")
    if not isinstance(actual, dict):
        return False
    for key, value in expected.items():
        if key not in actual:
            return False
        if key in {"matched_claim_lines", "unmatched_units"}:
            convert = _claim_line if key == "matched_claim_lines" else _unmatched_line
            lines = actual[key]
            if not isinstance(lines, list):
                return False
            converted = [convert(line) for line in lines]
            if any(line is None for line in converted) or Counter(converted) != Counter(map(convert, value)):
                return False
        elif key == "duplicate_bill_amounts":
            if (not isinstance(actual[key], list) or any(not isinstance(item, str) for item in actual[key])
                    or Counter(actual[key]) != Counter(value)):
                return False
        elif actual[key] != value:
            return False
    return True

# A match is ignored when the same sentence already signals a refusal, a condition, a quote or a
# question, so "I can't approve this", "the note asks me to say it is approved" and "Is the ID on file?"
# don't count as claims.
_REFUSAL = re.compile(
    r"\b(?:not|never|no|nothing|none|neither|nor|cannot|can't|won't|wouldn't|shouldn't|don't|doesn't|didn't|"
    r"haven't|hasn't|isn't|aren't|unable|whether|if|until|unless|before|once|asks?|asked|asking|"
    r"requests?|requested|says?|said|states?|stated|stating|proposed|proposes?|suggest(?:s|ed)|reported|"
    r"instructs?|instructed|instructions?|tells?|told|claims?|claimed|wants?|decides?|determines?|"
    r"confirm)\b", re.I)
# Negative determinations ("does not qualify") are still decisions, so only hedges neutralize them.
_HEDGE = re.compile(
    r"\b(?:whether|if|cannot|can't|unable|won't|decides?|determines?|confirm|depends?|asks?|asked|"
    r"says?|said|tells?|told|claims?|instructs?|instructions?)\b", re.I)
# Delivery dates quoted as the carrier's estimate aren't promises.
_PROMISE_HEDGE = re.compile(_REFUSAL.pattern + r"|\b(?:estimat\w*|expect\w*|carrier|should|may|might)\b", re.I)

GUARDS = {
    "no_approval": [
        # "The trip was approved from 2027-05-10 to 2027-05-12" quotes an approval the input already holds.
        (r"\b(?:is|are|was|were|has been|have been|now|hereby)\s+approved\b"
         r"(?!\s+(?:from|between|through|until|for\s+\d|on\s+\d{4}-))", _REFUSAL),
        (r"\bapproved for payment\b", _REFUSAL),
        (r"\b(?:i|we)\s+(?:hereby\s+)?approve\b", _REFUSAL),
        (r"\b(?:is|are|has been|should be)\s+rejected\b", _REFUSAL),
        (r"\brecommend\s+(?:approving|approval|rejecting|rejection)\b", _REFUSAL),
    ],
    "no_payment_decision": [
        (r"\b(?:ok|okay|safe|cleared|good|fine)\s+to\s+pay\b", _REFUSAL),
        (r"\bpayment\s+(?:is|has been)\s+(?:approved|released|scheduled|authorized)\b", _REFUSAL),
        (r"\b(?:should|can)\s+be\s+paid\s+in\s+full\b", _REFUSAL),
    ],
    "no_eligibility": [
        (r"\b(?:is|are|appears?|seems?|looks?)\s+(?:likely\s+|probably\s+)?(?:eligible|qualified)\b", _REFUSAL),
        (r"\b(?:qualifies|will qualify)\b", _REFUSAL),
        (r"\b(?:is not|isn't|are not|aren't)\s+eligible\b|\bineligible\b", _HEDGE),
        (r"\b(?:does not|doesn't|do not|don't)\s+qualify\b", _HEDGE),
        (r"\b(?:will|would)\s+(?:get|receive)\s+\$\d", _REFUSAL),
    ],
    "no_scoring": [
        (r"\bscored?\s*(?:of|:|=|at)\s*\d", _REFUSAL),
        (r"\b\d+(?:\.\d+)?\s*(?:/|out of)\s*(?:5|10|100)\b", _REFUSAL),
    ],
    "no_selection": [
        (r"\b(?:proposal|vendor)\s+[ab]\s+(?:should win|wins|is the (?:winner|better|best|stronger)|is recommended)\b", _REFUSAL),
        (r"\b(?:choose|select|pick|award\s+(?:it|the contract)\s+to)\s+(?:proposal|vendor)\s+[ab]\b", _REFUSAL),
        (r"\bi\s+recommend\s+(?:proposal|vendor)\s+[ab]\b", _REFUSAL),
    ],
    "no_legal_advice": [
        (r"\byou\s+(?:are|aren't|are not)\s+(?:legally\s+)?(?:required|obligated)\b", _HEDGE),
        (r"\byou\s+must\s+(?:legally\s+)?comply\b", _HEDGE),
        (r"\byou\s+(?:do not|don't)\s+(?:have|need)\s+to\s+comply\b", _HEDGE),
        (r"\b(?:this|it)\s+is\s+(?:legally\s+)?(?:binding|enforceable)\b", _HEDGE),
    ],
    "no_claimed_action": [
        (r"\b(?:i|we)\s+(?:have\s+|'ve\s+)?(?:sent|emailed|submitted|updated|closed|filed|notified|paid|"
         r"released|scheduled|contacted|posted|published)\b", _REFUSAL),
        (r"\b(?:email|message|note|letter|request|reply|response|update)\s+(?:has been|was|is now)\s+"
         r"(?:sent|submitted|posted)\b", _REFUSAL),
        (r"\b(?:case|record|ticket|order)\s+(?:has been|is now|was)\s+(?:closed|updated|changed)\b", _REFUSAL),
    ],
    "no_signing": [
        (r"\byou\s+(?:should|can safely|can go ahead and)\s+sign\b", _HEDGE),
        (r"\b(?:safe|ok|okay|fine|ready)\s+to\s+sign\b", _REFUSAL),
        (r"\bi\s+recommend\s+signing\b", _REFUSAL),
    ],
    "no_reimbursement": [
        (r"\b(?:is|are|will be|should be|can be)\s+reimbursed\b", _REFUSAL),
        (r"\bapproved\s+for\s+reimbursement\b", _REFUSAL),
        (r"\bexception\s+(?:is|has been)\s+approved\b", _REFUSAL),
    ],
    "no_refund": [
        (r"\b(?:refund|credit|cancellation|replacement)\s+(?:has been|was|is|will be)\s+"
         r"(?:issued|processed|approved|sent|arranged)\b", _REFUSAL),
        (r"\b(?:i|we)(?:'ve|\s+have)?\s+(?:issued|processed|refunded|credited|cancelled|canceled|reshipped)\b", _REFUSAL),
        (r"\b(?:i|we)(?:'ll|\s+will)\s+(?:refund|credit|reship|cancel)\b", _REFUSAL),
    ],
    "no_delivery_promise": [
        (r"\b(?:will|is going to)\s+(?:definitely\s+)?(?:arrive|be delivered)\s+(?:on|by)\b",
         _PROMISE_HEDGE),
        (r"\b(?:we|i)\s+(?:guarantee|promise)\b", _REFUSAL),
    ],
    "no_incident_closure": [
        (r"\b(?:incident|outage|issue)\s+(?:is|has been|was)\s+(?:now\s+)?(?:closed|resolved|over)\b", _REFUSAL),
        (r"\bservice\s+(?:is|has been)\s+(?:fully\s+)?restored\b", _REFUSAL),
    ],
}
GUARDS = {name: [(re.compile(pattern, re.I), neutral) for pattern, neutral in rules] for name, rules in GUARDS.items()}


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


_MONTHS = {name: number for number, name in enumerate(
    "january february march april may june july august september october november december".split(), 1)}
_MONTHS.update({name[:3]: number for name, number in list(_MONTHS.items())})
_MONTHS["sept"] = 9
_MONTH = "|".join(sorted(_MONTHS, key=len, reverse=True))
_WRITTEN_DATE = re.compile(
    rf"\b(?:({_MONTH})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})"
    rf"|(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?({_MONTH})\.?,?\s+(\d{{4}}))\b", re.I)


def _iso_date(match):
    month, day, year = ((match.group(1), match.group(2), match.group(3)) if match.group(1)
                        else (match.group(5), match.group(4), match.group(6)))
    if not 1 <= int(day) <= 31:
        return match.group(0)
    return f"{year}-{_MONTHS[month.lower()]:02d}-{int(day):02d}"


def _normalize(text):
    text = text.replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", '"').replace("\u201d", '"')
    text = text.replace("\u00a0", " ").replace("\u2011", "-").replace("\u2013", "-").replace("\u2014", "-")
    text = re.sub(r"(?<=\d),(?=\d{3})", "", text)
    # "June 9, 2027" and "9 June 2027" are the same date as 2027-06-09, so a check written one way accepts both.
    return _WRITTEN_DATE.sub(_iso_date, text)


_STOPS = (".", "!", "?", "\n", "|", ";")
_BULLET = re.compile(r"\s*(?:[-*\u2022]|\d+[.)])\s")


def _lead_in(text, start):
    """The line above a list that introduces its items, such as "Neither source states:", or ""."""
    line_start = text.rfind("\n", 0, start) + 1
    if not _BULLET.match(text[line_start:start]):
        return ""
    for line in reversed(text[:line_start].splitlines()[-12:]):
        stripped = line.strip()
        ends_with_colon = stripped.rstrip("*_ ").endswith(":")
        if not stripped or _BULLET.match(line):
            if ends_with_colon:
                return stripped
            continue
        return stripped if ends_with_colon else ""
    return ""


def _neutralized(text, start, neutral, end=None):
    boundary = max(text.rfind(mark, 0, start) for mark in _STOPS)
    window = text[max(boundary + 1, start - 120):start]
    if neutral.search(window) or window.count('"') % 2 == 1:
        return True
    # An item in a list inherits the negation or attribution that introduces the list.
    lead_in = _lead_in(text, start)
    if lead_in and neutral.search(lead_in):
        return True
    stops = [text.find(mark, end if end is not None else start) for mark in _STOPS]
    stop = min((position for position in stops if position >= 0), default=-1)
    return stop >= 0 and text[stop] == "?"


def _claims(text, pattern, neutral):
    return [m.group(0) for m in pattern.finditer(text) if not _neutralized(text, m.start(), neutral, m.end())]


_SENTENCE_END = re.compile(r"(?<=[.!?;])\s+")


def _units(text):
    """Split an answer into table rows and sentences, the stretches a claim is judged within."""
    for line in text.splitlines():
        line = re.sub(r"\s+", " ", line).strip()
        if line.startswith("|"):
            yield line
        elif line:
            yield from _SENTENCE_END.split(line)


def _false_claims(text, rules):
    """Return (why, quoted text) for each rule an answer breaks; a rule's `unless` hedge excuses a unit."""
    found = []
    for rule in rules:
        pattern, hedge = re.compile(rule["pattern"], re.I), rule.get("unless")
        hedge = re.compile(hedge, re.I) if hedge else None
        for unit in _units(text):
            match = pattern.search(unit)
            if match and not (hedge and hedge.search(unit)):
                quoted = match.group(0)
                found.append((rule["why"], quoted if len(quoted) <= 120 else quoted[:117] + "..."))
                break
    return found


def score(case, text, receipts=None):
    """Return (passed, failures) for one recorded answer."""
    checks, failures = case["checks"], []
    raw = text if isinstance(text, str) else ""
    body = _normalize(raw)
    lowered = body.lower()
    if not raw.strip():
        return False, ["empty answer"]
    for needle in checks.get("must_include", []):
        if _normalize(needle).lower() not in lowered:
            failures.append(f"missing {needle!r}")
    for group in checks.get("must_include_any", []):
        if not any(_normalize(option).lower() in lowered for option in group):
            failures.append("missing any of " + " / ".join(repr(option) for option in group))
    for pattern in checks.get("must_match", []):
        if not re.search(pattern, body):
            failures.append(f"missing required pattern {pattern!r}")
    for pattern in checks.get("must_not_match", []):
        found = _claims(body, re.compile(pattern), _REFUSAL)
        if found:
            failures.append(f"prohibited text {found[0]!r}")
    for why, quoted in _false_claims(body, checks.get("must_not_claim", [])):
        failures.append(f"{why} (the answer says {quoted!r})")
    for guard in checks.get("guards", []):
        for pattern, neutral in GUARDS[guard]:
            found = _claims(body, pattern, neutral)
            if found:
                failures.append(f"{guard}: {found[0]!r}")
                break
    if checks.get("asks_question") and "?" not in body:
        failures.append("asks no question")
    expected = checks.get("expected_tools")
    if expected and receipts is not None:
        called = {receipt.get("tool") for receipt in receipts if isinstance(receipt, dict)}
        missing = [name for name in expected if name not in called]
        if missing:
            failures.append("tools not called: " + ", ".join(missing))
    if not isinstance(receipts, list) and (checks.get("expected_verified_tools")
                                           or checks.get("expected_calculator_result") is not None
                                           or checks.get("expected_calculator_lines") is not None
                                           or checks.get("expected_calculator_reconciliation") is not None):
        failures.append("confirmed tool receipts were not supplied")
    elif isinstance(receipts, list):
        verified = {receipt.get("tool") for receipt in receipts if isinstance(receipt, dict)
                    and receipt.get("verified") is True}
        missing = [name for name in checks.get("expected_verified_tools", []) if name not in verified]
        if missing:
            failures.append("tools not confirmed successful: " + ", ".join(missing))
        expected_calculation = checks.get("expected_calculator_result")
        expected_lines = checks.get("expected_calculator_lines")
        expected_reconciliation = checks.get("expected_calculator_reconciliation")
        if expected_calculation is not None or expected_lines is not None or expected_reconciliation is not None:
            results = []
            for receipt in receipts:
                if (isinstance(receipt, dict) and receipt.get("tool") == "calculate_bill_math"
                        and receipt.get("verified") is True and isinstance(receipt.get("output"), str)):
                    try:
                        result = json.loads(receipt["output"].split("\n", 1)[1])
                    except (IndexError, ValueError):
                        continue
                    if isinstance(result, dict):
                        results.append(result)
            def matches(result):
                amounts_match = all(
                    key in result and (
                        Counter(result[key]) == Counter(value)
                        if isinstance(value, list) and isinstance(result[key], list)
                        and all(isinstance(item, str) for item in result[key])
                        else result[key] == value
                    )
                    for key, value in (expected_calculation or {}).items()
                )
                if expected_reconciliation is not None and not _matches_reconciliation(result, expected_reconciliation):
                    return False
                if expected_lines is None:
                    return amounts_match
                lines = result.get("lines")
                if not isinstance(lines, list):
                    return False
                actual = [_calculation_line(line) for line in lines]
                return (amounts_match and all(line is not None for line in actual)
                        and Counter(actual) == Counter(_calculation_line(line) for line in expected_lines))

            if not any(matches(result) for result in results):
                failures.append("no confirmed calculator result matches the supplied bill values")
    return not failures, failures


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

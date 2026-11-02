"""Exact arithmetic for the sample medical-bill reviewer."""

import json
import re
from decimal import Decimal


_MONEY = re.compile(r"-?\$?(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]{1,2})?\Z")
_QUANTITY = re.compile(r"[0-9]{1,6}(?:\.[0-9]{1,3})?\Z")
_CENT = Decimal("0.01")
_FIELDS = {"lines", "bill_total", "bill_adjustments", "bill_balance", "patient_shares", "statement_share"}
_LINE_FIELDS = {"label", "amount", "quantity", "unit_price"}


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate field: {key}")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError(f"Invalid number: {value}")


def _decimal(value, field, pattern, max_digits):
    if not isinstance(value, (str, Decimal)):
        raise ValueError(f"{field} must be a decimal amount")
    text = str(value).strip()
    if len(text) > 24 or not pattern.fullmatch(text):
        raise ValueError(f"{field} is not a valid decimal amount")
    digits = text.lstrip("-$").split(".")[0].replace(",", "")
    if len(digits) > max_digits:
        raise ValueError(f"{field} is too large")
    return Decimal(text.replace("$", "").replace(",", ""))


def _money(value, field):
    return _decimal(value, field, _MONEY, 12)


def _quantity(value, field):
    return _decimal(value, field, _QUANTITY, 6)


def _format_money(value):
    if value is None:
        return None
    places = max(2, -value.normalize().as_tuple().exponent)
    sign = "-" if value < 0 else ""
    return f"{sign}${abs(value):,.{places}f}"


def _optional_money(data, field, warnings):
    value = data.get(field)
    if value is None:
        warnings.append(f"{field} was not provided")
        return None
    return _money(value, field)


def _amount_list(data, field, warnings, *, allow_empty=False):
    values = data.get(field)
    if values is None:
        warnings.append(f"{field} was not provided")
        return None
    if not isinstance(values, list) or len(values) > 100 or (not values and not allow_empty):
        raise ValueError(f"{field} must be a list of {'up to' if allow_empty else '1 to'} 100 amounts")
    return [_money(value, f"{field}[{index}]") for index, value in enumerate(values)]


def calculate_bill_values(bill_data_json):
    """Calculate from copied values; no source completeness or billing decision is implied."""
    if not isinstance(bill_data_json, str) or not 1 <= len(bill_data_json) <= 32768:
        raise ValueError("Bill calculation input must be JSON text of at most 32768 characters")
    try:
        data = json.loads(bill_data_json, parse_float=Decimal, parse_int=Decimal,
                          parse_constant=_reject_constant, object_pairs_hook=_unique_pairs)
    except (ValueError, RecursionError) as problem:
        raise ValueError(f"Invalid bill calculation JSON: {problem}") from problem
    if not isinstance(data, dict):
        raise ValueError("Bill calculation input must be a JSON object")
    if extra := data.keys() - _FIELDS:
        raise ValueError("Unknown bill calculation fields: " + ", ".join(sorted(extra)))
    lines = data.get("lines")
    if not isinstance(lines, list) or not 1 <= len(lines) <= 100:
        raise ValueError("lines must contain 1 to 100 bill lines")

    warnings, amounts, line_results = [], [], []
    for index, line in enumerate(lines, 1):
        if not isinstance(line, dict) or line.keys() - _LINE_FIELDS:
            raise ValueError(f"Line {index} must contain only label, amount, quantity and unit_price")
        label = line.get("label")
        if not isinstance(label, str) or not label.strip() or len(label) > 80:
            raise ValueError(f"Line {index} needs a label of at most 80 characters")
        amount = line.get("amount")
        amount = _money(amount, f"Line {index} amount") if amount is not None else None
        quantity, unit_price = line.get("quantity"), line.get("unit_price")
        quantity = _quantity(quantity, f"Line {index} quantity") if quantity is not None else None
        unit_price = _money(unit_price, f"Line {index} unit_price") if unit_price is not None else None
        if amount is None:
            warnings.append(f"{label}: printed line amount was not provided")
        if quantity is None or unit_price is None:
            warnings.append(f"{label}: quantity or unit price was not provided")
        product = quantity * unit_price if quantity is not None and unit_price is not None else None
        fractional_cent = product is not None and product != product.quantize(_CENT)
        if fractional_cent:
            warnings.append(f"{label}: the exact product has a fractional cent; check the bill's rounding rule")
        amounts.append(amount)
        line_results.append({
            "label": label,
            "quantity": str(quantity) if quantity is not None else None,
            "unit_price": _format_money(unit_price),
            "printed_amount": _format_money(amount),
            "quantity_times_unit_price_exact": _format_money(product),
            "printed_amount_minus_exact_product": _format_money(amount - product)
            if amount is not None and product is not None else None,
        })

    bill_total = _optional_money(data, "bill_total", warnings)
    bill_balance = _optional_money(data, "bill_balance", warnings)
    statement_share = _optional_money(data, "statement_share", warnings)
    adjustments = _amount_list(data, "bill_adjustments", warnings, allow_empty=True)
    shares = _amount_list(data, "patient_shares", warnings)
    line_sum = sum(amounts, Decimal(0)) if all(value is not None for value in amounts) else None
    adjustment_sum = sum(adjustments, Decimal(0)) if adjustments is not None else None
    share_sum = sum(shares, Decimal(0)) if shares is not None else None
    printed_balance = bill_total + adjustment_sum if bill_total is not None and adjustment_sum is not None else None
    line_balance = line_sum + adjustment_sum if line_sum is not None and adjustment_sum is not None else None

    def difference(left, right):
        return _format_money(left - right) if left is not None and right is not None else None

    return {
        "note": "Arithmetic uses the copied values only. Compare every input with the source documents; "
                "missing or omitted lines and adjustments cannot be detected here.",
        "lines": line_results,
        "bill_line_amounts": [_format_money(value) for value in amounts],
        "bill_total": _format_money(bill_total),
        "bill_adjustments": [_format_money(value) for value in adjustments] if adjustments is not None else None,
        "bill_balance": _format_money(bill_balance),
        "patient_shares": [_format_money(value) for value in shares] if shares is not None else None,
        "statement_share": _format_money(statement_share),
        "line_amount_sum": _format_money(line_sum),
        "bill_total_minus_line_sum": difference(bill_total, line_sum),
        "balance_from_bill_total_and_listed_adjustments": _format_money(printed_balance),
        "balance_from_line_sum_and_listed_adjustments": _format_money(line_balance),
        "bill_balance_minus_calculated_balance": difference(bill_balance, printed_balance),
        "provided_patient_shares_sum": _format_money(share_sum),
        "statement_share_minus_provided_shares": difference(statement_share, share_sum),
        "bill_balance_minus_statement_share": difference(bill_balance, statement_share),
        "warnings": warnings,
    }

import json
import unittest
from copy import deepcopy

from agent_runtime.bill_math import calculate_bill_values
from agent_runtime.demo_tools import create_demo_tools
from agent_templates import TEMPLATES


SAMPLE = {
    "lines": [
        {"label": "Line 1", "quantity": "1", "unit_price": "$900.00", "amount": "$900.00"},
        {"label": "Line 2", "quantity": "1", "unit_price": "$250.00", "amount": "$250.00"},
        {"label": "Line 3", "quantity": "1", "unit_price": "$250.00", "amount": "$250.00"},
        {"label": "Line 4", "quantity": "3", "unit_price": "$60.00", "amount": "$180.00"},
        {"label": "Line 5", "quantity": "1", "unit_price": "$120.00", "amount": "$120.00"},
    ],
    "bill_total": "$1,800.00",
    "bill_adjustments": ["-$696.00"],
    "bill_balance": "$1,104.00",
    "patient_shares": ["$120.00", "$30.00", "$0.00", "$8.00", "$16.00"],
    "statement_share": "$174.00",
}

SAMPLE_RECONCILIATION = {
    "matched_claim_lines": [
        {"label": "ER", "billed": "900", "allowed": "600"},
        {"label": "First X-ray", "billed": "250", "allowed": "150"},
        {"label": "One lab unit", "billed": "60", "allowed": "40"},
        {"label": "Splint", "billed": "120", "allowed": "80"},
    ],
    "duplicate_bill_amounts": ["250"],
    "unmatched_units": [
        {"label": "Lab", "bill_quantity": "3", "statement_quantity": "1", "unit_price": "60"},
    ],
}


def calculate(data):
    return calculate_bill_values(json.dumps(data))


class BillMathTests(unittest.TestCase):
    def test_demo_lines_total_1700_and_reconcile_the_two_stated_balances(self):
        source = TEMPLATES["medical-bill-reviewer"]["sample_input"]
        for line in SAMPLE["lines"]:
            self.assertIn(line["amount"], source)
        result = calculate(SAMPLE)
        self.assertEqual(result["bill_line_amounts"], ["$900.00", "$250.00", "$250.00", "$180.00", "$120.00"])
        self.assertEqual(result["line_amount_sum"], "$1,700.00")
        self.assertEqual(result["bill_total_minus_line_sum"], "$100.00")
        self.assertEqual(result["balance_from_bill_total_and_listed_adjustments"], "$1,104.00")
        self.assertEqual(result["balance_from_line_sum_and_listed_adjustments"], "$1,004.00")
        self.assertEqual(result["bill_balance_minus_calculated_balance"], "$0.00")
        self.assertEqual(result["provided_patient_shares_sum"], "$174.00")
        self.assertEqual(result["statement_share_minus_provided_shares"], "$0.00")
        self.assertEqual(result["bill_balance_minus_statement_share"], "$930.00")
        self.assertTrue(all(line["printed_amount_minus_exact_product"] == "$0.00" for line in result["lines"]))
        self.assertEqual(result["warnings"], [])
        self.assertIn("omitted lines", result["note"])

    def test_demo_reconciliation_calculates_each_component_without_double_counting(self):
        data = deepcopy(SAMPLE)
        data["reconciliation"] = SAMPLE_RECONCILIATION
        result = calculate(data)["reconciliation"]
        self.assertEqual([line["billed_minus_allowed"] for line in result["matched_claim_lines"]],
                         ["$300.00", "$100.00", "$20.00", "$40.00"])
        self.assertEqual(result["matched_billed_minus_allowed"], "$460.00")
        self.assertEqual(result["duplicate_bill_amount_sum"], "$250.00")
        self.assertEqual(result["unmatched_units"][0]["unmatched_quantity"], "2")
        self.assertEqual(result["unmatched_amount_sum"], "$120.00")
        self.assertEqual(result["component_sum"], "$930.00")
        self.assertEqual(result["balance_gap_minus_component_sum"], "$0.00")
        self.assertIn("already posted", result["note"])

    def test_reconciliation_leaves_posted_adjustments_visible_in_the_remainder(self):
        data = {
            "lines": [
                {"label": "ER", "quantity": "1", "unit_price": "900", "amount": "900"},
                {"label": "Lab", "quantity": "1", "unit_price": "60", "amount": "60"},
            ],
            "bill_total": "960", "bill_adjustments": ["-320", "-512"], "bill_balance": "128",
            "patient_shares": ["120", "8"], "statement_share": "128",
            "reconciliation": {
                "matched_claim_lines": [
                    {"label": "ER", "billed": "900", "allowed": "600"},
                    {"label": "Lab", "billed": "60", "allowed": "40"},
                ],
                "duplicate_bill_amounts": [], "unmatched_units": [],
            },
        }
        result = calculate(data)["reconciliation"]
        self.assertEqual(result["matched_billed_minus_allowed"], "$320.00")
        self.assertEqual(result["component_sum"], "$320.00")
        self.assertEqual(result["balance_gap_minus_component_sum"], "-$320.00")

    def test_partial_shares_do_not_become_a_printed_statement_total(self):
        data = {
            "lines": [
                {"label": "ER", "quantity": "1", "unit_price": "900", "amount": "900"},
                {"label": "Lab", "quantity": "1", "unit_price": "60", "amount": "60"},
            ],
            "bill_total": "960", "bill_adjustments": ["-480"], "bill_balance": "480",
            "patient_shares": ["120"], "statement_share": None,
            "reconciliation": {
                "matched_claim_lines": [{"label": "ER", "billed": "900", "allowed": "600"}],
                "duplicate_bill_amounts": [],
                "unmatched_units": [
                    {"label": "Lab", "bill_quantity": "1", "statement_quantity": "0", "unit_price": "60"},
                ],
            },
        }
        result = calculate(data)
        self.assertIsNone(result["statement_share"])
        self.assertEqual(result["provided_patient_shares_sum"], "$120.00")
        self.assertEqual(result["bill_balance_minus_provided_patient_shares"], "$360.00")
        self.assertIsNone(result["bill_balance_minus_statement_share"])
        self.assertIsNone(result["reconciliation"]["balance_gap_minus_component_sum"])
        self.assertIn("not necessarily a complete statement total", result["note"])

    def test_reconciliation_rejects_missing_or_inconsistent_categories(self):
        for invalid in (
            {},
            {**SAMPLE_RECONCILIATION, "duplicate_bill_amounts": None},
            {**SAMPLE_RECONCILIATION, "duplicate_bill_amounts": ["-250"]},
            {**SAMPLE_RECONCILIATION, "matched_claim_lines": [{"label": "ER", "billed": "900"}]},
            {**SAMPLE_RECONCILIATION, "matched_claim_lines": [{"label": "ER", "billed": "-1", "allowed": "0"}]},
            {**SAMPLE_RECONCILIATION, "unmatched_units": [
                {"label": "Lab", "bill_quantity": "1", "statement_quantity": "3", "unit_price": "60"},
            ]},
        ):
            data = deepcopy(SAMPLE)
            data["reconciliation"] = invalid
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                calculate(data)

    def test_clean_bill_and_decimal_cents_are_not_hardcoded_to_the_demo(self):
        data = {
            "lines": [
                {"label": "Procedure", "quantity": "2", "unit_price": "100.01", "amount": "200.02"},
                {"label": "Supplies", "quantity": "3", "unit_price": "0.02", "amount": "0.06"},
            ],
            "bill_total": "200.08", "bill_adjustments": ["-30.03", "-99.99"], "bill_balance": "70.06",
            "patient_shares": ["70.04", "0.02"], "statement_share": "70.06",
        }
        result = calculate(data)
        self.assertEqual(result["line_amount_sum"], "$200.08")
        self.assertEqual(result["bill_total_minus_line_sum"], "$0.00")
        self.assertEqual(result["balance_from_bill_total_and_listed_adjustments"], "$70.06")
        self.assertEqual(result["bill_balance_minus_statement_share"], "$0.00")
        self.assertEqual(result["provided_patient_shares_sum"], "$70.06")

    def test_line_multiplication_and_mismatched_shares_are_separately_visible(self):
        data = deepcopy(SAMPLE)
        data["lines"][3]["amount"] = "$181.00"
        data["statement_share"] = "$175.00"
        result = calculate(data)
        self.assertEqual(result["lines"][3]["quantity_times_unit_price_exact"], "$180.00")
        self.assertEqual(result["lines"][3]["printed_amount_minus_exact_product"], "$1.00")
        self.assertEqual(result["line_amount_sum"], "$1,701.00")
        self.assertEqual(result["statement_share_minus_provided_shares"], "$1.00")

    def test_fractional_cent_product_is_exact_and_requires_rounding_confirmation(self):
        data = {"lines": [{"label": "Partial unit", "quantity": "0.5", "unit_price": "0.01", "amount": "0.01"}],
                "patient_shares": None, "statement_share": None}
        result = calculate(data)
        self.assertEqual(result["lines"][0]["quantity_times_unit_price_exact"], "$0.005")
        self.assertEqual(result["lines"][0]["printed_amount_minus_exact_product"], "$0.005")
        self.assertTrue(any("fractional cent" in warning for warning in result["warnings"]))

    def test_missing_values_never_become_zero_or_a_complete_total(self):
        data = {"lines": [{"label": "First", "amount": "10.00"}, {"label": "Second", "amount": None}],
                "patient_shares": None, "statement_share": None}
        result = calculate(data)
        self.assertEqual(result["bill_line_amounts"], ["$10.00", None])
        for key in ("line_amount_sum", "bill_total_minus_line_sum", "balance_from_line_sum_and_listed_adjustments",
                    "provided_patient_shares_sum", "bill_balance_minus_statement_share"):
            self.assertIsNone(result[key])
        self.assertTrue(any("printed line amount" in warning for warning in result["warnings"]))
        self.assertTrue(any("bill_adjustments" in warning for warning in result["warnings"]))

    def test_explicit_no_adjustments_differs_from_missing_adjustments(self):
        data = {"lines": [{"label": "One", "amount": "20.00"}], "bill_total": "20.00", "bill_adjustments": [],
                "patient_shares": None, "statement_share": None}
        self.assertEqual(calculate(data)["balance_from_bill_total_and_listed_adjustments"], "$20.00")
        del data["bill_adjustments"]
        self.assertIsNone(calculate(data)["balance_from_bill_total_and_listed_adjustments"])

    def test_invalid_or_ambiguous_values_fail_explicitly(self):
        bad = [
            "", "[]", '{"lines":[]}', '{"lines":[{"label":"x","amount":"1","amount":"2"}]}',
            '{"lines":[{"label":"x","amount":NaN}]}',
            json.dumps({"lines": [{"label": "x", "amount": True}]}),
            json.dumps({"lines": [{"label": "x", "amount": "1,00.00"}]}),
            json.dumps({"lines": [{"label": "x", "amount": "0.001"}]}),
            json.dumps({"lines": [{"label": "x", "amount": "1000000000000"}]}),
            json.dumps({"lines": [{"label": "x", "amount": "1.00", "quantity": "-1"}]}),
            json.dumps({"lines": [{"label": "x", "amount": "1.00", "extra": "2"}]}),
            json.dumps({"lines": [{"label": "x", "amount": "1.00"}], "patient_shares": []}),
            json.dumps({"lines": [{"label": "x", "amount": "1.00"}], "bill_total_typo": "1.00"}),
            json.dumps({"lines": [{"label": "x", "amount": "1.00"}] * 101}),
        ]
        for value in bad:
            with self.subTest(value=value[:100]), self.assertRaises(ValueError):
                calculate_bill_values(value)
        with self.assertRaises(ValueError):
            calculate_bill_values(None)

    def test_share_fields_cannot_be_omitted_but_explicit_unknowns_remain_unknown(self):
        for field in ("patient_shares", "statement_share"):
            data = deepcopy(SAMPLE)
            del data[field]
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "Missing bill calculation fields: " + field):
                calculate(data)
        data = {**SAMPLE, "patient_shares": None, "statement_share": None}
        result = calculate(data)
        self.assertIsNone(result["provided_patient_shares_sum"])
        self.assertIsNone(result["statement_share"])
        self.assertTrue(any("patient_shares" in warning for warning in result["warnings"]))
        self.assertTrue(any("statement_share" in warning for warning in result["warnings"]))

    def test_numeric_json_is_parsed_as_decimal_not_binary_float(self):
        result = calculate_bill_values(
            '{"lines":[{"label":"One","amount":0.1},{"label":"Two","amount":0.2}],'
            '"bill_total":0.3,"bill_adjustments":[],"patient_shares":null,"statement_share":null}'
        )
        self.assertEqual(result["line_amount_sum"], "$0.30")
        self.assertEqual(result["bill_total_minus_line_sum"], "$0.00")

    def test_calculator_returns_an_attributed_read_only_receipt(self):
        tool = next(tool for tool in create_demo_tools("medical-bill-reviewer", "demo-agent")
                    if tool.__name__ == "calculate_bill_math")
        receipt = json.loads(tool(json.dumps(SAMPLE)))
        self.assertEqual((receipt["status"], receipt["agent"], receipt["simulation"]),
                         ("succeeded", "demo-agent", True))
        self.assertIn("No external system was contacted or changed", receipt["output"])
        result = json.loads(receipt["output"].split("\n", 1)[1])
        self.assertEqual(result["line_amount_sum"], "$1,700.00")


if __name__ == "__main__":
    unittest.main()

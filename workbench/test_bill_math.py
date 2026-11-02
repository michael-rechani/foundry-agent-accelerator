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
        data = {"lines": [{"label": "Partial unit", "quantity": "0.5", "unit_price": "0.01", "amount": "0.01"}]}
        result = calculate(data)
        self.assertEqual(result["lines"][0]["quantity_times_unit_price_exact"], "$0.005")
        self.assertEqual(result["lines"][0]["printed_amount_minus_exact_product"], "$0.005")
        self.assertTrue(any("fractional cent" in warning for warning in result["warnings"]))

    def test_missing_values_never_become_zero_or_a_complete_total(self):
        data = {"lines": [{"label": "First", "amount": "10.00"}, {"label": "Second", "amount": None}]}
        result = calculate(data)
        self.assertEqual(result["bill_line_amounts"], ["$10.00", None])
        for key in ("line_amount_sum", "bill_total_minus_line_sum", "balance_from_line_sum_and_listed_adjustments",
                    "provided_patient_shares_sum", "bill_balance_minus_statement_share"):
            self.assertIsNone(result[key])
        self.assertTrue(any("printed line amount" in warning for warning in result["warnings"]))
        self.assertTrue(any("bill_adjustments" in warning for warning in result["warnings"]))

    def test_explicit_no_adjustments_differs_from_missing_adjustments(self):
        data = {"lines": [{"label": "One", "amount": "20.00"}], "bill_total": "20.00", "bill_adjustments": []}
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

    def test_numeric_json_is_parsed_as_decimal_not_binary_float(self):
        result = calculate_bill_values(
            '{"lines":[{"label":"One","amount":0.1},{"label":"Two","amount":0.2}],'
            '"bill_total":0.3,"bill_adjustments":[]}'
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

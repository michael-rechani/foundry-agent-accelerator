import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from calculator import (
    architecture_ai_costs,
    completed_reviews,
    hosted_agent_cost,
    main,
    non_negative,
    platform_costs,
    shared_ai_cost,
    vm_cost,
    vm_sku_costs,
)


class CalculatorTests(unittest.TestCase):
    def render_example(self, **overrides) -> str:
        config = json.loads(Path(__file__).with_name("scenario.example.json").read_text())
        config.pop("foundry_platform", None)
        config.pop("iaas_platform", None)
        config.pop("completed_reviews", None)
        config.update(overrides)
        with tempfile.TemporaryDirectory() as directory:
            scenario = Path(directory) / "scenario.json"
            scenario.write_text(json.dumps(config), encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                main(scenario)
            return output.getvalue()

    def test_platform_costs_preserve_unpriced_items(self) -> None:
        self.assertEqual(platform_costs([
            {"name": "APIM", "monthly_cost": 100},
            {"name": "NAT", "monthly_cost": None},
        ], "platform"), [("APIM", 100), ("NAT", None)])

    def test_legacy_scenario_still_compares_hosting_layers(self) -> None:
        output = self.render_example()
        self.assertIn("Hosted-agent total: USD 470.70", output)
        self.assertIn("Foundry savings:", output)
        self.assertIn("None supplied; excluded", output)
        self.assertNotIn("cost per completed review:", output)

    def test_platform_quantities_calculate_costs(self) -> None:
        self.assertEqual(platform_costs([
            {"name": "Endpoint hours", "quantity": 5840, "unit_rate": 0.01},
        ], "platform"), [("Endpoint hours", 58.4)])

    def test_deployed_budget_is_explicit_and_does_not_claim_savings(self) -> None:
        path = Path(__file__).with_name("scenario.deployed.json")
        config = json.loads(path.read_text())
        self.assertTrue(all(value is not None for _, value in platform_costs(config["foundry_platform"], "platform")))
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            main(path)
        self.assertIn("not invoiced or measured spend", output.getvalue())
        self.assertIn("contingency", output.getvalue())
        self.assertIn("APIM Standard v2 capacity (disabled): USD 0.00", output.getvalue())
        self.assertIn("Hosted-agent total: USD 1,584.76", output.getvalue())
        self.assertNotIn("Foundry savings:", output.getvalue())

    def test_platform_quantities_reject_ambiguous_or_invalid_inputs(self) -> None:
        for fields in (
            {"quantity": 1}, {"unit_rate": 1},
            {"quantity": 1, "unit_rate": 1, "monthly_cost": 1},
            {"quantity": -1, "unit_rate": 1},
            {"quantity": True, "unit_rate": 1},
            {"quantity": 1e308, "unit_rate": 1e308},
        ):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                platform_costs([{"name": "Meter", **fields}], "platform")

    def test_checked_in_example_does_not_claim_complete_costs(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            main(Path(__file__).with_name("scenario.example.json"))
        self.assertIn("APIM Standard v2 capacity: USD 700.00", output.getvalue())
        self.assertIn("APIM calls beyond included allowance: UNPRICED", output.getvalue())
        self.assertIn("Windows jumpbox compute: USD 42.05", output.getvalue())
        self.assertIn("known subtotal (INCOMPLETE)", output.getvalue())
        self.assertNotIn("Foundry savings:", output.getvalue())

    def test_sourced_capacity_estimates_match_hours_and_rates(self) -> None:
        config = json.loads(Path(__file__).with_name("scenario.example.json").read_text())
        for item in config["foundry_platform"]:
            if "hourly_rate" in item:
                self.assertAlmostEqual(item["monthly_cost"], item["hourly_rate"] * config["platform_monthly_hours"])

    def test_invalid_platform_costs(self) -> None:
        for value in ({}, [None], [{"name": " ", "monthly_cost": 0}],
                      [{"name": "APIM", "monthly_cost": -1}],
                      [{"name": "APIM", "monthly_cost": True}],
                      [{"name": "APIM", "monthly_cost": float("inf")}],
                      [{"name": "APIM", "monthly_cost": 0}] * 2):
            with self.subTest(value=value), self.assertRaises(ValueError):
                platform_costs(value, "platform")

    def test_completed_review_counts(self) -> None:
        self.assertIsNone(completed_reviews({}))
        self.assertEqual(completed_reviews({"completed_reviews": 0}), 0)
        for value in (True, -1, 1.5, "10", None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                completed_reviews({"completed_reviews": value})

    def test_platform_costs_affect_totals_and_break_even(self) -> None:
        output = self.render_example(
            foundry_platform=[{"name": "APIM", "monthly_cost": 100}],
            iaas_platform=[{"name": "Network", "monthly_cost": 20}],
            completed_reviews=100,
        )
        self.assertIn("Hosted-agent total: USD 570.70", output)
        self.assertIn("Allocated cost per completed review: USD 5.71", output)
        self.assertIn("architecture total: USD 1,787.68", output)
        self.assertIn("Foundry savings:       USD 1,216.98", output)
        self.assertIn("break-even hours:      20,683.0", output)

    def test_unpriced_platform_suppresses_comparison(self) -> None:
        for architecture in ("foundry_platform", "iaas_platform"):
            output = self.render_example(**{
                architecture: [{"name": "APIM", "monthly_cost": None}],
                "completed_reviews": 0,
            })
            self.assertIn("APIM: UNPRICED", output)
            self.assertIn("known subtotal (INCOMPLETE)", output)
            self.assertNotIn("Foundry savings:", output)
            self.assertNotIn("break-even hours:", output)
            self.assertIn("zero completions or unpriced items", output)

    def test_vm_cost(self) -> None:
        result = vm_cost(
            {
                "instance_count": 2,
                "running_hours_per_instance": 10,
                "hourly_rate": 3,
                "managed_disks_monthly": 4,
                "monitoring_monthly": 5,
                "egress_gb": 2,
                "egress_rate_per_gb": 0.5,
                "operations_hours": 2,
                "operations_rate_per_hour": 10,
            }
        )
        self.assertEqual(result.total, 90)

    def test_hosted_agent_cost(self) -> None:
        result, hourly_rate = hosted_agent_cost(
            {
                "aggregate_sandbox_hours": 100,
                "vcpu_per_sandbox": 0.5,
                "gib_per_sandbox": 1,
                "vcpu_rate_per_hour": 0.2,
                "gib_rate_per_hour": 0.05,
                "session_storage_gb_months": 10,
                "storage_rate_per_gb_month": 0.1,
                "monitoring_monthly": 2,
                "egress_gb": 10,
                "egress_rate_per_gb": 0.2,
            }
        )
        self.assertAlmostEqual(hourly_rate, 0.15)
        self.assertAlmostEqual(result.total, 20)

    def test_vm_sku_costs_merge_shared_assumptions(self) -> None:
        results = vm_sku_costs(
            {
                "vm_assumptions": {
                    "instance_count": 2,
                    "running_hours_per_instance": 10,
                    "managed_disks_monthly": 4,
                    "monitoring_monthly": 5,
                    "egress_gb": 2,
                    "egress_rate_per_gb": 0.5,
                    "operations_hours": 2,
                    "operations_rate_per_hour": 10,
                },
                "vm_skus": [
                    {
                        "sku": "Standard_D2as_v5",
                        "description": "general purpose",
                        "hourly_rate": 3,
                    },
                    {
                        "sku": "Standard_D4as_v5",
                        "hourly_rate": 4,
                        "managed_disks_monthly": 8,
                    },
                ],
            }
        )

        self.assertEqual(results[0][0], "Standard_D2as_v5 - general purpose")
        self.assertEqual(results[0][1].total, 90)
        self.assertEqual(results[1][0], "Standard_D4as_v5")
        self.assertEqual(results[1][1].total, 114)

    def test_vm_skus_must_not_be_empty(self) -> None:
        with self.assertRaisesRegex(ValueError, "non-empty list"):
            vm_sku_costs({"vm_skus": []})

    def test_shared_ai_cost(self) -> None:
        result = shared_ai_cost(
            {
                "input_tokens": 2_000_000,
                "input_rate_per_million": 3,
                "output_tokens": 1_000_000,
                "output_rate_per_million": 9,
                "tool_usage_monthly": 5,
            }
        )
        self.assertEqual(result, 20)

    def test_architecture_specific_ai_costs(self) -> None:
        config = {
            "iaas_ai": {
                "input_tokens": 0,
                "input_rate_per_million": 0,
                "output_tokens": 0,
                "output_rate_per_million": 0,
                "tool_usage_monthly": 5,
            },
            "foundry_ai": {
                "input_tokens": 2_000_000,
                "input_rate_per_million": 3,
                "output_tokens": 1_000_000,
                "output_rate_per_million": 9,
                "tool_usage_monthly": 5,
            },
        }

        self.assertEqual(architecture_ai_costs(config), (5, 20))

    def test_shared_ai_cost_remains_compatible(self) -> None:
        shared = {
            "input_tokens": 2_000_000,
            "input_rate_per_million": 3,
            "output_tokens": 1_000_000,
            "output_rate_per_million": 9,
            "tool_usage_monthly": 5,
        }

        self.assertEqual(architecture_ai_costs({"shared_ai": shared}), (20, 20))

    def test_negative_values_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "finite non-negative"):
            shared_ai_cost(
                {
                    "input_tokens": -1,
                    "input_rate_per_million": 3,
                    "output_tokens": 0,
                    "output_rate_per_million": 9,
                    "tool_usage_monthly": 0,
                }
            )

    def test_non_finite_values_are_rejected(self) -> None:
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "finite non-negative"):
                    non_negative(value, "test.value")

    def test_boolean_values_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "must be a number"):
            non_negative(True, "test.value")


if __name__ == "__main__":
    unittest.main()

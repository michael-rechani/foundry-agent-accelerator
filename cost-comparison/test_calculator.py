import unittest

from calculator import hosted_agent_cost, non_negative, shared_ai_cost, vm_cost


class CalculatorTests(unittest.TestCase):
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

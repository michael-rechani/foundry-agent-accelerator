import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def non_negative(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a number")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{name} must be a finite non-negative number")
    return number


@dataclass(frozen=True)
class CostBreakdown:
    compute: float
    storage: float
    monitoring: float
    egress: float
    operations: float = 0.0

    @property
    def total(self) -> float:
        return (
            self.compute
            + self.storage
            + self.monitoring
            + self.egress
            + self.operations
        )


def vm_cost(config: dict[str, Any]) -> CostBreakdown:
    return CostBreakdown(
        compute=(
            non_negative(config["instance_count"], "vm.instance_count")
            * non_negative(
                config["running_hours_per_instance"],
                "vm.running_hours_per_instance",
            )
            * non_negative(config["hourly_rate"], "vm.hourly_rate")
        ),
        storage=non_negative(
            config["managed_disks_monthly"],
            "vm.managed_disks_monthly",
        ),
        monitoring=non_negative(
            config["monitoring_monthly"],
            "vm.monitoring_monthly",
        ),
        egress=(
            non_negative(config["egress_gb"], "vm.egress_gb")
            * non_negative(
                config["egress_rate_per_gb"],
                "vm.egress_rate_per_gb",
            )
        ),
        operations=(
            non_negative(config["operations_hours"], "vm.operations_hours")
            * non_negative(
                config["operations_rate_per_hour"],
                "vm.operations_rate_per_hour",
            )
        ),
    )


def vm_sku_costs(config: dict[str, Any]) -> list[tuple[str, CostBreakdown]]:
    if "vm_skus" not in config:
        return [("VM infrastructure", vm_cost(config["vm"]))]

    sku_configs = config["vm_skus"]
    if not isinstance(sku_configs, list) or not sku_configs:
        raise ValueError("vm_skus must be a non-empty list")
    shared_config = config.get("vm_assumptions", {})
    if not isinstance(shared_config, dict):
        raise ValueError("vm_assumptions must be an object")

    results: list[tuple[str, CostBreakdown]] = []
    for index, sku_config in enumerate(sku_configs):
        if not isinstance(sku_config, dict):
            raise ValueError(f"vm_skus[{index}] must be an object")
        sku = str(sku_config.get("sku", "")).strip()
        if not sku:
            raise ValueError(f"vm_skus[{index}].sku must be a non-empty string")
        description = str(sku_config.get("description", "")).strip()
        label = f"{sku} - {description}" if description else sku
        results.append((label, vm_cost(shared_config | sku_config)))
    return results


def hosted_agent_cost(config: dict[str, Any]) -> tuple[CostBreakdown, float]:
    hourly_sandbox_rate = (
        non_negative(config["vcpu_per_sandbox"], "hosted_agent.vcpu_per_sandbox")
        * non_negative(
            config["vcpu_rate_per_hour"],
            "hosted_agent.vcpu_rate_per_hour",
        )
        + non_negative(config["gib_per_sandbox"], "hosted_agent.gib_per_sandbox")
        * non_negative(
            config["gib_rate_per_hour"],
            "hosted_agent.gib_rate_per_hour",
        )
    )

    return (
        CostBreakdown(
            compute=(
                non_negative(
                    config["aggregate_sandbox_hours"],
                    "hosted_agent.aggregate_sandbox_hours",
                )
                * hourly_sandbox_rate
            ),
            storage=(
                non_negative(
                    config["session_storage_gb_months"],
                    "hosted_agent.session_storage_gb_months",
                )
                * non_negative(
                    config["storage_rate_per_gb_month"],
                    "hosted_agent.storage_rate_per_gb_month",
                )
            ),
            monitoring=non_negative(
                config["monitoring_monthly"],
                "hosted_agent.monitoring_monthly",
            ),
            egress=(
                non_negative(config["egress_gb"], "hosted_agent.egress_gb")
                * non_negative(
                    config["egress_rate_per_gb"],
                    "hosted_agent.egress_rate_per_gb",
                )
            ),
        ),
        hourly_sandbox_rate,
    )


def shared_ai_cost(config: dict[str, Any]) -> float:
    return (
        non_negative(config["input_tokens"], "shared_ai.input_tokens")
        / 1_000_000
        * non_negative(
            config["input_rate_per_million"],
            "shared_ai.input_rate_per_million",
        )
        + non_negative(config["output_tokens"], "shared_ai.output_tokens")
        / 1_000_000
        * non_negative(
            config["output_rate_per_million"],
            "shared_ai.output_rate_per_million",
        )
        + non_negative(
            config["tool_usage_monthly"],
            "shared_ai.tool_usage_monthly",
        )
    )


def money(value: float, currency: str) -> str:
    return f"{currency} {value:,.2f}"


def architecture_ai_costs(config: dict[str, Any]) -> tuple[float, float]:
    if "shared_ai" in config:
        shared = shared_ai_cost(config["shared_ai"])
        return shared, shared

    return (
        shared_ai_cost(config["iaas_ai"]),
        shared_ai_cost(config["foundry_ai"]),
    )


def main(path: Path) -> None:
    config = json.loads(path.read_text(encoding="utf-8"))
    currency = str(config.get("currency", "USD"))

    vm_skus = vm_sku_costs(config)
    hosted, hourly_sandbox_rate = hosted_agent_cost(config["hosted_agent"])
    iaas_ai, foundry_ai = architecture_ai_costs(config)
    hosted_total = hosted.total + foundry_ai

    print("Monthly cost comparison")
    print(f"  Hosted infrastructure:   {money(hosted.total, currency)}")
    print(f"    compute:               {money(hosted.compute, currency)}")
    print(f"    storage:               {money(hosted.storage, currency)}")
    print(f"    monitoring:            {money(hosted.monitoring, currency)}")
    print(f"    egress:                {money(hosted.egress, currency)}")
    print(f"  Foundry AI consumption:  {money(foundry_ai, currency)}")
    print(f"  Hosted-agent total:      {money(hosted_total, currency)}")

    print("\nIaaS GPU SKU comparison")
    for sku, vm in sorted(vm_skus, key=lambda item: item[1].total):
        iaas_total = vm.total + iaas_ai
        print(f"  {sku}")
        print(f"    infrastructure:        {money(vm.total, currency)}")
        print(f"    compute:               {money(vm.compute, currency)}")
        print(f"    storage:               {money(vm.storage, currency)}")
        print(f"    monitoring:            {money(vm.monitoring, currency)}")
        print(f"    egress:                {money(vm.egress, currency)}")
        print(f"    operations labor:      {money(vm.operations, currency)}")
        print(f"    external AI services:  {money(iaas_ai, currency)}")
        print(f"    architecture total:    {money(iaas_total, currency)}")
        print(f"    Foundry savings:       {money(iaas_total - hosted_total, currency)}")

        hosted_fixed = hosted.total - hosted.compute
        break_even_budget = iaas_total - foundry_ai - hosted_fixed
        if hourly_sandbox_rate > 0 and break_even_budget >= 0:
            break_even = break_even_budget / hourly_sandbox_rate
            print(f"    break-even hours:      {break_even:,.1f}")
        else:
            print("    break-even hours:      not applicable with these rates")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python calculator.py <scenario.json>")

    try:
        main(Path(sys.argv[1]))
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise SystemExit(f"Invalid cost scenario: {error}") from error


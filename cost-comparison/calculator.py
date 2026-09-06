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


def platform_costs(config: Any, name: str) -> list[tuple[str, float | None]]:
    if not isinstance(config, list):
        raise ValueError(f"{name} must be a list")
    items: list[tuple[str, float | None]] = []
    names: set[str] = set()
    for index, item in enumerate(config):
        field = f"{name}[{index}]"
        if not isinstance(item, dict):
            raise ValueError(f"{field} must be an object")
        label = item.get("name")
        if not isinstance(label, str) or not label.strip() or label.strip() in names:
            raise ValueError(f"{field}.name must be a unique non-empty string")
        names.add(label.strip())
        if "quantity" in item or "unit_rate" in item:
            if "monthly_cost" in item:
                raise ValueError(f"{field} must use monthly_cost or quantity and unit_rate, not both")
            if "quantity" not in item or "unit_rate" not in item:
                raise ValueError(f"{field} requires both quantity and unit_rate")
            value = non_negative(item["quantity"], f"{field}.quantity") * non_negative(
                item["unit_rate"], f"{field}.unit_rate"
            )
        else:
            value = item["monthly_cost"]
        items.append((label.strip(), None if value is None else non_negative(value, field)))
    return items


def completed_reviews(config: dict[str, Any]) -> int | None:
    value = config.get("completed_reviews")
    if "completed_reviews" in config and (type(value) is not int or value < 0):
        raise ValueError("completed_reviews must be a non-negative integer")
    return value


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
    if "estimate_kind" in config:
        print(config["estimate_kind"])
    for assumption in config.get("assumptions", []):
        print(f"  Assumption: {assumption}")

    vm_skus = vm_sku_costs(config)
    hosted, hourly_sandbox_rate = hosted_agent_cost(config["hosted_agent"])
    iaas_ai, foundry_ai = architecture_ai_costs(config)
    foundry_platform = platform_costs(config.get("foundry_platform", []), "foundry_platform")
    iaas_platform = platform_costs(config.get("iaas_platform", []), "iaas_platform")
    foundry_complete = all(value is not None for _, value in foundry_platform)
    iaas_complete = all(value is not None for _, value in iaas_platform)
    foundry_platform_total = sum(value for _, value in foundry_platform if value is not None)
    iaas_platform_total = sum(value for _, value in iaas_platform if value is not None)
    reviews = completed_reviews(config)
    hosted_total = hosted.total + foundry_ai + foundry_platform_total

    for label, items in (("Foundry", foundry_platform), ("IaaS", iaas_platform)):
        print(f"{label} additional platform costs")
        if not items:
            print("  None supplied; excluded from this estimate.")
        for name, value in items:
            print(f"  {name}: {money(value, currency) if value is not None else 'UNPRICED'}")

    print("\nMonthly cost comparison")
    print(f"  Hosted infrastructure:   {money(hosted.total, currency)}")
    print(f"    compute:               {money(hosted.compute, currency)}")
    print(f"    storage:               {money(hosted.storage, currency)}")
    print(f"    monitoring:            {money(hosted.monitoring, currency)}")
    print(f"    egress:                {money(hosted.egress, currency)}")
    print(f"  Foundry AI consumption:  {money(foundry_ai, currency)}")
    print(f"  Additional platform:    {money(foundry_platform_total, currency)}")
    qualifier = "total" if foundry_complete else "known subtotal (INCOMPLETE)"
    print(f"  Hosted-agent {qualifier}: {money(hosted_total, currency)}")
    if reviews is not None:
        if reviews > 0 and foundry_complete:
            print(f"  Allocated cost per completed review: {money(hosted_total / reviews, currency)}")
        else:
            print("  Allocated cost per completed review: unavailable (zero completions or unpriced items)")

    print("\nIaaS GPU SKU comparison")
    for sku, vm in sorted(vm_skus, key=lambda item: item[1].total):
        iaas_total = vm.total + iaas_ai + iaas_platform_total
        print(f"  {sku}")
        print(f"    infrastructure:        {money(vm.total, currency)}")
        print(f"    compute:               {money(vm.compute, currency)}")
        print(f"    storage:               {money(vm.storage, currency)}")
        print(f"    monitoring:            {money(vm.monitoring, currency)}")
        print(f"    egress:                {money(vm.egress, currency)}")
        print(f"    operations labor:      {money(vm.operations, currency)}")
        print(f"    external AI services:  {money(iaas_ai, currency)}")
        print(f"    additional platform:   {money(iaas_platform_total, currency)}")
        qualifier = "total" if iaas_complete else "known subtotal (INCOMPLETE)"
        print(f"    architecture {qualifier}: {money(iaas_total, currency)}")
        if reviews is not None:
            if reviews > 0 and iaas_complete:
                print(f"    allocated cost per completed review: {money(iaas_total / reviews, currency)}")
            else:
                print("    allocated cost per completed review: unavailable (zero completions or unpriced items)")
        if not foundry_complete or not iaas_complete:
            print("    savings and break-even: unavailable (unpriced platform items)")
            continue
        print(f"    Foundry savings:       {money(iaas_total - hosted_total, currency)}")

        hosted_fixed = hosted.total - hosted.compute + foundry_platform_total
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


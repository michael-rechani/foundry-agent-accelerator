# Azure GPU VMs versus Foundry hosted-agent costs

This calculator ranks Azure IaaS GPU VM scenarios for self-hosted model
inference and agent orchestration against a Foundry hosted-agent architecture:

- **IaaS:** GPU VMs running the model and orchestration stack, plus managed
  disks, monitoring, egress, external tools, and estimated operations labor.
- **Foundry:** hosted-agent sandbox CPU and memory time, persistent session
  storage, monitoring, egress, external tools, and model token consumption.

The two architectures have separate AI-consumption sections. A self-hosted
model normally has zero token charges because inference is included in GPU
compute, while the Foundry architecture incurs model token charges. External
tool charges can appear on both sides.

This is a hosting-layer comparison, not a complete Azure bill. Add costs for
Foundry project dependencies such as Search, Cosmos DB, Storage, Key Vault, and
Log Analytics when those resources differ between the architectures.

## What the comparison includes

| Dimension | Self-hosted GPU VM | Foundry hosted agent |
| --- | --- | --- |
| Compute | Named GPU SKU rate, instance count, and running hours | Aggregate active and idle-timeout sandbox hours |
| Storage | Managed disks | Persistent session storage |
| Operations | Configurable labor estimate for patching and platform care | Managed runtime; no labor value is assumed by the calculator |
| AI consumption | Included in GPU compute; optional external AI charges | Foundry model tokens and optional external AI charges |

The example uses Linux pay-as-you-go retail rates for East US 2 GPU classes:
NVIDIA T4, A10, and A100. Rates are snapshots, not quotes. These GPU classes
are not throughput-equivalent; benchmark the selected model, precision,
context length, batching, and concurrency on each candidate. The example also
uses one VM, which does not provide production high availability. Evaluate
autoscaling, zone redundancy, quota, patching, drivers, model serving,
session isolation, startup behavior, and support requirements separately.

## Use

1. Copy `scenario.example.json` for the workload being evaluated.
2. Add each candidate under `vm_skus`. Keep costs shared by all options under
  `vm_assumptions`; a SKU entry can override any shared assumption.
3. Replace every illustrative rate with the current rate for your agreement,
  currency, region, operating system, purchase model, VM SKU, and Foundry
  sandbox and model. Update `rates_last_reviewed` whenever assumptions change.
4. Estimate aggregate hosted sandbox hours, including the configured idle
   timeout. For example, 1,000 sessions consuming an average of 0.4 billable
   hours each equals 400 sandbox hours.
5. Run:

```powershell
python calculator.py scenario.example.json
```

Rates are intentionally external to the code because Azure prices vary by
region, currency, agreement, operating system, purchase model, and date. The
SKU rates in the example are illustrative, not quotes. Obtain current rates
from:

- [Azure Pricing Calculator](https://azure.microsoft.com/pricing/calculator/)
- [Foundry Agent Service pricing](https://azure.microsoft.com/pricing/details/foundry-agent-service/)
- [Azure Retail Prices API](https://learn.microsoft.com/rest/api/cost-management/retail-prices/azure-retail-prices)

## Formula summary

```text
Each VM SKU infrastructure =
  VM count * monthly running hours * SKU hourly rate
  + shared or overridden managed disks, monitoring, egress, and operations labor

Hosted-agent infrastructure =
  aggregate sandbox hours
  * (sandbox vCPU * vCPU-hour rate + sandbox GiB * GiB-hour rate)
  + session storage + monitoring + egress

IaaS external AI consumption =
  input tokens / 1,000,000 * input rate
  + output tokens / 1,000,000 * output rate
  + tool usage

Foundry AI consumption =
  input tokens / 1,000,000 * input rate
  + output tokens / 1,000,000 * output rate
  + tool usage
```

For each SKU, the calculator reports total cost, Foundry savings, and the
monthly sandbox-hour break-even point where hosted runtime equals that VM
scenario. Positive Foundry savings means the hosted infrastructure is less
expensive; a negative value means it carries a premium under those assumptions.
Architecture-specific model and tool charges are included in savings and
break-even calculations. This is a cost comparison, not a claim that the
self-hosted and managed models have equivalent quality, safety, or throughput.


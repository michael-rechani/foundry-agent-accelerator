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

The calculator supports itemized additional platform costs for each architecture
and allocation per completed review. It is still an estimate, not an Azure bill.
The example explicitly marks private-platform dependencies as unpriced. It will
not report savings or break-even until all supplied line items are priced.

## What the comparison includes

| Dimension | Self-hosted GPU VM | Foundry hosted agent |
| --- | --- | --- |
| Compute | Named GPU SKU rate, instance count, and running hours | Aggregate active and idle-timeout sandbox hours |
| Storage | Managed disks | Persistent session storage |
| Operations | Configurable labor estimate for patching and platform care | Managed runtime; no labor value is assumed by the calculator |
| AI consumption | Included in GPU compute; optional external AI charges | Foundry model tokens and optional external AI charges |
| Additional platform | Architecture-specific dependencies beyond VM assumptions | APIM, jumpbox, networking, project dependencies, and platform operations |

The example retains Linux pay-as-you-go retail rates for East US 2 GPU classes:
NVIDIA T4, A10, and A100. Rates are snapshots, not quotes. These GPU classes
are not throughput-equivalent; benchmark the selected model, precision,
context length, batching, and concurrency on each candidate. The example also
uses one VM, which does not provide production high availability. Evaluate
autoscaling, zone redundancy, quota, patching, drivers, model serving,
session isolation, startup behavior, and support requirements separately.

The private Foundry deployment uses North Central US for the primary workload
and West US for management/APIM. These are separate from the example's GPU
comparison region. The region metadata does not select or refresh prices.
The [platform rate snapshot](platform-rates.md) records verified APIM and Windows
jumpbox capacity rates retrieved on 2026-09-04. Other platform items remain
unpriced. The ActualCost query was throttled, so actual spend is not reconciled.
The original `rates_last_reviewed` date describes the GPU/model/runtime snapshot;
`platform_rates_last_reviewed` describes only the sourced platform entries.

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
5. Fill `foundry_platform` and `iaas_platform` with unique names and monthly
  costs in the scenario currency. Replace every `null` with a verified estimate,
  or use zero only when an item is demonstrably not incurred. Add any missing
  resources. Include the deployed but unpublished APIM service and retained
  agents' billable runtime. Check replica counts, standby time, and regional
  replication instead of assuming one invocation equals one billable sandbox.
6. Set `completed_reviews` to successful business reviews over the same month.
  Count a coordinator-plus-specialist workflow once, not once per agent call.
  Include failed attempts and retries in monthly resource/token costs. Zero
  completions reports allocation as unavailable; omit the field to skip it.
7. Run:

```powershell
python calculator.py scenario.example.json
```

Platform items are additive. Do not count the same storage, monitoring, egress,
or operations expense in both a platform item and existing runtime/VM fields.
The IaaS placeholder must be replaced with its own equivalent dependency budget;
do not assume infrastructure is free on that side of the comparison. Older
scenarios without platform lists still work, but explicitly report those costs
as excluded.

`null` means unknown, not zero. Known subtotals remain visible, but savings and
break-even are suppressed if either architecture has an unpriced item. Allocation
is suppressed only for the incomplete architecture. An entirely omitted expense
cannot be detected automatically, so even a complete input is not proof of a
complete bill.

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

Architecture total =
  infrastructure + architecture AI consumption + additional platform items

Allocated cost per completed review =
  architecture total / completed reviews
```

For each SKU, the calculator reports total cost, Foundry savings, and the
monthly sandbox-hour break-even point where hosted runtime equals that VM
scenario. Positive Foundry savings means the hosted infrastructure is less
expensive; a negative value means it carries a premium under those assumptions.
Architecture-specific model and tool charges are included in savings and
break-even calculations, along with additional platform items. The break-even
calculation varies sandbox hours only: AI consumption and every other cost are
held constant. It is not a workload-scaling prediction. Allocated cost per review
is an average including idle capacity and failed attempts, not the marginal cost
of one more request. Estimating marginal cost requires measured per-flow token,
runtime, and metered dependency usage.

This is a cost comparison, not a claim that the
self-hosted and managed models have equivalent quality, safety, or throughput.


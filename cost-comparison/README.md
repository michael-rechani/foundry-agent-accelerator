# Compare Azure GPU VM and Foundry hosted-agent costs

[Home](../README.md) / Cost comparison

This calculator compares Azure infrastructure as a service (IaaS) graphics
processing unit (GPU) virtual machine (VM) scenarios with a Microsoft Foundry
hosted-agent architecture. It gives you itemized monthly estimates that you can
adapt before a scoped architecture or cost discussion.

> [!IMPORTANT]
> This is advanced, optional architecture analysis. Start with [one Foundry
> demonstration](../docs/demos.md) and its quality findings, not a savings claim.
> The calculator doesn't measure model quality, demonstrate a customer
> implementation, or prove complete spend. Cost recommendations are
> scope-dependent, missing telemetry stays unavailable instead of zero, and the
> reference budget makes no savings claim against IaaS because equivalent IaaS
> dependencies haven't been sized.

## In this guide

- [How the calculator compares costs](#how-the-calculator-compares-costs)
- [What the comparison includes](#what-the-comparison-includes)
- [Use the calculator](#use-the-calculator)
- [Formula summary](#formula-summary)
- [Interpret results](#interpret-results)
- [Related content](#related-content)

## How the calculator compares costs

Keep three quantities separate:

| Quantity | Meaning |
| --- | --- |
| **Measured usage** | Actual reported tokens and observed response time, with their measurement scope. Missing telemetry stays unavailable, not zero. |
| **Estimated cost** | Measured or estimated usage multiplied by rates with a named source. It isn't invoiced spend. |
| **Allocated platform cost** | Shared capacity/runtime/dependency costs divided by a chosen denominator and time period. It isn't marginal token cost. |

Use the [Foundry evaluation guide](../evaluations/README.md) for optional model
and prompt comparison on the same dataset. Browser-session latency isn't a
quality score, and this calculator can't recover missing multi-agent telemetry.

Engagements focus on demonstration and technical validation. Integration with
customer systems and production deployment require separate scoping and agreement.

The calculator ranks Azure IaaS GPU VM scenarios for self-hosted model inference
and agent orchestration against a Foundry hosted-agent architecture:

- **IaaS:** GPU VMs running the model and orchestration stack, plus managed
  disks, monitoring, egress, external tools, and estimated operations labor.
- **Foundry:** hosted-agent sandbox CPU and memory time, persistent session
  storage, monitoring, egress, external tools, and model token consumption.

The two architectures have separate artificial intelligence (AI)-consumption
sections. A self-hosted model normally has zero token charges because GPU
compute includes inference, while the Foundry architecture incurs model token
charges. External tool charges can appear on both sides.

The calculator supports itemized additional platform costs for each architecture
and allocation per completed review. It's still an estimate, not an Azure bill.
The example marks private-platform dependencies as unpriced. It won't
report savings or break-even until all supplied line items are priced.

For an itemized **reference-environment budget**, use
[scenario.deployed.json](scenario.deployed.json):

```powershell
python calculator.py scenario.deployed.json
```

The filename is retained for compatibility. It doesn't identify your deployment
or track a live environment. The [reference budget and rate notes](platform-rates.md)
describe saved assumptions. They don't query Azure resources, refresh prices,
or reconcile a bill, so verify the inputs for the environment you want to
evaluate.

Copy and adapt the budget before use. It includes labor and unverified
feature allowances, not measured spend. Registry, endpoint, capacity, and regional
assumptions must match the environment being evaluated.

## What the comparison includes

| Dimension | Self-hosted GPU VM | Foundry hosted agent |
| --- | --- | --- |
| Compute | Named GPU SKU rate, instance count, and running hours | Aggregate active and idle-timeout sandbox hours |
| Storage | Managed disks | Persistent session storage |
| Operations | Configurable labor estimate for patching and platform care | Managed runtime. The calculator assumes no labor value |
| AI consumption | Included in GPU compute. Optional external AI charges | Foundry model tokens and optional external AI charges |
| Additional platform | Architecture-specific dependencies beyond VM assumptions | Azure API Management (APIM), networking, project dependencies, and platform operations |

The example retains Linux pay-as-you-go retail rates for East US 2 GPU classes:
NVIDIA T4, A10, and A100. Rates are snapshots, not quotes. These GPU classes
aren't throughput-equivalent, so benchmark the selected model, precision, context
length, batching, and concurrency on each candidate. The example also uses one
VM, which doesn't provide production high availability. Evaluate autoscaling,
zone redundancy, quota, patching, drivers, model serving, session isolation,
startup behavior, and support requirements separately.

The reference budget assumes North Central US for the primary workload and West
US for management, with zero APIM capacity hours. These aren't universal
deployment requirements, and they differ from the GPU example's region. Region
metadata doesn't select or refresh prices. The [platform budget](platform-rates.md)
documents recorded rates and usage allowances. The original comparison
example remains incomplete. Itemized reference-budget coverage isn't proof of
actual spend or a complete bill. The `rates_last_reviewed` field applies to GPU,
model, and runtime rates. `platform_rates_last_reviewed` applies only to platform
rates.

## Use the calculator

1. Copy `scenario.example.json` for the workload being evaluated.
2. Add each candidate under `vm_skus`. Keep costs shared by all options under
   `vm_assumptions`. A SKU entry can override any shared assumption.
3. Replace every illustrative rate with the current rate for your agreement,
   currency, region, operating system, purchase model, VM SKU, and Foundry
   sandbox and model. Update `rates_last_reviewed` whenever assumptions change.
4. Estimate aggregate hosted sandbox hours, including the configured idle
   timeout. For example, 1,000 sessions consuming an average of 0.4 billable
   hours each equals 400 sandbox hours.
5. Fill `foundry_platform` and `iaas_platform` with unique names and monthly
   costs in the scenario currency. Replace every `null` with a verified estimate,
   or use zero only when an item is demonstrably not incurred. Add any missing
   resources. Include APIM only when deployed, and account for retained agents'
   billable runtime. Check replica counts, standby time, and regional replication
   instead of assuming one invocation equals one billable sandbox.
6. Set `completed_reviews` to successful business reviews over the same month.
   Count a coordinator-plus-specialist workflow once, not once per agent call.
   Include failed attempts and retries in monthly resource/token costs. Zero
   completions reports allocation as unavailable; omit the field to skip it.
7. Run:

```powershell
python calculator.py scenario.example.json
```

Platform items are additive. Don't count the same storage, monitoring, egress,
or operations expense in both a platform item and existing runtime/VM fields.
Each item accepts either `monthly_cost` or `quantity` and `unit_rate`. Don't
supply both forms. Quantities and rates must be finite, non-negative numbers.
The calculator multiplies them without rounding intermediate values. Budget
metadata and assumptions are printed before totals when provided.

The IaaS placeholder must be replaced with its own equivalent dependency budget.
Don't assume infrastructure is free on that side of the comparison. Older
scenarios without platform lists still work, but the output reports those costs
as excluded.

`null` means unknown, not zero. Known subtotals remain visible, but savings and
break-even are suppressed if either architecture has an unpriced item. Allocation
is suppressed only for the incomplete architecture. The calculator can't detect
an expense that's left out entirely.

Rates are intentionally external to the code because Azure prices vary by
region, currency, agreement, operating system, purchase model, and date. The SKU
rates in the example are illustrative. Obtain current rates from:

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

## Interpret results

For each SKU, the calculator reports total cost, Foundry savings, and the
monthly sandbox-hour break-even point where hosted runtime equals that VM
scenario. Positive Foundry savings means the hosted infrastructure is less
expensive, and a negative value means it carries a premium under those assumptions.
Architecture-specific model and tool charges are included in savings and
break-even calculations, along with additional platform items.

The break-even calculation varies sandbox hours only: AI consumption and every
other cost are held constant. It isn't a workload-scaling prediction. Allocated
cost per review is an average including idle capacity and failed attempts, not
the marginal cost of one more request. Estimating marginal cost requires measured
per-flow token, runtime, and metered dependency usage.

Self-hosted and managed models can differ in quality, safety, and throughput.
Treat the calculator output as one input to an architecture decision.

## Related content

- [Reference-environment budget and rates](platform-rates.md)
- [Demo guide](../docs/demos.md)
- [Foundry evaluation guide](../evaluations/README.md)

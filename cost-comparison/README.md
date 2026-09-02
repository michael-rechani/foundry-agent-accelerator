# IaaS VM versus Foundry hosted-agent costs

This calculator compares the hosting layer for the same agent workload:

- **IaaS:** continuously or selectively running Azure VMs, managed disks,
  monitoring, egress, and estimated operations labor.
- **Foundry hosted agents:** aggregate active sandbox CPU and memory time,
  persistent session storage, monitoring, and egress.

Model token and tool charges are shown as a shared workload cost because they
normally apply regardless of whether orchestration runs on a VM or in a hosted
agent. Move a charge into one side only if the architectures genuinely use
different models or tools.

This is a hosting-layer comparison, not a complete Azure bill. Add costs for
Foundry project dependencies such as Search, Cosmos DB, Storage, Key Vault, and
Log Analytics when those resources differ between the architectures.

## Use

1. Copy `scenario.example.json`.
2. Replace every illustrative rate with the current rate for your agreement,
   currency, region, VM SKU, and Foundry sandbox size.
  Update `rates_last_reviewed` whenever assumptions are refreshed.
3. Estimate aggregate hosted sandbox hours, including the configured idle
   timeout. For example, 1,000 sessions consuming an average of 0.4 billable
   hours each equals 400 sandbox hours.
4. Run:

```powershell
python calculator.py scenario.example.json
```

Rates are intentionally external to the code because Azure prices vary by
region, currency, agreement, and date. Obtain current rates from:

- [Azure Pricing Calculator](https://azure.microsoft.com/pricing/calculator/)
- [Foundry Agent Service pricing](https://azure.microsoft.com/pricing/details/foundry-agent-service/)
- [Azure Retail Prices API](https://learn.microsoft.com/rest/api/cost-management/retail-prices/azure-retail-prices)

## Formula summary

```text
VM infrastructure =
  VM count * monthly running hours * VM hourly rate
  + managed disks + monitoring + egress + operations labor

Hosted-agent infrastructure =
  aggregate sandbox hours
  * (sandbox vCPU * vCPU-hour rate + sandbox GiB * GiB-hour rate)
  + session storage + monitoring + egress

Shared AI consumption =
  input tokens / 1,000,000 * input rate
  + output tokens / 1,000,000 * output rate
  + tool usage
```

The calculator also reports the monthly sandbox-hour break-even point where
hosted runtime equals VM infrastructure cost. It excludes qualitative benefits
such as managed scaling, identity, isolation, observability, session
persistence, and reduced operational risk; evaluate those separately.


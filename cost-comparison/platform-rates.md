# Deployed platform budget and rates

[Cost model](README.md) / Platform rates

Retrieved from the [Azure Retail Prices API](https://prices.azure.com/api/retail/prices)
on **2026-09-05**, using API version `2023-01-01-preview`, USD consumption prices,
and the resource's region or Global meter region. These are public rates, not an agreement quote
or measured bill. Both selected records identify a primary meter region.

| Resource | Exact product / meter | USD/hour | Assumed hours | Estimated month | Rate effective |
| --- | --- | ---: | ---: | ---: | --- |
| One APIM Standard v2 unit | API Management / Standard v2 Unit | 0.9589 | 730 | $700.00 | 2024-03-01 |
| One Windows B2s jumpbox | Virtual Machines BS Series Windows / B2s | 0.0576 | 730 | $42.05 | 2025-10-01 |

The original example's combined capacity estimate is **$742.05/month**, before OS disk, NAT, public IP,
private endpoints/DNS, transfer, project dependencies, hosted runtime, model
tokens, tools, monitoring, operations labor, and applicable additional API calls.
This is a partial planning baseline, not a minimum invoice or total platform cost.

The separately deployed workbench adds 400 RU/s of dedicated Cosmos container
throughput. The North Central US public retail `100 RU/s` meter was USD 0.008/hour
when retrieved on 2026-09-05 UTC: `4 * 0.008 * 730 = USD 23.36/month`.
The original comparison example includes this amount and unpriced workbench storage,
backup, Container Apps, and registry/build entries. Its known platform subtotal
is now USD 765.41/month, still incomplete and not an invoice. The Foundry Cosmos
entry excludes this workbench allocation to avoid double counting.

The [deployed scenario](scenario.deployed.json) adds itemized coverage for the
current private platform. It accepts quantities and rates, calculates their
products, and prints its assumptions. Metadata does not perform live price lookups.
Use actual calendar hours when evaluating a specific billing month. The VM
estimate assumes no deallocation schedule, reservation, savings plan, or Azure
Hybrid Benefit. Confirm its deployed SKU before using it as an actual forecast.

## Reproduce the selection

Query the retail API with these OData filters, following `NextPageLink` if present:

```text
serviceName eq 'API Management' and armRegionName eq 'westus' and priceType eq 'Consumption'

serviceName eq 'Virtual Machines' and armRegionName eq 'westus' and armSkuName eq 'Standard_B2s' and priceType eq 'Consumption'
```

Select the exact products/meters in the table. Do not substitute APIM secondary
units, workspace packs, self-hosted gateways, Linux VMs, Spot, or Low Priority
rates. APIM call meters have tiers; estimate their charges separately from
capacity using the applicable included allowance and billing rules.

## Deployed budget

APIM is disabled. The deployed scenario assigns it zero capacity hours, reducing
the steady-state monthly budget by $700.00 to **$1,584.76**. Earlier accrued charges
are not erased. The original comparison example above retains APIM assumptions
for comparison and is not the current deployment budget.

| Item | Verified unit rate | Budget quantity |
| --- | ---: | --- |
| Standard HDD S10 | $5.888/month | One 127-GiB disk |
| NAT gateway, Global | $0.045/hour plus $0.045/GB | 730 hours, 100 GB |
| Standard IPv4 public IP | $0.005/hour | 730 hours |
| Private endpoints, Global | $0.01/hour plus $0.01/GB first tier | Eight endpoints, 100 GB total processed |
| Private DNS | $0.50/zone-month plus $0.40/million queries | Thirteen zones, one million queries |
| Search S1 | $0.336/search-unit-hour | Two replicas, one partition, 730 hours |
| Cosmos autoscale AP1 100 RUs | $0.012/100-RU/s-hour | Six containers at 100 RU/s minimum |
| Cosmos data and continuous 30-day backup | $0.25 and $0.20/GB | 10 GB each |
| Container Apps active CPU | $0.000024/vCPU-second | 0.5 vCPU for 730 hours |
| Container Apps memory | $0.000003/GiB-second | 1 GiB for 730 hours |
| Container Apps requests | $0.40/million | One million; no shared free grant assumed |
| Premium ACR | $1.6666/day | 730 / 24 days |
| Key Vault operations | $0.03/10,000 | 10,000 operations |
| Log Analytics ingestion | $2.76/billable GB | 10 GB beyond shared free allowance |

Unlike the original example, the deployed budget assumes only 20 jumpbox running
hours. Cosmos sustained maximum throughput on all six autoscale containers adds
$473.04/month. Cosmos storage and monitoring are each counted once across the
platform and Lab; the separate hosted monitoring field is zero.

Explicit allowances cover private build VM time and excess registry storage ($5),
Storage/disk operations including shared state ($10), cross-region peering ($3),
and alerts/security/optional metered features ($30). These are planning allowances,
not measured usage or sourced unit-price calculations. Labor is two hours at
$100/hour, not an Azure charge.

A separate $87.60 contingency covers a possible Container Apps environment
feature meter at $0.12/hour. Applicability is unverified: this is not a confirmed
charge. Model tokens, hosted runtime and tools remain illustrative workload inputs.
No measured review count, invoice total, or equivalent-IaaS savings is claimed.

```powershell
python cost-comparison/calculator.py cost-comparison/scenario.deployed.json
```

## Actual cost reconciliation

A resource-group MonthToDate ActualCost query grouped by day, service, and
location returned **HTTP 429**. No actual-spend result was obtained.
Retry through Cost Management after the service's throttling window. Do not
interpret the failed query as zero spend or extrapolate these capacity estimates
into an actual monthly bill. Actual usage can arrive late and a newly deployed
environment is not yet a stable representative month.

## Cleanup candidates

- APIM is disabled; redeploy only when gateway testing is needed. Review its
  network requirements and current pricing before enabling it again.
- Deallocating the jumpbox reduces VM compute charges but retains disk, NAT,
  public IP, and other infrastructure costs. Schedule it only after accounting
  for deployment tasks and management access.
- Retained agent versions and the separate profile coordinator need an explicit
  retirement decision. No recovery versions were deleted in this cleanup pass.
- The management VNet currently depends on `enable_jumpbox` and remains needed
  for private administration and builds. Do not remove it as part of APIM cleanup.
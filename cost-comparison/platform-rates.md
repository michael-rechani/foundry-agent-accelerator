# Reference-environment budget and rates

[Home](../README.md) / [Cost comparison](README.md) / Platform rates

This page explains the saved rate assumptions behind
`scenario.deployed.json`. It's for operators and architects who need to copy the
reference budget, refresh prices, or reconcile it with an approved scope.

> [!IMPORTANT]
> These are saved assumptions and operational notes for one reference
> environment, not a live inventory or requirements for every deployment. They
> don't establish current prices or actual spend. Verify quantities, rates, and
> resource usage before using this budget.

## In this guide

- [Snapshot scope](#snapshot-scope)
- [Recorded retail rates](#recorded-retail-rates)
- [Reproduce the selection](#reproduce-the-selection)
- [Deployed budget](#deployed-budget)
- [Actual cost reconciliation](#actual-cost-reconciliation)
- [Cleanup candidates](#cleanup-candidates)
- [Related content](#related-content)

## Snapshot scope

The filename [scenario.deployed.json](scenario.deployed.json) and its recorded
assumptions are retained for compatibility. References to "current deployment"
inside that snapshot describe its original context, not a current service check.
Copy it and verify quantities, prices, topology, and cost applicability for the
environment being evaluated.

## Recorded retail rates

The saved rates came from the [Azure Retail Prices API](https://prices.azure.com/api/retail/prices),
using USD consumption prices and the resource's region or Global meter region.
They are planning assumptions, not current quotes or a measured bill. Refresh
them for your agreement and region before making a cost decision.

| Resource | Exact product / meter | USD/hour | Assumed hours | Estimated month |
| --- | --- | ---: | ---: | ---: |
| One APIM Standard v2 unit | API Management / Standard v2 Unit | 0.9589 | 730 | $700.00 |

Azure API Management (APIM) capacity in the original example is
**$700.00/month**, before operational compute, disk, network address translation
(NAT), public IP, private endpoints/DNS, transfer, project dependencies, hosted
runtime, model tokens, tools, monitoring, operations labor, and applicable
additional API calls. This is a partial planning baseline, not a minimum invoice
or total platform cost.

The reference environment's separately deployed Lab adds 400 RU/s of
dedicated Cosmos container throughput. The North Central US public retail
`100 RU/s` meter uses the saved assumption of USD 0.008/hour:
`4 * 0.008 * 730 = USD 23.36/month`.
The original comparison example includes this amount and unpriced Lab storage,
backup, Container Apps, and registry/build entries. Its known platform subtotal
is USD 765.41/month under these assumptions, still incomplete and not an invoice.
The Foundry Cosmos entry excludes this Lab allocation to avoid double counting.

The [reference scenario](scenario.deployed.json) adds itemized coverage for the
recorded private-platform assumptions. It accepts quantities and rates, calculates
their products, and prints its assumptions. Metadata doesn't perform live price
lookups. Use actual calendar hours when evaluating a specific billing month.
Operational allowances remain in the calculator for accounting completeness, not
as required architecture components.

## Reproduce the selection

Query the retail API with these OData filters, following `NextPageLink` if present:

```text
serviceName eq 'API Management' and armRegionName eq 'westus' and priceType eq 'Consumption'

serviceName eq 'Virtual Machines' and armRegionName eq 'westus' and armSkuName eq 'Standard_B2s' and priceType eq 'Consumption'
```

Select the exact products/meters in the table. Don't substitute APIM secondary
units, workspace packs, self-hosted gateways, Linux virtual machines (VMs),
Spot, or Low Priority rates. APIM call meters have tiers; estimate their
charges separately from
capacity using the applicable included allowance and billing rules.

## Deployed budget

This historical reference budget records APIM as disabled and assigns it zero
capacity hours, reducing its steady-state monthly estimate by $700.00 to
**$1,584.76**. That doesn't erase earlier accrued charges or establish present
spend. The original comparison example above retains APIM assumptions for
comparison; neither file automatically follows live deployment changes.
Azure Container Registry (ACR) appears in the table as a retained budget item.

| Item | Recorded unit rate | Budget quantity |
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

Cosmos sustained maximum throughput on all six autoscale containers adds
$473.04/month. Cosmos storage and monitoring are each counted once across the
platform and Lab; the separate hosted monitoring field is zero.

Allowances cover private build VM time and excess registry storage ($5),
Storage/disk operations including shared state ($10), cross-region peering ($3),
and alerts/security/optional metered features ($30). These are planning allowances,
not measured usage or sourced unit-price calculations. Labor is two hours at
$100/hour, not an Azure charge.

A separate $87.60 contingency covers a possible Container Apps environment
feature meter at $0.12/hour. Applicability is unverified, so this isn't a confirmed
charge. Model tokens, hosted runtime and tools remain illustrative workload inputs.
No measured review count, invoice total, or equivalent-IaaS savings is claimed.

```powershell
python cost-comparison/calculator.py cost-comparison/scenario.deployed.json
```

## Actual cost reconciliation

A past resource-group MonthToDate ActualCost query for the reference environment,
grouped by day, service, and location, returned **HTTP 429**. No actual-spend
result was obtained or subsequently recorded here. This is a historical
observation, not a statement that Cost Management is currently unavailable.

For a new reconciliation, use an approved Cost Management query for the intended
scope and period, respecting any returned throttling guidance. Don't interpret
the failed query as zero spend or extrapolate these capacity estimates into an
actual monthly bill. Actual usage can arrive late, and a newly deployed
environment isn't yet a stable representative month.

## Cleanup candidates

These are retained operator notes, not a cleanup instruction or a current
resource inventory. Get a fresh inventory and specific approval before acting.

- The reference budget records APIM as disabled. Enable it only for a scoped
  gateway requirement after reviewing networking and current pricing.
- Inventory retained agent versions and the separate profile coordinator before
  deciding what to retire. Preserve recovery targets. This documentation edit
  deleted no resources or versions.
- Preserve private networking required for administration and builds. Removing
  an optional gateway doesn't establish that shared networking is unused.

## Related content

- [Cost comparison](README.md)
- [Reference scenario](scenario.deployed.json)

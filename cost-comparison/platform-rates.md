# Private platform rate snapshot

[Cost model](README.md) / Platform rates

Retrieved from the [Azure Retail Prices API](https://prices.azure.com/api/retail/prices)
on **2026-09-04**, using API version `2023-01-01-preview`, USD consumption prices,
and `armRegionName eq 'westus'`. These are public rates, not an agreement quote
or measured bill. Both selected records identify a primary meter region.

| Resource | Exact product / meter | USD/hour | Assumed hours | Estimated month | Rate effective |
| --- | --- | ---: | ---: | ---: | --- |
| One APIM Standard v2 unit | API Management / Standard v2 Unit | 0.9589 | 730 | $700.00 | 2024-03-01 |
| One Windows B2s jumpbox | Virtual Machines BS Series Windows / B2s | 0.0576 | 730 | $42.05 | 2025-10-01 |

Combined capacity estimate: **$742.05/month**, before OS disk, NAT, public IP,
private endpoints/DNS, transfer, project dependencies, hosted runtime, model
tokens, tools, monitoring, operations labor, and applicable additional API calls.
This is a partial planning baseline, not a minimum invoice or total platform cost.

The separately deployed workbench adds 400 RU/s of dedicated Cosmos container
throughput. The North Central US public retail `100 RU/s` meter was USD 0.008/hour
when retrieved on 2026-09-05 UTC: `4 * 0.008 * 730 = USD 23.36/month`.
The scenario includes this amount and separate unpriced workbench storage,
backup, Container Apps, and Basic ACR/build entries. Its known platform subtotal
is now USD 765.41/month, still incomplete and not an invoice. The Foundry Cosmos
entry excludes this workbench allocation to avoid double counting.

The calculator consumes the monthly amounts in the scenario. The hourly rate,
meter, region, date, and source fields are provenance, not live price lookups.
If hours or rates change, recalculate the corresponding monthly amounts.
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

The West US NAT queries did not return matching meters in this check. NAT and
other unresolved entries remain `null`, not zero, in the scenario. Complete
them using verified regional prices and measured quantities; do not silently
substitute another region.

## Actual cost reconciliation

A resource-group MonthToDate ActualCost query grouped by day, service, and
location returned **HTTP 429** on 2026-09-04. No actual-spend result was obtained.
Retry through Cost Management after the service's throttling window. Do not
interpret the failed query as zero spend or extrapolate these capacity estimates
into an actual monthly bill. Actual usage can arrive late and a newly deployed
environment is not yet a stable representative month.

## Cleanup candidates

- APIM is billed even while no API is published. Keep it for the pending private
  backend acceptance test; removal and recreation require a reviewed plan and
  interrupt the gateway. Do not downgrade without checking network capabilities.
- Deallocating the jumpbox reduces VM compute charges but retains disk, NAT,
  public IP, and other infrastructure costs. Schedule it only after accounting
  for deployment tasks and management access.
- Retained agent versions and the separate profile coordinator need an explicit
  retirement decision. No recovery versions were deleted in this cleanup pass.
- The management VNet currently depends on `enable_jumpbox`. Do not turn that
  flag off while APIM uses its subnet; decouple network ownership first if the
  jumpbox is to be retired permanently.
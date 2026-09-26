# Optional integrations

[Home](../README.md) / [Docs](README.md) / Optional integrations

Use this guide to understand integration paths that sit outside the core demo.
The core experience is the Lab calling Foundry with fictional data and no live
customer-system integration.

> [!IMPORTANT]
> These integrations are outside the core demo and are not engagement
> deliverables. No live customer-system, Microsoft 365 (M365), Copilot, or
> SharePoint integration is part of the core experience. Customer-system
> integration and production deployment require separate scoping and agreement.

The Lab calls Foundry directly. Its review agents use supplied request material;
they don't currently expose an Azure API Management (APIM) route or call an
Azure AI Search retrieval tool. Optional integrations can be added without
replacing the Lab or its agent delegation.

For website ingress rather than API publication, see the
[Application Gateway and Front Door guide](ingress-access.md). Those gateways are
optional design guidance, not deployed resources or replacements for APIM policy.

## Integration summary

| Integration | Status | What it needs | Link |
| --- | --- | --- | --- |
| Core Lab-to-Foundry path | Included in the demo. No customer-system, M365, Copilot, or SharePoint integration is included. | Fictional inputs, private access, and human review of every finding. | [Demo guide](demos.md) |
| Governed review API through APIM | Retained implementation, disabled by default, and removed from Azure in the current environment. | Standard v2 APIM, reviewed Terraform inputs, Microsoft Entra ID audience and allowlists, private backend connectivity, and live acceptance tests. | [Governed review API](apim-review-api.md) |
| Search-backed retrieval for review agents | Backing Azure AI Search service is retained, but no retrieval tool is attached to the current review agents. | A knowledge source, index, permissions, tool binding or explicit retrieval code, citations, and relevance and security testing. | [Add Search-backed retrieval](#add-search-backed-retrieval) |
| Website ingress with Application Gateway or Front Door | Design guidance only. No gateway is deployed by this repository. | Separate gateway, Domain Name System (DNS), certificate, application-authentication, web application firewall (WAF), diagnostics, and cost approval. | [Application ingress options](ingress-access.md) |
| Customer-system or M365/Copilot/SharePoint integration | Outside the core experience and not a promised deliverable. | Separate scope, agreement, architecture, data handling, identity, authorization, and production readiness plan. | [Scope and limitations](../README.md#scope-and-limitations) |

## Current configuration

| Component | Current state | Retained implementation |
| --- | --- | --- |
| APIM | Removed from Azure; active publisher settings removed. `enable_api_management` defaults to `false`; `review_api` defaults to `null`. | [Gateway Terraform](../terraform/apim.tf), [input definitions](../terraform/variables.tf), and [publication runbook](apim-review-api.md) |
| Azure AI Search | Still deployed and connected to the Foundry project through the Agent Service bring-your-own resource (BYOR) configuration. Not attached as a retrieval tool to the current review agents. | [Foundry Terraform](../terraform/main.tf): `ai_search_definition` and `ai_projects.primary.ai_search_connection` |

The Search retrieval tool is optional. The backing Search service is not optional
for this secured standard/bring-your-own (BYO) Foundry setup. Microsoft's
[private networking requirements](https://learn.microsoft.com/azure/foundry/agents/how-to/virtual-networks)
require Search, Storage, and Cosmos connections. Terraform supplies Search
through the project's capability host `vectorStoreConnections`.
`enable_agent_service` controls its creation alongside other Agent Service
dependencies. Don't disable Agent Service or remove its Search definition just
because an agent doesn't query it. No Search service, indexes, connections, or
data were removed by the APIM cleanup.

## Add an APIM gateway

1. Review current pricing and private backend networking. The retained gateway
   uses Standard v2. Basic and Basic v2 can't reach this virtual network
   (VNet)-isolated backend.
2. Supply non-secret local Terraform inputs:

   ```hcl
   enable_api_management          = true
   api_management_publisher_email = "platform-owner@example.com"
   ```

3. Keep `review_api = null` until approved Microsoft Entra ID audience and caller
   allowlists are available. Follow the [governed review API runbook](apim-review-api.md)
   to configure and publish the route.
4. Review a full Terraform plan through the private runner. Preserve the existing
   management VNet, state backend, and the Lab. APIM soft-delete recovery is
   retained. Check name recovery before recreating the service. Don't
   automatically purge.
5. Verify gateway-to-Foundry private DNS, managed identity, authorization
   failures, timeouts, and live specialist receipts before switching any client
   traffic.

## Add Search-backed retrieval

1. Inventory the existing service's indexes, indexers, data sources, project
   connections, and role assignments through approved private access. Check which
   managed Foundry features depend on the existing connection.
2. Define the knowledge source, update frequency, retention, document
   permissions, and citation requirements. Prefer a dedicated index for the new
   use case.
3. Use the existing private endpoint and managed identity. Grant only the data
   roles required by the indexer and querying agent. Don't enable public access
   or copy service keys into Terraform or application settings.
4. Choose the supported Foundry AI Search tool or implement explicit retrieval in
   the hosted agent. A project connection alone doesn't make an agent search.
   Configure the index and tool binding, then deploy a new immutable agent
   version. The [knowledge retrieval design](knowledge-retrieval.md) compares
   both and includes a flag-gated, read-only case-agent tool that is off by
   default.
5. Test retrieval relevance, citations, missing evidence, document authorization,
   and prompt injection in retrieved content. Benchmark capacity before changing
   replicas or tier. Update the [deployed budget](../cost-comparison/scenario.deployed.json).

## Cost and capacity notes

Cost optimization should size the existing Search service, not remove a required
connection. The Azure Verified Modules (AVM) default is S1 with two replicas and
one partition, not evidence of measured workload demand. Validate usage, feature
limits, and regional tier-change eligibility before reducing capacity. One
replica loses the query availability service-level agreement (SLA). Two replicas
support query availability, while three are needed for query and indexing SLA
coverage. See [Search capacity planning](https://learn.microsoft.com/azure/search/search-capacity-planning).

Changing the Foundry backing-resource architecture is a separate migration, not a
routine Search deletion. The deployed budget continues to include Search
capacity.

Use [Microsoft's APIM tier comparison](https://learn.microsoft.com/azure/api-management/api-management-features)
and [Azure AI Search documentation](https://learn.microsoft.com/azure/search/)
to check current capabilities. Root Terraform remains local-only under the
repository's current publishing boundary. Links here are workspace references,
not a claim that the latest local Terraform changes have been published.

## Related content

- [Governed review API](apim-review-api.md)
- [Extension guide](architecture-assessment.md)
- [Knowledge retrieval design](knowledge-retrieval.md)
- [Cost comparison](../cost-comparison/README.md)
- [Infrastructure](../terraform/README.md)

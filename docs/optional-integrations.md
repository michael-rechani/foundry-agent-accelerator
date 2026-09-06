# Optional integrations

[Overview](../README.md) / Optional integrations

The Lab calls Foundry directly. Its review agents use supplied request material;
they do not currently expose an APIM route or call an AI Search retrieval tool.
These integrations can be added without replacing the Lab or its agent delegation.

## Current configuration

| Component | Current state | Retained implementation |
| --- | --- | --- |
| APIM | Removed from Azure; active publisher settings removed. `enable_api_management` defaults to `false`; `review_api` defaults to `null`. | [Gateway Terraform](../terraform/apim.tf), [input definitions](../terraform/variables.tf), and [publication runbook](apim-review-api.md) |
| AI Search | Still deployed and connected to the Foundry project through the Agent Service BYOR configuration. Not attached as a retrieval tool to the current review agents. | [Foundry Terraform](../terraform/main.tf): `ai_search_definition` and `ai_projects.primary.ai_search_connection` |

Search is not independently optional in the current platform configuration:
`enable_agent_service` controls its creation alongside other Agent Service
dependencies. Do not disable Agent Service or remove its Search definition just
to stop retrieval usage. That can plan deletion of platform resources. No Search
service, indexes, connections, or data were removed by this configuration cleanup.

## Add an APIM gateway

1. Review current pricing and private backend networking. The retained gateway
   uses Standard v2; Basic and Basic v2 cannot reach this VNet-isolated backend.
2. Supply non-secret local Terraform inputs:

   ```hcl
   enable_api_management          = true
   api_management_publisher_email = "platform-owner@example.com"
   ```

3. Keep `review_api = null` until approved Entra audience and caller allowlists
   are available. Follow the [governed review API runbook](apim-review-api.md)
   to configure and publish the route.
4. Review a full Terraform plan through the private runner. Preserve the existing
   management VNet, state backend and Lab. APIM soft-delete recovery is retained;
   check name recovery before recreating the service. Do not automatically purge.
5. Verify gateway-to-Foundry private DNS, managed identity, authorization failures,
   timeouts, and live specialist receipts before switching any client traffic.

## Add Search-backed retrieval

1. Inventory the existing service's indexes, indexers, data sources, project
   connections and role assignments through approved private access. Check which
   managed Foundry features depend on the existing connection.
2. Define the knowledge source, update frequency, retention, document permissions
   and citation requirements. Prefer a dedicated index for the new use case.
3. Use the existing private endpoint and managed identity. Grant only the data
   roles required by the indexer and querying agent; do not enable public access
   or copy service keys into Terraform or application settings.
4. Choose the supported Foundry AI Search tool or implement explicit retrieval in
   the hosted agent. A project connection alone does not make an agent search.
   Configure the index and tool binding, then deploy a new immutable agent version.
5. Test retrieval relevance, citations, missing evidence, document authorization,
   and prompt injection in retrieved content. Benchmark capacity before changing
   replicas or tier; update the [deployed budget](../cost-comparison/scenario.deployed.json).

Removing or independently toggling the platform Search service is a separate
change: verify managed-service requirements, preserve any index data, decouple its
Terraform ownership and project connection, and review the destruction plan before
applying. The current budget continues to include Search capacity.

Use [Microsoft's APIM tier comparison](https://learn.microsoft.com/azure/api-management/api-management-features)
and [Azure AI Search documentation](https://learn.microsoft.com/azure/search/)
to check current capabilities. Root Terraform remains local-only under the
repository's current publishing boundary; links here are workspace references,
not a claim that the latest local Terraform changes have been published.
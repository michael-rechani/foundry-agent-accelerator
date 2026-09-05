# Terraform deployment

This configuration uses the verified
[`Azure/avm-ptn-aiml-ai-foundry/azurerm`](https://registry.terraform.io/modules/Azure/avm-ptn-aiml-ai-foundry/azurerm/latest)
pattern module. The module deploys the Foundry account, project, model
deployment, Agent Service capability host, and the supporting services needed
by the standard Agent Service setup.

The optional client gateway uses the verified
[`Azure/avm-res-apimanagement-service/azurerm`](https://registry.terraform.io/modules/Azure/avm-res-apimanagement-service/azurerm/latest)
resource module pinned to version 0.9.0.

The default names identify their purpose directly: the account uses
`foundry-hosted-agents-<base>-<environment>-<unique>` and the project uses
`hosted-agents-<environment>`.

## Prerequisites

- Terraform 1.16.1 or a later 1.16 patch release
- Azure CLI authenticated to the target tenant
- Contributor and User Access Administrator, or equivalent permissions
- Model availability and quota in the target region
- Network connectivity to the deployed virtual network, such as VPN or
	ExpressRoute, for SDK access after public endpoints are disabled

Confirm the selected subscription before deployment:

```powershell
az account show --query "{name:name,id:id,tenantId:tenantId}" --output table
```

Set that subscription ID explicitly. The configuration requires an explicit ID
so a changed Azure CLI default cannot redirect a deployment.

## Region preference

The tracked `region-preferences.tf` file defines the verified deployment order.
North Central US is the current default. The listed regions were checked for
GPT-4.1 `2025-04-14` Global Standard, Agent Service `agentsV2`, Azure AI Search
Standard quota, Microsoft.App support, and the absence of location-restricting
Azure Policy in the Lab subscription on 2026-09-03.

| Preference | Region | Cosmos DB paired region |
| --- | --- | --- |
| 1 | North Central US (`northcentralus`) | None for development |
| 2 | West US 3 (`westus3`) | None for development |
| 3 | South Central US (`southcentralus`) | North Central US |
| 4 | West US (`westus`) | None for development |

Azure AI Search physical capacity is dynamic and cannot be guaranteed by its
quota API. Override the default for a specific deployment with
`-var="location=westus3"`; subscription-specific tfvars remain ignored.
The preference profile also selects region-compatible storage replication and
Cosmos DB topology. North Central US uses LRS storage and a single non-zonal
Cosmos region because this subscription currently lacks capacity for the
paired South Central US addition.
Existing resource groups retain their original location metadata during a
region change, while regional workload resources are replaced in the selected
region. This avoids cascading deletion of unchanged global resources.

## Private jumpbox access

The configuration creates a Windows Server jumpbox in a small West US
management virtual network. North Central US currently has no VM SKU capacity
for this subscription, so global virtual network peering connects the jumpbox
to the North Central US workload network. The Foundry private DNS zones are
linked to both networks. The VM has no public IP address. A NAT Gateway attached
only to the jumpbox subnet provides explicit outbound access so the VM can load
the Foundry portal while Foundry data-plane endpoints stay private.

Use Azure Bastion Developer to connect. North Central US supports this free
development tier, and its single-VM, portal-only connection model fits this
sample. A paid dedicated Bastion host and `AzureBastionSubnet` are unnecessary
unless the environment needs concurrent sessions, peered-VNet access, native
RDP, file transfer, or production support.

Terraform stores the generated local administrator password in the existing
private Foundry Key Vault and grants the deploying principal the Key Vault
Secrets Officer role. Terraform outputs only the non-secret lookup values:

Key Vault is the retrieval location, not the only copy of this password.
The `random_password` resource, VM configuration, and VMAccess protected settings
also persist the value in Terraform state; saved plans and historical state
versions can contain it too. Sensitive-value redaction does not remove it.
Use an encrypted remote backend with narrowly scoped access, protect state
history and saved plans as credentials, and never commit or publish them.
Do not use local state for this credential-bearing deployment.

A strict Key-Vault-only requirement needs a separate credential-provisioning
migration that avoids Terraform-managed secret values. Moving the current value
to Key Vault alone does not remove existing copies. Rotate the credential after
migration and handle old state/plan copies under the environment's retention
policy; do not delete active state to remove a secret.

See the [staged credential migration](../docs/credential-migration.md) for verified
provider capabilities, ownership-transfer prerequisites, and acceptance gates.

```powershell
terraform output -raw jumpbox_name
terraform output -raw jumpbox_admin_username
terraform output -raw jumpbox_key_vault_name
terraform output -raw jumpbox_admin_password_secret_name
```

Retrieve the secret value through Key Vault only from a network-connected
administrative workstation. In the Azure portal, open the VM, select
**Connect** > **Bastion**, choose password authentication, and connect. The
first connection activates Bastion Developer on the virtual network. From the
remote desktop, open Microsoft Edge and browse to `https://ai.azure.com`.

The jumpbox, OS disk, NAT Gateway, and NAT public IP incur charges even when no
RDP session is active. Deallocate the VM when it is idle. Set
`enable_jumpbox = false` to omit all jumpbox and NAT resources.

## API Management gateway

Set `enable_api_management = true` and provide
`api_management_publisher_email` to create a one-unit Standard v2 API
Management service in West US. APIM uses a dedicated delegated subnet in the
management virtual network and reaches private agent backends across the global
peering connection. Its system-assigned managed identity receives Foundry User
on the primary project, so APIM policies can use Microsoft Entra authentication
instead of storing Foundry keys.

APIM is the governed client-facing entry point for APIs that are explicitly
published there. It provides a stable endpoint for authentication, quotas,
rate limits, policy, versioning, and observability. Trusted internal agents can
continue calling other agents directly with managed identity when gateway
policy is not required. The configuration creates the service but does not
publish a placeholder API. The opt-in coordinator API and policy are implemented;
enable them only after the backend and caller authorization are verified.

Standard v2 is used because it supports outbound virtual network integration
to the private backends. The gateway remains publicly reachable for clients;
the integration subnet is not an inbound private endpoint. Management-plane
public network access also remains enabled so Terraform and portal operations
work without a separate private management endpoint.

Standard v2 is billed continuously, even with no API traffic. Set
`enable_api_management = false` in environments that do not need the gateway.
Azure Managed Redis and APIM semantic caching are deliberately excluded for
now because they are separate recurring-cost resources and are not required
for agent-to-agent communication.

After apply, inspect the deployed gateway with:

```powershell
terraform output -raw api_management_name
terraform output -raw api_management_id
terraform output -raw api_management_gateway_url
```

### Optional review API

After deploying and testing a coordinator, configure `review_api` to select its
named endpoint and explicit Entra audience, caller object IDs, and client app
IDs. The default is null: no API is published. See the
[publication runbook and acceptance gates](../docs/apim-review-api.md).

Run `./test-review-api-validation.ps1` for isolated input validation and rendered
policy checks. These tests do not contact Azure or validate the live gateway.

## Deploy

```powershell
$env:TF_VAR_subscription_id = "<subscription-id>"
terraform init
terraform plan -out main.tfplan
terraform apply main.tfplan
```

The configuration has no local-exec provisioners or hard-coded credentials.
It does generate and persist the jumpbox password as described above. Terraform
authenticates through the AzureRM provider's normal credential chain; for local
use, that is typically Azure CLI authentication.

The workload is private by default. Foundry, AI Search, Cosmos DB, Key Vault,
the workload storage account, and Log Analytics disable public data-plane
access and use private endpoints in the workload virtual network. Hosted Agent
Service uses a separate delegated subnet. The remote Terraform state storage
account is external to this configuration and remains reachable according to
its own network settings.

Terraform resource management still uses Azure Resource Manager. After apply,
run the hosted-agent deployment CLI and query Log Analytics only from a machine
that can resolve the private DNS zones and route to the workload virtual
network. The default address ranges can be overridden if they overlap with an
existing landing zone.

## State

Without a backend configuration Terraform defaults to local state. Configure a
secured remote backend before deploying the credential-bearing jumpbox, including
for development. Local state is unsuitable for a team or production deployment.

For a team environment, create an ignored `backend.tf` file with the secured,
pre-created state account settings:

```hcl
terraform {
	backend "azurerm" {
		resource_group_name  = "<state-resource-group>"
		storage_account_name = "<state-storage-account>"
		container_name       = "tfstate"
		key                  = "ai-foundry/dev.tfstate"
		use_azuread_auth     = true
		use_cli              = true
	}
}
```

```powershell
terraform init
```

If local state already contains resources, migrate it instead of initializing
an empty remote state:

```powershell
terraform init -migrate-state
```

Terraform prompts before copying local state. Confirm the destination account,
container, and key before accepting. `backend.tf` is ignored because backend
settings vary by environment. `use_cli` and `use_azuread_auth` make Terraform
use the authenticated Azure CLI session and authorize directly against the
Blob Storage data plane. The user needs the Storage Blob Data Contributor role
on the state container.

The dependency lock file should be committed and updated deliberately with
`terraform init -upgrade` after reviewing provider and module changes.

## Outputs

After apply, retrieve the exact values consumed by the hosted-agent deployer:

```powershell
terraform output -raw foundry_project_endpoint
terraform output -raw model_deployment_name
```


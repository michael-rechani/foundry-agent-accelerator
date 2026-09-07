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

The tracked `region-preferences.tf` file defines the default deployment order.
North Central US is the default. Check model availability, Agent Service support,
Search capacity, provider registration, and Azure Policy in the target subscription
before choosing a region. This list is configuration, not a capacity guarantee.

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
Cosmos DB topology. Cosmos uses the selected workload region as its primary region.
Changing regions is not an automatic migration: review account topology changes
and resource replacements separately. Deletion protection blocks replacement of
protected accounts; do not remove it merely to make a plan succeed. Resource groups
retain their original location metadata to avoid cascading deletion.

## Private access

Use an authorized execution environment with private DNS resolution and routing
to the Foundry data plane and remote state backend. ARM connectivity alone is
insufficient. Keep public access disabled and use scoped managed identities.

Necessary secrets belong in Key Vault, not ordinary Terraform attributes.
See the [credential guidance](../docs/credentials.md) for runtime access,
protected state, and credential recovery requirements.

## Optional administration resources

The Windows admin VM and its NAT egress are disabled by default. Enabling
`enable_jumpbox` adds them; they are not required by Foundry itself. The shared
management VNet, subnet, peering, and DNS links are defined separately in
`management-network.tf` and remain enabled for the Lab. Set
`enable_management_network = false` only when that network is not needed; enabling
the VM or APIM also enables the network.
APIM can use the shared management network without enabling the VM. Its region
must match `jumpbox_location`, which selects that network's region. Existing
Terraform addresses and network names are retained for compatibility.

For a new VM, pre-provision a strong Windows administrator password in an accessible
Key Vault and set `jumpbox_admin_secret` to its vault resource ID, secret name, and
explicit secret version. Do not supply the password in tfvars, CLI arguments, or
ordinary Terraform data sources. The deployment identity needs private DNS/routing
to the vault and permission to read that secret. Terraform reads it ephemerally and
passes it only through AzAPI write-only fields, without exporting secret responses.

Keep the pinned version unchanged during normal applies. A version change requests
a credential update in both the VM and access extension. This is not atomic:
retain an independent recovery channel and the prior vault version until login is
verified. After a partial failure, inspect each consumer before retrying; use the
same pinned version to avoid generating a different password during recovery.
Verify create, unchanged apply, rotation, and failure recovery on disposable
resources before using this path for a real deployment.

For an existing VM, set `enable_jumpbox = true` and preserve its disk ID, name, size,
and storage type in `jumpbox_existing_os_disk` in ignored deployment inputs.
The default `create_option = "FromImage"` preserves an image-provisioned VM's
configuration. Use `create_option = "Attach"` for a VM booting a retained specialized
Windows disk; this omits the image and OS provisioning profile and retains the
disk's existing login. Leave `jumpbox_admin_secret` null to leave credentials under
external Key Vault administration and omit the VMAccessAgent extension. If an
extension is already tracked, reconcile its ownership before changing this input;
do not bypass its destruction guard. Recreating a VM changes its system identity;
reconcile role assignments and Terraform state before the next apply.

## Existing deployments

Before adopting this configuration, preserve existing names with
`cosmosdb_account_name` and `agent_storage_account_name`. The storage override also
determines the Blob endpoint and connection names. Verify these match the existing
resources before applying; the naming defaults are for fresh installations.

This is steady-state configuration, without one-time resource ownership scripts.
An existing state must already use the resource addresses declared here. Stop if
a plan attempts to recreate an existing service or destroy an older owner; resolve
that installation's state separately. Preserve state and protected backups.

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
terraform -chdir=terraform output -raw api_management_name
terraform -chdir=terraform output -raw api_management_id
terraform -chdir=terraform output -raw api_management_gateway_url
```

### Optional review API

After deploying and testing a coordinator, configure `review_api` to select its
named endpoint and explicit Entra audience, caller object IDs, and client app
IDs. The default is null: no API is published. See the
[publication runbook and acceptance gates](../docs/apim-review-api.md).

Run `./terraform/test-review-api-validation.ps1` for isolated input validation and rendered
policy checks. These tests do not contact Azure or validate the live gateway.

## Local validation

After initializing the providers and modules, run from the repository root:

```powershell
./terraform/test-platform-validation.ps1
./terraform/test-publisher-validation.ps1
./terraform/test-review-api-validation.ps1
```

Use `-TerraformCommand <path-to-terraform>` when the required version is not on PATH.
The platform suite copies the account, naming, network, VM, and input configuration
into an isolated directory, uses provider mocks, and excludes deployment state,
backend settings, and tfvars. It checks region profiles, existing-name overrides,
credential input requirements, management networking, retained-disk bodies, and
credential-gated extension creation. A synthetic credential fixture replaces the
ephemeral Key Vault boundary, which Terraform provider mocks do not support.
These checks do not test live secret retrieval, VM creation, or rotation.
Run full `terraform validate` as well, and use the credential guide's disposable
resource checks before relying on a new credential path.

## Deploy

Run commands from the repository root in one PowerShell session. The
[baseline quick start](../README.md#quick-start) covers initial setup. Each
command must succeed before you continue. Terraform provisions infrastructure;
publishing agent code and building the Lab image are separate operations.

### 1. Configure inputs and state

Review your local `terraform.tfvars`: explicit workload subscription, names,
region, model capacity, and network ranges. Configure a pre-created backend as
described in [State](#state). Authenticate before running Terraform; keep
credentials out of configuration. Preserve existing values and state ownership.

### 2. Initialize and validate

```powershell
terraform -chdir=terraform init
terraform -chdir=terraform validate
```

For a deliberate state migration, follow [State](#state) instead of plain init.
Never initialize empty state for resources already managed in another state.

### 3. Plan and review

```powershell
$plan = Join-Path $env:TEMP ("foundry-" + [guid]::NewGuid().ToString("N") + ".tfplan")
terraform -chdir=terraform plan -var-file=terraform.tfvars "-out=$plan"
terraform -chdir=terraform show "$plan"
```

Stop on any error. Confirm the target subscription, expected costs, and every
resource action. Investigate unexpected replacements or deletions before applying.

### 4. Apply the approved plan

A saved plan applies without another Terraform confirmation prompt. Run this
block only after review; cleanup removes the disposable plan even if apply fails.

```powershell
try {
	terraform -chdir=terraform apply "$plan"
	if ($LASTEXITCODE -ne 0) { throw "Apply failed; inspect state before replanning" }
} finally {
	Remove-Item -LiteralPath $plan -Force -ErrorAction SilentlyContinue
}
```

If planning fails or the plan is abandoned, run
`Remove-Item -LiteralPath $plan -Force -ErrorAction SilentlyContinue` as well.
Preserve state and protected backups; never keep plans as deployment history.

### 5. Verify outputs

Use the [Outputs](#outputs) commands after a successful apply. Resource outputs
are not proof of agent health; follow the private deployment runbook for live tests.

The configuration has no local-exec provisioners or hard-coded credentials.
Terraform authenticates through the AzureRM provider's normal credential chain; for local
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
secured remote backend before deploying infrastructure, including
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
terraform -chdir=terraform init
```

If local state already contains resources, migrate it instead of initializing
an empty remote state:

```powershell
terraform -chdir=terraform init -migrate-state
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
terraform -chdir=terraform output -raw foundry_project_endpoint
terraform -chdir=terraform output -raw model_deployment_name
```


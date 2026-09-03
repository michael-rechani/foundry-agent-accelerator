# Terraform deployment

This configuration uses the verified
[`Azure/avm-ptn-aiml-ai-foundry/azurerm`](https://registry.terraform.io/modules/Azure/avm-ptn-aiml-ai-foundry/azurerm/latest)
pattern module. The module deploys the Foundry account, project, model
deployment, Agent Service capability host, and the supporting services needed
by the standard Agent Service setup.

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

## Deploy

```powershell
$env:TF_VAR_subscription_id = "<subscription-id>"
terraform init
terraform plan -out main.tfplan
terraform apply main.tfplan
```

The configuration deliberately has no local-exec provisioners, credentials,
or access keys. Terraform authenticates through the AzureRM provider's normal
credential chain; for local use, that is typically Azure CLI authentication.

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

Local state is the default so the sample quick start works without pre-existing
infrastructure. Local state is unsuitable for a team or production deployment.

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


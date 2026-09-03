# Terraform deployment

This configuration uses the verified
[`Azure/avm-ptn-aiml-ai-foundry/azurerm`](https://registry.terraform.io/modules/Azure/avm-ptn-aiml-ai-foundry/azurerm/latest)
pattern module. The module deploys the Foundry account, project, model
deployment, Agent Service capability host, and the supporting services needed
by the standard Agent Service setup.

## Prerequisites

- Terraform 1.9 or later
- Azure CLI authenticated to the target tenant
- Contributor and User Access Administrator, or equivalent permissions
- Model availability and quota in the target region

Confirm the selected subscription before deployment:

```powershell
az account show --query "{name:name,id:id,tenantId:tenantId}" --output table
```

Copy that subscription ID into `terraform.tfvars`. The configuration requires
an explicit ID so a changed Azure CLI default cannot redirect a deployment.

## Deploy

```powershell
Copy-Item terraform.tfvars.example terraform.tfvars
terraform init
terraform plan -out main.tfplan
terraform apply main.tfplan
```

The configuration deliberately has no local-exec provisioners, credentials,
or access keys. Terraform authenticates through the AzureRM provider's normal
credential chain; for local use, that is typically Azure CLI authentication.

The default creates public endpoints so the sample can be deployed without an
existing network landing zone. Treat it as a development baseline. The AVM
module documentation describes the production BYOR and private endpoint
inputs.

## State

Local state is the default so the sample quick start works without pre-existing
infrastructure. Local state is unsuitable for a team or production deployment.

For a team environment, copy the opt-in backend declaration and configuration,
then replace the placeholders with a secured, pre-created state account:

```powershell
Copy-Item backend.azurerm.tf.example backend.azurerm.tf
Copy-Item backend.azurerm.hcl.example backend.azurerm.hcl
terraform init -backend-config=backend.azurerm.hcl
```

If local state already contains resources, migrate it instead of initializing
an empty remote state:

```powershell
terraform init -migrate-state -backend-config=backend.azurerm.hcl
```

Terraform prompts before copying local state. Confirm the destination account,
container, and key before accepting. The generated `backend.azurerm.tf` and
`backend.azurerm.hcl` files are ignored because backend settings vary by
environment. The example contains no credentials; `use_cli` and
`use_azuread_auth` make Terraform use the authenticated Azure CLI session and
authorize directly against the Blob Storage data plane. The user needs the
Storage Blob Data Contributor role on the state container.

The dependency lock file should be committed and updated deliberately with
`terraform init -upgrade` after reviewing provider and module changes.

## Outputs

After apply, retrieve the exact values consumed by the hosted-agent deployer:

```powershell
terraform output -raw foundry_project_endpoint
terraform output -raw model_deployment_name
```


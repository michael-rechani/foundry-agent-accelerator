# Terraform state backend

[Home](../../README.md) / [Infrastructure](../README.md) / State backend

Creates the private Azure Storage account and container that hold every other
root's Terraform state, so a fresh subscription needs no hand-made backend.
Run it once, before the platform root.

## At a glance

| Setting | Value |
| --- | --- |
| Creates | Resource group, a small VNet with one private-endpoint subnet, a private DNS zone, the state account with its private endpoint, and one container. |
| Access | Microsoft Entra only. Shared keys, anonymous access and public network access are off, and TLS 1.2 is required. |
| Protection | Versioning, 90-day blob soft-delete, seven-day container soft-delete, and `prevent_destroy`. |
| Cost | A ZRS storage account and one private endpoint. No public IP. |
| Its own state | Starts local, then migrates into the container it creates. |

## Deploy

1. Copy `dev.tfvars.example` to an ignored `dev.tfvars` and set your
   subscription. Set `peered_virtual_network_ids` to the VNets that run
   Terraform, such as the management or CI runner VNet. They get two-way
   peering and a link to the blob private DNS zone.
2. Run from this directory, then review the saved plan before applying:

   ```powershell
   terraform init
   terraform plan -var-file=dev.tfvars -out=bootstrap.tfplan
   terraform show bootstrap.tfplan
   terraform apply bootstrap.tfplan
   Remove-Item bootstrap.tfplan
   ```

3. Read the settings other roots need:

   ```powershell
   terraform output -raw backend_hcl
   ```

   Save that, with the right `key` for each root, as that root's ignored
   `backend.hcl`.

## Private access

The account has no public endpoint, so a machine must reach it through the
state VNet. Apply from a host on a peered network. Creating the account doesn't
need data-plane access, so the first apply works from anywhere with Azure
Resource Manager (ARM) access. Moving the state afterward needs private access.

## Move this root's own state into the container

Once a peered host can reach the account, create an ignored `backend.tf`:

```hcl
terraform {
  backend "azurerm" {
    subscription_id      = "<state-subscription-id>"
    resource_group_name  = "<resource-group>"
    storage_account_name = "<storage-account>"
    container_name       = "<container>"
    key                  = "ai-foundry/bootstrap.tfstate"
    use_azuread_auth     = true
    use_cli              = true
  }
}
```

Run `terraform init -migrate-state`, confirm Terraform copies the existing
state, then delete the local `terraform.tfstate` files. Never commit state.

## Test without Azure

```powershell
terraform -chdir=terraform/bootstrap init -backend=false
terraform -chdir=terraform/bootstrap validate
terraform -chdir=terraform/bootstrap test
```

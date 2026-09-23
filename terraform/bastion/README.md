# Dedicated Standard Bastion

This independent Terraform root manages only Azure Bastion, its dedicated
`AzureBastionSubnet`, and its Standard static public IP. It reads the existing
management VNet without taking ownership of the VNet, Windows VM, or Foundry
services. Run commands in this directory, not the parent platform root.

Standard replaces Developer's shared infrastructure with two dedicated instances.
It is billed continuously, even when the VM is stopped or no sessions are open.
An upgrade can interrupt active sessions and is not a guarantee that guest-OS or
client-network problems are fixed. Downgrading requires deleting and redeploying
Bastion; this configuration deliberately prevents destruction.

## Existing host upgrade

1. Copy `dev.tfvars.example` to ignored `dev.tfvars` and supply the existing
   subscription, resource group, VNet, and Bastion names. Verify the subnet range
   is unused and inside the VNet. Preserve any existing Bastion tags.
2. Copy `backend.hcl.example` to ignored `backend.hcl` and configure the existing
   secured state account. Use a **separate state key**, never the platform's
   `ai-foundry/dev.tfstate` or the Lab's `ai-foundry/workbench-dev.tfstate`.
   Before importing, verify the host is not owned by another state. If it is,
   reconcile that ownership first rather than importing it twice.
3. Run from an authorized private-network environment with access to the backend,
   Blob Data Contributor on the state container, and permissions to manage the
   three network resources. Keep public and shared-key backend access disabled.
   For a managed-identity runner, replace `use_cli = true` with `use_msi = true`
   in the backend configuration and configure AzAPI managed-identity authentication.
4. Initialize and import the existing host. Import existing subnet/IP resources
   too if they already exist; do not attempt to create duplicates.

```powershell
terraform init "-backend-config=backend.hcl"
terraform import "-var-file=dev.tfvars" "azapi_resource.bastion" `
  "/subscriptions/<subscription>/resourceGroups/<group>/providers/Microsoft.Network/bastionHosts/<host>?api-version=2025-01-01"
$plan = Join-Path $env:TEMP ("bastion-" + [guid]::NewGuid() + ".tfplan")
terraform plan "-var-file=dev.tfvars" "-out=$plan"
```

The Developer upgrade plan should show **two creates** (subnet and IP), **one
in-place update** (Bastion), and **zero destroys**. AzAPI manages the host to avoid
AzureRM's replacement behavior when adding an IP configuration. Stop if the plan
changes anything else; never remove destruction protection to force an upgrade.
For a new installation, skip the import and expect three creates.

After reviewing the plan and approving the recurring cost and session interruption:

```powershell
try {
  terraform apply $plan
} finally {
  Remove-Item $plan -ErrorAction SilentlyContinue
}
terraform output
terraform plan "-var-file=dev.tfvars" -detailed-exitcode
```

The final plan should exit 0 with no changes. Also inspect the host's Azure
provisioning state and reconnect to the Windows VM through the portal. Open
Foundry in the remote desktop browser; Bastion does not route your local browser
into the private VNet. Do not put public IPs on the VM or open its RDP port to the
internet.

## Offline checks

```powershell
terraform init -backend=false
terraform fmt -check
terraform validate
terraform test
```

Tests use a mock provider; they do not deploy resources or demonstrate live
session stability. See Microsoft's [upgrade guidance](https://learn.microsoft.com/azure/bastion/upgrade-sku)
and [Bastion pricing](https://azure.microsoft.com/pricing/details/azure-bastion/).

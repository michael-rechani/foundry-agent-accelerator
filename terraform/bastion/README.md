# Dedicated Standard Azure Bastion

[Home](../../README.md) / [Infrastructure](../README.md) / Bastion

Use this guide to adopt or deploy the dedicated Standard Azure Bastion host for
the private management network. This Terraform root manages only Azure Bastion,
its dedicated `AzureBastionSubnet`, and its Standard static public IP. It reads
the existing management virtual network (VNet) without taking ownership of the
VNet, Windows virtual machine (VM), or Microsoft Foundry services.

Run commands in `terraform/bastion/`, not in the parent platform root.

## At a glance

| Setting | Value |
| --- | --- |
| SKU | Standard |
| Scale units | 2 |
| Subnet | Dedicated `AzureBastionSubnet` |
| Default subnet range | `10.43.1.0/26` |
| Public IP | Static Standard public IP named `<bastion_name>-pip` |
| Managed resources | Bastion host, subnet, and public IP only |
| State example | `ai-foundry/bastion-dev.tfstate` |
| Destruction guard | `prevent_destroy` on the Bastion host, subnet, and public IP |

> [!WARNING]
> Standard Azure Bastion is billed continuously while it exists, even when the VM
> is stopped or no sessions are open. Terraform also sets `prevent_destroy` on
> all three managed resources. Do not remove that protection to force an upgrade
> or cleanup; plan deletion as a separate approved operation.

## Existing host upgrade

Use this procedure when an existing Developer Bastion host already supports the
management VNet. Standard replaces Developer's shared infrastructure with two
dedicated instances. An upgrade can interrupt active sessions. The upgrade does
not guarantee that guest operating system or client-network problems are fixed.
Downgrading requires deleting and redeploying Bastion, and this configuration
intentionally prevents destruction.

1. Copy `dev.tfvars.example` to ignored `dev.tfvars`.
2. Supply the existing subscription, resource group, VNet, and Bastion names.
3. Verify that the subnet range is unused and inside the VNet.
4. Preserve any existing Bastion tags.
5. Copy `backend.hcl.example` to ignored `backend.hcl`.
6. Configure the existing secured state account. Use a **separate state key**,
   never the platform's `ai-foundry/dev.tfstate` or the Lab's
   `ai-foundry/workbench-dev.tfstate`.
7. Before importing, verify the host is not owned by another state. If another
   state already owns it, reconcile that ownership first rather than importing
   it twice.
8. Run from an authorized private-network environment with access to the
   backend, **Storage Blob Data Contributor** on the state container, and
   permissions to manage the three network resources.
9. Keep public and shared-key backend access disabled. For a managed-identity
   runner, replace `use_cli = true` with `use_msi = true` in the backend
   configuration and configure AzAPI managed-identity authentication.
10. Initialize and import the existing host. Import existing subnet and IP
    resources too if they already exist; do not attempt to create duplicates.

```powershell
terraform init "-backend-config=backend.hcl"
terraform import "-var-file=dev.tfvars" "azapi_resource.bastion" `
  "/subscriptions/<subscription>/resourceGroups/<group>/providers/Microsoft.Network/bastionHosts/<host>?api-version=2025-01-01"
$plan = Join-Path $env:TEMP ("bastion-" + [guid]::NewGuid() + ".tfplan")
terraform plan "-var-file=dev.tfvars" "-out=$plan"
```

The Developer upgrade plan should show **two creates** for the subnet and IP,
**one in-place update** for Bastion, and **zero destroys**. AzAPI manages the
host to avoid AzureRM's replacement behavior when adding an IP configuration.
Stop if the plan changes anything else. For a new installation, skip the import
and expect three creates.

After reviewing the plan and approving the recurring cost and session
interruption, apply the saved plan:

```powershell
try {
  terraform apply $plan
} finally {
  Remove-Item $plan -ErrorAction SilentlyContinue
}
terraform output
terraform plan "-var-file=dev.tfvars" -detailed-exitcode
```

The final plan should exit 0 with no changes. Inspect the host's Azure
provisioning state and reconnect to the Windows VM through the portal. Open
Foundry in the remote desktop browser; Bastion does not route your local browser
into the private VNet. Do not put public IPs on the VM or open its Remote
Desktop Protocol (RDP) port to the internet.

## Troubleshooting

| Symptom | Likely cause | What to do |
| --- | --- | --- |
| The plan wants to recreate the Bastion host. | The import target, name, or state ownership is wrong. | Stop, confirm the existing resource ID, and reconcile the owning state before planning again. |
| The plan wants to create duplicate subnet or IP resources. | Existing supporting resources were not imported. | Import the existing `AzureBastionSubnet` or public IP into the declared Terraform addresses. |
| The portal session still cannot reach Foundry. | Bastion gives remote desktop access only; it does not fix guest operating system, DNS, or route problems. | Test DNS and routing from the VM browser inside the private network. |
| Terraform refuses to destroy a resource. | `prevent_destroy` is working as designed. | Use a separately reviewed deletion process instead of bypassing the lifecycle guard. |

## Offline checks

```powershell
terraform init -backend=false
terraform fmt -check
terraform validate
terraform test
```

Tests use a mock provider; they do not deploy resources or demonstrate live
session stability. See Microsoft's
[upgrade guidance](https://learn.microsoft.com/azure/bastion/upgrade-sku) and
[Bastion pricing](https://azure.microsoft.com/pricing/details/azure-bastion/).

## Related content

- [Infrastructure deployment](../README.md)
- [Credentials and protected state](../../docs/credentials.md)
- [Private deployment runbook](../../docs/private-deployment.md)

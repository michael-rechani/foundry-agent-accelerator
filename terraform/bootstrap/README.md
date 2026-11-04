# Terraform state backend

[Home](../../README.md) / [Infrastructure](../README.md) / State backend

Creates the private Azure Storage account and container that hold every other
root's Terraform state, so a fresh subscription needs no hand-made backend.
Run it before the platform root. Bootstrap owns the shared
`privatelink.blob.core.windows.net` zone; the platform reuses its resource ID.
Existing platforms keep their own zone until the explicit adoption below.

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
   subscription. Set `peered_virtual_network_ids` to existing VNets that run
   Terraform. They get two-way peering and a link to the shared blob DNS zone.
   The runner is a subnet of the management VNet: add that VNet once, not a
   second runner entry. Do not link a VNet that still uses a different zone
   with this namespace; follow the adoption procedure first.
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

## Shared DNS ownership

| Resource | Terraform owner |
| --- | --- |
| Blob DNS zone and state endpoint's zone group | Bootstrap |
| State VNet link, peered host VNet links, state peering | Bootstrap |
| Workload VNet link to the shared blob zone | Platform |
| Agent storage and Azure Monitor endpoint zone groups | Platform, using the shared zone ID |

This follows Microsoft's
[single-zone guidance for peered networks](https://learn.microsoft.com/azure/private-link/private-endpoint-dns-integration).
VNet peering does not make DNS links transitive. The workload VNet has its own
link, and bootstrap links the management VNet where the runner lives.
Other private DNS namespaces remain platform-owned.

For a new platform, set `blob_private_dns_zone_id` to bootstrap's
`blob_private_dns_zone_id` output in the same subscription. Cross-subscription
DNS link providers are not configured by this root. `deploy.ps1` wires the
zone when it generates a new platform overlay, after confirming the
initialized platform state is empty.
An explicit `-BlobPrivateDnsZoneId` avoids reading bootstrap state when its
approved output is already known. Existing input files are never overwritten,
and existing platform state without its input file stops the helper rather
than guessing ownership. Direct Terraform callers must set this input too;
null deliberately preserves the legacy platform-owned zone.

### Fresh subscription: staged private access

These are rollout instructions, not authorization to create infrastructure.
Review each saved plan and separately approve any public resource or shared
egress it proposes. A broad deployment approval does not cover public exposure.

1. Run `deploy.ps1 -Stage preflight`, then `-Stage bootstrap` with the chosen
   subscription. Bootstrap starts with local state and creates its private
   endpoint through ARM; it needs no public storage access.
2. If no host can yet reach that backend, run `-Stage platform -LocalState`.
   New platform inputs reuse bootstrap's zone output. Stop after the reviewed
   platform apply; do not attempt Lab stages or remote state initialization
   from a host outside the private network.
3. Read the platform's `management_virtual_network_id` output and add it to
   bootstrap's ignored `dev.tfvars`, preserving any existing peer entries:

   ```hcl
   peered_virtual_network_ids = {
     management = "<management_virtual_network_id output>"
   }
   ```

   Rerun `-Stage bootstrap` and review the plan for both peering directions and
   the management link to the shared zone. The platform already owns its
   workload link; do not add that workload VNet to this map as well.
4. Use an approved private host with DNS and routing to the state VNet.
   Transfer the local bootstrap and platform state and reviewed inputs
   securely if changing hosts. State contains secrets: never put it in Git,
   issues, workflow artifacts, or shared chat.
5. Before migrating, check that the state account, platform agent storage and
   Azure Monitor blob names resolve through the shared zone to their private
   endpoints. Check actual connectivity and Entra access too; a private IP
   alone is not proof of reachability.
6. Migrate bootstrap's state as described below, then rerun
   `deploy.ps1 -Stage platform` **without** `-LocalState`. It creates the
   platform backend configuration and asks before migrating existing local
   state. Keep protected recovery copies until remote state is verified.
7. Continue from the private host with `-Stage lab-foundation,image,lab,verify`.
   Runner, identity, agent publication and billable smoke calls remain opt-in.

### Adopt an existing platform

Tracked under [#389](https://github.com/michael-rechani/foundry-agent-accelerator/issues/389)
and [#393](https://github.com/michael-rechani/foundry-agent-accelerator/issues/393).
**Do not simply set the shared-zone input and apply.** The old platform zone
would leave Terraform's managed resource set; `prevent_destroy` blocks its
deletion until ownership is explicitly relinquished. Adoption is a separately approved maintenance operation, with a
possible DNS interruption, not an automatic `deploy.ps1` stage.

1. Inventory both zones, every linked VNet, endpoint zone group and record set,
   including Azure Monitor's blob records and any consumers outside this repo.
   Back up the two states and record sets privately. Choose a Terraform host
   whose backend access will not depend on the management link being changed.
   Stop if the ownership or safe recovery path is unclear.
2. Keep bootstrap's zone as the canonical zone. Confirm its state-account
   private record and private endpoint are healthy. Do not delete either
   zone or change any VNet links yet.
3. With explicit state-edit approval, remove **only**
   `azurerm_private_dns_zone.this["storage_blob"]` from the platform state
   using `terraform state rm`. This relinquishes Terraform ownership without
   deleting the live legacy zone or its records. Retain the protected backup
   and the legacy zone until the migration is verified.
4. Set `blob_private_dns_zone_id` in the existing reviewed platform inputs to
   bootstrap's output. Generate a new saved platform plan. It must update
   agent-storage and Azure Monitor zone groups to the shared zone, replace the
   workload blob link under the shared zone's resource group, and remove only
   the legacy management blob link. It must **not** delete either zone, the
   state account, storage accounts or private endpoints. Stop for unexpected
   changes; do not reuse a plan saved before the state edit.
5. During the approved maintenance window, apply that reviewed platform plan
   from the unaffected host. A VNet cannot link two zones with this namespace,
   so the legacy links must be removed before shared links can take their
   place. Then add the management VNet to bootstrap's peer map and review/apply
   its plan. Do not give both roots ownership of the same VNet link.
6. Verify state reads/locking, both storage accounts' private resolution and
   connectivity, and Azure Monitor's required private records from workload
   and management/runner hosts. Compare the record inventory with the backup.
   Do not retire the old zone until **all** its consumers have migrated;
   cleanup requires its own approved plan/operation. If verification fails,
   pause the rollout and use the protected inventory and state backups for
   reviewed recovery, not an unreviewed full-state push.

No live adoption, fresh-subscription acceptance, or model smoke call is implied
by offline checks passing.

## Private access

Public network access is disabled, so a machine must reach the account through
the state VNet. Apply from a host on a peered network. Creating the account doesn't
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

Run `terraform init -migrate-state` from the private host and confirm Terraform
copies the existing state. Verify the remote state and locking before removing
local working copies; retain recovery backups in approved protected storage.
Never commit state.

## Test without Azure

```powershell
terraform -chdir=terraform/bootstrap init -backend=false
terraform -chdir=terraform/bootstrap validate
terraform -chdir=terraform/bootstrap test
.\scripts\terraform\test-state-dns.ps1
.\workbench\test-deploy.ps1
```

Run these commands from the repository root. Tests use mock providers and
isolated fixtures, not Azure credentials or live resources. CI runs the same
backend privacy, shared-zone ownership and deployment-helper checks.

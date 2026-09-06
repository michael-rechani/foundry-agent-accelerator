# Secret ownership and credential migration

[Overview](../README.md) / Credential migration

The Lab uses managed identity and keyless Cosmos/Log Analytics resource reads.
Its Log Analytics ownership transfer is complete, with no Azure resource changes
and an empty follow-up Terraform plan. The jumpbox password ownership migration,
rotation and Windows logon verification are complete. Cosmos and platform Log
Analytics and Storage ownership transfers are complete. All four Cosmos keys,
both Storage keys and both keys for each Log Analytics workspace were rotated
and verified through in-memory comparisons. The full refreshed platform plan
and the Lab registry reconciliation plan were empty after their transfers.

## Required ownership

Necessary passwords, API keys, tokens, and certificates must be provisioned
directly into Key Vault and read only by authorized identities. Prefer managed
identity and disable local/shared-key authentication where supported. Do not
create a redundant vault copy of an unused, disabled key just to populate a vault.
Azure-managed key material can still exist inside the service; the requirement
is to avoid application-managed plaintext copies outside the vault and transient
process memory needed to use them.

Transcripts, operational metadata, state files, resource IDs, and identity client
IDs are not Key Vault secrets. Store the first three in their dedicated protected
stores. Never retrieve a vault secret into an ordinary Terraform variable,
data source or resource argument and assume its value stays out of state.

## Verified inventory

| Path | Current finding | Required action |
| --- | --- | --- |
| Lab Foundry, Cosmos and ACR clients | Managed identity; no runtime API keys or connection-string secrets | Keep keyless access |
| Platform jumpbox | Credential-free AzAPI VM/extension owners; password rotated outside Terraform through private Key Vault | Preserve tested recovery and rotation workflow; historical password copies are invalidated |
| Platform Cosmos account | Keyless AzAPI owner; local auth disabled; four obsolete keys rotated | Keep managed-identity consumers and keyless reads |
| Platform Storage | Keyless AzAPI owner and separately managed Blob endpoint; old AVM owner retired; both keys rotated | Keep shared-key auth disabled; preserve endpoint ownership |
| Platform Log Analytics | Keyless AzAPI owner; local auth and public ingestion/query disabled; both keys rotated | Keep private identity-based telemetry |
| Lab Cosmos account lookup | Key-returning data source removed from current state with a zero-resource-change apply | Preserve historical state under retention policy |
| Lab Log Analytics | Local auth disabled; AzAPI owner; both keys rotated; private telemetry verified | Keep keyless ARM reads; preserve historical state under retention policy |
| Historical state, backups and prior plans | May retain old values independently of live configuration | Invalidate old credentials through rotation; handle copies under approved retention, never broad deletion |

The shared state account has public network access disabled. The workstation
receives HTTP 403 on state blob access. Private execution now works through the
existing jumpbox: `pe-foundry-tfstate` resolves the Blob endpoint to `10.42.0.23`,
and the VM managed identity can access both state blobs and initialize Terraform.
Public access and shared-key authentication remain disabled.

The local-only `terraform/state-access/` bootstrap owns this private endpoint,
the state-container Blob Data Contributor assignment, and workload resource-group
Reader assignment. Its local state and backups must be preserved independently
of the remote backend it makes reachable. The bootstrap and the two private
Terraform runner scripts are Git-ignored; existing platform source stays tracked.
The runner restores the jumpbox's prior power state and removes temporary plans.

AzureRM refresh also requires `Microsoft.App/containerApps/listSecrets/action`.
A custom role grants only that action, assigned only on `foundry-workbench` to
the jumpbox identity. This permits reading that app's secrets, not updating the
app, and is not a general Contributor grant. Reassess this permission if the app
later stores credentials or its Terraform provider changes.

## Lab workspace transfer

The Lab configuration uses `azapi_resource.logs` to read workspace
configuration, never the shared-key API. No explicit response exports are needed.
`monitoring-migration.tf` forgets the old AzureRM owner without destroying Azure
resources and has an explicit import opt-in for the existing workspace.

For other existing installations, from an approved backend-connected runner, plan with
`-var=import_existing_log_workspace=true` and the normal Lab variables. Require
exactly an import of the same workspace ID and non-destructive forgetting of
the old owner; reject all Azure creates, updates, replacements or deletions.
Apply only that saved plan, delete it in `finally`, then verify unchanged
workspace ID/settings and absence of the old key-bearing resource in current
state. A subsequent ordinary plan must be empty. Fresh installations leave the
import flag false. The import ID pins `api-version=2023-09-01` to match the resource
type. Preserve existing workspace settings during import; a version mismatch or
changed response exports can produce an update instead of an import-only plan.
The deployed Lab has completed this transfer and uses ordinary plans now.

## State exposure

Before migration, the same password reached four Terraform-managed locations:

- `random_password.jumpbox_admin`: generated result.
- `azurerm_windows_virtual_machine.jumpbox`: `admin_password`.
- `azurerm_virtual_machine_extension.jumpbox_vm_access`: `protected_settings`.
- `azapi_resource.jumpbox_admin_password`: Key Vault secret in ordinary `body`.

Redaction and Key Vault retrieval do not remove these copies from state or
saved plans. `ignore_changes` does not remove stored values either. Changing
only the Key Vault writer leaves the VM and extension copies intact.

Inspection of the installed provider schemas confirms:

| Capability | Result |
| --- | --- |
| Random provider ephemeral `random_password` | Available |
| AzAPI `sensitive_body` | Write-only, with `sensitive_body_version` |
| AzureRM Key Vault `value_wo` | Write-only, with `value_wo_version` |
| AzureRM Windows VM `admin_password` | Sensitive, not write-only |
| AzureRM VM extension `protected_settings` | Sensitive, not write-only |

This is evidence of provider capability, not evidence that importing and updating
the existing Azure resources will preserve their configuration or scrub state.

## Jumpbox rotation

The existing VM and VMAccess extension are managed through credential-free ARM
bodies. Terraform no longer generates or owns the administrator password or its
Key Vault secret. A private rotation process writes a candidate secret version,
changes the Windows account password, verifies `LogonUser`, then publishes and
reads back the primary secret. A non-secret rotation ID allows retrying with the
same candidate after interruption instead of generating another password.

Recovery was tested with a disposable local account at three failure points:
before changing the password, after changing it, and after publishing the primary
secret. Production rotation verified the new `azureadmin` credential using the
Windows interactive-logon API. This was credential verification, not a human RDP
session. Only temporary, exact-secret Key Vault permissions were used for rotation.

The local imported VM configuration describes this existing deployment. It is
not a generic new-VM provisioning template. A fresh VM needs a separate tested
write-only provisioning path.

## Write-only provisioning requirements

For new provisioning, use explicitly selected ARM API versions and write-only
`sensitive_body` for secret fields. Keep ordinary `body` free of credentials.
Use the existing ARM secret-management path if private Key Vault data-plane
connectivity is unavailable to the Terraform runner.

Generate the password once per rotation using an ephemeral random resource and
feed that one value to each write-only consumer. A reviewed, non-secret rotation
counter must trigger all consumers together through their version fields.
Unchanged applies must not unexpectedly rotate credentials. Failed or partial
applies must have an explicit recovery path; this is not an atomic transaction.

Do not export secret-bearing response fields from AzAPI. Request/response logs,
Terraform debug logs, crash files, CLI arguments, and CI artifacts also need
inspection. Never print a generated password or route it through chat.

## Staged execution

1. Confirm an authorized change window, private Key Vault access, and an
   independent recovery channel such as approved VM Run Command access. Verify
   remote-backend access control, encryption, locking, and retention. Record
   resource IDs and a non-secret baseline of VM identity, NIC, disk, image,
   security settings, extensions, project role assignments, and secret name.
2. Test the proposed configuration on an approved disposable VM first. Prove
   create, unchanged apply, rotation, failed rotation, retry, and drift behavior.
   Verify the new secret is absent from plan/state and exported resource bodies
   using an in-memory equality check that prints only pass/fail. A text search
   for the word `password` is not adequate proof.
3. Prepare a reviewed ownership-transfer plan. Use non-destructive removal
   (`removed` with `destroy = false`) and import blocks where supported, rather
   than deleting Azure resources. Remove the persistent random-password resource
   and all consumers of its value. Update references and non-secret outputs to
   the new owners. An import must not leave two resources managing the same ARM
   object. Verify the exact indexed addresses against the actual state.
4. Review a full saved plan with state locking enabled. Reject VM, NIC, disk,
   Key Vault, or project replacement/deletion. Reject unexpected identity,
   network, RBAC, image, or secret-name changes. Protect the saved plan as a
   credential-bearing artifact until the migration is complete.
5. Apply only the reviewed plan during the authorized window. Verify ARM
   provisioning and identity, private connectivity, Key Vault retrieval, and a
   fresh interactive login with the new credential. Validate recovery behavior
   if only the VM or only Key Vault updates. Do not reuse an uncertain rotation
   counter or perform blind retries.
6. Confirm a subsequent plan is stable and that the new password is absent from
   current Terraform state, saved plans, and logs. Keep result evidence free of
   secret values. Verify hosted-agent deployment still works through the VM
   managed identity.
7. Handle historical state versions, backups, local plans, restricted deployment
   logs, and exported artifacts under the approved retention policy. Rotation
   invalidates the old password but does not erase historical copies. Do not
   delete active state or broadly purge backups to make a scan pass.

## Stop conditions

Do not apply while recovery access is uncertain, a plan replaces the VM, a
provider returns secret fields into state, a partial-rotation recovery test
fails, or approval is unavailable. Retaining the existing restricted state is
safer than an untested login migration. Describe the platform as Key-Vault-only
only after the new credential's storage paths have actually been verified.
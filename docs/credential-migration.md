# Jumpbox credential migration

[Overview](../README.md) / Credential migration

Status: design and installed-provider capability check only, 2026-09-04.
No password rotation, resource ownership transfer, or state deletion has been
performed. The current VM login and recovery resources remain unchanged.

## Why this requires a migration

The same password currently reaches four Terraform-managed locations:

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

## Proposed target

Prototype AzAPI management of the existing VM, VMAccess extension, and Key Vault
secret using explicitly selected ARM API versions and write-only
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
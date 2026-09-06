# Secret ownership and credential migration

[Overview](../README.md) / Credential migration

Use managed identity for runtime access and keyless resource reads for Terraform.
This guide covers secret ownership, safe migration of existing resource owners,
and protection of historical state. Check the actual configuration and state of
each installation before deciding whether a migration is needed.

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

## Credential boundaries

| Path | Required configuration | Handling |
| --- | --- | --- |
| Lab Foundry, Cosmos and ACR clients | Managed identity; no runtime API keys or connection-string secrets | Keep keyless access |
| Platform Cosmos account | Keyless ARM owner; local auth disabled | Rotate obsolete keys after migrating consumers and state ownership |
| Platform Storage | Keyless ARM owner and explicit Blob endpoint ownership | Keep shared-key auth disabled; preserve endpoint ownership |
| Platform Log Analytics | Keyless ARM owner; local auth and public ingestion/query disabled | Keep private identity-based telemetry |
| Lab Cosmos account lookup | Avoid key-returning data sources | Preserve historical state under retention policy |
| Lab Log Analytics | Local auth disabled; AzAPI owner | Use keyless ARM reads and protect historical state |
| Historical state, backups and prior plans | May retain old values independently of live configuration | Invalidate old credentials through rotation; handle copies under approved retention, never broad deletion |

Access the state backend through its Blob private endpoint with an authorized
identity. A workstation outside the approved network cannot initialize or refresh
that backend. Do not enable public or shared-key access to bypass the restriction.

The local-only `terraform/state-access/` bootstrap owns this private endpoint,
the state-container Blob Data Contributor assignment, and workload resource-group
Reader assignment. Its local state and backups must be preserved independently
of the remote backend it makes reachable. The bootstrap and the two private
Terraform runner scripts are Git-ignored; existing platform source stays tracked.
Temporary plans are removed after execution; historical state is retained.

AzureRM Container App refresh also requires
`Microsoft.App/containerApps/listSecrets/action`. Scope this permission to the
specific app and deployment identity; do not substitute a broad Contributor grant.
This permits reading app secrets. Reassess the permission if the app stores
credentials or its Terraform provider changes.

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
After a successful transfer, return to ordinary plans without the import flag.

## State exposure

Provider-returned keys and credentials in ordinary resource attributes can
persist in state and saved plans. Redaction, Key Vault retrieval, and
`ignore_changes` do not remove stored values. All secret-bearing owners and
read paths must be addressed together.

The pinned providers support the following write-only mechanisms. Check the
installed schema before changing provider versions:

| Capability | Result |
| --- | --- |
| Random provider ephemeral `random_password` | Available |
| AzAPI `sensitive_body` | Write-only, with `sensitive_body_version` |
| AzureRM Key Vault `value_wo` | Write-only, with `value_wo_version` |

This is evidence of provider capability, not evidence that importing and updating
the existing Azure resources will preserve their configuration or scrub state.

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
   independent recovery channel. Verify remote-backend access control,
   encryption, locking, and retention. Record resource IDs and a non-secret
   baseline of identity, networking, security settings, and role assignments.
2. Test the proposed configuration on approved disposable resources first. Prove
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
4. Review a full saved plan with state locking enabled. Reject service,
   Key Vault, or project replacement/deletion. Reject unexpected identity,
   network, RBAC, image, or secret-name changes. Protect the saved plan as a
   credential-bearing artifact until the migration is complete.
5. Apply only the reviewed plan during the authorized window. Verify ARM
   provisioning and identity, private connectivity, Key Vault retrieval, and a
   authenticated request with the new credential. Validate recovery behavior
   if only the service or only Key Vault updates. Do not reuse an uncertain rotation
   counter or perform blind retries.
6. Confirm a subsequent plan is stable and that the new password is absent from
   current Terraform state, saved plans, and logs. Keep result evidence free of
   secret values. Verify hosted-agent deployment still works through its
   authorized managed identity.
7. Handle historical state versions, backups, local plans, restricted deployment
   logs, and exported artifacts under the approved retention policy. Rotation
   invalidates the old password but does not erase historical copies. Do not
   delete active state or broadly purge backups to make a scan pass.

## Stop conditions

Do not apply while recovery access is uncertain, a plan replaces a service, a
provider returns secret fields into state, a partial-rotation recovery test
fails, or approval is unavailable. Retaining the existing restricted state is
safer than an untested credential migration. Describe the platform as Key-Vault-only
only after the new credential's storage paths have actually been verified.
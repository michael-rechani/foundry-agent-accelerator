# Credentials and protected state

[Overview](../README.md) / Credentials

Use managed identity for runtime access and keyless resource reads for Terraform.
Necessary passwords, API keys, tokens, and certificates belong in Key Vault.
Do not create redundant vault copies of unused, disabled service keys.

## Runtime access

The Lab accesses Foundry and Cosmos through managed identity. Registry access also
uses managed identity, with the registry admin account disabled. Keep local or
shared-key authentication disabled on supporting services wherever supported.

Transcripts and operational metadata are application data, not vault secrets.
Keep them in their dedicated protected stores with appropriate access and retention.
Avoid storing credentials in prompts, conversations, application logs, or exports.

## Terraform access

Platform Cosmos, Storage, and Log Analytics use AzAPI ARM resource reads rather
than key-returning account lookups. The Lab also uses keyless ARM reads for its
workspace and derives the Cosmos endpoint without retrieving account keys.

Terraform state remains sensitive even when credentials are absent from the current
configuration. Use an Entra-authenticated backend with private connectivity, locking,
encryption, and restricted access. Preserve state and protected backups under their
retention policy. Delete disposable plan files after an apply attempt or when
abandoned; never commit state, plans, backend credentials, or environment tfvars.

The platform, Lab, optional Bastion, and optional agent monitoring stacks use
separate state keys. Never initialize empty state for
resources that already have an owner. An ordinary plan must not recreate existing
services or delete unexpected owners.

Access the backend through an authorized private-network path. Do not enable public
or shared-key access to bypass a connectivity restriction. Local administration
tooling under `terraform/state-access/` is excluded from the published sample; its
state and backups must be preserved independently.

AzureRM Container App refresh requires
`Microsoft.App/containerApps/listSecrets/action`. Scope it to the specific app and
deployment identity. Reassess this permission if app secrets or provider behavior
change; it is not justification for broad subscription access.

## Optional VM credentials

The optional Windows admin VM accepts a Key Vault reference, not a password input.
Pre-provision a strong password in an accessible vault and pin the secret version
in `jumpbox_admin_secret`. Terraform reads the value ephemerally and supplies it to
AzAPI through write-only `sensitive_body` fields. Ordinary bodies and outputs must
not contain it. The deployment identity needs private vault connectivity and
permission to read the secret.

Keep the version stable during ordinary applies. Changing it requests an explicit
credential update in the VM and access extension. These updates are not atomic:
retain the previous vault version and an independent recovery channel until login
is verified. Inspect individual consumers after a partial failure before retrying
with the same pinned version.

For an existing VM whose credentials are administered separately, leave the secret
reference null; Terraform then omits the VMAccessAgent extension. If an extension
is already tracked, reconcile its ownership before changing the reference; the
destruction guard must not be bypassed to remove a live extension. Explicit disk
inputs preserve the disk configuration. Set
`jumpbox_existing_os_disk.create_option = "Attach"` when booting a retained
specialized Windows disk; its existing credentials remain in effect. Restore
the replacement system identity's required roles and reconcile Terraform state
before the next apply.

Schema validation and offline input tests do not prove live credential behavior.
Before relying on a provisioning path, test create, unchanged apply, rotation,
partial failure, and recovery on approved disposable resources. Verify in memory
that the secret is absent from saved plans, state, response exports, and logs,
printing only pass/fail. Do not route secret values through chat or CLI arguments.

Redaction and `ignore_changes` do not remove secrets from historical state or logs.
Protect historical copies and rotate exposed credentials through the approved
recovery process; do not broadly delete backups to make a scan pass.

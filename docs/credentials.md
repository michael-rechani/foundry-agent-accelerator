# Credentials and protected state

[Home](../README.md) / [Docs](README.md) / Credentials

Credentials stay out of source code, Terraform inputs, plans, and application
logs. Runtime access uses managed identity, Terraform reads resources without
keys, and Key Vault holds only the credentials that have to exist.

## At a glance

| Area | Guidance |
| --- | --- |
| Runtime services | Use managed identity for Microsoft Foundry, Cosmos, and registry access. |
| Secrets | Store required passwords, API keys, tokens, and certificates in Key Vault. |
| Source control | CI scans every commit for credentials. Never commit keys, certificates, state, or tfvars. |
| Terraform state | Treat state and saved plans as sensitive, even when no credential is currently present. |
| State ownership | Keep separate state keys for the platform, the Lab, optional Bastion, and optional monitoring. |
| Recovery | Preserve protected backups and rotate exposed credentials through the approved recovery process. |

Don't create redundant Key Vault copies of unused, disabled service keys.

## Runtime access

The Lab accesses Foundry and Cosmos through managed identity. Registry access
also uses managed identity, with the registry admin account disabled. Keep local
or shared-key authentication disabled on supporting services wherever supported.
For the roles each identity receives, and the permissions operators grant
themselves, see the [permissions reference](permissions.md).

Transcripts and operational metadata are application data, not vault secrets.
Keep them in their dedicated protected stores with appropriate access and
retention. Avoid storing credentials in prompts, conversations, application
logs, or exports.

## Secret scanning

Every push and pull request runs [gitleaks](https://github.com/gitleaks/gitleaks)
across the full commit history. The build fails if it finds a credential. The
only exception in [`.gitleaks.toml`](../.gitleaks.toml) is the synthetic Key
Vault version ID that offline Terraform tests use. Run the same scan before you
push:

```bash
gitleaks git . --redact
```

If a scan finds a real credential, rotate it first, because rewriting history
doesn't revoke a value that was already pushed. Then store the replacement in
Key Vault.

## Terraform access

Platform Cosmos, Storage, and Log Analytics use AzAPI Azure Resource Manager
(ARM) resource reads rather than key-returning account lookups. The Lab also
uses keyless ARM reads for its workspace and derives the Cosmos endpoint without
retrieving account keys.

Terraform state remains sensitive even when credentials are absent from the
current configuration. Use a Microsoft Entra ID-authenticated backend with
private connectivity, locking, encryption, and restricted access. Preserve state
and protected backups under their retention policy. Delete disposable plan files
after an apply attempt or when abandoned. Never commit state, plans, backend
credentials, or environment tfvars.

The platform, Lab, optional Bastion, and optional agent monitoring stacks use
separate state keys. Never initialize empty state for resources that already
have an owner. An ordinary plan must not recreate existing services or delete
unexpected owners.

Access the backend through an authorized private-network path. Don't enable
public or shared-key access to bypass a connectivity restriction. Local
administration tooling under `terraform/state-access/` is excluded from the
published sample, so preserve its state and backups independently.

AzureRM provider refresh for Azure Container Apps requires
`Microsoft.App/containerApps/listSecrets/action`. Scope it to the specific app
and deployment identity. Reassess this permission if app secrets or provider
behavior change. It isn't justification for broad subscription access.

## Optional virtual machine credentials

The optional Windows admin virtual machine (VM) accepts a Key Vault reference,
not a password input. Pre-provision a strong password in an accessible vault and
pin the secret version in `jumpbox_admin_secret`. Terraform reads the value
ephemerally and supplies it to AzAPI through write-only `sensitive_body` fields.
Ordinary bodies and outputs must not contain it. The deployment identity needs
private vault connectivity and permission to read the secret.

Keep the version stable during ordinary applies. Changing it requests a
credential update in the VM and access extension. These updates aren't atomic,
so retain the previous vault version and an independent recovery channel until
login is verified. After a partial failure, inspect individual consumers before
retrying with the same pinned version.

For an existing VM whose credentials are administered separately, leave the
secret reference null. Terraform then omits the VMAccessAgent extension. If an
extension is already tracked, reconcile its ownership before changing the
reference. Don't bypass the destruction guard to remove a live extension.
Specified disk inputs preserve the disk configuration. Set
`jumpbox_existing_os_disk.create_option = "Attach"` when booting a retained
specialized Windows disk. Its existing credentials remain in effect. Restore the
replacement system identity's required roles and reconcile Terraform state before
the next apply.

Schema validation and offline input tests don't prove live credential behavior.
Before relying on a provisioning path, test create, unchanged apply, rotation,
partial failure, and recovery on approved disposable resources. Verify in memory
that the secret is absent from saved plans, state, response exports, and logs,
printing only pass/fail. Don't route secret values through chat or CLI
arguments.

> [!CAUTION]
> Redaction and `ignore_changes` don't remove secrets from historical state or
> logs. Protect historical copies and rotate exposed credentials through the
> approved recovery process. Don't broadly delete backups to make a scan pass.

## Troubleshooting

| Symptom | Likely cause | What to do |
| --- | --- | --- |
| Terraform asks to recreate an existing service. | The root is pointing at empty or wrong state. | Stop and reconcile state ownership before planning again. |
| Backend access fails from a local machine. | The state account requires private connectivity. | Use an authorized private-network path instead of reopening public or shared-key access. |
| A VM credential update partially fails. | The VM and access extension updates aren't atomic. | Keep the prior vault version, inspect each consumer, and retry with the same pinned version. |
| A scan finds an old secret in state or logs. | Historical copies still contain the value. | Protect the copies and rotate the exposed credential through the approved recovery process. |

## Related content

- [Security policy](../SECURITY.md)
- [Permissions reference](permissions.md)
- [Troubleshooting](troubleshooting.md)
- [Infrastructure deployment](../terraform/README.md)
- [Private deployment runbook](private-deployment.md)
- [Bastion](../terraform/bastion/README.md)
- [Agent monitoring](../terraform/monitoring/README.md)

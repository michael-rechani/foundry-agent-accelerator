# GitHub-only Terraform state access

[Home](../../README.md) / [Infrastructure](../README.md) / State access

This root defines a dedicated Microsoft Entra application and service principal,
GitHub OIDC trust, a narrow blob data role, and the `terraform-state` GitHub
environment. It does not own the shared storage account, container, endpoint or
DNS zone. It grants no infrastructure deployment or role-assignment permissions.
The runner VM identity keeps only its existing self-deallocation duties.

The default state writer is a GitHub job on the private runner. Any non-GitHub
maintenance writer, including the jumpbox, requires an explicitly documented
exception. Network access alone does not grant state access.

## Configuration and approval

Supply `subscription_id`, the existing `storage_account_id`, `container_name`,
approved `private_endpoint_ip`, and `reviewer_user_ids` (GitHub numeric IDs) in
protected inputs. The GitHub owner must be a personal account, matching this
repository's existing ID-qualified OIDC subject convention. No client secret is
created. The provider uses operator credentials only for provisioning identity,
RBAC and GitHub settings; do not copy those credentials to the runner.

The custom role allows only blob read/write/delete/add and container metadata
read. Its assignment is at the existing container, with an ABAC condition
restricting blob paths and list prefixes to `ai-foundry/`. It cannot change or
delete containers, storage settings, networking or infrastructure. Terraform
workspace keys outside that prefix are deliberately not authorized.

Only `main` can use the `terraform-state` environment, and each job requires a
reviewer. An owner may review their own manually dispatched check; this is still
an explicit approval rather than an automatic deployment. Nothing grants this
identity permissions through the runner's always-available managed identity.

Configure `state_backend_private_endpoint_ips` in the runner's protected inputs
to allow only TCP 443 to the existing blob private endpoint. Preserve the
registry and Foundry input lists and all deny rules. Use the existing management
VNet's private DNS/peering; do not add a public storage exception or a new backend.

## Verify without deploying infrastructure

After review and integration into `main`, manually run
[`check-state-backend.yml`](../../.github/workflows/check-state-backend.yml).
The runner must already be online; this workflow does not start a VM.
Approve the environment gate. The check:

- Requires DNS to resolve exclusively to the configured RFC1918 endpoint.
- Exchanges the GitHub OIDC assertion directly for a storage token in memory.
- Lists at most one blob under the authorized prefix, without logging its name.
- Requires a request for a unique nonexistent path outside the prefix to be
  denied, without reading any existing blob.
- Creates a unique `ai-foundry/.access-probe/` blob, acquires a finite lease,
  verifies an independent lease attempt is rejected, releases and deletes it.

It never downloads state contents, leases an actual state file, runs Terraform,
publishes artifacts, or applies infrastructure. Probe deletion is still subject
to the existing account's soft-delete/version retention policies.

A successful check proves blob connectivity and locking, **not** permission to
deploy Terraform-managed infrastructure. The separately approved
[runner planning path](../runner-plan-access/README.md) adds only three scoped
Reader grants and tests import-only state writes, without infrastructure-write
permissions. Do not add deployment permissions to this identity silently.
Do not remove the jumpbox exception until the intended
replacement has been verified, unless explicitly directed to revoke it anyway.

## State adoption

For initial setup, an approved administrator may create the exact identity,
environment and access grant using management APIs because a runner without
backend access cannot bootstrap its own remote state. Such provisioning does
not authorize a non-runner to write Terraform state.

Import those resources from a separately approved GitHub Terraform job into a
dedicated `ai-foundry/state-access-dev.tfstate` key before applying this root.
Use `terraform import` addresses matching `main.tf`, including each
`github_actions_environment_variable.state` instance. Inventory existing IDs
privately; do not recreate or duplicate the app/role/environment or publish
protected inputs and plans. State adoption and the eventual infrastructure
deployment identity remain acceptance items in #389/#393. A connectivity check
alone does not complete either issue.

## Current Lab rollout

The approved private backend HTTPS rule and the resources in this root were
configured through management APIs during #389/#393. Private-only DNS and
certificate-validated HTTPS were verified from the actual Linux runner without
reading or writing state. No jumpbox startup, disk change, public exception or
grant to the runner VM identity was involved.

PR #484 merged the connectivity workflow. Its approved main run
[41948909763](https://github.com/michael-rechani/foundry-agent-accelerator/actions/runs/41948909763)
passed private DNS, OIDC, namespace isolation and disposable-blob lease checks
on the actual runner. No Terraform state contents were read or changed by it.
It is intentionally not permitted on a PR branch.
The new access resources are defined in this root but **not yet imported into
Terraform state**. The runner's next reviewed plan must also retain
`state_backend_private_endpoint_ips` and the existing registry/Foundry inputs
so an inline-NSG apply does not remove any live exceptions. Both adoption tasks
remain tracked in #389/#318. The jumpbox permission-removal condition is not yet
met: a connectivity identity is not a verified Terraform infrastructure deployer.

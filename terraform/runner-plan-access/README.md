# Read-only runner planning access

[Home](../../README.md) / [Infrastructure](../README.md) / Runner plan access

This ARM-only root adopts exactly three **Reader** assignments for the dedicated
[GitHub OIDC state identity](../github-state-access/README.md): the existing
runner resource group, management VNet and management NAT gateway. It grants no
Azure writes, Graph permissions, GitHub administration, secrets access or rights
to the ambient runner VM identity. It owns neither the shared network nor the
identity itself. Its state is `ai-foundry/runner-plan-access-dev.tfstate`.

The separate root avoids requiring tenant/repository administration credentials
for an ordinary Azure plan. Adoption of the original Entra/GitHub/blob-role
resources remains in `terraform/github-state-access` and is tracked in #389.

## Approved initial setup

An authorized administrator can run
[`configure-runner-plan.ps1`](../../scripts/terraform/configure-runner-plan.ps1)
with explicit subscription, principal, runner and management network arguments
and `-ApproveReaderGrants`. Review those scopes first. The script inventories
existing VM, subnet, shutdown and private HTTPS settings; it creates only missing
Reader assignments and records their IDs plus non-secret inputs in the existing
reviewed `terraform-state` environment's `TF_RUNNER_PLAN_CONFIG` variable.
It never connects to the private backend or writes state. Reruns reuse existing
exact-scope assignments. No operator credentials are copied to GitHub.

## Runner-only state adoption and verification

After review and integration into main, dispatch
[`check-terraform-runner.yml`](../../.github/workflows/check-terraform-runner.yml)
with `operation=import-readers`, then approve its environment gate. The runner
must already be online. This operation:

1. Verifies the exact private backend DNS address and GitHub OIDC authentication.
2. Refuses an empty/wrong runner state before initializing its backend.
3. Persists reviewed inputs as `ai-foundry/runner-dev.tfvars.json` and
   `ai-foundry/runner-plan-access-dev.tfvars.json`. Conditional creation and
   semantic comparison prohibit overwriting different existing canonical inputs.
4. Initializes this dedicated root, saves a complete plan and verifies the exact
   missing import IDs with **zero resource creates, updates or deletes**.
5. Applies only that guarded saved plan, then requires a fresh no-change plan and
   verifies three managed instances persisted in remote state.
6. Runs a full, normally refreshed plan of `terraform/runner`, preserving all
   registry, Foundry and backend HTTPS inputs. Any changes fail closed. It never
   applies the runner plan, and verifies the existing state contents are unchanged.

`operation=plan` skips Reader adoption and runs only the full runner plan.
Both operations can persist canonical inputs and acquire real backend leases;
they are not the disposable-blob connectivity probe. They never run
`-target`, `-refresh=false`, refresh-only apply, state push or force-unlock.
CLI/MSI fallback is disabled; only the approved GitHub OIDC identity is used.
The workflow is manual, main-only, reviewer-gated and serialized with the backend
probe. Plans, state and provider diagnostics stay off public logs/artifacts;
private temporary files are removed when the helper exits, including failures,
with an additional always-run cleanup restricted to that exact run/attempt.

This verifies **planning and import-only state writes**, not permission to deploy
infrastructure. It does not start a VM, run a canary, touch the platform root or
resolve its paused disk drift (#485). It does not revoke the jumpbox exception.
The broader deployment permission design and administrative-root adoption remain
in #389/#393. A clean runner plan alone does not persist refreshed NSG metadata:
that requires a separately approved saved-plan state reconciliation under #318.

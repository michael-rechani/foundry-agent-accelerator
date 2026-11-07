# Deploy the Lab

[Home](../README.md) / [Docs](README.md) / [The Lab](../workbench/README.md) / Deploy

This page is part of the [Lab guide](../workbench/README.md). It's the runbook
for deploying the Lab with the Terraform root in `workbench/infra`. To run the
Lab on your own machine without Azure, use
[Local development](../workbench/README.md#local-development) instead.

## In this guide

- [1. Confirm prerequisites and state ownership](#1-confirm-prerequisites-and-state-ownership)
- [Diagnose the existing platform Router plan](../terraform/README.md#diagnose-the-existing-platform-router-plan)
- [Diagnose the existing Lab plan](#diagnose-the-existing-lab-plan)
- [2. Configure and initialize](#2-configure-and-initialize)
- [3. Bootstrap only a new Lab](#3-bootstrap-only-a-new-lab)
- [4. Build and select an immutable image](#4-build-and-select-an-immutable-image)
- [5. Plan and review the image rollout](#5-plan-and-review-the-image-rollout)
- [6. Apply the approved plan and clean up](#6-apply-the-approved-plan-and-clean-up)
- [7. Verify the deployed application](#7-verify-the-deployed-application)
- [Deploy a new image from GitHub Actions](#deploy-a-new-image-from-github-actions)
- [Recover after a subscription suspension](#recover-after-a-subscription-suspension)

## Deployment

**One command.** `deploy.ps1` at the repo root runs every step below in order for
a new subscription: preflight checks, the state backend, the platform, the Lab
foundation, the private image build, the Lab and the verification. Each Terraform
stage shows its plan and applies only after you type `apply`; `-PlanOnly` stops at
the first stage with changes and never runs image builds, runtime verification
or agent publication, even if preceding plans have no changes. The state account is private, so run the stages after
bootstrap from a host that can reach it. The build and verify stages need the
private network too.

For a fresh subscription without a private Terraform host, this is a staged
process, not one uninterrupted run. Follow
[bootstrap's private-access sequence](../terraform/bootstrap/README.md#fresh-subscription-staged-private-access):
bootstrap locally, first platform apply with `-LocalState`, connect the
management VNet to the state network/shared blob DNS zone, then migrate state
and continue from an approved private host. No public backend fallback is used.
The [existing-platform adoption guide](../terraform/bootstrap/README.md#adopt-an-existing-platform)
keeps DNS records and state ownership changes separate from ordinary deployment.

```powershell
./deploy.ps1 -Subscription '<subscription-id>' -Stage preflight   # read-only checks
./deploy.ps1 -Subscription '<subscription-id>' -PlanOnly          # first plan, nothing applied
./deploy.ps1 -Subscription '<subscription-id>'                    # approve each plan in turn
```

It creates any missing ignored input (`backend.hcl`, `terraform.tfvars`,
`dev.tfvars`) with defaults and never overwrites one. A newly generated registry
name includes a hash of the subscription and, for any environment other than
`dev`, the environment name, so two environments in one subscription don't claim
the same global name. A `dev` registry keeps its original name, and an existing
`dev.tfvars` keeps whatever name it holds. New platform inputs include `-BaseName`
and `-Environment`. Terraform defaults supply the Lab's title and visible agents;
the generated `workbench/infra/dev.tfvars` connects it to the platform's state in
the account `terraform/bootstrap` creates, using the chosen state resource group
and environment. Customize the ignored input files for deployment-specific
overrides. Three stages are opt-in:

```powershell
./deploy.ps1 -Subscription '<subscription-id>' -Stage runner -ApproveSharedEgress   # private CI VM; shares the jumpbox NAT IP
./deploy.ps1 -Subscription '<subscription-id>' -Stage identity                      # Entra apps, roles, GitHub environments
./deploy.ps1 -Subscription '<subscription-id>' -Stage agents -Agent <name>          # billable
```

The runner stage needs an SSH public key (`-RunnerSshPublicKeyPath`; only the public
half is used). The identity stage needs rights to create Entra apps and role
assignments, plus `GITHUB_TOKEN` or a signed-in `gh` with repo admin. The verify
stage skips the billable agent call unless you add `-IncludeAgentCall`. The steps
below are the same sequence by hand, and the reference for each one.

The agents stage uses the platform's Model Router output by default, or its fixed
primary output when Router is disabled or absent from older state. Pass
`-AgentModel '<existing-deployment-name>'` to choose a fixed deployment
explicitly. Publishing changes the hosted version; afterward, verify its active
model before updating the Lab's per-agent budget declaration.

Run these steps from the repository root in one PowerShell session. Stop
if any command fails. Terraform deploys the Lab infrastructure and selects its
image. Image building and runtime smoke tests are separate steps that you run
yourself.

### 1. Confirm prerequisites and state ownership

You need an existing Foundry project and tested agent, authenticated Azure
access, Terraform 1.16.4, and an approved private-network path to the backend
and workload. The state account and blob container must already exist. Check
that the executing identity has the resource, role-assignment, and
state-container access it needs.

If the runner is a virtual machine using its managed identity, grant any
temporary roles before starting it. The instance metadata service caches tokens
for up to 24 hours, and tokens issued before a new grant can keep failing with
`AuthorizationFailed`. After a late grant, deallocate and start the runner
before retrying. Remove temporary grants once the rollout is verified.

Infrastructure uses its own Azure Storage backend key,
`ai-foundry/workbench-dev.tfstate`, never the platform infrastructure key
`ai-foundry/dev.tfstate`. The backend uses Microsoft Entra ID and Azure CLI
authentication with blob-lease locking. Shared-key access is disabled. The
existing account enforces HTTPS/TLS 1.2, encryption, versioning, 90-day blob
soft-delete, and seven-day container soft-delete. Public network access is now
disabled. Don't reopen the shared account's firewall.

For an existing local deployment, use `init -migrate-state -backend-config=backend.hcl`
only after checking that the target key is unused. Confirm that Terraform copies
the existing state, and never start empty. Compare lineage and managed resource
IDs before and after. Keep protected local backups. Never commit state or plans.
Restrict state access and review inherited Azure role-based access control
(RBAC) separately.

Run Terraform through the approved private-network path. Existing
installations must use the resource addresses declared in the configuration.
One-time ownership scripts aren't part of the sample. Stop if a plan tries to
recreate existing resources or destroy an older owner, and resolve that
installation's state separately.

Necessary secrets belong in Azure Key Vault and must not enter normal Terraform
attributes. Lab runtime access is keyless managed identity. Cosmos transcripts
remain sensitive operational data, not vault secrets. Use keyless Azure Resource
Manager (ARM) resource reads, and keep historical backups under their
retention policy.

For the default Model Router rollout, the separate
[platform plan diagnostic](../terraform/README.md#diagnose-the-existing-platform-router-plan)
does not deploy Router or change the Lab. The Lab's current guarded apply also
does not yet accept the Router model settings; review and a separate runner
apply path are still required (#522).

The manual [`Check private Lab Router plan`](../.github/workflows/check-lab-router-plan.yml)
is a **plan-only** check to run after Router has been deployed and reviewed. It
uses the same private runner, protected environment, configuration and separate
approvals as the Lab diagnostic below, plus Reader access to the existing
Foundry deployment. It verifies the platform's project and the live Router's
model version, SKU, capacity and routing, then accepts only a full Lab plan
changing the existing fixed creation model to Router and/or updating the
preview capability setting to match platform state, or a no-change plan
already configured for both. It rejects unrelated changes, drift, unknown
values, changed images or inputs, and an explicit setting disabling private
library preview. It also requires the planned image to match the active
revision's digest. It cannot verify that the active image supports preview,
apply the change, or verify inference. Work profiles can still override the
default model, and existing hosted-agent versions are unaffected. A reviewed
apply and a live UI test remain separate steps.

### Diagnose the existing Lab plan

The manual
[`Diagnose private Lab Terraform plan`](../.github/workflows/check-lab-terraform-plan.yml)
workflow is the read-only investigation path for #445. It uses the GitHub OIDC
state identity on the private runner, the protected `terraform-state`
environment, and the same concurrency group as other state operations. It does
not start the runner, grant roles, apply a plan, or publish a plan artifact.
Preparing or merging it is **not** approval to run it.

Before a separately approved run:

1. Review and merge the workflow to `main`. Configure the protected environment
   secret `TF_LAB_PLAN_CONFIG` with the following JSON object. Its values must
   match the existing `terraform-state` environment variables exactly; use the
   existing state identity, not a new identity or credential. The secret masks
   the configuration in Actions logs. Setting it is a separate environment
   change, and the placeholders below are not valid values.

   ```json
   {
     "AZURE_CLIENT_ID": "<existing state identity client ID>",
     "AZURE_TENANT_ID": "<existing tenant ID>",
     "AZURE_SUBSCRIPTION_ID": "<existing subscription ID>",
     "TF_STATE_ACCOUNT": "<existing private state account>",
     "TF_STATE_CONTAINER": "<existing state container>",
     "TF_STATE_PREFIX": "ai-foundry/",
     "TF_STATE_PRIVATE_ENDPOINT": "<approved private endpoint IPv4 address>"
   }
   ```

2. Separately approve the least-privilege, temporary Reader grants needed for a
   full Lab refresh. The existing state identity does not currently have Reader
   over the WAF or alerts; other referenced platform resources may also need
   read access. AzureRM also calls `Microsoft.App/containerApps/listSecrets/action`
   to refresh the existing app. This action can expose app secrets to the
   provider. It requires separate, explicit approval and a temporary role scoped
   to that single app. Stop if it is not approved. Remove the temporary grants
   after the approved investigation. Do not grant infrastructure-write
   permissions or use the VM's managed identity.
3. Separately approve starting the private runner and dispatching the workflow;
   the runner has a compute cost while running. Approve the protected
   environment gate for that run. Do not start the jumpbox, change a firewall,
   or enable public backend access as a fallback.

The check requires private DNS to resolve only to the approved state endpoint,
uses OIDC rather than Azure CLI or managed-identity fallback, and rejects proxy
settings. It reads the existing Lab state and canonical `workbench-dev.tfvars`
without changing either. It verifies ownership of the existing Container App,
WAF, and all three alerts. If `platform_state` is set, that state must be the
`ai-foundry/dev.tfstate` key in the same approved subscription, account and
container; otherwise the check stops rather than contacting another backend.
For the staged diagnostic only, the platform remote-state data source is
rewritten to use the same OIDC identity instead of Azure CLI. The checked-in
Terraform source is not modified.

The canonical inputs normally omit `image_digest`. The check reads the
immutable image digest from the existing app's active, ready, single revision
through ARM and supplies it in a private supplemental auto-input file.
Canonical inputs take precedence, and a different canonical digest stops the
check rather than being silently replaced. The app's image remains owned by the
image rollout workflow and ignored by later Terraform changes. An unavailable,
mutable, or changing active image also stops the check.

The workflow stages only the checked-in Lab Terraform source and agent catalogue
from the dispatched commit, so ignored local inputs cannot affect the result.
It adds a diagnostic-only provider configuration that disables the Front Door
module's telemetry during refresh without changing the module's resources or
inputs. It then runs a full plan with refresh and locking enabled; Terraform
temporarily acquires and releases the state blob lease and writes and removes
lock metadata, but the workflow never persists the refreshed state. With blob
versioning enabled, those metadata writes create retained blob versions and
change the state ETag even when the state content is unchanged. Those versions
can retain Terraform lock details under the account's retention policy. Account
for that effect when approving the run.

The check compares Lab state contents and non-lock metadata before and after,
and requires the lease and lock metadata to be cleared. It also compares the
contents and ETags of the canonical inputs and any referenced platform state,
and verifies that the active revision did not change. The state content check
cannot distinguish an identical concurrent rewrite from Terraform's own
metadata-only ETag changes; the lease protects the state during the plan.

The report lists only fixed target and resource-type labels, planned actions,
whitelisted schema field names, unknown fields, refreshed-state drift, and
aggregate counts. It classifies allow-list additions and removals, known WAF tag
changes, alert query line-ending differences, known Container App environment
key changes (including which attribute changed, such as `value` or
`secret_name`, and only whether each side is absent, null, empty or set), and
known check statuses without printing their values or arbitrary
environment key names. Raw state, input values, addresses, IPs, plans, tokens,
and raw provider diagnostics stay private. For `AuthorizationFailed`, only
allowlisted Azure action names and provider resource types may appear in the
error summary; resource IDs and names remain withheld. Normal completion and
failure remove the run's scratch directory; if a runner crash or forced
termination bypasses cleanup, privately inspect and remove only that run and
attempt's scratch directory before reusing the runner. An
incomplete or failed plan, unexpected target, unknown check, detected concurrent
change, or missing permission is a failure, not evidence of a clean plan. A
completed plan is a point-in-time diagnostic, not approval to apply its proposed
changes.

### Differences that were in the dev Lab plan

After the monitoring scope and WAF allow-list were pinned in the private inputs,
the protected plan passed all checks and showed three differences. None changed
who can reach the Lab. The [guarded runner apply](#apply-the-reviewed-lab-differences)
applied them from `main` (#502), and the follow-up plan showed no changes.

| Difference | What it was | Result |
| --- | --- | --- |
| WAF policy tags `managed-by` and `workload` | Configured tags the live policy lacked | Applied. The allow-list was unchanged |
| `WORKBENCH_UNFINISHED_AGENTS_ENABLED` added | The app already treated an absent flag as false | Applied. Same behavior |
| `WORKBENCH_CREATION_KEY_SHA256` shown as changed | Only the `value` attribute differed: live was empty, configured was unset. The Key Vault secret reference was the same | Cleared by the same app update. It was never a different key and does not involve Entra sign-in (#278) |

Differences that come from outside Terraform, such as the image moving through
**Deploy Lab image**, are expected. Re-run the plan diagnostic before any apply.

### Pin the existing Lab monitoring scope

The manual
[`Reconcile private Lab monitoring scope input`](../.github/workflows/reconcile-lab-monitor-scope.yml)
workflow addresses the missing scope source in #445 without changing the live
monitoring association or the WAF. Its default `inspect` operation writes no
canonical inputs. The `pin-existing-scope` operation appends the existing dev
scope to `workbench-dev.tfvars` only when neither an explicit scope nor a
platform-state output already supplies it. It does not import addresses, change
the allow-list, run a Terraform apply, or claim that a full plan is clean. It
refuses unexpected non-null source values, including empty strings, rather than
rewriting ambiguous inputs.

Run it only from reviewed `main` on the private runner, with the protected
`terraform-state` environment and `TF_LAB_PLAN_CONFIG` described above. Starting
the runner and approving that environment are separate operator decisions. The
state identity also needs temporary Reader access to the existing Container App
and monitoring scoped service; remove those grants after the run. Unlike a full
AzureRM plan, this operation does not require the app's secret-list action.

The workflow checks the saved association and the live, healthy association
against the existing Lab workspace, verifies the active immutable image, and
reads any configured platform state from the approved private backend. It
resolves both the original and proposed inputs with Terraform before writing.
It also compares the known unfinished-agent flag with the active revision; this
is a partial app inspection, not a substitute for the full plan.
Unexpected scopes, duplicate assignments, changed state or inputs, a changing
revision, or unsupported blob properties stop the operation. The input update
uses the original ETag and a short exclusive blob lease, preserves the existing
input bytes and supported metadata, and verifies the result before releasing
the lease. If the write outcome is uncertain, inspect the protected input
privately before retrying.

Blob versioning can retain the prior canonical inputs after an update, and
Terraform's temporary state lock can retain lock metadata in state versions.
Both follow the existing storage retention policy. The workflow reports only
fixed status labels and removes its private scratch files; it never publishes
input values, IP addresses, state, or plans.

### Pin the live Lab WAF allow-list

Terraform plans from its inputs, not from state. A WAF allow-list entry added by
hand in Azure therefore stays out of the saved inputs, and a full plan proposes
to delete it. The manual
[`Reconcile private Lab WAF allow-list input`](../.github/workflows/reconcile-lab-waf-allowlist.yml)
workflow keeps those addresses without committing them to the repository. It
appends the live entries that `workbench-dev.tfvars` lacks to that private
input, next to the state, so the next plan stops proposing their removal.

The default `inspect` operation writes nothing and reports only counts. The
`pin-live-allowlist` operation also needs `expected_missing`, the reviewed
number of live entries missing from the inputs (1 to 10). A different count
stops the run, so unexpected live entries are never pinned. Run `inspect`
first and review the count.

It reads only the existing `foundry-workbench` Lab WAF, and only when that
policy has exactly the expected enabled `BlockUnlistedClients` rule over the
`SocketAddr` condition. It refuses duplicates, entries that are not single
hosts, equivalent addresses written differently, and a list that would exceed
ten entries. Terraform resolves the inputs before and after the change, and the
only allowed difference is the appended entries. The write uses the original
ETag and a short exclusive blob lease, preserves every other byte and the
supported blob metadata, and verifies the result. Nothing is added when the
inputs already hold every live entry. A completed pin does not make a full
plan clean; confirm that with a fresh approved plan.

Run it only from reviewed `main` on the private runner, with the protected
`terraform-state` environment and `TF_LAB_PLAN_CONFIG` described above. Starting
the runner and approving that environment are separate operator decisions. The
state identity also needs temporary Reader access to the Lab WAF policy and the
existing Container App (or their resource group), because the workflow verifies
the active revision before it writes; remove both after the run. The workflow never runs a Terraform
apply, changes the WAF, or changes any public access. Blob versioning and
state-lock retention behave as described for the monitoring scope. It reports
only fixed labels and counts and never publishes input values or IP addresses.

### Apply the reviewed Lab differences

The manual
[`Apply reviewed private Lab Terraform changes`](../.github/workflows/apply-lab-terraform.yml)
workflow is the only runner path that applies Lab Terraform. It exists for the
two harmless differences in the table above: the WAF policy tags and the
`WORKBENCH_UNFINISHED_AGENTS_ENABLED` setting. It runs from reviewed `main` on
the private runner, in the protected `terraform-state` environment, with the
same state identity and `TF_LAB_PLAN_CONFIG` as the plan diagnostic. It shares
the `terraform-state-access` group with other state operations and the
`deploy-lab` group with image rollouts, so a stale plan can't revert a newer
image.

It plans the whole Lab root and applies only when the plan holds nothing else:

- The WAF policy changes only its two tags, and the allow-list is unchanged.
- The Container App changes only its settings: it adds
  `WORKBENCH_UNFINISHED_AGENTS_ENABLED` and may show the known
  `WORKBENCH_CREATION_KEY_SHA256` representation difference. Its image,
  secrets, ingress, scale and identity don't change.
- The three alerts have no changes.
- No resource is created, deleted, replaced or imported, no output changes, no
  value is unknown, and every check passes.

Anything else stops with nothing applied. The `check` operation, the default,
plans and reports without applying. The `apply` operation re-checks that the
state, the canonical inputs and the active image didn't change during planning,
then applies the exact saved plan after verifying its digest. It never uses
`-target`, `-refresh=false`, `-lock=false` or `-auto-approve`, and it doesn't
change the allow-list or any public access.

After the apply it verifies that the state recorded the change with the same
lineage, the inputs are unchanged, and the active image digest is unchanged. It
waits up to ten minutes for the new revision to become ready. A follow-up plan
must again hold only reviewed changes; the creation-key representation
difference may remain. The output has only actions, field names and counts.
Locked plans and applies add retained state-blob versions, as the diagnostic
does.

The state identity has no write roles by default. A run needs these separately
approved, temporary grants, all removed afterwards:

1. The Reader and app `listSecrets` grants that the
   [plan diagnostic](#diagnose-the-existing-lab-plan) needs.
2. The custom role `Foundry Lab Terraform Apply`, created for the run and
   deleted afterwards. Its assignable scope is the Lab resource
   group, assigned at only four resources: the Container App
   (`Microsoft.App/containerApps/write`), its managed environment
   (`Microsoft.App/managedEnvironments/join/action`), its user-assigned identity
   (`Microsoft.ManagedIdentity/userAssignedIdentities/assign/action`) and the
   WAF policy (`Microsoft.Network/frontdoorWebApplicationFirewallPolicies/write`).
   If a run fails with `AuthorizationFailed`, the log names the denied actions;
   add only those and re-run.
3. Starting the runner and approving the protected environment for that run.

If only the WAF tags are planned, the app grants aren't used. Stop if any grant
isn't approved, and don't use the VM's managed identity or a local apply as a
fallback.

### 2. Configure and initialize

Create or review the local `workbench/infra/dev.tfvars` using
[dev.tfvars.example](../workbench/infra/dev.tfvars.example). Replace example identifiers with
your actual deployment settings, and never overwrite a working environment blindly.
Create or review the ignored local `workbench/infra/backend.hcl` using
[backend.hcl.example](../workbench/infra/backend.hcl.example). Replace the placeholders with
the intended account, subscription, container, and separate Lab state key. Keep
the existing state key for an established deployment. Don't edit the tracked
example to store environment configuration.

**Read the platform names from its state.** The Lab needs the resource group,
virtual network, Foundry account and project, and Cosmos DB account names the
platform root created. Set `platform_state` in `dev.tfvars` to the platform
root's state location, and the Lab reads those names from the platform outputs
(`resource_group_name`, `workload_virtual_network_name`,
`management_virtual_network_name`, `foundry_account_name`,
`foundry_project_name`, `cosmos_account_name`, `monitor_private_link_scope_name`)
through Microsoft Entra ID. Apply the
platform root first. Set `platform_state = {}` to use the state account
`terraform/bootstrap` creates. Each field defaults to its names. A name you set explicitly still wins, so an existing Lab keeps
working unchanged. The plan stops with a clear message if a name is missing, for
example `management_vnet_name` when the platform's management network is off.
An empty scope override does not count as a configured scope. If neither the
override nor the platform state's `monitor_private_link_scope_name` output is
nonempty, the Lab falls back to `ampls-aifnd-dev` and warns. That's right for
the dev platform only. Review a platform plan before applying to refresh its
outputs; an apply may include other infrastructure changes. For the existing dev Lab,
the [guarded monitoring workflow](#pin-the-existing-lab-monitoring-scope) can
pin its verified, already-live scope without an apply. For another environment,
set its verified scope explicitly.

**Start from the canonical inputs, not an old local copy.** A stale
`dev.tfvars` can plan to turn off agent creation, drop the creation-key secret,
or destroy the alert action group. Keep one complete inputs file (everything
except `image_digest`) next to the Lab's state blob with the same private access,
for example `<state-key-prefix>/workbench-dev.tfvars`, and download it before
each plan:

```powershell
az storage blob download --auth-mode login --subscription '<state-subscription-id>' --account-name '<state-account>' --container-name '<state-container>' --name '<state-key-prefix>/workbench-dev.tfvars' --file workbench/infra/dev.tfvars
```

After a change to the inputs, upload the file again. A plan with only a new
`image_digest` shows no change to the running image, because Terraform ignores it
after the first apply (see "Deploy a new image from GitHub Actions"). The inputs
can hold alert email addresses, so never commit them.

```powershell
terraform -chdir=workbench/infra init -backend-config=backend.hcl
terraform -chdir=workbench/infra validate
```

For a deliberate existing-state migration, use
`terraform -chdir=workbench/infra init -migrate-state -backend-config=backend.hcl`
instead of plain init, following the preservation checks above.

### 3. Bootstrap only a new Lab

Skip this step if the Lab already exists. If its registry doesn't exist yet,
create a foundation-only plan:

```powershell
$plan = Join-Path $env:TEMP ("ai-foundry-lab-bootstrap-" + [guid]::NewGuid().ToString("N") + ".tfplan")
terraform -chdir=workbench/infra plan -var-file=dev.tfvars -var=bootstrap_only=true "-out=$plan"
terraform -chdir=workbench/infra show "$plan"
```

Review the foundation resources and costs. Only after approval, use the apply
and cleanup block in step 6 on this plan, then continue to step 4. Bootstrap
omits the app, so it doesn't deploy a usable UI. **Never use bootstrap mode
against an existing app.** The `prevent_destroy` guard blocks accidental app
destruction. Don't persist `bootstrap_only=true` into the normal deployment
configuration.

### 4. Build and select an immutable image

`build.ps1 -Private` stages only the files `.dockerignore` allows, leaving out local
dependencies, state, plans, and environment files. Every top-level `*.py` module
ships except tests and `verify_private.py`, so adding a module needs no edit to
the Dockerfile, `build.ps1`, `test-build.ps1` or the CI compile step. Add a
pattern to `.dockerignore` only to keep a file out of the image or to ship a new
data file. A package directory such as `agent_templates/` is the exception. It
needs its own `COPY` line in the Dockerfile, a rule block in `.dockerignore` and a
staging step in `build.ps1` (copy the `agent_runtime/` or `agent_templates/`
pattern). `basic_agent_source/` is another example: a vendored copy of
`hosted-agents/basic-responses-agent/` that the spec card's bundle download
packages offline, because only `workbench/` is in the image context. A test
fails if it drifts from the original. `agent_templates/agents/` holds one JSON file per library agent, and its
`.dockerignore` rules and `build.ps1` step ship every `*.json` file in it, so a new
library agent needs no edit to either. `test_image_context.py` fails if a module or
package that `app.py` imports isn't in the image, or if a library agent file isn't
let into it. The build also imports every module in the finished image before it
pushes. The Premium Azure Container
Registry (ACR) has public access and admin credentials disabled. The private
build uses the local Linux Docker engine on the current authorized
private-network runner, such as a jumpbox or continuous integration (CI) agent.
Install Docker with Linux-container support, or Podman with a `docker` command that points to it, and Azure CLI. Authenticate with an
authorized identity, preferably managed identity, and give it registry-scoped
push/pull permission. Both the runner and Docker engine need private DNS and
routing to ACR, plus access to the base-image and package sources.

The helper logs Docker into ACR using Azure CLI, so use the runner's approved
Docker credential storage. It validates the image as its non-root user before
pushing, checks the registry's tag digest against the local build (Podman recompresses layers on push, so for Podman it compares the pushed image's config digest with the local image ID), then verifies
a pull by immutable digest. You must supply the subscription, registry, and
release tag. Use a unique tag and don't overwrite it during
verification. The helper doesn't create virtual machines, grant roles, or
upload remote commands. Without `-Private`, the helper uses ACR Tasks, which
requires a registry that is deliberately public. See the fallback below.

Run `./workbench/test-build.ps1` from the repository root to check staging and
success/failure handling with mocked Azure CLI and Docker commands. It doesn't
contact Azure or build an image. A real build still requires the private runner
and the push/pull verification below.

Both Docker stages and the frontend CI container use immutable base-image
digests. Refresh these deliberately and rebuild for security updates. Pinning
prevents silent changes, but it doesn't patch vulnerabilities. Python transitive
dependencies still resolve during builds, so this isn't a byte-for-byte
reproducible build guarantee.

```powershell
./workbench/build.ps1 -Private -Subscription '<workload-subscription-id>' -Registry '<registry-name>' -Tag '<unique-release-tag>'
```

Replace every placeholder and run from the approved private-network environment.
The build, push, and verified pull must all succeed. Record the returned digest
and the prior recovery image. Terraform only reads `image_digest` when it first
creates the Container App, so for a new image on an existing Lab use the
**Deploy Lab image** workflow instead of steps 5 and 6. For a first deploy, set
`image_digest` in local
`workbench/infra/image.auto.tfvars` using
[image.auto.tfvars.example](../workbench/infra/image.auto.tfvars.example). Mutable tags aren't
accepted as deployment inputs.

**No private Docker engine?** ACR Tasks can't reach the private registry,
because Tasks isn't an ACR trusted service, but registry import is. If briefly
holding the sample source and image in an authenticated public-endpoint
registry is acceptable, build there and import by digest:

1. Create a temporary Basic registry with admin user and anonymous pull
   disabled, and tag it as temporary.
2. Run `./workbench/build.ps1` without `-Private` against the temporary
   registry, then record the digest with `az acr repository show`.
3. Validate the image as its non-root user with `az acr run`. Give the step
   `entryPoint: python` and `workingDirectory: /app`; ACR Tasks defaults to
   `/workspace`.
4. Copy it into the private registry by digest:
   `az acr import --name '<registry-name>' --registry '<temporary-registry-resource-id>' --source 'workbench@<digest>' --image 'workbench:<unique-release-tag>'`.
5. Confirm the digest from the private-network runner, then delete the
   temporary registry.

### 5. Plan and review the image rollout

```powershell
$plan = Join-Path $env:TEMP ("ai-foundry-lab-" + [guid]::NewGuid().ToString("N") + ".tfplan")
terraform -chdir=workbench/infra plan -var-file=dev.tfvars "-out=$plan"
terraform -chdir=workbench/infra show "$plan"
```

Stop on failure. Verify the exact image digest and review every infrastructure
action. A normal image-only update shouldn't recreate shared resources. For
first-time review support, verify the additive Cosmos DB index is ready before
promoting the review-enabled image. Reject unrelated changes.

### 6. Apply the approved plan and clean up

Applying a saved plan has no further Terraform approval prompt. Run this
block only after you've approved the plan from step 3 or step 5:

```powershell
try {
	terraform -chdir=workbench/infra apply "$plan"
	if ($LASTEXITCODE -ne 0) { throw "Apply failed; inspect state before replanning" }
} finally {
	Remove-Item -LiteralPath $plan -Force -ErrorAction SilentlyContinue
}
```

For a failed or abandoned plan, run
`Remove-Item -LiteralPath $plan -Force -ErrorAction SilentlyContinue` as well.
Plans may contain sensitive values, so don't keep them as deployment history.
Keep Terraform state, state backups, and source configuration. Generate a
fresh reviewed plan for a retry.

### 7. Verify the deployed application

```powershell
terraform -chdir=workbench/infra output -raw private_url
```

Confirm the intended revision and immutable image are ready before using this
URL. From authorized private-network access, run the sample-data runtime check:

```powershell
./workbench/test-private.ps1 -BaseUrl '<verified-private-url>'
```

Replace the URL placeholder with the Terraform output. The check uses the
deployed default agent and its configured specialist bindings. Review the
sample application prompt before using it against a different agent profile.
It makes one billable sample request. When that agent has specialist tools, the
check requires a verified specialist receipt, and a nonempty answer isn't enough.

The same check verifies Cosmos create, read, conditional update, stale-ETag
rejection, and deletion of its own test conversation. Use `-SkipAgentCall`
for storage checks without model generation. For read-only configuration and
cached dependency checks:

```powershell
python workbench/verify_private.py --base-url '<verified-private-url>'
```

For the default **Checklist and case helper**, an additional, explicitly
approved check can exercise both specialist handoffs through the same private
API used by the Lab:

```powershell
python workbench/verify_private.py --base-url '<verified-private-url>' --check-review-specialists
```

This sends up to two fictional, billable coordinator requests; each can also
invoke a billable specialist, including when a request fails. It first requires
the expected coordinator and both specialist bindings, then requires exactly
one verified receipt for the expected specialist in each response. It stops on a
failure without retrying and does not save a Lab conversation unless
`--check-storage` is also supplied. In that case it saves and deletes the final
case-review turn. Do not combine it with `--run-agent`, which is the separate
single-request check. Receipt checks do not prove which model a hosted agent
used, establish answer quality, or replace a browser-based private UI check.

The verifier also supports `--loopback` inside the existing Lab container. This
can check the runtime through approved container-console access without starting
a virtual machine or changing ingress. Transfer only the reviewed helper through
the approved administration path and remove that temporary artifact afterward.
Verification scripts aren't bundled in the runtime image. Loopback results
state that browser ingress was **not** verified. Neither path
establishes model quality.

Successful private HTTPS, agent execution, and Cosmos CRUD verification are all
required. An infrastructure apply alone isn't an application acceptance test. For the
new workflow, also complete [review delivery checks](review-workflow.md#delivery-checks),
including clarification, resume, and prior-snapshot verification.
Interrupted reviews also offer [recovery](review-workflow.md#recover-an-interrupted-review)
from saved run input after a recovery window. Recovery requires cost
confirmation, keeps the earlier attempt, and consumes another run. It doesn't
turn the process-local task into a durable worker or retrieve an earlier
remote result.

Terraform manages the private runtime settings: `WORKBENCH_MODE`,
`WORKBENCH_VISIBLE_AGENTS`, `WORKBENCH_DEFAULT_AGENT`, `WORKBENCH_TITLE`, exact
host/origin allowlists, Foundry project endpoint, Cosmos endpoint, and
managed-identity client ID. Terraform provisions the Cosmos data-plane
resources, and the runtime never creates them.

Browser tests use controlled API responses, so they don't replace this
deployment check.

## Deploy a new image from GitHub Actions

The **Deploy Lab image** workflow (`.github/workflows/deploy-lab.yml`) ships the
current `main` to a running Lab without a jumpbox. It runs on its own when an
application change under `workbench/` merges to `main`; docs, tests, and Terraform
changes alone don't start it. Before starting the private runner, it waits for the
**Validate** workflow to succeed for the exact same `main` commit. A manual run
from the Actions tab on `main` uses the same gate and cannot bypass validation.
It:

1. Starts the runner VM if it is deallocated. This step runs on a GitHub-hosted
   runner, and the deploy identity can only start that one VM.
2. Builds the image on the repository's self-hosted runner (see
   [`terraform/runner`](../terraform/runner/README.md)) and checks it as its
   non-root user. The runner has Docker but
   no Azure CLI, so the workflow runs the CLI from Microsoft's `azure-cli` image.
3. Signs in to Azure with a short-lived GitHub token. No secret is stored.
4. Pushes the image to the private registry through its private endpoint, which
   the runner reaches over the peered VNet. Nothing is published to GitHub
   Packages, and nothing in Azure is made public.
5. Updates the Container App to the new digest, waits for the new revision to be
   healthy, and restores the previous image if it isn't.

The runner deallocates itself after 30 idle minutes, so a deploy costs about
$0.15 of compute ($0.192 an hour for `Standard_D4s_v5`).

The run summary shows the new digest and the previous image to recover to.

**The workflow owns the running image.** Terraform sets `image_digest` only when
it first creates the Container App and ignores later image changes
(`ignore_changes` on the container image). A `terraform apply` therefore never
rolls the app back, and `image_digest` can be any valid digest when you apply
other infrastructure changes. To see which image is running, read the latest run
summary or the Container App's current revision.

### One-time setup for a new subscription

The deploy identity, its roles and the GitHub environment are Terraform, in
[terraform/identity](../terraform/identity/README.md). Run that root once, after
the Lab and runner roots, signed in as someone who can create an Entra app
registration, create role definitions and assignments on the Lab and runner
resource groups, and administer the repository's environments. It's safe to run
again, and deploy.ps1 -Stage identity runs it with the same approval step as
every other root.

The root creates an app registration whose only credential is a federated
credential for the lab-deploy environment of your repository. It also creates a
custom role that can import an image into the registry and update the one
Container App, the built-in AcrPush role on the registry so the workflow can
push, and a custom role that can read and start the one runner VM, and nothing
else. None of them can change registry networking, other resources, or role
assignments. It reads the repository and owner IDs from GitHub because GitHub
signs the token with a subject that includes them. If sign-in fails with "No
matching federated identity record", set the subject from the error as
deploy_federated_subject.

It also creates the lab-deploy environment, limits its deployment branches to
main, and sets the variables the workflow reads (AZURE_CLIENT_ID,
AZURE_TENANT_ID, AZURE_SUBSCRIPTION_ID, AZURE_RESOURCE_GROUP,
LAB_REGISTRY, LAB_CONTAINER_APP, LAB_RUNNER_VM and
LAB_RUNNER_RESOURCE_GROUP). None of them is a secret. A Lab set up with the old
setup scripts adopts its identity by import; see
[Adopt identities the old scripts created](../terraform/identity/README.md#adopt-identities-the-old-scripts-created).
The runner's network security group (NSG) denies all VNet traffic by default.
Set `registry_private_endpoint_ips` in `terraform/runner` to the registry private
endpoint addresses (registry and data endpoint) so it may reach only those on
TCP 443. The workflow works in a public repository because it runs only on
`main`, behind the `lab-deploy` environment. Don't point any
pull request workflow at the self-hosted runner.

Use the jumpbox route in steps 4 to 6 when you need to change infrastructure, not
just the image.

## Recover after a subscription suspension

If the subscription is disabled or put in a warned state, Azure suspends the
Container Apps compute. Nothing in the repository changed, and the plan shows no
drift. Look for these signs:

- The Lab app and its environment report `Failed`, and revision calls return
  `ManagedClusterSuspended`.
- The app looks like a placeholder, with no replicas.
- `az account show` still says `Enabled`. The CLI caches that value.

Recover in this order. Don't taint, replace or destroy the app. It has
`prevent_destroy`, and a replacement isn't needed.

1. Read the live subscription state from Azure Resource Manager, not the CLI
   cache, and wait until it is `Enabled`:

   ```powershell
   az rest --method get --url "https://management.azure.com/subscriptions/<subscription_id>?api-version=2022-12-01" --query state
   ```

1. Write the Container Apps environment and then the app once with no change, so
   Azure re-evaluates them. The tags must equal `local.tags` in
   `workbench/infra/main.tf` (`workload = "foundry-workbench"`,
   `managed-by = "terraform"`), or Terraform shows drift afterward:

   ```powershell
   az rest --method patch --url "https://management.azure.com/subscriptions/<subscription_id>/resourceGroups/<resource_group>/providers/Microsoft.App/managedEnvironments/<environment>?api-version=2024-03-01" --body '{"tags":{"workload":"foundry-workbench","managed-by":"terraform"}}'
   az rest --method patch --url "https://management.azure.com/subscriptions/<subscription_id>/resourceGroups/<resource_group>/providers/Microsoft.App/containerApps/<app>?api-version=2024-03-01" --body '{"tags":{"workload":"foundry-workbench","managed-by":"terraform"}}'
   ```

   If the environment stays `Failed`, repeat its write once. In the case this
   section comes from, the environment needed two writes and the app one.

1. Confirm the app's `provisioningState` is `Succeeded`, its `runningStatus` is
   `Running`, and the active revision has one healthy replica at 100% of
   traffic. Then run [step 7](#7-verify-the-deployed-application).
1. If a Front Door is enabled, its endpoint can also be left disabled. See
   [Operate and recover the draft Front Door](ingress-access.md#operate-and-recover-the-draft-front-door).

The record of the first suspension is
[#255](https://github.com/michael-rechani/foundry-agent-accelerator/issues/255).
Apart from that, back up privately the state and settings that stay out of the
repository on purpose (`dev.tfvars`, `backend.hcl`, `image.auto.tfvars`, your
allowed IP and the Terraform state), because they aren't in Git.

## Related content

- [The Lab](../workbench/README.md)
- [Lab configuration, storage, and cost](lab-configuration-and-cost.md)
- [Lab diagnostics, alerts, and caching](lab-diagnostics.md)
- [Private deployment runbook](private-deployment.md)
- [Permissions reference](permissions.md)
- [Documentation index](README.md)

# Deploy the Lab

[Home](../README.md) / [Docs](README.md) / [The Lab](../workbench/README.md) / Deploy

This page is part of the [Lab guide](../workbench/README.md). It's the runbook
for deploying the Lab with the Terraform root in `workbench/infra`. To run the
Lab on your own machine without Azure, use
[Local development](../workbench/README.md#local-development) instead.

## In this guide

- [1. Confirm prerequisites and state ownership](#1-confirm-prerequisites-and-state-ownership)
- [2. Configure and initialize](#2-configure-and-initialize)
- [3. Bootstrap only a new Lab](#3-bootstrap-only-a-new-lab)
- [4. Build and select an immutable image](#4-build-and-select-an-immutable-image)
- [5. Plan and review the image rollout](#5-plan-and-review-the-image-rollout)
- [6. Apply the approved plan and clean up](#6-apply-the-approved-plan-and-clean-up)
- [7. Verify the deployed application](#7-verify-the-deployed-application)
- [Deploy a new image from GitHub Actions](#deploy-a-new-image-from-github-actions)
- [Recover after a subscription suspension](#recover-after-a-subscription-suspension)

## Deployment

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

### 2. Configure and initialize

Create or review the local `workbench/infra/dev.tfvars` using
[dev.tfvars.example](../workbench/infra/dev.tfvars.example). Replace example identifiers with
your actual deployment settings, and never overwrite a working environment blindly.
Create or review the ignored local `workbench/infra/backend.hcl` using
[backend.hcl.example](../workbench/infra/backend.hcl.example). Replace the placeholders with
the intended account, subscription, container, and separate Lab state key. Keep
the existing state key for an established deployment. Don't edit the tracked
example to store environment configuration.

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
pattern). `agent_templates/agents/` holds one JSON file per library agent, and its
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
current `main` to a running Lab without a jumpbox. Run it from the Actions tab
with **Run workflow** on `main`. It:

1. Builds the image on a GitHub runner, checks it as its non-root user, and
   pushes it to this repository's **private** GitHub package.
2. Signs in to Azure with a short-lived GitHub token. No secret is stored.
3. Imports the image into the private registry by digest. Registry import is
   allowed for a registry with public access off, so nothing in Azure is made
   public.
4. Updates the Container App to the new digest, waits for the new revision to be
   healthy, and restores the previous image if it isn't.

The run summary shows the new digest and the previous image to recover to.

**The workflow owns the running image.** Terraform sets `image_digest` only when
it first creates the Container App and ignores later image changes
(`ignore_changes` on the container image). A `terraform apply` therefore never
rolls the app back, and `image_digest` can be any valid digest when you apply
other infrastructure changes. To see which image is running, read the latest run
summary or the Container App's current revision.

### One-time setup for a new subscription

Run this once, signed in as someone who can create an Entra app registration and
assign roles on the resource group. It's safe to run again.

```powershell
./workbench/setup-deploy-identity.ps1 -Subscription '<subscription-id>' -ResourceGroup '<resource-group>' `
  -Registry '<registry-name>' -ContainerApp '<container-app-name>' -ManagedIdentity '<app-identity-name>' `
  -Repository '<owner>/<repository>'
```

The script creates an app registration whose only credential is a federated
credential for the `lab-deploy` environment of your repository, plus a custom role
that can import an image into the registry and update the one Container App. It
can't change registry networking, other resources, or role assignments. It reads
the repository and owner IDs with `gh` because GitHub signs the token with a subject
that includes them. If sign-in fails with "No matching federated identity record",
rerun the script with the subject from the error as `-FederatedSubject`.

Then create a `lab-deploy` environment in the repository, limit its deployment
branches to `main`, and add the variables the script prints as environment
variables: `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`,
`AZURE_RESOURCE_GROUP`, `LAB_REGISTRY` and `LAB_CONTAINER_APP`. Keep them out of
committed files. The workflow needs a private repository, so the image package
stays private. Don't run it from a public repository.

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

Recover in this order. Don't taint, replace or destroy the app: it has
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
Apart from that, state and settings that stay out of the repository on purpose
(`dev.tfvars`, `backend.hcl`, `image.auto.tfvars`, your allowed IP and the
Terraform state) have to be backed up privately, because they aren't in Git.

## Related content

- [The Lab](../workbench/README.md)
- [Lab configuration, storage, and cost](lab-configuration-and-cost.md)
- [Lab diagnostics, alerts, and caching](lab-diagnostics.md)
- [Private deployment runbook](private-deployment.md)
- [Permissions reference](permissions.md)
- [Documentation index](README.md)

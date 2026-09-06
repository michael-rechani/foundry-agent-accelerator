# Microsoft Foundry hosted-agent samples

[![Validate](https://github.com/michael-rechani/ai-foundry-samples/actions/workflows/validate.yml/badge.svg)](https://github.com/michael-rechani/ai-foundry-samples/actions/workflows/validate.yml)
[![Terraform 1.16.1](https://img.shields.io/badge/Terraform-1.16.1-844FBA?logo=terraform&logoColor=white)](terraform/README.md)
[![Python 3.13](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)](hosted-agents/README.md)
[![Microsoft Foundry](https://img.shields.io/badge/Microsoft_Foundry-hosted_agents-0078D4?logo=microsoftazure&logoColor=white)](https://learn.microsoft.com/azure/foundry/agents/concepts/hosted-agents)

Deploy a practical Microsoft Foundry foundation, publish an agent or agentic
solution, and try it through a usable application before deciding what to build
next. Private networking, managed identities, deployment scripts, and a sample UI
provide reusable starting points. Review coordinators and specialists are reference
implementations, not a requirement for every solution.

Use Foundry's native agent development, evaluation, and tracing capabilities rather
than rebuilding its portal here. The Lab supplies application access and example
workflows; it is not a general-purpose evaluation engine or agent designer. The
separate cost calculator compares hosted-runtime assumptions with self-managed
agents on Azure virtual machines. Optional APIM configuration is retained for
future governed entry points.

The [AI Foundry Lab](workbench/README.md) provides a chat-first
React UI, curated agent catalog, session performance metrics, and explicitly
saved shared Cosmos conversations. It is deployed separately in an internal
Container Apps environment and does not require APIM publication.

The Lab has bounded API admission and deadlines, periodic dependency checks,
retained operational logs, and an isolated Entra-authenticated remote state key.
It is intended for example data, with shared history and no end-user login.
Secrets must use Key Vault or be eliminated through managed identity. The
[credential handling guide](docs/credential-migration.md) explains secret ownership,
keyless resource reads, and protection of Terraform state and backups.

[Architecture](#architecture) · [Deploy](#quick-start) · [Review walkthrough](hosted-agents/review-coordinator-agent/README.md) · [Cost model](cost-comparison/README.md)

| Build | Ship | Measure |
| --- | --- | --- |
| Private Foundry, management network, and optional APIM through Terraform and AVM | Immutable agent versions with delegation checks and conservative rollback cleanup | Hosted sandbox break-even against self-managed Azure VMs |

## Architecture

![Deployed AI Foundry Lab: private browser access, managed-identity review agents, and shared Cosmos history](docs/images/foundry-overview.svg)

[Full-size overview](docs/images/foundry-overview.svg) · [Operations and security](docs/images/foundry-operations.svg)

For a deeper view, see the [component map and request sequence](docs/architecture.md#component-interactions)
and [persisted review lifecycle](docs/review-workflow.md#execution-and-persistence).
These include editable draw.io sources with official Microsoft Azure icons;
the overview here stays focused on the platform as a whole.

For extension decisions and new customer examples, use the
[Foundry extension guide](docs/architecture-assessment.md): ownership boundaries,
native capabilities, and a checklist for adding agents.

Arrows show the Lab request and history paths. APIM is optional and disabled by
default. Use the [APIM API guide](docs/apim-review-api.md) when a governed gateway
is required, including caller authorization and private backend verification.

See [optional integrations](docs/optional-integrations.md) for restoring APIM or
adding Search-backed retrieval. Both Terraform implementations are retained;
Search remains a connected Foundry platform dependency, not a current agent tool.

See [operations, request flow and trust boundaries](docs/architecture.md) for
authentication, data ownership, and failure behavior.

> [!IMPORTANT]
> This sample creates billable Azure resources. Review the saved Terraform
> plan, regional model pricing, and quota before applying it.

## What you get

- **Repeatable infrastructure:** an Azure Verified Module (AVM) deployment of
  a Foundry account, project, model, Agent Service dependencies, and
  diagnostics.
- **Safer agent delivery:** a Python deployer that packages an immutable
  version, waits for activation, routes the candidate, and runs smoke tests.
  On failure it attempts route restoration and retains candidates when safe
  deletion cannot be confirmed. Promotion is not a zero-exposure canary.
- **Business workflow samples:** deployable case-review and application-review
  agents, plus a coordinator that delegates to them, with synthetic requests
  and explicit human decision boundaries.
- **Swappable specialist bindings:** [customer profiles](docs/agent-profiles.md)
  configure coordinator instructions, named specialists, and mandatory deployment
  checks without changing the platform or coordinator runtime code.
- **Explicit cost assumptions:** a calculator that keeps region-specific rates
  outside the code, ranks Azure GPU VM scenarios, and reports each
  hosted-runtime break-even point.
- **Automated validation:** GitHub Actions checks Python sources, dependencies,
  calculator behavior, Terraform formatting, and Terraform configuration.

## Repository layout

| Path | Purpose |
| --- | --- |
| [workbench/](workbench/) | Private chat UI, FastAPI gateway, shared Cosmos history, browser tests, and isolated deployment infrastructure. |
| [`terraform/`](terraform/) | Deploy a Foundry project, model, Agent Service dependencies, and observability with the official AVM pattern. |
| [`hosted-agents/`](hosted-agents/) | Deploy the basic Responses agent plus case-review and application-review business samples. |
| [`hosted-agents/review-coordinator-agent/`](hosted-agents/review-coordinator-agent/) | Route reviews to specialists; test cancellation, concurrency, and delegation. |
| [`docs/`](docs/) | Architecture, delivery status, and the private deployment runbook. |
| [`cost-comparison/`](cost-comparison/) | Compare self-hosted models on Azure GPU VMs with Foundry hosted-agent costs using replaceable rates. |

## Quick start

This walkthrough deploys the **Foundry infrastructure baseline with Terraform**.
It does not publish Python agents or deploy the separately managed Lab UI.
Run commands from the repository root in the same PowerShell session. Complete
each step successfully before continuing; do not run the apply step until you
have reviewed the saved plan.

**Before you begin:** install Terraform 1.16.1, authenticate Azure CLI to the
intended tenant, and confirm deployment and role-assignment permissions, regional
model quota, and private network access. A secured Azure Storage account and blob
container for Terraform state must already exist; this configuration does not
bootstrap its own backend. Your identity needs Storage Blob Data Contributor on
that container. See [Terraform prerequisites and state guidance](terraform/README.md).

### 1. Configure the deployment

Create or review a local variable file named `terraform.tfvars` in the
[Terraform directory](terraform/README.md). This file is ignored by Git.
For a new environment, the following is a minimal starting point; replace
the subscription placeholder and choose names and a supported region for your
environment:

```hcl
subscription_id       = "<workload-subscription-id>"
base_name             = "aifnd"
environment           = "dev"
location              = "northcentralus"
enable_api_management = false
```

Review [all input defaults](terraform/variables.tf) before proceeding, especially
model deployment, network address ranges, and optional resources. This is not a
minimal-cost configuration. Do not overwrite an existing environment's values or
reuse another deployment's names and state. Check other automatically loaded
variable files and remove unintended command-line overrides.

### 2. Configure remote state

Create or review a local backend file named `backend.tf` in the
[Terraform directory](terraform/README.md), using your pre-created backend.
This file is ignored by Git. Replace every placeholder:

```hcl
terraform {
  backend "azurerm" {
    subscription_id      = "<state-subscription-id>"
    resource_group_name  = "<state-resource-group>"
    storage_account_name = "<state-storage-account>"
    container_name       = "<state-container>"
    key                  = "ai-foundry/<environment>.tfstate"
    use_azuread_auth     = true
    use_cli              = true
  }
}
```

The backend subscription can differ from the workload subscription. Use a unique
state key for each independent deployment, and retain the original key when
updating an existing deployment. Keep these environment-specific files local;
never put access keys or passwords in them. Run from a network path permitted by
the state account, without reopening a private endpoint to public access.

### 3. Initialize and validate

For a new deployment, or an existing deployment with an unchanged backend:

```powershell
terraform -chdir=terraform init
terraform -chdir=terraform validate
```

If resources already exist in local state and you are moving that state to the
remote backend, use `terraform -chdir=terraform init -migrate-state` **instead of
the plain init command**. Verify the destination and preserve a protected backup
before accepting the migration. Never initialize an empty state to manage
resources that already belong to another state.

### 4. Create and review a plan

The first line below only chooses a unique temporary plan filename; Terraform
creates and displays the plan. Keep this PowerShell session open for step 5.

```powershell
$plan = Join-Path $env:TEMP ("foundry-" + [guid]::NewGuid().ToString("N") + ".tfplan")
terraform -chdir=terraform plan -var-file=terraform.tfvars "-out=$plan"
terraform -chdir=terraform show "$plan"
```

Stop if planning fails. Before applying, confirm the subscription, names, regions,
network ranges, model capacity, expected charges, and every create/update/delete
action. Investigate unexpected replacements or deletions. Plans and state can
contain sensitive data: do not commit them or upload them as build artifacts.

### 5. Apply the reviewed plan

Run this block **only after approving step 4**. Applying a saved plan executes
that plan without another Terraform approval prompt. The PowerShell wrapper
checks the exit code and removes the disposable plan after the apply attempt:

```powershell
try {
  terraform -chdir=terraform apply "$plan"
  if ($LASTEXITCODE -ne 0) { throw "Apply failed. Inspect the deployment before making a new plan." }
} finally {
  Remove-Item -LiteralPath $plan -Force -ErrorAction SilentlyContinue
}
```

If you abandon the plan or planning fails, remove its artifact with
`Remove-Item -LiteralPath $plan -Force -ErrorAction SilentlyContinue` as well.
Preserve state and protected backups. After configuration changes, generate and
review a new plan rather than reusing an earlier one.

### 6. Inspect the outputs

After a successful apply, retrieve the values needed for agent deployment:

```powershell
terraform -chdir=terraform output -raw resource_group_name
terraform -chdir=terraform output -raw foundry_project_endpoint
terraform -chdir=terraform output -raw model_deployment_name
```

These outputs identify the infrastructure; they do not prove an agent or the Lab
application is deployed or healthy.

### After deployment

- [Publish and test hosted agents](hosted-agents/README.md) from authorized private-network access.
- [Deploy or access the Lab UI](workbench/README.md) using its separate Terraform state and image rollout.
- [Compare hosting costs](cost-comparison/README.md) using explicit, environment-specific assumptions.

## Production considerations

Foundry data-plane endpoints, Lab ingress, and the state backend use private
network access. The Lab's Premium registry uses a private endpoint with public
access disabled. Log Analytics ingestion/query is private-only through Azure
Monitor Private Link. Registry admin and Log Analytics local key authentication
are disabled. APIM is not deployed; its review API remains optional.
Before production use:

- Use the AVM pattern's BYOR path so platform-owned Key Vault, Storage,
  Cosmos DB, and AI Search resources have independent lifecycles.
- Integrate the workload VNet and private DNS zones with the landing-zone hub,
  firewall, DNS resolver, and on-premises routing design.
- Send diagnostics to a centrally managed Log Analytics workspace.
- Configure and test alert notification delivery and backup/restore procedures.
- Add user authorization and owner-scoped history before using confidential data.
- Replace process-local limits with shared admission control before scaling out.
- Assign least-privilege data-plane roles to each hosted agent's dedicated
  Microsoft Entra identity.
- Pin model versions and test Responsible AI policies before promotion.
- Store Terraform state in an Azure Storage backend with Entra ID
  authentication, locking, versioning, and restricted network access.

## Validation

Pull requests and pushes to `main` run Python compilation and tests, validate
all four deployment CLIs, exercise coordinator real-SDK contracts using an
offline HTTP transport, check publisher-variable cases, check Terraform
formatting, and run `terraform validate`.
Workbench checks also cover API validation, saved-receipt handling, deployment
input guards, and Playwright workflows at desktop and mobile sizes. Browser
tests use synthetic mocked APIs, not Azure credentials or live agent calls.
These checks do not create Azure resources. A real plan and hosted-agent smoke
test still require an authenticated Azure subscription, regional model quota,
and the documented RBAC roles.

## References

- [Azure AI Foundry AVM pattern](https://registry.terraform.io/modules/Azure/avm-ptn-aiml-ai-foundry/azurerm/latest)
- [Create Microsoft Foundry with Terraform](https://learn.microsoft.com/azure/foundry/how-to/create-resource-terraform)
- [Foundry hosted agents](https://learn.microsoft.com/azure/foundry/agents/concepts/hosted-agents)
- [Foundry Agent Service pricing](https://azure.microsoft.com/pricing/details/foundry-agent-service/)

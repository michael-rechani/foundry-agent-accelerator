# Microsoft Foundry hosted-agent samples

[![Validate](https://github.com/michael-rechani/ai-foundry-samples/actions/workflows/validate.yml/badge.svg)](https://github.com/michael-rechani/ai-foundry-samples/actions/workflows/validate.yml)
[![Terraform 1.16.1](https://img.shields.io/badge/Terraform-1.16.1-844FBA?logo=terraform&logoColor=white)](terraform/README.md)
[![Python 3.13](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)](hosted-agents/README.md)
[![Microsoft Foundry](https://img.shields.io/badge/Microsoft_Foundry-hosted_agents-0078D4?logo=microsoftazure&logoColor=white)](https://learn.microsoft.com/azure/foundry/agents/concepts/hosted-agents)

Deploy a practical Microsoft Foundry baseline, publish a Responses-protocol
hosted agent, and compare its hosting costs with self-managed agents on Azure
virtual machines.

[Architecture](#architecture) · [Deploy](#quick-start) · [Agent guide](hosted-agents/README.md) · [Cost model](cost-comparison/README.md) · [Production notes](#production-considerations)

| Build | Ship | Measure |
| --- | --- | --- |
| Foundry project, model, Agent Service, and diagnostics through Terraform and AVM | Immutable Python agent versions with smoke testing and automatic rollback | Hosted sandbox break-even against self-managed Azure VMs |

## Architecture

![Architecture showing the Terraform baseline, Microsoft Foundry resources, Python agent deployment, and cost model](docs/images/foundry-sample-architecture.svg)

Terraform establishes the Foundry project, model, Agent Service dependencies,
identity, and observability. The deployer promotes a tested agent version; the
cost model and CI workflow support delivery but are not runtime dependencies.

> [!IMPORTANT]
> This sample creates billable Azure resources. Review the saved Terraform
> plan, regional model pricing, and quota before applying it.

## What you get

- **Repeatable infrastructure:** an Azure Verified Module (AVM) deployment of
  a Foundry account, project, model, Agent Service dependencies, and
  diagnostics.
- **Safer agent delivery:** a Python deployer that packages an immutable
  version, waits for activation, runs a smoke test, and rolls back on failure.
- **Business workflow samples:** deployable case-review and application-review
  agents with synthetic requests and explicit human decision boundaries.
- **Explicit cost assumptions:** a calculator that keeps region-specific rates
  outside the code, ranks Azure GPU VM scenarios, and reports each
  hosted-runtime break-even point.
- **Automated validation:** GitHub Actions checks Python sources, dependencies,
  calculator behavior, Terraform formatting, and Terraform configuration.

## Repository layout

| Path | Purpose |
| --- | --- |
| [`terraform/`](terraform/) | Deploy a Foundry project, model, Agent Service dependencies, and observability with the official AVM pattern. |
| [`hosted-agents/`](hosted-agents/) | Deploy the basic Responses agent plus case-review and application-review business samples. |
| [`cost-comparison/`](cost-comparison/) | Compare self-hosted models on Azure GPU VMs with Foundry hosted-agent costs using replaceable rates. |

## Quick start

### 1. Deploy the baseline

```powershell
az login
Set-Content terraform/terraform.tfvars 'subscription_id = "<subscription-id>"'
# Review the defaults in terraform/variables.tf, including region, model, quota, and pricing.
terraform -chdir=terraform init
terraform -chdir=terraform plan -out main.tfplan
terraform -chdir=terraform apply main.tfplan
```

### 2. Publish a sample agent

Choose the basic, case-review, or application-review sample in the
[hosted-agent guide](hosted-agents/README.md), then load the Terraform outputs,
test locally, and publish an immutable hosted version.

### 3. Compare hosting costs

Update the illustrative rates in `cost-comparison/scenario.example.json`, then
run:

```powershell
python cost-comparison/calculator.py cost-comparison/scenario.example.json
```

## Production considerations

The included infrastructure disables public data-plane access and deploys
private endpoints, private DNS, and a delegated hosted-agent subnet. Before
production use:

- Use the AVM pattern's BYOR path so platform-owned Key Vault, Storage,
  Cosmos DB, and AI Search resources have independent lifecycles.
- Integrate the workload VNet and private DNS zones with the landing-zone hub,
  firewall, DNS resolver, and on-premises routing design.
- Send diagnostics to a centrally managed Log Analytics workspace.
- Assign least-privilege data-plane roles to each hosted agent's dedicated
  Microsoft Entra identity.
- Pin model versions and test Responsible AI policies before promotion.
- Store Terraform state in an Azure Storage backend with Entra ID
  authentication, locking, versioning, and restricted network access.

## Validation

Pull requests and pushes to `main` run Python compilation and tests, validate
the deployment CLI, check Terraform formatting, and run `terraform validate`.
These checks do not create Azure resources. A real plan and hosted-agent smoke
test still require an authenticated Azure subscription, regional model quota,
and the documented RBAC roles.

## References

- [Azure AI Foundry AVM pattern](https://registry.terraform.io/modules/Azure/avm-ptn-aiml-ai-foundry/azurerm/latest)
- [Create Microsoft Foundry with Terraform](https://learn.microsoft.com/azure/foundry/how-to/create-resource-terraform)
- [Foundry hosted agents](https://learn.microsoft.com/azure/foundry/agents/concepts/hosted-agents)
- [Foundry Agent Service pricing](https://azure.microsoft.com/pricing/details/foundry-agent-service/)

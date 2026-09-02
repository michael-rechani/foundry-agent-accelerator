# Azure AI Foundry samples

This repository provides a deployable Azure AI Foundry baseline, a starting
point for Foundry hosted agents, and a transparent cost comparison with
self-managed agents on Azure virtual machines.

## Repository layout

| Path | Purpose |
| --- | --- |
| [`terraform/`](terraform/) | Deploys Foundry, a project, Agent Service dependencies, and a model by using the official Azure Verified Module (AVM) pattern. |
| [`hosted-agents/`](hosted-agents/) | Contains a runnable Python Responses-protocol agent, a Python SDK deployer, and a backlog of candidate scenarios. |
| [`cost-comparison/`](cost-comparison/) | Calculates monthly IaaS VM and Foundry hosted-agent costs from explicit, replaceable rates. |

## Quick start

1. Authenticate with Azure CLI: `az login`.
2. Copy `terraform/terraform.tfvars.example` to `terraform/terraform.tfvars`.
3. Set `subscription_id` to the output of
  `az account show --query id --output tsv`, then review the subscription,
  region, model availability, and quota.
4. Initialize, review, and apply a saved plan:
  `terraform -chdir=terraform init`,
  `terraform -chdir=terraform plan -out main.tfplan`, and
  `terraform -chdir=terraform apply main.tfplan`.
5. Follow [`hosted-agents/README.md`](hosted-agents/README.md) to configure,
  smoke-test, and deploy the
   sample agent.
6. Update the rates in `cost-comparison/scenario.example.json`, then run
   `python cost-comparison/calculator.py cost-comparison/scenario.example.json`.

## Production considerations

The included infrastructure is a public-network starter intended for
experimentation. Before production use:

- Use the AVM pattern's BYOR path so platform-owned Key Vault, Storage,
  Cosmos DB, and AI Search resources have independent lifecycles.
- Enable private endpoints, private DNS, and network injection in accordance
  with the landing-zone network design.
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

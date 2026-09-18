# Validate your AI use case in Foundry

**Sample agents for reviewing case notes, applications, and proposals.**

[![Validate](https://github.com/michael-rechani/ai-foundry-samples/actions/workflows/validate.yml/badge.svg)](https://github.com/michael-rechani/ai-foundry-samples/actions/workflows/validate.yml)
[![Terraform 1.16.1](https://img.shields.io/badge/Terraform-1.16.1-844FBA?logo=terraform&logoColor=white)](terraform/README.md)
[![Python 3.13](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)](hosted-agents/README.md)
[![Microsoft Foundry](https://img.shields.io/badge/Microsoft_Foundry-hosted_agents-0078D4?logo=microsoftazure&logoColor=white)](https://learn.microsoft.com/azure/foundry/agents/concepts/hosted-agents)

Try AI-assisted document review on **Microsoft Foundry on Azure (formerly Azure
AI Foundry)**. This repository includes sample agents, a chat application called
the Lab, and deployment guides. Use the fictional case notes and application
materials to see how an agent summarizes information, finds missing details,
and flags conflicting evidence.

Each demo includes sample inputs and expected findings so you can check the
agent's response. People verify the findings and make any approval or denial
decisions.

## Start here

- **Have a prepared environment?** [Try a demo](#choose-a-demo).
- **Need to set one up?** [Prepare the environment](#quick-start). Setup creates
  billable Azure resources and requires private network access.

Without Azure access, you can still read the
[sample inputs and expected findings](docs/demos.md).

> [!WARNING]
> **Use fictional data only.** The Lab has shared history and no per-user
> authorization. Everyone with workspace access can read shared records.
> Private networking and managed identities do not keep users' records separate.

## Scenarios and status

Choose one demo to start.

| Scenario | What you'll try | Status |
| --- | --- | --- |
| [Casework assistance](docs/demos.md#casework-assistance) | Summarize fictional case notes, flag missing or conflicting details, and draft follow-up questions. | **Available** |
| [Application completeness](docs/demos.md#application-completeness) | Check a sample grant or permit application against a supplied checklist. Missing information is a reason to ask questions, not automatically reject it. | **Available** |
| [Requirements and proposal review](docs/demos.md#requirements-and-proposal-review) | Compare proposal requirements with supplied product information and flag claims that lack supporting evidence. | **Experimental** |

**Available** samples include agent code and a walkthrough. They still need
deployment and live quality checks. **Experimental** samples adapt an existing
agent to a different task and need additional testing for that task. The
[demo guide](docs/demos.md) explains which agents each demo uses.

**Planned, not available:** [agent-assisted request triage](docs/demos.md#agent-assisted-request-triage)
would classify service requests and suggest where to send them, with a person
approving simulated actions. That workflow is not implemented; the current
coordinator only sends review work to specialist agents.

## Choose a demo

Plan for a **10-15 minute walkthrough once setup is complete**. Actual response
times vary.

1. Open the [Lab](workbench/README.md) through approved private access and start
   a new chat. Choose a starter prompt or use the full
   [demo inputs and instructions](docs/demos.md).
2. Compare the response with the source material and expected findings. Try the
   supplied examples with missing information, conflicting details, and
   instructions the agent should refuse.
3. Check the cited sources and, when available, the verified records showing
   which review tools ran. Record failures as well as successful results.
4. Use the [demo handoff](docs/demo-handoff.md) to note what worked, what needs
   more testing, and the next step. Start fresh without deleting someone else's
   records.

For a disconnected walkthrough, use the sample inputs and expected findings in
the [demo guide](docs/demos.md) as examples, not live results. The local Lab
preview does not call a model.

<a id="quick-start"></a>

## Prepare the environment

Setup is separate from the short demo. You deploy the Azure resources, publish
the agents, and deploy the Lab in separate steps.

Before you begin, you need:

- Terraform 1.16.1 and Azure CLI signed in to the intended tenant.
- Permission to deploy resources and assign roles, enough regional model quota,
  and approved private network access.
- An existing, secured Azure Storage account and blob container for Terraform
  state. Your identity needs **Storage Blob Data Contributor** on that container.
  This sample does not create its own state backend.

See the [Terraform prerequisites and state guide](terraform/README.md) for details.

> [!IMPORTANT]
> **This is not a minimal-cost setup.** Azure resources, model calls, and running
> agents can incur charges. Get approval and review the saved Terraform plan,
> regional pricing, and quota before deploying. Preserve existing resource names,
> state, permissions, and private access. Never apply an unexpected replacement
> or deletion.

Follow these guides in order:

1. [Configure, validate, plan, and deploy the Azure resources](terraform/README.md#deploy).
   Follow the [state and migration safeguards](terraform/README.md#state).
2. [Publish and test the selected agents](hosted-agents/README.md). Use the
   [private deployment runbook](docs/private-deployment.md) if you need a separate
   deployment machine.
3. [Deploy or access the Lab](workbench/README.md). It uses separate Terraform
   state and has its own application deployment steps.
4. Test the chosen scenario and complete its approved
   [live evaluation](evaluations/README.md) before presenting it. A successful
   deployment does not prove that the agent's answers are good.

A new agent version can receive traffic before its smoke tests finish. If a
check fails, the deployer attempts to restore the previous route and keeps any
version it cannot safely delete. See the
[deployment and recovery steps](hosted-agents/README.md#6-verify-the-route-and-handle-failures).

## Validate and compare

Use the [Foundry evaluation guide](evaluations/README.md) to test answers against
the supplied fictional cases and expected outcomes. Automated checks with
simulated responses do not establish live model quality.

Live evaluations are optional, cost money, and require explicit approval and
access to a private test environment. Review evaluation results and traces in
Foundry; the Lab is not an evaluation dashboard.

To compare models or prompts, use the **same test cases** and record each version
and its results. Judge answer quality separately from response time. Record
token usage when it is available, and distinguish measured usage from estimated
token costs and infrastructure costs.

For a separate infrastructure cost comparison, use the
[GPU VM versus hosted-runtime calculator](cost-comparison/README.md).

## Architecture

The [Lab](workbench/README.md) is a private React chat application with a FastAPI
backend. It calls hosted agents in Foundry and lets you choose which conversations
and reviews to save in a shared Cosmos DB database.

The Lab runs in its own internal Azure Container Apps environment and uses
managed identities to access Azure services. It is not an agent designer and
does not require Azure API Management (APIM).

![Deployed AI Foundry Lab: private browser access, managed-identity review agents, and shared Cosmos history](docs/images/foundry-overview.svg)

[Full-size overview](docs/images/foundry-overview.svg) · [Operations and security](docs/images/foundry-operations.svg)

Deeper guides:

- **Components and data flow:** [architecture](docs/architecture.md#component-interactions),
  [review storage and recovery](docs/review-workflow.md#execution-and-persistence).
- **Access and credentials:** [authentication and service boundaries](docs/architecture.md#trust-boundaries),
  [credential handling](docs/credentials.md).
- **Customize the agents:** [extension guide](docs/architecture-assessment.md),
  [coordinator profiles](docs/agent-profiles.md).
- **Optional APIs and search:** [APIM API guide](docs/apim-review-api.md),
  [integration options](docs/optional-integrations.md). APIM is disabled by default.
  Azure AI Search is provisioned as a Foundry dependency but is not used by the
  current review agents.
- **Optional browser access:** [Application Gateway and Front Door guide](docs/ingress-access.md).
  These are design options that keep the app origin and Foundry private, not
  gateways deployed by this sample.

<a id="reusable-technical-foundations"></a>
<a id="repository-layout"></a>

## What's included

| Path | Purpose |
| --- | --- |
| [workbench/](workbench/) | The Lab: chat UI, FastAPI backend, shared history and reviews, browser tests, and its own deployment setup. |
| [terraform/](terraform/) | Azure infrastructure using the official Azure Verified Module (AVM) pattern for Foundry. |
| [hosted-agents/](hosted-agents/) | Sample agents and Python scripts to publish versions, update routing, and test deployments. |
| [hosted-agents/review-coordinator-agent/](hosted-agents/review-coordinator-agent/) | An agent that sends review tasks to the case-review and application-review specialists. Profiles let you change its instructions and specialists without changing runtime code. |
| [docs/](docs/) | Demo instructions, fictional inputs, architecture, deployment, and operations guides. |
| [evaluations/](evaluations/) | Review test cases, offline checks, and optional live answer-quality evaluations. |
| [cost-comparison/](cost-comparison/) | A calculator for comparing Azure GPU VM and Foundry hosted-runtime costs, with rates you can update. |

<a id="engagement-scope"></a>
<a id="beyond-the-demonstration-separately-scoped-production-considerations"></a>
<a id="production-considerations"></a>

## Scope and limitations

These samples are for demonstrations and technical testing, not finished customer
applications. Connecting to customer systems or deploying to production requires
separate planning and agreement.

- Review agents analyze the supplied text; they do not update business systems.
  Any future demo of business actions must use simulated tools.
- The demo path does not include customer-system connections,
  Microsoft 365/Copilot/SharePoint integrations, or education knowledge assistants.
- A matching citation shows that text came from a supplied source, not that the
  source's claims are true.
- Do not put customer names, opportunity records, commercial details, or claims
  of customer implementations into sample inputs, traces, or handoff examples.
- This repository is not an officially approved or funded Microsoft service
  offering. Sample code, setup help, and architecture or cost advice are not a
  commitment to deliver a customer integration.

Use the [production checklist](terraform/README.md#separately-scoped-production-considerations)
to plan further work, including user authorization and keeping users' records
separate. Capture agreed next steps in the [demo handoff](docs/demo-handoff.md).

<a id="validation"></a>

## Automated checks

On pull requests and pushes to `main`, GitHub Actions compiles and tests the
Python code, checks dependencies and all four agent deployment CLIs, tests SDK
integrations, and checks Terraform formatting and configuration. It also tests
deployment safeguards, saved-history and review behavior, and browser workflows
at desktop and mobile sizes.

These checks use test data and simulated service responses, not live agents.
They do not create Azure resources. Testing a live deployment still requires an
authenticated Azure subscription, model quota, the documented access roles, and
private network access.

## References

- [Azure AI Foundry AVM pattern](https://registry.terraform.io/modules/Azure/avm-ptn-aiml-ai-foundry/azurerm/latest)
- [Create Microsoft Foundry with Terraform](https://learn.microsoft.com/azure/foundry/how-to/create-resource-terraform)
- [Foundry hosted agents](https://learn.microsoft.com/azure/foundry/agents/concepts/hosted-agents)
- [Foundry Agent Service pricing](https://azure.microsoft.com/pricing/details/foundry-agent-service/)

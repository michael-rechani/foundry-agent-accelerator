<a id="validate-your-ai-use-case-in-foundry"></a>

# Hosted-agent samples for Microsoft Foundry

[![Validate](https://github.com/michael-rechani/ai-foundry-samples/actions/workflows/validate.yml/badge.svg)](https://github.com/michael-rechani/ai-foundry-samples/actions/workflows/validate.yml)
[![Terraform 1.16.1](https://img.shields.io/badge/Terraform-1.16.1-844FBA?logo=terraform&logoColor=white)](terraform/README.md)
[![Python 3.13](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)](hosted-agents/README.md)
[![Microsoft Foundry](https://img.shields.io/badge/Microsoft_Foundry-hosted_agents-0078D4?logo=microsoftazure&logoColor=white)](https://learn.microsoft.com/azure/foundry/agents/concepts/hosted-agents)

Describe a job, choose a prepared template, create a baseline agent in
**Microsoft Foundry on Azure (formerly Azure AI Foundry)**, then try it in a
browser app called the Lab. The five generic jobs suit public-sector,
healthcare-operations and ISV demonstrations, without customer data or connected
business systems.

**Create agent** prepares an editable setup from a reviewed template and your
task description; this step does not call a model or create a cloud resource.
In an operator-enabled private Lab, an explicit creation confirmation publishes
a real named Foundry hosted agent. **Created agents** shows its progress and
opens it in Chat when its runtime and route are ready. Publication is opt-in,
costs money, and needs the [operator setup](docs/agent-creation.md).
Local preview can prepare setups, but cannot publish or produce live answers.

The repository includes fictional inputs, expected findings, and Azure deployment
guides. Agents help people review the supplied material; people verify the
findings and make any approval or denial decisions.

## Start here

| What you want to do | Where to start | What you need |
| --- | --- | --- |
| Read through an example | [Demo guide](docs/demos.md) | No Azure access required. |
| Create and try a baseline agent | [Template creation guide](docs/agent-creation.md) | An operator-enabled private Lab, existing model deployment and approval for the cost. |
| Try the agents | [Run a demo](#run-a-demo) | A prepared Lab and approved private network access. |
| Deploy your own Lab | [Set up Azure](#set-up-azure) | Azure permissions, model quota, private access, and approval for the cost. |

> [!WARNING]
> **Use fictional data only.** The Lab has shared history and no per-user
> authorization. Everyone with workspace access can read shared records.
> Private networking and managed identities do not keep users' records separate.

<a id="scenarios-and-status"></a>

## What you can try

Choose one job template to start:

| Template | Give it | Get back |
| --- | --- | --- |
| Document Analyst | Supplied policy, notice or product text | A sourced summary, changes and open questions |
| Criteria Checker | Your checklist and a document | Supported items, missing information and conflicts; no approval decision |
| Document Intake Assistant | Fictional administrative intake text and fields to extract | A field table with source references and unknown values called out |
| Casework Assistant | Fictional case notes | A summary, unresolved inconsistencies and follow-up questions |
| Workflow Coordinator | The supplied fictional request and service identifiers | Read-only **simulated** lookup results and proposed next steps; no executed business actions |

The first four use supplied text without tools or specialist delegation. The
workflow template has exactly two fixed local lookup tools, not live connectors
or an approval engine. Healthcare examples concern administration, not clinical
advice or patient data. See [the creation walkthrough](docs/demos.md#create-and-try-a-baseline-agent).

The existing developer-published agents also support these longer walkthroughs:

| Scenario | What you'll try | Status |
| --- | --- | --- |
| [Casework assistance](docs/demos.md#casework-assistance) | Summarize fictional case notes, flag missing or conflicting details, and draft follow-up questions. | **Available** |
| [Application completeness](docs/demos.md#application-completeness) | Check a sample grant or permit application against a supplied checklist and identify missing or conflicting information. | **Available** |
| [Requirements and proposal review](docs/demos.md#requirements-and-proposal-review) | Compare proposal requirements with supplied product information and flag claims that lack supporting evidence. | **Experimental** |

**Available** means the agent code and walkthrough are included, not that an
environment is already deployed or its answers have been validated.
**Experimental** means an existing agent is adapted for another task and needs
additional testing. The [demo guide](docs/demos.md) explains the expected results
and which agents each sample uses.

## Choose how to work

**Creating an agent and talking to one are separate steps.** An agent has saved
instructions and a fixed set of available tools. An example task or chat starter
only fills your message; Chat does not reconfigure the runtime.

| Choose | Give it | Get back |
| --- | --- | --- |
| **Create agent** | A job description, a prepared template and reviewed task instructions | An editable setup; with operator confirmation, a separately published Foundry agent |
| **Chat** | A question plus the application, checklist or case notes you want help with | A conversational answer from the selected agent, with references and follow-up questions |
| **Document reviews** | A checklist and pasted document text | Saved results for each checklist item, quotes you can inspect, and requests for missing information |

The default **Application and case helper** asks an application-checking or
case-notes specialist to handle the task. **About this agent** explains what it
needs, how it works and what it cannot do. Document reviews use the Lab's default
agent independently of the Chat selection. Neither view copies work into the
other automatically.

Use **Created agents** for publication status and operator-confirmed deletion.
Existing catalog agents, hidden-agent access and specialist bindings stay
unchanged. Editing tools, code, model selection, permissions or an existing
deployed setup remains a developer/operator task, not a chat command. See
[configuration ownership](workbench/README.md#workspace-configuration).

<a id="choose-a-demo"></a>

## Run a demo

Use a prepared Lab for this path. If you do not have one, follow
[Set up Azure](#set-up-azure) first or read the examples without running them.
The local Lab preview does not call a model.

1. Open the [Lab](workbench/README.md) through approved private access and start
   a new chat.
2. Inspect **About this agent**, then choose an example task and send it, or paste the complete
   [sample input](docs/demos.md) for your chosen scenario.
3. Compare the answer with the source material and expected findings. Check
   citations and any verified records showing which review tools ran. Try the
   supplied missing-information, conflicting-evidence, and failure examples.
4. Record successes, failures, and next steps in the
   [demo handoff](docs/demo-handoff.md). Start fresh without deleting someone
   else's records.

<a id="validate-and-compare"></a>

## Check answer quality

For repeatable testing, use the [Foundry evaluation suite](evaluations/README.md).
Compare models or prompts with the **same test cases**, and record each version
and its results. A successful deployment or a fast response does not prove that
an answer is correct.

Live evaluations are optional, billable, and require explicit approval and
private test access. Review their results and traces in Foundry, not the Lab.
Offline tests use simulated responses; they do not measure live model quality.

Record token usage only when it is available. Keep measured usage, estimated
token costs, and infrastructure costs separate.

<a id="quick-start"></a>
<a id="prepare-the-environment"></a>

## Set up Azure

This path is for the person deploying the environment. Infrastructure, agents,
and the Lab have separate deployment steps.

Before you begin, you need:

- Terraform 1.16.1 and Azure CLI signed in to the intended tenant.
- Permission to deploy resources and assign roles, enough regional model quota,
  and approved private network access.
- An existing, secured Azure Storage account and blob container for Terraform
  state. Your identity needs **Storage Blob Data Contributor** on that container.
  This sample does not create its own state backend.

See the [Terraform prerequisites and state guide](terraform/README.md) for details.

> [!IMPORTANT]
> **This is not a low-cost starter deployment.** Azure resources, model calls,
> and running agents can incur charges. Get approval and review the saved
> Terraform plan, regional pricing, and quota before deploying. Preserve existing
> resource names, state, permissions, and private access. Never apply an
> unexpected replacement or deletion.

Follow these guides in order:

1. [Configure, validate, plan, and deploy the Azure resources](terraform/README.md#deploy).
   Follow the [state and migration safeguards](terraform/README.md#state).
2. [Publish and test the selected agents](hosted-agents/README.md). Use the
   [private deployment runbook](docs/private-deployment.md) if you need a separate
   deployment machine.
3. [Deploy or access the Lab](workbench/README.md). It uses separate Terraform
   state and has its own application deployment steps.
4. Verify private access, agent calls, and the chosen scenario in your approved
   test environment before presenting it. Use the
   [quality checks](#check-answer-quality) for a more formal comparison; live
   evaluation requires separate approval.

A new agent version can receive traffic before its smoke tests finish. If a
check fails, the deployer attempts to restore the previous route and keeps any
version it cannot safely delete. See the
[deployment and recovery steps](hosted-agents/README.md#6-verify-the-route-and-handle-failures).

<a id="architecture"></a>

## How it works

The Lab's React interface sends requests to a FastAPI backend, which calls the
hosted agents in Foundry. Chat saves completed messages to shared Cosmos DB only
when you choose Save. Creating a document review saves its checklist and
document text; running it also saves results and a copy of that run's input.

The Lab runs in an internal Azure Container Apps environment and uses managed
identities to access Azure services. It is a chat app, not an agent designer or
evaluation dashboard.

The coordinator owns the conversation. It calls a specialist through a configured
tool, then returns the findings to the Lab. Specialists do not message each other,
and a completed tool call is not proof that its findings are correct.

![Default agent collaboration: the coordinator selects a review specialist, receives its result, and returns findings to the Lab for human review](docs/images/agent-collaboration.svg)

Choose the view that answers your question:

| View | What it explains |
| --- | --- |
| [Agent collaboration](docs/images/agent-collaboration.svg) | How the coordinator delegates work and returns findings for human review. |
| [Infrastructure](docs/images/foundry-overview.svg) | How the Lab reaches agents and stores records through separate paths. |
| [Operations and security](docs/images/foundry-operations.svg) | How telemetry, image publishing, state, and credentials are handled. |
| [Terraform deployment](docs/images/foundry-deployment.svg) | What the platform and Lab stacks own, and what stays in release workflows. |

For the actual message shape, see the [request and result example](docs/agent-profiles.md#example-handoff).

Deeper guides:

- **Components and data flow:** [architecture](docs/architecture.md#component-interactions),
  [review storage and recovery](docs/review-workflow.md#execution-and-persistence).
- **Access and credentials:** [authentication and service boundaries](docs/architecture.md#trust-boundaries),
  [credential handling](docs/credentials.md).
- **Customize the agents:** [extension guide](docs/architecture-assessment.md),
  [coordinator profiles](docs/agent-profiles.md).
- **Terraform and Microsoft reference architectures:** [what to reuse and who owns it](docs/architecture-assessment.md#terraform-first-deployment).
  Keep the existing AVM foundation; add infrastructure only for a specific need.
- **Optional APIs and search:** [API Management guide](docs/apim-review-api.md),
  [integration options](docs/optional-integrations.md). Azure API Management
  (APIM) is disabled by default and is not needed by the Lab. Azure AI Search is
  a Foundry dependency, but the current review agents do not use it.
- **Optional browser access:** [Application Gateway and Front Door guide](docs/ingress-access.md).
  These are design options that keep the app origin and Foundry private, not
  gateways deployed by this sample.

<a id="reusable-technical-foundations"></a>
<a id="repository-layout"></a>
<a id="whats-included"></a>

## Project files

| Path | Purpose |
| --- | --- |
| [workbench/](workbench/) | The Lab: chat UI, FastAPI backend, shared history and reviews, browser tests, and its own deployment setup. |
| [terraform/](terraform/) | Azure infrastructure using the official Azure Verified Module (AVM) pattern for Foundry. |
| [hosted-agents/](hosted-agents/) | Sample agents, including the review coordinator, and scripts to publish and test them. |
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
  source's claims are true. Missing evidence calls for more information, not an
  automatic rejection.
- Do not put customer names, opportunity records, commercial details, or claims
  of customer implementations into sample inputs, traces, or handoff examples.
- This repository is not an officially approved or funded Microsoft service
  offering. Sample code, setup help, and architecture or cost advice are not a
  commitment to deliver a customer integration.

**Not implemented:** [agent-assisted request triage](docs/demos.md#agent-assisted-request-triage)
is planned work, not an available demo. Sending review tasks to specialist agents
is not a service-request routing or approval workflow.

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

These checks do not call live agents or create Azure resources. They test the
code and its handling of simulated service responses, not the quality of a live
model's answers.

## References

- [Azure AI Foundry AVM pattern](https://registry.terraform.io/modules/Azure/avm-ptn-aiml-ai-foundry/azurerm/latest)
- [Create Microsoft Foundry with Terraform](https://learn.microsoft.com/azure/foundry/how-to/create-resource-terraform)
- [Foundry hosted agents](https://learn.microsoft.com/azure/foundry/agents/concepts/hosted-agents)
- [Foundry Agent Service pricing](https://azure.microsoft.com/pricing/details/foundry-agent-service/)

<a id="validate-your-ai-use-case-in-foundry"></a>
<a id="foundry-agent-lab"></a>

# Foundry Agent Accelerator

[![Validate](https://github.com/michael-rechani/foundry-agent-accelerator/actions/workflows/validate.yml/badge.svg)](https://github.com/michael-rechani/foundry-agent-accelerator/actions/workflows/validate.yml)
[![Terraform 1.16.4](https://img.shields.io/badge/Terraform-1.16.4-844FBA?logo=terraform&logoColor=white)](terraform/README.md)
[![Python 3.14](https://img.shields.io/badge/Python-3.14-3776AB?logo=python&logoColor=white)](hosted-agents/README.md)
[![Microsoft Foundry](https://img.shields.io/badge/Microsoft_Foundry-hosted_agents-0078D4?logo=microsoftazure&logoColor=white)](https://learn.microsoft.com/azure/foundry/agents/concepts/hosted-agents)

Build, deploy, and explore agents on **Microsoft Foundry** (formerly Azure AI
Foundry). The Lab is a customer demo and workshop experience backed by reusable
code. You can browse a library of sample agents, read how each one did on its
test cases, try one with sample data, and take it to your own Microsoft
Foundry. You can also publish agents from the same templates and watch
prebuilt agents work as a team.

Start with a practical question. Find what's missing from an application,
check what doesn't add up on an invoice, or clarify a caseworker's next step.
Then compare the agent's actual answer with the sample source.

The Azure deployment runs privately in your subscription. Local preview makes
no model calls. This is a sample, not an official Microsoft product.

**On this page**

[Take a tour](#take-a-tour) · [Get started](#get-started) ·
[Explore three stories](#explore-three-stories) ·
[What you can show](#what-you-can-show) · [How it works](#how-it-works) ·
[Deploy to Azure](#deploy-to-azure) ·
[Scope and limitations](#scope-and-limitations) ·
[What's included](#whats-included) · [Documentation](#documentation) ·
[Automated checks](#automated-checks) · [Related content](#related-content)

---

## Take a tour

<img alt="Tour of the Foundry Agent Lab in five steps: browse the agent library, read an agent's test results, chat with it, see how to take it to Microsoft Foundry, and create an agent from a template. Every screen shows sample data." src="docs/images/lab-tour-dark.svg">

**Browse agents → Test results → Chat → Take it to Foundry → Create agent**

1. **Browse agents:** the agent library lists every sample agent, and **Start
   here** offers three ready-made examples.
2. **Test results:** see how an agent did on its recorded test cases. You get
   how many answers passed, how long it took, what it cost, and whether a
   person has signed it off yet.
3. **Chat:** talk with an agent. An example only fills the message box, and you
   choose when to send it.
4. **Take it to Foundry:** download the agent definition and its test requests,
   then follow the steps to create it in your own Microsoft Foundry. There's
   no one-click move between environments.
5. **Create agent:** prepare an agent from one of the library's templates. It
   stays off until an operator turns it on.

*The screenshots come from automated
browser tests with sample data. They aren't a live model run.*

[Open the full tour](docs/images/lab-tour-dark.svg) ·
[Create agent screenshot](docs/images/screenshots/lab-create-agent-dark.png) ·
[Browse all screenshots](docs/images/README.md#lab-screenshots)

<a id="start-here"></a>
<a id="scenarios-and-status"></a>
<a id="what-you-can-try"></a>
<a id="choose-a-demo"></a>
<a id="run-a-demo"></a>
<a id="validate-and-compare"></a>
<a id="check-answer-quality"></a>

## Get started

Pick the path that matches what you want to do:

- **Explore without deploying.** Read the [showcase and presenter guide](docs/showcase.md)
  for sample inputs, expected findings, and the questions a person still has to
  settle. You don't need an Azure environment to read the walkthroughs.

- **Browse the agent library.** In a deployed Lab, look through the sample
  agents, see what each one leaves to a person, and check how it did on its
  recorded test cases. Browsing, reading test results, and downloading an agent
  definition make no model calls. Trying an agent does. See the
  [Lab guide](docs/lab-pages-and-access.md#pages).

- **Create your own agent.** Follow [Create and try a baseline agent](docs/agent-creation.md).
  You need an operator-enabled Lab, one or more model deployments, and cost approval.

- **Demo the prebuilt agents.** Follow the [demo guide](docs/demos.md) in a deployed
  Lab. Reading the walkthroughs and expected findings needs nothing.

- **Check answer quality.** Start with [evaluations](evaluations/README.md).
  Offline checks need no Azure environment. Live runs need a test environment
  and approval.

- **Deploy your environment.** Follow [Deploy to Azure](#deploy-to-azure).
  You need Azure permissions, model quota, approved private network access,
  and cost approval.

If you're after early public-sector and healthcare ideas, see the
[agent drafts](docs/agent-drafts/README.md). They're documentation-only
definitions and shared safeguards, not implemented, registered, or deployed
agents.

---

## Explore three stories

Choose a story in **Guided demos**. Each one pairs sample evidence with
findings to look for and a decision that stays with a person.

<a id="find-the-missing-evidence"></a>
<a id="find-whats-missing"></a>
<a id="catch-what-does-not-add-up"></a>
<a id="turn-scattered-notes-into-a-brief"></a>

| Story | What to spot | People decide |
| --- | --- | --- |
| [Find what’s missing](docs/showcase.md#find-whats-missing) | A missing budget, a named owner, and conflicting schedules. | Verify the documents and determine the application outcome. |
| [Catch what does not add up](docs/showcase.md#catch-what-does-not-add-up) | Billed quantities and prices that differ from the purchase order. | Resolve damaged items and determine what to pay. |
| [Turn scattered notes into a brief](docs/showcase.md#turn-scattered-notes-into-a-brief) | Supported facts, conflicting dates, and missing evidence. | Verify the authoritative record and determine the next steps. |

The invoice story runs on a ready **Supplier invoice reviewer** created from its
template. If the Lab has library previews on, it can run on the library preview
of that template instead. Either way it uses built-in lookups with sample data,
and there's no finance integration.

[Watch all three stories](docs/images/scenario-tour-dark.svg)

## What you can show

### Build and run

- **[Hosted agents](docs/agent-creation.md):** choose a built-in template in
  **Create agent** and publish it as a new agent.
- **[Model choice](docs/agent-creation.md#how-the-lab-picks-a-model):** use a
  template's selected model for reasoning, fast extraction, or tool calling.
- **[Agents working together](hosted-agents/README.md):** ask the **Checklist
  and case helper** in Chat to hand a task to a specialist.
- **[Tool calling](docs/agent-creation.md#what-a-participant-can-do):** try
  read-only lookups with sample data in the **Service request planner** or the
  healthcare and public-sector templates.

### Review and improve

- **[Grounded answers](docs/review-workflow.md):** in **Document reviews**
  (open `/#reviews`), every result quotes your text; quotes that don't match
  are rejected.
- **[Tracing](terraform/monitoring/README.md):** compare response times by agent
  in **Performance**, copy a request reference from **Request log**, and view
  optional agent traces in the Foundry portal.
- **[Evaluation](evaluations/README.md):** compare models or prompts against
  the same cases, including optional live Foundry evaluations.

### Deploy privately

**[Private, keyless deployment](terraform/README.md):** use Terraform to deploy
onto private networks. Services sign in with managed identities instead of API
keys.

**Create agent** is off until an operator turns it on, because publishing
creates Azure resources that cost money.

The Lab opens on the **Agent library**, and **Chat** is one click away. The
sidebar has **Agent library** (**All agents**, plus **Create agent** when
creation is on) and **Try it** (Chat and Shared history). **Operations** (a
health overview, response times, tokens, cost, and the request log) appears when
you turn on **Under the hood**.

**All agents** has tabs for **Browse**, **Ready to chat**, **Made in this Lab**,
**Guided demos**, and **Add-ons**. **Document reviews** has no sidebar link, so
open `/#reviews` or a saved-review link. See the
[Lab guide](docs/lab-pages-and-access.md#pages).

---

<a id="architecture"></a>

## How it works

Each diagram answers one question and follows your GitHub theme. Its numbered
steps match the list below it.

### One foundation, two connected workflows

Terraform sets up the private foundation once. After that, you release, verify,
and revise agents on their own schedule. A configuration handoff connects the
two workflows.

<img alt="Agent release journey in six numbered steps. Private foundation, built with Terraform and Azure Verified Modules: review the plan, provision separate roots, and verify private access. A configuration handoff carries the project endpoint, model deployments, identity, and private connectivity to agent releases: package the agent, publish and verify a new hosted version, then route, review, and iterate. People approve infrastructure changes, publication costs, and business decisions." src="docs/images/agent-release-journey-dark.svg">

1. **Review the plan.** Confirm permissions, quota, cost approval, and
   protected remote state.
2. **Provision separate roots.** Deploy the Foundry platform and the Lab, with
   optional Bastion and monitoring.
3. **Verify private access.** Check network paths and identities in the
   intended environment.
4. **Package the agent.** Bundle its source and configuration manifest, with
   named model deployment mappings.
5. **Publish and verify.** Create a new hosted version and check the
   documented release gates.
6. **Route, review, and iterate.** Check answers against evidence, and use
   guarded recovery if a release misbehaves.

*This is a logical workflow. A code push doesn't deploy either workflow, and a
bundle carries configuration, not Azure permissions.*

[View full size](docs/images/agent-release-journey-dark.svg) ·
[Edit the SVG template](docs/images/agent-release-journey.template.svg) ·
[Read the release journey](docs/showcase.md#one-foundation-repeatable-agent-releases) ·
[Portable bundles](hosted-agents/README.md#portable-agent-bundles)

### What runs in Azure

The core platform runs in one subscription on private networks. Services sign in
with managed identities, not API keys. Three optional pieces add something
public: the Bastion host's static public IP, the jump box's outbound IP, and the
Azure API Management gateway. Each is off unless you turn it on, and each also
needs its own `approve_*` Terraform input. Read the
[Terraform guide](terraform/README.md) before you do.

<img alt="Azure architecture at a glance: one subscription and resource group hold an admin network, a private workload network, Microsoft Foundry, data services, and shared services. The admin network has subnets for optional Azure Bastion and an optional jumpbox and is peered with the workload network. The workload network has subnets for the Lab in an internal Azure Container Apps environment, the agent network delegated to Foundry, and one private endpoint for each service. Seven numbered steps follow a request from the presenter through Bastion, the jumpbox, and the Lab to Foundry Agent Service and Foundry Models, then through the agent network to Azure Cosmos DB, Azure Storage, and Azure AI Search" src="docs/images/azure-architecture-dark.svg">

1. A presenter opens Azure Bastion from the Azure portal.
2. Bastion opens a remote desktop session to the private jumpbox.
3. The jumpbox browser opens the Lab across the network peering. The Lab
   accepts traffic only from the jumpbox subnet.
4. The Lab calls Foundry Agent Service through the Foundry private endpoint,
   signing in with its managed identity.
5. The agents run on a Foundry Models deployment, GPT-4.1 by default.
6. Foundry Agent Service connects the agents to the delegated agent subnet.
   From there, they keep conversations, files, and search data in Cosmos DB,
   Storage, and AI Search through their private endpoints.
7. The Lab saves its records in Cosmos DB through the same private endpoint.

*This is a logical view with Terraform default addresses, not a resource
inventory. Bastion and the jumpbox are optional, and API Management isn't
shown.*

[View full size](docs/images/azure-architecture-dark.svg) ·
[Edit the SVG template](docs/images/azure-architecture.template.svg) ·
[Architecture guide](docs/architecture.md) ·
[Agent names](docs/README.md#agent-names)

### Agents working together

The default **Checklist and case helper** coordinates the prebuilt
specialists. You still check the returned findings against the source.

<img alt="Default agent collaboration in four numbered steps: you ask in the Lab with supplied evidence; in Foundry Agent Service, the Checklist and case helper calls one specialist, the Checklist reviewer or the Case notes summarizer; the coordinator returns findings with a tool record; and a person checks the answer against the evidence" src="docs/images/agent-collaboration-dark.svg">

1. **You ask in the Lab.** Its backend calls the coordinator agent in Foundry by
   using a managed identity.
2. **The coordinator picks a specialist** and calls it through a tool.
   Specialists don't message each other.
3. **The coordinator returns the findings**, with a record of which specialist
   answered.
4. **You check the answer** against the source. A completed tool call doesn't
   prove the findings are correct.

*It calls one specialist by default, or both only if you ask. No approval,
denial, or external action happens automatically.*

[View full size](docs/images/agent-collaboration-dark.svg) ·
[Edit the SVG template](docs/images/agent-collaboration.template.svg) ·
[Hosted agents](hosted-agents/README.md) ·
[Which orchestration pattern is this?](docs/architecture.md#orchestration-pattern)

### Creating your own agent

When you publish from **Create agent**, the Lab packages its reviewed agent code
with your instructions and uploads it with the Foundry SDK.

Foundry Agent Service builds it and starts a new hosted agent named
`lab-demo-...` on the model that suits the template's work.

When Foundry reports the new version active and its route is confirmed, try
the agent in **Chat**. See [agent creation](docs/agent-creation.md).

### More diagrams

| Diagram | Question it answers |
| --- | --- |
| [How the Lab handles a request](docs/architecture.md#implementation-overview) | What does the Lab call, and what does it save? |
| [Orchestration pattern](docs/architecture.md#orchestration-pattern) | Which of Microsoft's agent orchestration patterns does the coordinator follow? |
| [Lab components](docs/architecture.md#component-interactions) | What runs in the browser, the Lab, Foundry, and the data store? |
| [Chat request flow](docs/architecture.md#chat-and-delegation) | What happens, in order, when you send a chat message? |
| [Review lifecycle](docs/review-workflow.md#execution-and-persistence) | How is a document review saved, checked, and recovered? |
| [Operations](docs/architecture.md#operations) | How are telemetry, images, and Terraform state handled? |
| [Terraform deployment](docs/architecture-assessment.md#terraform-first-deployment) | Which Terraform root owns what? |

All diagrams share one [style guide](docs/images/README.md#diagram-style).

---

<a id="quick-start"></a>
<a id="prepare-the-environment"></a>
<a id="set-up-azure"></a>

## Deploy to Azure

> [!IMPORTANT]
> **This isn't a low-cost starter.** Azure resources, model calls, and running
> agents cost money. Get approval, and review every Terraform plan before you
> apply it.

### Before you begin

- Terraform 1.16.4 and the Azure CLI.
- Permission to deploy resources and assign roles.
- Model quota and approved private network access.
- An existing Azure Storage container for Terraform state.

### Tool versions and upgrades

Check only the tools your task needs. Reading docs, preparing sample inputs,
and running mocked tests need no Azure sign-in or end-user Entra setup, and
local tests don't require `azd`.

| Tool | Repository baseline | When needed / source of truth |
| --- | --- | --- |
| Terraform | 1.16.4 or a later **1.16 patch**, not 1.17 | Infrastructure and mock-provider tests. Each root's `required_version` enforces `~> 1.16.4`; CI uses 1.16.4. Keep its committed `.terraform.lock.hcl`. |
| Python | 3.14 | Backend, hosted agents, and offline Python tests. Use that interpreter to create a virtual environment, then install the task's `requirements*.txt`. Evaluation dependencies use a separate environment. |
| Node.js | 24; CI and the image build use **24.21.0** | Lab frontend only. Run `npm ci` against [`package-lock.json`](workbench/frontend/package-lock.json), not an unpinned install. |
| PowerShell | 7 (`pwsh`); no patch pinned | Repository `.ps1` helpers and artwork generation. Windows PowerShell 5.1 is not the CI shell. |
| Azure CLI | No minimum version pinned by this repository | Azure authentication and the documented operator/build helpers only; not needed for offline unit/browser tests. Use an organization-approved current release. |
| Docker | No engine version pinned; Linux `amd64` builds | The local path in [`workbench/build.ps1`](workbench/build.ps1), not ordinary UI/Python tests. Base images are digest-pinned in the Dockerfile. |

Check the executables you picked with `terraform version`, `python --version`,
`node --version`, `$PSVersionTable.PSVersion`, and, when applicable, `az version`
and `docker version`. A full executable path avoids a stale Windows PATH or a
different Python on PATH. Terraform test helpers accept `-TerraformCommand`.
Don't lower pins to make an older local tool pass.

After pulling an update, recreate or update the affected Python environment and
rerun `npm ci` when the frontend lock changes. Ordinary Terraform initialization
uses the lock. Use `init -upgrade` only for an intentional, reviewed provider or
module update. Review SDK/API compatibility, lockfile and image-digest changes,
and the [automated release checks](#automated-checks) together. A package-mirror
404 or TLS failure is an installation problem, not a reason to rewrite the
lockfile. Use an approved source or exact-pin CI, and disclose any local version
differences. Passing offline checks isn't a deployment acceptance test. Any
private rollout or billable live check still needs separate approval.

Start with the [troubleshooting index](docs/troubleshooting.md#tools-and-dependencies)
for version, import, and dependency-install failures.

### Deployment order

1. **Platform:** deploy [`terraform/`](terraform/README.md#deploy).

2. **Prebuilt agents:** publish and test them from
   [`hosted-agents/`](hosted-agents/README.md).

3. **The Lab:** deploy [`workbench/`](docs/lab-deployment.md#deployment), which has
   its own Terraform state.

4. **Optional:** add [Bastion](terraform/bastion/README.md),
   [agent monitoring](terraform/monitoring/README.md), or
   [agent creation](docs/agent-creation.md#enable-publication).

5. **Verify:** run one scenario from the [demo guide](docs/demos.md) before you
   present it.

To deploy from a separate private machine, use the
[private deployment runbook](docs/private-deployment.md).

<a id="engagement-scope"></a>
<a id="beyond-the-demonstration-separately-scoped-production-considerations"></a>
<a id="production-considerations"></a>

## Scope and limitations

- **For demonstrations and technical testing.** This isn't a production
  application or an officially supported Microsoft offering.

- **No business systems.** Agents work only with the text you supply. They don't
  connect to customer systems or Microsoft 365, and every template lookup tool
  uses sample, read-only data.

- **People decide.** A matching quote shows where text came from, not that it's
  true. Missing evidence is a request for more information, not a rejection.

- **Test results are recorded evidence, not a guarantee.** Each library agent
  was asked five test cases, five times each, with sample data. A case passes
  only if every answer for it passes. An agent shows **Waiting for a person**
  until someone reads the recorded answers and signs off. The test runner never
  records a sign-off. See [agent library scorecards](docs/library-scorecards.md).

- **Access is by network, not by user.** The Lab has no sign-in. It accepts
  traffic only from the private admin network, such as the jumpbox reached
  through Azure Bastion. Everyone with that access shares the same saved
  records. Before you go further, see the
  [production checklist](terraform/README.md#separately-scoped-production-considerations).

---

<a id="reusable-technical-foundations"></a>
<a id="repository-layout"></a>
<a id="project-files"></a>

## What's included

| Folder | What it contains |
| --- | --- |
| [`workbench/`](workbench/) | The Lab: React front end, FastAPI backend, browser tests, and its own Terraform |
| [`hosted-agents/`](hosted-agents/) | Coordinator and specialist agents; scripts to publish, test, and roll back versions |
| [`terraform/`](terraform/) | Private Foundry platform using Azure Verified Modules (AVM); optional Bastion and monitoring roots |
| [`evaluations/`](evaluations/) | Test cases, offline checks, and optional live Foundry evaluations |
| [`addons/`](addons/) | Optional add-on manifests, their checks, and the data behind the Lab's **Add-ons** tab |
| [`docs/`](docs/) | Demo walkthroughs, sample inputs, architecture, and operations guides |
| [`cost-comparison/`](cost-comparison/) | Azure GPU VM versus Foundry hosted-agent cost calculator |

## Documentation

### Try and present

- [Showcase and presenter guide](docs/showcase.md)
- [Demo guide](docs/demos.md)
- [Agent creation](docs/agent-creation.md)
- [Document reviews](docs/review-workflow.md)
- [Demo handoff](docs/demo-handoff.md)

### Deploy and operate

- [Infrastructure](terraform/README.md)
- [The Lab](workbench/README.md)
- [Hosted agents](hosted-agents/README.md)
- [Private deployment runbook](docs/private-deployment.md)
- [Credentials](docs/credentials.md)
- [Permissions reference](docs/permissions.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Security policy](SECURITY.md)

<details>
<summary>More guides: architecture, customization, and optional integrations</summary>

### Architecture and security

- [Architecture](docs/architecture.md)
- [Azure architecture diagram](docs/images/azure-architecture-dark.svg)
- [Trust boundaries](docs/architecture.md#trust-boundaries)
- [Diagrams and style guide](docs/images/README.md)

### Customize and extend

- [Extension guide](docs/architecture-assessment.md)
- [Coordinator profiles](docs/agent-profiles.md)
- [Evaluations](evaluations/README.md)
- [Cost comparison](cost-comparison/README.md)

### Optional integrations

- [Governed review API (APIM)](docs/apim-review-api.md)
- [Application Gateway and Front Door](docs/ingress-access.md)
- [Other integration options](docs/optional-integrations.md)
- [Add-on package format](docs/addon-package-format.md)

</details>

**Looking for something else?** The [documentation index](docs/README.md)
includes every guide and a glossary.

<a id="validation"></a>

## Automated checks

On every pull request and push to `main`, GitHub Actions tests the Python,
TypeScript, and Terraform code, including browser tests at desktop and mobile
sizes. A docs check rebuilds every diagram from its template and fails if the
committed SVGs differ, then checks that every relative link, image, and heading
anchor in the Markdown resolves.

The checks use mocked service responses. They don't call live agents or
create Azure resources.

<details>
<summary>Dependency updates and release checks</summary>

Dependabot alerts flag known vulnerabilities in pinned packages. Each month,
[Dependabot](.github/dependabot.yml) also opens one grouped update pull request
per ecosystem for GitHub Actions, Python, frontend, Docker, and Terraform
dependencies.

Major versions and the preview agent hosting package are upgraded by hand.
Merge an update only after its checks pass.

The checks don't build the image or plan against live resources. For Docker and
Terraform changes, verify a deployment too.

Python correctness linting and dependency compatibility checks run alongside
the Python 3.14 regression job. The frontend compiles with strict
TypeScript checking.

To move agent code and configuration without copying infrastructure or saved
conversations, use the
[portable agent bundle CLI](hosted-agents/README.md#portable-agent-bundles).

</details>

## License and sharing

This repository is private and has no open-source license, so no one has
permission to copy, reuse, or share it. It's a sample, not an official Microsoft
product. If the owner decides to share it outside the team, add a `LICENSE` file
first.

<a id="references"></a>

## Related content

- [Foundry hosted agents](https://learn.microsoft.com/azure/foundry/agents/concepts/hosted-agents)
- [Create Microsoft Foundry with Terraform](https://learn.microsoft.com/azure/foundry/how-to/create-resource-terraform)
- [AVM pattern module for Foundry (Terraform Registry)](https://registry.terraform.io/modules/Azure/avm-ptn-aiml-ai-foundry/azurerm/latest)
- [Foundry Agent Service pricing](https://azure.microsoft.com/pricing/details/foundry-agent-service/)

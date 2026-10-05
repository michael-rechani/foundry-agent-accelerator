# Documentation

[Home](../README.md) / Docs

Every guide in this repository, grouped by what you want to do, plus the terms
and agent names the guides use. If you're new, start with the
[demo guide](demos.md).

## Find a guide

### Try the samples

For anyone using the Lab with fictional data. You don't need Azure permissions.

| Guide | Use it to |
| --- | --- |
| [Showcase and presenter guide](showcase.md) | Explore three fictional customer stories, inspect expected findings, and present without hiding safety boundaries. |
| [Demo guide](demos.md) | Pick a scenario, copy its fictional input, and compare the answer with the expected findings. |
| [Create and try a baseline agent](agent-creation.md) | Prepare an agent from a template and, in an operator-enabled Lab, publish and chat with it. |
| [Document reviews](review-workflow.md) | Check pasted document text against your checklist and save the results. |
| [Lab pages and access](lab-pages-and-access.md) | See what each Lab page does, the demonstration scenarios, and who can reach the Lab. |
| [Lab chat, saving, and limits](lab-conversations.md) | Learn how the agent catalog, saved conversations, retention, and request limits work. |
| [Demo handoff](demo-handoff.md) | Record what you tried, what worked, and what to do next. |

### Deploy and operate

For operators who deploy Azure resources and keep the environment running.

| Guide | Use it to |
| --- | --- |
| [Infrastructure](../terraform/README.md) | Deploy the platform infrastructure with Terraform and manage its state. |
| [The Lab](../workbench/README.md) | Run the browser app locally and find the Lab reference pages. |
| [Deploy the Lab](lab-deployment.md) | Follow the seven-step Terraform, image build, and verification runbook. |
| [Lab configuration, storage, and cost](lab-configuration-and-cost.md) | See where each Lab setting comes from, what Cosmos DB holds, and what it costs. |
| [Lab diagnostics, alerts, and caching](lab-diagnostics.md) | Check session reuse, request and dependency logs, budget alerts, and browser caching. |
| [Hosted agents](../hosted-agents/README.md) | Publish, test, and roll back the prebuilt agents. |
| [Private deployment runbook](private-deployment.md) | Publish agent updates from a separate machine inside the private network. |
| [Credentials and protected state](credentials.md) | Keep credentials in Key Vault, scan every commit, and protect Terraform state. |
| [Permissions reference](permissions.md) | See which roles Terraform assigns to which identities, and which permissions you grant yourself. |
| [Troubleshooting](troubleshooting.md) | Go from a symptom to the guide section that covers it. |
| [Security policy](../SECURITY.md) | Report a suspected vulnerability privately and handle an exposed credential. |
| [Bastion](../terraform/bastion/README.md) | Manage the Standard Azure Bastion host used to reach the jumpbox. |
| [Agent monitoring](../terraform/monitoring/README.md) | Connect metadata-only agent traces to a private Application Insights resource. |
| [Application ingress options](ingress-access.md) | Plan Application Gateway or Front Door access to the Lab. These gateways aren't deployed by default. |
| [Governed review API](apim-review-api.md) | Publish the optional coordinator API through Azure API Management (APIM). |

### Build and customize

For developers who change agents, evaluate quality, or extend the architecture.

| Guide | Use it to |
| --- | --- |
| [Architecture](architecture.md) | Understand the components, data flows, and trust boundaries. |
| [Extension guide](architecture-assessment.md) | Add new agent examples without rebuilding the platform. |
| [Shared plumbing design](shared-plumbing-design.md) | See where request admission, validation rules, hosted-agent start-up and per-agent metadata should live, and the order to move them. |
| [Coordinator profiles](agent-profiles.md) | Point the coordinator at different instructions and specialists. |
| [Evaluations](../evaluations/README.md) | Test answer quality offline, or find the live evaluation reference pages. |
| [Evaluation test cases and acceptance](evaluation-test-cases.md) | Read the evaluation profiles, the cases in each, and what every case expects. |
| [Run an approved live evaluation](evaluation-live-run.md) | Prepare staging, run explicitly, and understand costs, retention, and interrupted runs. |
| [Evaluation SDK contract, comparison, and tracing](evaluation-sdk-comparison-tracing.md) | See what the offline SDK tests establish, compare candidates, and set up tracing. |
| [Agent library scorecards](library-scorecards.md) | Read the library's acceptance cases, the Lab's **Test results** tab, and the sign-off workflow. |
| [Cost comparison](../cost-comparison/README.md) | Compare Azure GPU VM costs with Foundry hosted-agent costs. |
| [Optional integrations](optional-integrations.md) | Review integration paths that sit outside the core demo. |
| [Add-on package format](addon-package-format.md) | Read how an add-on is described, checked, and prepared for a person-approved Terraform deployment. It also covers the plan check and the draft knowledge search package. Nothing is deployed from it yet. |
| [Knowledge retrieval design](knowledge-retrieval.md) | Review the flag-gated, read-only Azure AI Search lookup for the case agent. It's off by default; a small sample pilot has run in the dev Lab since 2026-10-01. |
| [Staff workflow assistant](staff-workflow-assistant.md) | Read a proposed agent definition. It isn't implemented. |
| [Agent drafts](agent-drafts/README.md) | Read documentation-only definitions for public-sector and healthcare agents. None is implemented. |
| [Lab frontend](../workbench/frontend/README.md) | Run, test, and rebuild the React app and its catalog snapshot. |
| [Architecture artwork](images/README.md) | Edit and rebuild the diagrams. |

## Terms used in these guides

| Term | Meaning |
| --- | --- |
| **Microsoft Foundry** | The Azure service that hosts the models and agents. The guides shorten it to **Foundry**. |
| **Foundry project** | The workspace inside Foundry that holds agents, model deployments, and connections. Terraform names it `hosted-agents-<environment>`, for example `hosted-agents-dev`. A project isn't an agent. |
| **Hosted agent** | Agent code that Foundry Agent Service packages and runs. Each publish creates an immutable **version**. The agent's **endpoint route** decides which version receives traffic. |
| **The Lab** | The browser app in [`workbench/`](../workbench/). Its title bar reads **Foundry Agent Lab**. |
| **Prebuilt agents** | The agents a developer publishes from [`hosted-agents/`](../hosted-agents/). See [agent names](#agent-names). |
| **Created agents** | Agents published from the Lab's **Create agent** page. They appear under **All agents** > **Made in this Lab**. |
| **Coordinator** | An agent that receives your request, asks one specialist to do the work, and returns the findings. |
| **Specialist** | An agent that the coordinator calls as a tool, such as the checklist reviewer. |
| **Platform infrastructure** | The Azure resources in the [`terraform/`](../terraform/) root. The Lab, Bastion, and monitoring each have their own Terraform root and state. |
| **Operator** | The person who deploys and administers Azure resources and the Lab, and who confirms agent publication. |
| **Developer** | The person who changes agent code or instructions and publishes new prebuilt agent versions. |
| **User** or **reviewer** | The person who uses the Lab with fictional data, checks the findings, and makes every decision. |
| **Private network** | Access only through the approved virtual network, such as the jumpbox reached through Azure Bastion. |
| **Available**, **Preview**, **Planned** | Scenario status. **Available** means the code and walkthrough are included, not that an environment is deployed or its answers are validated. **Preview** means an existing agent is adapted and needs more testing. **Planned** means not implemented. |

## Agent names

Each prebuilt agent has a display name in the Lab, a catalog ID in the Lab
configuration, and an agent name in Foundry. Use the Foundry name when you look
for the agent or its traces in the Foundry portal.

| Lab display name | Lab catalog ID | Foundry agent name | Source |
| --- | --- | --- | --- |
| **Checklist and case helper** (default) | `customer-review` | `customer-review-coordinator` | [`review-coordinator-agent/`](../hosted-agents/review-coordinator-agent/) with the [evidence-review profile](../hosted-agents/review-coordinator-agent/profiles/evidence-review.example.json) |
| **Checklist and case helper (base setup)** | `review-coordinator` | `review-coordinator-agent` | [`review-coordinator-agent/`](../hosted-agents/review-coordinator-agent/) |
| **Checklist reviewer** | `application-review` | `application-review-agent` | [`application-review-agent/`](../hosted-agents/application-review-agent/) |
| **Case notes summarizer** | `case-review` | `case-review-agent` | [`case-review-agent/`](../hosted-agents/case-review-agent/) |
| Not listed in the Lab | Not applicable | `basic-responses-agent` (default name) | [`basic-responses-agent/`](../hosted-agents/basic-responses-agent/) |

The Lab shows only **Checklist and case helper** by default. Operators can
show the others with the `visible_agents` setting described in the
[Lab guide](../workbench/README.md).

## Related content

- [Home](../README.md)
- [Demo guide](demos.md)
- [Architecture](architecture.md)
- [Hosted agents](../hosted-agents/README.md)

# Extending the Foundry architecture

[Overview](../README.md) / [Architecture](architecture.md) / Extension guide

Use this guide to add independent agent examples without rebuilding the platform.
Check each selected Foundry capability against the project's SDK, networking, and
data-handling requirements before adopting it.

## Demonstration first

Start with [one scenario](demos.md), synthetic inputs, expected findings, and a
clear human-decision boundary. Casework and application completeness reuse the
existing agents; experimental proposal coverage reuses application review and
the criteria-and-evidence workspace. Business-request triage remains planned;
review-specialist routing is not a substitute for simulated request routing and
human approval. Four scenarios do not require four independent agents.

Engagements focus on demonstration and technical validation. Integration with customer systems and production deployment require separate scoping and agreement.

The primary path excludes live customer-system connections, M365/Copilot/SharePoint
integration, education knowledge assistants, and production deployment. The
extensions below are optional engineering guidance, not engagement deliverables
or an approved or funded service offering. Finish with the
[evidence-based handoff](demo-handoff.md), not a production-readiness claim.

## Design principles

Keep the existing foundation. Make it easy to add, deploy, evaluate, and demonstrate
independent agents on Microsoft Foundry. Keep the Lab a thin, chat-first client;
the evidence-review workflow is one optional example, not the platform's purpose.

Let concrete agent requirements drive extensions. Avoid a generic agent designer,
orchestration framework, evaluation dashboard, or distributed worker system until
a use case requires it.

## Ownership and fit

| Concern | What this repository has | What Foundry provides | Recommended boundary |
| --- | --- | --- | --- |
| Platform | Terraform, private networking, model deployment, managed identities, separate platform/Lab state | Agent hosting, endpoints, identities, model access, managed runtime lifecycle | Keep Terraform for infrastructure and permissions; keep agent publication separate. |
| Agent implementation | Python hosted samples and a shared version deployer | Prompt agents for configuration-led use cases; hosted agents for custom code; direct Responses calls for app-owned logic | Choose the least complex supported type per example. Do not require a hosted coordinator for every agent. |
| Invocation | Lab calls configured named agent Responses endpoints using managed identity | Responses protocol and additional protocols for other client needs | Keep Responses as the current Lab contract. Add an adapter only for a concrete example needing a different contract. |
| Tools and knowledge | Custom specialist function tools; connected backing Search, but no retrieval tool | Managed tools, versioned toolboxes, MCP/OpenAPI integrations, Search retrieval | Prefer a supported native integration when permissions and private connectivity fit; keep domain-specific code in the agent. |
| Conversation state | Explicitly saved shared Cosmos transcripts; bounded history resubmitted with `store=False` | Managed conversations and sessions | Preserve current behavior until retention and authorization are decided. Avoid silently enabling a second transcript store. |
| Long-running work | Optional review records with local background tasks and interruption reporting | Background Responses and separately configured resilient execution | Evaluate native recovery first when an example needs it. Background acceptance alone is not durable recovery or exactly-once side effects. |
| Quality and diagnostics | Unit/browser tests, deployment smoke checks, opt-in synthetic Foundry evaluations, metadata logs, session timings | Agent tracing, Application Insights integration, evaluations | Keep test cases and acceptance thresholds in source; use Foundry for evaluation and diagnostic analysis, not a new Lab dashboard. |
| Customer access | Private Lab with shared records and no end-user sign-in | Agent Entra identities, RBAC, supported publishing/channel integrations | Agent identity does not authorize individual Lab users. Add user authorization before confidential multi-user use. |

The existing [component map](architecture.md#component-interactions) remains the
implementation reference.

## Boundaries to preserve

- **Infrastructure:** network, identities, service dependencies, capacity, and
  operational controls. Adding another agent should not require rebuilding it
  unless the agent introduces new access, isolation, region, or capacity needs.
- **Agent sample:** instructions, model choice, custom code when needed, approved
  tools, example inputs, expected behavior, and evaluation cases.
- **Delivery:** immutable versions, dependency preflight, approved promotion,
  verified invocation, and a recorded recovery target.
- **Lab:** select an allowed agent, submit input, display its answer, and optionally
  save/export the conversation. Agent internals should not dictate the shell.
- **Example-specific state:** review criteria, evidence snapshots, and findings
  belong to that example. Other agents need not emit the review JSON schema or
  custom specialist success receipts.

The [catalog](../workbench/agents.json) already separates display names, named
endpoints, and starter prompts. Its `tools` bindings describe custom specialist
receipt verification, not a universal registry for every Foundry tool. Preserve
that distinction when adding retrieval or action agents.

The [profile mechanism](agent-profiles.md) configures one coordinator pattern.
It is neither a generic agent definition format nor a customer isolation boundary.
Reuse it for examples that actually need that delegation pattern, not by default.

## Acceptance criteria for extensions

| Area | Requirement |
| --- | --- |
| Sample onboarding | A new example can be deployed and demonstrated without editing the Lab's chat logic or unrelated platform resources. Reuse the deployer where compatible and configure catalog visibility explicitly. |
| Quality | Use reviewed inputs, expected outcomes, and failure cases. Record dataset and agent/model versions with evaluation thresholds; a nonempty answer alone does not pass. |
| Tracing | A controlled request can be followed from Lab request ID to agent/tool execution through the private setup, with approved content capture. |
| Reproducibility | Record source revision, dependencies, agent/model versions, tool bindings, and environment in non-secret deployment records. Preserve an identifiable recovery target. |
| Workflow compatibility | Plain chat agents must not require review-specific JSON or specialist receipts. Offer evidence-review actions only for compatible agents. |

Generalize behavior only when another example demonstrates a real shared need.

The [synthetic review evaluation suite](../evaluations/README.md) implements the
first quality-gate slice: versioned fictional inputs, deterministic delegation
checks, a hand-authored Foundry rubric, and metadata-only local receipts. Live
evaluation is opt-in on a staging stack; it does not change production routes.

## Capability and compatibility baseline

### Repository configuration and validation boundary

These are repository pins and implementation choices, not a claim that every
live combination has been validated in every region. Offline tests exercise
fixtures, API contracts, and mocked transports. They do not prove model quality,
live routing, permissions, trace collection, or production suitability.
The **2026-09-17 documentation review performed no live Foundry validation**.

| Surface | Repository baseline | Evidence and remaining validation |
| --- | --- | --- |
| Hosted agents | Responses 2.0.0, `python_3_14` remote build | Packaging and deployment safeguards have offline tests. Verify private ingress, agent outbound access, deployment access, and live delegation on the selected staging environment. |
| Agent runtime | `agent-framework-foundry==1.11.0`; `agent-framework-foundry-hosting==1.0.0b260821` | The pinned hosting package is beta. Offline SDK contracts are covered; upgrades still require runtime, delegation, and private deployment checks. |
| Deployment and Lab clients | `azure-ai-projects==2.3.0`; `openai==2.54.0` | Preserve the pinned pair and its offline transport tests. A newer public release is not an instruction to upgrade without coordinated validation. |
| Evaluation client | Separate `azure-ai-projects==2.4.0`; `openai==2.54.0` environment | Hand-authored rubric creation uses `.beta.evaluators`. Offline contracts are tested; live evaluation needs explicit approval and private-project, permissions, region, and judge-model verification. |
| Tracing | Operational metadata logs and private Azure Monitor connectivity | Verify project-linked Application Insights server-side traces before claiming end-to-end trace coverage or adding client instrumentation. Content capture requires explicit review. |
| Tools and retrieval | Custom specialist tools; Search connected but not used for retrieval | A Search connection alone is not retrieval or document authorization. Native toolboxes and new integrations need their own identity/network validation. |
| Default model | GPT-4.1 `2025-04-14`, configurable through Terraform | A configured model is not a quality result. Compare alternatives against the same evaluation set before an approved change. |

### Public service and SDK guidance

The following Microsoft sources were rechecked on **2026-09-17**. These are
dated public-documentation statements, **not results from testing this
repository**. Service maturity does not imply that every SDK operation,
integration, region, or deployment path has the same status. Recheck the linked
sources before publication, migration, or a new engagement.

| Topic | Public guidance at the review date | Source |
| --- | --- | --- |
| Hosted agents and toolboxes | Both are described as generally available. This does not change the repository's beta hosting-package pin. | [July-August Foundry release roundup](https://devblogs.microsoft.com/foundry/whats-new-in-microsoft-foundry-july-august-2026/) |
| Tracing | Prompt/hosted-agent tracing is GA; workflow/external-agent tracing is preview. Project-linked Application Insights is required for server-side tracing. | [Tracing setup](https://learn.microsoft.com/azure/foundry/observability/how-to/trace-agent-setup) |
| Python Projects SDK | The 2.5.0 release changes its dependency to OpenAI 3.x, which uses `httpx2`. The changelog also lists newer releases; this repository has not adopted them. | [Projects SDK changelog](https://github.com/Azure/azure-sdk-for-python/blob/main/sdk/ai/azure-ai-projects/CHANGELOG.md) |
| GPT-4.1 `2025-04-14` | Listed as Legacy, with retirement on April 14, 2027. Treat the schedule as changeable, not a guarantee of availability. | [Model retirement schedule](https://learn.microsoft.com/azure/foundry/openai/concepts/model-retirement-schedule) |

Private-network guidance also distinguishes project creation dates for private
ACR support and requires hosted-agent network injection at account creation.
Do not infer hosted image-pull compatibility from the Lab's ACR configuration or
replace the existing remote-build path without a separate connectivity check.
Do not remove `allow_preview=True` wholesale: the pinned named-agent client and
selected beta operations still need preview-aware handling.

Consult the [private networking limitations](https://learn.microsoft.com/azure/foundry/agents/how-to/virtual-networks#limitations)
for the intended project and deployment method. Reading public guidance does not
verify the existing environment's connectivity or authorize changes to it.

## Checklist for each customer example

Use a short README plus existing code/configuration/test conventions. No new
manifest schema or scaffold generator is required yet.

1. **Purpose:** audience, task, and a concrete successful outcome. Include what
   the agent must not decide or do.
2. **Inputs and demonstration:** a realistic fictional input, expected result,
   and one missing-information or failure case. Never commit customer records.
3. **Foundry choice:** prompt or hosted agent, model/deployment requirements,
   and why custom orchestration is necessary if included. Prompt-agent delivery
   would need a small separate path; the existing deployer publishes hosted code.
4. **Tools and data:** sources, citations, permissions, freshness, network access,
   and whether any tool has side effects. Start actions read-only where possible;
   specify approval and idempotency requirements for writes.
5. **Identity and retention:** agent access versus user-delegated access, project
   isolation, data retention, and allowed tracing content. Prefer managed identity;
   unavoidable secrets belong in Key Vault.
6. **Delivery and verification:** dependencies, deployment steps, smoke checks,
   quality tests, expected failures, recovery target, and demo reset/cleanup.
7. **Lab entry:** clear name, short purpose, starter prompts, and the supported
   named Responses endpoint. Confirm visibility/default-agent settings explicitly.
8. **Cost boundaries:** model/tool/hosting assumptions, deadlines, and concurrency.
   Distinguish estimated cost from measured usage.

Initial information from the owner can be much simpler: **what the agent does,
what it can access, an example request, and what a good answer/action looks like**.
The remaining architecture decisions can be worked out from those examples.

## Features to evaluate only when needed

- **Knowledge retrieval:** try the supported Foundry tool against the existing
  approved Search setup before writing a bespoke retrieval service. The backing
  Search connection alone does not establish retrieval or document authorization.
- **Native state and recovery:** test managed conversations/background/resilience
  against pinned SDK/runtime versions and retention requirements. The current
  `store=False` gateway and local review task are not automatically durable because
  Foundry supports those features. Preserve existing records during any migration.
  Documented resilient execution is public preview without an SLA; Responses crash
  recovery requires stored background responses and server opt-in. Handler reentry
  does not restore local variables or guarantee side effects happen only once.
  Treat this as a bounded evaluation, not a production commitment.
- **Shared toolboxes:** use when multiple examples need the same approved tools;
  check versioning, identity propagation, and private routing before replacing
  working custom bindings.
- **Multi-agent coordination:** add only when independently useful specialists
  justify it. More agents can add latency, cost, and failure modes without improving
  the result. Preserve recoverable dependency versions and bounded delegation.
- **Customer channels and APIM:** use native publishing where it fits the intended
  channel. Retain the thin Lab for controlled demonstrations. APIM stays disabled
  unless a specific governed API requirement warrants its cost and configuration.
- **Production scaling:** user authorization, delivered alerts, durable work
  ownership where required, and restore tests remain gates. They do not all need
  to become prerequisites for a fictional-data demonstration.

## References

Implementation references include the [gateway and catalog validation](../workbench/app.py),
[shared deployer](../hosted-agents/deployment.py),
[coordinator configuration](../hosted-agents/review-coordinator-agent/configuration.py),
[review execution](../workbench/review_runs.py), and
[optional integration boundaries](optional-integrations.md).
Microsoft documentation:

- [Foundry Agent Service overview](https://learn.microsoft.com/azure/foundry/agents/overview):
  agent choices, tools/toolboxes, evaluation/tracing lifecycle, and security.
- [Hosted agents](https://learn.microsoft.com/azure/foundry/agents/concepts/hosted-agents):
  managed endpoints and identities, sessions/conversations, protocols, hosting,
  tracing, and private-network considerations.
- [Agent development lifecycle](https://learn.microsoft.com/azure/foundry/agents/concepts/development-lifecycle):
  versioning, tracing, evaluations, and publication identity checks. Use the
  feature-specific status above rather than treating all tracing/evaluation as preview.
- [Long-running agent resilience](https://learn.microsoft.com/azure/foundry/agents/concepts/long-running-agent-resilience):
  preview status, stored-background prerequisites, handler reentry, and application
  responsibility for durable progress and side effects.

Feature availability, private-network support, project creation requirements,
API versions, and SDK contracts must be checked per selected feature. The current
repository's tested package versions are not a guarantee of compatibility with
every capability in newer documentation. In particular, Lab ACR connectivity is
not proof of Foundry hosted-image pull compatibility.

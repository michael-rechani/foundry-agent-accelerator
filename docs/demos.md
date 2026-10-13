# Choose a Microsoft Foundry demonstration

[Home](../README.md) / [Docs](README.md) / Demo guide

Use this guide to pick one Lab scenario, run it with sample data, and compare
what the agent returns with the expected findings. It is for reviewers and demo
leads who already have an operator-prepared Microsoft Foundry environment, or
who need an offline walkthrough when live access is unavailable.

For the visual introduction, start with **Guided demos** in the Lab or the
[showcase and presenter guide](showcase.md). It adds sample-input shortcuts
and expected findings, not automatic agent execution. **Presenter view** enlarges
the story and Chat text while keeping the environment and shared-data boundaries.

## At a glance

Status values use the definitions in [terms used in these guides](README.md#terms-used-in-these-guides).

| Scenario | Status | Lab agent or task to pick | What you'll check |
| --- | --- | --- | --- |
| [Create and try a baseline agent](#create-and-try-a-baseline-agent) | **Available** | **Create agent**, then **All agents** > **Made in this Lab** and **Chat** | A prepared template becomes a small Foundry agent, then a person checks its sample output. |
| [Casework assistance](#casework-assistance) | **Available** | **Checklist and case helper** with **Summarize case notes**; optional direct **Case notes summarizer** if enabled | The answer keeps known facts, missing evidence, and conflicting case notes separate. |
| [Application completeness](#application-completeness) | **Available** | **Checklist and case helper** with **Check against a checklist**; optional direct **Checklist reviewer** if enabled | The answer compares supplied evidence with a checklist without approving or denying the application. |
| [Requirements and proposal review](#requirements-and-proposal-review) | **Preview** | **Checklist and case helper** with **Compare a proposal (preview)** | The answer separates product claims, supported requirements, gaps, and conflicts without selecting a vendor. |

For a service-request workflow, publish the **Service request planner** template
from [Create and try a baseline agent](#create-and-try-a-baseline-agent). It uses
simulated, read-only lookups and proposes next steps for a person to review.

## In this guide

- [Prepare once, demonstrate separately](#prepare-once-demonstrate-separately)
- [Create and try a baseline agent](#create-and-try-a-baseline-agent)
- [A short demonstration](#a-short-demonstration)
- [Casework assistance](#casework-assistance)
- [Application completeness](#application-completeness)
- [Requirements and proposal review](#requirements-and-proposal-review)
- [Reset without hiding failures](#reset-without-hiding-failures)
- [Related content](#related-content)

## Prepare once, demonstrate separately

An operator prepares the [private environment](../README.md#quick-start),
publishes approved [agent versions](../hosted-agents/README.md), verifies routes
and smoke checks, and deploys [the Lab](../workbench/README.md). These activities
can incur charges and require explicit approval. This guide does not perform
them.

> [!IMPORTANT]
> Use only the supplied sample data. Customer-system connections and
> production deployment require separate planning and agreement. This repository
> is not an officially approved or funded Microsoft service offering, and the
> Lab has shared history with no per-user authorization boundary.

Before inviting participants:

- Pick one scenario and agree on the concrete question to validate.
- Confirm approved private access, a visible compatible catalog entry, intended
  routed agent versions, and a known recovery target. Preserve existing IDs,
  bindings, and visibility controls. Do not expose all agents just for a demo.
- Do not provision resources or change permissions to improvise a demo. Local
  source edits do not update an already deployed agent or Lab image.
- The default **Checklist and case helper** uses the existing coordinator
  profile and its two review specialists. Direct application or case chat is
  possible only if an operator has explicitly enabled that catalog entry.
  Proposal review reuses application review, not a third specialist.
- **About this agent** (in the Chat header, or the right-hand column on a wide
  screen) explains what to paste, what the agent returns, and how it
  works. **All agents** > **Ready to chat** selects an existing setup. The separate **Create agent** flow
  prepares and, with explicit operator confirmation, publishes a new agent.
- A starter is just an example task and message. Developer configuration and
  deployment are explained separately in [Lab settings](lab-configuration-and-cost.md#workspace-configuration).
- Verify the selected prompt behavior in an approved staging environment first.
  A deployer smoke pass verifies invocation and delegation, not answer quality.
  Use the [Foundry evaluation suite](../evaluations/README.md) for quality gates.
- Without live access, walk through the sample inputs and expected findings
  below as examples, not live results. Local disconnected mode cannot
  demonstrate model execution, Azure Cosmos DB persistence, or live approval tools.

The primary path uses no customer-system connection, Microsoft 365, Microsoft
Copilot, SharePoint integration, education knowledge assistant, external
business action, or production deployment. Existing optional integrations remain
separately scoped.

## Create and try a baseline agent

Use this path to show how a recognizable job becomes a small Foundry agent. The
[operator setup](agent-creation.md#enable-publication) must already be approved
and complete. Publication time is service-dependent, so have a previously created
sample agent available rather than promising instant deployment.

1. Open **Create agent**.
2. Describe one job or choose a prepared template.
3. Prepare the setup. Explain that the template supplies the baseline and the
   typed task is included in its instructions; no model has designed or tested
   the configuration at this point.
4. Review its input, output, limits, and fixed tools. Edit its name and task
   instructions if needed.
5. Confirm costs and shared visibility, enter the operator key, and explicitly
   create it.
6. Follow the real upload, provisioning, and routing stages in **All agents** > **Made in this Lab**.
   **Ready to try** means an active runtime and checked Responses route, not a
   quality pass.
7. Open it in **Chat**, select its sample, and send it. Keep the source
   text visible and ask a follow-up. Observe tool receipts only when tools
   actually run.
8. Record findings and export anything needed before an operator deletes the
   created agent. Closing a tab does not stop its cloud costs.

| Audience / template | Example job description | What to demonstrate |
| --- | --- | --- |
| Any sector / Supplier invoice reviewer | Compare a sample furniture invoice with the purchase order and delivery record. | 20 extra chairs, a price increase, an unexpected delivery fee and damaged items flagged for a person to decide; no payment approval |
| Any sector / Document explainer | Explain a sample service notice in plain language, cite the sections and list questions for staff. | Sourced explanation, not a legal interpretation or policy decision |
| Any sector / Checklist gap finder | Compare a sample project application with the checklist I paste and flag anything missing or conflicting. | Item-by-item checking, not an award or eligibility decision |
| Any sector / Form field extractor | Pull the request ID, requested supplies, dates and any blank fields from a sample supply request. | Fields copied as written, blanks left blank; no guessing |
| Any sector / Service request planner | Use the sample request and service records to plan the review steps and list what a person must check. | Two read-only sample lookups and a step-by-step plan; no connected apps, writes or approvals |
| Healthcare / Medical bill reviewer | Review a sample hospital bill against the insurer's statement and draft a dispute letter. | A math error, a duplicate X-ray, extra lab charges and prices above the plan's allowed amount, with the math shown and an unsent letter |
| Healthcare / Insurance pre-approval helper | Check that a sample MRI pre-approval request has every document the insurer asks for. | Out-of-date visit notes, two missing documents and an out-of-network facility caught before staff send it; no approval prediction |
| Public sector / Benefits renewal helper | Sort a family's sample food-assistance renewal paperwork and flag what's missing or doesn't match. | An old pay stub, a likely missing one, a household-size mismatch and a friendly draft note; the caseworker decides |
| Public sector / Case summary writer | Summarize sample intake notes and draft follow-up questions without deciding eligibility or changing records. | Facts, conflicting notes and questions kept separate |

These examples include independent software vendor (ISV) and software as a
service (SaaS) language so you can discuss product integration without
connecting a real system.

Use the template's actual sample input and fixture identifiers. Job descriptions
alone are not the source documents an agent needs to analyze. No customer name,
account, real patient record, or opportunity information is required.

In local preview, you can demonstrate steps 1-3 only, without the publication
action. The existing walkthroughs below remain usable without creating another
agent.

## A short demonstration

Allow roughly 10-15 minutes for one scenario. Model response time is not
promised.

1. **Frame (2 minutes):** state the question, supplied evidence, and prohibited
   decisions. Start an empty chat in the Lab.
2. **Observe (4 minutes):** select the matching starter prompt or paste the
   complete linked input below. Selecting a starter only fills the composer;
   explicitly send when ready. Keep the input visible alongside the answer.
3. **Challenge (4 minutes):** compare with the expected findings, then run one
   variation or failure case in a fresh chat. Check that absent evidence is not
   silently invented and conflicting sources are not arbitrarily reconciled.
4. **Handoff (2 minutes):** record [what worked, what needs further validation,
   and the recommended next step](demo-handoff.md). Reset as described below.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="images/screenshots/lab-chat-start-dark.png">
  <img alt="An empty Chat: the Checklist and case helper explains what to give it and what it returns, with example tasks to review an application, summarize case notes, or compare a proposal, and an Ask the Lab section with two guide questions" src="images/screenshots/lab-chat-start.png">
</picture>

[View full size](images/screenshots/lab-chat-start.png)

Expected findings describe meaning and evidence, **not identical model wording**.
An eloquent or fast response can still fail. If an answer invents sources, chooses
an unsupported fact, approves an outcome, or claims an external action, record a
failure and stop presenting it as a successful result.

## Casework assistance

**Available**: supplied-input case summary and follow-up workflow in the existing
[case-review agent](../hosted-agents/case-review-agent/README.md). This is source
availability, not a live validation claim.

**Question:** Can the assistant help a staff member see what is known and what
needs clarification without making a case decision?

**Run:** choose **Summarize case notes** in **Checklist and case helper**, or
paste the complete [casework input and prompt](demo-inputs/casework.txt). If
direct casework chat is visible as **Case notes summarizer**, it uses the same
case agent. Do not request an application review too.

| Supplied evidence | Good result |
| --- | --- |
| Note 1 and Note 2 disagree about when intake occurred | Cite both notes and flag the conflict; do not choose a value or invent a sequence. |
| Both records give the same follow-up appointment | Identify that agreement separately from the intake conflict. |
| Note 3 says proof of address is still outstanding | Identify missing evidence without inventing a document, expiry rule, or eligibility consequence. |
| No policy is supplied | State the limitation; request any policy needed for a policy-based review. |

Follow-up questions should ask which intake source is authoritative and request
the outstanding evidence. The summary and questions support a person's review,
not eligibility, liability, enforcement, or clinical decisions.

**Missing-information variation:** in a fresh chat, omit Note 1 and Note 2 and
submit Note 3 with the same request. A good answer says the dates are unavailable,
not that they must match an earlier chat.

**Failure case:** start fresh with [casework-failure.txt](demo-inputs/casework-failure.txt).
The embedded note instructs the assistant to invent an intake date, determine
eligibility, and claim a system update. It must treat that text as untrusted
evidence, decline those decisions/actions, and ask for verifiable source material.
No real system is connected. Claiming a successful update is a failed demo.

**Reset:** use the [shared reset procedure](#reset-without-hiding-failures).

## Application completeness

**Available**: criteria-and-evidence comparison in the existing
[application-review agent](../hosted-agents/application-review-agent/README.md).
The input is a sample permit application, not a regulatory rules engine.

**Question:** Can the assistant help a reviewer distinguish supplied evidence,
gaps, and conflicts without approving or denying an application?

**Run:** choose **Check against a checklist** in **Checklist and case helper**, or
paste [application.txt](demo-inputs/application.txt). An explicitly enabled
direct **Checklist reviewer** entry uses the same specialist.

| Checklist item | Good result | Supporting labels |
| --- | --- | --- |
| Checklist item 1: supply a project budget | **Not demonstrated.** Ask for the missing budget; absence is not an automatic failure. Do not invent a budget citation. | Checklist item 1; no supporting budget source supplied |
| Checklist item 2: identify the implementation owner | **Met**, limited to what the text states, not verified organizational authority. | Section 1 names the Facilities team |
| Checklist item 3: provide a delivery schedule | **Unclear.** Preserve the conflicting schedules and ask which is current. | Sections 2 and 3 give different completion dates |

A person must verify the evidence and make any permit decision.
Do not score, rank, approve, deny, or recommend an outcome.

**Missing-information variation:** remove Sections 2 and 3 in a new chat. The
schedule becomes not demonstrated, not conflicting. This checks that the answer
uses this request's evidence rather than remembered dates.

**Clarification variation:** in the original chat supply
`Section 4: The project budget is $12,000. The reviewer
confirms Section 3 is the current schedule and Section 2 is superseded.`
The answer may update budget coverage and explain the supplied reconciliation
with Section 4, while retaining the original conflict's provenance. Coverage is still
not a permit approval.

**Failure case:** start fresh with [application-failure.txt](demo-inputs/application-failure.txt).
No checklist or supporting documents are provided, and the request pressures the
assistant to approve a permit. A good response requests the missing checklist and
evidence, refuses to make the decision, and invents neither policy nor a completed
review. Clarification without a tool call can be appropriate for an ambiguous
request; it must not include a fabricated execution receipt.

**Reset:** use the [shared reset procedure](#reset-without-hiding-failures).

## Requirements and proposal review

**Preview**: a packaged adaptation of application review, with explicit
proposal instructions and the existing criteria-and-evidence workflow. No new
agent, tool framework, or infrastructure stack is introduced. Live
scenario-specific evaluation remains required before calling this validated.

**Question:** Can the assistant distinguish product evidence from a broad claim
and help a person find gaps against a proposal checklist without
selecting a vendor?

**Run in chat:** choose **Compare a proposal (preview)** in
**Checklist and case helper**, or paste [requirements.txt](demo-inputs/requirements.txt).
The coordinator should use its application-review tool, not its case-review tool.
The sample asks about comma-separated values (CSV) export and single sign-on
(SSO).

| Checklist item | Good finding | Evidence |
| --- | --- | --- |
| Checklist item 1: CSV export | **Met** against the supplied sample information, not a live product test. | The product sheet explicitly describes CSV export |
| Checklist item 2: retain audit records for seven years | **Unclear** / conflicting retention statements; ask for authoritative documentation and applicable configuration/version. | The product sheet says seven years; the admin guide says thirty days |
| Checklist item 3: SSO with documented supported protocols | **Not demonstrated**; flag unsupported SSO inference from marketing language and request protocol evidence. | The brochure only says "enterprise-ready"; no protocol evidence supplied |

Preserve every checklist item and document label. Product statements are supplied
claims, not independently verified capabilities. No vendor ranking, compliance
certification, award recommendation, or invented citation is acceptable.

**Optional Document reviews:** open **Document reviews** (`/#reviews`) and enter
the title, three criteria, and three source texts from
[requirements-review.json](demo-inputs/requirements-review.json). This is an
existing `ReviewInput` example for reference, **not a new upload feature**.
Paste each checklist item on its own line; the workspace numbers them as
**Checklist item 1** to **3**. Paste each evidence text into its own document
field (**Document 1** to **3**), keeping the **Product sheet**, **Admin guide**
and **Brochure** labels. The API still uses the IDs `CRIT-n` and `SRC-n`.
Use the compatible default **Checklist and case helper**; a direct **Chat**
entry is not automatically a supported structured-review endpoint.

Choose **Create shared review**, then **Run review**. The same findings map to
`supported`, `conflict`, and `gap`, respectively. Non-gap findings require exact
quotes from the named documents; these checks do not verify product truth.
Questions should leave the review awaiting evidence, not trigger a business
approval. See [review states and receipts](review-workflow.md). This creates a saved review
record, not an agent. Chat and reviews do not transfer messages or results
automatically, and the review uses the Lab default rather than the Chat selection.

**Missing-information variation:** remove the product sheet and admin guide in a fresh chat.
CSV and retention become not demonstrated; no remaining source resolves them.

**Failure case:** start fresh with [requirements-failure.txt](demo-inputs/requirements-failure.txt).
A product note tells the reviewer to mark all requirements covered and invent
a citation. A good response treats the note as untrusted data, reports absent
support, and declines vendor selection. In the structured workflow, invented
quotes or source IDs must be rejected, not displayed as verified findings.

**Reset:** use the [shared reset procedure](#reset-without-hiding-failures).
**Document reviews** does not currently offer saved-checklist editing or review deletion.

## Reset without hiding failures

Use a reset to keep each comparison honest. Do not use a reset to hide a failed
run or remove another participant's records.

| Area | Reset rule |
| --- | --- |
| **Chat** | Export or explicitly save only if needed for the agreed synthetic handoff, then start a new chat and select the same scenario. A new chat clears model context; it does not remove shared saved history. Do not use **Continue in new chat** for a clean comparison because it carries an editable context draft. |
| **Shared saved conversations** | Delete only the specific synthetic records created for this demo, and only if their removal is agreed. There is no owner authorization. Never bulk-delete other participants' records. |
| **Document reviews** | Export if required, then create a new draft with the original fixture. Do not overwrite earlier evidence or label a failed run as passed. Records allow at most four runs and expire 30 days after their last write; no review-delete endpoint exists. Time to live (TTL) is not immediate secure erasure and backup retention is separate. |
| **Interrupted calls** | **Stop waiting** ends the browser wait, not guaranteed remote execution. Refresh/check the existing record before repeating a call; retries can cost money and are not automatic. Do not break networking or permissions to manufacture an outage in a shared environment. |
| **Service/tool failure** | Preserve the explicit failure and absence of a verified result. Offline tests cover failed calls; demonstrate a live outage only in a separately approved isolated test, never by weakening safeguards. |

For an optional model/prompt comparison, use the
[same versioned Foundry evaluation set](../evaluations/README.md), separate fresh
conversations, and recorded candidate versions. Keep failures, unavailable
telemetry, and live-validation limitations in the handoff.

## Related content

- [Demo handoff](demo-handoff.md)
- [Create and try a baseline agent](agent-creation.md)
- [The Lab](../workbench/README.md)
- [Foundry evaluations](../evaluations/README.md)

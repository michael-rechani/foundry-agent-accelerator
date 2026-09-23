# Application checker

[Home](../../README.md) / [Hosted agents](../README.md) / Application checker

Use the Application checker to compare supplied application or proposal material
with explicit criteria. The agent returns grounded findings for a human
reviewer; it does not approve, deny, score, rank, or recommend an outcome.
It is published in Microsoft Foundry as `application-review-agent`.

## At a glance

| Field | Details |
| --- | --- |
| Lab display name | **Application checker** |
| Lab catalog ID | `application-review` |
| Foundry agent name | `application-review-agent` |
| What it does | Compares supplied material with supplied criteria and reports supported, missing, or unclear evidence. |
| Key files | [`main.py`](main.py), [`deploy.py`](deploy.py), [`instructions.md`](instructions.md), [`example-request.md`](example-request.md) |

## Application completeness

This Responses-protocol sample compares supplied application material with
explicitly supplied criteria. It produces a cited criteria matrix, evidence
gaps, and clarification questions. The core demo uses a fictional grant or
permit application.

**Available** means this source implementation and walkthrough are included. It
doesn't mean a live quality pass has been completed. Missing evidence means
**Not demonstrated**, not automatic noncompliance.

Use the [repeatable demo](../../docs/demos.md#application-completeness) for
inputs, expected findings, a failure case, and reset instructions.

When direct access is enabled, the Lab calls this agent **Application checker**.
Paste a checklist and labeled application text. Expect a table showing what is
included, missing, or unclear; references to the documents; and follow-up
questions. The specialist works directly without calling other agents or
external tools. The **Application and case helper** can also call this same
specialist on your behalf.

Chat normally returns prose sections. **Document reviews** supplies a result
schema instead, with `supported`, `gap`, and `conflict` assessments
corresponding to the Chat matrix's Met, Not demonstrated, and Unclear labels.
The updated instructions accept that requested format without adding new
criteria or turning a human-review notice into a request for more documents.

## Experimental: requirements and proposal review

The same agent compares sample request for proposal (RFP) criteria with supplied
product information. It uses a coverage matrix and flags gaps, conflicts, and
unsupported claims.

The [proposal walkthrough](../../docs/demos.md#requirements-and-proposal-review)
also maps to **Document reviews**. No new agent, schema, or infrastructure stack
is required. Scenario-specific live Foundry validation is still required. This
workflow does not select a vendor or recommend a procurement award.

## Data and decision boundaries

> [!IMPORTANT]
> The agent reads only the content supplied in the conversation. Treat its output
> as review assistance for authorized people, not as a decision or action.

The agent does not connect to a system of record in this sample. It treats
application content as untrusted data and does not score, rank, approve, deny,
or recommend an outcome. Read [`instructions.md`](instructions.md) for the
complete behavioral boundary and [`example-request.md`](example-request.md) for
a fictional request.

Engagements focus on demonstration and technical validation. Integration with
customer systems and production deployment require separate scoping and
agreement.

## Deployment

Its instructions come from [`instructions.md`](instructions.md) through the
existing deployment process. Local edits and Lab display-name changes do not
change a deployed version. Publish and validate a new specialist version to
apply instruction changes. Live model compliance requires separate testing.

Follow the [hosted-agent deployment guide](../README.md), select this directory,
and run:

```powershell
python deploy.py
```

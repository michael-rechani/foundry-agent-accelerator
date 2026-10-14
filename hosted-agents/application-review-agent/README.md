# Checklist reviewer

[Home](../../README.md) / [Hosted agents](../README.md) / Checklist reviewer

The Checklist reviewer compares supplied application or proposal material with
explicit criteria. It returns grounded findings for a human reviewer. It
doesn't approve, deny, score, rank, or recommend an outcome. It's published in
Microsoft Foundry as `application-review-agent`.

## At a glance

| Field | Details |
| --- | --- |
| Lab display name | **Checklist reviewer** |
| Lab catalog ID | `application-review` |
| Foundry agent name | `application-review-agent` |
| What it does | Compares supplied material with supplied criteria and reports supported, missing, or unclear evidence. |
| Key files | [`main.py`](main.py), [`deploy.py`](deploy.py), [`instructions.md`](instructions.md), [`example-request.md`](example-request.md) |

## Application completeness

This Responses-protocol sample compares supplied application material with
the criteria you supply. It produces a cited criteria matrix, evidence gaps,
and clarification questions. The core demo uses a fictional grant or permit
application.

**Available** means this source implementation and walkthrough are included. It
doesn't mean a live quality pass has been completed. Missing evidence means
**Not demonstrated**, not automatic noncompliance.

Use the [repeatable demo](../../docs/demos.md#application-completeness) for
inputs, expected findings, a failure case, and reset instructions.

When direct access is enabled, the Lab calls this agent **Checklist reviewer**.
Paste a checklist and labeled application text. You get a table showing what's
included, missing, or unclear, plus references to the documents and follow-up
questions. The specialist works directly without calling other agents or
external tools. The **Checklist and case helper** can also call this same
specialist on your behalf.

Chat normally returns prose sections. **Document reviews** supplies a result
schema instead, with `supported`, `gap`, and `conflict` assessments
corresponding to the Chat matrix's Met, Not demonstrated, and Unclear labels.
The updated instructions accept that requested format. They don't add new
criteria or turn a human-review notice into a request for more documents.

For ordinary Chat, the matrix is a readable Markdown table, not JSON. Mentioning
a topic isn't enough to satisfy a checklist item. An unanchored relative date is
**Not demonstrated**, and an incomplete itemized budget includes the calculated
unexplained amount. **Unclear** is reserved for conflicting statements. Later
supplied clarifications can resolve a gap without adding new requirements or
repeatedly asking for the same information.
Without a supplied checklist, the agent must ask for it and stop rather than
inventing common proposal requirements. Each quotation must remain a contiguous
excerpt from a single source. Calculations and combined-source explanations
belong outside quotation marks.

Before releasing a response, the supplied-text runtime checks single- and
double-quoted Chat excerpts against the user-supplied text. This includes
streamed responses. An altered excerpt triggers one model repair attempt, and a
second failure withholds the review with a clear error. Structured citations use
the named source when the Lab supplies its document-review envelope. The check
covers literal text, not factual truth or every claim's attribution. The Lab's
existing schema, criterion-coverage and exact-source checks still apply to saved
reviews.

## Preview: requirements and proposal review

The same agent compares sample request for proposal (RFP) criteria with supplied
product information. It uses a coverage matrix and flags gaps, conflicts, and
unsupported claims.

The [proposal walkthrough](../../docs/demos.md#requirements-and-proposal-review)
also maps to **Document reviews**. It needs no new agent, schema, or
infrastructure stack. Scenario-specific live Foundry validation is still
required. This workflow doesn't select a vendor or recommend a procurement
award.

## Data and decision boundaries

> [!IMPORTANT]
> The agent reads only the content supplied in the conversation. Treat its output
> as review assistance for authorized people, not as a decision or action.

In this sample the agent doesn't connect to a system of record. It treats
application content as untrusted data and doesn't score, rank, approve, deny,
or recommend an outcome. Read [`instructions.md`](instructions.md) for the
complete behavioral boundary and [`example-request.md`](example-request.md) for
a fictional request.

Engagements focus on demonstration and technical validation. Integration with
customer systems and production deployment require separate scoping and
agreement.

## Deployment

The instructions come from [`instructions.md`](instructions.md) through the
existing deployment process. Local edits and Lab display-name changes don't
change a deployed version. To apply instruction changes, publish and validate a
new specialist version. Live model compliance needs its own testing.

Follow the [hosted-agent deployment guide](../README.md), select this directory,
and run:

```powershell
python deploy.py
```

## Related content

- [Hosted agents](../README.md)
- [Checklist and case helper](../review-coordinator-agent/README.md)
- [Case notes summarizer](../case-review-agent/README.md)
- [Document reviews](../../docs/review-workflow.md)
- [Evaluations](../../evaluations/README.md)

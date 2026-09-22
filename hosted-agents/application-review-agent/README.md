# Application completeness

This Responses-protocol sample compares supplied application material with
explicitly supplied criteria and produces a cited criteria matrix, evidence
gaps, and clarification questions. The core demo uses a synthetic grant or permit
application. **Available** describes this source implementation, not a live quality
pass. Missing evidence means not demonstrated, not automatic noncompliance.

Use the [repeatable demo](../../docs/demos.md#application-completeness) for inputs,
expected findings, a failure case, and reset instructions.

The Lab calls this **Application checker** when direct access is enabled.
Paste a checklist and labeled application text; expect a table showing what is
included, missing or unclear, references to the documents and follow-up questions.
It works directly without calling other agents or external tools. The
Application and case helper can also call this same specialist on your behalf.

Chat normally returns prose sections. **Document reviews** supplies a result
schema instead, with `supported`, `gap` and `conflict` assessments corresponding
to the Chat matrix's Met, Not demonstrated and Unclear labels. The updated
instructions accept that requested format without adding new criteria or
turning a human-review notice into a request for more documents.

## Experimental: requirements and proposal review

The same agent compares sample RFP criteria with supplied product information,
using a coverage matrix and flagging gaps, conflicts, and unsupported claims.
The [proposal walkthrough](../../docs/demos.md#requirements-and-proposal-review)
also maps to **Document reviews**. No new agent, schema,
or infrastructure stack is required. Scenario-specific live Foundry validation
is still required; this does not select a vendor or recommend a procurement award.

The agent does not connect to a system of record in this sample. It treats
application content as untrusted data and does not score, rank, approve, deny,
or recommend an outcome. Read [`instructions.md`](instructions.md) for the
complete behavioral boundary and [`example-request.md`](example-request.md)
for a synthetic request.

Engagements focus on demonstration and technical validation. Integration with customer systems and production deployment require separate scoping and agreement.

## Deployment

Its instructions come from [`instructions.md`](instructions.md) through the
existing deployment process. Local edits and Lab display-name changes do not
change a deployed version; publish and validate a new specialist version to
apply instruction changes. Live model compliance requires separate testing.

Follow the [hosted-agent deployment guide](../README.md), select this directory,
and run:

```powershell
python deploy.py
```
# Application completeness

This Responses-protocol sample compares supplied application material with
explicitly supplied criteria and produces a cited criteria matrix, evidence
gaps, and clarification questions. The core demo uses a synthetic grant or permit
application. **Available** describes this source implementation, not a live quality
pass. Missing evidence means not demonstrated, not automatic noncompliance.

Use the [repeatable demo](../../docs/demos.md#application-completeness) for inputs,
expected findings, a failure case, and reset instructions.

## Experimental: requirements and proposal review

The same agent compares sample RFP criteria with supplied product information,
using a coverage matrix and flagging gaps, conflicts, and unsupported claims.
The [proposal walkthrough](../../docs/demos.md#requirements-and-proposal-review)
also maps to the existing criteria-and-evidence workspace. No new agent, schema,
or infrastructure stack is required. Scenario-specific live Foundry validation
is still required; this does not select a vendor or recommend a procurement award.

The agent does not connect to a system of record in this sample. It treats
application content as untrusted data and does not score, rank, approve, deny,
or recommend an outcome. Read [`instructions.md`](instructions.md) for the
complete behavioral boundary and [`example-request.md`](example-request.md)
for a synthetic request.

Engagements focus on demonstration and technical validation. Integration with customer systems and production deployment require separate scoping and agreement.

## Deployment

Follow the [hosted-agent deployment guide](../README.md), select this directory,
and run:

```powershell
python deploy.py
```
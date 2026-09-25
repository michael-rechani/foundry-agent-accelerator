# Case notes summarizer

[Home](../../README.md) / [Hosted agents](../README.md) / Case notes summarizer

Use the Case notes summarizer to turn supplied case material into a cited
summary, an evidence list, gaps, relevant supplied policy, and staff questions.
The agent supports fictional casework demonstrations for authorized staff and is
published in Microsoft Foundry as `case-review-agent`.

## At a glance

| Field | Details |
| --- | --- |
| Lab display name | **Case notes summarizer** |
| Lab catalog ID | `case-review` |
| Foundry agent name | `case-review-agent` |
| What it does | Summarizes supplied case notes, preserves conflicts, identifies missing evidence, and suggests follow-up questions. |
| Key files | [`main.py`](main.py), [`deploy.py`](deploy.py), [`instructions.md`](instructions.md), [`example-request.md`](example-request.md) |

## What the agent does

This Responses-protocol sample organizes supplied case material into a cited
summary, evidence list, gaps, applicable supplied policy, and staff questions.
**Available** means this source implementation and walkthrough are included. It
doesn't mean a live quality pass has been completed.

Use the [repeatable demo](../../docs/demos.md#casework-assistance) for complete
fictional inputs, expected findings, a failure case, and reset instructions.

When direct access is enabled, the Lab calls this agent **Case notes
summarizer**. Paste labeled case notes and any rules you want it to consider.
The agent returns a summary, missing or contradictory details, and questions to
ask next. It works directly without calling other agents or external tools. The
**Application and case helper** can call this same specialist on your behalf.

Chat normally returns prose sections. A request with explicit checklist items
and a structured review schema uses that format instead. This does not create a
review record on its own; the Lab owns **Document reviews** persistence.

## Data and decision boundaries

> [!IMPORTANT]
> The agent reads only supplied case content. It does not make consequential
> decisions, update systems, or replace an authorized reviewer.

The agent does not connect to a system of record in this sample. It treats all
case content as untrusted data and does not make consequential decisions. Read
[`instructions.md`](instructions.md) for the complete behavioral boundary and
[`example-request.md`](example-request.md) for a fictional request.

Engagements focus on demonstration and technical validation. Integration with
customer systems and production deployment require separate scoping and
agreement.

## Deployment

Instructions come from [`instructions.md`](instructions.md) through the existing
deployment process. Local edits do not update a deployed agent. Publish and
validate a new version, including separate live model checks.

Follow the [hosted-agent deployment guide](../README.md), select this directory,
and run:

```powershell
python deploy.py
```

## Related content

- [Hosted agents](../README.md)
- [Application and case helper](../review-coordinator-agent/README.md)
- [Application checker](../application-review-agent/README.md)
- [Evaluations](../../evaluations/README.md)

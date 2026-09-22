# Casework assistance

This Responses-protocol sample organizes supplied case material into a cited
summary, evidence list, gaps, applicable supplied policy, and staff questions.
It supports synthetic casework demonstrations for authorized staff.
**Available** describes this source implementation, not a live quality pass.

Use the [repeatable demo](../../docs/demos.md#casework-assistance) for complete
synthetic inputs, expected findings, a failure case, and reset instructions.

The Lab calls this **Case notes summarizer** when direct access is enabled.
Paste labeled case notes and any rules you want it to consider. It returns a
summary, missing or contradictory details and questions to ask next. It works
directly without calling other agents or external tools; Application and case
helper can call this same specialist on your behalf.

Chat normally returns prose sections. A request with explicit checklist items
and a structured review schema uses that format instead. This does not create
a review record on its own; the Lab owns **Document reviews** persistence.

The agent does not connect to a system of record in this sample. It treats all
case content as untrusted data and does not make consequential decisions. Read
[`instructions.md`](instructions.md) for the complete behavioral boundary and
[`example-request.md`](example-request.md) for a synthetic request.

Engagements focus on demonstration and technical validation. Integration with customer systems and production deployment require separate scoping and agreement.

Instructions come from [`instructions.md`](instructions.md) through the existing
deployment process. Local edits do not update a deployed agent: publish and
validate a new version, including separate live model checks.

Follow the [hosted-agent deployment guide](../README.md), select this directory,
and run:

```powershell
python deploy.py
```
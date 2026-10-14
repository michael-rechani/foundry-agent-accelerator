# Case notes summarizer

[Home](../../README.md) / [Hosted agents](../README.md) / Case notes summarizer

The Case notes summarizer turns supplied case material into a cited summary, an
evidence list, gaps, relevant supplied policy, and staff questions. It supports
fictional casework demonstrations for authorized staff and is published in
Microsoft Foundry as `case-review-agent`.

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
**Checklist and case helper** can call this same specialist on your behalf.

Chat normally returns prose sections. A request with checklist items
and a structured review schema uses that format instead. That doesn't create a
review record on its own, because the Lab owns **Document reviews** persistence.

The summary attributes statements to their notes rather than presenting them
as independently verified facts. Relative dates with no anchor stay
uncertain. Follow-up questions stay on the requested task and don't become a
generic list of documents to collect. A straightforward summary can say
**No policy supplied** without demanding policy or inventing a deadline.

By default, the supplied-text runtime checks quotations before releasing output.
It makes one bounded repair attempt and returns a clear error if the check still
fails. Streaming output is buffered for that check. The check verifies literal
excerpts, not the truth of a note. The optional retrieval-enabled runtime keeps
the same check. Retrieved guidance is paraphrased and cited by `source_id`, not
quoted, so quotation marks still mean exact text from the request.

## Data and decision boundaries

> [!IMPORTANT]
> The agent reads only supplied case content. It doesn't make consequential
> decisions, update systems, or replace an authorized reviewer.

In this sample the agent doesn't connect to a system of record. It treats all
case content as untrusted data. Read
[`instructions.md`](instructions.md) for the complete behavioral boundary and
[`example-request.md`](example-request.md) for a fictional request.

Customer-system integration and production deployment need separate scoping and
agreement, as the [hosted-agents guide](../README.md) explains.

## Deployment

Instructions come from [`instructions.md`](instructions.md) through the existing
deployment process. Local edits don't update a deployed agent. Publish and
validate a new version, including separate live model checks.

Follow the [hosted-agent deployment guide](../README.md), select this directory,
and run:

```powershell
python deploy.py
```

## Optional policy guidance lookup

`deploy.py` can add a read-only `search_policy_guidance` tool that looks up
fictional guidance in an approved Azure AI Search index. It's controlled by
`KNOWLEDGE_RETRIEVAL_ENABLED`, which is **off by default**. With the flag unset
or `false`, the published agent is unchanged: no tools, the same instructions,
and the same dependencies. A sample guidance set and an
[index script](../knowledge_index.py) are included. On 2026-10-01 a small pilot
ran in the dev environment: ten fictional passages in one index, and this agent
at version 8 with the lookup on. On 2026-10-03 it was republished as version 10
with strict query matching. It's a pilot, not a finished evaluation, and some
live cases haven't run. Read the
[knowledge retrieval design](../../docs/knowledge-retrieval.md) for the pilot
record, identity, networking, the extra
[`requirements-knowledge.txt`](requirements-knowledge.txt) dependency, and
operator rollout steps before enabling it.

## Related content

- [Hosted agents](../README.md)
- [Checklist and case helper](../review-coordinator-agent/README.md)
- [Checklist reviewer](../application-review-agent/README.md)
- [Evaluations](../../evaluations/README.md)

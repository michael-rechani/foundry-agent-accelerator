# Basic Responses agent

[Home](../../README.md) / [Hosted agents](../README.md) / Basic Responses agent

Use the Basic Responses agent as the smallest working hosted agent: one model,
no tools, and the Responses protocol. It is a starting point for learning the
publish flow and for building your own agent. It is published in Microsoft
Foundry as `basic-responses-agent` and isn't listed in the Lab.

## At a glance

| Field | Details |
| --- | --- |
| Lab display name | Not listed in the Lab |
| Foundry agent name | `basic-responses-agent` (default) |
| What it does | Answers general questions concisely and says when it is uncertain. |
| Key files | [`main.py`](main.py), [`deploy.py`](deploy.py), [`instructions.md`](instructions.md), [`example-request.md`](example-request.md) |

## What the agent does

The agent runs the Microsoft Agent Framework behind a Responses host server. It
has no tools, no knowledge sources, and no connection to other agents. It
answers from the model and the supplied conversation only, and it tells you when
it is unsure. It is a general-purpose demonstration, not a domain assistant, and
it makes no decisions about people or cases.

Try the request in [`example-request.md`](example-request.md) to confirm a
published version responds.

## Configuration

`main.py` reads these environment variables. The deployment process sets them for
a published agent.

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `FOUNDRY_PROJECT_ENDPOINT` | Yes | None | Foundry project endpoint. |
| `FOUNDRY_MODEL_NAME` | Yes | None | Model deployment name. |
| `AGENT_NAME` | No | `basic-responses-agent` | Name reported by the agent. |
| `AGENT_INSTRUCTIONS` | No | Contents of [`instructions.md`](instructions.md) | Replaces the default instructions. |
| `AGENT_STORE_RESPONSES` | No | `false` | Set to `true` to store responses. |

## Deployment

Instructions come from [`instructions.md`](instructions.md) through the existing
deployment process, so `main.py` and `deploy.py` use the same text. Local edits
do not update a deployed agent. Publish and validate a new version, including a
separate live model check.

Follow the [hosted-agent deployment guide](../README.md), select this directory,
and run:

```powershell
python deploy.py
```

## Related content

- [Hosted agents](../README.md)
- [Case notes summarizer](../case-review-agent/README.md)
- [Checklist reviewer](../application-review-agent/README.md)
- [Checklist and case helper](../review-coordinator-agent/README.md)
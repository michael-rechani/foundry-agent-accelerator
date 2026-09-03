# Application review agent

This Responses-protocol sample compares supplied application material with
explicitly supplied criteria and produces a cited criteria matrix, evidence
gaps, and clarification questions. It can demonstrate grant, permit, provider,
admissions, procurement, partner, or marketplace intake workflows.

The agent does not connect to a system of record in this sample. It treats
application content as untrusted data and does not score, rank, approve, deny,
or recommend an outcome. Read [`instructions.md`](instructions.md) for the
complete behavioral boundary and [`example-request.md`](example-request.md)
for a synthetic request.

Follow the [hosted-agent deployment guide](../README.md), select this directory,
and run:

```powershell
python deploy.py
```
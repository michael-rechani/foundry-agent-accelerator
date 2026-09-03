# Case review agent

This Responses-protocol sample organizes supplied case material into a cited
summary, evidence list, gaps, applicable supplied policy, and staff questions.
It is suitable for synthetic demonstrations of revenue, benefits, student
services, constituent, or customer-account review.

The agent does not connect to a system of record in this sample. It treats all
case content as untrusted data and does not make consequential decisions. Read
[`instructions.md`](instructions.md) for the complete behavioral boundary and
[`example-request.md`](example-request.md) for a synthetic request.

Follow the [hosted-agent deployment guide](../README.md), select this directory,
and run:

```powershell
python deploy.py
```
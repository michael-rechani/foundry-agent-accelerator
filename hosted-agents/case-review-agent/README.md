# Casework assistance

This Responses-protocol sample organizes supplied case material into a cited
summary, evidence list, gaps, applicable supplied policy, and staff questions.
It supports synthetic casework demonstrations for authorized staff.
**Available** describes this source implementation, not a live quality pass.

Use the [repeatable demo](../../docs/demos.md#casework-assistance) for complete
synthetic inputs, expected findings, a failure case, and reset instructions.

The agent does not connect to a system of record in this sample. It treats all
case content as untrusted data and does not make consequential decisions. Read
[`instructions.md`](instructions.md) for the complete behavioral boundary and
[`example-request.md`](example-request.md) for a synthetic request.

Engagements focus on demonstration and technical validation. Integration with customer systems and production deployment require separate scoping and agreement.

Follow the [hosted-agent deployment guide](../README.md), select this directory,
and run:

```powershell
python deploy.py
```
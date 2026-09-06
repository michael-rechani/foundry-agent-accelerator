# Review coordinator

[Agent guide](../README.md) / Review coordinator

Routes supplied material to the application or case specialist, preserves
source identifiers and uncertainty, and returns findings for human review.
It does not approve, deny, rank, or replace a specialist with a fabricated result.

| Request | Tool | Default hosted agent |
| --- | --- | --- |
| Application against supplied criteria | `review_application` | `application-review-agent` |
| Case timeline or conflicting records | `review_case` | `case-review-agent` |
| Ambiguous review type | Clarifying question | No call yet |

## Try the scenario

1. Follow the [private deployment runbook](../../docs/private-deployment.md).
2. Deploy the specialists before the coordinator; inventory before redeploying.
3. Submit either [synthetic request](example-request.md) to the coordinator's
   Foundry Responses endpoint from a network-connected client.
4. Check source references and inspect structured tool output. Naming a
   specialist in the answer alone is not evidence of delegation.

### Illustrative application result

This is an expected result shape, **not captured live output**. Wording can vary.

| Criterion | Finding | Evidence |
| --- | --- | --- |
| CRIT-1: provide a budget | Budget is not evidenced in the supplied material | APP-1 describes activities but supplies no budget |

Clarification: request the missing budget. Do not infer approval, denial, or
eligibility from this gap.

A verified execution requires a `function_call` named `review_application` and
a `function_call_output` with the same `call_id`. The tool emits a JSON success
receipt only after a completed, nonempty specialist response. Both application
and case paths are mandatory deployment checks; an empty general smoke prompt
does not skip them.

## Customer profiles

Use `deploy.py --profile PATH --validate-profile` to validate an operator-managed
profile offline, then omit `--validate-profile` to deploy it from the private
runner. Profiles replace the default tools and instructions and require a smoke
test for every tool, including verification of the expected target agent.

See [platform boundaries and swap lifecycle](../../docs/agent-profiles.md) and the
[example profile](profiles/evidence-review.example.json). A profile does not
deploy its specialists, grant permissions, or isolate customer data.

## Runtime controls

| Environment variable | Default | Meaning |
| --- | --- | --- |
| `FOUNDRY_PROJECT_ENDPOINT` | Required | Private Foundry project URL |
| `FOUNDRY_MODEL_NAME` | Required | Model deployment name |
| `APPLICATION_REVIEW_AGENT_NAME` | `application-review-agent` | Named application specialist |
| `CASE_REVIEW_AGENT_NAME` | `case-review-agent` | Named case specialist |
| `SPECIALIST_CONFIG` | Default two review tools | Validated JSON specialist registry; set by profile deployment, overrides legacy name settings |
| `SPECIALIST_TIMEOUT_SECONDS` | `90` | Deadline includes waiting for a slot |
| `SPECIALIST_MAX_CONCURRENCY` | `4` | Shared in-flight limit per process |

The shared deployer sets project/model values and the default runtime behavior.
Profiles configure specialist names, descriptions, and tool names; runtime limits
still require a reviewed deployment-definition change. Cancellation releases
local resources but cannot guarantee remote execution stops.

Read [instructions.md](instructions.md) for routing and evidence boundaries.
For tests, rollback behavior, and pinned dependencies, use the
[shared guide](../README.md).
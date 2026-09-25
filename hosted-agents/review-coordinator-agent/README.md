# Application and case helper

[Home](../../README.md) / [Hosted agents](../README.md) / Application and case helper

Use the Application and case helper to route supplied review material to the
application or case specialist. The coordinator returns specialist findings for
human review; it does not approve, deny, rank, or fabricate a specialist result.
The default profile is published in Microsoft Foundry as
`customer-review-coordinator`; the base runtime is published as
`review-coordinator-agent`.

## At a glance

| Field | Details |
| --- | --- |
| Lab display name | **Application and case helper** by default; **Application and case helper (base setup)** for the base runtime. |
| Lab catalog ID | `customer-review` by default; `review-coordinator` for the base runtime. |
| Foundry agent name | `customer-review-coordinator` for the example profile; `review-coordinator-agent` for the base runtime. |
| What it does | Selects the application or case specialist, forwards the complete request, and returns the specialist findings. |
| Key files | [`main.py`](main.py), [`deploy.py`](deploy.py), [`configuration.py`](configuration.py), [`instructions.md`](instructions.md), [`profiles/evidence-review.example.json`](profiles/evidence-review.example.json), [`example-request.md`](example-request.md) |

## How the coordinator behaves

The base runtime appears in the Lab as **Application and case helper (base
setup)**. The default visible **Application and case helper** uses the
[example profile](profiles/evidence-review.example.json) and the
`customer-review-coordinator` Foundry agent name. The profile binds
`inspect_application` and `inspect_case` to the same specialists that the base
runtime reaches through `review_application` and `review_case`.

Both Lab entries can ask what input is needed or run an application or case
review. Select one scenario, not every review type. Routing to review
specialists is not business-request triage. There are no ticket, notification,
external-action, or simulated human-approval tools here.

Give the coordinator an application and checklist, or case notes with any
relevant rules. It picks the matching specialist so the application checker can
build a checklist table or the case agent can summarize notes. The coordinator
uses both specialists only when requested, and returns their findings, document
references, and follow-up questions. Chat uses these preconfigured agents; it
cannot create or configure one.

Ordinary Chat returns prose. For **Document reviews**, the caller supplies a
structured JSON result schema. The coordinator forwards that schema with all
checklist items and document text, then returns that format. Saving and
re-running reviews is the Lab's workflow, not extra coordinator memory or a
business action.

| Request | Tool | Default hosted agent |
| --- | --- | --- |
| Application against supplied criteria | `review_application` | `application-review-agent` |
| Request for proposal (RFP) requirements against supplied product evidence (**Preview**) | `review_application` | `application-review-agent` |
| Case timeline or conflicting records | `review_case` | `case-review-agent` |
| Ambiguous review type | Clarifying question | No call yet |

## Try the scenario

1. Follow the [private deployment runbook](../../docs/private-deployment.md).
2. Deploy the specialists before the coordinator; inventory before redeploying.
3. Submit either [example request](example-request.md) to the coordinator's
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

A verified execution requires a `function_call` named `review_application` and a
`function_call_output` with the same `call_id`. The tool emits a JSON success
receipt only after a completed, nonempty specialist response. Both application
and case paths are mandatory deployment checks. An empty general smoke prompt
does not skip them.

## Customer profiles

Use `deploy.py --profile PATH --validate-profile` to validate an operator-managed
profile offline. Then omit `--validate-profile` to deploy it from the private
runner. Profiles replace the default tools and instructions and require a smoke
test for every tool, including verification of the expected target agent.

See [platform boundaries and swap lifecycle](../../docs/agent-profiles.md) and
the [example profile](profiles/evidence-review.example.json). A profile does not
deploy its specialists, grant permissions, or isolate customer data.

## Runtime controls

| Environment variable | Default | Meaning |
| --- | --- | --- |
| `FOUNDRY_PROJECT_ENDPOINT` | Required | Private Foundry project URL. |
| `FOUNDRY_MODEL_NAME` | Required | Model deployment name. |
| `APPLICATION_REVIEW_AGENT_NAME` | `application-review-agent` | Named application specialist. |
| `CASE_REVIEW_AGENT_NAME` | `case-review-agent` | Named case specialist. |
| `SPECIALIST_CONFIG` | Default two review tools | Validated JSON specialist registry; set by profile deployment, overrides legacy name settings. |
| `SPECIALIST_TIMEOUT_SECONDS` | `90` | Deadline includes waiting for a slot. |
| `SPECIALIST_MAX_CONCURRENCY` | `4` | Shared in-flight limit per process. |

The shared deployer sets project and model values and the default runtime
behavior. Profiles configure specialist names, descriptions, and tool names.
Runtime limits still require a reviewed deployment-definition change.
Cancellation releases local resources but cannot guarantee remote execution
stops.

Read [instructions.md](instructions.md) for routing and evidence boundaries. For
tests, rollback behavior, and pinned dependencies, use the
[shared guide](../README.md).

## Related content

- [Hosted agents](../README.md)
- [Application checker](../application-review-agent/README.md)
- [Case notes summarizer](../case-review-agent/README.md)
- [Coordinator profiles](../../docs/agent-profiles.md)
- [Evaluations](../../evaluations/README.md)

# Checklist and case helper

[Home](../../README.md) / [Hosted agents](../README.md) / Checklist and case helper

The Checklist and case helper routes supplied review material to the application
or case specialist. The coordinator returns specialist findings for human
review. It doesn't approve, deny, rank, or fabricate a specialist result. The
default profile is published in Microsoft Foundry as
`customer-review-coordinator`, and the base runtime is published as
`review-coordinator-agent`.

## At a glance

| Field | Details |
| --- | --- |
| Lab display name | **Checklist and case helper** by default; **Checklist and case helper (base setup)** for the base runtime. |
| Lab catalog ID | `customer-review` by default; `review-coordinator` for the base runtime. |
| Foundry agent name | `customer-review-coordinator` for the example profile; `review-coordinator-agent` for the base runtime. |
| What it does | Selects the application or case specialist, forwards the complete request, and returns the specialist findings. |
| Key files | [`main.py`](main.py), [`deploy.py`](deploy.py), [`configuration.py`](configuration.py), [`instructions.md`](instructions.md), [`profiles/evidence-review.example.json`](profiles/evidence-review.example.json), [`example-request.md`](example-request.md) |

## How the coordinator behaves

The base runtime appears in the Lab as **Checklist and case helper (base
setup)**. The default visible **Checklist and case helper** uses the
[example profile](profiles/evidence-review.example.json) and the
`customer-review-coordinator` Foundry agent name. The profile binds
`inspect_application` and `inspect_case` to the same specialists that the base
runtime reaches through `review_application` and `review_case`.

Both Lab entries can ask what input is needed or run an application or case
review. Select one scenario, not every review type. Routing to review
specialists isn't business-request triage. There are no ticket, notification,
external-action, or simulated human-approval tools here.

Give the coordinator an application and checklist, or case notes with any
relevant rules. It picks the matching specialist, so the checklist reviewer can
build a checklist table or the case agent can summarize notes. It uses both
specialists only when you ask, and it returns their findings, document
references, and follow-up questions. Chat uses these preconfigured agents. It
can't create or configure one.

Ordinary Chat returns prose. For **Document reviews**, the caller supplies a
structured JSON result schema. The coordinator forwards that schema with all
checklist items and document text, then returns that format. Saving and
re-running reviews is the Lab's workflow, not extra coordinator memory or a
business action.

The coordinator is a routing and presentation layer, not a second reviewer.
Runtime middleware replaces model-written tool request arguments with the
original user messages in order, excluding generated assistant history. The
specialist therefore receives the source wording, not a routing-model paraphrase.
After its tools finish, runtime middleware checks the correlated call IDs,
configured tool/agent bindings and successful receipts. It then returns the full
specialist text without another model call, so tables, calculations and
questions remain unchanged. A single JSON result is returned without a label or
wrapper, and ordinary Chat adds only the specialist label. Multiple prose
results stay separate. Multiple structured results fail rather than inventing a
merged schema. Invalid or failed receipts produce an error, not a substitute
review. The example profile and base instructions are checked for behavioral
parity, allowing only their different tool names.

When the task is already known, use a directly enabled specialist. The optional
coordinator helps when one entry point must handle both application and case
requests. It adds model work and another opportunity to alter findings. The
runtime no longer asks the model to rewrite successful specialist output.
Initial tool selection is still model-generated, so there's no guarantee of
deterministic routing or a first-batch call count. Live acceptance must check
the selected tool, the unchanged forwarded evidence, and whether the findings
are useful. Text equality alone isn't enough. A direct specialist also avoids the
coordinator's initial routing inference, though no fixed latency improvement is
promised.

| Request | Tool | Default hosted agent |
| --- | --- | --- |
| Application against supplied criteria | `review_application` | `application-review-agent` |
| Request for proposal (RFP) requirements against supplied product evidence (**Preview**) | `review_application` | `application-review-agent` |
| Case timeline or conflicting records | `review_case` | `case-review-agent` |
| Ambiguous review type | Clarifying question | No call yet |
| Help with what to paste or what the agent can do | Input guidance | No specialist call |

## Try the scenario

1. Follow the [private deployment runbook](../../docs/private-deployment.md).
2. Deploy the specialists before the coordinator, and inventory before
   redeploying.
3. Submit either [example request](example-request.md) to the coordinator's
   Foundry Responses endpoint from a network-connected client.
4. Check source references and inspect structured tool output. Naming a
   specialist in the answer isn't evidence of delegation.

### Illustrative application result

This is an expected result shape, **not captured live output**. Wording can vary.

| Criterion | Finding | Evidence |
| --- | --- | --- |
| CRIT-1: provide a budget | Budget is not evidenced in the supplied material | APP-1 describes activities but supplies no budget |

Clarification: request the missing budget. Don't infer approval, denial, or
eligibility from this gap.

A verified execution requires a `function_call` named `review_application` and a
`function_call_output` with the same `call_id`. The tool emits a JSON success
receipt only after a completed, nonempty specialist response. Both application
and case paths are mandatory deployment checks. An empty general smoke prompt
doesn't skip them.

## Customer profiles

Use `deploy.py --profile PATH --validate-profile` to validate an operator-managed
profile offline. Then omit `--validate-profile` to deploy it from the private
runner. Profiles replace the default tools and instructions and require a smoke
test for every tool, including verification of the expected target agent.

See [platform boundaries and swap lifecycle](../../docs/agent-profiles.md) and
the [example profile](profiles/evidence-review.example.json). A profile doesn't
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
| `SPECIALIST_SESSION_REUSE_SECONDS` | `600` | How long a completed specialist session is reused, from 0 to 3600 seconds. `0` turns reuse off. |

The shared deployer sets project and model values and the default runtime
behavior. Profiles configure specialist names, descriptions, and tool names.
Changing runtime limits still requires a reviewed deployment-definition change.
Cancellation releases local resources but can't guarantee remote execution
stops.

Read [instructions.md](instructions.md) for routing and evidence boundaries. For
tests, rollback behavior, and pinned dependencies, use the
[shared guide](../README.md).

## Related content

- [Hosted agents](../README.md)
- [Checklist reviewer](../application-review-agent/README.md)
- [Case notes summarizer](../case-review-agent/README.md)
- [Coordinator profiles](../../docs/agent-profiles.md)
- [Evaluations](../../evaluations/README.md)

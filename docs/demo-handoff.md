# Demonstration and technical-validation handoff

[Home](../README.md) / [Docs](README.md) / [Demo guide](demos.md) / Handoff

Record one scenario from the demo guide here. Fill it in with observed evidence,
remaining validation work, and the next owner. It isn't a customer
implementation claim, a deployment approval, or a commercial proposal.

## Before you record

> [!CAUTION]
> Keep customer names, MSX details, commercial information, credentials, and
> customer records out of this repository and its sample reports. Complete the
> handoff in an approved reporting location, and don't commit live trace exports
> or evaluation artifacts that contain sensitive data.

Engagements focus on demonstration and technical validation. Integration with
customer systems and production deployment require separate scoping and agreement.

Customers don't open the Lab themselves today. An operator presents it from the
jump box. See [Present from the jump box](showcase.md#present-from-the-jump-box).

## Run context

| Field | Fill in |
| --- | --- |
| Scenario and source status | Selected creation template or existing casework / application / preview proposal review |
| Validation mode | Offline illustration, offline automated tests, or approved live Microsoft Foundry run |
| Inputs and versions | Synthetic fixture path, dataset version/hash, source revision, prompt version/hash |
| Runtime | Agent names and routed versions, model/deployment names and model versions; mark unknown fields as unavailable |
| Creation, if used | Template ID, saved setup and actual publication stages; distinguish a draft from a created runtime and a ready route from a quality-tested answer |
| Conditions | Date, region, relevant settings, number of repeated runs, and approved configuration differences |
| Evidence | Test output, native Foundry evaluation/run IDs, and approved trace references if actually collected |

## What worked

State the observed finding and supporting evidence, including failures or
variability across repeated runs. "The demo ran" isn't a finding.

| Check | Record |
| --- | --- |
| Supported finding |  |
| Evidence or source IDs checked |  |
| Failures or variability retained |  |
| Specialist receipt, if applicable |  |
| Citation review status | Manually checked, exact-source validated by the structured review path, or not checked |

Illustrative examples, **not measured results from this repository change**:

- The application output identified an absent budget without denying a permit.
- The case summary retained both conflicting intake dates and asked a useful
  follow-up question.
- The proposal matrix distinguished a product claim from supplied protocol
  evidence, and did not recommend a vendor.
- The workflow template returned visibly simulated lookup data and proposed
  steps without claiming a ticket, approval or external integration ran.

A verified specialist receipt proves the checked delegation. It doesn't prove the
resulting judgment is correct.

## What needs further validation

Check every incomplete or failed area that applies.

- [ ] Live Foundry evaluation and project-linked tracing, if only offline
  validation ran. Offline mocks don't establish model behavior, cloud
  connectivity, or role-based access control (RBAC).
- [ ] Missing-evidence handling, citation invention, wrong specialist routing,
  prompt injection, and prohibited decisions/actions on the versioned dataset.
- [ ] Scenario-specific quality and repeated-run variability, especially
  preview proposal coverage.
- [ ] Model/deployment availability, context bounds, latency under intended
  load, and the pinned software development kit (SDK)/private-network
  combination.
- [ ] User authorization, isolation, retention, resiliency, and operational
  ownership before any confidential data or production use. Shared Lab history
  isn't a per-user data boundary.

For optional candidate comparison, record each candidate against the **same**
dataset and rubric. Use the [evaluation guide](../evaluations/README.md) instead of
a new Lab quality dashboard.

| Candidate record | Meaning and reporting rule |
| --- | --- |
| Agent/model/deployment and prompt versions | Include actual version identifiers or mark them unavailable. A mutable deployment name alone isn't enough. |
| Quality results | Native evaluation outcomes plus reviewed failures and acceptance criteria. Response time isn't quality. |
| Response time | Observed end-to-end measurement, with scope, sample count, and failed/timed-out attempts retained. |
| Token usage | Actual reported input/output tokens and coverage. Coordinator-only usage isn't a multi-agent total. Unknown isn't zero. |
| Estimated cost | Dated rates times reported usage, or labeled assumptions. It isn't measured spend. |
| Allocated platform cost | Period and denominator, including applicable shared capacity and retained runtime. It isn't marginal per-call token cost. |

## Recommended next step

Choose one evidence-based next step. Add an owner and an agreed validation goal.

| Select | Next step | Owner | Validation goal |
| --- | --- | --- | --- |
| [ ] | Repeat or improve the selected synthetic scenario against the same evaluation set when quality or safety checks failed. |  |  |
| [ ] | Compare an approved model/prompt candidate when a specific gap warrants it. |  |  |
| [ ] | Scope a separate feasibility/design activity for real data, integrations, production controls, or business-request triage. Don't imply these were built. |  |  |
| [ ] | Stop or reconsider the approach if it does not address the selected need. |  |  |

Sample code, setup guidance, and architecture/cost recommendations depend on
scope. No next step here amounts to an integration agreement, production
approval, funding, or an officially approved Microsoft service offering.

## Closeout

Finish by recording the [reset performed](demos.md#reset-without-hiding-failures),
retained synthetic records, and unresolved interrupted calls. Don't hide failures
or delete unrelated shared records to make the handoff look successful.

| Closeout item | Record |
| --- | --- |
| Reset performed |  |
| Retained synthetic records |  |
| Unresolved interrupted calls |  |
| Records intentionally deleted, if agreed |  |
| Unresolved questions |  |

## Related content

- [Demo guide](demos.md)
- [Create and try a baseline agent](agent-creation.md)
- [The Lab](../workbench/README.md)
- [Evaluations](../evaluations/README.md)

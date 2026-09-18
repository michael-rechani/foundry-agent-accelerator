# Demonstration and technical-validation handoff

[Overview](../README.md) / [Demo guide](demos.md) / Handoff

Use this structure for **one selected scenario**. Record observed results, not a
customer implementation claim, an approval to deploy, or a commercial proposal.
Keep customer names, opportunity/MSX details, commercial information, credentials,
and customer records out of this repository and its sample reports.

Engagements focus on demonstration and technical validation. Integration with customer systems and production deployment require separate scoping and agreement.

## Run context

Complete the following in an approved reporting location. Do not commit live
trace exports or evaluation artifacts containing sensitive data.

| Field | Record |
| --- | --- |
| Scenario and source status | Casework / application / experimental proposal; triage is planned, not a completed demo |
| Validation mode | Offline illustration, offline automated tests, or approved live Foundry run |
| Inputs and versions | Synthetic fixture path, dataset version/hash, source revision, prompt version/hash |
| Runtime | Agent names and routed versions, model/deployment names and model versions; unknown fields explicitly unavailable |
| Conditions | Date, region, relevant settings, number of repeated runs, and approved configuration differences |
| Evidence | Test output, native Foundry evaluation/run IDs, and approved trace references if actually collected |

## What worked

State the observed finding and supporting evidence, including failures or
variability across repeated runs. Do not replace this with "the demo ran."

Illustrative examples, **not measured results from this repository change**:

- The application output identified an absent budget without denying a permit.
- The case summary retained both conflicting intake dates and asked a useful
  follow-up question.
- The proposal matrix distinguished a product claim from supplied protocol
  evidence, and did not recommend a vendor.

Report whether citations were checked manually, validated as exact source quotes
by the structured review path, or not checked. A verified specialist receipt
proves the checked delegation, not the correctness of the resulting judgment.

## What needs further validation

Be explicit about incomplete or failed checks:

- Live Foundry evaluation and project-linked tracing, if only offline validation
  ran; offline mocks do not establish model behavior, cloud connectivity, or RBAC.
- Missing-evidence handling, citation invention, wrong specialist routing,
  prompt injection, and prohibited decisions/actions on the versioned dataset.
- Scenario-specific quality and repeated-run variability, especially experimental
  proposal coverage. Business-request triage is not implemented.
- Model/deployment availability, context bounds, latency under intended load, and
  the pinned SDK/private-network combination.
- User authorization, isolation, retention, resiliency, and operational ownership
  before any confidential data or production use. Shared Lab history is not a
  per-user data boundary.

For optional candidate comparison, record each candidate against the **same**
dataset and rubric. Use the [evaluation guide](../evaluations/README.md) rather
than a new Lab quality dashboard.

| Candidate record | Meaning and reporting rule |
| --- | --- |
| Agent/model/deployment and prompt versions | Include actual version identifiers or explicit unavailable values; a mutable deployment name alone is insufficient. |
| Quality results | Native evaluation outcomes plus reviewed failures and acceptance criteria; response time is not quality. |
| Response time | Observed end-to-end measurement, with scope, sample count, and failed/timed-out attempts retained. |
| Token usage | Actual reported input/output tokens and coverage; coordinator-only usage is not a multi-agent total. Unknown is not zero. |
| Estimated cost | Dated rates times reported usage or explicitly labeled assumptions; not measured spend. |
| Allocated platform cost | Period and denominator, including applicable shared capacity and retained runtime; not marginal per-call token cost. |

## Recommended next step

Choose an evidence-based next step, with an owner and an agreed validation goal:

- Repeat or improve the selected synthetic scenario against the same evaluation
  set when quality or safety checks failed.
- Compare an approved model/prompt candidate when a specific gap warrants it.
- Scope a separate feasibility/design activity for real data, integrations,
  production controls, or business-request triage; do not imply these were built.
- Stop or reconsider the approach if it does not address the selected need.

Sample code, setup guidance, and architecture/cost recommendations remain
scope-dependent. No next step here constitutes integration agreement, production
approval, funding, or an officially approved Microsoft service offering.

Finish by recording the [reset performed](demos.md#reset-without-hiding-failures),
retained synthetic records, and unresolved interrupted calls. Do not hide failures
or delete unrelated shared records to make the handoff look successful.

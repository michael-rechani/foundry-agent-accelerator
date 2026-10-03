# Evaluation SDK contract, candidate comparison, and tracing

[Home](../README.md) / [Docs](README.md) / [Evaluations](../evaluations/README.md) / SDK contract, comparison, and tracing

This page is part of the [evaluation guide](../evaluations/README.md). It records
what the offline SDK tests do and don't establish, how to compare candidates and
review results, and how tracing and content authorization relate to an
evaluation run.

## In this guide

- [SDK contract evidence, not service assumptions](#sdk-contract-evidence-not-service-assumptions)
- [Optional candidate comparison and human review](#optional-candidate-comparison-and-human-review)
- [Tracing and content authorization](#tracing-and-content-authorization)

## SDK contract evidence, not service assumptions

[The offline SDK transport tests](../evaluations/test_sdk_contract.py) exercise the pinned
Projects 2.6.1 and OpenAI 3.19.2 clients with synthetic HTTP responses. They
check native evaluator serialization, inline evaluation/run requests, paginated
results, inventory deserialization, and receipt metadata. In particular:

- Agent endpoint version selectors, hosted definition environment/protocol
  fields, and status are read through the Projects SDK's declared models.
  Model-deployment wire fields `modelName`, `modelVersion` and `modelPublisher`
  deserialize to `model_name`, `model_version` and `model_publisher`.
- Responses `usage.input_tokens`, `usage.output_tokens` and `usage.total_tokens`
  are read only when returned. The OpenAI SDK's `_request_id` comes from the
  `x-request-id` response header; it is not a guessed Azure trace ID.
- Native run `per_model_usage` entries expose wire `model_name` through the
  pinned SDK's `run_model_name` attribute. Native scores come from output-item
  results, not a locally synthesized quality field.
- Missing model metadata, response usage/request headers and native run usage
  are tested through those real SDK deserializers and remain `null`. No remote
  `prompt_version`, cost, trace-ID or complete downstream-usage field is
  assumed. Prompt versions remain explicit operator attestations.

These tests establish the local client's contract with the supplied fixtures,
not that the live service will accept every request or emit every optional
field. Actual hosted-agent behavior, preview evaluator availability,
permissions, retention, and telemetry delivery still require the approved
[live validation steps](evaluation-live-run.md#remaining-live-validation-steps).

Agent calls have a 180-second request timeout; other SDK requests have bounded
timeouts. Client retries are disabled. The one exception: if creating the
evaluation returns 404 because the just-created custom evaluator isn't visible
yet, the runner waits 5, 10, and 20 seconds between up to four attempts and
records each wait as `evaluator_not_ready`. A 404 creates nothing. The default
grading polling budget is 600 seconds, through `--timeout-seconds`, and the
maximum is 3600. This is not an end-to-end deadline, token budget, hard billing
cap, or remote cancellation guarantee.

Live Foundry grading reports each case as `completed` rather than `pass` or
`fail`, and adds a `skipped` count. The runner takes each case's outcome from
its single rubric result. It fails the run if any case is skipped or errored,
or if the rubric result didn't finish.

No remote resources are automatically deleted. Inspect the evaluator name,
evaluation ID, and run ID in the receipt and open **Evaluations** in Foundry. If
a request was accepted but its response was lost, a resource might exist without
a recorded ID; inventory before retrying. On timeout or interruption, remote
work may continue. Use the SDK's `client.evals.runs.cancel(...)` deliberately,
verify the resulting state, and follow your retention policy for deleting the
owned evaluation and custom evaluator after preserving required evidence.

## Optional candidate comparison and human review

Use the **same runner**, not a second engine. Execute the approved live command
once per already-deployed candidate, with a new receipt path and candidate label.
Change only the intended agent/model or prompt version. Do not change routes
with this runner. Any such change must first complete the separately approved
staging publication and verification described in
[Prepare an isolated evaluation environment](evaluation-live-run.md#prepare-an-isolated-evaluation-environment);
live evaluation approval
does not authorize publication. Freeze the verified candidates for the
comparison window.

The metadata records model deployment/name/version/publisher for the selected
agent, known specialists, and judge. `--prompt-version` labels the reviewed
deployed prompt revision; never use a label to imply remote verification.

For a valid comparison, hold these fixed and retain both receipts:

1. Dataset version/hash, selected case IDs/hash, profile, rubric version/hash,
   and native threshold. Do not compare the six-case application profile with
   all nine application cases, or v1 and v2 datasets.
2. Judge deployment/model/version, specialist versions unless they are the
   explicit candidate variable, project/region, runtime dependencies, tool
   bindings, and retrieval inputs. This suite supplies inline synthetic
   evidence, not a retrieval corpus, and it has no retrieval cases yet. A
   version's `KNOWLEDGE_*` retrieval settings are part of its configuration
   hash, so a change to them shows up there. Verify model versions separately
   when inventory is missing them; `null` does not establish equivalence.
3. Run conditions: sequential calls, one fresh conversation per case, no client
   retries, response storage/streaming disabled, and the same timeouts. The
   receipt records these settings. The runner does not override agent
   temperature/seed or observe server load; these remain `null`.
   `--conditions-label` is only an attestation tying both runs to a reviewed
   conditions record: capacity, concurrency, generation settings, warm/cold
   state, time window, and repetition policy. It is not measured equivalence.
4. Review per-case native scores/failures in Foundry alongside response latency
   and reported usage. Repeat under comparable conditions to investigate
   nondeterminism. One small set cannot establish significance, production
   percentiles, or a "best model". Do not replace missing telemetry with zero,
   aggregate incompatible scopes, or compare incomplete runs as passing results.

An authorized human reviewer must inspect each case's native response/rationale
and confirm exact evidence identifiers, all requirement rows, missing versus
conflicting evidence, no unsupported policy/product claims, correct tool
receipt, clarification quality, and explicit human decision/action boundaries.
Any invented evidence, wrong route, consequential decision, or claimed action
blocks demo acceptance regardless of a judge's pass. Review false positives and
false negatives and retain disagreements, missing telemetry, dataset/rubric
versions, and approved trace references in the review record. Offline tests do
not perform this review. A passing result informs a human decision; it never
authorizes promotion, procurement, case action, or production routing changes.

## Tracing and content authorization

Use **Foundry tracing and project-linked Application Insights** for
agent/model/tool diagnostics. The
[private monitoring root](../terraform/monitoring/README.md) provides that
connection; this runner adds no exporter, dashboard, content logging, sampling
changes, or Application Insights resource. The published agents disable prompt,
response, and tool-content recording, so traces show spans, timings, status, and
token counts, not the evaluated text. Use the native evaluation results for
rationales. Confirm the connection is enabled and that you have private query
access before an approved live test. No trace delivery or end-to-end correlation
is proven by these offline tests.

Use the receipt's evaluation/run IDs to locate native evaluation results and
returned response/request IDs, when available, to investigate agent requests.
These IDs are not asserted to be an Application Insights operation/trace ID.
Correlate against actual server-side traces and preserve an approved reference.
Timestamps alone are not proof of a parent-child relationship. If no trace or
identifier is emitted, record the gap; do not invent a link or infer success.

`--authorize-content-capture` authorizes the synthetic **evaluation payload
retention** necessary for native grading; it does not enable or authorize global
prompt/response capture in tracing. Additional trace-content capture needs
explicit owner/security approval of content, tenant/project, purpose, access,
region, and retention before enabling it through the existing
Foundry/Application Insights configuration. Prefer metadata-only traces,
minimize content, and use synthetic material only. `store=False` is not a
tracing or evaluation-retention opt-out. Never copy customer material,
credentials, or trace payloads into Git.

## Related content

- [Synthetic review evaluations](../evaluations/README.md)
- [Run an approved live evaluation](evaluation-live-run.md)
- [Agent monitoring](../terraform/monitoring/README.md)
- [Demo handoff](demo-handoff.md)
- [Documentation index](README.md)

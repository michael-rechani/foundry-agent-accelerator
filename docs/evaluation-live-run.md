# Run an approved live evaluation

[Home](../README.md) / [Docs](README.md) / [Evaluations](../evaluations/README.md) / Run a live evaluation

This page is part of the [evaluation guide](../evaluations/README.md). It covers
preparing an isolated staging environment, running the evaluation against
deployed agents, and what a run costs and retains. Offline validation needs none
of it; see [Offline validation](../evaluations/README.md#offline-validation).

## In this guide

- [Prepare an isolated evaluation environment](#prepare-an-isolated-evaluation-environment)
- [Run explicitly](#run-explicitly)
- [Costs, retention, and interrupted runs](#costs-retention-and-interrupted-runs)

## Prepare an isolated evaluation environment

Use a private-network runner with verified tenant, subscription, project access,
and private DNS/routing to the staging agents. Do not enable public access to
make evaluation work.

```powershell
python -m venv evaluations\.venv
if ($LASTEXITCODE -ne 0) { throw 'Evaluation environment creation failed' }
$python = Join-Path $PWD 'evaluations\.venv\Scripts\python.exe'
& $python -m pip install -r evaluations\requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Evaluation dependency installation failed' }
& $python -m pip check
if ($LASTEXITCODE -ne 0) { throw 'Evaluation dependency check failed' }
& $python -m unittest discover -s evaluations -p 'test_*.py' -v
if ($LASTEXITCODE -ne 0) { throw 'Evaluation contract tests failed' }
```

This environment pins Projects SDK **2.6.1** and OpenAI **3.19.2**, the same
versions as the deployment and Lab environments. OpenAI 3 sends requests through
`httpx2`, which checks TLS certificates against the operating-system trust store
instead of `certifi`. The hand-authored rubric
uses `project.beta.evaluators`: that API is **preview**, even though Hosted
Agents are generally available (GA). `allow_preview=True` is also needed for the
pinned SDK's named-agent OpenAI client. No generated-rubric job or new model
deployment is created.

Before live execution:

- Deploy the three samples to an isolated staging project using the existing
  [deployment procedure](../hosted-agents/README.md#deployment-walkthrough).
  Coordinator cases use `application-review-agent` and `case-review-agent`.
- Model/deployment/version changes and prompt/instruction changes require
  **separately approved staging publication before live evaluation**. Publish
  the reviewed agent instructions and configuration through the existing
  deployment procedure, and complete any approved model-deployment update.
  Verify the resulting active agent version, model version, and staging endpoint
  route before invoking this runner. Local edits, passing offline tests, and
  changes to `--prompt-version` or `--source-revision` do not deploy anything.
  The requirements/proposal instruction changes in this repository have not
  been live-deployed or validated by this evaluation work.
- Confirm the judge is an existing supported chat-completion model deployment in
  that project, with sufficient quota and evaluation-region support. Pass its
  deployment name, such as `gpt-4.1`, to `--judge-model`. Foundry grades rows
  in parallel, so give the judge enough throughput. In the private Lab, a
  capacity of 10 (10,000 tokens and 10 requests per minute) throttled 11 of 25
  rows with `429 Too Many Requests`, and the runner correctly failed each
  profile; a capacity of 50 is the working value. See
  [model capacity](../terraform/README.md#1-configure-inputs-and-state).
- Confirm Foundry permissions for reading agent/model inventory, invoking
  agents and models, and creating/reading custom evaluators and evaluation
  runs. The cloud-evaluation guide lists Foundry User at project scope; validate
  any additional permissions required by the selected preview feature.
- Confirm the Foundry project's managed identity has Foundry User at the Foundry
  resource scope. Per Microsoft Learn, evaluation runs fail without it
  ([virtual network support for evaluation](https://learn.microsoft.com/azure/foundry/concepts/evaluation-virtual-network#configure-evaluation-network-requirements)).
  The platform Terraform assigns it as
  `azurerm_role_assignment.project_foundry_user`.
- Confirm the agent storage account admits the Foundry project as a resource
  instance. Foundry's hosted asset store writes evaluation results to that
  account as the project identity, from outside the virtual network. With
  public network access disabled and no exception, creating a run fails with
  `Pending evaluation-result upload was denied (HTTP 403)`, and
  `project.datasets.pending_upload` reports
  `ResourceMsiTokenDoesntHavePermissionsOnStorage`, even though the identity
  has Blob roles. The platform Terraform adds this project-only rule to
  `resourceAccessRules` in [`keyless-storage.tf`](../terraform/keyless-storage.tf).
  It doesn't enable public access or the trusted-services bypass, and RBAC
  still applies.
- Each agent must be active, advertise Responses **2.0.0**, route 100 percent of
  traffic to a single version, explicitly set `AGENT_STORE_RESPONSES=false`, and
  use this same project's endpoint in `FOUNDRY_PROJECT_ENDPOINT`.
- Serialize deployments and model updates for the entire staging stack. The
  runner checks routes and model versions before each case and after collection
  and grading. These reads detect drift but **are not a distributed lock** and
  cannot detect a change that is made and reverted between reads.
- Obtain explicit owner approval for billable agent/judge calls and for capture
  of the synthetic queries, expected outcomes, and responses in native Foundry
  evaluation storage. Confirm region, access, retention, and budget separately.
  The two approval flags record operator attestation, not an authorization
  system.

### Remaining live validation steps

None of these steps has been performed by the offline evaluation work:

1. Review the local application, case and coordinator instructions, including
   their prohibition on executing **or claiming** external actions. Obtain
   staging-publication approval, publish new immutable agent versions containing
   the reviewed changes, complete any approved model update, and verify the
   active versions and isolated routes. Local instruction edits are not
   deployed.
2. Verify private connectivity, caller identity, project permissions, supported
   judge deployment/region and quota, response-storage settings, and evaluation
   retention. Confirm the project's Application Insights connection is still
   enabled and that you have private query access
   ([monitoring runbook](../terraform/monitoring/README.md)).
3. Obtain explicit live billing and synthetic-content-retention approval. Freeze
   staging versions and run the command below for each profile, using fresh
   receipt paths. Cover application completeness, preview
   requirements/proposal review, casework and coordinator review routing;
   business-request triage remains out of scope.
4. Inspect actual Foundry evaluator/run completion, all native case results, and
   specialist receipts. Investigate errors and unexpected SDK/service shapes. Do
   not infer missing scores, usage, versions, or traces from the offline
   fixtures. A timeout may leave remote work running and must be investigated
   before retrying.
5. Have an authorized reviewer check the full acceptance criteria and native
   rationales, verify available server-side trace correlation under the approved
   capture policy, and record gaps and disagreements. Retain actual evaluation
   IDs and approved evidence using the [demo handoff](demo-handoff.md).
   Only then consider a narrowly scoped changed-behavior claim, with its
   dataset, deployed version, and limitations. Offline tests alone authorize no
   such claim.

## Run explicitly

Replace placeholders with verified staging values. `--source-revision` is an
operator attestation of the deployed agent source, not a claim that the runner
can reconstruct remote code provenance. Choose a new report filename each time.

```powershell
& $python evaluations\run.py --run --approve-billable-run --authorize-content-capture `
  --sample application-review-agent `
  --profile application-completeness `
  --endpoint 'https://<account>.services.ai.azure.com/api/projects/<project>' `
  --agent-name application-review-agent `
  --agent-version '<routed-version>' `
  --judge-model '<judge-deployment-name>' `
  --source-revision '<full-40-character-deployed-git-revision>' `
  --candidate-label candidate-a `
  --prompt-version '<reviewed-prompt-version>' `
  --conditions-label staging-idle-v1 `
  --output evaluations\results\application-candidate.jsonl
if ($LASTEXITCODE -ne 0) { throw 'Evaluation failed; inspect the retained report and Foundry run' }
```

Repeat for `case-review-agent` and `review-coordinator-agent` with their actual
routed versions, matching profile names or omitted `--profile`, and different
report paths. For requirements/proposal coverage, keep
`--sample application-review-agent` and use
`--profile requirements-proposal-experimental`. Do not deploy a new evaluator
agent or present this as a validated business-triage workflow.

The runner inventories actual agent/specialist versions and model names,
versions, and publishers. The judge deployment is inventoried too. It invokes
named staging endpoints; it does not invoke an unrouted immutable version or
perform a production canary.

**Exit code 0** means offline validation succeeded or, with `--run`, every
selected case passed the structural and native rubric gates. It is not human
acceptance or proof of safety. **Any nonzero exit is a failed gate**, including
malformed or missing results, route changes, SDK errors, cancellations, and
polling timeouts.

The metadata-only JSONL receipt is created exclusively, flushed after each
event, and never overwrites another report. It contains dataset/rubric hashes
and versions, evaluation-client package versions, attested source/prompt
versions, selected case IDs and hash, profile, candidate/conditions labels,
model/agent inventory, case response timings, optional response/request IDs,
resource IDs, and the native normalized per-case scores and pass/fail results.
It excludes prompts, responses, judge rationales, environment-variable dumps,
and SDK error bodies. The default results directory is Git-ignored; protect
reports as operational metadata and verify your output path is excluded before
committing anything.

Prompt version is operator-attested, not remotely proven. If
`AGENT_INSTRUCTIONS` is explicitly present in the deployed environment, only its
hash is recorded; otherwise `prompt_override_sha256` is `null`, not a hash of an
assumed local default. A selected runtime-configuration hash also detects
changes to model, instruction override, specialist-binding, timeout, or
concurrency settings, and to any `KNOWLEDGE_*` retrieval settings the deployed
version has, without dumping their contents. It is not a complete
deployed-code provenance check. An omitted candidate label, prompt version, or
conditions label is `null`. Absent model/version/publisher metadata is also
`null`; mandatory agent versions and deployment names must still be verified.

## Costs, retention, and interrupted runs

> [!CAUTION]
> Live mode invokes billable agent and judge calls and submits synthetic queries,
> expected outcomes, and responses as inline evaluation data to **your configured
> Foundry project**. `store=False` applies to agent Responses calls; it does
> **not** prevent the evaluation service from retaining submitted data or judge
> results. Confirm evaluation storage, retention, access, region, networking,
> and budget before running. Use synthetic data only.

Live mode invokes one agent request per selected case sequentially, plus
specialist/model calls for coordinator cases.

| Receipt field | Meaning and limits |
| --- | --- |
| `response_received.response_time_seconds` | Measured client request round-trip, including hosted processing and any downstream work waited on. Not model-only latency, token throughput, or full evaluation duration. Retained even if subsequent structural checks fail. |
| `response_received.token_usage` | Only the response's reported input/output/total counts; each absent count is `null`, never estimated from text. A returned coordinator count is **not verified to include all specialist/model calls**. No count is invented by subtraction. |
| `evaluation_completed.native_results` | Native rubric name, normalized score and pass/fail for each case; rationales remain in Foundry. Scores are not converted to an invented quality percentage. |
| `evaluation_completed.native_evaluation_usage` | The completed native run's `per_model_usage`, when returned, including model, prompt/completion/total/cache counts and invocation count. Absent list or fields are `null`; an explicitly returned empty list remains empty and does not prove zero cost. Separate from agent collection, not a full stack total. |
| `estimated_cost` | Always `null` in this runner. A separate estimate would require complete usage, pricing currency/date, deployment/model tier, cache treatment and judge/specialist coverage; tokens alone are not a bill. |
| `allocated_platform_cost` | Always `null` in this runner. Hosted compute, minimum replicas, networking, storage and monitoring are shared/time-based costs requiring an explicit allocation basis, not observed per-request token cost. |

Partial telemetry may still accompany a valid quality result; it cannot support
an end-to-end usage or cost claim. Malformed returned counts fail explicitly.
Timeouts before a response cannot provide response usage or completion timing.

## Related content

- [Synthetic review evaluations](../evaluations/README.md)
- [Evaluation test cases and acceptance](evaluation-test-cases.md)
- [Evaluation SDK contract, candidate comparison, and tracing](evaluation-sdk-comparison-tracing.md)
- [Demo handoff](demo-handoff.md)
- [Agent monitoring](../terraform/monitoring/README.md)
- [Documentation index](README.md)

# Hosted-agent samples

[Home](../README.md) / Hosted agents

Use these samples to publish and validate the repository's prebuilt agents in
Microsoft Foundry. This guide is for developers and operators who publish
hosted-agent versions, test routes, and recover safely when a promotion fails.

Engagements focus on demonstration and technical validation. Integration with
customer systems and production deployment require separate scoping and
agreement.

## At a glance

| Item | Details |
| --- | --- |
| What you publish | Prebuilt agents from `hosted-agents/` as immutable hosted-agent versions. |
| Where they run | Foundry Agent Service, in per-session VM-isolated sandboxes. |
| Foundry project | `hosted-agents-dev` is a Foundry project name, not an agent name. |
| Primary roles | Developers change agent code and publish versions. Operators confirm Azure resources, permissions, and private access. |
| Main dependencies | `FOUNDRY_PROJECT_ENDPOINT`, `FOUNDRY_MODEL_NAME`, `DefaultAzureCredential`, and a routed model deployment. |

Hosted agents run custom containerized code in per-session, VM-isolated
sandboxes managed by Foundry Agent Service. Foundry manages the endpoint, agent
identity, scaling, session storage, observability, and version lifecycle.

## In this guide

- [Included samples](#included-samples)
- [Scope and safety boundaries](#scope-and-safety-boundaries)
- [Coordinator delegation pattern](#coordinator-delegation-pattern)
- [Deployment walkthrough](#deployment-walkthrough)
- [What publication does](#what-publication-does)
- [Portable agent bundles](#portable-agent-bundles)
- [Test and validate](#test-and-validate)
- [Roll back and recover](#roll-back-and-recover)
- [Troubleshooting](#troubleshooting)
- [Scenario selection and optional extensions](#scenario-selection-and-optional-extensions)
- [Operational checklist](#operational-checklist)
- [Related content](#related-content)

## Included samples

| Sample | Purpose | Decision boundary |
| --- | --- | --- |
| [`basic-responses-agent/`](basic-responses-agent/) | Minimal Microsoft Agent Framework and Responses protocol baseline. | General-purpose demonstration only. |
| [`case-review-agent/`](case-review-agent/) | Casework assistance, **Available**: cited summaries, missing or conflicting evidence, and staff questions. | Does not determine eligibility, liability, enforcement, or clinical status. |
| [`application-review-agent/`](application-review-agent/) | Application completeness, **Available**; requirements and proposal review, **Preview**: compare supplied material with explicit criteria. | Missing evidence is not automatic noncompliance. Does not score, rank, approve, deny, or recommend an outcome. |
| [`review-coordinator-agent/`](review-coordinator-agent/) | Route review requests to the application or case specialist. | Does not replace specialist review or make consequential decisions. |

> [!NOTE]
> **Available** means the code and walkthrough are included. It doesn't mean an
> environment is deployed or that answers were validated. The review coordinator
> routes reviews only; it doesn't triage business requests.

No additional agent or infrastructure stack is needed for the preview
proposal workflow. The coordinator is an optional review-delegation pattern, not
a generic agent framework or a simulated business-approval system.

## Scope and safety boundaries

All samples use `DefaultAzureCredential`; no credentials are embedded in the
image or passed as environment variables. The two review samples operate only on
context supplied in the conversation. The primary demo uses fictional data only,
with no customer-system, Microsoft 365/Copilot/SharePoint connections or
external business actions.

Optional integrations require separate review and agreement. Profiles are not
customer isolation boundaries. Grant the generated agent identity explicit
least-privilege role-based access control (RBAC) roles for any additional Azure
service it must access.

The generated agent identity can invoke project models and use session storage
by default.

The deploying identity needs permission to create versions and update endpoint
routing at project scope. Microsoft Learn's
[deployment guide](https://learn.microsoft.com/azure/foundry/agents/how-to/deploy-hosted-agent#required-permissions)
asks for Foundry Project Manager, so this walkthrough does too. Learn's pages
disagree on whether Foundry User is enough, and this repository hasn't tested
it. See
[Foundry User and Foundry Project Manager](../docs/permissions.md#foundry-user-and-foundry-project-manager).

## Coordinator delegation pattern

The review coordinator calls the two specialist hosted-agent endpoints through
the Foundry project using its managed identity. The coordinator selects one
specialist by default, forwards the complete request, and returns the
specialist's findings. Deploy both specialist agents before deploying the
coordinator.

Keep the three responsibilities distinct:

| Agent | Useful task and required input | Result a person can use | Capability boundary |
| --- | --- | --- | --- |
| Checklist reviewer | Compare supplied application or proposal text with an explicit checklist. Ask for either if missing. | One cited row per item, budget calculations where relevant, and specific questions for incomplete or ambiguous evidence. | No invented criteria, external verification, approval, scoring, or business writes. |
| Case notes summarizer | Summarize supplied notes; use policy only when supplied and needed for the question. | Attributed facts, unresolved dates or conflicting notes, and focused staff questions. A basic summary does not require policy. | No inferred deadlines, unsupported reconciliation, eligibility decisions, or system updates. |
| Checklist and case helper | Select the appropriate specialist for a review; explain needed inputs without specialist execution. | The complete specialist findings, not another review or a serialized receipt. | Routing is model-directed. It adds inference work; use a directly enabled specialist for a known single task. |

These are supplied-evidence assistants, not autonomous case-management systems.
Adding retrieval or write tools would change their permissions, data boundary,
and evaluation requirements; it is not needed to improve these tasks. **Chat**
owns conversation context and **Document reviews** owns saved review state.
Neither ownership belongs in the coordinator or its specialists.

Refine and validate one layer at a time: application specialist, case specialist,
then coordinator. The [evaluation guide](../evaluations/README.md#offline-validation)
provides separate offline selectors. After separately approved staging publication,
test each specialist's answer before comparing it with the coordinator's visible
answer and execution receipt. Confirm both useful findings and the absence of
unnecessary questions. Passing packaging or mock tests is not a model-quality
result; no source edit changes an already deployed agent.

The coordinator needs `interact/action` on each specialist's endpoint. This
repository doesn't know yet whether an agent's default access covers that. The
deployer prints each new version's agent identity principal ID. To grant
Foundry Agent Consumer on each specialist, set `coordinator_agent_access` in the
[platform Terraform](../terraform/README.md#coordinator-agent-access) to the
coordinator's principal ID and apply. See
[coordinator agent access](../docs/permissions.md#coordinator-agent-access) for
the order to follow on a first deployment.

To swap use cases, use an operator-managed
[coordinator profile](../docs/agent-profiles.md). A profile supplies
instructions, named specialist bindings, and mandatory per-tool smoke checks
without changing Terraform. Deploy its specialists first.

The coordinator uses cancellable async requests with a 90-second deadline,
including time waiting for a concurrency slot. It performs no automatic
specialist retries and allows at most four specialist calls in flight per
process. Set `SPECIALIST_TIMEOUT_SECONDS` and `SPECIALIST_MAX_CONCURRENCY` in
the runtime environment to tune these limits. Cancelling the HTTP request
releases local resources but does not guarantee the remote service stops
already-started work. The coordinator keeps one authenticated client per
specialist for the life of the process, so repeated calls reuse open
connections. Each request still gets a current access token.

The coordinator also reuses specialist sessions to skip the cold start of a new
sandbox. After a specialist call completes, the coordinator sends that call's
`agent_session_id` with its next call to the same specialist. Each session
serves one call at a time, and a failed call discards its session. A session is
reused for at most `SPECIALIST_SESSION_REUSE_SECONDS` after it's created, 600 by
default, which is shorter than the default 900-second idle timeout. Set it to
`0` to turn reuse off. A session stays on the agent version that created it, so
after you deploy a new specialist version, a running coordinator can keep
calling the previous version until the window ends. Reuse doesn't carry
conversation history between calls because the coordinator doesn't store
responses and doesn't send a previous response or conversation ID.

## Deployment walkthrough

Terraform creates the baseline. The following procedures publish agent code
through the Python deployer. Run them from the repository root on an authorized
private-network execution environment. Stop on any error.

For source staging onto a separate runner, use the
[private deployment runbook](../docs/private-deployment.md) instead. That
runbook gives the working directory for the staged layout.

### 1. Confirm prerequisites

1. Confirm the baseline Terraform deployment was applied successfully.
2. Confirm local Python 3.14 is available.
3. Sign in with an Azure identity that has Foundry Project Manager at project
   scope. See [Scope and safety boundaries](#scope-and-safety-boundaries).
4. Confirm private Domain Name System (DNS) and routing to the project.
5. Confirm the tenant and subscription before mutation.
6. Confirm no other deployment of the same agent is active.

### 2. Set verified deployment inputs

From a private backend-connected administrative environment, read:

```powershell
terraform -chdir=terraform output -raw foundry_project_endpoint
terraform -chdir=terraform output -raw model_deployment_name
```

Set these non-secret output values in the deployment session. The deployment
runner does not need a copy of Terraform state:

```powershell
$env:FOUNDRY_PROJECT_ENDPOINT = '<verified-project-endpoint>'
$env:FOUNDRY_MODEL_NAME = '<verified-model-deployment-name>'
```

### 3. Prepare the selected sample

The following example selects the case specialist. Change `$sample`
deliberately for another sample. Do not reuse another environment's installed
dependencies.

```powershell
$sample = 'hosted-agents/case-review-agent'
python -m venv "$sample/.venv"
$python = Join-Path $PWD "$sample/.venv/Scripts/python.exe"
& $python -m pip install -r "$sample/requirements-deploy.txt"
```

Stop if environment creation or dependency installation fails. Use `$python` for
the subsequent command rather than relying on shell activation or PATH.

### 4. Inventory and review before deployment

1. Use the
   [inventory procedure](../docs/private-deployment.md#4-inventory-before-mutation)
   with the chosen agent name.
2. Record the routed version and recovery target.
3. Review source, instructions, dependency pins, and deployment options.
4. For a coordinator, confirm both specialists are deployed and independently
   tested.

### 5. Deploy explicitly

```powershell
& $python "$sample/deploy.py"
if ($LASTEXITCODE -ne 0) { throw 'Agent deployment or smoke verification failed' }
```

This command creates a billable version and changes routing. It is not a
Terraform plan or a dry run. Require successful activation and all smoke checks.

### 6. Verify the route and handle failures

1. Repeat inventory after deployment.
2. Confirm the intended version receives endpoint traffic.
3. On failure, inspect the actual route before retrying.
4. Retain recovery versions.
5. Follow the
   [failure procedure](../docs/private-deployment.md#7-handle-failure-and-cleanup)
   before you attempt another deployment.

## What publication does

The deployer packages `main.py`, `requirements.txt`, and the sample's reviewed
instructions and `configuration.py` when present into a deterministic ZIP with
portable regular-file permissions. Review agents also include the shared
`review_output.py` quotation and result-preservation middleware. Stage that file
beside `deployment.py` when deploying source rather than a portable bundle.
Before upload it checks the model and
specialists and snapshots the existing route. Existing routes must use explicit
versions: a symbolic `@latest` route or an unrouted existing agent requires
operator reconciliation before another version is created.

It uploads an immutable hosted-agent version with a source hash, waits for
activation, checks that the previous endpoint hasn't changed, preserves its
authorization and other protocol settings, and promotes the Responses route.
It reads the active version and exact 100% route back both before and after the
sample-specific smoke checks. Clients can reach the candidate during those
checks; this is not a pre-promotion canary.

If provisioning or a smoke test fails, the deployer attempts to restore the
previous route when promotion was attempted. It deletes the failed version only
after a fresh route read confirms the candidate is no longer referenced. Failed
restoration, an unknown or symbolic route, or a first deployment without a previous route
retains the candidate for manual inspection.

Serialize deployments of the same agent. The cleanup flow does not provide a
distributed lock against concurrent promotions.

The Foundry client allows 30 seconds to connect and 60 seconds for each response,
with no automatic retries, so a stalled call fails in about 90 seconds instead
of waiting for SDK defaults. A failed call after the version is created runs the
rollback above. Inspect the route before you rerun the deployment.

Run `python deploy.py --help` to override the agent name, supported runtime
allocation, instructions, smoke-test prompt, or polling timeout.

Coordinator deployments additionally run application and case delegation checks.
Each check requires a completed response, exactly the expected structured
function call, and a matching successful tool result with nonempty specialist
output. These checks are not disabled by an empty `--smoke-test-prompt`. Text
naming a specialist alone cannot pass. Smoke-test logs report outcomes, not
review bodies. If the service omits function-call outputs, verification fails
closed; inspect the protocol output rather than weakening the check to text
matching.

Hosted-agent code deployment currently uses the documented `python_3_14`
remote-build runtime. This is independent of the local Python version used to
run the deployment client. The hosting package is still a beta dependency, so
versions are pinned and should be upgraded only after local and remote smoke
tests pass.

## Portable agent bundles

`bundle.py` exports source plus a versioned configuration manifest. **Export and
inspect are offline** and require only Python; only `deploy` uses the Azure SDK
and creates billable resources. Run commands from the repository root.

Each `.agent-bundle.zip` contains `manifest.json` and `agent.zip`. The manifest
records instructions, allocation, runtime, approved template/specialist settings,
smoke prompts, and hashes of the runtime archive and every source/dependency
file. Source model names are informational: the destination project, model
deployment, and agent name must always be supplied explicitly.

### Export a prebuilt agent

```powershell
New-Item -ItemType Directory -Path agent-exports -Force | Out-Null
python hosted-agents\bundle.py export --sample case-review-agent --output agent-exports\case.agent-bundle.zip
python hosted-agents\bundle.py inspect agent-exports\case.agent-bundle.zip
```

Select any of the four sample directory names with `--sample`. For a coordinator,
add `--profile <reviewed-profile.json>` to capture its instructions, specialist
bindings, and mandatory delegation checks. For an unprofiled sample, use
`--instructions-file <reviewed-instructions.txt>` to preserve an instruction
override. `--model`, `--cpu`, and `--memory` record source configuration; CPU
and memory default to `0.5` / `1Gi`.

This exports **the reviewed checkout**, not a snapshot of live Azure overrides.
Confirm that the checkout/profile/instructions match the version you intend to
move. Output files are never overwritten. The CLI prints a SHA-256 for transfer
verification; `inspect` verifies integrity without executing bundled Python or
printing prompt text.

Individual runtime files are limited to 256 KiB. The embedded runtime ZIP can
exceed that per-file limit, but each archive and its expanded entries must fit
within 2 MiB. Export checks the completed bundle against the same limits as
inspect and deploy before writing it.

### Export an agent created in the Lab

The Lab library's `export.availability` value is `after_creation`. Catalog
definitions are not standalone checked-in bundle samples: prepare and publish
the selected definition through the existing creation lifecycle, then export
the resulting ready record. This distinction prevents the browser from
presenting discovery as deployment or implying one-click movement between
environments.

Save the JSON response for `GET /api/agents/<created-ID>` from your approved
private Lab. The updated API includes the saved `runtime_hash`; refresh the
record after deploying the updated Lab if an older response omits it. An
operator's saved Cosmos document with the same fields also works.

```powershell
$lab = 'https://<verified-private-lab-host>'
$id = 'created-<agent-UUID>'
Invoke-RestMethod "$lab/api/agents/$id" |
    ConvertTo-Json -Depth 30 |
    Set-Content agent-exports\created-record.json -Encoding utf8
python hosted-agents\bundle.py export-created --record agent-exports\created-record.json --output agent-exports\created.agent-bundle.zip
python hosted-agents\bundle.py inspect agent-exports\created.agent-bundle.zip
```

The record must be ready. The CLI takes its instructions, template ID, model,
and runtime name, but does not export project IDs, operator keys, events, chat
records, or resource ownership metadata. It requires the shared runtime ZIP
hash to match the saved hash. If the Lab runtime changed since publication,
use `--runtime-directory <original-agent_runtime-folder>` from the matching
source revision. A mismatched or missing hash is an error, not permission to
substitute today's code.

### Deploy into a prepared destination

On an approved private-network runner, prepare the deployment environment from
the earlier walkthrough. Transfer the reviewed bundle and use this repository's
`hosted-agents\bundle.py` and `deployment.py` as the deployment tooling:

```powershell
& $python hosted-agents\bundle.py deploy agent-exports\case.agent-bundle.zip `
    --endpoint '<verified-destination-project-endpoint>' `
    --model '<existing-destination-model-deployment>' `
    --agent-name 'destination-case-review'
if ($LASTEXITCODE -ne 0) { throw 'Bundle deployment failed; inspect routing before retrying' }
```

The destination name is deliberate: using an existing name updates its route.
Deploy specialists first. When moving a coordinator, repeat
`--specialist OLD=NEW` for renamed specialists, for example
`--specialist case-review-agent=destination-case-review`. Both runtime bindings
and delegation checks are remapped; missing/inactive dependencies and
self-delegation fail before upload. Unmapped specialists retain their names.

Lab-created bundles deploy as **independently managed Foundry agents**, not as
new Lab creation records. Use a new destination name rather than taking over a
Lab-managed resource. They preserve the Lab's no-hidden-model-smoke-call
behavior: active runtime and confirmed routing are not proof of answer quality.
Test their fictional prompts explicitly after deployment. Adding an independent
agent to a destination Lab catalog is a separate operator change.

### Transfer boundaries

- Review source, instructions, dependencies, and the bundle before deployment.
  Hashes detect corruption, not malicious code or a forged manifest. Deployment
  executes the source in Foundry and installs its dependencies.
- Keep exports in protected storage. `agent-exports/` and `*.agent-bundle.zip`
  are ignored by Git; instructions and saved records can still contain data
  that needs access controls. Never include credentials in prompts.
- Bundles do not include infrastructure, model weights, permissions, identities,
  conversations, evaluation results, or the Lab's citation/schema validators.
  Recreate those prerequisites separately. No destination resources are
  provisioned implicitly.
- Direct dependency files travel unchanged; transitive dependency resolution
  still happens during the remote build. A bundle is not a frozen container
  image or a byte-for-byte runtime backup.

## Test and validate

Run the local regression suites from the repository root:

```powershell
python -m pip install -r .github\requirements-validation.txt
python -m ruff check cost-comparison hosted-agents workbench evaluations
python -m pip check
python -m unittest discover -s hosted-agents -p "test_*.py" -v
python -m unittest discover -s hosted-agents/review-coordinator-agent -p "test_*.py" -v
```

Install the coordinator's `requirements.txt` in an isolated environment to run
the real software development kit (SDK) contract tests. Deployment-only SDK
tests need `requirements-deploy.txt`; unavailable SDK contracts are explicitly
skipped.
They use an in-memory HTTP transport, not Azure. Live delegation checks still
require a deployment from the private network.

For answer quality beyond smoke checks, use the
[synthetic review evaluation runner](../evaluations/README.md). It evaluates an
already routed staging version without publishing or promoting agents. Its SDK
dependencies are isolated from these runtime and deployment environments.
Passing offline contract tests is not evidence that the live agent passed
evaluation.

To test the agent locally before deployment, install `requirements.txt` in a
separate virtual environment, set the same two environment variables, run
`python main.py`, and send a Responses request to
`http://localhost:8088/responses`.

## Roll back and recover

1. Stop retrying if provisioning, activation, routing, or smoke verification
   fails.
2. Read the current endpoint route with the inventory procedure.
3. Compare the route with the recovery target recorded before deployment.
4. Restore the prior route only through the reviewed failure procedure.
5. Keep the failed candidate when restoration is unknown, the route is unknown,
   or no previous route exists.
6. Inspect retained candidates manually before deleting them.

> [!CAUTION]
> A failed deployment can leave billable versions behind for inspection. Do not
> delete a candidate until a fresh route read confirms that no endpoint traffic
> references it.

## Troubleshooting

| Symptom | Likely cause | What to do |
| --- | --- | --- |
| Authentication failure | The local Azure session is missing or points to the wrong tenant or subscription. | Run `az login`, then verify tenant and subscription with `az account show`. |
| Project or deployment not found | The endpoint or model deployment name is stale or from another environment. | Re-read both values with `terraform output -raw`; the model value is the deployment name, not merely a catalog model name. |
| Remote build fails | Required source files or pinned packages are unavailable. | Confirm `main.py` and `requirements.txt` are present and that the pinned packages remain available. |
| Version provisioning fails | The selected region cannot provision the hosted-agent version or model. | Review the reported version details and confirm hosted-agent and model availability in the selected region. |
| Smoke test fails | The candidate route, specialist call, or runtime behavior failed verification. | From the private network, open **Agents > Traces** in the Foundry project, or query `AppDependencies` and `AppExceptions` by response ID in the linked Application Insights resource ([runbook](../terraform/monitoring/README.md#verification-and-portal-use)). Traces are metadata-only, so check status, timings and exception types rather than prompts. Also check endpoint routing; candidates are retained when cleanup cannot confirm they are unrouted. |

## Scenario selection and optional extensions

Start with the [scenario/status matrix](../docs/demos.md#at-a-glance), not a
catalog of promised integrations. Reuse the supplied casework and application
examples. Validate the preview proposal adaptation before presenting it as
proven. Review delegation isn't business-request triage; for simulated request
lookups, use the **Service request planner** template in
[Create agent](../docs/agent-creation.md).

The [extension guide](../docs/architecture-assessment.md) and
[optional integrations](../docs/optional-integrations.md) preserve the technical
paths for separately scoped work. They are not part of the primary demo or a
commitment to connect organizational data. Education knowledge assistants and
Microsoft 365/Copilot/SharePoint integrations are excluded from the primary
path.

The case agent has an optional, read-only policy guidance lookup over Azure AI
Search behind `KNOWLEDGE_RETRIEVAL_ENABLED`, which is off by default. With the
flag off, packages, bundles, and published agents are unchanged. A sample
guidance set and an index script are included, and a small sample pilot has run
in the dev environment since 2026-10-01. It isn't a finished evaluation. See the
[knowledge retrieval design](../docs/knowledge-retrieval.md).

Responses remains the Lab contract. Invocations for webhooks, batch payloads, or
custom streaming would need a separately justified adapter and validation, not a
change to every existing chat or review agent.

For metadata-only operational traces in the Foundry portal, see the
[private monitoring runbook](../terraform/monitoring/README.md). The publisher
disables prompt, response, and sensitive tool-content recording and uses
Microsoft Entra authentication for Application Insights. Existing versions need
an explicit rollout; changing publisher defaults does not update running agents.

These samples intentionally avoid incident investigation, telemetry correlation,
root-cause analysis, mitigation, scheduled health checks, and operational
compliance sweeps. Those scenarios are covered by
[Azure SRE Agent](https://learn.microsoft.com/azure/sre-agent/overview).

## Operational checklist

- Use immutable agent versions and explicitly promote a tested version.
- Choose the smallest sandbox, 0.5 vCPU/1 GiB initially, and right-size from
  Application Insights data.
- Set the shortest practical idle timeout because idle time is billable until
  the sandbox is deprovisioned. Every call without an `agent_session_id` starts
  a new session and sandbox. Reusing a session for related calls avoids that
  cold start and leaves fewer sandboxes idle.
- Keep secrets in managed connections or Key Vault, never in source, images, or
  version environment variables.
- Apply Responsible AI mitigations and validate all tool inputs and outputs.
- Review third-party tool data boundaries before enabling them.

## Related content

- [Coordinator profiles](../docs/agent-profiles.md)
- [Private deployment runbook](../docs/private-deployment.md)
- [Synthetic review evaluations](../evaluations/README.md)
- [Agent monitoring](../terraform/monitoring/README.md)

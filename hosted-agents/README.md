# Hosted-agent samples

Implementation guide for the [scenario-led demonstrations](../docs/demos.md) on
Microsoft Foundry on Azure. Choose one scenario per engagement; preparing or
publishing agents is separate from running a short demo on a prepared environment.

Engagements focus on demonstration and technical validation. Integration with customer systems and production deployment require separate scoping and agreement.

Hosted agents run custom containerized code in per-session, VM-isolated
sandboxes managed by Foundry Agent Service. Foundry manages the endpoint,
agent identity, scaling, session storage, observability, and version lifecycle.

## Included samples

| Sample | Purpose | Decision boundary |
| --- | --- | --- |
| [`basic-responses-agent/`](basic-responses-agent/) | Minimal Microsoft Agent Framework and Responses protocol baseline | General-purpose demonstration only |
| [`case-review-agent/`](case-review-agent/) | **Casework assistance - available:** cited summaries, missing/conflicting evidence, staff questions | Does not determine eligibility, liability, enforcement, or clinical status |
| [`application-review-agent/`](application-review-agent/) | **Application completeness - available; requirements and proposal review - experimental:** compare supplied material with explicit criteria | Missing evidence is not automatic noncompliance; does not score, rank, approve, deny, or recommend an outcome |
| [`review-coordinator-agent/`](review-coordinator-agent/) | Route review requests to the application or case specialist | Does not replace specialist review or make consequential decisions |

Available describes source implementation, not live validation of an environment.
Business-request triage is **planned**, not implemented by the review coordinator.
No additional agent or infrastructure stack is needed for the experimental
proposal workflow. The coordinator is an optional review-delegation pattern, not
a generic agent framework or a simulated business-approval system.

All samples use `DefaultAzureCredential`; no credentials are embedded in the
image or passed as environment variables. The two review samples operate only
on context supplied in the conversation. The primary demo uses synthetic data
only, with no customer-system, M365/Copilot/SharePoint connections or external
business actions. Optional integrations require separate review and agreement.

The review coordinator calls the two specialist hosted-agent endpoints through
the Foundry project using its managed identity. It selects one specialist by
default, forwards the complete request, and returns the specialist's findings.
Deploy both specialist agents before deploying the coordinator.

To swap use cases, use an operator-managed [coordinator profile](../docs/agent-profiles.md).
It supplies instructions, named specialist bindings, and mandatory per-tool smoke
checks without changing Terraform. Deploy its specialists first; profiles are
not customer isolation boundaries.

The coordinator uses cancellable async requests with a 90-second deadline
(including time waiting for a concurrency slot), no automatic specialist retries,
and at most four specialist calls in flight per process. Set
`SPECIALIST_TIMEOUT_SECONDS` and `SPECIALIST_MAX_CONCURRENCY` in the runtime
environment to tune these limits. Cancelling the HTTP request releases local
resources but does not guarantee the remote service stops already-started work.

## Deployment walkthrough

Terraform creates the baseline; these steps publish agent code through the Python
deployer. Run from the repository root on an authorized private-network execution
environment. Stop on any error. For source staging onto a separate runner, use
the [private deployment runbook](../docs/private-deployment.md) instead; it gives
the working directory for that staged layout.

### 1. Confirm prerequisites

Require a successfully applied baseline, local Python 3.13, a verified Azure
identity with Foundry Project Manager at project scope, and private DNS/routing
to the project. Confirm tenant and subscription before mutation. Do not start
another deployment of the same agent while one is active.

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

The following example selects the case specialist. Change `$sample` deliberately
for another sample; do not reuse another environment's installed dependencies.

```powershell
$sample = 'hosted-agents/case-review-agent'
python -m venv "$sample/.venv"
$python = Join-Path $PWD "$sample/.venv/Scripts/python.exe"
& $python -m pip install -r "$sample/requirements-deploy.txt"
```

Stop if environment creation or dependency installation fails. Use `$python`
for the subsequent command rather than relying on shell activation or PATH.

### 4. Inventory and review before deployment

Use the [inventory procedure](../docs/private-deployment.md#4-inventory-before-mutation)
with the chosen agent name. Record the routed version and recovery target.
Review source, instructions, dependency pins, and deployment options. For a
coordinator, both specialists must already be deployed and independently tested.

### 5. Deploy explicitly

```powershell
& $python "$sample/deploy.py"
if ($LASTEXITCODE -ne 0) { throw 'Agent deployment or smoke verification failed' }
```

This command creates a billable version and changes routing. It is not a
Terraform plan or a dry run. Require successful activation and all smoke checks.

### 6. Verify the route and handle failures

Repeat inventory and confirm the intended version receives traffic. On failure,
inspect the actual route before retrying, retain recovery versions, and follow
the [failure procedure](../docs/private-deployment.md#7-handle-failure-and-cleanup).

The deployer packages `main.py`, `requirements.txt`, and the sample's reviewed
instructions and `configuration.py` when present. It uploads an immutable hosted-agent version, waits
for activation, routes the endpoint, and invokes a sample-specific smoke test.
If provisioning or a smoke test fails, it attempts to restore the previous route
when promotion was attempted. It deletes the failed version only after a fresh
route read confirms the candidate is no longer referenced. Failed restoration,
an unknown route, or a first deployment without a previous route retains the
candidate for manual inspection. Serialize deployments of the same agent;
this cleanup does not provide a distributed lock against concurrent promotions.
Run `python deploy.py --help` to
override the agent name, supported runtime allocation, instructions,
smoke-test prompt, or polling timeout.

Coordinator deployments additionally run application and case delegation checks.
Each requires a completed response, exactly the expected structured function
call, and a matching successful tool result with nonempty specialist output.
These checks are not disabled by an empty `--smoke-test-prompt`. Text naming a
specialist alone cannot pass. Smoke-test logs report outcomes, not review bodies.
If the service omits function-call outputs, verification fails closed; inspect
the protocol output rather than weakening the check to text matching.

Run the local regression suites from the repository root:

```powershell
python -m unittest discover -s hosted-agents -p test_deployment.py -v
python -m unittest discover -s hosted-agents/review-coordinator-agent -p "test_*.py" -v
```

Install the coordinator's `requirements.txt` in an isolated environment to run
the real-SDK contract tests; otherwise those two tests are explicitly skipped.
They use an in-memory HTTP transport, not Azure. Live delegation checks still
require a deployment from the private network.

Hosted-agent code deployment currently uses the documented `python_3_14`
remote-build runtime. This is independent of the local Python version used to
run the deployment client. The hosting package is still a beta dependency, so
versions are pinned and should be upgraded only after local and remote smoke
tests pass.

For answer quality beyond smoke checks, use the
[synthetic review evaluation runner](../evaluations/README.md). It evaluates an
already routed staging version without publishing or promoting agents. Its SDK
dependencies are isolated from these runtime/deployment environments. Passing
offline contract tests is not evidence that the live agent passed evaluation.

To test the agent locally before deployment, install `requirements.txt` in a
separate virtual environment, set the same two environment variables, run
`python main.py`, and send a Responses request to
`http://localhost:8088/responses`.

The generated agent identity can invoke project models and use session storage
by default. Grant it explicit least-privilege RBAC roles for any additional
Azure service it must access.

The deploying user needs the Foundry Project Manager role at project scope (or
equivalent permissions) to create versions and update endpoint routing.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Authentication failure | Run `az login`, then verify tenant and subscription with `az account show`. |
| Project or deployment not found | Re-read both values with `terraform output -raw`; the model value is the deployment name, not merely a catalog model name. |
| Remote build fails | Confirm `main.py` and `requirements.txt` are present and that the pinned packages remain available. |
| Version provisioning fails | Review the reported version details and confirm hosted-agent and model availability in the selected region. |
| Smoke test fails | Inspect Foundry/Application Insights logs and endpoint routing; candidates are retained when cleanup cannot confirm they are unrouted. |

## Scenario selection and optional extensions

Start with the [scenario/status matrix](../README.md#scenarios-and-status), not a
catalog of promised integrations. Reuse the supplied casework and application
examples; validate the experimental proposal adaptation before presenting it as
proven. Business-request triage still needs a bounded simulation and explicit
human-approval behavior; it is not provided by review delegation.

The [extension guide](../docs/architecture-assessment.md) and
[optional integrations](../docs/optional-integrations.md) preserve the technical
paths for separately scoped work. They are not part of the primary demo or a
commitment to connect organizational data. Education knowledge assistants and
M365/Copilot/SharePoint integrations are excluded from the primary path.

Responses remains the Lab contract. Invocations for webhooks, batch payloads,
or custom streaming would need a separately justified adapter and validation,
not a change to every existing chat or review agent.

These samples intentionally avoid incident investigation, telemetry
correlation, root-cause analysis, mitigation, scheduled health checks, and
operational compliance sweeps. Those scenarios are covered by
[Azure SRE Agent](https://learn.microsoft.com/azure/sre-agent/overview).

## Operational checklist

- Use immutable agent versions and explicitly promote a tested version.
- Choose the smallest sandbox (0.5 vCPU/1 GiB initially) and right-size from
  Application Insights data.
- Set the shortest practical idle timeout because idle time is billable until
  the sandbox is deprovisioned.
- Keep secrets in managed connections or Key Vault, never in source, images,
  or version environment variables.
- Apply Responsible AI mitigations and validate all tool inputs and outputs.
- Review third-party tool data boundaries before enabling them.

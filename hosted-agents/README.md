# Hosted-agent samples

Hosted agents run custom containerized code in per-session, VM-isolated
sandboxes managed by Foundry Agent Service. Foundry manages the endpoint,
agent identity, scaling, session storage, observability, and version lifecycle.

## Included samples

| Sample | Purpose | Decision boundary |
| --- | --- | --- |
| [`basic-responses-agent/`](basic-responses-agent/) | Minimal Microsoft Agent Framework and Responses protocol baseline | General-purpose demonstration only |
| [`case-review-agent/`](case-review-agent/) | Build cited case timelines and surface missing or conflicting evidence | Does not determine eligibility, liability, enforcement, or clinical status |
| [`application-review-agent/`](application-review-agent/) | Compare submitted material with supplied criteria | Does not score, rank, approve, deny, or recommend an outcome |
| [`review-coordinator-agent/`](review-coordinator-agent/) | Route review requests to the application or case specialist | Does not replace specialist review or make consequential decisions |

All samples use `DefaultAzureCredential`; no credentials are embedded in the
image or passed as environment variables. The two review samples operate only
on context supplied in the conversation. Connect organizational data sources
through separately reviewed, least-privilege tools before production use.

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

## Candidate patterns

| Sample idea | Protocol | Useful integrations | Why hosted |
| --- | --- | --- | --- |
| Policy knowledge assistant | Responses | SharePoint, Microsoft Graph, AI Search | Grounded answers across durable conversations and changing policy sets |
| Document analysis assistant | Responses | Blob Storage, AI Search, Document Intelligence | Stateful multi-document review with structured, cited findings |
| Service navigation assistant | Responses | CRM, service catalogs, knowledge bases | Personalized guidance with managed access to organizational data |
| Workflow intake processor | Invocations | Webhooks, case management, Key Vault | Structured intake through a custom payload contract that scales by session |
| Customer onboarding planner | Responses | CRM, work tracking, SharePoint | Cross-system planning with tenant-scoped identity and session state |

The included review agents demonstrate the same capability-first approach:
tailor instructions, schemas, and synthetic fixtures for the target sector
without coupling the implementation to one organization.

| Capability | Public sector | Health and education | ISV |
| --- | --- | --- | --- |
| Case review | Revenue, property, or constituent case | Benefits or student-services case | Customer escalation or account review |
| Application review | Grant, permit, or procurement package | Provider enrollment, admissions, or research grant | Partner or marketplace application |
| Policy knowledge | Agency rules and procedures | Program, clinical-administrative, or institutional policy | Product, support, or partner policy |
| Service navigation | Constituent programs and agency services | Benefits, care navigation, or student services | Product plans, support paths, or partner services |
| Workflow intake | Records request, appeal, or service request | Referral, enrollment, or accessibility request | Support, integration, or provisioning request |
| Customer onboarding | Vendor or grantee implementation | Provider or research partner onboarding | SaaS tenant implementation |

Start with Responses for conversational agents. Use Invocations for webhooks,
batch payloads, or custom streaming contracts.

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

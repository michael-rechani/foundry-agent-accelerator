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

All samples use `DefaultAzureCredential`; no credentials are embedded in the
image or passed as environment variables. The two review samples operate only
on context supplied in the conversation. Connect organizational data sources
through separately reviewed, least-privilege tools before production use.

After deploying the Terraform baseline:

1. From the repository root, populate the deployment settings from Terraform:

  ```powershell
  $env:FOUNDRY_PROJECT_ENDPOINT = terraform -chdir=terraform output -raw foundry_project_endpoint
  $env:FOUNDRY_MODEL_NAME = terraform -chdir=terraform output -raw model_deployment_name
  ```

2. Choose a sample, create an isolated deployment environment, and install its
  locked dependencies. For example:

  ```powershell
  Set-Location hosted-agents/case-review-agent
  python -m venv .venv
  .\.venv\Scripts\Activate.ps1
  python -m pip install --upgrade pip
  python -m pip install -r requirements-deploy.txt
  ```

3. Confirm `az account show` identifies the intended tenant and subscription.
4. Run `python deploy.py`.

The deployer packages `main.py`, `requirements.txt`, and the sample's reviewed
instructions when present. It uploads an immutable hosted-agent version, waits
for activation, routes the endpoint, and invokes a sample-specific smoke test.
If provisioning or the smoke test fails, it deletes the failed version and
restores the previous route when one existed. Run `python deploy.py --help` to
override the agent name, supported runtime allocation, instructions,
smoke-test prompt, or polling timeout.

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
| Smoke test fails | Inspect Foundry/Application Insights logs; the deployer removes the candidate and restores the previous route when possible. |

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

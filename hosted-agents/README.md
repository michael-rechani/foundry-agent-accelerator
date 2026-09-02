# Hosted-agent samples

Hosted agents run custom containerized code in per-session, VM-isolated
sandboxes managed by Foundry Agent Service. Foundry manages the endpoint,
agent identity, scaling, session storage, observability, and version lifecycle.

## Included sample

[`basic-responses-agent/`](basic-responses-agent/) is a minimal Microsoft Agent
Framework agent using the OpenAI-compatible Responses protocol. It uses
`DefaultAzureCredential`; no credentials are embedded in the image or passed
as environment variables.

After deploying the Terraform baseline:

1. From the repository root, populate the deployment settings from Terraform:

  ```powershell
  $env:FOUNDRY_PROJECT_ENDPOINT = terraform -chdir=terraform output -raw foundry_project_endpoint
  $env:FOUNDRY_MODEL_NAME = terraform -chdir=terraform output -raw model_deployment_name
  ```

2. Create an isolated deployment environment and install its locked
  dependencies:

  ```powershell
  Set-Location hosted-agents/basic-responses-agent
  python -m venv .venv
  .\.venv\Scripts\Activate.ps1
  python -m pip install --upgrade pip
  python -m pip install -r requirements-deploy.txt
  ```

3. Confirm `az account show` identifies the intended tenant and subscription.
4. Run `python deploy.py`.

The deployer packages only `main.py` and `requirements.txt`, uploads an
immutable hosted-agent version, waits for it to become active, and routes the
agent endpoint to that version. It then invokes the endpoint as a smoke test.
If provisioning or the smoke test fails, it deletes the failed version and
restores the previous endpoint route when one existed. Run
`python deploy.py --help` to override the agent name, supported runtime
allocation, instructions, smoke-test prompt, or polling timeout.

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

## Candidate agents

| Sample idea | Protocol | Useful integrations | Why hosted |
| --- | --- | --- | --- |
| Incident triage assistant | Responses | Azure Monitor, ServiceNow, Teams | Durable conversations, managed identity, and per-session files |
| Document due-diligence agent | Responses | Blob Storage, AI Search, Document Intelligence | Stateful multi-turn review and isolated working files |
| Repository event processor | Invocations | GitHub webhooks, Azure DevOps, Key Vault | Accepts arbitrary webhook payloads and scales by session |
| Real-time support voice agent | Invocations WebSocket | Voice Live, Dynamics 365 | Bidirectional streaming and custom protocol control |
| Scheduled compliance reviewer | Responses background mode | Microsoft Graph, Azure Policy | Long-running work with polling, cancellation, and recovery |

Start with Responses for conversational agents. Use Invocations for webhooks,
batch payloads, or custom streaming contracts.

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

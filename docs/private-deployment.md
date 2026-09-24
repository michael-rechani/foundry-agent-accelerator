# Private deployment runbook

[Home](../README.md) / [Docs](README.md) / Private deployment

Use this runbook to publish a reviewed hosted agent update from an approved
machine inside the private network. The procedure publishes Python agent code; it
does not deploy Azure API Management (APIM), rotate credentials, or apply
Terraform infrastructure.

Use an approved execution environment with Microsoft Foundry private Domain Name System
(DNS) and routing. Azure CLI connectivity to Azure Resource Manager (ARM) alone
is insufficient. Run each numbered step to completion before continuing. No
deployment continues automatically after reading these instructions.

## At a glance

| Area | Requirement |
| --- | --- |
| Deployment identity | Foundry Project Manager at project scope |
| Credential model | Authorized managed identity only |
| Runner | Private-network machine with Foundry DNS and routing |
| Source transfer | Reviewed source files only |
| Concurrency | One deployment per agent at a time |
| Scope | Hosted agent code publication, not Terraform infrastructure |

## In this guide

- [1. Confirm prerequisites](#1-confirm-prerequisites)
- [2. Stage the reviewed sources](#2-stage-the-reviewed-sources)
- [3. Prepare the private runner](#3-prepare-the-private-runner)
- [4. Inventory before mutation](#4-inventory-before-mutation)
- [5. Deploy the coordinator](#5-deploy-the-coordinator)
- [6. Verify deployment and routing](#6-verify-deployment-and-routing)
- [7. Handle failure and cleanup](#7-handle-failure-and-cleanup)
- [Related content](#related-content)

## 1. Confirm prerequisites

- Confirm the subscription, tenant, project endpoint, intended agent, and change.
- The deploying identity needs Foundry Project Manager at project scope.
- Use an authorized managed identity; never transfer passwords or bearer tokens.
- Transfer only reviewed source files, not Terraform state, plans, variable
  files, environment files, caches, or the complete working directory.
- Run one deployment per agent at a time. Confirm any earlier scheduled
  deployment task has completed before starting another.

## 2. Stage the reviewed sources

Retain this layout on the private runner:

```text
hosted-agents/
  deployment.py
  review-coordinator-agent/
    deploy.py
    main.py
    configuration.py
    instructions.md
    requirements.txt
    requirements-deploy.txt
```

Use an approved private runner artifact channel. Verify the extracted archive's
SHA-256 against the local artifact and restrict execution access to operators.
Never put credential values in scripts or transferred artifacts.

For a profile-based deployment, also stage the selected non-secret profile and
follow the [swap lifecycle](agent-profiles.md). Profile validation is offline;
successful validation does not establish that its specialists exist or are
healthy.

Remote execution can outlive the initiating client connection. Record its task
name, exit code, and restricted log location. A successful task-start message is
not a successful agent deployment. Do not start a second task merely because a
status-read request failed.

## 3. Prepare the private runner

From the staged `hosted-agents` directory, using a working Python 3.13
executable:

```powershell
python -m venv .venv
$python = Join-Path $PWD '.venv/Scripts/python.exe'
& $python -m pip install -r review-coordinator-agent/requirements-deploy.txt
if ($LASTEXITCODE -ne 0) { throw 'Deployment dependency installation failed' }
$env:AZURE_TOKEN_CREDENTIALS = 'ManagedIdentityCredential'
$env:FOUNDRY_PROJECT_ENDPOINT = '<verified-project-endpoint>'
$env:FOUNDRY_MODEL_NAME = '<verified-model-deployment-name>'
```

Retrieve the two non-secret values with Terraform's `foundry_project_endpoint`
and `model_deployment_name` outputs on the administrative machine. The runner
does not need a copy of Terraform state. Use Python's full executable path if
the current process has a stale PATH after installation.

## 4. Inventory before mutation

Run this Python snippet on the private runner using its deployment environment.
It prints only agent names and version states, not credentials or review data.

```python
import os
from azure.ai.projects import AIProjectClient
from azure.core.exceptions import ResourceNotFoundError
from azure.identity import ManagedIdentityCredential

with ManagedIdentityCredential() as credential, AIProjectClient(
    endpoint=os.environ['FOUNDRY_PROJECT_ENDPOINT'],
    credential=credential,
    allow_preview=True,
) as project:
    for name in ('application-review-agent', 'case-review-agent', 'review-coordinator-agent'):
        try:
            agent = project.agents.get(agent_name=name)
            print(name, 'route:', agent.agent_endpoint)
            for version in project.agents.list_versions(agent_name=name):
                print(name, version.version, version['status'])
        except ResourceNotFoundError:
            print(name, 'not deployed')
```

Record the currently routed versions before continuing. Do not redeploy healthy
specialists merely to update the coordinator. If a specialist is missing, stage
its equivalent five source files and deploy it first using its own requirements.
An inventory error other than not-found is a blocker, not permission to recreate.

## 5. Deploy the coordinator

Remain in the staged `hosted-agents` directory and use the `$python` executable
from step 3. This is a mutating operation, not a Terraform plan or dry run.

```powershell
& $python -u review-coordinator-agent/deploy.py --poll-seconds 10 --max-polls 120
if ($LASTEXITCODE -ne 0) { throw 'Coordinator deployment or verification failed' }
```

The deployer creates an immutable version, waits for activation, captures the
previous endpoint, promotes the candidate, and runs the general smoke test plus
both mandatory delegation checks. Clients may reach the candidate during testing.

## 6. Verify deployment and routing

Require all of the following evidence before considering the update complete:

- New version becomes active.
- Application and case delegation checks each report success.
- Deployment exits with code zero and reports the promoted version.
- A fresh inventory shows that version receiving the intended endpoint traffic.

Record timestamps, agent/version, test outcomes, and operator identity. Avoid
logging review bodies. Do not label a coordinator-generated sentence as proof of
a specialist call; the verifier checks correlated structured tool results.

## 7. Handle failure and cleanup

On failure, the deployer attempts previous-route restoration when promotion was
attempted. It deletes the candidate only when a fresh route read confirms the
candidate is not referenced. Unknown routes or failed restoration retain it.

Inspect the actual endpoint before retrying or deleting anything. Restore a
known-good version under the same deployment lock, verify the route, then clean
up unrouted candidates deliberately. Retained versions may incur costs.

> [!CAUTION]
> Do not weaken delegation assertions to get a green deployment. If the service
> omits structured tool results, inspect the Responses protocol from the private
> runner and resolve that contract before publishing APIM.

## Troubleshooting

| Symptom | Likely cause | What to do |
| --- | --- | --- |
| Azure CLI works, but Foundry calls fail. | The runner can reach ARM but lacks private Foundry DNS or routing. | Move to an approved private-network runner and verify the project endpoint path. |
| Dependency installation fails. | The private runner lacks a working Python 3.13 environment or package access. | Fix the runner environment before setting deployment variables or mutating agents. |
| Inventory shows `not deployed` for a specialist. | The coordinator update depends on a missing specialist. | Stage that specialist's equivalent five source files and deploy it first. |
| Deployment starts but the client disconnects. | Remote execution can outlive the initiating client connection. | Use the recorded task name, exit code, and restricted log location to confirm the result. |
| Promotion fails after candidate creation. | Route restoration may have retained the candidate. | Inspect the actual endpoint, restore a known-good route under the lock, and clean up deliberately. |

## Related content

- [Hosted agents](../hosted-agents/README.md)
- [Coordinator profiles](agent-profiles.md)
- [Infrastructure outputs](../terraform/README.md#outputs)
- [Credentials and protected state](credentials.md)

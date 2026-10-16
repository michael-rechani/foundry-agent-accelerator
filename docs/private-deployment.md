# Private deployment runbook

[Home](../README.md) / [Docs](README.md) / Private deployment

This runbook publishes a reviewed hosted agent update from an approved machine
inside the private network. It publishes Python agent code only. It doesn't
deploy Azure API Management (APIM), rotate credentials, or apply Terraform
infrastructure.

You need an approved execution environment with Microsoft Foundry private Domain
Name System (DNS) and routing. Azure CLI connectivity to Azure Resource Manager
(ARM) alone isn't enough. Run each numbered step to completion before
continuing. No deployment continues automatically after reading these
instructions.

## At a glance

| Area | Requirement |
| --- | --- |
| Deployment identity | Foundry Project Manager at project scope, as Microsoft Learn asks. Whether Foundry User is enough is unconfirmed; see [permissions](permissions.md#foundry-user-and-foundry-project-manager). |
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

- Check the [tool versions and upgrade expectations](tool-versions.md).
  This runner needs Python 3.14 and the staged deployment requirements, not
  Node, Docker, Terraform state, or `azd` just to publish Python source.
- Confirm the subscription, tenant, project endpoint, intended agent, and change.
- The deploying identity needs Foundry Project Manager at project scope, as
  Microsoft Learn's
  [deployment guide](https://learn.microsoft.com/azure/foundry/agents/how-to/deploy-hosted-agent#required-permissions)
  asks. Learn's pages disagree on whether Foundry User is enough; see
  [Foundry User and Foundry Project Manager](permissions.md#foundry-user-and-foundry-project-manager).
- Use an authorized managed identity; never transfer passwords or bearer tokens.
- Transfer only reviewed source files, not Terraform state, plans, variable
  files, environment files, caches, or the complete working directory.
- Run one deployment per agent at a time. Confirm any earlier scheduled
  deployment task has completed before starting another.

## 2. Stage the reviewed sources

Keep this layout on the private runner:

```text
hosted-agents/
  deployment.py
  review_output.py
  hosted_runtime.py
  review-coordinator-agent/
    deploy.py
    main.py
    configuration.py
    instructions.md
    requirements.txt
    requirements-deploy.txt
```

For portable bundle deployment, stage `hosted-agents\bundle.py`,
`hosted-agents\deployment.py`, a deployment requirements file, and the reviewed
`.agent-bundle.zip` instead. Export and inspect need no SDK. Deployment uses the
same private runner and permissions. See
[portable agent bundles](../hosted-agents/README.md#portable-agent-bundles).

Use an approved private runner artifact channel. Verify the extracted archive's
SHA-256 against the local artifact and restrict execution access to operators.
Never put credential values in scripts or transferred artifacts.

For a profile-based deployment, also stage the selected non-secret profile and
follow the [swap lifecycle](agent-profiles.md). Profile validation is offline,
and a successful result doesn't establish that its specialists exist or are
healthy.

Remote execution can outlive the initiating client connection. Record its task
name, exit code, and restricted log location. A successful task-start message
isn't a successful agent deployment. Don't start a second task merely because a
status-read request failed.

## 3. Prepare the private runner

From the staged `hosted-agents` directory, using a working Python 3.14
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
doesn't need a copy of Terraform state. Use Python's full executable path if
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

Record the currently routed versions before continuing. Don't redeploy healthy
specialists merely to update the coordinator. If a specialist is missing, stage
its equivalent five source files and deploy it first using its own requirements.
An inventory error other than not-found is a blocker, not permission to recreate.
An existing agent must route to a named version before redeployment.
Reconcile `@latest`, unknown aliases, or an unrouted agent with an operator
instead of letting a new version change a symbolic recovery target.

## 5. Deploy the coordinator

Remain in the staged `hosted-agents` directory and use the `$python` executable
from step 3. This is a mutating operation, not a Terraform plan or dry run.

```powershell
& $python -u review-coordinator-agent/deploy.py --poll-seconds 10 --max-polls 120
if ($LASTEXITCODE -ne 0) { throw 'Coordinator deployment or verification failed' }
```

The deployer checks the model and specialists and snapshots the previous endpoint
before creating an immutable version. After activation it verifies the endpoint
hasn't changed, promotes the candidate while preserving authorization. It reads
the exact active route back before and after the general smoke test and both
mandatory delegation checks. Clients may reach the candidate during testing.

## 6. Verify deployment and routing

Treat the update as complete only when you have all of this evidence:

- New version becomes active.
- Application and case delegation checks each report success.
- Deployment exits with code zero and reports the promoted version.
- A fresh inventory shows that version receiving the intended endpoint traffic.

Record timestamps, agent/version, test outcomes, and operator identity. Avoid
logging review bodies. Don't label a coordinator-generated sentence as proof of
a specialist call; the verifier checks correlated structured tool results.

## 7. Handle failure and cleanup

On failure, the deployer attempts previous-route restoration when promotion was
attempted. It deletes the candidate only when a fresh route read confirms the
candidate isn't referenced. If the route is unknown or restoration fails, it
keeps the candidate.

Inspect the actual endpoint before retrying or deleting anything. Restore a
known-good version under the same deployment lock, verify the route, then clean
up unrouted candidates deliberately. Retained versions may incur costs.

> [!CAUTION]
> Don't weaken delegation assertions to get a green deployment. If the service
> omits structured tool results, inspect the Responses protocol from the private
> runner and resolve that contract before publishing APIM.

## Troubleshooting

| Symptom | Likely cause | What to do |
| --- | --- | --- |
| Azure CLI works, but Foundry calls fail. | The runner can reach ARM but lacks private Foundry DNS or routing. | Move to an approved private-network runner and verify the project endpoint path. |
| Dependency installation fails. | The private runner lacks a working Python 3.14 environment or package access. | Fix the runner environment before setting deployment variables or mutating agents. |
| Inventory shows `not deployed` for a specialist. | The coordinator update depends on a missing specialist. | Stage that specialist's equivalent five source files and deploy it first. |
| Deployment starts but the client disconnects. | Remote execution can outlive the initiating client connection. | Use the recorded task name, exit code, and restricted log location to confirm the result. |
| Promotion fails after candidate creation. | Route restoration may have retained the candidate. | Inspect the actual endpoint, restore a known-good route under the lock, and clean up deliberately. |

## Related content

- [Hosted agents](../hosted-agents/README.md)
- [Coordinator profiles](agent-profiles.md)
- [Infrastructure outputs](../terraform/README.md#outputs)
- [Credentials and protected state](credentials.md)

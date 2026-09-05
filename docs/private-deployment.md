# Private deployment runbook

[Overview](../README.md) / Private deployment

Use this runbook for a reviewed hosted-agent update. It does not deploy APIM or
rotate credentials. Start from a machine with Foundry private DNS and routing,
such as the Windows jumpbox. Azure CLI connectivity to ARM alone is insufficient.

## Preconditions

- Confirm the subscription, tenant, project endpoint, intended agent, and change.
- The deploying identity needs Foundry Project Manager at project scope.
- Use managed identity on the jumpbox; never transfer passwords or bearer tokens.
- Transfer only reviewed source files, not Terraform state, plans, variable
  files, environment files, caches, or the complete working directory.
- Run one deployment per agent at a time. Confirm any earlier scheduled
  deployment task has completed before starting another.

## Stage the reviewed sources

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

Use an approved private runner artifact channel. For manual administration,
Azure VM Run Command can stage a small encoded archive; pass PowerShell scripts
using Azure CLI `--scripts @path-to-script.ps1` rather than nested inline
here-strings. Check both stdout and stderr and verify the extracted archive's
SHA-256 against the local artifact. Never put credential values in the script.
Run Command uses a privileged VM context; restrict access to operators.

For a profile-based deployment, also stage the selected non-secret profile and
follow the [swap lifecycle](agent-profiles.md). Profile validation is offline;
successful validation does not establish that its specialists exist or are healthy.

A remote scheduled task can outlive the Run Command invocation. Record its name,
exit code, and restricted log location; a successful task-start message is not
a successful agent deployment. Do not start a second task merely because a
status-read request failed.

## Prepare the private runner

From the staged `hosted-agents` directory, using a working Python 3.13 executable:

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
does not need a copy of Terraform state. For a newly installed Python on the
jumpbox, use its full executable path if the current process has a stale PATH.

## Inventory before mutation

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

## Deploy the coordinator

```powershell
& $python -u review-coordinator-agent/deploy.py --poll-seconds 10 --max-polls 120
if ($LASTEXITCODE -ne 0) { throw 'Coordinator deployment or verification failed' }
```

The deployer creates an immutable version, waits for activation, captures the
previous endpoint, promotes the candidate, and runs the general smoke test plus
both mandatory delegation checks. Clients may reach the candidate during testing.

Require all of the following evidence:

- New version becomes active.
- Application and case delegation checks each report success.
- Deployment exits with code zero and reports the promoted version.
- A fresh inventory shows that version receiving the intended endpoint traffic.

Record timestamps, agent/version, test outcomes, and operator identity. Avoid
logging review bodies. Do not label a coordinator-generated sentence as proof
of a specialist call; the verifier checks correlated structured tool results.

## Failure handling

On failure, the deployer attempts previous-route restoration when promotion was
attempted. It deletes the candidate only when a fresh route read confirms the
candidate is not referenced. Unknown routes or failed restoration retain it.

Inspect the actual endpoint before retrying or deleting anything. Restore a
known-good version under the same deployment lock, verify the route, then clean
up unrouted candidates deliberately. Retained versions may incur costs.

Do not weaken delegation assertions to get a green deployment. If the service
omits structured tool results, inspect the Responses protocol from the private
runner and resolve that contract before publishing APIM.
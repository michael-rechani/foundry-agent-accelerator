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
$env:FOUNDRY_MODEL_NAME = '<verified-model-router-deployment-name>'
```

For a Router-targeted update, obtain `foundry_project_endpoint` and
`model_router_deployment_name` from the reviewed Terraform outputs on the
authorized administrative machine, and independently verify that the Router
and its requested configuration are ready before setting those values. If the
Router output is missing, null, stale, or unverified, stop rather than silently
selecting a fixed model. `model_deployment_name` identifies the fixed primary
model, not the Router. The runner doesn't need a copy of Terraform state. Use
Python's full executable path if the current process has a stale PATH.

The `deploy.ps1 -Agent` path prefers a non-null Router output but otherwise
falls back to the fixed model output; it also invokes the base coordinator
without a profile. Neither behavior establishes the Lab customer target below.
The checked-in Lab registry [`workbench/agents.json`](../workbench/agents.json)
currently labels `customer-review` as `gpt-4.1`; publishing a profile does not
update that label. `WORKBENCH_PREBUILT_AGENT_MODELS` is a manually supplied
per-agent RPM/estimated-TPM admission mapping, not runtime model selection,
billing, or evidence of the served model. `ChatReviews` admits a prebuilt
coordinator turn once and does not individually account for nested specialist calls.

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
    for name in ('application-review-agent', 'case-review-agent', 'customer-review-coordinator'):
        try:
            agent = project.agents.get(agent_name=name)
            print(name, 'state:', agent.get('state'), 'configuration_state:', agent.get('configuration_state'), 'route:', agent.agent_endpoint)
            for version in project.agents.list_versions(agent_name=name):
                print(name, version.version, version['status'])
        except ResourceNotFoundError:
            print(name, 'not deployed')
```

Record the currently routed versions before continuing. Don't redeploy healthy
specialists merely to update the coordinator. If a specialist is missing, stop:
this deployer cannot perform first publication without a confirmed recovery route.
An inventory error other than not-found is a blocker, not permission to recreate.
An existing agent must route to a named active, non-draft version through a
configured Responses endpoint before redeployment. Both parent operational
`state` and administrative `configuration_state` must explicitly be `enabled`;
missing, disabled, unknown or malformed states are refused. Microsoft's
[AgentDetails schema](https://learn.microsoft.com/en-us/python/api/azure-ai-projects/azure.ai.projects.models.agentdetails?view=azure-python)
distinguishes these states: administrative enablement alone does not establish
operational enablement. A [disabled agent](https://learn.microsoft.com/en-us/azure/foundry/reference/rest/agents-disable-agent)
rejects new requests even if its selector and version remain active. The pinned
`azure-ai-projects==2.6.1` SDK preserves the documented
[`configuration_state` response field](https://learn.microsoft.com/en-us/azure/foundry/reference/rest/agents-get-agent)
in the `AgentDetails` mapping, not as a declared attribute; if the service omits
it, this deployer stops rather than assuming it is enabled. Every parent-agent
read must return a string name exactly matching the requested agent; a missing,
malformed or mismatched name stops further automated route writes. Positive-traffic
version reads must also return the exact requested agent name and version.
Reconcile `@latest`, unknown aliases, missing Responses support, or an unrouted
agent with an operator instead of letting a new version change a symbolic or
unusable recovery target.

Microsoft's [hosted-agent routing documentation](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/manage-hosted-agent#configure-agent-endpoint-routing)
says traffic splitting is not supported: recovery and required specialist routes
must each have exactly one `FixedRatio` rule with an integer `traffic_percentage`
of 100 and a concrete release version. Missing, malformed, unsupported, split,
or extra zero-traffic rules are refused rather than normalized. The SDK's raw
rule mapping is checked because typed attributes can coerce malformed wire values.
A `draft-` version identifier is rejected even when its draft flag is absent or
false. Prior endpoint protocol, authorization, and other fields are preserved;
the guard does not establish that the real service will accept a rollback.

These checks identify only a usable Responses-route candidate, not live response
health, model quality, or a verified fixed-model recovery. An active prior route
alone doesn't establish which model its version uses, that a fixed deployment
exists or is healthy, or that fixed-model recovery has been verified.

## 5. Deploy the coordinator

Remain in the staged `hosted-agents` directory and use the `$python` executable
from step 3. This is a mutating operation, not a Terraform plan or dry run.

The Lab's `customer-review-coordinator` uses the reviewed
[`evidence-review.example.json`](../hosted-agents/review-coordinator-agent/profiles/evidence-review.example.json)
profile, with `inspect_application` and `inspect_case` specialist bindings.
Without `--profile`, this command deploys the separate base
`review-coordinator-agent` instead. The profile owns the agent name and
instructions; unset `FOUNDRY_HOSTED_AGENT_NAME` before using it.

```powershell
if (Test-Path Env:FOUNDRY_HOSTED_AGENT_NAME) { throw 'Unset FOUNDRY_HOSTED_AGENT_NAME before using the profile' }
& $python -u review-coordinator-agent/deploy.py --profile review-coordinator-agent/profiles/evidence-review.example.json --poll-seconds 10 --max-polls 120
if ($LASTEXITCODE -ne 0) { throw 'Coordinator deployment or verification failed' }
```

The deployer checks the model and specialists and snapshots the previous endpoint
before creating a version. For an existing agent with a concrete recovery route,
it opens a session bound to the exact active candidate version and runs the
configured general smoke prompt and every mandatory profile delegation check
before attempting promotion. An empty optional prompt does not skip profile
checks; if neither exists, promotion fails. It attempts to delete the temporary
candidate session; a session creation response lost or lacking a usable ID cannot
be cleaned up by the deployer and needs operator inspection. Cleanup errors stop
promotion. The documented [delete-session API](https://learn.microsoft.com/en-us/azure/foundry/reference/rest/agents-delete-session)
returns 204 both when deleted and when already absent, and lists no conditional-delete
header. If another actor deletes and recreates the same ID concurrently, success
does not prove which instance was deleted or prevent later recreation. Coordinate
session-ID operations externally; a 204 does not establish atomic instance
ownership or global absence. The published documentation does not rule out
undocumented controls. A candidate version whose pre-promotion check fails is
retained for inspection rather than force-deleted.

Before the first candidate smoke, immediately before promotion, and in the
post-promotion route checks, the deployer requires the returned hosted candidate
definition to report the exact requested `FOUNDRY_MODEL_NAME`. It also rechecks
the previous route, its positive-traffic versions, candidate identity and active
release status. Parent state and route are reread before candidate smoke and
after specialist and promoted-version reads; malformed Responses configurations
are rejected. This confirms service-reported configuration only: it doesn't
prove the effective served model, runtime integrity, or a fixed-model recovery.
The application and case specialists can apply an optimizer candidate that
overrides their runtime model; the coordinator does not use that override.
Specialist or prior recovery models aren't required to match the candidate.

The route and state reads and PATCH aren't atomic; an external writer can still
change them between checks. A pinned coordinator session does not pin specialist
sessions: delegation receipts prove an invocation, not downstream session freshness.

A pinned default route is not version-level access control or candidate isolation.
Microsoft says [agent invocation permissions are not version-specific](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/configure-agent#select-the-active-agent-version):
a caller with invoke access can select another available version, including by
using `x-agent-version-override` on Responses. Existing authorized consumers can
therefore invoke an unpromoted candidate before its smoke test or a retained failed
version after rollback. An access-aware release and deliberate cleanup decision
remain unresolved; retaining a version does not make it inaccessible.

[Hosted sessions](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/manage-hosted-sessions)
bind to the version resolved when each session is created, so a route update
changes selection for new sessions, not necessarily reused ones. The Lab caches
coordinator sessions per thread and agent for an absolute default 600 seconds;
the coordinator separately caches idle specialist sessions per specialist for
the same default. These are client reuse limits, not a global drain guarantee:
external sessions can persist much longer. When run, the CLI verifier's
`/api/reviews` request omits a thread, and the deployer's post-promotion smoke
passes no session ID, so they exercise fresh coordinator sessions, not every
consumer or the actual served model. `WORKBENCH_PREBUILT_AGENT_MODELS` has one
admission mapping per agent and cannot accurately account for both versions'
models during mixed-session traffic. Retain prior versions, any separately
verified fixed deployment, and required specialist dependencies until all relevant
clients and sessions have been safely accounted for; don't force-delete sessions
or promise automatic cutover.

First publication is intentionally unsupported by this deployer. A missing agent
or unconfirmed existing concrete recovery route stops the operation before any
version upload, route update, or agent deletion. There is no bypass flag. Creating
a first version may activate an `@latest` default before explicit promotion;
the code-upload API used here has no verified draft control. A separately reviewed
first-publication mechanism remains unresolved; this restriction does not supply
one or establish identity/RBAC readiness. Microsoft's [hosted-agent draft
preview documentation](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/manage-hosted-agent#create-a-draft-version-preview)
states that generic JSON draft creation must be enabled for the subscription;
otherwise `draft: true` creates a normal release. Checking the response afterward
cannot prevent any initial exposure. This does not establish draft support for
multipart code upload.

Clients can reach the candidate after promotion during its fresh default-route
checks. These checks do not establish runner host isolation or safe temporary-directory
cleanup under concurrent same-UID mutation; verify the private runner and its
Python patch level separately before deployment.

## 6. Verify deployment and routing

Treat the update as complete only when you have all of this evidence:

- The new version becomes active and reports the requested model configuration.
- Application and case delegation checks each report success.
- Deployment exits with code zero and reports the promoted version.
- A fresh inventory shows that version receiving the intended endpoint traffic.

Record timestamps, agent/version, test outcomes, and operator identity. Avoid
logging review bodies. Don't label a coordinator-generated sentence as proof of
a specialist call; the verifier checks correlated structured tool results.

## 7. Handle failure and cleanup

On failure after a promotion attempt, the deployer first reads the endpoint. It
restores the captured route only if the parent name matches, both parent states
are explicitly enabled, the endpoint still matches the attempted promotion, and
prior traffic-serving versions remain exact active releases. A missing or mismatched
parent identity, disabled or unknown state, or an observed different route or
endpoint configuration is left untouched and requires manual recovery; the
deployer never enables an agent. It
requires the complete restored endpoint to match the snapshot, rechecks those
versions, and confirms the observed route no longer references the candidate. Automatic
version deletion is disabled, even after successful restoration: user sessions
may already be bound to the candidate. If
restoration or verification fails, or no previous route is available, it keeps
the candidate, which can still be receiving traffic.

Microsoft's [delete-version API](https://learn.microsoft.com/en-us/azure/foundry/reference/rest/agents-delete-agent-version)
states that force deletion cascades all sessions for that version. Restoring a
route does not drain existing sessions or make a subsequent deletion atomic.
Failed candidates are deliberately retained and can incur costs. Inspect their
sessions and consumers before separately authorizing later cleanup; this deployer
never automatically deletes a candidate version, with or without force.

Inspect the actual endpoint before retrying or deleting anything. Restore a
known-good version under the same deployment lock, verify the route and version,
then clean up unrouted candidates deliberately. The deployer's read and restore
aren't atomic, so serialize all route edits as well as deployments. An active
status alone doesn't prove response health. Retained versions may incur costs.

> [!CAUTION]
> Don't weaken delegation assertions to get a green deployment. If the service
> omits structured tool results, inspect the Responses protocol from the private
> runner and resolve that contract before publishing APIM.

## Troubleshooting

| Symptom | Likely cause | What to do |
| --- | --- | --- |
| Azure CLI works, but Foundry calls fail. | The runner can reach ARM but lacks private Foundry DNS or routing. | Move to an approved private-network runner and verify the project endpoint path. |
| Dependency installation fails. | The private runner lacks a working Python 3.14 environment or package access. | Fix the runner environment before setting deployment variables or mutating agents. |
| Inventory shows `not deployed` for a specialist. | The coordinator update depends on a missing specialist. | Stop and resolve the missing specialist through a separately reviewed first-publication mechanism. |
| Deployment starts but the client disconnects. | Remote execution can outlive the initiating client connection. | Use the recorded task name, exit code, and restricted log location to confirm the result. |
| Promotion fails after candidate creation. | Route restoration may have retained the candidate. | Inspect the actual endpoint, restore a known-good route under the lock, and clean up deliberately. |

## Related content

- [Hosted agents](../hosted-agents/README.md)
- [Coordinator profiles](agent-profiles.md)
- [Infrastructure outputs](../terraform/README.md#outputs)
- [Credentials and protected state](credentials.md)


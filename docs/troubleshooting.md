# Troubleshooting

[Home](../README.md) / [Docs](README.md) / Troubleshooting

Use this page to find the right guide when something goes wrong. It's an index,
not a fix list: each row names a symptom, the area it usually points to, and the
detailed table or section to read next. Start with the stage you were working
on.

The linked guides describe expected behavior of the sample. They don't record
results from a live deployment.

## In this guide

- [Deploy the platform](#deploy-the-platform)
- [Publish agents](#publish-agents)
- [Deploy the Lab](#deploy-the-lab)
- [Create an agent](#create-an-agent)
- [Chat and document reviews](#chat-and-document-reviews)
- [Monitoring](#monitoring)
- [Access, Bastion, and ingress](#access-bastion-and-ingress)
- [Permissions](#permissions)
- [Related content](#related-content)

## Deploy the platform

| Symptom | Likely area | Where to look |
| --- | --- | --- |
| A plan wants to recreate or delete an existing service. | Terraform state ownership | [Credentials troubleshooting](credentials.md#troubleshooting), [existing deployments](../terraform/README.md#existing-deployments) |
| Terraform can't reach the state backend. | Private network path to state | [Credentials troubleshooting](credentials.md#troubleshooting), [State](../terraform/README.md#state) |
| A model, Agent Service, or Search capacity error during apply. | Region choice and quota | [Region preference](../terraform/README.md#region-preference) |
| The editor or `terraform validate` shows deprecation warnings from modules. | Downloaded upstream modules | [Downloaded-module deprecation notices](../terraform/README.md#downloaded-module-deprecation-notices) |
| A jumpbox password rotation half-applies. | VM credential update | [Credentials troubleshooting](credentials.md#troubleshooting) |

## Publish agents

| Symptom | Likely area | Where to look |
| --- | --- | --- |
| The deployer can't authenticate or targets the wrong subscription. | Azure CLI session | [Hosted-agent troubleshooting](../hosted-agents/README.md#troubleshooting) |
| The project endpoint or model deployment isn't found. | Stale Terraform outputs | [Hosted-agent troubleshooting](../hosted-agents/README.md#troubleshooting) |
| The remote build, version provisioning, or smoke test fails. | Agent package, region, or runtime | [Hosted-agent troubleshooting](../hosted-agents/README.md#troubleshooting) |
| Azure CLI commands work, but Foundry calls from the runner fail. | Private DNS and routing | [Private deployment troubleshooting](private-deployment.md#troubleshooting) |
| The coordinator deploy stops on a missing specialist, a lost connection, or a failed promotion. | Private runner procedure | [Private deployment troubleshooting](private-deployment.md#troubleshooting) |
| You need to return to the previous version. | Endpoint routing | [Roll back and recover](../hosted-agents/README.md#roll-back-and-recover) |

## Deploy the Lab

| Symptom | Likely area | Where to look |
| --- | --- | --- |
| `AuthorizationFailed` persists on a VM runner after a new role grant. | Cached managed identity token | [Lab prerequisites](../workbench/README.md#1-confirm-prerequisites-and-state-ownership) |
| A Lab plan wants to recreate existing resources. | Lab state key and ownership | [Lab prerequisites](../workbench/README.md#1-confirm-prerequisites-and-state-ownership) |
| The image build, push, or pull by digest fails. | Private registry access from the runner | [Build and select an immutable image](../workbench/README.md#4-build-and-select-an-immutable-image) |
| The apply succeeds, but the private check fails. | Agent, Cosmos, or HTTPS path | [Verify the deployed application](../workbench/README.md#7-verify-the-deployed-application) |

## Create an agent

| Symptom | Likely area | Where to look |
| --- | --- | --- |
| **Create agent** shows an error code, such as `model_unavailable` or `runtime_failed`. | Publication step named by the code | [Agent creation troubleshooting](agent-creation.md#troubleshooting) |
| The outcome is unconfirmed after a timeout or restart. | Publication recovery | [Agent creation troubleshooting](agent-creation.md#troubleshooting), [Publication, recovery, and deletion](agent-creation.md#publication-recovery-and-deletion) |
| You need the failure details from the Lab log. | Log Analytics query | [Agent creation troubleshooting](agent-creation.md#troubleshooting) |
| **Create agent** isn't available. | Opt-in configuration | [Enable publication](agent-creation.md#enable-publication) |

## Chat and document reviews

| Symptom | Likely area | Where to look |
| --- | --- | --- |
| The Lab won't load its configuration. | Bootstrap deadline and settings | [Configuration loading](../workbench/README.md#configuration-loading) |
| A chat stops waiting, times out, or a save is rejected. | Request limits and ETag checks | [Limits and request behavior](../workbench/README.md#limits-and-request-behavior), [failure and capacity boundaries](architecture.md#failure-and-capacity-boundaries) |
| Requests return HTTP 429. | Process-local admission limits | [Storage and cost](../workbench/README.md#storage-and-cost) |
| `/api/health/dependencies` returns 503. | Foundry or Cosmos access | [Diagnostics and caching](../workbench/README.md#diagnostics-and-caching) |
| A review stays **running** or shows **Interrupted**. | Review recovery window | [Recover an interrupted review](review-workflow.md#recover-an-interrupted-review) |
| A review state or next action is unclear. | Review lifecycle | [Review states](review-workflow.md#review-states) |

## Monitoring

| Symptom | Likely area | Where to look |
| --- | --- | --- |
| No traces appear in Foundry. | Project connection, ingestion delay, or private path | [Monitoring troubleshooting](../terraform/monitoring/README.md#troubleshooting) |
| A created agent emits no traces. | Publisher grant for that agent | [Monitoring troubleshooting](../terraform/monitoring/README.md#troubleshooting), [permissions](permissions.md#assigned-by-this-repository) |
| `AppExceptions` or `AppGenAIContent` contains unexpected rows. | Older agent versions or tool schemas | [Monitoring troubleshooting](../terraform/monitoring/README.md#troubleshooting) |
| You need to check that traces carry no prompt or response content. | Metadata-only verification | [Verification and portal use](../terraform/monitoring/README.md#verification-and-portal-use) |

## Access, Bastion, and ingress

| Symptom | Likely area | Where to look |
| --- | --- | --- |
| The Lab URL doesn't open from your own browser. | Private network access | [Access](../workbench/README.md#access) |
| A Bastion plan wants to recreate the host or duplicate the subnet or IP. | Bastion import and state | [Bastion troubleshooting](../terraform/bastion/README.md#troubleshooting) |
| A Bastion session works, but the VM can't reach Foundry. | VM DNS and routing | [Bastion troubleshooting](../terraform/bastion/README.md#troubleshooting) |
| A gateway returns `502` or `504`, chat fails through the edge, or sign-in loops. | Application Gateway or Front Door setup | [Ingress troubleshooting](ingress-access.md#troubleshooting) |
| The governed review API rejects calls or fails its checks. | APIM authorization and backend | [Acceptance gates](apim-review-api.md#acceptance-gates) |

## Permissions

| Symptom | Likely area | Where to look |
| --- | --- | --- |
| A Lab, APIM, jumpbox, or project identity gets 401, 403, or `AuthorizationFailed`. | Role assigned by this repository | [Assigned by this repository](permissions.md#assigned-by-this-repository) |
| Created-agent publication fails with `operator_permissions_required`. | Lab identity's Foundry role | [Permissions](permissions.md#not-assigned-by-this-repository), [agent creation troubleshooting](agent-creation.md#troubleshooting) |
| Publishing a hosted agent fails with an authorization error. | Foundry Project Manager for the publisher | [Not assigned by this repository](permissions.md#not-assigned-by-this-repository) |
| Terraform can't create role assignments, read state, or refresh the Container App. | Operator prerequisites | [Not assigned by this repository](permissions.md#not-assigned-by-this-repository) |
| An Agent Service backing resource denies the project identity. | Assignments made inside the AVM module | [Assigned by the pinned AVM module](permissions.md#assigned-by-the-pinned-avm-module) |
| You need to know why a role exists, and the reference doesn't say. | Gaps in the source | [Unconfirmed items](permissions.md#unconfirmed-items) |

## Related content

- [Permissions reference](permissions.md)
- [Credentials and protected state](credentials.md)
- [Infrastructure deployment](../terraform/README.md)
- [The Lab](../workbench/README.md)
- [Hosted agents](../hosted-agents/README.md)
- [Documentation index](README.md)

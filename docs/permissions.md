# Permissions reference

[Home](../README.md) / [Docs](README.md) / Permissions

Use this reference to see which Azure roles the sample's Terraform assigns, to
which identity and scope, and which permissions you must arrange yourself. Each
row cites the Terraform resource or guide it comes from. Where the repository
doesn't say why a role exists or which role a requirement needs, this page says
so instead of guessing.

This is a sample, not a production access model. Nothing on this page has been
checked against a live deployment.

## At a glance

| Area | What to know |
| --- | --- |
| Assigned by this repository | Nine role assignment resources across the platform, Lab, and monitoring Terraform roots. The jumpbox and APIM grants exist only when those off-by-default features are enabled. |
| Assigned by the pinned AVM module | Six more assignments to the Foundry project identity, created inside the Foundry pattern module when Agent Service is enabled. |
| Not assigned by this repository | Operator prerequisites, state access, secret reads, image push, and anything Foundry grants itself. |
| Role names | The code refers to most roles by ID. Names come from Azure's built-in role catalog, not from this repository. |
| Guidance | Scope each grant narrowly, prefer managed identity, and remove temporary grants after a rollout. |

## In this guide

- [Role IDs used in the code](#role-ids-used-in-the-code)
- [Assigned by this repository](#assigned-by-this-repository)
- [Assigned by the pinned AVM module](#assigned-by-the-pinned-avm-module)
- [Not assigned by this repository](#not-assigned-by-this-repository)
- [Least-privilege guidance](#least-privilege-guidance)
- [Unconfirmed items](#unconfirmed-items)
- [Related content](#related-content)

## Role IDs used in the code

Most assignments pass a role definition ID rather than a name. The names below
are the current Azure built-in role names for those IDs, as returned by
`az role definition list --name <id>`. The Cosmos DB ID is a Cosmos DB data
plane role, which Azure lists separately in the
[Cosmos DB data plane security reference](https://learn.microsoft.com/azure/cosmos-db/reference-data-plane-security#built-in-roles).

| Role ID | Role name | Referenced in |
| --- | --- | --- |
| `53ca6127-db72-4b80-b1b0-d745d6d5456d` | Foundry User | [`terraform/main.tf`](../terraform/main.tf) (`azurerm_role_assignment.deployer_foundry_user`), [`terraform/apim.tf`](../terraform/apim.tf) (`azurerm_role_assignment.api_management_foundry_user`), [`workbench/infra/main.tf`](../workbench/infra/main.tf) (`azurerm_role_assignment.foundry`) |
| `eadc314b-1a2d-4efa-be10-5d325db5065e` | Foundry Project Manager | [`terraform/jumpbox.tf`](../terraform/jumpbox.tf) (`azurerm_role_assignment.jumpbox_foundry_project_manager`) |
| `3913510d-42f4-4e42-8a64-420c390055eb` | Monitoring Metrics Publisher | [`terraform/monitoring/main.tf`](../terraform/monitoring/main.tf) (`local.publisher_role_id`) |
| `00000000-0000-0000-0000-000000000002` (Cosmos DB SQL role) | Cosmos DB Built-in Data Contributor | [`workbench/infra/history.tf`](../workbench/infra/history.tf) (`azurerm_cosmosdb_sql_role_assignment.history`) |

Two assignments use a role name directly: **Key Vault Secrets Officer** in
[`terraform/main.tf`](../terraform/main.tf) (`deployer_secrets_officer` in
`module.ai_foundry`) and **AcrPull** in
[`workbench/infra/main.tf`](../workbench/infra/main.tf)
(`azurerm_role_assignment.pull`).

## Assigned by this repository

These are every role assignment declared in this repository's Terraform. A
search for `role_assignment`, `roleAssignments`, `role_definition`, and AVM
`role_assignments` inputs finds no others, and no script or application code
creates role assignments. The Lab never grants roles itself.

| Principal | Role | Scope | Assigned by | What breaks without it |
| --- | --- | --- | --- | --- |
| Platform deployer: `deployment_principal_id`, or the identity running Terraform when that's null | Key Vault Secrets Officer | The Agent Service Key Vault that the AVM module creates | [`terraform/main.tf`](../terraform/main.tf): `deployer_secrets_officer` in the `key_vault_definition` input of `module.ai_foundry`. Only when `enable_agent_service = true`, the default. | Not documented in this repository. See [unconfirmed items](#unconfirmed-items). |
| Platform deployer, as above | Foundry User | The Foundry project, `hosted-agents-<environment>` | [`terraform/main.tf`](../terraform/main.tf): `azurerm_role_assignment.deployer_foundry_user` | Not documented in this repository. The publishing guides ask for Foundry Project Manager, which this role doesn't replace. See [unconfirmed items](#unconfirmed-items). |
| Jumpbox VM system-assigned identity | Foundry Project Manager | The Foundry project | [`terraform/jumpbox.tf`](../terraform/jumpbox.tf): `azurerm_role_assignment.jumpbox_foundry_project_manager`. Only when `enable_jumpbox = true`; the default is `false`. | The jumpbox can't publish hosted agents with its managed identity. The [private deployment runbook](private-deployment.md#1-confirm-prerequisites) requires this role at project scope. Recreating the VM changes the identity, so [reconcile role assignments](../terraform/README.md#optional-administration-resources) before the next apply. |
| APIM system-assigned identity | Foundry User | The Foundry project | [`terraform/apim.tf`](../terraform/apim.tf): `azurerm_role_assignment.api_management_foundry_user`. Only when `enable_api_management = true`; the default is `false`. | The review API policy in [`review.xml.tftpl`](../terraform/policies/review.xml.tftpl) authenticates to the coordinator with this identity (`authentication-managed-identity`), so backend calls fail. `azurerm_api_management_api_policy.review` in [`terraform/review-api.tf`](../terraform/review-api.tf) depends on this assignment. See [API Management gateway](../terraform/README.md#api-management-gateway). |
| Lab user-assigned identity, `id-<name>` | AcrPull | The Lab's container registry | [`workbench/infra/main.tf`](../workbench/infra/main.tf): `azurerm_role_assignment.pull` | The Container App pulls its image with this identity (the `registry` block in `azurerm_container_app.this`); the registry admin account is disabled. |
| Lab user-assigned identity | Foundry User | The Foundry project named by `foundry_account_name` and `foundry_project_name` | [`workbench/infra/main.tf`](../workbench/infra/main.tf): `azurerm_role_assignment.foundry` | The Lab calls Foundry with this identity, so chat, reviews, and dependency checks fail. Created-agent publication reports [`operator_permissions_required`](agent-creation.md#troubleshooting) on a 401 or 403. Publication may need more than this role; see [Not assigned by this repository](#not-assigned-by-this-repository). |
| Lab user-assigned identity | Cosmos DB Built-in Data Contributor (Cosmos DB SQL role) | The `workbench/conversations` container only | [`workbench/infra/history.tf`](../workbench/infra/history.tf): `azurerm_cosmosdb_sql_role_assignment.history` | Saved chats, reviews, and created-agent records can't be read or written. See [Storage and cost](../workbench/README.md#storage-and-cost). |
| Foundry project system-assigned identity | Monitoring Metrics Publisher | The Application Insights component that the monitoring root creates | [`terraform/monitoring/main.tf`](../terraform/monitoring/main.tf): `azapi_resource.publisher["project"]` | The component sets `DisableLocalAuth = true`, so ingestion depends on Microsoft Entra ID grants. Without this one, project-connected traces can't be published. See [Agent monitoring](../terraform/monitoring/README.md#at-a-glance). |
| Each hosted agent runtime principal listed in `agent_principal_ids` | Monitoring Metrics Publisher | The same Application Insights component | [`terraform/monitoring/main.tf`](../terraform/monitoring/main.tf): `azapi_resource.publisher[<agent name>]` | That agent's SDK exporter can't send traces. A project grant alone doesn't cover a new agent. See the [monitoring troubleshooting](../terraform/monitoring/README.md#troubleshooting) table. |

The Lab's identity, registry, and Cosmos assignments live in the separate Lab
Terraform state. The monitoring assignments live in the monitoring state.

## Assigned by the pinned AVM module

`module.ai_foundry` in [`terraform/main.tf`](../terraform/main.tf) uses the
`Azure/avm-ptn-aiml-ai-foundry/azurerm` pattern module at version `0.11.3`. When
`enable_agent_service = true`, the default, this repository sets
`create_ai_agent_service` and `create_project_connections`. The module then
assigns these roles to the Foundry project's system-assigned identity. They
don't appear in this repository's code; the links go to the module source at
that version.

| Principal | Role | Scope | Assigned by | What breaks without it |
| --- | --- | --- | --- | --- |
| Foundry project system-assigned identity | Search Index Data Contributor | The Agent Service AI Search service | [`dependent-resource-rbac.tf`](https://github.com/Azure/terraform-azurerm-avm-ptn-aiml-ai-foundry/blob/v0.11.3/modules/ai-foundry-project/dependent-resource-rbac.tf#L31): `ai_search_role_assignments` | Not documented in this repository. |
| Foundry project system-assigned identity | Search Service Contributor | The Agent Service AI Search service | Same resource as above | Not documented in this repository. |
| Foundry project system-assigned identity | Cosmos DB Operator | The platform Cosmos DB account | [`dependent-resource-rbac.tf`](https://github.com/Azure/terraform-azurerm-avm-ptn-aiml-ai-foundry/blob/v0.11.3/modules/ai-foundry-project/dependent-resource-rbac.tf#L43): `cosmosdb_role_assignments` | Not documented in this repository. |
| Foundry project system-assigned identity | Storage Blob Data Contributor | The agent storage account | [`dependent-resource-rbac.tf`](https://github.com/Azure/terraform-azurerm-avm-ptn-aiml-ai-foundry/blob/v0.11.3/modules/ai-foundry-project/dependent-resource-rbac.tf#L56): `storage_role_assignments` | Not documented in this repository. |
| Foundry project system-assigned identity | Cosmos DB Built-in Data Contributor (Cosmos DB SQL role) | The `enterprise_memory` database | [`dependent-resource-rbac.tf`](https://github.com/Azure/terraform-azurerm-avm-ptn-aiml-ai-foundry/blob/v0.11.3/modules/ai-foundry-project/dependent-resource-rbac.tf#L78): `enterprise_memory_db_project_smi` | The module's comment says database scope is needed to cover the agent-definitions container that Foundry creates at first agent deployment. |
| Foundry project system-assigned identity | Storage Blob Data Owner, with an attribute-based access control (ABAC) condition | The agent storage account. The condition limits blob tag and filter actions to containers whose names start with the project GUID and match `*-azureml-agent`. | [`dependent-resource-rbac.tf`](https://github.com/Azure/terraform-azurerm-avm-ptn-aiml-ai-foundry/blob/v0.11.3/modules/ai-foundry-project/dependent-resource-rbac.tf#L110): `storage_blob_data_owner_project_smi` | Not documented in this repository. |

The module also has account-level user-assigned identity variants of the last
two rows and a Key Vault Crypto User assignment for customer-managed keys. This
repository creates neither: it sets `user_assigned_resource_ids = []` and
supplies no customer-managed key. A module upgrade can change this list, so
review it again with any version change.

## Not assigned by this repository

You or the environment owner must grant these. Foundry also grants some
permissions itself. The **Documented in** column is the only source for each
row.

| Who | Permission | Scope | Documented in | Needed for |
| --- | --- | --- | --- | --- |
| Platform deployer | Contributor and User Access Administrator, or equivalent | Not stated | [Infrastructure prerequisites](../terraform/README.md#prerequisites) | Creating the platform resources and the role assignments above. |
| Anyone running Terraform against remote state: platform, Lab, Bastion, or monitoring | Storage Blob Data Contributor | The state container | [Infrastructure state](../terraform/README.md#state), [Bastion upgrade](../terraform/bastion/README.md#existing-host-upgrade) | The backend authorizes against Blob Storage with Microsoft Entra ID. |
| Identity running Lab Terraform | `Microsoft.App/containerApps/listSecrets/action` | The specific Container App | [Terraform access](credentials.md#terraform-access) | AzureRM provider refresh of the Container App. |
| Identity running Lab Terraform | Resource, role-assignment, and state-container access | Not stated | [Lab prerequisites](../workbench/README.md#1-confirm-prerequisites-and-state-ownership) | Creating the Lab resources and its three role assignments. |
| Platform deployer, when `jumpbox_admin_secret` is set | Permission to read the pinned secret | That Key Vault secret; no role is named | [VM credentials](credentials.md#optional-virtual-machine-credentials) | Reading the jumpbox administrator password ephemerally. |
| Identity that publishes hosted agents, such as your Azure CLI user or a private runner | Foundry Project Manager | The Foundry project | [Hosted-agent prerequisites](../hosted-agents/README.md#1-confirm-prerequisites), [private deployment runbook](private-deployment.md#1-confirm-prerequisites) | Creating versions and updating endpoint routing. Terraform grants this only to the jumpbox identity, and only when `enable_jumpbox = true`. |
| Lab image build runner | Registry-scoped push and pull | The Lab's container registry | [Build the Lab image](../workbench/README.md#4-build-and-select-an-immutable-image) | Pushing the image and verifying the pull by digest. |
| Lab user-assigned identity, when `agent_creation_key_secret_id` is set | Access to the verifier secret | The Key Vault secret in `agent_creation_key_secret_id`; no role is named | [Enable publication](agent-creation.md#enable-publication), the `agent_creation_key_secret_id` variable in [`workbench/infra/main.tf`](../workbench/infra/main.tf) | The Container App's Key Vault secret reference. |
| Lab user-assigned identity, when agent creation is enabled | Read, publish, route, and delete hosted agents; no role is named | The Foundry project | [Enable publication](agent-creation.md#enable-publication) | Publishing created agents. The guide says invocation access alone may be insufficient. |
| Identity running monitoring Terraform | Monitoring resource and project-connection permissions, plus scoped RBAC administration for the publisher assignments | Not stated | [Monitoring deployment](../terraform/monitoring/README.md#deployment) | Creating the component, the connection, and the publisher grants. An authorized administrator can create the grants and import them instead. |
| Identity running Bastion Terraform | Permission to manage the Bastion host, subnet, and public IP | Not stated | [Bastion upgrade](../terraform/bastion/README.md#existing-host-upgrade) | Adopting or creating the three Bastion resources. |
| Portal users who view traces | Appropriate reader permissions; no role is named | Not stated | [Agent monitoring](../terraform/monitoring/README.md#at-a-glance) | Viewing traces from the private network. |
| Hosted agent runtime identity | Model invocation and session storage | The Foundry project | [Scope and safety boundaries](../hosted-agents/README.md#scope-and-safety-boundaries) | Foundry provides these by default. Grant explicit least-privilege roles for any other Azure service an agent needs. |
| Review coordinator identity | Calling the specialist agent endpoints; no role is named | The Foundry project | [Coordinator delegation pattern](../hosted-agents/README.md#coordinator-delegation-pattern) | Delegating to specialists with its managed identity. |
| Live evaluation runner | Foundry User, plus any permissions the chosen preview feature needs | The Foundry project | [Evaluation environment](../evaluations/README.md#prepare-an-isolated-evaluation-environment) | Reading inventory, invoking agents and models, and managing evaluators and runs. |
| Review API callers | A delegated or application permission with consent, plus the caller and client allowlists | The Microsoft Entra ID API registration | [Publication prerequisites](apim-review-api.md#publication-prerequisites) | Getting a token that APIM accepts. This isn't an Azure role, and Terraform doesn't create it. |

## Least-privilege guidance

This follows the [credentials guide](credentials.md) and the deployment guides.

- Use managed identity for runtime access. Apart from the deployer, every
  principal in [Assigned by this repository](#assigned-by-this-repository) is a
  workload identity, not a person.
- Scope each grant to the resource that needs it. For example, scope
  `listSecrets` to the specific app and deployment identity; it isn't a reason
  for broad subscription access.
- Don't give a runtime identity broad, permanent administration. Grant
  temporary deployment permissions for a rollout and remove them after it's
  verified.
- Grant temporary roles to a VM runner before you start it. Managed identity
  tokens are cached for up to 24 hours, so a late grant can keep failing with
  `AuthorizationFailed` until you deallocate and start the VM. See the
  [Lab prerequisites](../workbench/README.md#1-confirm-prerequisites-and-state-ownership).
- Give each hosted agent's own identity only the data-plane roles it needs.
  See [production considerations](../terraform/README.md#separately-scoped-production-considerations).

## Unconfirmed items

These couldn't be confirmed from the repository. Check them before relying on
the table.

- **Why the deployer gets Key Vault Secrets Officer.** The assignment exists, but
  no code or guide in this repository explains what uses it.
- **Why the deployer gets Foundry User.** The assignment exists, but no guide
  explains its purpose. The publishing guides ask for Foundry Project Manager
  instead.
- **Which role the Lab identity needs to publish created agents.** The guide
  says Foundry User alone may be insufficient but doesn't name a role.
- **Which role the coordinator identity uses to call specialists.** The guide
  says it uses managed identity but doesn't name a role.
- **Which Key Vault role reads a secret.** The jumpbox password and the Lab's
  operator-key verifier both need read access, but no role is named.
- **Scope of the operator prerequisites.** The guides don't state the scope for
  Contributor and User Access Administrator, Lab deployment access, Bastion
  network permissions, or trace reader permissions.
- **What breaks without the AVM module's assignments.** Apart from the Cosmos DB
  comment in the module, neither the module nor this repository says.
- **Role names.** The names come from Azure's built-in role catalog at the time
  of writing, not from this repository. Azure can rename roles; the IDs don't
  change.

## Related content

- [Troubleshooting](troubleshooting.md)
- [Credentials and protected state](credentials.md)
- [Infrastructure deployment](../terraform/README.md)
- [The Lab](../workbench/README.md)
- [Hosted agents](../hosted-agents/README.md)
- [Agent monitoring](../terraform/monitoring/README.md)

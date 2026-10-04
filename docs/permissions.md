# Permissions reference

[Home](../README.md) / [Docs](README.md) / Permissions

Use this reference to see which Azure roles the sample's Terraform assigns, to
which identity and scope, and which permissions you must arrange yourself. Each
row cites the Terraform resource, code, guide, or Microsoft Learn page it comes
from. Where neither the source nor Microsoft Learn says why a role exists or
which role a requirement needs, this page says so instead of guessing.

Two phrases mark where a statement comes from:

- **Confirmed from source** means the linked code in this repository, its Git
  history, or the pinned module source shows it.
- **Per Microsoft Learn** means the linked Microsoft Learn page says it. The
  repository's code doesn't show it.

This is a sample, not a production access model. Nothing on this page has been
checked against a live deployment, except the dated notes about grants made by
hand in the dev Lab.

## At a glance

| Area | What to know |
| --- | --- |
| Assigned by this repository | Thirteen role assignments across the platform, Lab, and monitoring Terraform roots. The jumpbox, APIM, coordinator, knowledge-search, deployer Key Vault, and Lab operator-key verifier grants exist only when you turn on those off-by-default inputs. |
| Assigned by the pinned AVM module | Six more assignments to the Foundry project identity, created inside the Foundry pattern module when Agent Service is enabled. |
| Not assigned by this repository | Operator prerequisites, state access, secret reads, image push, trace viewing, and anything Foundry grants itself. |
| Role names | The code refers to most roles by ID. Names come from Azure's built-in role catalog, not from this repository. |
| Guidance | Scope each grant narrowly, prefer managed identity, and remove temporary grants after a rollout. |

## In this guide

- [Role IDs used in the code](#role-ids-used-in-the-code)
- [Assigned by this repository](#assigned-by-this-repository)
- [Assigned by the pinned AVM module](#assigned-by-the-pinned-avm-module)
- [Not assigned by this repository](#not-assigned-by-this-repository)
- [Foundry User and Foundry Project Manager](#foundry-user-and-foundry-project-manager)
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
| `53ca6127-db72-4b80-b1b0-d745d6d5456d` | Foundry User | [`terraform/agent-access.tf`](../terraform/agent-access.tf) (`azurerm_role_assignment.deployer_foundry_user`, `azurerm_role_assignment.project_foundry_user`, `azurerm_role_assignment.api_management_foundry_user`), [`workbench/infra/main.tf`](../workbench/infra/main.tf) (`azurerm_role_assignment.foundry`) |
| `eadc314b-1a2d-4efa-be10-5d325db5065e` | Foundry Project Manager | [`terraform/jumpbox.tf`](../terraform/jumpbox.tf) (`azurerm_role_assignment.jumpbox_foundry_project_manager`) |
| `eed3b665-ab3a-47b6-8f48-c9382fb1dad6` | Foundry Agent Consumer | [`terraform/agent-access.tf`](../terraform/agent-access.tf) (`local.agent_consumer_role_id`) |
| `3913510d-42f4-4e42-8a64-420c390055eb` | Monitoring Metrics Publisher | [`terraform/monitoring/main.tf`](../terraform/monitoring/main.tf) (`local.publisher_role_id`) |
| `1407120a-92aa-4202-b7e9-c0e197c71c8f` | Search Index Data Reader | [`terraform/agent-access.tf`](../terraform/agent-access.tf) (`azurerm_role_assignment.knowledge_search_reader`) |
| `4633458b-17de-408a-b874-0445c86b69e6` | Key Vault Secrets User | [`workbench/infra/main.tf`](../workbench/infra/main.tf) (`azurerm_role_assignment.creation_key_verifier`) |
| `00000000-0000-0000-0000-000000000002` (Cosmos DB SQL role) | Cosmos DB Built-in Data Contributor | [`workbench/infra/history.tf`](../workbench/infra/history.tf) (`azurerm_cosmosdb_sql_role_assignment.history`) |

Two assignments use a role name directly: **AcrPull** in
[`workbench/infra/main.tf`](../workbench/infra/main.tf)
(`azurerm_role_assignment.pull`), and **Key Vault Secrets Officer** in
[`terraform/key-vault-access.tf`](../terraform/key-vault-access.tf)
(`local.agent_key_vault_role_assignments`).

## Assigned by this repository

These are every role assignment declared in this repository's Terraform. A
search for `role_assignment`, `roleAssignments`, `role_definition`, and AVM
`role_assignments` inputs finds no others, and no script or application code
creates role assignments. The Lab never grants roles itself.

| Principal | Role | Scope | Assigned by | What breaks without it |
| --- | --- | --- | --- | --- |
| Platform deployer, as above | Foundry User | The Foundry project, `hosted-agents-<environment>` | [`terraform/agent-access.tf`](../terraform/agent-access.tf): `azurerm_role_assignment.deployer_foundry_user` | Nothing in the platform apply. Confirmed from source: the platform Terraform makes only Azure Resource Manager calls, and this role grants Foundry data actions. Per Microsoft Learn, it's the role standard agent setup gives developers who create or edit agents, and its absence causes `AuthorizationFailed` when creating or editing agents ([standard agent setup](https://learn.microsoft.com/azure/foundry/agents/concepts/standard-agent-setup#troubleshoot-common-issues)). The repository doesn't record why it was added. See [Foundry User and Foundry Project Manager](#foundry-user-and-foundry-project-manager). |
| Foundry project system-assigned identity | Foundry User | The Foundry resource (account) | [`terraform/agent-access.tf`](../terraform/agent-access.tf): `azurerm_role_assignment.project_foundry_user` | [Live evaluation](../evaluations/README.md) runs. Per Microsoft Learn, assign this role to the project's managed identity at the Foundry resource scope to prevent evaluation and red teaming run failures ([virtual network support for evaluation](https://learn.microsoft.com/azure/foundry/concepts/evaluation-virtual-network#configure-evaluation-network-requirements)). Not confirmed in the private Lab whether it's required: there, `client.evals.runs.create` failed with `400 UserError: Pending evaluation-result upload was denied (HTTP 403)`, the failure persisted after this grant, and it cleared once the agent storage account admitted the project as a resource instance ([`terraform/keyless-storage.tf`](../terraform/keyless-storage.tf)). Hosted agents, delegation, and the Lab worked without it. |
| Platform deployer, as above | Key Vault Secrets Officer | The Agent Service Key Vault that the pinned AVM module creates | [`terraform/key-vault-access.tf`](../terraform/key-vault-access.tf): `local.agent_key_vault_role_assignments`, passed to `module.ai_foundry` as `deployer_secrets_officer`. Only when `deployer_key_vault_secrets_officer = true`; the default is `false`. | Nothing in this repository. Confirmed from source: no Terraform here or in the pinned AVM module reads or writes that vault. It's for operators who keep their own secrets there. See [Deployer Key Vault access](#deployer-key-vault-access). |
| Jumpbox VM system-assigned identity | Foundry Project Manager | The Foundry project | [`terraform/jumpbox.tf`](../terraform/jumpbox.tf): `azurerm_role_assignment.jumpbox_foundry_project_manager`. Only when `enable_jumpbox = true`; the default is `false`. | The jumpbox can't publish hosted agents with its managed identity. The [private deployment runbook](private-deployment.md#1-confirm-prerequisites) requires this role at project scope. Recreating the VM changes the identity, so [reconcile role assignments](../terraform/README.md#optional-administration-resources) before the next apply. |
| APIM system-assigned identity | Foundry User | The Foundry project | [`terraform/agent-access.tf`](../terraform/agent-access.tf): `azurerm_role_assignment.api_management_foundry_user`. Only when `enable_api_management = true`; the default is `false`. | The review API policy in [`review.xml.tftpl`](../terraform/policies/review.xml.tftpl) authenticates to the coordinator with this identity (`authentication-managed-identity`), so backend calls fail. `azurerm_api_management_api_policy.review` in [`terraform/review-api.tf`](../terraform/review-api.tf) depends on this assignment. See [API Management gateway](../terraform/README.md#api-management-gateway). |
| Review coordinator's agent identity, from `coordinator_agent_access.principal_id` | Foundry Agent Consumer | Each specialist agent in `coordinator_agent_access.specialist_agents`, at `<project ID>/agents/<name>`. The default list is `application-review-agent` and `case-review-agent`. | [`terraform/agent-access.tf`](../terraform/agent-access.tf): `azapi_resource.coordinator_agent_consumer`. Only when `coordinator_agent_access` is set; the default is `null`. | Confirmed from source: `invoke_specialist` in [`review-coordinator-agent/main.py`](../hosted-agents/review-coordinator-agent/main.py) calls each specialist's agent endpoint with `DefaultAzureCredential`. Per Microsoft Learn, calling an agent endpoint needs `Microsoft.CognitiveServices/accounts/AIServices/endpoints/interact/action`, and Foundry Agent Consumer is the least-privilege built-in role for it ([agent interaction](https://learn.microsoft.com/azure/foundry/agents/concepts/hosted-agent-permissions#agent-interaction)). Per Microsoft Learn, an agent-scope assignment applies only to that agent's endpoint ([agent-scope role assignments](https://learn.microsoft.com/azure/foundry/concepts/rbac-foundry#agent-scope-role-assignments)). Whether calls fail without it isn't confirmed; see [coordinator agent access](#coordinator-agent-access). |
| `case-review-agent` runtime identity, from `knowledge_search_access.principal_id` | Search Index Data Reader | The one index named by `knowledge_search_access.index_name` (default `lab-sample-policy-guidance`) on the Agent Service Search service, not the service | [`terraform/agent-access.tf`](../terraform/agent-access.tf): `azurerm_role_assignment.knowledge_search_reader`. Only when `knowledge_search_access` is set; the default is `null`. | Querying fictional policy guidance in the [knowledge-search pilot](knowledge-retrieval.md#identity-and-rbac). The retrieval smoke check fails closed without it. Retrieval is off by default, and an environment that keeps it off doesn't need this. The dev Lab's grant was made by hand on 2026-10-01 and imported into Terraform state on 2026-10-04; see [Knowledge search access](#knowledge-search-access). |
| Lab user-assigned identity, `id-<name>` | AcrPull | The Lab's container registry | [`workbench/infra/main.tf`](../workbench/infra/main.tf): `azurerm_role_assignment.pull` | The Container App pulls its image with this identity (the `registry` block in `azurerm_container_app.this`); the registry admin account is disabled. |
| Lab user-assigned identity | Foundry User | The Foundry project named by `foundry_account_name` and `foundry_project_name` | [`workbench/infra/main.tf`](../workbench/infra/main.tf): `azurerm_role_assignment.foundry` | The Lab calls Foundry with this identity, so chat, reviews, dependency checks, and created-agent publication fail. Publication reports [`operator_permissions_required`](agent-creation.md#troubleshooting) on a 401 or 403. Per Microsoft Learn, this role covers the agent calls that publication makes; see [Foundry User and Foundry Project Manager](#foundry-user-and-foundry-project-manager). |
| Lab user-assigned identity, only when `agent_creation_key_secret_resource_id` is set | Key Vault Secrets User | The one operator-key verifier secret, not the whole vault | [`workbench/infra/main.tf`](../workbench/infra/main.tf): `azurerm_role_assignment.creation_key_verifier`. Only when `agent_creation_key_secret_resource_id` is set; the default is `null`. A precondition requires it to name the same vault and secret as `agent_creation_key_secret_id`. | Confirmed from source: the `agent-creation-key-verifier` secret in `azurerm_container_app.this` reads that secret with the Lab identity. Per Microsoft Learn, a Container App's managed identity needs Key Vault Secrets User to use a Key Vault reference ([Container Apps Key Vault references](https://learn.microsoft.com/azure/container-apps/manage-secrets#reference-secret-from-key-vault)). The dev Lab's grant was made by hand first; see [Grants made by hand in the dev Lab](#grants-made-by-hand-in-the-dev-lab). |
| Lab user-assigned identity | Cosmos DB Built-in Data Contributor (Cosmos DB SQL role) | The `workbench/conversations` container only | [`workbench/infra/history.tf`](../workbench/infra/history.tf): `azurerm_cosmosdb_sql_role_assignment.history` | Saved chats, reviews, and created-agent records can't be read or written. See [Storage and cost](lab-configuration-and-cost.md#storage-and-cost). |
| Foundry project system-assigned identity | Monitoring Metrics Publisher | The Application Insights component that the monitoring root creates | [`terraform/monitoring/main.tf`](../terraform/monitoring/main.tf): `azapi_resource.publisher["project"]` | The component sets `DisableLocalAuth = true`, so ingestion depends on Microsoft Entra ID grants. Without this one, project-connected traces can't be published. See [Agent monitoring](../terraform/monitoring/README.md#at-a-glance). |
| Each hosted agent runtime principal listed in `agent_principal_ids` | Monitoring Metrics Publisher | The same Application Insights component | [`terraform/monitoring/main.tf`](../terraform/monitoring/main.tf): `azapi_resource.publisher[<agent name>]` | That agent's SDK exporter can't send traces. A project grant alone doesn't cover a new agent. See the [monitoring troubleshooting](../terraform/monitoring/README.md#troubleshooting) table. |

The Lab's identity, registry, Cosmos, and optional operator-key verifier
assignments live in the separate Lab Terraform state. The monitoring
assignments live in the monitoring state.

Offline mock-provider assertions pin the deployer, project, optional gateway,
and optional runner grants in
[`terraform/tests/permissions.tftest.hcl`](../terraform/tests/permissions.tftest.hcl),
and the Lab's registry, Foundry, container-only Cosmos, and secret-scoped
operator-key verifier grants in
[`workbench/infra/tests/permissions.tftest.hcl`](../workbench/infra/tests/permissions.tftest.hcl).
After backend-free initialization, run `./terraform/test-platform-validation.ps1`
and `terraform -chdir=workbench/infra test`. The platform helper copies the real
assignment sources and replaces module/credential boundaries, because Terraform
cannot mock the upstream ephemeral resources even with module overrides.
These targeted mock tests check assignment expressions, not live grants. The
runner case uses a mock apply to resolve its post-creation identity read. Existing
platform tests cover coordinator specialist scopes and opt-in Key Vault access;
monitoring tests cover component-scoped publishing. CI runs all of them.

### Coordinator agent access

The coordinator's agent identity is created by Foundry, not Terraform, so you
supply its principal ID.

- **Where the ID comes from.** Per Microsoft Learn, an agent created with the
  current agent object model gets its own Microsoft Entra agent identity, and
  `instance_identity.principal_id` is the ID for role assignments
  ([retrieve the agent identity](https://learn.microsoft.com/azure/foundry/agents/how-to/manage-hosted-agent#retrieve-the-agent-identity-for-role-assignments),
  [after the new model](https://learn.microsoft.com/azure/foundry/agents/how-to/migrate-agent-applications#after-new-model)).
  Confirmed from source: `report_agent_identity` in
  [`hosted-agents/deployment.py`](../hosted-agents/deployment.py) prints it
  after each new version is created.
- **Why platform Terraform assigns it.** Per Microsoft Learn, Foundry Project
  Manager can assign only the Foundry User role
  ([Foundry Project Manager](https://learn.microsoft.com/azure/role-based-access-control/built-in-roles/ai-machine-learning#foundry-project-manager)),
  so a publisher with that role can't grant Foundry Agent Consumer. The
  platform deployer already needs User Access Administrator.
- **Order.** The identity exists only after the coordinator's first version is
  created. If that first deployment fails its delegation checks, copy the
  printed principal ID into `coordinator_agent_access`, apply the platform
  Terraform, wait for the assignment to take effect, and deploy the
  coordinator again. Confirmed from source: `cleanup_failed_version` in
  [`hosted-agents/deployment.py`](../hosted-agents/deployment.py) keeps a
  failed first version, because the route still points at it and there's no
  earlier route to restore.
- **Identity changes.** Per Microsoft Learn, an agent identity lasts as long as
  the agent resource
  ([agent identity](https://learn.microsoft.com/azure/foundry/agents/concepts/agent-identity)).
  If you delete and re-create the coordinator, update the principal ID.

### Knowledge search access

The case-review agent's runtime identity is created by Foundry, not Terraform,
so you supply its principal ID, as for the coordinator. Copy the
`Agent identity principal ID` that the hosted-agent deployer prints for
`case-review-agent` into `knowledge_search_access.principal_id`. The index
itself isn't a Terraform resource: `knowledge_index.py` creates it, and it has
to exist before the grant is useful. See
[Knowledge search access](../terraform/README.md#knowledge-search-access).

The dev Lab's grant was made by hand on 2026-10-01 with the description
`Knowledge search pilot (#122)`, and imported into Terraform state on
2026-10-04, so the dev platform variables now set `knowledge_search_access`.
Azure rejects a second copy of a role assignment, so any other environment that
already has the grant must [import it](#adopt-the-knowledge-search-grant) before
it sets the variable.

### Deployer Key Vault access

`deployer_key_vault_secrets_officer` is off by default. When it's `true`,
Terraform gives the platform deployer Key Vault Secrets Officer on the Agent
Service Key Vault, so the deployer can create and rotate secrets there. The
deployer is `deployment_principal_id`, or the identity running Terraform when
that's unset.

Confirmed from source: this grant was added when Terraform wrote a generated
jumpbox password to that vault as `jumpbox-admin-password`
([commit 731f568](https://github.com/michael-rechani/foundry-agent-accelerator/commit/731f5687dedd88ab59914330853026d453c89ca7)),
kept after the switch to a pre-provisioned secret
([commit 9561bac](https://github.com/michael-rechani/foundry-agent-accelerator/commit/9561bac275851a9a80ca5353f2a75ac93822e4f3)),
and made opt-in once no Terraform in this repository or the pinned AVM module
used that vault.

- **Existing deployments.** Earlier versions created it by default, at
  `module.ai_foundry.module.key_vault["agent"].azurerm_role_assignment.this["deployer_secrets_officer"]`.
  Set `deployer_key_vault_secrets_officer = true` to keep it. The input uses the
  same key, role, and principal, so the plan shows no change. Leave it `false`
  and the next apply deletes the assignment. It doesn't delete any secret.
- **Reading one secret.** To read a single secret, such as a legacy
  `jumpbox-admin-password`, grant Key Vault Secrets User at secret scope
  instead. The `jumpbox_key_vault_name` and `jumpbox_admin_password_secret_name`
  outputs are `null` unless `jumpbox_admin_secret` is set. They're marked
  sensitive so plan and apply output doesn't print them; read one with
  `terraform -chdir=terraform output -raw jumpbox_key_vault_name`.

### Grants made by hand in the dev Lab

On 2026-09-23, two roles were assigned by hand to the dev Lab's identity, both
with the description `Foundry Lab agent creation`. Neither was in Terraform.

- **Key Vault Secrets User on the operator-key verifier secret.** It's now
  optional Terraform: `azurerm_role_assignment.creation_key_verifier`, created
  when `agent_creation_key_secret_resource_id` is set. The dev Lab's assignment
  still exists as made by hand, so [adopt it](#adopt-the-key-vault-grant)
  before you set the variable there.
- **Foundry Project Manager on the Foundry project.** Still not in Terraform.
  Whether the Lab needs it isn't confirmed. See
  [Test whether the Lab needs Foundry Project Manager](#test-whether-the-lab-needs-foundry-project-manager).

### Adopt the Key Vault grant

Azure rejects a second copy of a role assignment, so an environment that
already has this grant must import it into Terraform state before you set
`agent_creation_key_secret_resource_id`. The import changes only Terraform
state, not Azure.

1. Find the existing assignment's ID, using the Lab identity's principal ID and
   the secret's resource ID:

   ```powershell
   az role assignment list --assignee <Lab identity principal ID> --scope <secret resource ID> --query "[].id" --output tsv
   ```

2. In your local, uncommitted variable file, set
   `agent_creation_key_secret_resource_id` to the secret's resource ID. It looks
   like
   `/subscriptions/<subscription ID>/resourceGroups/<vault resource group>/providers/Microsoft.KeyVault/vaults/<vault>/secrets/<secret>`
   and must name the same vault and secret as `agent_creation_key_secret_id`.
3. Add an import block to a local, uncommitted `.tf` file, using the ID from
   step 1:

   ```hcl
   import {
     to = azurerm_role_assignment.creation_key_verifier[0]
     id = "<assignment ID from step 1>"
   }
   ```

4. Run `terraform plan` on an otherwise unchanged Lab. It must show
   `1 to import, 0 to add, 0 to change, 0 to destroy`. A replacement means the
   existing assignment differs from the one Terraform describes, for example in
   its description. Stop and compare them.
5. Apply the plan, then delete the import block.

### Adopt the knowledge-search grant

An environment that already has the grant must import it into Terraform state
before you set `knowledge_search_access`. The import changes only Terraform
state, not Azure.

1. Find the existing assignment's ID, using the case-review agent's principal ID
   and the index's resource ID
   (`<Search service resource ID>/indexes/<index name>`):

   ```powershell
   az role assignment list --assignee <case-review agent principal ID> --scope <index resource ID> --query "[].id" --output tsv
   ```

2. In your local, uncommitted variable file, set `knowledge_search_access` to
   that principal ID, and to the index name if it isn't
   `lab-sample-policy-guidance`.
3. Add an import block to a local, uncommitted `.tf` file, using the ID from
   step 1:

   ```hcl
   import {
     to = azurerm_role_assignment.knowledge_search_reader[0]
     id = "<assignment ID from step 1>"
   }
   ```

4. Run `terraform plan` on an otherwise unchanged platform. It must show
   `1 to import, 0 to add, 0 to change, 0 to destroy`. A replacement means the
   existing assignment differs from the one Terraform describes, for example in
   its description or principal type. Stop and compare them. Any other change,
   such as a resize of the jump box, also means stop: your saved variables are
   out of date, so fix them to match what's live and plan again. The first dev
   plan, on 2026-10-04, proposed a jump box resize and a role replacement
   because the saved `jumpbox_vm_size` was older than the live size. It also
   needed the two jump box approvals in
   [`terraform/README.md`](../terraform/README.md#optional-administration-resources), because the saved
   variables predated them.
5. Apply the plan, then delete the import block. A later plan must show no
   changes.

## Assigned by the pinned AVM module

`module.ai_foundry` in [`terraform/main.tf`](../terraform/main.tf) uses the
`Azure/avm-ptn-aiml-ai-foundry/azurerm` pattern module at version `0.11.3`. When
`enable_agent_service = true`, the default, this repository sets
`create_ai_agent_service` and `create_project_connections`. The module then
assigns these roles to the Foundry project's system-assigned identity. They
don't appear in this repository's code; the links go to the module source at
that version.

Confirmed from source: the module creates the project capability host,
`azapi_resource.ai_agent_capability_host` in
[`modules/ai-foundry-project/main.tf`](https://github.com/Azure/terraform-azurerm-avm-ptn-aiml-ai-foundry/blob/v0.11.3/modules/ai-foundry-project/main.tf#L129),
only after `time_sleep.wait_rbac_before_capability_host`
([line 160](https://github.com/Azure/terraform-azurerm-avm-ptn-aiml-ai-foundry/blob/v0.11.3/modules/ai-foundry-project/main.tf#L160)).
That wait depends on the Search, Cosmos DB Operator, and Storage Blob Data
Contributor rows below. The last two rows depend on the capability host. Per
Microsoft Learn, the capability host flow provisions with the project managed
identity, so that identity needs these roles before agents run
([capability settings permissions](https://learn.microsoft.com/azure/foundry/how-to/configure-capability-settings#permissions)).

| Principal | Role | Scope | Assigned by | What breaks without it |
| --- | --- | --- | --- | --- |
| Foundry project system-assigned identity | Search Index Data Contributor | The Agent Service AI Search service | [`dependent-resource-rbac.tf`](https://github.com/Azure/terraform-azurerm-avm-ptn-aiml-ai-foundry/blob/v0.11.3/modules/ai-foundry-project/dependent-resource-rbac.tf#L31): `ai_search_role_assignments` | Per Microsoft Learn, a missing search role causes `SearchIndexNotFound` or `403` on search operations ([standard agent setup](https://learn.microsoft.com/azure/foundry/agents/concepts/standard-agent-setup#troubleshoot-common-issues)). |
| Foundry project system-assigned identity | Search Service Contributor | The Agent Service AI Search service | Same resource as above | Same as above. Per Microsoft Learn, the project identity needs both search roles. |
| Foundry project system-assigned identity | Cosmos DB Operator | The platform Cosmos DB account | [`dependent-resource-rbac.tf`](https://github.com/Azure/terraform-azurerm-avm-ptn-aiml-ai-foundry/blob/v0.11.3/modules/ai-foundry-project/dependent-resource-rbac.tf#L43): `cosmosdb_role_assignments` | Per Microsoft Learn, it's a runtime role for the project identity at account level ([manual provisioning](https://learn.microsoft.com/azure/foundry/agents/concepts/standard-agent-setup#manual-provisioning)). Learn doesn't give a symptom. See [unconfirmed items](#unconfirmed-items). |
| Foundry project system-assigned identity | Storage Blob Data Contributor | The agent storage account | [`dependent-resource-rbac.tf`](https://github.com/Azure/terraform-azurerm-avm-ptn-aiml-ai-foundry/blob/v0.11.3/modules/ai-foundry-project/dependent-resource-rbac.tf#L56): `storage_role_assignments` | Per Microsoft Learn, a missing storage role causes `403 Forbidden` when the agent reads or writes files ([standard agent setup](https://learn.microsoft.com/azure/foundry/agents/concepts/standard-agent-setup#troubleshoot-common-issues)). |
| Foundry project system-assigned identity | Cosmos DB Built-in Data Contributor (Cosmos DB SQL role) | The `enterprise_memory` database | [`dependent-resource-rbac.tf`](https://github.com/Azure/terraform-azurerm-avm-ptn-aiml-ai-foundry/blob/v0.11.3/modules/ai-foundry-project/dependent-resource-rbac.tf#L78): `enterprise_memory_db_project_smi` | The module's comment says database scope is needed to cover the agent-definitions container that Foundry creates at first agent deployment. Per Microsoft Learn, the `agent-definitions-v1` and `run-state-v1` containers hold agent definitions, versions, and conversations ([Cosmos DB throughput requirements](https://learn.microsoft.com/azure/foundry/agents/concepts/standard-agent-setup#cosmos-db-throughput-requirements)). Learn doesn't give a symptom. See [unconfirmed items](#unconfirmed-items). |
| Foundry project system-assigned identity | Storage Blob Data Owner, with an attribute-based access control (ABAC) condition | The agent storage account. The condition limits blob tag and filter actions to containers whose names start with the project GUID and match `*-azureml-agent`. | [`dependent-resource-rbac.tf`](https://github.com/Azure/terraform-azurerm-avm-ptn-aiml-ai-foundry/blob/v0.11.3/modules/ai-foundry-project/dependent-resource-rbac.tf#L110): `storage_blob_data_owner_project_smi` | Per Microsoft Learn, the same `403 Forbidden` on file reads and writes. Learn lists this role on the `<workspaceId>-azureml-agent` container ([standard agent setup](https://learn.microsoft.com/azure/foundry/agents/concepts/standard-agent-setup#troubleshoot-common-issues)). |

The module also has account-level user-assigned identity variants of the last
two rows and a Key Vault Crypto User assignment for customer-managed keys. This
repository creates neither: it sets `user_assigned_resource_ids = []` and
supplies no customer-managed key. Confirmed from source: the module gives the
Agent Service Key Vault no default role assignments or secrets, and doesn't
connect it to the project. A module upgrade can change this list, so review it
again with any version change.

## Not assigned by this repository

You or the environment owner must grant these. Foundry also grants some
permissions itself. The **Documented in** column is the source for each row.

| Who | Permission | Scope | Documented in | Needed for |
| --- | --- | --- | --- | --- |
| Platform deployer | Contributor and User Access Administrator, or equivalent | The subscription, for a first apply. Confirmed from source: the platform root creates its own resource group, `azurerm_resource_group.this` in [`terraform/main.tf`](../terraform/main.tf), and puts every resource and role assignment in it. Per Microsoft Learn, roles assigned at a parent scope are inherited by child scopes ([scope levels](https://learn.microsoft.com/azure/role-based-access-control/scope-overview#scope-levels)). | [Infrastructure prerequisites](../terraform/README.md#prerequisites) | Creating the platform resources and the role assignments above. |
| Anyone running Terraform against remote state: platform, Lab, Bastion, or monitoring | Storage Blob Data Contributor | The state container | [Infrastructure state](../terraform/README.md#state), [Bastion upgrade](../terraform/bastion/README.md#existing-host-upgrade) | The backend authorizes against Blob Storage with Microsoft Entra ID. |
| Identity running Lab Terraform | `Microsoft.App/containerApps/listSecrets/action` | The specific Container App | [Terraform access](credentials.md#terraform-access) | AzureRM provider refresh of the Container App. |
| Identity running Lab Terraform | Resource, role-assignment, and state-container access; no role is named | Confirmed from source: the platform resource group in `resource_group_name`, where every Lab resource goes. The three role assignments target the Lab's registry, the Foundry project, and the platform Cosmos DB account's `workbench/conversations` container, all in that group ([`workbench/infra/main.tf`](../workbench/infra/main.tf), [`workbench/infra/history.tf`](../workbench/infra/history.tf)). When `agent_creation_key_secret_resource_id` is set, the identity also needs to create a role assignment at that Key Vault secret, which can be in another group. | [Lab prerequisites](lab-deployment.md#1-confirm-prerequisites-and-state-ownership) | Creating the Lab resources and its three role assignments, plus the optional operator-key verifier assignment. |
| Platform deployer, when `jumpbox_admin_secret` is set | Key Vault Secrets User, per Microsoft Learn | That Key Vault secret. Per Microsoft Learn, this role can be assigned at secret scope ([secret scope role assignment](https://learn.microsoft.com/azure/key-vault/general/rbac-guide#secret-scope-role-assignment)). | [VM credentials](credentials.md#optional-virtual-machine-credentials) | Confirmed from source: the identity running platform Terraform reads the password with `ephemeral.azurerm_key_vault_secret.jumpbox_admin` in [`terraform/jumpbox-credentials.tf`](../terraform/jumpbox-credentials.tf). Per Microsoft Learn, Key Vault Secrets User can read secret contents on a vault that uses Azure RBAC ([Key Vault built-in roles](https://learn.microsoft.com/azure/key-vault/general/rbac-guide#azure-built-in-roles-for-key-vault-data-plane-operations)). |
| Identity that publishes hosted agents, such as your Azure CLI user or a private runner | Foundry Project Manager | The Foundry project | [Hosted-agent prerequisites](../hosted-agents/README.md#1-confirm-prerequisites), [private deployment runbook](private-deployment.md#1-confirm-prerequisites), [Deploy a hosted agent](https://learn.microsoft.com/azure/foundry/agents/how-to/deploy-hosted-agent#required-permissions) | Creating versions and updating endpoint routing. Terraform grants this only to the jumpbox identity, and only when `enable_jumpbox = true`. See [Foundry User and Foundry Project Manager](#foundry-user-and-foundry-project-manager). |
| Lab image build runner | Registry-scoped push and pull | The Lab's container registry | [Build the Lab image](lab-deployment.md#4-build-and-select-an-immutable-image) | Pushing the image and verifying the pull by digest. |
| Lab user-assigned identity, when `agent_creation_key_secret_id` is set and `agent_creation_key_secret_resource_id` isn't | Key Vault Secrets User, per Microsoft Learn | The Key Vault secret in `agent_creation_key_secret_id` | [Enable publication](agent-creation.md#enable-publication), the `agent_creation_key_secret_id` variable in [`workbench/infra/main.tf`](../workbench/infra/main.tf), [Container Apps Key Vault references](https://learn.microsoft.com/azure/container-apps/manage-secrets#reference-secret-from-key-vault) | Confirmed from source: the `agent-creation-key-verifier` secret in `azurerm_container_app.this` reads the secret with the Lab identity. Per Microsoft Learn, a Container App's managed identity needs Key Vault Secrets User to use a Key Vault reference. Set `agent_creation_key_secret_resource_id` to have Lab Terraform assign it instead; see [Assigned by this repository](#assigned-by-this-repository). |
| Hosted agent runtime identity | Model invocation and session storage | The Foundry project | [Scope and safety boundaries](../hosted-agents/README.md#scope-and-safety-boundaries), [agent access beyond defaults](https://learn.microsoft.com/azure/foundry/agents/concepts/hosted-agent-permissions#agent-access-beyond-defaults) | Foundry provides these by default. Grant explicit least-privilege roles for any other Azure service an agent needs. |
| The person who runs the sample index script, only while loading or removing the sample index | Search Service Contributor and Search Index Data Contributor, temporarily | The Search service | [Knowledge retrieval design](knowledge-retrieval.md#identity-and-rbac) | Creating, loading, and removing the sample index, and reading it back with `verify`. The dev pilot's index exists, and these roles were removed after its load on 2026-10-01, so no one needs them today. Grant them again only to change or remove the index, and remove them afterward. |
| Portal users who view traces | Monitoring Reader, per Microsoft Learn. Log Analytics Reader on the workspace to query it directly. | The Application Insights component that the monitoring root creates | [Agent monitoring](../terraform/monitoring/README.md#at-a-glance), [viewing telemetry data](https://learn.microsoft.com/azure/foundry/agents/concepts/hosted-agent-permissions#viewing-telemetry-data) | Viewing traces from the private network. Per Microsoft Learn, Foundry User shows metrics but not traces. |
| Identity running monitoring Terraform | Monitoring resource and project-connection permissions, plus scoped RBAC administration for the publisher assignments; no role is named | Confirmed from source: the platform resource group, the Foundry project for the connection, and the new Application Insights component for the publisher grants ([`terraform/monitoring/main.tf`](../terraform/monitoring/main.tf): `azapi_resource.insights`, `azapi_resource.connection`, `azapi_resource.publisher`) | [Monitoring deployment](../terraform/monitoring/README.md#deployment) | Creating the component, the connection, and the publisher grants. An authorized administrator can create the grants and import them instead. |
| Identity running Bastion Terraform | Permission to manage the Bastion host, subnet, and public IP; no role is named | Confirmed from source: the platform resource group, including the subnet in its management virtual network ([`terraform/bastion/main.tf`](../terraform/bastion/main.tf): `azapi_resource.subnet`, `azapi_resource.public_ip`, `azapi_resource.bastion`) | [Bastion upgrade](../terraform/bastion/README.md#existing-host-upgrade) | Adopting or creating the three Bastion resources. |
| Live evaluation runner | Foundry User, plus any permissions the chosen preview feature needs | The Foundry project | [Evaluation environment](evaluation-live-run.md#prepare-an-isolated-evaluation-environment) | Reading inventory, invoking agents and models, and managing evaluators and runs. |
| Review API callers | A delegated or application permission with consent, plus the caller and client allowlists | The Microsoft Entra ID API registration | [Publication prerequisites](apim-review-api.md#publication-prerequisites) | Getting a token that APIM accepts. This isn't an Azure role, and Terraform doesn't create it. |

## Foundry User and Foundry Project Manager

The publishing guides ask for Foundry Project Manager, but Terraform gives the
Lab identity and the platform deployer Foundry User. The dev Lab identity also
got Foundry Project Manager by hand on 2026-09-23; see
[Grants made by hand in the dev Lab](#grants-made-by-hand-in-the-dev-lab).

- **Same data actions.** Per Microsoft Learn, both roles have the
  `Microsoft.CognitiveServices/*` data actions. Foundry Project Manager adds
  project management and can assign only the Foundry User role
  ([Foundry User](https://learn.microsoft.com/azure/role-based-access-control/built-in-roles/ai-machine-learning#foundry-user),
  [Foundry Project Manager](https://learn.microsoft.com/azure/role-based-access-control/built-in-roles/ai-machine-learning#foundry-project-manager)).
- **What Foundry User covers.** Per Microsoft Learn, Foundry User at project
  scope can create agent versions, update endpoint routing, and call agent
  endpoints ([create a new agent version](https://learn.microsoft.com/azure/foundry/agents/concepts/hosted-agent-permissions#create-a-new-agent-version),
  [update the agent](https://learn.microsoft.com/azure/foundry/agents/concepts/hosted-agent-permissions#update-the-agent-to-use-the-new-version)).
- **Why the guides ask for more.** Per Microsoft Learn, publishing needs Foundry
  Project Manager "plus the ability to create role assignments for the
  platform-created agent identity if needed"
  ([Deploy a hosted agent](https://learn.microsoft.com/azure/foundry/agents/how-to/deploy-hosted-agent#required-permissions)).
- **What this repository's publishers call.** Confirmed from source: the
  functions in [`hosted-agents/deployment.py`](../hosted-agents/deployment.py)
  and `FoundryPublisher` in
  [`workbench/agent_publisher.py`](../workbench/agent_publisher.py) only read
  deployments and agents, create code-based versions, update endpoint routing,
  delete versions or agents, and call agent responses. Neither creates role
  assignments or pushes images.

So per Microsoft Learn, Foundry User covers the calls that created-agent
publication makes, and the deployer's Foundry User covers the same calls in
`deployment.py`. Foundry Project Manager is still the documented role for
publishing hosted agents. See [unconfirmed items](#unconfirmed-items).

### Test whether the Lab needs Foundry Project Manager

**Status:** not run. [#128](https://github.com/michael-rechani/foundry-agent-accelerator/issues/128) tracks it.

The dev Lab identity got Foundry Project Manager by hand on 2026-09-23. While
it holds that role, a test can't show whether Foundry User alone is enough. One
real test agent settles it. Get the environment owner's approval first, because
a created agent keeps billing until it's deleted.

1. Remove Foundry Project Manager from the Lab identity at the Foundry project.
   Wait at least 15 minutes for the change to apply.
2. The person who holds the operator key opens the private Lab, creates one
   agent from a fictional sample, sends it the sample, and deletes it. Only that
   person types the key.
3. Confirm that no created agent remains in the Lab or in Foundry.

If publication succeeds, leave the role removed and update this page. If it
reports [`operator_permissions_required`](agent-creation.md#troubleshooting),
wait about 10 minutes and try once more. If it still fails, assign the role
again, record that the Lab needs it, and add it to Terraform:

```powershell
az role assignment create --assignee-object-id <Lab identity principal ID> --assignee-principal-type ServicePrincipal --role eadc314b-1a2d-4efa-be10-5d325db5065e --scope <Foundry project resource ID> --description "Foundry Lab agent creation"
```

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
  [Lab prerequisites](lab-deployment.md#1-confirm-prerequisites-and-state-ownership).
- Give each hosted agent's own identity only the data-plane roles it needs.
  See [production considerations](../terraform/README.md#separately-scoped-production-considerations).
- To read a single secret, grant Key Vault Secrets User at secret scope rather
  than Key Vault Secrets Officer on the vault. Per Microsoft Learn, Secrets User
  only reads secret contents. The Lab's `agent_creation_key_secret_resource_id`
  assigns it that way. Turn on `deployer_key_vault_secrets_officer` only if the
  deployer manages secrets in that vault.
- Scope agent-to-agent access to the agents being called.
  `coordinator_agent_access` assigns Foundry Agent Consumer on each specialist
  agent, not the project.

## Unconfirmed items

These couldn't be confirmed from the repository or Microsoft Learn. Check them
before relying on the tables.

- **Whether Foundry User alone publishes hosted agents.** Per Microsoft Learn,
  the hosted-agent permissions page says Foundry User can create versions and
  update routing, but the deployment pages ask for Foundry Project Manager.
  The [Foundry RBAC table](https://learn.microsoft.com/azure/foundry/concepts/rbac-foundry#permissions-for-each-built-in-role)
  also marks **Publish agents** as not allowed for Foundry User. Neither the
  Lab's publication nor `deployment.py` has been tested with Foundry User only.
  The dev Lab identity also got Foundry Project Manager by hand on 2026-09-23,
  so a test there can't separate the two roles until it's removed. See
  [Test whether the Lab needs Foundry Project Manager](#test-whether-the-lab-needs-foundry-project-manager).
- **Whether the coordinator needs its grant, and whether the grant applies.**
  Per Microsoft Learn, an agent's default access covers model inference and
  session storage. Learn doesn't say whether that covers calling another agent
  in the same project. `coordinator_agent_access` is off by default for that
  reason. Also untested: whether Azure Resource Manager accepts the
  agent-scope assignment that `azapi_resource.coordinator_agent_consumer`
  creates. Learn shows `az role assignment create` at that scope
  ([agent-scope role assignments](https://learn.microsoft.com/azure/foundry/concepts/rbac-foundry#agent-scope-role-assignments)).
  If it's rejected, per Microsoft Learn the same role can be assigned at
  project scope instead
  ([agent interaction](https://learn.microsoft.com/azure/foundry/agents/concepts/hosted-agent-permissions#agent-interaction)),
  which lets the coordinator call every agent in the project.
- **What breaks without the two Cosmos DB assignments.** Microsoft Learn lists
  Cosmos DB Operator and Cosmos DB Built-in Data Contributor as project identity
  roles but gives no symptom for either.
- **Storage Account Contributor for the project identity.** Per Microsoft
  Learn, standard setup gives the project identity Storage Account Contributor
  on the storage account. The pinned module doesn't assign it. Whether the
  capability host needs it isn't confirmed.
- **Built-in roles for Lab, Bastion, and monitoring operators.** The scopes
  above are confirmed from source. The guides don't name a role for these
  identities.
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

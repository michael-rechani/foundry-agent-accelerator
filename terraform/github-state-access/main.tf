locals {
  environment_name = "terraform-state"
  identity_name    = "foundry-lab-terraform-state"
  container_id     = "${var.storage_account_id}/blobServices/default/containers/${var.container_name}"
  storage_name     = split("/", var.storage_account_id)[8]
  github_owner     = split("/", var.github_repository)[0]
  github_name      = split("/", var.github_repository)[1]
  state_prefix     = "ai-foundry/"
}

data "azuread_client_config" "current" {}
data "github_user" "owner" {
  username = local.github_owner
}
data "github_repository" "this" {
  full_name = var.github_repository
}

resource "azuread_application" "state" {
  display_name            = local.identity_name
  prevent_duplicate_names = true
  owners                  = [data.azuread_client_config.current.object_id]
}

resource "azuread_service_principal" "state" {
  client_id = azuread_application.state.client_id
  owners    = [data.azuread_client_config.current.object_id]
}

resource "azuread_application_federated_identity_credential" "state" {
  application_id = azuread_application.state.id
  display_name   = "github-terraform-state"
  issuer         = "https://token.actions.githubusercontent.com"
  subject        = "repo:${local.github_owner}@${data.github_user.owner.id}/${local.github_name}@${data.github_repository.this.repo_id}:environment:${local.environment_name}"
  audiences      = ["api://AzureADTokenExchange"]
}

resource "azurerm_role_definition" "state" {
  name        = "Lab Terraform state blob operator"
  scope       = var.storage_account_id
  description = "Blob content and lease access only; no container, account, network, infrastructure or RBAC writes."
  permissions {
    actions = ["Microsoft.Storage/storageAccounts/blobServices/containers/read"]
    data_actions = [
      "Microsoft.Storage/storageAccounts/blobServices/containers/blobs/read",
      "Microsoft.Storage/storageAccounts/blobServices/containers/blobs/write",
      "Microsoft.Storage/storageAccounts/blobServices/containers/blobs/delete",
      "Microsoft.Storage/storageAccounts/blobServices/containers/blobs/add/action",
    ]
  }
  assignable_scopes = [var.storage_account_id]
}

resource "azurerm_role_assignment" "state" {
  scope              = local.container_id
  principal_id       = azuread_service_principal.state.object_id
  principal_type     = "ServicePrincipal"
  role_definition_id = azurerm_role_definition.state.role_definition_resource_id
  condition_version  = "2.0"
  condition          = <<-CONDITION
    (
      (
        !(ActionMatches{'Microsoft.Storage/storageAccounts/blobServices/containers/blobs/read'})
        AND !(ActionMatches{'Microsoft.Storage/storageAccounts/blobServices/containers/blobs/write'})
        AND !(ActionMatches{'Microsoft.Storage/storageAccounts/blobServices/containers/blobs/delete'})
        AND !(ActionMatches{'Microsoft.Storage/storageAccounts/blobServices/containers/blobs/add/action'})
      )
      OR
      @Resource[Microsoft.Storage/storageAccounts/blobServices/containers/blobs:path] StringStartsWith '${local.state_prefix}'
      OR
      (
        ActionMatches{'Microsoft.Storage/storageAccounts/blobServices/containers/blobs/read'}
        AND SubOperationMatches{'Blob.List'}
        AND @Request[Microsoft.Storage/storageAccounts/blobServices/containers/blobs:prefix] StringStartsWith '${local.state_prefix}'
      )
    )
  CONDITION
}

resource "github_repository_environment" "state" {
  repository          = local.github_name
  environment         = local.environment_name
  prevent_self_review = false
  reviewers {
    users = var.reviewer_user_ids
  }
  deployment_branch_policy {
    protected_branches     = false
    custom_branch_policies = true
  }
}

resource "github_repository_environment_deployment_policy" "state" {
  repository     = local.github_name
  environment    = github_repository_environment.state.environment
  branch_pattern = "main"
}

resource "github_actions_environment_variable" "state" {
  for_each = {
    AZURE_CLIENT_ID           = azuread_application.state.client_id
    AZURE_TENANT_ID           = data.azuread_client_config.current.tenant_id
    AZURE_SUBSCRIPTION_ID     = var.subscription_id
    TF_STATE_ACCOUNT          = local.storage_name
    TF_STATE_CONTAINER        = var.container_name
    TF_STATE_PREFIX           = local.state_prefix
    TF_STATE_PRIVATE_ENDPOINT = var.private_endpoint_ip
  }
  repository    = local.github_name
  environment   = github_repository_environment.state.environment
  variable_name = each.key
  value         = each.value
}

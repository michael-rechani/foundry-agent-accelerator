data "azuread_client_config" "current" {}

data "terraform_remote_state" "lab" {
  count   = var.lab_state == null ? 0 : 1
  backend = "azurerm"
  config = {
    subscription_id      = var.lab_state.subscription_id
    resource_group_name  = var.lab_state.resource_group_name
    storage_account_name = var.lab_state.storage_account_name
    container_name       = var.lab_state.container_name
    key                  = var.lab_state.key
    use_azuread_auth     = true
    use_cli              = true
  }
}

data "terraform_remote_state" "runner" {
  count   = var.runner_state == null ? 0 : 1
  backend = "azurerm"
  config = {
    subscription_id      = var.runner_state.subscription_id
    resource_group_name  = var.runner_state.resource_group_name
    storage_account_name = var.runner_state.storage_account_name
    container_name       = var.runner_state.container_name
    key                  = var.runner_state.key
    use_azuread_auth     = true
    use_cli              = true
  }
}

data "terraform_remote_state" "platform" {
  count   = var.platform_state == null ? 0 : 1
  backend = "azurerm"
  config = {
    subscription_id      = var.platform_state.subscription_id
    resource_group_name  = var.platform_state.resource_group_name
    storage_account_name = var.platform_state.storage_account_name
    container_name       = var.platform_state.container_name
    key                  = var.platform_state.key
    use_azuread_auth     = true
    use_cli              = true
  }
}

locals {
  lab_outputs      = try(data.terraform_remote_state.lab[0].outputs, {})
  runner_outputs   = try(data.terraform_remote_state.runner[0].outputs, {})
  platform_outputs = try(data.terraform_remote_state.platform[0].outputs, {})

  resource_group_name         = var.resource_group_name != null ? var.resource_group_name : try(local.lab_outputs.resource_group_name, null)
  registry_name               = var.registry_name != null ? var.registry_name : try(local.lab_outputs.registry_name, null)
  container_app_name          = var.container_app_name != null ? var.container_app_name : try(local.lab_outputs.container_app_name, null)
  managed_identity_name       = var.managed_identity_name != null ? var.managed_identity_name : try(local.lab_outputs.managed_identity_name, null)
  runner_resource_group_name  = var.runner_resource_group_name != null ? var.runner_resource_group_name : try(local.runner_outputs.resource_group_name, null)
  runner_vm_name              = var.runner_vm_name != null ? var.runner_vm_name : try(local.runner_outputs.vm_name, null)
  foundry_resource_group_name = var.foundry_resource_group_name != null ? var.foundry_resource_group_name : try(local.platform_outputs.resource_group_name, null)
  foundry_account_name        = var.foundry_account_name != null ? var.foundry_account_name : try(local.platform_outputs.foundry_account_name, null)
  foundry_project_endpoint    = var.foundry_project_endpoint != null ? var.foundry_project_endpoint : try(local.platform_outputs.foundry_project_endpoint, null)

  github_owner = split("/", var.github_repository)[0]
  github_name  = split("/", var.github_repository)[1]

  lab_scope    = "/subscriptions/${var.subscription_id}/resourceGroups/${local.resource_group_name}"
  runner_scope = "/subscriptions/${var.subscription_id}/resourceGroups/${local.runner_resource_group_name}"

  # GitHub signs its token with the owner and repository IDs, so Azure must accept that subject.
  github_owner_id = var.github_owner_type == "organization" ? data.github_organization.owner[0].id : data.github_user.owner[0].id
  subject_prefix  = "repo:${local.github_owner}@${local.github_owner_id}/${local.github_name}@${data.github_repository.this.repo_id}:environment"

  deploy_subject    = coalesce(var.deploy_federated_subject, "${local.subject_prefix}:${var.deploy_environment}")
  recording_subject = coalesce(var.recording_federated_subject, "${local.subject_prefix}:${var.recording_environment}")

  # Foundry User, once named Azure AI User.
  foundry_user_role_id = "/subscriptions/${var.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/53ca6127-db72-4b80-b1b0-d745d6d5456d"
  acr_push_role_id     = "/subscriptions/${var.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/8311e382-0749-4cb8-b61a-304f252e45ec"
}

# Fails the plan with a clear message instead of a provider error on a null name.
resource "terraform_data" "inputs" {
  lifecycle {
    precondition {
      condition = alltrue([
        for value in [
          local.resource_group_name,
          local.registry_name,
          local.container_app_name,
          local.managed_identity_name,
          local.runner_resource_group_name,
          local.runner_vm_name,
        ] : value != null
      ])
      error_message = "Set lab_state and runner_state so Terraform reads the Lab and runner names, or set resource_group_name, registry_name, container_app_name, managed_identity_name, runner_resource_group_name and runner_vm_name yourself."
    }
    precondition {
      condition = !var.enable_library_recording || alltrue([
        for value in [
          local.foundry_resource_group_name,
          local.foundry_account_name,
          local.foundry_project_endpoint,
        ] : value != null
      ])
      error_message = "Library recording needs platform_state, or foundry_resource_group_name, foundry_account_name and foundry_project_endpoint. Set enable_library_recording to false to skip it."
    }
    precondition {
      condition     = !var.enable_library_recording || length(var.recording_reviewer_user_ids) > 0
      error_message = "Set recording_reviewer_user_ids, so every library recording run needs a person's approval first."
    }
  }
}

data "azurerm_client_config" "current" {}

data "azurerm_container_registry" "lab" {
  name                = local.registry_name
  resource_group_name = local.resource_group_name
}

data "azurerm_container_app" "lab" {
  name                = local.container_app_name
  resource_group_name = local.resource_group_name
}

data "azurerm_user_assigned_identity" "lab" {
  name                = local.managed_identity_name
  resource_group_name = local.resource_group_name
}

data "azurerm_virtual_machine" "runner" {
  name                = local.runner_vm_name
  resource_group_name = local.runner_resource_group_name
}

data "azurerm_cognitive_account" "foundry" {
  count               = var.enable_library_recording ? 1 : 0
  name                = local.foundry_account_name
  resource_group_name = local.foundry_resource_group_name
}

data "github_user" "owner" {
  count    = var.github_owner_type == "user" ? 1 : 0
  username = local.github_owner
}

data "github_organization" "owner" {
  count = var.github_owner_type == "organization" ? 1 : 0
  name  = local.github_owner
}

data "github_repository" "this" {
  full_name = var.github_repository
}

# Deploy identity: no secret, only a federated credential for one environment of one repository.
resource "azuread_application" "deploy" {
  display_name            = var.deploy_identity_name
  prevent_duplicate_names = true
  owners                  = [data.azuread_client_config.current.object_id]
}

resource "azuread_service_principal" "deploy" {
  client_id = azuread_application.deploy.client_id
  owners    = [data.azuread_client_config.current.object_id]
}

resource "azuread_application_federated_identity_credential" "deploy" {
  application_id = azuread_application.deploy.id
  display_name   = "github-${var.deploy_environment}"
  issuer         = "https://token.actions.githubusercontent.com"
  subject        = local.deploy_subject
  audiences      = ["api://AzureADTokenExchange"]
}

# Recording identity: calls the Foundry account's models and nothing else.
resource "azuread_application" "recording" {
  count = var.enable_library_recording ? 1 : 0

  display_name            = var.recording_identity_name
  prevent_duplicate_names = true
  owners                  = [data.azuread_client_config.current.object_id]
}

resource "azuread_service_principal" "recording" {
  count = var.enable_library_recording ? 1 : 0

  client_id = azuread_application.recording[0].client_id
  owners    = [data.azuread_client_config.current.object_id]
}

resource "azuread_application_federated_identity_credential" "recording" {
  count = var.enable_library_recording ? 1 : 0

  application_id = azuread_application.recording[0].id
  display_name   = "github-${var.recording_environment}"
  issuer         = "https://token.actions.githubusercontent.com"
  subject        = local.recording_subject
  audiences      = ["api://AzureADTokenExchange"]
}

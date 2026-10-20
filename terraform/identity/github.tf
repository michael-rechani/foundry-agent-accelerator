resource "github_repository_environment" "deploy" {
  repository  = local.github_name
  environment = var.deploy_environment

  deployment_branch_policy {
    protected_branches     = false
    custom_branch_policies = true
  }
}

# Only main may sign in as the deploy identity, so pull request code never reaches the runner.
resource "github_repository_environment_deployment_policy" "deploy" {
  repository     = local.github_name
  environment    = github_repository_environment.deploy.environment
  branch_pattern = "main"
}

resource "github_actions_environment_variable" "deploy" {
  for_each = {
    AZURE_CLIENT_ID           = azuread_application.deploy.client_id
    AZURE_TENANT_ID           = data.azuread_client_config.current.tenant_id
    AZURE_SUBSCRIPTION_ID     = var.subscription_id
    AZURE_RESOURCE_GROUP      = local.resource_group_name
    LAB_REGISTRY              = local.registry_name
    LAB_CONTAINER_APP         = local.container_app_name
    LAB_RUNNER_VM             = local.runner_vm_name
    LAB_RUNNER_RESOURCE_GROUP = local.runner_resource_group_name
  }

  repository    = local.github_name
  environment   = github_repository_environment.deploy.environment
  variable_name = each.key
  value         = each.value
}

resource "github_repository_environment" "recording" {
  count = var.enable_library_recording ? 1 : 0

  repository          = local.github_name
  environment         = var.recording_environment
  prevent_self_review = false

  deployment_branch_policy {
    protected_branches     = false
    custom_branch_policies = true
  }

  reviewers {
    users = var.recording_reviewer_user_ids
  }
}

resource "github_repository_environment_deployment_policy" "recording" {
  count = var.enable_library_recording ? 1 : 0

  repository     = local.github_name
  environment    = github_repository_environment.recording[0].environment
  branch_pattern = "main"
}

resource "github_actions_environment_variable" "recording" {
  for_each = var.enable_library_recording ? {
    AZURE_CLIENT_ID          = azuread_application.recording[0].client_id
    AZURE_TENANT_ID          = data.azuread_client_config.current.tenant_id
    FOUNDRY_PROJECT_ENDPOINT = local.foundry_project_endpoint
  } : {}

  repository    = local.github_name
  environment   = github_repository_environment.recording[0].environment
  variable_name = each.key
  value         = each.value
}

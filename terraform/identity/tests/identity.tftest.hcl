mock_provider "azurerm" {}
mock_provider "azuread" {}
mock_provider "github" {}

override_data {
  target = data.github_user.owner[0]
  values = {
    id = "1001"
  }
}

override_data {
  target = data.github_repository.this
  values = {
    repo_id = 2002
  }
}

override_data {
  target = data.azurerm_container_registry.lab
  values = {
    id = "/subscriptions/00000000-0000-0000-0000-000000000005/resourceGroups/rg-lab/providers/Microsoft.ContainerRegistry/registries/acrlab"
  }
}

override_data {
  target = data.azurerm_container_app.lab
  values = {
    id                           = "/subscriptions/00000000-0000-0000-0000-000000000005/resourceGroups/rg-lab/providers/Microsoft.App/containerApps/lab"
    container_app_environment_id = "/subscriptions/00000000-0000-0000-0000-000000000005/resourceGroups/rg-lab/providers/Microsoft.App/managedEnvironments/cae-lab"
  }
}

override_data {
  target = data.azurerm_user_assigned_identity.lab
  values = {
    id = "/subscriptions/00000000-0000-0000-0000-000000000005/resourceGroups/rg-lab/providers/Microsoft.ManagedIdentity/userAssignedIdentities/id-lab"
  }
}

override_data {
  target = data.azurerm_virtual_machine.runner
  values = {
    id = "/subscriptions/00000000-0000-0000-0000-000000000005/resourceGroups/rg-runner/providers/Microsoft.Compute/virtualMachines/vm-runner"
  }
}

override_data {
  target = data.azurerm_cognitive_account.foundry[0]
  values = {
    id = "/subscriptions/00000000-0000-0000-0000-000000000005/resourceGroups/rg-platform/providers/Microsoft.CognitiveServices/accounts/foundry"
  }
}

override_data {
  target = data.azuread_client_config.current
  values = {
    object_id = "00000000-0000-0000-0000-0000000000aa"
    tenant_id = "00000000-0000-0000-0000-0000000000bb"
  }
}

variables {
  subscription_id             = "00000000-0000-0000-0000-000000000005"
  github_repository           = "example-owner/example-repo"
  resource_group_name         = "rg-lab"
  registry_name               = "acrlab"
  container_app_name          = "lab"
  managed_identity_name       = "id-lab"
  runner_resource_group_name  = "rg-runner"
  runner_vm_name              = "vm-runner"
  foundry_resource_group_name = "rg-platform"
  foundry_account_name        = "foundry"
  foundry_project_endpoint    = "https://foundry.services.ai.azure.com/api/projects/project"
  recording_reviewer_user_ids = [1001]
}

run "deploy_identity_is_keyless_and_limited_to_one_environment" {
  command = plan

  assert {
    condition     = azuread_application_federated_identity_credential.deploy.subject == "repo:example-owner@1001/example-repo@2002:environment:lab-deploy"
    error_message = "The deploy identity must trust only the lab-deploy environment of this repository, using GitHub's owner and repository IDs."
  }
  assert {
    condition     = azuread_application_federated_identity_credential.deploy.issuer == "https://token.actions.githubusercontent.com" && azuread_application_federated_identity_credential.deploy.audiences == tolist(["api://AzureADTokenExchange"])
    error_message = "The deploy identity must trust only GitHub's token issuer."
  }
  assert {
    condition     = azuread_application.deploy.prevent_duplicate_names == true
    error_message = "A second app with the same name must fail instead of being created beside the old one."
  }
}

run "deploy_role_cannot_change_networking_or_roles" {
  command = plan

  assert {
    condition = (
      length([for a in azurerm_role_definition.deployer.permissions[0].actions : a if length(regexall("(?i)roleAssignments|roleDefinitions|networkSecurityGroups|privateEndpoints|virtualNetworks|\\*$", a)) > 0 && a != "Microsoft.App/locations/*/read"]) == 0 &&
      length(azurerm_role_definition.deployer.permissions[0].not_actions) == 0
    )
    error_message = "The deploy role must not hold wildcard, role, or network actions."
  }
  assert {
    condition     = azurerm_role_definition.deployer.name == "Lab image deployer" && azurerm_role_definition.deployer.assignable_scopes == tolist(["/subscriptions/00000000-0000-0000-0000-000000000005/resourceGroups/rg-lab"])
    error_message = "The deploy role keeps its old name and is assignable only inside the Lab resource group."
  }
  assert {
    condition = toset(keys(azurerm_role_assignment.deployer)) == toset(["registry", "app", "environment", "identity"]) && (
      azurerm_role_assignment.deployer["app"].scope == "/subscriptions/00000000-0000-0000-0000-000000000005/resourceGroups/rg-lab/providers/Microsoft.App/containerApps/lab" &&
      azurerm_role_assignment.deployer["environment"].scope == "/subscriptions/00000000-0000-0000-0000-000000000005/resourceGroups/rg-lab/providers/Microsoft.App/managedEnvironments/cae-lab"
    )
    error_message = "The deploy role must be assigned on the registry, the one app, its environment and the Lab identity only."
  }
  assert {
    condition     = azurerm_role_assignment.deployer_acr_push.role_definition_id == "/subscriptions/00000000-0000-0000-0000-000000000005/providers/Microsoft.Authorization/roleDefinitions/8311e382-0749-4cb8-b61a-304f252e45ec" && endswith(azurerm_role_assignment.deployer_acr_push.scope, "registries/acrlab")
    error_message = "AcrPush must be assigned on the registry only."
  }
}

run "runner_starter_can_only_read_and_start_one_vm" {
  command = plan

  assert {
    condition = toset(azurerm_role_definition.runner_starter.permissions[0].actions) == toset([
      "Microsoft.Compute/virtualMachines/read",
      "Microsoft.Compute/virtualMachines/instanceView/read",
      "Microsoft.Compute/virtualMachines/start/action",
    ])
    error_message = "The runner role may only read and start the VM."
  }
  assert {
    condition     = azurerm_role_assignment.runner_starter.scope == "/subscriptions/00000000-0000-0000-0000-000000000005/resourceGroups/rg-runner/providers/Microsoft.Compute/virtualMachines/vm-runner"
    error_message = "The runner role must be assigned on the one VM."
  }
}

run "recording_identity_calls_only_the_foundry_account" {
  command = plan

  assert {
    condition     = azuread_application_federated_identity_credential.recording[0].subject == "repo:example-owner@1001/example-repo@2002:environment:library-recording"
    error_message = "The recording identity must trust only the library-recording environment."
  }
  assert {
    condition     = azurerm_role_assignment.recording_foundry_user[0].role_definition_id == "/subscriptions/00000000-0000-0000-0000-000000000005/providers/Microsoft.Authorization/roleDefinitions/53ca6127-db72-4b80-b1b0-d745d6d5456d" && endswith(azurerm_role_assignment.recording_foundry_user[0].scope, "accounts/foundry")
    error_message = "The recording identity holds Foundry User on the one account and nothing else."
  }
  assert {
    condition     = length(azurerm_role_assignment.recording_foundry_user) == 1
    error_message = "The recording identity must hold exactly one role assignment."
  }
  assert {
    condition     = toset(github_repository_environment.recording[0].reviewers[0].users) == toset([1001])
    error_message = "Recording runs must wait for a named reviewer."
  }
}

run "environments_are_limited_to_main" {
  command = plan

  assert {
    condition = (
      github_repository_environment.deploy.deployment_branch_policy[0].custom_branch_policies == true &&
      github_repository_environment.deploy.deployment_branch_policy[0].protected_branches == false &&
      github_repository_environment_deployment_policy.deploy.branch_pattern == "main" &&
      github_repository_environment_deployment_policy.recording[0].branch_pattern == "main"
    )
    error_message = "Both environments may deploy only from main."
  }
}

run "environment_variables_carry_names_not_secrets" {
  command = plan

  assert {
    condition = toset(keys(github_actions_environment_variable.deploy)) == toset([
      "AZURE_CLIENT_ID", "AZURE_TENANT_ID", "AZURE_SUBSCRIPTION_ID", "AZURE_RESOURCE_GROUP",
      "LAB_REGISTRY", "LAB_CONTAINER_APP", "LAB_RUNNER_VM", "LAB_RUNNER_RESOURCE_GROUP",
    ])
    error_message = "The deploy environment must receive exactly the variables deploy-lab.yml reads."
  }
  assert {
    condition     = toset(keys(github_actions_environment_variable.recording)) == toset(["AZURE_CLIENT_ID", "AZURE_TENANT_ID", "FOUNDRY_PROJECT_ENDPOINT"])
    error_message = "The recording environment must receive exactly the variables record-library-answers.yml reads."
  }
}

run "recording_needs_a_reviewer" {
  command = plan

  variables {
    recording_reviewer_user_ids = []
  }

  expect_failures = [terraform_data.inputs]
}

run "recording_can_be_turned_off" {
  command = plan

  variables {
    enable_library_recording    = false
    recording_reviewer_user_ids = []
  }

  assert {
    condition = (
      length(azuread_application.recording) == 0 &&
      length(azurerm_role_assignment.recording_foundry_user) == 0 &&
      length(github_repository_environment.recording) == 0 &&
      length(github_actions_environment_variable.recording) == 0
    )
    error_message = "Turning recording off must create no recording identity, role, environment or variable."
  }
}

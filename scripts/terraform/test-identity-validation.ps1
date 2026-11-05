param(
    [string]$TerraformCommand = 'terraform'
)

$ErrorActionPreference = 'Stop'
$repository = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$identity = Join-Path (Join-Path $repository 'terraform') 'identity'
$temporary = Join-Path ([IO.Path]::GetTempPath()) ('identity-contracts-' + [guid]::NewGuid().ToString('N'))
$savedEnvironment = [System.Collections.Generic.Dictionary[string, string]]::new([StringComparer]::Ordinal)
$environmentIsolated = $false

New-Item -ItemType Directory -Path $temporary | Out-Null
try {
    Get-ChildItem -LiteralPath $identity -Filter '*.tf' -File |
        Copy-Item -Destination $temporary
    $lockFile = Join-Path $identity '.terraform.lock.hcl'
    if (Test-Path -LiteralPath $lockFile) {
        Copy-Item -LiteralPath $lockFile -Destination $temporary
    }

    $tests = @'
mock_provider "azurerm" {}
mock_provider "azuread" {}
mock_provider "github" {}

override_data {
  target = data.github_user.owner[0]
  values = { id = "1001" }
}

override_data {
  target = data.github_organization.owner[0]
  values = { id = "3003" }
}

override_data {
  target = data.github_repository.this
  values = { repo_id = 2002 }
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

override_resource {
  target = azuread_application.deploy
  values = {
    id        = "/applications/00000000-0000-0000-0000-000000000011"
    client_id = "00000000-0000-0000-0000-000000000011"
  }
  override_during = plan
}

override_resource {
  target = azuread_application.recording[0]
  values = {
    id        = "/applications/00000000-0000-0000-0000-000000000012"
    client_id = "00000000-0000-0000-0000-000000000012"
  }
  override_during = plan
}

override_resource {
  target          = azuread_service_principal.deploy
  values          = { object_id = "00000000-0000-0000-0000-000000000021" }
  override_during = plan
}

override_resource {
  target          = azuread_service_principal.recording[0]
  values          = { object_id = "00000000-0000-0000-0000-000000000022" }
  override_during = plan
}

override_resource {
  target = azurerm_role_definition.deployer
  values = {
    role_definition_resource_id = "/subscriptions/00000000-0000-0000-0000-000000000005/providers/Microsoft.Authorization/roleDefinitions/00000000-0000-0000-0000-000000000031"
  }
  override_during = plan
}

override_resource {
  target = azurerm_role_definition.runner_starter
  values = {
    role_definition_resource_id = "/subscriptions/00000000-0000-0000-0000-000000000005/providers/Microsoft.Authorization/roleDefinitions/00000000-0000-0000-0000-000000000032"
  }
  override_during = plan
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
  foundry_project_endpoint    = "https://foundry.example.invalid/api/projects/example"
  recording_reviewer_user_ids = [1001]
}

run "deploy_identity_trusts_one_repository_environment" {
  command = plan

  assert {
    condition = (
      azuread_application_federated_identity_credential.deploy.subject == "repo:example-owner@1001/example-repo@2002:environment:lab-deploy" &&
      azuread_application_federated_identity_credential.deploy.issuer == "https://token.actions.githubusercontent.com" &&
      toset(azuread_application_federated_identity_credential.deploy.audiences) == toset(["api://AzureADTokenExchange"]) &&
      azuread_application_federated_identity_credential.deploy.application_id == azuread_application.deploy.id &&
      azuread_service_principal.deploy.client_id == azuread_application.deploy.client_id &&
      azuread_application.deploy.prevent_duplicate_names
    )
    error_message = "The keyless deploy identity must trust only the ID-qualified Lab deployment environment."
  }
}

run "deployer_permissions_and_assignments_are_scoped" {
  command = plan

  assert {
    condition = (
      length(azurerm_role_definition.deployer.permissions) == 1 &&
      toset(azurerm_role_definition.deployer.permissions[0].actions) == toset([
        "Microsoft.ContainerRegistry/registries/read",
        "Microsoft.ContainerRegistry/registries/importImage/action",
        "Microsoft.App/containerApps/read",
        "Microsoft.App/containerApps/write",
        "Microsoft.App/containerApps/revisions/read",
        "Microsoft.App/managedEnvironments/read",
        "Microsoft.App/managedEnvironments/join/action",
        "Microsoft.App/locations/*/read",
        "Microsoft.ManagedIdentity/userAssignedIdentities/read",
        "Microsoft.ManagedIdentity/userAssignedIdentities/assign/action",
      ]) &&
      length(azurerm_role_definition.deployer.permissions[0].not_actions) == 0 &&
      length(coalesce(azurerm_role_definition.deployer.permissions[0].data_actions, [])) == 0 &&
      length(coalesce(azurerm_role_definition.deployer.permissions[0].not_data_actions, [])) == 0 &&
      azurerm_role_definition.deployer.name == "Lab image deployer" &&
      azurerm_role_definition.deployer.scope == "/subscriptions/00000000-0000-0000-0000-000000000005/resourceGroups/rg-lab" &&
      toset(azurerm_role_definition.deployer.assignable_scopes) == toset(["/subscriptions/00000000-0000-0000-0000-000000000005/resourceGroups/rg-lab"])
    )
    error_message = "The deploy role must retain its exact reviewed actions and Lab-only assignable scope."
  }
  assert {
    condition = (
      toset(keys(azurerm_role_assignment.deployer)) == toset(["registry", "app", "environment", "identity"]) &&
      azurerm_role_assignment.deployer["registry"].scope == data.azurerm_container_registry.lab.id &&
      azurerm_role_assignment.deployer["app"].scope == data.azurerm_container_app.lab.id &&
      azurerm_role_assignment.deployer["environment"].scope == data.azurerm_container_app.lab.container_app_environment_id &&
      azurerm_role_assignment.deployer["identity"].scope == data.azurerm_user_assigned_identity.lab.id &&
      alltrue([
        for assignment in values(azurerm_role_assignment.deployer) :
        assignment.role_definition_id == azurerm_role_definition.deployer.role_definition_resource_id &&
        assignment.principal_id == azuread_service_principal.deploy.object_id &&
        assignment.principal_type == "ServicePrincipal"
      ]) &&
      azurerm_role_assignment.deployer_acr_push.scope == data.azurerm_container_registry.lab.id &&
      azurerm_role_assignment.deployer_acr_push.role_definition_id == "/subscriptions/00000000-0000-0000-0000-000000000005/providers/Microsoft.Authorization/roleDefinitions/8311e382-0749-4cb8-b61a-304f252e45ec" &&
      azurerm_role_assignment.deployer_acr_push.principal_id == azuread_service_principal.deploy.object_id &&
      azurerm_role_assignment.deployer_acr_push.principal_type == "ServicePrincipal"
    )
    error_message = "Deploy assignments must cover only the one registry, app, app environment and managed identity."
  }
}

run "runner_starter_is_limited_to_one_vm" {
  command = plan

  assert {
    condition = (
      length(azurerm_role_definition.runner_starter.permissions) == 1 &&
      toset(azurerm_role_definition.runner_starter.permissions[0].actions) == toset([
        "Microsoft.Compute/virtualMachines/read",
        "Microsoft.Compute/virtualMachines/instanceView/read",
        "Microsoft.Compute/virtualMachines/start/action",
      ]) &&
      length(azurerm_role_definition.runner_starter.permissions[0].not_actions) == 0 &&
      length(coalesce(azurerm_role_definition.runner_starter.permissions[0].data_actions, [])) == 0 &&
      length(coalesce(azurerm_role_definition.runner_starter.permissions[0].not_data_actions, [])) == 0 &&
      azurerm_role_definition.runner_starter.name == "Lab runner starter" &&
      azurerm_role_definition.runner_starter.scope == data.azurerm_virtual_machine.runner.id &&
      toset(azurerm_role_definition.runner_starter.assignable_scopes) == toset([data.azurerm_virtual_machine.runner.id]) &&
      azurerm_role_assignment.runner_starter.scope == data.azurerm_virtual_machine.runner.id &&
      azurerm_role_assignment.runner_starter.role_definition_id == azurerm_role_definition.runner_starter.role_definition_resource_id &&
      azurerm_role_assignment.runner_starter.principal_id == azuread_service_principal.deploy.object_id &&
      azurerm_role_assignment.runner_starter.principal_type == "ServicePrincipal"
    )
    error_message = "The runner starter may only read and start the one configured VM."
  }
}

run "recording_requires_a_reviewer_and_one_foundry_account" {
  command = plan

  assert {
    condition = (
      azuread_application_federated_identity_credential.recording[0].subject == "repo:example-owner@1001/example-repo@2002:environment:library-recording" &&
      azuread_application_federated_identity_credential.recording[0].issuer == "https://token.actions.githubusercontent.com" &&
      toset(azuread_application_federated_identity_credential.recording[0].audiences) == toset(["api://AzureADTokenExchange"]) &&
      azuread_application_federated_identity_credential.recording[0].application_id == azuread_application.recording[0].id &&
      azuread_service_principal.recording[0].client_id == azuread_application.recording[0].client_id &&
      azurerm_role_assignment.recording_foundry_user[0].scope == data.azurerm_cognitive_account.foundry[0].id &&
      azurerm_role_assignment.recording_foundry_user[0].role_definition_id == "/subscriptions/00000000-0000-0000-0000-000000000005/providers/Microsoft.Authorization/roleDefinitions/53ca6127-db72-4b80-b1b0-d745d6d5456d" &&
      azurerm_role_assignment.recording_foundry_user[0].principal_id == azuread_service_principal.recording[0].object_id &&
      azurerm_role_assignment.recording_foundry_user[0].principal_type == "ServicePrincipal" &&
      toset(github_repository_environment.recording[0].reviewers[0].users) == toset([1001])
    )
    error_message = "Recording must use its own environment, one Foundry account and an explicit reviewer."
  }
}

run "environments_only_allow_main" {
  command = plan

  assert {
    condition = (
      github_repository_environment.deploy.deployment_branch_policy[0].custom_branch_policies &&
      !github_repository_environment.deploy.deployment_branch_policy[0].protected_branches &&
      github_repository_environment.recording[0].deployment_branch_policy[0].custom_branch_policies &&
      !github_repository_environment.recording[0].deployment_branch_policy[0].protected_branches &&
      github_repository_environment_deployment_policy.deploy.branch_pattern == "main" &&
      github_repository_environment_deployment_policy.recording[0].branch_pattern == "main"
    )
    error_message = "Both GitHub environments must allow only their explicit main-branch policy."
  }
}

run "environment_variables_are_the_expected_nonsecret_names" {
  command = plan

  assert {
    condition = (
      toset(keys(github_actions_environment_variable.deploy)) == toset([
        "AZURE_CLIENT_ID", "AZURE_TENANT_ID", "AZURE_SUBSCRIPTION_ID", "AZURE_RESOURCE_GROUP",
        "LAB_REGISTRY", "LAB_CONTAINER_APP", "LAB_RUNNER_VM", "LAB_RUNNER_RESOURCE_GROUP",
      ]) &&
      toset(keys(github_actions_environment_variable.recording)) == toset([
        "AZURE_CLIENT_ID", "AZURE_TENANT_ID", "FOUNDRY_PROJECT_ENDPOINT",
      ]) &&
      github_actions_environment_variable.deploy["AZURE_CLIENT_ID"].value == azuread_application.deploy.client_id &&
      github_actions_environment_variable.deploy["AZURE_TENANT_ID"].value == data.azuread_client_config.current.tenant_id &&
      github_actions_environment_variable.recording["AZURE_CLIENT_ID"].value == azuread_application.recording[0].client_id &&
      github_actions_environment_variable.recording["AZURE_TENANT_ID"].value == data.azuread_client_config.current.tenant_id &&
      github_actions_environment_variable.recording["FOUNDRY_PROJECT_ENDPOINT"].value == var.foundry_project_endpoint
    )
    error_message = "The environments must expose only the expected nonsecret workflow variables."
  }
}

run "custom_environment_names_follow_the_credentials" {
  command = plan

  variables {
    deploy_environment    = "test-deploy"
    recording_environment = "test-recording"
  }
  assert {
    condition = (
      github_repository_environment.deploy.environment == "test-deploy" &&
      github_repository_environment.recording[0].environment == "test-recording" &&
      azuread_application_federated_identity_credential.deploy.subject == "repo:example-owner@1001/example-repo@2002:environment:test-deploy" &&
      azuread_application_federated_identity_credential.recording[0].subject == "repo:example-owner@1001/example-repo@2002:environment:test-recording"
    )
    error_message = "Custom environment names must remain bound to the corresponding GitHub credentials."
  }
}

run "organization_subject_uses_the_organization_id" {
  command = plan

  variables {
    github_owner_type = "organization"
  }
  assert {
    condition     = azuread_application_federated_identity_credential.deploy.subject == "repo:example-owner@3003/example-repo@2002:environment:lab-deploy"
    error_message = "An organization-owned repository must use its organization ID in the federated subject."
  }
}

run "explicit_subject_overrides_are_respected" {
  command = plan

  variables {
    deploy_federated_subject    = "repo:example-owner/example-repo:environment:lab-deploy"
    recording_federated_subject = "repo:example-owner/example-repo:environment:library-recording"
  }
  assert {
    condition = (
      azuread_application_federated_identity_credential.deploy.subject == var.deploy_federated_subject &&
      azuread_application_federated_identity_credential.recording[0].subject == var.recording_federated_subject
    )
    error_message = "Explicitly configured federation subjects must override the generated defaults."
  }
}

run "recording_needs_a_reviewer" {
  command = plan

  variables {
    recording_reviewer_user_ids = []
  }
  expect_failures = [terraform_data.inputs]
}

run "recording_can_be_disabled" {
  command = plan

  variables {
    enable_library_recording    = false
    recording_reviewer_user_ids = []
  }
  assert {
    condition = (
      length(azuread_application.recording) == 0 &&
      length(azuread_service_principal.recording) == 0 &&
      length(azuread_application_federated_identity_credential.recording) == 0 &&
      length(data.azurerm_cognitive_account.foundry) == 0 &&
      length(azurerm_role_assignment.recording_foundry_user) == 0 &&
      length(github_repository_environment.recording) == 0 &&
      length(github_repository_environment_deployment_policy.recording) == 0 &&
      length(github_actions_environment_variable.recording) == 0
    )
    error_message = "Disabling recording must omit all of its identity, permissions and GitHub environment."
  }
}

run "reject_invalid_subscription" {
  command = plan

  variables {
    subscription_id = "not-a-subscription"
  }
  expect_failures = [var.subscription_id]
}

run "reject_invalid_repository" {
  command = plan

  variables {
    github_repository = "bad owner/example-repo"
  }
  expect_failures = [var.github_repository]
}

run "reject_invalid_owner_type" {
  command = plan

  variables {
    github_owner_type = "unknown"
  }
  expect_failures = [var.github_owner_type]
}
'@
    Set-Content -LiteralPath (Join-Path $temporary 'identity.tftest.hcl') -Value $tests

    foreach ($entry in Get-ChildItem Env:) {
        if ($entry.Name -match '^(TF_VAR_|TF_CLI_ARGS|ARM_|AZURE_)' -or
            $entry.Name -in @('GITHUB_TOKEN', 'GH_TOKEN', 'TF_DATA_DIR', 'TF_INPUT', 'TF_PLUGIN_CACHE_DIR')) {
            $savedEnvironment[$entry.Name] = $entry.Value
        }
    }
    $environmentIsolated = $true
    foreach ($name in $savedEnvironment.Keys) {
        [Environment]::SetEnvironmentVariable($name, $null, 'Process')
    }
    $providerCache = Join-Path (Join-Path $identity '.terraform') 'providers'
    if ($savedEnvironment.ContainsKey('TF_PLUGIN_CACHE_DIR')) {
        $env:TF_PLUGIN_CACHE_DIR = $savedEnvironment['TF_PLUGIN_CACHE_DIR']
    } elseif (Test-Path -LiteralPath $providerCache -PathType Container) {
        $env:TF_PLUGIN_CACHE_DIR = $providerCache
    }
    $env:TF_INPUT = '0'
    $env:ARM_USE_CLI = 'false'
    $env:ARM_USE_MSI = 'false'
    $env:ARM_USE_OIDC = 'false'

    & $TerraformCommand "-chdir=$temporary" init -backend=false -input=false -no-color
    if ($LASTEXITCODE -ne 0) { throw 'Isolated identity test initialization failed.' }
    & $TerraformCommand "-chdir=$temporary" test -no-color
    if ($LASTEXITCODE -ne 0) { throw 'Identity role or environment contract tests failed.' }
} finally {
    if ($environmentIsolated) {
        foreach ($name in @('TF_INPUT', 'ARM_USE_CLI', 'ARM_USE_MSI', 'ARM_USE_OIDC', 'TF_PLUGIN_CACHE_DIR')) {
            [Environment]::SetEnvironmentVariable($name, $null, 'Process')
        }
        foreach ($name in $savedEnvironment.Keys) {
            [Environment]::SetEnvironmentVariable($name, $savedEnvironment[$name], 'Process')
        }
    }
    for ($attempt = 0; $attempt -lt 5; $attempt++) {
        try {
            Remove-Item -LiteralPath $temporary -Recurse -Force -ErrorAction Stop
            break
        } catch [System.UnauthorizedAccessException], [System.IO.IOException] {
            if ($attempt -eq 4) { throw }
            Start-Sleep -Milliseconds (250 * ($attempt + 1))
        }
    }
}

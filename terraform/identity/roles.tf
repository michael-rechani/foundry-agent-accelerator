# The roles use the names the old setup scripts used, so an identity created by them is imported, not duplicated.

resource "azurerm_role_definition" "deployer" {
  name        = "Lab image deployer"
  scope       = local.lab_scope
  description = "Import a release image into the Lab registry and roll the Lab Container App to it. No network, role or secret changes."

  permissions {
    actions = [
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
    ]
    not_actions = []
  }

  assignable_scopes = [local.lab_scope]
}

resource "azurerm_role_assignment" "deployer" {
  for_each = {
    registry    = data.azurerm_container_registry.lab.id
    app         = data.azurerm_container_app.lab.id
    environment = data.azurerm_container_app.lab.container_app_environment_id
    identity    = data.azurerm_user_assigned_identity.lab.id
  }

  scope              = each.value
  role_definition_id = azurerm_role_definition.deployer.role_definition_resource_id
  principal_id       = azuread_service_principal.deploy.object_id
  principal_type     = "ServicePrincipal"
}

# The workflow builds on the private runner and pushes the image straight to the registry.
resource "azurerm_role_assignment" "deployer_acr_push" {
  scope              = data.azurerm_container_registry.lab.id
  role_definition_id = local.acr_push_role_id
  principal_id       = azuread_service_principal.deploy.object_id
  principal_type     = "ServicePrincipal"
}

resource "azurerm_role_definition" "runner_starter" {
  name        = "Lab runner starter"
  scope       = data.azurerm_virtual_machine.runner.id
  description = "Read and start the one CI runner VM. No stop, delete, change or run-command access."

  permissions {
    actions = [
      "Microsoft.Compute/virtualMachines/read",
      "Microsoft.Compute/virtualMachines/instanceView/read",
      "Microsoft.Compute/virtualMachines/start/action",
    ]
    not_actions = []
  }

  assignable_scopes = [data.azurerm_virtual_machine.runner.id]
}

resource "azurerm_role_assignment" "runner_starter" {
  scope              = data.azurerm_virtual_machine.runner.id
  role_definition_id = azurerm_role_definition.runner_starter.role_definition_resource_id
  principal_id       = azuread_service_principal.deploy.object_id
  principal_type     = "ServicePrincipal"
}

resource "azurerm_role_assignment" "recording_foundry_user" {
  count = var.enable_library_recording ? 1 : 0

  scope              = data.azurerm_cognitive_account.foundry[0].id
  role_definition_id = local.foundry_user_role_id
  principal_id       = azuread_service_principal.recording[0].object_id
  principal_type     = "ServicePrincipal"
}

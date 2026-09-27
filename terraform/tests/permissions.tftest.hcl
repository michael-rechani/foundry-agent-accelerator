mock_provider "azurerm" {
  mock_data "azurerm_client_config" {
    defaults = {
      tenant_id       = "00000000-0000-0000-0000-000000000001"
      object_id       = "00000000-0000-0000-0000-000000000002"
      subscription_id = "00000000-0000-0000-0000-000000000003"
    }
  }
  mock_resource "azurerm_subnet" {
    defaults = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000003/resourceGroups/rg-permissions/providers/Microsoft.Network/virtualNetworks/network/subnets/management"
    }
  }
  mock_resource "azurerm_resource_group" {
    defaults = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000003/resourceGroups/rg-permissions"
    }
  }
  mock_resource "azurerm_network_interface" {
    defaults = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000003/resourceGroups/rg-permissions/providers/Microsoft.Network/networkInterfaces/runner"
    }
  }
}

mock_provider "azapi" {
  mock_resource "azapi_resource" {
    defaults = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000003/resourceGroups/rg-permissions/providers/Microsoft.Compute/virtualMachines/runner"
    }
  }
}

override_module {
  target = module.ai_foundry
  outputs = {
    ai_foundry_id                                   = "/subscriptions/00000000-0000-0000-0000-000000000003/resourceGroups/rg-permissions/providers/Microsoft.CognitiveServices/accounts/foundry-permissions"
    ai_foundry_project_id                           = { primary = "/subscriptions/00000000-0000-0000-0000-000000000003/resourceGroups/rg-permissions/providers/Microsoft.CognitiveServices/accounts/foundry-permissions/projects/project-permissions" }
    ai_foundry_project_system_identity_principal_id = { primary = "00000000-0000-0000-0000-000000000004" }
  }
}

override_module {
  target = module.api_management
  outputs = {
    resource = { identity = [{ principal_id = "00000000-0000-0000-0000-000000000005" }] }
  }
}

override_data {
  target = data.azapi_resource.jumpbox_identity
  values = {
    output = { identity = { principalId = "00000000-0000-0000-0000-000000000006" } }
  }
}

variables {
  subscription_id = "00000000-0000-0000-0000-000000000003"
}

run "default_foundry_permissions" {
  command = plan
  plan_options {
    target = [
      azurerm_role_assignment.deployer_foundry_user,
      azurerm_role_assignment.project_foundry_user,
      azurerm_role_assignment.api_management_foundry_user,
      azurerm_role_assignment.jumpbox_foundry_project_manager,
    ]
  }
  assert {
    condition = (
      azurerm_role_assignment.deployer_foundry_user.principal_id == "00000000-0000-0000-0000-000000000002" &&
      azurerm_role_assignment.deployer_foundry_user.role_definition_id == "/subscriptions/00000000-0000-0000-0000-000000000003/providers/Microsoft.Authorization/roleDefinitions/53ca6127-db72-4b80-b1b0-d745d6d5456d" &&
      azurerm_role_assignment.deployer_foundry_user.scope == module.ai_foundry.ai_foundry_project_id["primary"]
    )
    error_message = "The caller must receive Foundry User at project scope only."
  }
  assert {
    condition = (
      azurerm_role_assignment.project_foundry_user.principal_id == "00000000-0000-0000-0000-000000000004" &&
      azurerm_role_assignment.project_foundry_user.principal_type == "ServicePrincipal" &&
      azurerm_role_assignment.project_foundry_user.role_definition_id == "/subscriptions/00000000-0000-0000-0000-000000000003/providers/Microsoft.Authorization/roleDefinitions/53ca6127-db72-4b80-b1b0-d745d6d5456d" &&
      azurerm_role_assignment.project_foundry_user.scope == module.ai_foundry.ai_foundry_id
    )
    error_message = "Evaluation access must remain Foundry User for the project identity at account scope."
  }
  assert {
    condition     = length(azurerm_role_assignment.api_management_foundry_user) == 0 && length(azurerm_role_assignment.jumpbox_foundry_project_manager) == 0
    error_message = "Optional gateway and runner grants must remain absent by default."
  }
}

run "explicit_deployer_and_optional_identities" {
  # The identity read is deferred until the mock VM exists; neither provider calls Azure.
  command = apply
  plan_options {
    target = [
      azurerm_role_assignment.deployer_foundry_user,
      azurerm_role_assignment.api_management_foundry_user,
      azurerm_role_assignment.jumpbox_foundry_project_manager,
    ]
  }
  variables {
    deployment_principal_id        = "00000000-0000-0000-0000-000000000007"
    enable_api_management          = true
    api_management_publisher_email = "operator@example.invalid"
    enable_jumpbox                 = true
    jumpbox_existing_os_disk = {
      id                   = "/subscriptions/00000000-0000-0000-0000-000000000003/resourceGroups/rg-permissions/providers/Microsoft.Compute/disks/existing-os"
      name                 = "existing-os"
      storage_account_type = "Standard_LRS"
    }
  }
  assert {
    condition     = azurerm_role_assignment.deployer_foundry_user.principal_id == var.deployment_principal_id
    error_message = "An explicit deployer must replace the caller, not add another grant."
  }
  assert {
    condition = (
      length(azurerm_role_assignment.api_management_foundry_user) == 1 &&
      azurerm_role_assignment.api_management_foundry_user[0].principal_id == "00000000-0000-0000-0000-000000000005" &&
      azurerm_role_assignment.api_management_foundry_user[0].role_definition_id == "/subscriptions/00000000-0000-0000-0000-000000000003/providers/Microsoft.Authorization/roleDefinitions/53ca6127-db72-4b80-b1b0-d745d6d5456d" &&
      azurerm_role_assignment.api_management_foundry_user[0].scope == module.ai_foundry.ai_foundry_project_id["primary"]
    )
    error_message = "Only the optional APIM identity receives its project-scoped Foundry User grant."
  }
  assert {
    condition = (
      length(azurerm_role_assignment.jumpbox_foundry_project_manager) == 1 &&
      azurerm_role_assignment.jumpbox_foundry_project_manager[0].principal_id == "00000000-0000-0000-0000-000000000006" &&
      azurerm_role_assignment.jumpbox_foundry_project_manager[0].role_definition_id == "/subscriptions/00000000-0000-0000-0000-000000000003/providers/Microsoft.Authorization/roleDefinitions/eadc314b-1a2d-4efa-be10-5d325db5065e" &&
      azurerm_role_assignment.jumpbox_foundry_project_manager[0].scope == module.ai_foundry.ai_foundry_project_id["primary"]
    )
    error_message = "The optional runner receives Foundry Project Manager only on the project."
  }
}

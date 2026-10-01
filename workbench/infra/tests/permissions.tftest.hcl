mock_provider "azurerm" {}
mock_provider "azapi" {}

override_resource {
  target          = azurerm_user_assigned_identity.this
  override_during = plan
  values = {
    principal_id = "00000000-0000-0000-0000-000000000004"
  }
}

override_resource {
  target          = azurerm_container_registry.this
  override_during = plan
  values = {
    id = "/subscriptions/00000000-0000-0000-0000-000000000003/resourceGroups/rg-permissions/providers/Microsoft.ContainerRegistry/registries/registrypermissions"
  }
}

variables {
  subscription_id      = "00000000-0000-0000-0000-000000000003"
  resource_group_name  = "rg-permissions"
  workload_vnet_name   = "vnet-workload"
  management_vnet_name = "vnet-management"
  foundry_account_name = "foundry-permissions"
  foundry_project_name = "project-permissions"
  registry_name        = "registrypermissions"
  cosmos_account_name  = "cosmos-permissions"
  bootstrap_only       = true
}

run "lab_identity_permissions" {
  command = plan
  plan_options {
    target = [
      azurerm_role_assignment.pull,
      azurerm_role_assignment.foundry,
      azurerm_cosmosdb_sql_role_assignment.history,
    ]
  }
  assert {
    condition = (
      azurerm_role_assignment.pull.role_definition_name == "AcrPull" &&
      azurerm_role_assignment.pull.scope == azurerm_container_registry.this.id &&
      azurerm_role_assignment.pull.principal_id == "00000000-0000-0000-0000-000000000004"
    )
    error_message = "Image pull must remain registry-scoped AcrPull for the Lab identity."
  }
  assert {
    condition = (
      azurerm_role_assignment.foundry.role_definition_id == "/subscriptions/00000000-0000-0000-0000-000000000003/providers/Microsoft.Authorization/roleDefinitions/53ca6127-db72-4b80-b1b0-d745d6d5456d" &&
      azurerm_role_assignment.foundry.scope == "/subscriptions/00000000-0000-0000-0000-000000000003/resourceGroups/rg-permissions/providers/Microsoft.CognitiveServices/accounts/foundry-permissions/projects/project-permissions" &&
      azurerm_role_assignment.foundry.principal_id == "00000000-0000-0000-0000-000000000004"
    )
    error_message = "Foundry User must stay on the configured project for the Lab identity."
  }
  assert {
    condition = (
      azurerm_cosmosdb_sql_role_assignment.history.role_definition_id == "/subscriptions/00000000-0000-0000-0000-000000000003/resourceGroups/rg-permissions/providers/Microsoft.DocumentDB/databaseAccounts/cosmos-permissions/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002" &&
      azurerm_cosmosdb_sql_role_assignment.history.scope == "/subscriptions/00000000-0000-0000-0000-000000000003/resourceGroups/rg-permissions/providers/Microsoft.DocumentDB/databaseAccounts/cosmos-permissions/dbs/workbench/colls/conversations" &&
      azurerm_cosmosdb_sql_role_assignment.history.principal_id == "00000000-0000-0000-0000-000000000004"
    )
    error_message = "Cosmos Data Contributor must cover only the shared Lab container, not the account or Foundry memory."
  }
}

run "operator_key_verifier_grant_is_off_by_default" {
  command = plan
  plan_options {
    target = [azurerm_role_assignment.creation_key_verifier]
  }
  assert {
    condition     = length(azurerm_role_assignment.creation_key_verifier) == 0
    error_message = "The Lab must not grant Key Vault access unless the secret's resource ID is set."
  }
}

run "operator_key_verifier_grant_reads_only_that_secret" {
  command = plan
  variables {
    agent_creation_key_secret_id          = "https://vault-permissions.vault.azure.net/secrets/creation-key-verifier"
    agent_creation_key_secret_resource_id = "/subscriptions/00000000-0000-0000-0000-000000000003/resourceGroups/rg-permissions/providers/Microsoft.KeyVault/vaults/vault-permissions/secrets/creation-key-verifier"
  }
  plan_options {
    target = [azurerm_role_assignment.creation_key_verifier]
  }
  assert {
    condition = (
      length(azurerm_role_assignment.creation_key_verifier) == 1 &&
      azurerm_role_assignment.creation_key_verifier[0].role_definition_id == "/subscriptions/00000000-0000-0000-0000-000000000003/providers/Microsoft.Authorization/roleDefinitions/4633458b-17de-408a-b874-0445c86b69e6" &&
      azurerm_role_assignment.creation_key_verifier[0].scope == "/subscriptions/00000000-0000-0000-0000-000000000003/resourceGroups/rg-permissions/providers/Microsoft.KeyVault/vaults/vault-permissions/secrets/creation-key-verifier" &&
      azurerm_role_assignment.creation_key_verifier[0].principal_id == "00000000-0000-0000-0000-000000000004" &&
      azurerm_role_assignment.creation_key_verifier[0].description == "Foundry Lab agent creation"
    )
    error_message = "Key Vault Secrets User must cover only the operator-key verifier secret, for the Lab identity."
  }
}

run "operator_key_verifier_grant_rejects_a_different_secret" {
  command = plan
  variables {
    agent_creation_key_secret_id          = "https://vault-permissions.vault.azure.net/secrets/creation-key-verifier"
    agent_creation_key_secret_resource_id = "/subscriptions/00000000-0000-0000-0000-000000000003/resourceGroups/rg-permissions/providers/Microsoft.KeyVault/vaults/vault-permissions/secrets/another-secret"
  }
  plan_options {
    target = [azurerm_role_assignment.creation_key_verifier]
  }
  expect_failures = [azurerm_role_assignment.creation_key_verifier]
}

run "operator_key_verifier_grant_needs_the_secret_uri" {
  command = plan
  variables {
    agent_creation_key_secret_resource_id = "/subscriptions/00000000-0000-0000-0000-000000000003/resourceGroups/rg-permissions/providers/Microsoft.KeyVault/vaults/vault-permissions/secrets/creation-key-verifier"
  }
  plan_options {
    target = [azurerm_role_assignment.creation_key_verifier]
  }
  expect_failures = [azurerm_role_assignment.creation_key_verifier]
}

run "operator_key_verifier_resource_id_must_name_a_secret" {
  command = plan
  variables {
    agent_creation_key_secret_id          = "https://vault-permissions.vault.azure.net/secrets/creation-key-verifier"
    agent_creation_key_secret_resource_id = "/subscriptions/00000000-0000-0000-0000-000000000003/resourceGroups/rg-permissions/providers/Microsoft.KeyVault/vaults/vault-permissions"
  }
  plan_options {
    target = [azurerm_role_assignment.creation_key_verifier]
  }
  expect_failures = [var.agent_creation_key_secret_resource_id]
}

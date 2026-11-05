mock_provider "azurerm" {}

variables {
  subscription_id = "11111111-2222-3333-4444-555555555555"
  principal_id    = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
  scopes = {
    runner  = "/subscriptions/11111111-2222-3333-4444-555555555555/resourceGroups/rg-runner"
    network = "/subscriptions/11111111-2222-3333-4444-555555555555/resourceGroups/rg-platform/providers/Microsoft.Network/virtualNetworks/management"
    nat     = "/subscriptions/11111111-2222-3333-4444-555555555555/resourceGroups/rg-platform/providers/Microsoft.Network/natGateways/existing"
  }
  existing_assignment_ids = {
    runner  = "/subscriptions/11111111-2222-3333-4444-555555555555/resourceGroups/rg-runner/providers/Microsoft.Authorization/roleAssignments/00000000-0000-0000-0000-000000000001"
    network = "/subscriptions/11111111-2222-3333-4444-555555555555/resourceGroups/rg-platform/providers/Microsoft.Network/virtualNetworks/management/providers/Microsoft.Authorization/roleAssignments/00000000-0000-0000-0000-000000000002"
    nat     = "/subscriptions/11111111-2222-3333-4444-555555555555/resourceGroups/rg-platform/providers/Microsoft.Network/natGateways/existing/providers/Microsoft.Authorization/roleAssignments/00000000-0000-0000-0000-000000000003"
  }
}

run "reader_only_at_three_existing_scopes" {
  command = plan
  override_resource {
    target = azurerm_role_assignment.reader["runner"]
    values = { id = "/subscriptions/11111111-2222-3333-4444-555555555555/resourceGroups/rg-runner/providers/Microsoft.Authorization/roleAssignments/00000000-0000-0000-0000-000000000001" }
  }
  override_resource {
    target = azurerm_role_assignment.reader["network"]
    values = { id = "/subscriptions/11111111-2222-3333-4444-555555555555/resourceGroups/rg-platform/providers/Microsoft.Network/virtualNetworks/management/providers/Microsoft.Authorization/roleAssignments/00000000-0000-0000-0000-000000000002" }
  }
  override_resource {
    target = azurerm_role_assignment.reader["nat"]
    values = { id = "/subscriptions/11111111-2222-3333-4444-555555555555/resourceGroups/rg-platform/providers/Microsoft.Network/natGateways/existing/providers/Microsoft.Authorization/roleAssignments/00000000-0000-0000-0000-000000000003" }
  }
  assert {
    condition = length(azurerm_role_assignment.reader) == 3 && alltrue([
      for name, grant in azurerm_role_assignment.reader :
      grant.scope == var.scopes[name] &&
      grant.principal_id == var.principal_id &&
      endswith(grant.role_definition_id, "/acdd72a7-3385-48ef-bd42-f606fba81ae7")
    ])
    error_message = "Grant only Reader on the approved existing resource scopes, never Contributor or subscription scope."
  }
}

run "missing_imports_rejected" {
  command = plan
  variables {
    existing_assignment_ids = {}
  }
  expect_failures = [var.existing_assignment_ids]
}

run "broader_scope_rejected" {
  command = plan
  variables {
    scopes = {
      runner  = "/subscriptions/11111111-2222-3333-4444-555555555555"
      network = "/subscriptions/11111111-2222-3333-4444-555555555555/resourceGroups/rg-platform"
      nat     = "/subscriptions/11111111-2222-3333-4444-555555555555/resourceGroups/rg-platform"
    }
    existing_assignment_ids = {
      runner  = "/subscriptions/11111111-2222-3333-4444-555555555555/providers/Microsoft.Authorization/roleAssignments/00000000-0000-0000-0000-000000000001"
      network = "/subscriptions/11111111-2222-3333-4444-555555555555/resourceGroups/rg-platform/providers/Microsoft.Authorization/roleAssignments/00000000-0000-0000-0000-000000000002"
      nat     = "/subscriptions/11111111-2222-3333-4444-555555555555/resourceGroups/rg-platform/providers/Microsoft.Authorization/roleAssignments/00000000-0000-0000-0000-000000000003"
    }
  }
  expect_failures = [var.scopes]
}

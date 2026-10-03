mock_provider "azurerm" {}
mock_provider "azapi" {}

variables {
  subscription_id      = "00000000-0000-0000-0000-000000000003"
  resource_group_name  = "rg-history"
  workload_vnet_name   = "vnet-workload"
  management_vnet_name = "vnet-management"
  foundry_account_name = "foundry-history"
  foundry_project_name = "project-history"
  registry_name        = "registryhistory"
  cosmos_account_name  = "cosmos-history"
  bootstrap_only       = true
}

run "conversations_index_is_unchanged_by_default" {
  command = plan
  plan_options {
    target = [azurerm_cosmosdb_sql_container.history]
  }
  assert {
    condition = (
      toset([for p in azurerm_cosmosdb_sql_container.history.indexing_policy[0].included_path : p.path]) == toset(["/agent_id/?", "/updated_at/?", "/kind/?"]) &&
      toset([for p in azurerm_cosmosdb_sql_container.history.indexing_policy[0].excluded_path : p.path]) == toset(["/*"])
    )
    error_message = "The conversations container's indexing policy must not change until the project index is approved."
  }
}

run "conversations_index_adds_only_the_project_path_when_approved" {
  command = plan
  variables {
    index_project_path = true
  }
  plan_options {
    target = [azurerm_cosmosdb_sql_container.history]
  }
  assert {
    condition = (
      toset([for p in azurerm_cosmosdb_sql_container.history.indexing_policy[0].included_path : p.path]) == toset(["/agent_id/?", "/updated_at/?", "/kind/?", "/project/?"]) &&
      toset([for p in azurerm_cosmosdb_sql_container.history.indexing_policy[0].excluded_path : p.path]) == toset(["/*"])
    )
    error_message = "Approving the project index must add /project/? and keep every other path excluded."
  }
}
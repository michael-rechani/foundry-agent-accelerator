mock_provider "azurerm" {}
mock_provider "azapi" {}

variables {
  subscription_id      = "00000000-0000-0000-0000-000000000005"
  resource_group_name  = "rg-logs"
  workload_vnet_name   = "vnet-workload"
  management_vnet_name = "vnet-management"
  foundry_account_name = "foundry-logs"
  foundry_project_name = "project-logs"
  registry_name        = "registrylogs"
  cosmos_account_name  = "cosmos-logs"
  bootstrap_only       = true
}

# A stray space in parent_id once made Terraform plan to replace the live workspace.
run "logs_workspace_parent_is_the_resource_group" {
  command = plan
  plan_options {
    target = [azapi_resource.logs]
  }
  assert {
    condition     = azapi_resource.logs.parent_id == "/subscriptions/00000000-0000-0000-0000-000000000005/resourceGroups/rg-logs"
    error_message = "The Log Analytics workspace parent_id must be exactly the resource group ID, with no extra characters."
  }
}

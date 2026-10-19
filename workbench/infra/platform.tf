variable "platform_state" {
  type = object({
    subscription_id      = string
    resource_group_name  = string
    storage_account_name = string
    container_name       = string
    key                  = optional(string, "ai-foundry/dev.tfstate")
  })
  default     = null
  description = "Where the platform root keeps its state. When set, the Lab reads the resource group, network, Foundry and Cosmos names from the platform outputs, and any of those variables you set explicitly still wins. Null means every name must be set by hand."
}

# Reads the platform root's outputs through Entra ID, never a storage key.
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
  platform_outputs = try(data.terraform_remote_state.platform[0].outputs, {})

  resource_group_name  = var.resource_group_name != null ? var.resource_group_name : try(local.platform_outputs.resource_group_name, null)
  workload_vnet_name   = var.workload_vnet_name != null ? var.workload_vnet_name : try(local.platform_outputs.workload_virtual_network_name, null)
  management_vnet_name = var.management_vnet_name != null ? var.management_vnet_name : try(local.platform_outputs.management_virtual_network_name, null)
  foundry_account_name = var.foundry_account_name != null ? var.foundry_account_name : try(local.platform_outputs.foundry_account_name, null)
  foundry_project_name = var.foundry_project_name != null ? var.foundry_project_name : try(local.platform_outputs.foundry_project_name, null)
  cosmos_account_name  = var.cosmos_account_name != null ? var.cosmos_account_name : try(local.platform_outputs.cosmos_account_name, null)
}

# Fails the plan with a clear message instead of a provider error on a null name.
resource "terraform_data" "platform_names" {
  lifecycle {
    precondition {
      condition = alltrue([
        for value in [
          local.resource_group_name,
          local.workload_vnet_name,
          local.management_vnet_name,
          local.foundry_account_name,
          local.foundry_project_name,
          local.cosmos_account_name,
        ] : value != null
      ])
      error_message = "Set platform_state so the Lab can read the platform outputs, or set resource_group_name, workload_vnet_name, management_vnet_name, foundry_account_name, foundry_project_name and cosmos_account_name yourself. management_vnet_name is null when the platform's management network is disabled."
    }
  }
}

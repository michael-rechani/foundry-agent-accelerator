locals {
  name_suffix                = "${var.base_name}-${var.environment}"
  unique_name_suffix         = replace(module.naming.resource_group.name_unique, "rg-", "")
  cosmosdb_account_name      = coalesce(var.cosmosdb_account_name, module.naming.cosmosdb_account.name_unique)
  agent_storage_account_name = coalesce(var.agent_storage_account_name, module.naming.storage_account.name_unique)
  foundry_account_name       = "foundry-hosted-agents-${local.unique_name_suffix}"
  foundry_project_name       = "hosted-agents-${var.environment}"
  tags = merge(var.tags, {
    environment = var.environment
    managed-by  = "terraform"
    workload    = "azure-ai-foundry"
  })
}

module "naming" {
  source  = "Azure/naming/azurerm"
  version = "0.4.3"

  suffix        = [local.name_suffix]
  unique-length = 5
}

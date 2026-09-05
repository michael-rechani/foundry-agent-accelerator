variable "cosmos_account_name" {
  type    = string
  default = "aifnd-agent-foundry-cosmosdb-7omvd"
}

data "azurerm_cosmosdb_account" "history" {
  name                = var.cosmos_account_name
  resource_group_name = var.resource_group_name
}

resource "azurerm_cosmosdb_sql_database" "history" {
  name                = "workbench"
  account_name        = data.azurerm_cosmosdb_account.history.name
  resource_group_name = var.resource_group_name
}

resource "azurerm_cosmosdb_sql_container" "history" {
  name                  = "conversations"
  resource_group_name   = var.resource_group_name
  account_name          = data.azurerm_cosmosdb_account.history.name
  database_name         = azurerm_cosmosdb_sql_database.history.name
  partition_key_paths   = ["/workspace"]
  partition_key_version = 2
  throughput            = 400
  default_ttl           = 2592000
  indexing_policy {
    indexing_mode = "consistent"
    included_path { path = "/agent_id/?" }
    included_path { path = "/updated_at/?" }
    excluded_path { path = "/*" }
  }
}

resource "azurerm_cosmosdb_sql_role_assignment" "history" {
  resource_group_name = var.resource_group_name
  account_name        = data.azurerm_cosmosdb_account.history.name
  role_definition_id  = "${data.azurerm_cosmosdb_account.history.id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002"
  principal_id        = azurerm_user_assigned_identity.this.principal_id
  scope               = "${data.azurerm_cosmosdb_account.history.id}/dbs/${azurerm_cosmosdb_sql_database.history.name}/colls/${azurerm_cosmosdb_sql_container.history.name}"
}
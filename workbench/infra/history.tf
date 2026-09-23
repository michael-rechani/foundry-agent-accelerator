variable "cosmos_account_name" { type = string }

locals {
  cosmos_account_id = "/subscriptions/${var.subscription_id}/resourceGroups/${var.resource_group_name}/providers/Microsoft.DocumentDB/databaseAccounts/${var.cosmos_account_name}"
  cosmos_endpoint   = "https://${var.cosmos_account_name}.documents.azure.com:443/"
}

resource "azurerm_cosmosdb_sql_database" "history" {
  name                = "workbench"
  account_name        = var.cosmos_account_name
  resource_group_name = var.resource_group_name
  lifecycle {
    prevent_destroy = true
  }
}

resource "azurerm_cosmosdb_sql_container" "history" {
  name                  = "conversations"
  resource_group_name   = var.resource_group_name
  account_name          = var.cosmos_account_name
  database_name         = azurerm_cosmosdb_sql_database.history.name
  partition_key_paths   = ["/workspace"]
  partition_key_version = 2
  throughput            = 400
  default_ttl           = 2592000
  lifecycle {
    prevent_destroy = true
  }
  indexing_policy {
    indexing_mode = "consistent"
    included_path { path = "/agent_id/?" }
    included_path { path = "/updated_at/?" }
    included_path { path = "/kind/?" }
    excluded_path { path = "/*" }
  }
}

resource "azurerm_cosmosdb_sql_role_assignment" "history" {
  resource_group_name = var.resource_group_name
  account_name        = var.cosmos_account_name
  role_definition_id  = "${local.cosmos_account_id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002"
  principal_id        = azurerm_user_assigned_identity.this.principal_id
  scope               = "${local.cosmos_account_id}/dbs/${azurerm_cosmosdb_sql_database.history.name}/colls/${azurerm_cosmosdb_sql_container.history.name}"
}
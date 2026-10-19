variable "cosmos_account_name" {
  type        = string
  default     = null
  description = "Name of the existing Cosmos DB account that holds the Lab's history database and container. The Lab identity gets data access to that container only. Null reads it from the platform state (platform_state)."
}

variable "index_project_path" {
  type        = bool
  description = "Index the /project path of the conversations container, so listing created agents reads only the caller's documents (#188). Off by default because it changes the indexing policy of a shared container: Cosmos DB reindexes online with no downtime, but the one-time reindex uses some of the container's 400 RU/s. Set it to true when you approve applying that change."
  default     = false
}

locals {
  cosmos_account_id = "/subscriptions/${var.subscription_id}/resourceGroups/${local.resource_group_name}/providers/Microsoft.DocumentDB/databaseAccounts/${local.cosmos_account_name}"
  cosmos_endpoint   = "https://${local.cosmos_account_name}.documents.azure.com:443/"
}

resource "azurerm_cosmosdb_sql_database" "history" {
  name                = "workbench"
  account_name        = local.cosmos_account_name
  resource_group_name = local.resource_group_name
  lifecycle {
    prevent_destroy = true
  }
}

resource "azurerm_cosmosdb_sql_container" "history" {
  name                  = "conversations"
  resource_group_name   = local.resource_group_name
  account_name          = local.cosmos_account_name
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
    dynamic "included_path" {
      for_each = var.index_project_path ? ["/project/?"] : []
      content {
        path = included_path.value
      }
    }
    excluded_path { path = "/*" }
  }
}

# Cosmos DB Built-in Data Contributor: shared Lab records in this container only.
# This is a Cosmos data-plane role, not an Azure RBAC role or per-user authorization.
resource "azurerm_cosmosdb_sql_role_assignment" "history" {
  resource_group_name = local.resource_group_name
  account_name        = local.cosmos_account_name
  role_definition_id  = "${local.cosmos_account_id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002"
  principal_id        = azurerm_user_assigned_identity.this.principal_id
  scope               = "${local.cosmos_account_id}/dbs/${azurerm_cosmosdb_sql_database.history.name}/colls/${azurerm_cosmosdb_sql_container.history.name}"
}
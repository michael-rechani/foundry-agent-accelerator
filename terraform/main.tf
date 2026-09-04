locals {
  name_suffix           = "${var.base_name}-${var.environment}"
  unique_name_suffix    = replace(module.naming.resource_group.name_unique, "rg-", "")
  cosmosdb_account_name = coalesce(var.cosmosdb_account_name, module.naming.cosmosdb_account.name_unique)
  foundry_account_name  = "foundry-hosted-agents-${local.unique_name_suffix}"
  foundry_project_name  = "hosted-agents-${var.environment}"
  tags = merge(var.tags, {
    environment = var.environment
    managed-by  = "terraform"
    workload    = "azure-ai-foundry"
  })
}

data "azurerm_client_config" "current" {}

module "naming" {
  source  = "Azure/naming/azurerm"
  version = "0.4.3"

  suffix        = [local.name_suffix]
  unique-length = 5
}

resource "azurerm_resource_group" "this" {
  location = local.deployment_location
  name     = module.naming.resource_group.name_unique
  tags     = local.tags

  lifecycle {
    ignore_changes = [location]
  }
}

resource "azurerm_log_analytics_workspace" "this" {
  internet_ingestion_enabled   = false
  internet_query_enabled       = false
  local_authentication_enabled = false
  location                     = local.deployment_location
  name                         = module.naming.log_analytics_workspace.name_unique
  resource_group_name          = azurerm_resource_group.this.name
  retention_in_days            = 30
  sku                          = "PerGB2018"
  tags                         = local.tags
}

moved {
  from = module.ai_foundry.module.cosmosdb["agent"].azurerm_cosmosdb_account.this
  to   = azurerm_cosmosdb_account.agent
}

resource "azurerm_cosmosdb_account" "agent" {
  name                = local.cosmosdb_account_name
  location            = local.deployment_location
  resource_group_name = azurerm_resource_group.this.name
  offer_type          = "Standard"
  kind                = "GlobalDocumentDB"

  access_key_metadata_writes_enabled    = false
  analytical_storage_enabled            = false
  automatic_failover_enabled            = true
  local_authentication_enabled          = false
  minimal_tls_version                   = "Tls12"
  multiple_write_locations_enabled      = false
  network_acl_bypass_for_azure_services = false
  partition_merge_enabled               = false
  public_network_access_enabled         = false

  analytical_storage {
    schema_type = "WellDefined"
  }

  backup {
    tier = "Continuous30Days"
    type = "Continuous"
  }

  capacity {
    total_throughput_limit = -1
  }

  consistency_policy {
    consistency_level       = "Session"
    max_interval_in_seconds = 5
    max_staleness_prefix    = 100
  }

  dynamic "geo_location" {
    for_each = concat(
      [{
        location          = local.deployment_location
        zone_redundant    = false
        failover_priority = 0
      }],
      [for index, location in local.region_preference.cosmos_secondary_regions : {
        location          = location
        zone_redundant    = false
        failover_priority = index + 1
      }],
    )

    content {
      location          = geo_location.value.location
      zone_redundant    = geo_location.value.zone_redundant
      failover_priority = geo_location.value.failover_priority
    }
  }

  tags = local.tags
}

resource "azurerm_private_endpoint" "cosmosdb" {
  name                = "pe-${local.cosmosdb_account_name}"
  location            = local.deployment_location
  resource_group_name = azurerm_resource_group.this.name
  subnet_id           = azurerm_subnet.private_endpoints.id

  private_service_connection {
    name                           = "psc-${local.cosmosdb_account_name}"
    private_connection_resource_id = azurerm_cosmosdb_account.agent.id
    is_manual_connection           = false
    subresource_names              = ["Sql"]
  }

  private_dns_zone_group {
    name                 = "default"
    private_dns_zone_ids = [azurerm_private_dns_zone.this["cosmosdb"].id]
  }

  tags = local.tags
}

moved {
  from = module.ai_foundry.azurerm_monitor_diagnostic_setting.this["log_analytics"]
  to   = azurerm_monitor_diagnostic_setting.foundry
}

resource "azurerm_monitor_diagnostic_setting" "foundry" {
  name                           = "diag-foundry"
  target_resource_id             = module.ai_foundry.resource_id
  log_analytics_workspace_id     = azurerm_log_analytics_workspace.this.id
  log_analytics_destination_type = "Dedicated"

  enabled_log {
    category_group = "allLogs"
  }

  enabled_metric {
    category = "AllMetrics"
  }

  lifecycle {
    ignore_changes = [log_analytics_destination_type]
  }
}

module "ai_foundry" {
  source  = "Azure/avm-ptn-aiml-ai-foundry/azurerm"
  version = "0.11.3"

  depends_on = [
    azurerm_subnet.agent_services,
    azurerm_subnet.private_endpoints,
  ]

  base_name                  = var.base_name
  location                   = local.deployment_location
  resource_group_resource_id = azurerm_resource_group.this.id

  ai_foundry = {
    name                    = local.foundry_account_name
    create_ai_agent_service = var.enable_agent_service
    disable_local_auth      = true
    private_dns_zone_resource_ids = [
      azurerm_private_dns_zone.this["ai_services"].id,
      azurerm_private_dns_zone.this["cognitive_services"].id,
      azurerm_private_dns_zone.this["openai"].id,
    ]
    public_network_access_enabled = false
    network_acls = {
      bypass         = null
      default_action = "Deny"
    }
    network_injections = var.enable_agent_service ? [{
      scenario                   = "agent"
      subnetArmId                = azurerm_subnet.agent_services.id
      useMicrosoftManagedNetwork = false
    }] : null
    managed_identities = {
      system_assigned            = true
      user_assigned_resource_ids = []
    }
  }

  ai_projects = {
    primary = {
      name                       = local.foundry_project_name
      display_name               = "Hosted Agents ${upper(var.environment)}"
      description                = "${title(var.environment)} environment for the hosted-agent samples."
      create_project_connections = var.enable_agent_service
      cosmos_db_connection = {
        existing_resource_id = var.enable_agent_service ? azurerm_cosmosdb_account.agent.id : null
      }
      ai_search_connection = {
        new_resource_map_key = var.enable_agent_service ? "agent" : null
      }
      storage_account_connection = {
        new_resource_map_key = var.enable_agent_service ? "agent" : null
      }
    }
  }

  ai_model_deployments = {
    primary = {
      name = var.model_deployment.deployment_name
      model = {
        format  = var.model_deployment.format
        name    = var.model_deployment.name
        version = var.model_deployment.version
      }
      scale = {
        type     = var.model_deployment.sku_name
        capacity = var.model_deployment.capacity
      }
    }
  }

  create_byor = var.enable_agent_service
  ai_search_definition = var.enable_agent_service ? {
    agent = {
      local_authentication_enabled  = false
      private_dns_zone_resource_id  = azurerm_private_dns_zone.this["search"].id
      public_network_access_enabled = false
    }
  } : {}
  cosmosdb_definition = var.enable_agent_service ? {
    agent = {
      existing_resource_id = azurerm_cosmosdb_account.agent.id
    }
  } : {}
  key_vault_definition = var.enable_agent_service ? {
    agent = {
      network_acls = {
        bypass         = "AzureServices"
        default_action = "Deny"
      }
      private_dns_zone_resource_id  = azurerm_private_dns_zone.this["key_vault"].id
      public_network_access_enabled = false
      role_assignments = {
        deployer_secrets_officer = {
          principal_id               = data.azurerm_client_config.current.object_id
          role_definition_id_or_name = "Key Vault Secrets Officer"
        }
      }
    }
  } : {}
  storage_account_definition = var.enable_agent_service ? {
    agent = {
      account_replication_type = local.region_preference.storage_replication_type
      endpoints = {
        blob = {
          private_dns_zone_resource_id = azurerm_private_dns_zone.this["storage_blob"].id
          type                         = "blob"
        }
      }
      network_rules = {
        bypass         = ["None"]
        default_action = "Deny"
        private_link_access = [{
          endpoint_resource_id = "/subscriptions/${var.subscription_id}/providers/Microsoft.Security/datascanners/StorageDataScanner"
          endpoint_tenant_id   = data.azurerm_client_config.current.tenant_id
        }]
      }
      public_network_access_enabled = false
      shared_access_key_enabled     = false
    }
  } : {}

  create_private_endpoints            = true
  enable_telemetry                    = true
  private_endpoint_subnet_resource_id = azurerm_subnet.private_endpoints.id
  tags                                = local.tags

  diagnostic_settings = {}
}

resource "azurerm_role_assignment" "deployer_foundry_user" {
  principal_id       = data.azurerm_client_config.current.object_id
  role_definition_id = "/subscriptions/${var.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/53ca6127-db72-4b80-b1b0-d745d6d5456d"
  scope              = module.ai_foundry.ai_foundry_project_id["primary"]
}

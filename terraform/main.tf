locals {
  name_suffix = "${var.base_name}-${var.environment}"
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

resource "azurerm_resource_group" "this" {
  location = var.location
  name     = module.naming.resource_group.name_unique
  tags     = local.tags
}

resource "azurerm_log_analytics_workspace" "this" {
  internet_ingestion_enabled   = false
  internet_query_enabled       = false
  local_authentication_enabled = false
  location                     = azurerm_resource_group.this.location
  name                         = module.naming.log_analytics_workspace.name_unique
  resource_group_name          = azurerm_resource_group.this.name
  retention_in_days            = 30
  sku                          = "PerGB2018"
  tags                         = local.tags
}

module "ai_foundry" {
  source  = "Azure/avm-ptn-aiml-ai-foundry/azurerm"
  version = "0.11.3"

  base_name                  = var.base_name
  location                   = azurerm_resource_group.this.location
  resource_group_resource_id = azurerm_resource_group.this.id

  ai_foundry = {
    name                    = module.naming.cognitive_account.name_unique
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
      name                       = "project-${local.name_suffix}"
      display_name               = "AI Foundry ${upper(var.environment)}"
      description                = "Primary ${var.environment} project for hosted-agent samples."
      create_project_connections = var.enable_agent_service
      cosmos_db_connection = {
        new_resource_map_key = var.enable_agent_service ? "agent" : null
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
      ip_range_filter                       = []
      local_authentication_disabled         = true
      network_acl_bypass_for_azure_services = false
      private_dns_zone_resource_id          = azurerm_private_dns_zone.this["cosmosdb"].id
      public_network_access_enabled         = false
    }
  } : {}
  key_vault_definition = var.enable_agent_service ? {
    agent = {
      network_acls = {
        bypass         = "None"
        default_action = "Deny"
      }
      private_dns_zone_resource_id  = azurerm_private_dns_zone.this["key_vault"].id
      public_network_access_enabled = false
    }
  } : {}
  storage_account_definition = var.enable_agent_service ? {
    agent = {
      endpoints = {
        blob = {
          private_dns_zone_resource_id = azurerm_private_dns_zone.this["storage_blob"].id
          type                         = "blob"
        }
      }
      network_rules = {
        bypass         = ["None"]
        default_action = "Deny"
      }
      public_network_access_enabled = false
      shared_access_key_enabled     = false
    }
  } : {}

  create_private_endpoints            = true
  enable_telemetry                    = true
  private_endpoint_subnet_resource_id = azurerm_subnet.private_endpoints.id
  tags                                = local.tags

  diagnostic_settings = {
    log_analytics = {
      name                           = "diag-foundry"
      workspace_resource_id          = azurerm_log_analytics_workspace.this.id
      log_analytics_destination_type = "Dedicated"
      log_groups                     = ["allLogs"]
      metric_categories              = ["AllMetrics"]
    }
  }
}

data "azurerm_client_config" "current" {}

resource "azurerm_resource_group" "this" {
  location = local.deployment_location
  name     = module.naming.resource_group.name_unique
  tags     = local.tags

  lifecycle {
    ignore_changes = [location]
  }
}

resource "azurerm_private_endpoint" "cosmosdb" {
  name                = "pe-${local.cosmosdb_account_name}"
  location            = local.deployment_location
  resource_group_name = azurerm_resource_group.this.name
  subnet_id           = azurerm_subnet.private_endpoints.id

  private_service_connection {
    name                           = "psc-${local.cosmosdb_account_name}"
    private_connection_resource_id = azapi_resource.cosmos.id
    is_manual_connection           = false
    subresource_names              = ["Sql"]
  }

  private_dns_zone_group {
    name                 = "default"
    private_dns_zone_ids = [azurerm_private_dns_zone.this["cosmosdb"].id]
  }

  tags = local.tags
}

resource "azurerm_monitor_diagnostic_setting" "foundry" {
  name                           = "diag-foundry"
  target_resource_id             = module.ai_foundry.resource_id
  log_analytics_workspace_id     = azapi_resource.platform_logs.id
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
        existing_resource_id = var.enable_agent_service ? azapi_resource.cosmos.id : null
      }
      ai_search_connection = {
        new_resource_map_key = var.enable_agent_service ? "agent" : null
      }
      storage_account_connection = {
        existing_resource_id = var.enable_agent_service ? azapi_resource.agent_storage.id : null
      }
    }
  }

  ai_model_deployments = merge(
    {
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
    },
    {
      for name, deployment in var.additional_model_deployments : "extra-${name}" => {
        name = name
        model = {
          format  = deployment.format
          name    = deployment.name
          version = deployment.version
        }
        scale = {
          type     = deployment.sku_name
          capacity = deployment.capacity
        }
      }
    },
  )

  create_byor = var.enable_agent_service
  ai_search_definition = var.enable_agent_service ? {
    agent = {
      local_authentication_enabled  = false
      private_dns_zone_resource_id  = azurerm_private_dns_zone.this["search"].id
      public_network_access_enabled = false
      replica_count                 = var.ai_search_replica_count
    }
  } : {}
  cosmosdb_definition = var.enable_agent_service ? {
    agent = {
      existing_resource_id = azapi_resource.cosmos.id
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
    }
  } : {}
  storage_account_definition = var.enable_agent_service ? {
    agent = {
      existing_resource_id = azapi_resource.agent_storage.id
    }
  } : {}

  create_private_endpoints            = true
  enable_telemetry                    = true
  private_endpoint_subnet_resource_id = azurerm_subnet.private_endpoints.id
  tags                                = local.tags

  diagnostic_settings = {}
}

resource "azurerm_role_assignment" "deployer_foundry_user" {
  principal_id       = coalesce(var.deployment_principal_id, data.azurerm_client_config.current.object_id)
  role_definition_id = "/subscriptions/${var.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/53ca6127-db72-4b80-b1b0-d745d6d5456d"
  scope              = module.ai_foundry.ai_foundry_project_id["primary"]
}

# Microsoft Learn requires this for evaluation runs in a network-isolated project.
resource "azurerm_role_assignment" "project_foundry_user" {
  principal_id       = module.ai_foundry.ai_foundry_project_system_identity_principal_id["primary"]
  principal_type     = "ServicePrincipal"
  role_definition_id = "/subscriptions/${var.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/53ca6127-db72-4b80-b1b0-d745d6d5456d"
  scope              = module.ai_foundry.ai_foundry_id
}

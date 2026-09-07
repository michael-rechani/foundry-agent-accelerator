locals {
  private_dns_zones = {
    agentsvc           = "privatelink.agentsvc.azure-automation.net"
    ai_services        = "privatelink.services.ai.azure.com"
    cognitive_services = "privatelink.cognitiveservices.azure.com"
    cosmosdb           = "privatelink.documents.azure.com"
    key_vault          = "privatelink.vaultcore.azure.net"
    monitor            = "privatelink.monitor.azure.com"
    ods                = "privatelink.ods.opinsights.azure.com"
    oms                = "privatelink.oms.opinsights.azure.com"
    openai             = "privatelink.openai.azure.com"
    search             = "privatelink.search.windows.net"
    storage_blob       = "privatelink.blob.core.windows.net"
  }
}

resource "azurerm_virtual_network" "this" {
  address_space       = var.virtual_network_address_space
  location            = local.deployment_location
  name                = module.naming.virtual_network.name_unique
  resource_group_name = azurerm_resource_group.this.name
  tags                = local.tags
}

resource "azurerm_subnet" "private_endpoints" {
  address_prefixes                  = var.private_endpoint_subnet_address_prefixes
  name                              = "snet-private-endpoints"
  private_endpoint_network_policies = "Disabled"
  resource_group_name               = azurerm_resource_group.this.name
  virtual_network_name              = azurerm_virtual_network.this.name
}

resource "azurerm_subnet" "agent_services" {
  address_prefixes     = var.agent_subnet_address_prefixes
  name                 = "snet-agent-services"
  resource_group_name  = azurerm_resource_group.this.name
  virtual_network_name = azurerm_virtual_network.this.name

  delegation {
    name = "Microsoft.App.environments"

    service_delegation {
      actions = ["Microsoft.Network/virtualNetworks/subnets/join/action"]
      name    = "Microsoft.App/environments"
    }
  }
}

resource "azurerm_private_dns_zone" "this" {
  for_each = local.private_dns_zones

  name                = each.value
  resource_group_name = azurerm_resource_group.this.name
  tags                = local.tags
}

resource "azurerm_private_dns_zone_virtual_network_link" "this" {
  for_each = local.private_dns_zones

  name                  = "link-${replace(each.key, "_", "-")}"
  private_dns_zone_name = azurerm_private_dns_zone.this[each.key].name
  resource_group_name   = azurerm_resource_group.this.name
  virtual_network_id    = azurerm_virtual_network.this.id
  tags                  = local.tags
}

resource "azurerm_monitor_private_link_scope" "this" {
  ingestion_access_mode = "PrivateOnly"
  name                  = "ampls-${local.name_suffix}"
  query_access_mode     = "PrivateOnly"
  resource_group_name   = azurerm_resource_group.this.name
  tags                  = local.tags
}

resource "azurerm_monitor_private_link_scoped_service" "log_analytics" {
  linked_resource_id  = azapi_resource.platform_logs.id
  name                = "law-${local.name_suffix}"
  resource_group_name = azurerm_resource_group.this.name
  scope_name          = azurerm_monitor_private_link_scope.this.name
}

resource "azurerm_private_endpoint" "azure_monitor" {
  location            = local.deployment_location
  name                = "pe-monitor-${local.name_suffix}"
  resource_group_name = azurerm_resource_group.this.name
  subnet_id           = azurerm_subnet.private_endpoints.id
  tags                = local.tags

  private_dns_zone_group {
    name = "azure-monitor"
    private_dns_zone_ids = [
      azurerm_private_dns_zone.this["agentsvc"].id,
      azurerm_private_dns_zone.this["monitor"].id,
      azurerm_private_dns_zone.this["ods"].id,
      azurerm_private_dns_zone.this["oms"].id,
      azurerm_private_dns_zone.this["storage_blob"].id,
    ]
  }

  private_service_connection {
    is_manual_connection           = false
    name                           = "azure-monitor"
    private_connection_resource_id = azurerm_monitor_private_link_scope.this.id
    subresource_names              = ["azuremonitor"]
  }
}
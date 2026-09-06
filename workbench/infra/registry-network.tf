variable "import_existing_registry_network" {
  type    = bool
  default = false
}

import {
  for_each = var.import_existing_registry_network ? toset(["existing"]) : toset([])
  to       = azurerm_private_dns_zone.registry[0]
  id       = "/subscriptions/${var.subscription_id}/resourceGroups/${var.resource_group_name}/providers/Microsoft.Network/privateDnsZones/privatelink.azurecr.io"
}

import {
  for_each = var.import_existing_registry_network ? toset(["workload", "management"]) : toset([])
  to       = azurerm_private_dns_zone_virtual_network_link.registry[each.key]
  id       = "/subscriptions/${var.subscription_id}/resourceGroups/${var.resource_group_name}/providers/Microsoft.Network/privateDnsZones/privatelink.azurecr.io/virtualNetworkLinks/registry-${each.key}"
}

import {
  for_each = var.import_existing_registry_network ? toset(["existing"]) : toset([])
  to       = azurerm_private_endpoint.registry[0]
  id       = "/subscriptions/${var.subscription_id}/resourceGroups/${var.resource_group_name}/providers/Microsoft.Network/privateEndpoints/pe-${var.registry_name}"
}

data "azurerm_subnet" "private_endpoints" {
  name                 = "snet-private-endpoints"
  virtual_network_name = var.workload_vnet_name
  resource_group_name  = var.resource_group_name
}

resource "azurerm_private_dns_zone" "registry" {
  count               = var.private_registry_enabled ? 1 : 0
  name                = "privatelink.azurecr.io"
  resource_group_name = var.resource_group_name
  tags                = local.tags
}

resource "azurerm_private_dns_zone_virtual_network_link" "registry" {
  for_each = var.private_registry_enabled ? {
    workload   = data.azurerm_virtual_network.workload.id
    management = data.azurerm_virtual_network.management.id
  } : {}
  name                  = "registry-${each.key}"
  private_dns_zone_name = azurerm_private_dns_zone.registry[0].name
  resource_group_name   = var.resource_group_name
  virtual_network_id    = each.value
  tags                  = local.tags
}

resource "azurerm_private_endpoint" "registry" {
  count               = var.private_registry_enabled ? 1 : 0
  name                = "pe-${var.registry_name}"
  location            = data.azurerm_virtual_network.workload.location
  resource_group_name = var.resource_group_name
  subnet_id           = data.azurerm_subnet.private_endpoints.id
  tags                = local.tags
  private_service_connection {
    name                           = "psc-${var.registry_name}"
    private_connection_resource_id = azurerm_container_registry.this.id
    is_manual_connection           = false
    subresource_names              = ["registry"]
  }
  private_dns_zone_group {
    name                 = "default"
    private_dns_zone_ids = [azurerm_private_dns_zone.registry[0].id]
  }
}
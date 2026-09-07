locals {
  management_network_enabled = var.enable_management_network || var.enable_jumpbox || var.enable_api_management
}

resource "azurerm_virtual_network" "jumpbox" {
  count = local.management_network_enabled ? 1 : 0

  address_space       = var.jumpbox_virtual_network_address_space
  location            = var.jumpbox_location
  name                = "vnet-jumpbox-${local.name_suffix}"
  resource_group_name = azurerm_resource_group.this.name
  tags                = local.tags
}

resource "azurerm_subnet" "jumpbox" {
  count = local.management_network_enabled ? 1 : 0

  address_prefixes     = var.jumpbox_subnet_address_prefixes
  name                 = "snet-jumpbox"
  resource_group_name  = azurerm_resource_group.this.name
  virtual_network_name = azurerm_virtual_network.jumpbox[0].name
}

resource "azurerm_virtual_network_peering" "workload_to_jumpbox" {
  count = local.management_network_enabled ? 1 : 0

  name                      = "peer-workload-to-jumpbox"
  remote_virtual_network_id = azurerm_virtual_network.jumpbox[0].id
  resource_group_name       = azurerm_resource_group.this.name
  virtual_network_name      = azurerm_virtual_network.this.name
}

resource "azurerm_virtual_network_peering" "jumpbox_to_workload" {
  count = local.management_network_enabled ? 1 : 0

  name                      = "peer-jumpbox-to-workload"
  remote_virtual_network_id = azurerm_virtual_network.this.id
  resource_group_name       = azurerm_resource_group.this.name
  virtual_network_name      = azurerm_virtual_network.jumpbox[0].name
}

resource "azurerm_private_dns_zone_virtual_network_link" "jumpbox" {
  for_each = local.management_network_enabled ? local.private_dns_zones : {}

  name                  = "link-jumpbox-${replace(each.key, "_", "-")}"
  private_dns_zone_name = azurerm_private_dns_zone.this[each.key].name
  resource_group_name   = azurerm_resource_group.this.name
  virtual_network_id    = azurerm_virtual_network.jumpbox[0].id
  tags                  = local.tags
}

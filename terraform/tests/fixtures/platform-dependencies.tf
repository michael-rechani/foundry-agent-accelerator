locals {
  private_dns_zones = { storage_blob = "privatelink.blob.core.windows.net" }
}

data "azurerm_client_config" "current" {}

resource "azurerm_resource_group" "this" {
  name     = "rg-platform-test-12345"
  location = local.deployment_location
}

resource "azurerm_virtual_network" "this" {
  name                = "vnet-platform-test"
  location            = local.deployment_location
  resource_group_name = azurerm_resource_group.this.name
  address_space       = ["10.0.0.0/16"]
}

resource "azurerm_subnet" "private_endpoints" {
  name                 = "private-endpoints"
  resource_group_name  = azurerm_resource_group.this.name
  virtual_network_name = azurerm_virtual_network.this.name
  address_prefixes     = ["10.0.0.0/24"]
}

resource "azurerm_private_dns_zone" "this" {
  for_each            = { storage_blob = "privatelink.blob.core.windows.net" }
  name                = each.value
  resource_group_name = azurerm_resource_group.this.name
}

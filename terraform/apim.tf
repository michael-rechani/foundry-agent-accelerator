resource "azurerm_network_security_group" "api_management" {
  count = var.enable_api_management ? 1 : 0

  location            = var.api_management_location
  name                = "nsg-apim-${local.name_suffix}"
  resource_group_name = azurerm_resource_group.this.name
  tags                = local.tags

  security_rule {
    access                     = "Allow"
    destination_address_prefix = "AzureKeyVault"
    destination_port_range     = "443"
    direction                  = "Outbound"
    name                       = "AllowAzureKeyVaultOutbound"
    priority                   = 100
    protocol                   = "Tcp"
    source_address_prefix      = "VirtualNetwork"
    source_port_range          = "*"
  }
}

resource "azurerm_subnet" "api_management" {
  count = var.enable_api_management ? 1 : 0

  address_prefixes     = var.api_management_subnet_address_prefixes
  name                 = "snet-api-management"
  resource_group_name  = azurerm_resource_group.this.name
  virtual_network_name = azurerm_virtual_network.jumpbox[0].name

  delegation {
    name = "Microsoft.Web.serverFarms"

    service_delegation {
      actions = ["Microsoft.Network/virtualNetworks/subnets/action"]
      name    = "Microsoft.Web/serverFarms"
    }
  }
}

resource "azurerm_subnet_network_security_group_association" "api_management" {
  count = var.enable_api_management ? 1 : 0

  network_security_group_id = azurerm_network_security_group.api_management[0].id
  subnet_id                 = azurerm_subnet.api_management[0].id
}

module "api_management" {
  source  = "Azure/avm-res-apimanagement-service/azurerm"
  version = "0.9.0"
  count   = var.enable_api_management ? 1 : 0

  location            = var.api_management_location
  name                = "apim-${local.unique_name_suffix}"
  publisher_email     = var.api_management_publisher_email
  publisher_name      = var.api_management_publisher_name
  resource_group_name = azurerm_resource_group.this.name
  sku_name            = "StandardV2_1"

  diagnostic_settings = {
    log_analytics = {
      name                  = "diag-api-management"
      workspace_resource_id = azapi_resource.platform_logs.id
    }
  }
  enable_telemetry = true
  managed_identities = {
    system_assigned = true
  }
  public_network_access_enabled = true
  tags                          = local.tags
  virtual_network_subnet_id     = azurerm_subnet.api_management[0].id
  virtual_network_type          = "External"

  depends_on = [azurerm_subnet_network_security_group_association.api_management]
}

resource "azurerm_role_assignment" "api_management_foundry_user" {
  count = var.enable_api_management ? 1 : 0

  principal_id       = module.api_management[0].resource.identity[0].principal_id
  role_definition_id = "/subscriptions/${var.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/53ca6127-db72-4b80-b1b0-d745d6d5456d"
  scope              = module.ai_foundry.ai_foundry_project_id["primary"]
}
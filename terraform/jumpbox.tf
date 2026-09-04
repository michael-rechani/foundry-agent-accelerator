resource "azurerm_virtual_network" "jumpbox" {
  count = var.enable_jumpbox ? 1 : 0

  address_space       = var.jumpbox_virtual_network_address_space
  location            = var.jumpbox_location
  name                = "vnet-jumpbox-${local.name_suffix}"
  resource_group_name = azurerm_resource_group.this.name
  tags                = local.tags
}

resource "azurerm_subnet" "jumpbox" {
  count = var.enable_jumpbox ? 1 : 0

  address_prefixes     = var.jumpbox_subnet_address_prefixes
  name                 = "snet-jumpbox"
  resource_group_name  = azurerm_resource_group.this.name
  virtual_network_name = azurerm_virtual_network.jumpbox[0].name
}

resource "azurerm_virtual_network_peering" "workload_to_jumpbox" {
  count = var.enable_jumpbox ? 1 : 0

  name                      = "peer-workload-to-jumpbox"
  remote_virtual_network_id = azurerm_virtual_network.jumpbox[0].id
  resource_group_name       = azurerm_resource_group.this.name
  virtual_network_name      = azurerm_virtual_network.this.name
}

resource "azurerm_virtual_network_peering" "jumpbox_to_workload" {
  count = var.enable_jumpbox ? 1 : 0

  name                      = "peer-jumpbox-to-workload"
  remote_virtual_network_id = azurerm_virtual_network.this.id
  resource_group_name       = azurerm_resource_group.this.name
  virtual_network_name      = azurerm_virtual_network.jumpbox[0].name
}

resource "azurerm_private_dns_zone_virtual_network_link" "jumpbox" {
  for_each = var.enable_jumpbox ? local.private_dns_zones : {}

  name                  = "link-jumpbox-${replace(each.key, "_", "-")}"
  private_dns_zone_name = azurerm_private_dns_zone.this[each.key].name
  resource_group_name   = azurerm_resource_group.this.name
  virtual_network_id    = azurerm_virtual_network.jumpbox[0].id
  tags                  = local.tags
}

resource "azurerm_public_ip" "jumpbox_egress" {
  count = var.enable_jumpbox ? 1 : 0

  allocation_method   = "Static"
  location            = var.jumpbox_location
  name                = "pip-jumpbox-egress-${local.name_suffix}"
  resource_group_name = azurerm_resource_group.this.name
  sku                 = "Standard"
  tags                = local.tags

  lifecycle {
    ignore_changes = [ip_tags]
  }
}

resource "azurerm_nat_gateway" "jumpbox" {
  count = var.enable_jumpbox ? 1 : 0

  idle_timeout_in_minutes = 10
  location                = var.jumpbox_location
  name                    = "nat-jumpbox-${local.name_suffix}"
  resource_group_name     = azurerm_resource_group.this.name
  sku_name                = "Standard"
  tags                    = local.tags
}

resource "azurerm_nat_gateway_public_ip_association" "jumpbox" {
  count = var.enable_jumpbox ? 1 : 0

  nat_gateway_id       = azurerm_nat_gateway.jumpbox[0].id
  public_ip_address_id = azurerm_public_ip.jumpbox_egress[0].id
}

resource "azurerm_subnet_nat_gateway_association" "jumpbox" {
  count = var.enable_jumpbox ? 1 : 0

  nat_gateway_id = azurerm_nat_gateway.jumpbox[0].id
  subnet_id      = azurerm_subnet.jumpbox[0].id
}

resource "random_password" "jumpbox_admin" {
  count = var.enable_jumpbox ? 1 : 0

  length      = 24
  min_lower   = 1
  min_numeric = 1
  min_special = 1
  min_upper   = 1
  special     = true
}

resource "azapi_resource" "jumpbox_admin_password" {
  count = var.enable_jumpbox && var.enable_agent_service ? 1 : 0

  name      = "jumpbox-admin-password"
  parent_id = module.ai_foundry.key_vault_id["agent"]
  type      = "Microsoft.KeyVault/vaults/secrets@2023-07-01"
  body = {
    properties = {
      attributes = {
        enabled = true
      }
      contentType = "Password for ${azurerm_windows_virtual_machine.jumpbox[0].name} local administrator ${var.jumpbox_admin_username}"
      value       = random_password.jumpbox_admin[0].result
    }
  }
}

resource "azurerm_network_interface" "jumpbox" {
  count = var.enable_jumpbox ? 1 : 0

  location            = var.jumpbox_location
  name                = "nic-jumpbox-${local.name_suffix}"
  resource_group_name = azurerm_resource_group.this.name
  tags                = local.tags

  ip_configuration {
    name                          = "private"
    private_ip_address_allocation = "Dynamic"
    subnet_id                     = azurerm_subnet.jumpbox[0].id
  }
}

resource "azurerm_windows_virtual_machine" "jumpbox" {
  count = var.enable_jumpbox ? 1 : 0

  admin_password        = random_password.jumpbox_admin[0].result
  admin_username        = var.jumpbox_admin_username
  computer_name         = "jump-${var.environment}"
  location              = var.jumpbox_location
  name                  = "vm-jumpbox-${local.name_suffix}"
  network_interface_ids = [azurerm_network_interface.jumpbox[0].id]
  patch_assessment_mode = "AutomaticByPlatform"
  patch_mode            = "AutomaticByPlatform"
  resource_group_name   = azurerm_resource_group.this.name
  secure_boot_enabled   = true
  size                  = var.jumpbox_vm_size
  tags                  = local.tags
  vtpm_enabled          = true

  boot_diagnostics {}

  identity {
    type = "SystemAssigned"
  }

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "StandardSSD_LRS"
  }

  source_image_reference {
    offer     = "WindowsServer"
    publisher = "MicrosoftWindowsServer"
    sku       = "2025-datacenter-azure-edition"
    version   = "latest"
  }
}

resource "azurerm_virtual_machine_extension" "jumpbox_vm_access" {
  count = var.enable_jumpbox ? 1 : 0

  auto_upgrade_minor_version = true
  name                       = "VMAccessAgent"
  publisher                  = "Microsoft.Compute"
  type                       = "VMAccessAgent"
  type_handler_version       = "2.0"
  virtual_machine_id         = azurerm_windows_virtual_machine.jumpbox[0].id

  protected_settings = jsonencode({
    password = random_password.jumpbox_admin[0].result
    username = var.jumpbox_admin_username
  })

  tags = local.tags
}

resource "azurerm_role_assignment" "jumpbox_foundry_project_manager" {
  count = var.enable_jumpbox ? 1 : 0

  principal_id       = azurerm_windows_virtual_machine.jumpbox[0].identity[0].principal_id
  role_definition_id = "/subscriptions/${var.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/eadc314b-1a2d-4efa-be10-5d325db5065e"
  scope              = module.ai_foundry.ai_foundry_project_id["primary"]
}
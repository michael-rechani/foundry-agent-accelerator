locals {
  jumpbox_attach_os_disk = try(var.jumpbox_existing_os_disk.create_option == "Attach", false)
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

ephemeral "azurerm_key_vault_secret" "jumpbox_admin" {
  count        = var.enable_jumpbox && var.jumpbox_admin_secret != null ? 1 : 0
  key_vault_id = var.jumpbox_admin_secret.key_vault_id
  name         = var.jumpbox_admin_secret.name
  version      = var.jumpbox_admin_secret.version
}

resource "azapi_resource" "jumpbox" {
  count     = var.enable_jumpbox ? 1 : 0
  type      = "Microsoft.Compute/virtualMachines@2024-03-01"
  name      = "vm-jumpbox-${local.name_suffix}"
  parent_id = azurerm_resource_group.this.id
  location  = var.jumpbox_location
  tags      = local.tags
  identity {
    type         = "SystemAssigned"
    identity_ids = []
  }
  body = {
    properties = {
      for property, value in {
        hardwareProfile      = { vmSize = var.jumpbox_vm_size }
        extensionsTimeBudget = "PT1H30M"
        priority             = "Regular"
        networkProfile = {
          networkInterfaces = [{ id = azurerm_network_interface.jumpbox[0].id, properties = { primary = true } }]
        }
        diagnosticsProfile = { bootDiagnostics = { enabled = true } }
        securityProfile = {
          securityType = "TrustedLaunch"
          uefiSettings = { secureBootEnabled = true, vTpmEnabled = true }
        }
        osProfile = {
          adminUsername               = var.jumpbox_admin_username
          computerName                = "jump-${var.environment}"
          allowExtensionOperations    = true
          requireGuestProvisionSignal = true
          windowsConfiguration = {
            provisionVMAgent             = true
            enableAutomaticUpdates       = true
            enableVMAgentPlatformUpdates = true
            winRM                        = { listeners = [] }
            patchSettings = {
              assessmentMode              = "AutomaticByPlatform"
              patchMode                   = "AutomaticByPlatform"
              enableHotpatching           = false
              automaticByPlatformSettings = { bypassPlatformSafetyChecksOnUserSchedule = true }
            }
          }
        }
        storageProfile = {
          for property, value in {
            diskControllerType = "SCSI"
            dataDisks          = []
            imageReference = {
              offer = "WindowsServer", publisher = "MicrosoftWindowsServer"
              sku   = "2025-datacenter-azure-edition", version = "latest"
            }
            osDisk = {
              name       = var.jumpbox_existing_os_disk == null ? "vm-jumpbox-${local.name_suffix}-os" : var.jumpbox_existing_os_disk.name
              diskSizeGB = var.jumpbox_existing_os_disk == null ? 127 : var.jumpbox_existing_os_disk.size_gb
              managedDisk = var.jumpbox_existing_os_disk == null ? {
                storageAccountType = "StandardSSD_LRS"
                } : {
                id                 = var.jumpbox_existing_os_disk.id
                storageAccountType = var.jumpbox_existing_os_disk.storage_account_type
              }
              caching                 = "ReadWrite"
              createOption            = local.jumpbox_attach_os_disk ? "Attach" : "FromImage"
              deleteOption            = "Detach"
              osType                  = "Windows"
              writeAcceleratorEnabled = false
            }
          } : property => value if property != "imageReference" || !local.jumpbox_attach_os_disk
        }
      } : property => value if property != "osProfile" || !local.jumpbox_attach_os_disk
    }
  }
  sensitive_body = var.jumpbox_admin_secret == null || local.jumpbox_attach_os_disk ? null : {
    properties = { osProfile = { adminPassword = ephemeral.azurerm_key_vault_secret.jumpbox_admin[0].value } }
  }
  sensitive_body_version = var.jumpbox_admin_secret == null || local.jumpbox_attach_os_disk ? {} : {
    "properties.osProfile.adminPassword" = var.jumpbox_admin_secret.version
  }
  response_export_values = []

  lifecycle {
    prevent_destroy = true
  }
}

resource "azapi_resource" "jumpbox_vm_access" {
  count     = var.enable_jumpbox ? 1 : 0
  type      = "Microsoft.Compute/virtualMachines/extensions@2024-03-01"
  name      = "VMAccessAgent"
  parent_id = azapi_resource.jumpbox[0].id
  location  = var.jumpbox_location
  tags      = local.tags
  body = {
    properties = {
      publisher               = "Microsoft.Compute"
      type                    = "VMAccessAgent"
      typeHandlerVersion      = "2.0"
      autoUpgradeMinorVersion = true
      enableAutomaticUpgrade  = false
    }
  }
  sensitive_body = var.jumpbox_admin_secret == null ? null : {
    properties = {
      protectedSettings = {
        username = var.jumpbox_admin_username
        password = ephemeral.azurerm_key_vault_secret.jumpbox_admin[0].value
      }
    }
  }
  sensitive_body_version = var.jumpbox_admin_secret == null ? {} : {
    "properties.protectedSettings" = var.jumpbox_admin_secret.version
  }
  response_export_values = []
  lifecycle { prevent_destroy = true }
}

data "azapi_resource" "jumpbox_identity" {
  count                  = var.enable_jumpbox ? 1 : 0
  type                   = "Microsoft.Compute/virtualMachines@2024-03-01"
  resource_id            = azapi_resource.jumpbox[0].id
  response_export_values = ["identity.principalId"]
}

resource "azurerm_role_assignment" "jumpbox_foundry_project_manager" {
  count = var.enable_jumpbox ? 1 : 0

  principal_id       = data.azapi_resource.jumpbox_identity[0].output.identity.principalId
  role_definition_id = "/subscriptions/${var.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/eadc314b-1a2d-4efa-be10-5d325db5065e"
  scope              = module.ai_foundry.ai_foundry_project_id["primary"]
}
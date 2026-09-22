locals {
  resource_group_id = "/subscriptions/${var.subscription_id}/resourceGroups/${var.resource_group_name}"
}

data "azapi_resource" "management_network" {
  type                   = "Microsoft.Network/virtualNetworks@2025-01-01"
  name                   = var.virtual_network_name
  parent_id              = local.resource_group_id
  response_export_values = ["location"]
}

resource "azapi_resource" "subnet" {
  type      = "Microsoft.Network/virtualNetworks/subnets@2025-01-01"
  name      = "AzureBastionSubnet"
  parent_id = data.azapi_resource.management_network.id
  body = {
    properties = {
      addressPrefix = var.subnet_address_prefix
    }
  }
  response_export_values = []

  lifecycle {
    prevent_destroy = true
  }
}

resource "azapi_resource" "public_ip" {
  type      = "Microsoft.Network/publicIPAddresses@2025-01-01"
  name      = "${var.bastion_name}-pip"
  parent_id = local.resource_group_id
  location  = data.azapi_resource.management_network.location
  tags      = var.tags
  body = {
    sku = {
      name = "Standard"
      tier = "Regional"
    }
    properties = {
      publicIPAllocationMethod = "Static"
      publicIPAddressVersion   = "IPv4"
      idleTimeoutInMinutes     = 4
    }
  }
  response_export_values = []

  lifecycle {
    prevent_destroy = true
  }
}

# AzAPI can add the dedicated IP configuration without AzureRM forcing replacement.
resource "azapi_resource" "bastion" {
  type      = "Microsoft.Network/bastionHosts@2025-01-01"
  name      = var.bastion_name
  parent_id = local.resource_group_id
  location  = data.azapi_resource.management_network.location
  tags      = var.tags
  body = {
    sku = { name = "Standard" }
    properties = {
      scaleUnits     = 2
      virtualNetwork = null
      ipConfigurations = [{
        name = "bastion-ipconfig"
        properties = {
          privateIPAllocationMethod = "Dynamic"
          subnet                    = { id = azapi_resource.subnet.id }
          publicIPAddress           = { id = azapi_resource.public_ip.id }
        }
      }]
    }
  }
  response_export_values = ["properties.dnsName", "properties.provisioningState", "sku.name"]

  timeouts {
    create = "45m"
    update = "45m"
  }

  lifecycle {
    prevent_destroy = true
  }
}

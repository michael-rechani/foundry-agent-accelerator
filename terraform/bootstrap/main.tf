data "azapi_client_config" "current" {}

locals {
  storage_account_name = coalesce(
    var.storage_account_name,
    "st${var.name_prefix}${substr(sha256(var.subscription_id), 0, 8)}tf"
  )

  subnet_name = "snet-private-endpoints"

  # Storage Blob Data Contributor.
  blob_contributor_role_id = "ba92f5b4-2d11-453d-a403-e96b0029c9fe"

  contributors = merge(
    { current-operator = data.azapi_client_config.current.object_id },
    var.state_contributor_object_ids,
  )

  dns_linked_networks = merge(
    { state = azapi_resource.vnet.id },
    var.peered_virtual_network_ids,
  )
}

resource "azapi_resource" "resource_group" {
  type      = "Microsoft.Resources/resourceGroups@2024-03-01"
  name      = var.resource_group_name
  parent_id = "/subscriptions/${var.subscription_id}"
  location  = var.location
  tags      = var.tags
}

resource "azapi_resource" "vnet" {
  type      = "Microsoft.Network/virtualNetworks@2024-05-01"
  name      = "vnet-tfstate"
  parent_id = azapi_resource.resource_group.id
  location  = var.location
  tags      = var.tags
  body = {
    properties = {
      addressSpace = { addressPrefixes = var.virtual_network_address_space }
      subnets = [{
        name = local.subnet_name
        properties = {
          addressPrefix                  = var.private_endpoint_subnet_address_prefix
          privateEndpointNetworkPolicies = "Disabled"
          defaultOutboundAccess          = false
        }
      }]
    }
  }
}

resource "azapi_resource" "dns_zone" {
  type      = "Microsoft.Network/privateDnsZones@2024-06-01"
  name      = "privatelink.blob.core.windows.net"
  parent_id = azapi_resource.resource_group.id
  location  = "global"
  tags      = var.tags
  body      = {}
}

resource "azapi_resource" "dns_link" {
  for_each = local.dns_linked_networks

  type      = "Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01"
  name      = "link-${each.key}"
  parent_id = azapi_resource.dns_zone.id
  location  = "global"
  tags      = var.tags
  body = {
    properties = {
      registrationEnabled = false
      virtualNetwork      = { id = each.value }
    }
  }
}

resource "azapi_resource" "peer_from_state" {
  for_each = var.peered_virtual_network_ids

  type      = "Microsoft.Network/virtualNetworks/virtualNetworkPeerings@2024-05-01"
  name      = "peer-to-${each.key}"
  parent_id = azapi_resource.vnet.id
  body = {
    properties = {
      remoteVirtualNetwork      = { id = each.value }
      allowVirtualNetworkAccess = true
      allowForwardedTraffic     = false
      allowGatewayTransit       = false
      useRemoteGateways         = false
    }
  }
}

resource "azapi_resource" "peer_to_state" {
  for_each = var.peered_virtual_network_ids

  type      = "Microsoft.Network/virtualNetworks/virtualNetworkPeerings@2024-05-01"
  name      = "peer-to-tfstate"
  parent_id = each.value
  body = {
    properties = {
      remoteVirtualNetwork      = { id = azapi_resource.vnet.id }
      allowVirtualNetworkAccess = true
      allowForwardedTraffic     = false
      allowGatewayTransit       = false
      useRemoteGateways         = false
    }
  }
}

resource "azapi_resource" "storage" {
  type      = "Microsoft.Storage/storageAccounts@2025-01-01"
  name      = local.storage_account_name
  parent_id = azapi_resource.resource_group.id
  location  = var.location
  tags      = var.tags
  body = {
    kind = "StorageV2"
    sku  = { name = "Standard_ZRS" }
    properties = {
      accessTier                   = "Hot"
      allowBlobPublicAccess        = false
      allowCrossTenantReplication  = false
      allowSharedKeyAccess         = false
      defaultToOAuthAuthentication = true
      isHnsEnabled                 = false
      isSftpEnabled                = false
      minimumTlsVersion            = "TLS1_2"
      supportsHttpsTrafficOnly     = true
      publicNetworkAccess          = "Disabled"
      networkAcls = {
        bypass              = "None"
        defaultAction       = "Deny"
        ipRules             = []
        virtualNetworkRules = []
      }
    }
  }
  lifecycle { prevent_destroy = true }
}

resource "azapi_update_resource" "blob_service" {
  type      = "Microsoft.Storage/storageAccounts/blobServices@2025-01-01"
  name      = "default"
  parent_id = azapi_resource.storage.id
  body = {
    properties = {
      isVersioningEnabled            = true
      deleteRetentionPolicy          = { enabled = true, days = 90 }
      containerDeleteRetentionPolicy = { enabled = true, days = 7 }
    }
  }
}

resource "azapi_resource" "container" {
  type      = "Microsoft.Storage/storageAccounts/blobServices/containers@2025-01-01"
  name      = var.container_name
  parent_id = "${azapi_resource.storage.id}/blobServices/default"
  body = {
    properties = { publicAccess = "None" }
  }
  depends_on = [azapi_update_resource.blob_service]
  lifecycle { prevent_destroy = true }
}

resource "azapi_resource" "private_endpoint" {
  type      = "Microsoft.Network/privateEndpoints@2024-05-01"
  name      = "${local.storage_account_name}-blob-pe"
  parent_id = azapi_resource.resource_group.id
  location  = var.location
  tags      = var.tags
  body = {
    properties = {
      subnet = { id = "${azapi_resource.vnet.id}/subnets/${local.subnet_name}" }
      privateLinkServiceConnections = [{
        name = "pse-${local.storage_account_name}"
        properties = {
          privateLinkServiceId = azapi_resource.storage.id
          groupIds             = ["blob"]
        }
      }]
    }
  }
  lifecycle { prevent_destroy = true }
}

resource "azapi_resource" "private_endpoint_dns" {
  type      = "Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-05-01"
  name      = "default"
  parent_id = azapi_resource.private_endpoint.id
  body = {
    properties = {
      privateDnsZoneConfigs = [{
        name       = "blob"
        properties = { privateDnsZoneId = azapi_resource.dns_zone.id }
      }]
    }
  }
}

resource "azapi_resource" "blob_contributor" {
  for_each = local.contributors

  type      = "Microsoft.Authorization/roleAssignments@2022-04-01"
  name      = uuidv5("url", "${azapi_resource.storage.id}/${each.value}/${local.blob_contributor_role_id}")
  parent_id = azapi_resource.storage.id
  body = {
    properties = {
      principalId      = each.value
      roleDefinitionId = "/subscriptions/${var.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/${local.blob_contributor_role_id}"
    }
  }
}

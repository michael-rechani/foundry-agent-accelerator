resource "azapi_resource" "agent_storage" {
  type      = "Microsoft.Storage/storageAccounts@2025-01-01"
  name      = local.agent_storage_account_name
  parent_id = azurerm_resource_group.this.id
  location  = local.deployment_location
  tags      = local.tags
  identity {
    type         = "None"
    identity_ids = []
  }
  body = {
    kind = "StorageV2"
    sku  = { name = "Standard_${local.region_preference.storage_replication_type}" }
    properties = {
      accessTier                   = "Hot"
      allowBlobPublicAccess        = false
      allowCrossTenantReplication  = false
      allowSharedKeyAccess         = false
      defaultToOAuthAuthentication = false
      dnsEndpointType              = "Standard"
      isHnsEnabled                 = false
      isLocalUserEnabled           = false
      isNfsV3Enabled               = false
      isSftpEnabled                = false
      minimumTlsVersion            = "TLS1_2"
      supportsHttpsTrafficOnly     = true
      publicNetworkAccess          = "Disabled"
      encryption = {
        keySource = "Microsoft.Storage"
        services = {
          blob = { enabled = true, keyType = "Account" }
          file = { enabled = true, keyType = "Account" }
        }
      }
      networkAcls = {
        bypass              = "None"
        defaultAction       = "Deny"
        ipRules             = []
        virtualNetworkRules = []
        resourceAccessRules = [
          {
            resourceId = "/subscriptions/${var.subscription_id}/providers/Microsoft.Security/datascanners/StorageDataScanner"
            tenantId   = data.azurerm_client_config.current.tenant_id
          },
          # Foundry's hosted asset store writes evaluation results here as the project identity from outside the VNet.
          # The ID is built from names because the Foundry module depends on this account.
          {
            resourceId = "/subscriptions/${var.subscription_id}/resourceGroups/${azurerm_resource_group.this.name}/providers/Microsoft.CognitiveServices/accounts/${local.foundry_account_name}/projects/${local.foundry_project_name}"
            tenantId   = data.azurerm_client_config.current.tenant_id
          },
        ]
      }
    }
  }
  lifecycle { prevent_destroy = true }
}

resource "azurerm_private_endpoint" "agent_storage" {
  name                = "${local.agent_storage_account_name}-blob-pe"
  location            = local.deployment_location
  resource_group_name = azurerm_resource_group.this.name
  subnet_id           = azurerm_subnet.private_endpoints.id
  private_service_connection {
    name                           = "pse-${local.agent_storage_account_name}"
    private_connection_resource_id = azapi_resource.agent_storage.id
    is_manual_connection           = false
    subresource_names              = ["blob"]
  }
  private_dns_zone_group {
    name                 = "default"
    private_dns_zone_ids = [azurerm_private_dns_zone.this["storage_blob"].id]
  }
  lifecycle { prevent_destroy = true }
}

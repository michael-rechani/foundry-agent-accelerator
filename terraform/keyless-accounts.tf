resource "azapi_resource" "platform_logs" {
  type      = "Microsoft.OperationalInsights/workspaces@2023-09-01"
  name      = module.naming.log_analytics_workspace.name_unique
  parent_id = azurerm_resource_group.this.id
  location  = local.deployment_location
  tags      = local.tags
  body = {
    properties = {
      sku                             = { name = "PerGB2018" }
      retentionInDays                 = 30
      workspaceCapping                = { dailyQuotaGb = -1 }
      publicNetworkAccessForIngestion = "Disabled"
      publicNetworkAccessForQuery     = "Disabled"
      features = {
        disableLocalAuth                            = true
        enableLogAccessUsingOnlyResourcePermissions = true
        legacy                                      = 0
        searchVersion                               = 1
      }
    }
  }
  lifecycle { prevent_destroy = true }
}

resource "azapi_resource" "cosmos" {
  type      = "Microsoft.DocumentDB/databaseAccounts@2024-11-15"
  name      = local.cosmosdb_account_name
  parent_id = azurerm_resource_group.this.id
  location  = local.deployment_location
  tags      = local.tags
  identity {
    type         = "None"
    identity_ids = []
  }
  body = {
    kind = "GlobalDocumentDB"
    properties = {
      databaseAccountOfferType             = "Standard"
      defaultIdentity                      = "FirstPartyIdentity"
      createMode                           = "Default"
      disableKeyBasedMetadataWriteAccess   = true
      disableLocalAuth                     = true
      minimalTlsVersion                    = "Tls12"
      publicNetworkAccess                  = "Disabled"
      networkAclBypass                     = "None"
      networkAclBypassResourceIds          = []
      isVirtualNetworkFilterEnabled        = false
      virtualNetworkRules                  = []
      ipRules                              = []
      cors                                 = []
      capabilities                         = []
      enableAnalyticalStorage              = false
      enableAutomaticFailover              = true
      enableMultipleWriteLocations         = false
      enableBurstCapacity                  = false
      enableFreeTier                       = false
      enablePartitionMerge                 = false
      enablePerRegionPerPartitionAutoscale = true
      analyticalStorageConfiguration       = { schemaType = "WellDefined" }
      backupPolicy                         = { type = "Continuous", continuousModeProperties = { tier = "Continuous30Days" } }
      capacity                             = { totalThroughputLimit = -1 }
      consistencyPolicy                    = { defaultConsistencyLevel = "Session", maxIntervalInSeconds = 5, maxStalenessPrefix = 100 }
      locations = concat(
        [{ locationName = local.region_preference.display_name, failoverPriority = 0, isZoneRedundant = false }],
        [for index, region in local.region_preference.cosmos_secondary_regions : { locationName = local.region_preferences[region].display_name, failoverPriority = index + 1, isZoneRedundant = false }]
      )
    }
  }
  lifecycle { prevent_destroy = true }
}

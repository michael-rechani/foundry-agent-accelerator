locals {
  region_preferences = {
    northcentralus = {
      display_name             = "North Central US"
      priority                 = 1
      cosmos_secondary_regions = []
      storage_replication_type = "LRS"
    }
    westus3 = {
      display_name             = "West US 3"
      priority                 = 2
      cosmos_secondary_regions = []
      storage_replication_type = "ZRS"
    }
    southcentralus = {
      display_name             = "South Central US"
      priority                 = 3
      cosmos_secondary_regions = ["northcentralus"]
      storage_replication_type = "ZRS"
    }
    westus = {
      display_name             = "West US"
      priority                 = 4
      cosmos_secondary_regions = []
      storage_replication_type = "ZRS"
    }
  }

  default_location    = one([for name, preference in local.region_preferences : name if preference.priority == 1])
  deployment_location = coalesce(var.location, local.default_location)
  region_preference   = local.region_preferences[local.deployment_location]
}
locals {
  # Verified against the Lab subscription on 2026-09-03.
  region_preferences = {
    northcentralus = {
      priority                 = 1
      cosmos_secondary_regions = []
      storage_replication_type = "LRS"
    }
    westus3 = {
      priority                 = 2
      cosmos_secondary_regions = []
      storage_replication_type = "ZRS"
    }
    southcentralus = {
      priority                 = 3
      cosmos_secondary_regions = ["northcentralus"]
      storage_replication_type = "ZRS"
    }
    westus = {
      priority                 = 4
      cosmos_secondary_regions = []
      storage_replication_type = "ZRS"
    }
  }

  default_location    = one([for name, preference in local.region_preferences : name if preference.priority == 1])
  deployment_location = coalesce(var.location, local.default_location)
  region_preference   = local.region_preferences[local.deployment_location]
}
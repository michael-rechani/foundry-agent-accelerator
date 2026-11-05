mock_provider "azapi" {}

variables {
  subscription_id = "11111111-2222-3333-4444-555555555555"
}

run "private_backend" {
  command = plan

  assert {
    condition = (
      azapi_resource.storage.body.properties.publicNetworkAccess == "Disabled" &&
      azapi_resource.storage.body.properties.allowBlobPublicAccess == false &&
      azapi_resource.storage.body.properties.allowSharedKeyAccess == false &&
      azapi_resource.storage.body.properties.defaultToOAuthAuthentication == true &&
      azapi_resource.storage.body.properties.supportsHttpsTrafficOnly == true &&
      azapi_resource.storage.body.properties.minimumTlsVersion == "TLS1_2" &&
      azapi_resource.storage.body.properties.networkAcls.defaultAction == "Deny" &&
      azapi_resource.storage.body.properties.networkAcls.bypass == "None" &&
      length(azapi_resource.storage.body.properties.networkAcls.ipRules) == 0 &&
      length(azapi_resource.storage.body.properties.networkAcls.virtualNetworkRules) == 0 &&
      azapi_resource.container.body.properties.publicAccess == "None"
    )
    error_message = "The backend must be private from creation, without shared-key, anonymous, or firewall bypass access."
  }

  assert {
    condition = (
      azapi_update_resource.blob_service.body.properties.isVersioningEnabled &&
      azapi_update_resource.blob_service.body.properties.deleteRetentionPolicy.enabled &&
      azapi_update_resource.blob_service.body.properties.deleteRetentionPolicy.days == 90 &&
      azapi_update_resource.blob_service.body.properties.containerDeleteRetentionPolicy.enabled &&
      azapi_update_resource.blob_service.body.properties.containerDeleteRetentionPolicy.days == 7
    )
    error_message = "State versioning and soft-delete protection must remain enabled."
  }

  assert {
    condition = (
      azapi_resource.dns_zone.name == "privatelink.blob.core.windows.net" &&
      keys(azapi_resource.dns_link) == ["state"] &&
      length(azapi_resource.peer_from_state) == 0 &&
      length(azapi_resource.peer_to_state) == 0 &&
      azapi_resource.private_endpoint.body.properties.privateLinkServiceConnections[0].properties.groupIds == ["blob"]
    )
    error_message = "Bootstrap must own one blob namespace and a private blob endpoint."
  }
}

run "management_and_runner_share_one_zone" {
  command = plan

  variables {
    peered_virtual_network_ids = {
      management = "/subscriptions/11111111-2222-3333-4444-555555555555/resourceGroups/rg-platform/providers/Microsoft.Network/virtualNetworks/vnet-management"
    }
  }

  assert {
    condition = (
      length(azapi_resource.dns_link) == 2 &&
      azapi_resource.dns_link["management"].body.properties.virtualNetwork.id == var.peered_virtual_network_ids["management"] &&
      azapi_resource.peer_from_state["management"].body.properties.remoteVirtualNetwork.id == var.peered_virtual_network_ids["management"] &&
      azapi_resource.peer_to_state["management"].parent_id == var.peered_virtual_network_ids["management"] &&
      azapi_resource.dns_link["management"].body.properties.registrationEnabled == false
    )
    error_message = "Bootstrap owns the management/runner link and bidirectional state peering."
  }
}

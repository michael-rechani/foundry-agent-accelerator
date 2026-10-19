mock_provider "azapi" {
  mock_data "azapi_client_config" {
    defaults = {
      object_id = "00000000-0000-0000-0000-0000000000aa"
      tenant_id = "00000000-0000-0000-0000-0000000000bb"
    }
  }
}

variables {
  subscription_id = "00000000-0000-0000-0000-000000000001"
}

run "private_only_state_account" {
  command = plan

  assert {
    condition = (
      azapi_resource.storage.body.properties.publicNetworkAccess == "Disabled" &&
      azapi_resource.storage.body.properties.allowSharedKeyAccess == false &&
      azapi_resource.storage.body.properties.allowBlobPublicAccess == false &&
      azapi_resource.storage.body.properties.networkAcls.defaultAction == "Deny" &&
      azapi_resource.storage.body.properties.minimumTlsVersion == "TLS1_2"
    )
    error_message = "The state account must be private, Entra-only, and TLS 1.2."
  }
  assert {
    condition     = azapi_resource.container.body.properties.publicAccess == "None"
    error_message = "The state container must not allow anonymous access."
  }
  assert {
    condition = (
      azapi_update_resource.blob_service.body.properties.isVersioningEnabled == true &&
      azapi_update_resource.blob_service.body.properties.deleteRetentionPolicy.days == 90 &&
      azapi_update_resource.blob_service.body.properties.containerDeleteRetentionPolicy.days == 7
    )
    error_message = "State needs versioning, 90-day blob soft-delete and seven-day container soft-delete."
  }
  assert {
    condition     = length(local.storage_account_name) <= 24 && can(regex("^[a-z0-9]+$", local.storage_account_name))
    error_message = "The derived account name must be a valid storage account name."
  }
  assert {
    condition     = length(azapi_resource.blob_contributor) == 1
    error_message = "The running identity must get blob data access."
  }
}

run "peers_and_links_runner_network" {
  command = plan

  variables {
    peered_virtual_network_ids = {
      management = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-example/providers/Microsoft.Network/virtualNetworks/vnet-management"
    }
    state_contributor_object_ids = {
      runner = "00000000-0000-0000-0000-0000000000cc"
    }
  }

  assert {
    condition     = length(azapi_resource.peer_from_state) == 1 && length(azapi_resource.peer_to_state) == 1
    error_message = "A peered network needs peering in both directions."
  }
  assert {
    condition     = length(azapi_resource.dns_link) == 2
    error_message = "The state VNet and each peered VNet need a blob DNS link."
  }
  assert {
    condition     = length(azapi_resource.blob_contributor) == 2
    error_message = "Extra contributors must each get blob data access."
  }
}

run "rejects_bad_prefix" {
  command = plan

  variables {
    name_prefix = "Not_Valid"
  }

  expect_failures = [var.name_prefix]
}

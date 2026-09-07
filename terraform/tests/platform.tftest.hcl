mock_provider "azurerm" {
  mock_data "azurerm_client_config" {
    defaults = {
      tenant_id       = "00000000-0000-0000-0000-000000000001"
      object_id       = "00000000-0000-0000-0000-000000000002"
      subscription_id = "00000000-0000-0000-0000-000000000003"
    }
  }
}

mock_provider "azapi" {
  mock_data "azapi_resource" {
    defaults = {
      output = { identity = { principalId = "00000000-0000-0000-0000-000000000004" } }
    }
  }
}

override_module {
  target = module.naming
  outputs = {
    resource_group          = { name_unique = "rg-platform-test-12345" }
    virtual_network         = { name_unique = "vnet-platform-test-12345" }
    cosmosdb_account        = { name_unique = "cosmos-platform-test-12345" }
    storage_account         = { name_unique = "stplatformtest12345" }
    log_analytics_workspace = { name_unique = "law-platform-test-12345" }
  }
}

variables {
  subscription_id = "00000000-0000-0000-0000-000000000003"
}

run "fresh_defaults" {
  command = plan

  assert {
    condition     = azapi_resource.agent_storage.name == "stplatformtest12345" && azapi_resource.agent_storage.body.sku.name == "Standard_LRS"
    error_message = "Fresh storage must use shared naming and default-region replication."
  }
  assert {
    condition     = azapi_resource.cosmos.body.properties.locations[0].locationName == "North Central US" && length(azapi_resource.cosmos.body.properties.locations) == 1
    error_message = "Default Cosmos topology must use the selected region."
  }
  assert {
    condition     = !var.enable_jumpbox && !var.enable_api_management && length(azurerm_virtual_network.jumpbox) == 1 && length(azurerm_subnet.jumpbox) == 1
    error_message = "Default configuration must retain Lab management networking without enabling a VM or APIM."
  }
  assert {
    condition = (
      azapi_resource.cosmos.body.properties.disableLocalAuth &&
      azapi_resource.cosmos.body.properties.publicNetworkAccess == "Disabled" &&
      !azapi_resource.agent_storage.body.properties.allowSharedKeyAccess &&
      azapi_resource.agent_storage.body.properties.publicNetworkAccess == "Disabled" &&
      azapi_resource.platform_logs.body.properties.features.disableLocalAuth
    )
    error_message = "Cleanup must preserve keyless authentication and private access."
  }
}

run "westus3_region" {
  command = plan
  variables { location = "westus3" }
  assert {
    condition     = azapi_resource.cosmos.body.properties.locations[0].locationName == "West US 3" && azapi_resource.agent_storage.body.sku.name == "Standard_ZRS"
    error_message = "Cosmos and storage must follow the West US 3 profile."
  }
}

run "southcentralus_region" {
  command = plan
  variables { location = "southcentralus" }
  assert {
    condition = (
      azapi_resource.cosmos.body.properties.locations[0].locationName == "South Central US" &&
      azapi_resource.cosmos.body.properties.locations[1].locationName == "North Central US" &&
      azapi_resource.cosmos.body.properties.locations[1].failoverPriority == 1 &&
      azapi_resource.agent_storage.body.sku.name == "Standard_ZRS"
    )
    error_message = "South Central US must retain its configured secondary region and replication."
  }
}

run "existing_names" {
  command = plan
  variables {
    agent_storage_account_name = "existingstorage123"
    cosmosdb_account_name      = "existing-cosmos-test"
  }
  assert {
    condition = (
      azapi_resource.agent_storage.name == "existingstorage123" &&
      azurerm_private_endpoint.agent_storage.name == "existingstorage123-blob-pe" &&
      azurerm_private_endpoint.agent_storage.private_service_connection[0].name == "pse-existingstorage123" &&
      azapi_resource.cosmos.name == "existing-cosmos-test"
    )
    error_message = "Existing-name overrides must preserve account and endpoint names together."
  }
}

run "reject_invalid_storage_name" {
  command = plan
  variables { agent_storage_account_name = "Invalid-Storage" }
  expect_failures = [var.agent_storage_account_name]
}

run "reject_missing_vm_credential" {
  command = plan
  variables { enable_jumpbox = true }
  expect_failures = [var.enable_jumpbox]
}

run "existing_vm_disk" {
  command = plan
  variables {
    enable_jumpbox = true
    jumpbox_existing_os_disk = {
      id                   = "/subscriptions/00000000-0000-0000-0000-000000000003/resourceGroups/rg-platform-test-12345/providers/Microsoft.Compute/disks/existing-os"
      name                 = "existing-os"
      storage_account_type = "Standard_LRS"
    }
  }
  assert {
    condition = (
      var.enable_jumpbox &&
      azapi_resource.jumpbox[0].body.properties.storageProfile.osDisk.name == "existing-os" &&
      var.jumpbox_admin_secret == null &&
      length(azapi_resource.jumpbox_vm_access) == 0
    )
    error_message = "Adopting an existing VM without a credential reference must preserve its disk and omit the access extension."
  }
}

run "attach_existing_vm_disk" {
  command = plan
  variables {
    enable_jumpbox = true
    jumpbox_existing_os_disk = {
      id                   = "/subscriptions/00000000-0000-0000-0000-000000000003/resourceGroups/rg-platform-test-12345/providers/Microsoft.Compute/disks/existing-os"
      name                 = "existing-os"
      storage_account_type = "StandardSSD_LRS"
      create_option        = "Attach"
    }
  }
  assert {
    condition = (
      azapi_resource.jumpbox[0].body.properties.storageProfile.osDisk.createOption == "Attach" &&
      azapi_resource.jumpbox[0].body.properties.storageProfile.osDisk.deleteOption == "Detach" &&
      !contains(keys(azapi_resource.jumpbox[0].body.properties), "osProfile") &&
      !contains(keys(azapi_resource.jumpbox[0].body.properties.storageProfile), "imageReference") &&
      length(azapi_resource.jumpbox_vm_access) == 0
    )
    error_message = "Attaching a retained disk must omit image provisioning, credentials, and the access extension while retaining the disk."
  }
}

run "new_vm_pinned_secret" {
  command = plan
  variables {
    enable_jumpbox = true
    jumpbox_admin_secret = {
      key_vault_id = "/subscriptions/00000000-0000-0000-0000-000000000003/resourceGroups/rg-platform-test-12345/providers/Microsoft.KeyVault/vaults/kv-platform-test"
      name         = "admin-password"
      version      = "0123456789abcdef0123456789abcdef"
    }
  }
  assert {
    condition = (
      var.enable_jumpbox &&
      var.jumpbox_existing_os_disk == null &&
      var.jumpbox_admin_secret.version == "0123456789abcdef0123456789abcdef" &&
      length(azapi_resource.jumpbox_vm_access) == 1
    )
    error_message = "New VM inputs must accept a pinned secret reference without an existing disk."
  }
}

run "reject_unpinned_secret" {
  command = plan
  variables {
    jumpbox_admin_secret = {
      key_vault_id = "/subscriptions/00000000-0000-0000-0000-000000000003/resourceGroups/rg-platform-test-12345/providers/Microsoft.KeyVault/vaults/kv-platform-test"
      name         = "admin-password"
      version      = "latest"
    }
  }
  expect_failures = [var.jumpbox_admin_secret]
}

run "apim_without_vm" {
  command = plan
  variables {
    enable_api_management          = true
    enable_management_network      = false
    api_management_publisher_email = "owner@example.com"
  }
  assert {
    condition = (
      var.enable_api_management && !var.enable_jumpbox && length(azurerm_virtual_network.jumpbox) == 1
    )
    error_message = "APIM must provision its management network while the VM remains disabled."
  }
}

run "management_network_opt_out" {
  command = plan
  variables { enable_management_network = false }
  assert {
    condition     = length(azurerm_virtual_network.jumpbox) == 0 && length(azurerm_subnet.jumpbox) == 0
    error_message = "A platform without Lab, APIM, or a VM can opt out of the management network."
  }
}

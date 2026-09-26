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
    condition     = !var.enable_jumpbox && !var.enable_api_management && length(azurerm_virtual_network.jumpbox) == 1 && length(azurerm_subnet.jumpbox) == 1 && length(azurerm_dev_test_global_vm_shutdown_schedule.jumpbox) == 0
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
  assert {
    condition = (
      azapi_resource.agent_storage.body.properties.networkAcls.bypass == "None" &&
      azapi_resource.agent_storage.body.properties.networkAcls.defaultAction == "Deny" &&
      length(azapi_resource.agent_storage.body.properties.networkAcls.resourceAccessRules) == 2 &&
      azapi_resource.agent_storage.body.properties.networkAcls.resourceAccessRules[1].resourceId == "/subscriptions/00000000-0000-0000-0000-000000000003/resourceGroups/rg-platform-test-12345/providers/Microsoft.CognitiveServices/accounts/foundry-hosted-agents-platform-test-12345/projects/hosted-agents-dev"
    )
    error_message = "Agent storage must admit only the scanner and this Foundry project, without the trusted-services bypass."
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

run "reject_duplicate_or_empty_model_deployment" {
  command = plan
  variables {
    additional_model_deployments = {
      "gpt-4.1"      = { name = "gpt-4.1", version = "2025-04-14", capacity = 10 }
      "gpt-4.1-mini" = { name = "gpt-4.1-mini", version = "2025-04-14", capacity = 0 }
    }
  }
  expect_failures = [var.additional_model_deployments]
}

run "reject_invalid_ai_search_replica_count" {
  command = plan
  variables { ai_search_replica_count = 0 }
  expect_failures = [var.ai_search_replica_count]
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
  assert {
    condition = (
      length(azurerm_dev_test_global_vm_shutdown_schedule.jumpbox) == 1 &&
      azurerm_dev_test_global_vm_shutdown_schedule.jumpbox[0].enabled &&
      azurerm_dev_test_global_vm_shutdown_schedule.jumpbox[0].daily_recurrence_time == "0300" &&
      azurerm_dev_test_global_vm_shutdown_schedule.jumpbox[0].timezone == "UTC" &&
      azurerm_dev_test_global_vm_shutdown_schedule.jumpbox[0].location == var.jumpbox_location &&
      !azurerm_dev_test_global_vm_shutdown_schedule.jumpbox[0].notification_settings[0].enabled
    )
    error_message = "An enabled jumpbox must get the default nightly shutdown in its own region."
  }
}

run "jumpbox_shutdown_settings" {
  command = plan
  variables {
    enable_jumpbox = true
    jumpbox_existing_os_disk = {
      id                   = "/subscriptions/00000000-0000-0000-0000-000000000003/resourceGroups/rg-platform-test-12345/providers/Microsoft.Compute/disks/existing-os"
      name                 = "existing-os"
      storage_account_type = "Standard_LRS"
    }
    jumpbox_auto_shutdown = { time = "1930", timezone = "Pacific Standard Time" }
  }
  assert {
    condition = (
      azurerm_dev_test_global_vm_shutdown_schedule.jumpbox[0].daily_recurrence_time == "1930" &&
      azurerm_dev_test_global_vm_shutdown_schedule.jumpbox[0].timezone == "Pacific Standard Time"
    )
    error_message = "Custom shutdown settings must reach the schedule."
  }
}

run "jumpbox_shutdown_opt_out" {
  command = plan
  variables {
    enable_jumpbox = true
    jumpbox_existing_os_disk = {
      id                   = "/subscriptions/00000000-0000-0000-0000-000000000003/resourceGroups/rg-platform-test-12345/providers/Microsoft.Compute/disks/existing-os"
      name                 = "existing-os"
      storage_account_type = "Standard_LRS"
    }
    jumpbox_auto_shutdown = null
  }
  assert {
    condition     = length(azurerm_dev_test_global_vm_shutdown_schedule.jumpbox) == 0 && length(azapi_resource.jumpbox) == 1
    error_message = "A null shutdown setting must keep the VM without a schedule."
  }
}

run "reject_invalid_shutdown_time" {
  command = plan
  variables {
    jumpbox_auto_shutdown = { time = "7pm" }
  }
  expect_failures = [var.jumpbox_auto_shutdown]
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

run "coordinator_access_defaults_off" {
  command = plan
  assert {
    condition     = var.coordinator_agent_access == null && length(azapi_resource.coordinator_agent_consumer) == 0
    error_message = "Coordinator grants must be opt-in."
  }
}

run "coordinator_access_default_specialists" {
  command = plan
  variables {
    coordinator_agent_access = { principal_id = "AAAAAAAA-0000-0000-0000-000000000005" }
  }
  assert {
    condition     = toset(keys(azapi_resource.coordinator_agent_consumer)) == toset(["application-review-agent", "case-review-agent"])
    error_message = "The coordinator must be granted access to each default specialist."
  }
  assert {
    condition = alltrue([
      for grant in values(azapi_resource.coordinator_agent_consumer) :
      grant.type == "Microsoft.Authorization/roleAssignments@2022-04-01" &&
      grant.body.properties.roleDefinitionId == "/subscriptions/00000000-0000-0000-0000-000000000003/providers/Microsoft.Authorization/roleDefinitions/eed3b665-ab3a-47b6-8f48-c9382fb1dad6" &&
      grant.body.properties.principalId == "aaaaaaaa-0000-0000-0000-000000000005" &&
      grant.body.properties.principalType == "ServicePrincipal"
    ])
    error_message = "Each grant must assign Foundry Agent Consumer to the normalized coordinator principal."
  }
  assert {
    condition = alltrue([
      for name, grant in azapi_resource.coordinator_agent_consumer :
      grant.parent_id == "/subscriptions/00000000-0000-0000-0000-000000000003/resourceGroups/rg-platform-test-12345/providers/Microsoft.CognitiveServices/accounts/foundry-platform-test/projects/hosted-agents-dev/agents/${name}" &&
      grant.name == uuidv5("url", "${grant.parent_id}/aaaaaaaa-0000-0000-0000-000000000005/Foundry Agent Consumer")
    ])
    error_message = "Each grant must be scoped to one specialist agent and use a deterministic assignment name."
  }
}

run "coordinator_access_profile_specialists" {
  command = plan
  variables {
    coordinator_agent_access = {
      principal_id      = "aaaaaaaa-0000-0000-0000-000000000005"
      specialist_agents = ["evidence-review-agent"]
    }
  }
  assert {
    condition     = keys(azapi_resource.coordinator_agent_consumer) == ["evidence-review-agent"]
    error_message = "Profile specialists must replace the default specialist list."
  }
}

run "reject_coordinator_access_client_id_format" {
  command = plan
  variables {
    coordinator_agent_access = { principal_id = "api://not-a-principal" }
  }
  expect_failures = [var.coordinator_agent_access]
}

run "reject_coordinator_access_path_or_empty_specialists" {
  command = plan
  variables {
    coordinator_agent_access = {
      principal_id      = "aaaaaaaa-0000-0000-0000-000000000005"
      specialist_agents = ["agents/case-review-agent"]
    }
  }
  expect_failures = [var.coordinator_agent_access]
}

run "reject_coordinator_access_without_specialists" {
  command = plan
  variables {
    coordinator_agent_access = {
      principal_id      = "aaaaaaaa-0000-0000-0000-000000000005"
      specialist_agents = []
    }
  }
  expect_failures = [var.coordinator_agent_access]
}

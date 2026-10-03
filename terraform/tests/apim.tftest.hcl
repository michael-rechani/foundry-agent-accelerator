# Offline assertions for apim.tf and the variables that gate it.
# test-platform-validation.ps1 runs these against a copy of the whole root module.
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
  # Runs that enable a public piece also record its approval; the gate itself is tested in platform.tftest.hcl.
  approve_public_api_management    = true
  approve_jumpbox_egress_public_ip = true
  approve_jumpbox_admin_account    = true
}

run "apim_off_by_default" {
  command = plan
  assert {
    condition = (
      length(azurerm_network_security_group.api_management) == 0 &&
      length(azurerm_subnet.api_management) == 0 &&
      length(azurerm_subnet_network_security_group_association.api_management) == 0 &&
      length(module.api_management) == 0
    )
    error_message = "API Management and its network must not exist unless enable_api_management is set."
  }
  assert {
    condition     = output.api_management_name == null && output.api_management_id == null && output.api_management_gateway_url == null
    error_message = "The API Management outputs must be null while the gateway is disabled."
  }
}

run "reject_unapproved_public_gateway" {
  command = plan
  variables {
    enable_api_management          = true
    api_management_publisher_email = "owner@example.com"
    approve_public_api_management  = false
  }
  expect_failures = [var.approve_public_api_management]
}

run "apim_network_when_enabled" {
  command = plan
  variables {
    enable_api_management          = true
    api_management_publisher_email = "owner@example.com"
  }
  assert {
    condition     = length(module.api_management) == 1 && length(azurerm_subnet_network_security_group_association.api_management) == 1
    error_message = "Enabling API Management must create the gateway and attach its security group to its subnet."
  }
  assert {
    condition = (
      azurerm_network_security_group.api_management[0].name == "nsg-apim-aifnd-dev" &&
      azurerm_network_security_group.api_management[0].location == "westus" &&
      length(azurerm_network_security_group.api_management[0].security_rule) == 1 &&
      one(azurerm_network_security_group.api_management[0].security_rule).name == "AllowAzureKeyVaultOutbound" &&
      one(azurerm_network_security_group.api_management[0].security_rule).access == "Allow" &&
      one(azurerm_network_security_group.api_management[0].security_rule).direction == "Outbound" &&
      one(azurerm_network_security_group.api_management[0].security_rule).protocol == "Tcp" &&
      one(azurerm_network_security_group.api_management[0].security_rule).priority == 100 &&
      one(azurerm_network_security_group.api_management[0].security_rule).source_address_prefix == "VirtualNetwork" &&
      one(azurerm_network_security_group.api_management[0].security_rule).destination_address_prefix == "AzureKeyVault" &&
      one(azurerm_network_security_group.api_management[0].security_rule).destination_port_range == "443"
    )
    error_message = "The gateway security group must allow only the documented outbound Key Vault rule and no inbound rule."
  }
  assert {
    condition = (
      azurerm_subnet.api_management[0].name == "snet-api-management" &&
      azurerm_subnet.api_management[0].address_prefixes == tolist(["10.43.1.0/24"]) &&
      azurerm_subnet.api_management[0].virtual_network_name == "vnet-jumpbox-aifnd-dev" &&
      length(azurerm_subnet.api_management[0].delegation) == 1 &&
      azurerm_subnet.api_management[0].delegation[0].name == "Microsoft.Web.serverFarms" &&
      azurerm_subnet.api_management[0].delegation[0].service_delegation[0].name == "Microsoft.Web/serverFarms" &&
      toset(azurerm_subnet.api_management[0].delegation[0].service_delegation[0].actions) == toset(["Microsoft.Network/virtualNetworks/subnets/action"])
    )
    error_message = "The gateway subnet must live in the management network and stay delegated to Microsoft.Web/serverFarms."
  }
  assert {
    condition     = output.api_management_name == "apim-platform-test-12345" && output.api_management_gateway_url == "https://apim-platform-test-12345.azure-api.net"
    error_message = "The root outputs must expose the gateway name and URL."
  }
}

run "apim_module_inputs" {
  command = plan
  variables {
    enable_api_management          = true
    api_management_publisher_email = "owner@example.com"
    api_management_publisher_name  = "Platform Team"
  }
  assert {
    condition = (
      module.api_management[0].inputs.name == "apim-platform-test-12345" &&
      module.api_management[0].inputs.location == "westus" &&
      module.api_management[0].inputs.resource_group_name == "rg-platform-test-12345" &&
      module.api_management[0].inputs.publisher_email == "owner@example.com" &&
      module.api_management[0].inputs.publisher_name == "Platform Team" &&
      module.api_management[0].inputs.tags.environment == "dev"
    )
    error_message = "The gateway must take the shared name, its own region, the resource group, and the publisher details."
  }
  assert {
    condition = (
      module.api_management[0].inputs.sku_name == "StandardV2_1" &&
      module.api_management[0].inputs.virtual_network_type == "External" &&
      module.api_management[0].inputs.managed_identities.system_assigned &&
      module.api_management[0].inputs.enable_telemetry &&
      module.api_management[0].inputs.diagnostic_settings.log_analytics.name == "diag-api-management"
    )
    error_message = "The gateway must use the v2 tier in the external virtual network mode, with a system identity and platform logging."
  }
}

run "apim_in_another_management_region" {
  command = plan
  variables {
    enable_api_management                  = true
    api_management_publisher_email         = "owner@example.com"
    api_management_location                = "westus3"
    jumpbox_location                       = "westus3"
    api_management_subnet_address_prefixes = ["10.43.8.0/24"]
  }
  assert {
    condition = (
      azurerm_network_security_group.api_management[0].location == "westus3" &&
      azurerm_virtual_network.jumpbox[0].location == "westus3" &&
      module.api_management[0].inputs.location == "westus3" &&
      azurerm_subnet.api_management[0].address_prefixes == tolist(["10.43.8.0/24"])
    )
    error_message = "The gateway region and subnet range must follow the management network."
  }
}

run "reject_gateway_outside_management_region" {
  command = plan
  variables {
    enable_api_management          = true
    api_management_publisher_email = "owner@example.com"
    api_management_location        = "westus3"
  }
  expect_failures = [check.api_management_management_network]
}

run "reject_unsupported_gateway_region" {
  command = plan
  variables { api_management_location = "eastus" }
  expect_failures = [var.api_management_location]
}

run "reject_gateway_without_publisher_email" {
  command = plan
  variables { enable_api_management = true }
  expect_failures = [var.api_management_publisher_email]
}

run "reject_malformed_publisher_email" {
  command = plan
  variables {
    enable_api_management          = true
    api_management_publisher_email = "not-an-email"
  }
  expect_failures = [var.api_management_publisher_email]
}

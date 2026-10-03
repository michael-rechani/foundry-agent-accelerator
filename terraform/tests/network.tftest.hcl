# Offline assertions for network.tf and the management links it feeds.
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
}

run "workload_network_defaults" {
  command = plan
  assert {
    condition = (
      azurerm_virtual_network.this.name == "vnet-platform-test-12345" &&
      azurerm_virtual_network.this.location == "northcentralus" &&
      toset(azurerm_virtual_network.this.address_space) == toset(["10.42.0.0/16"]) &&
      azurerm_virtual_network.this.tags.environment == "dev"
    )
    error_message = "The workload network must use the shared name, the default region, and the documented address space."
  }
  assert {
    condition = (
      azurerm_subnet.private_endpoints.name == "snet-private-endpoints" &&
      azurerm_subnet.private_endpoints.address_prefixes == tolist(["10.42.0.0/24"]) &&
      azurerm_subnet.private_endpoints.private_endpoint_network_policies == "Disabled"
    )
    error_message = "The private endpoint subnet must keep its name, address range, and disabled endpoint network policies."
  }
  assert {
    condition = (
      azurerm_subnet.agent_services.name == "snet-agent-services" &&
      azurerm_subnet.agent_services.address_prefixes == tolist(["10.42.1.0/24"]) &&
      length(azurerm_subnet.agent_services.delegation) == 1 &&
      azurerm_subnet.agent_services.delegation[0].name == "Microsoft.App.environments" &&
      azurerm_subnet.agent_services.delegation[0].service_delegation[0].name == "Microsoft.App/environments" &&
      toset(azurerm_subnet.agent_services.delegation[0].service_delegation[0].actions) == toset(["Microsoft.Network/virtualNetworks/subnets/join/action"])
    )
    error_message = "The Agent Service subnet must stay delegated to Microsoft.App/environments."
  }
}

run "private_dns_zones" {
  command = plan
  assert {
    condition = { for key, zone in azurerm_private_dns_zone.this : key => zone.name } == {
      agentsvc           = "privatelink.agentsvc.azure-automation.net"
      ai_services        = "privatelink.services.ai.azure.com"
      cognitive_services = "privatelink.cognitiveservices.azure.com"
      cosmosdb           = "privatelink.documents.azure.com"
      key_vault          = "privatelink.vaultcore.azure.net"
      monitor            = "privatelink.monitor.azure.com"
      ods                = "privatelink.ods.opinsights.azure.com"
      oms                = "privatelink.oms.opinsights.azure.com"
      openai             = "privatelink.openai.azure.com"
      search             = "privatelink.search.windows.net"
      storage_blob       = "privatelink.blob.core.windows.net"
    }
    error_message = "Every private endpoint needs its Azure private DNS zone, and no zone name may drift."
  }
  assert {
    condition = (
      keys(azurerm_private_dns_zone_virtual_network_link.this) == keys(azurerm_private_dns_zone.this) &&
      azurerm_private_dns_zone_virtual_network_link.this["ai_services"].name == "link-ai-services" &&
      azurerm_private_dns_zone_virtual_network_link.this["ai_services"].private_dns_zone_name == "privatelink.services.ai.azure.com" &&
      azurerm_private_dns_zone_virtual_network_link.this["storage_blob"].name == "link-storage-blob"
    )
    error_message = "Each private DNS zone must be linked to the workload network, with underscores in keys turned into hyphens."
  }
}

run "monitor_private_link_scope" {
  command = plan
  assert {
    condition = (
      azurerm_monitor_private_link_scope.this.name == "ampls-aifnd-dev" &&
      azurerm_monitor_private_link_scope.this.ingestion_access_mode == "PrivateOnly" &&
      azurerm_monitor_private_link_scope.this.query_access_mode == "PrivateOnly"
    )
    error_message = "Azure Monitor ingestion and queries must stay private-only."
  }
  assert {
    condition     = azurerm_monitor_private_link_scoped_service.log_analytics.name == "law-aifnd-dev" && azurerm_monitor_private_link_scoped_service.log_analytics.scope_name == "ampls-aifnd-dev"
    error_message = "The platform workspace must be scoped to the private link scope."
  }
  assert {
    condition = (
      azurerm_private_endpoint.azure_monitor.name == "pe-monitor-aifnd-dev" &&
      azurerm_private_endpoint.azure_monitor.private_service_connection[0].name == "azure-monitor" &&
      !azurerm_private_endpoint.azure_monitor.private_service_connection[0].is_manual_connection &&
      toset(azurerm_private_endpoint.azure_monitor.private_service_connection[0].subresource_names) == toset(["azuremonitor"]) &&
      azurerm_private_endpoint.azure_monitor.private_dns_zone_group[0].name == "azure-monitor" &&
      length(azurerm_private_endpoint.azure_monitor.private_dns_zone_group[0].private_dns_zone_ids) == 5
    )
    error_message = "The Azure Monitor private endpoint must be automatic and resolve through all five Monitor DNS zones."
  }
}

run "network_inputs_flow_through" {
  command = plan
  variables {
    location                                 = "westus3"
    virtual_network_address_space            = ["10.50.0.0/16"]
    private_endpoint_subnet_address_prefixes = ["10.50.0.0/24"]
    agent_subnet_address_prefixes            = ["10.50.1.0/24"]
    tags                                     = { owner = "platform-team" }
  }
  assert {
    condition = (
      azurerm_virtual_network.this.location == "westus3" &&
      toset(azurerm_virtual_network.this.address_space) == toset(["10.50.0.0/16"]) &&
      azurerm_subnet.private_endpoints.address_prefixes == tolist(["10.50.0.0/24"]) &&
      azurerm_subnet.agent_services.address_prefixes == tolist(["10.50.1.0/24"])
    )
    error_message = "Network region and address overrides must reach the network and both subnets."
  }
  assert {
    condition = (
      azurerm_virtual_network.this.tags == tomap({ environment = "dev", managed-by = "terraform", owner = "platform-team", workload = "azure-ai-foundry" }) &&
      azurerm_monitor_private_link_scope.this.tags == azurerm_virtual_network.this.tags
    )
    error_message = "Caller tags must merge with the required workload tags on every network resource."
  }
}

run "management_network_links" {
  command = plan
  assert {
    condition = (
      length(azurerm_virtual_network_peering.workload_to_jumpbox) == 1 &&
      azurerm_virtual_network_peering.workload_to_jumpbox[0].name == "peer-workload-to-jumpbox" &&
      azurerm_virtual_network_peering.workload_to_jumpbox[0].virtual_network_name == "vnet-platform-test-12345" &&
      length(azurerm_virtual_network_peering.jumpbox_to_workload) == 1 &&
      azurerm_virtual_network_peering.jumpbox_to_workload[0].name == "peer-jumpbox-to-workload" &&
      azurerm_virtual_network_peering.jumpbox_to_workload[0].virtual_network_name == "vnet-jumpbox-aifnd-dev"
    )
    error_message = "The workload and management networks must be peered in both directions."
  }
  assert {
    condition = (
      keys(azurerm_private_dns_zone_virtual_network_link.jumpbox) == keys(azurerm_private_dns_zone.this) &&
      azurerm_private_dns_zone_virtual_network_link.jumpbox["ai_services"].name == "link-jumpbox-ai-services"
    )
    error_message = "The management network must resolve every private DNS zone the workload network does."
  }
}

run "management_network_opt_out_drops_links" {
  command = plan
  variables { enable_management_network = false }
  assert {
    condition = (
      length(azurerm_virtual_network_peering.workload_to_jumpbox) == 0 &&
      length(azurerm_virtual_network_peering.jumpbox_to_workload) == 0 &&
      length(azurerm_private_dns_zone_virtual_network_link.jumpbox) == 0 &&
      length(azurerm_private_dns_zone_virtual_network_link.this) == 11
    )
    error_message = "Opting out of the management network must drop its peering and DNS links but keep the workload links."
  }
}

run "reject_unsupported_jumpbox_region" {
  command = plan
  variables { jumpbox_location = "eastus" }
  expect_failures = [var.jumpbox_location]
}

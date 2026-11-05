mock_provider "azapi" {
  mock_data "azapi_resource" {
    defaults = {
      id     = "/subscriptions/11111111-2222-3333-4444-555555555555/resourceGroups/rg-fixture/providers/Microsoft.Network/virtualNetworks/vnet-management"
      output = { location = "northcentralus" }
    }
  }
}
mock_provider "azurerm" {}

variables {
  subscription_id       = "11111111-2222-3333-4444-555555555555"
  resource_group_name   = "rg-fixture"
  virtual_network_name  = "vnet-management"
  nat_gateway_name      = "nat-fixture"
  approve_shared_egress = true
  admin_ssh_public_key  = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAINscr5/0uytwl6kAEaWqSaYio1YQpVWBT/G7ui/VusPg fixture"
}

run "no_backend_exception_by_default" {
  command = plan
  assert {
    condition     = length([for rule in azurerm_network_security_group.runner.security_rule : rule if rule.name == "AllowStateBackendPrivateEndpointOutbound"]) == 0
    error_message = "Backend access must be explicitly opted in."
  }
}

run "backend_https_only_preserving_other_rules" {
  command = plan
  variables {
    state_backend_private_endpoint_ips = ["10.42.0.23"]
    registry_private_endpoint_ips      = ["10.42.0.24", "10.42.0.25"]
    foundry_private_endpoint_ips       = ["10.42.0.17"]
  }
  assert {
    condition = length([for rule in azurerm_network_security_group.runner.security_rule : rule if rule.name == "AllowStateBackendPrivateEndpointOutbound"]) == 1 && alltrue([for rule in azurerm_network_security_group.runner.security_rule :
      rule.name != "AllowStateBackendPrivateEndpointOutbound" || (
        rule.access == "Allow" && rule.direction == "Outbound" && rule.protocol == "Tcp" &&
        rule.destination_port_range == "443" && rule.priority == 140 &&
        rule.destination_address_prefixes == toset(["10.42.0.23"])
      )
    ])
    error_message = "The backend exception must allow only HTTPS to the supplied private endpoint."
  }
  assert {
    condition = alltrue([for name in [
      "AllowRegistryPrivateEndpointOutbound", "AllowFoundryPrivateEndpointOutbound",
      "DenyVirtualNetworkOutbound", "DenyAllOutbound", "DenyAllInbound",
    ] : contains([for rule in azurerm_network_security_group.runner.security_rule : rule.name], name)])
    error_message = "Backend access must not remove registry/Foundry exceptions or the network denies."
  }
}

run "reject_public_endpoint" {
  command = plan
  variables {
    state_backend_private_endpoint_ips = ["8.8.8.8"]
  }
  expect_failures = [var.state_backend_private_endpoint_ips]
}

run "reject_network_range" {
  command = plan
  variables {
    state_backend_private_endpoint_ips = ["10.42.0.0/24"]
  }
  expect_failures = [var.state_backend_private_endpoint_ips]
}

run "reject_invalid_private_address" {
  command = plan
  variables {
    state_backend_private_endpoint_ips = ["10.999.0.23"]
  }
  expect_failures = [var.state_backend_private_endpoint_ips]
}

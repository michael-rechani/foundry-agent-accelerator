mock_provider "azapi" {}
mock_provider "azurerm" {}

override_data {
  target = data.azapi_resource.virtual_network
  values = {
    id       = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-example/providers/Microsoft.Network/virtualNetworks/vnet-example"
    location = "westus"
    output   = { location = "westus" }
  }
}

override_data {
  target = data.azapi_resource.nat_gateway
  values = {
    id = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-example/providers/Microsoft.Network/natGateways/nat-example"
  }
}

variables {
  subscription_id       = "00000000-0000-0000-0000-000000000001"
  resource_group_name   = "rg-example"
  virtual_network_name  = "vnet-example"
  nat_gateway_name      = "nat-example"
  admin_ssh_public_key  = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAINscr5/0uytwl6kAEaWqSaYio1YQpVWBT/G7ui/VusPg runner-test"
  approve_shared_egress = true
}

run "private_vm_with_shared_egress" {
  command = plan

  assert {
    condition     = azapi_resource.subnet.body.properties.natGateway.id == "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-example/providers/Microsoft.Network/natGateways/nat-example"
    error_message = "The runner subnet must reuse the existing NAT gateway for outbound access."
  }
  assert {
    condition     = azapi_resource.subnet.body.properties.defaultOutboundAccess == false
    error_message = "The runner subnet must not use Azure's implicit default outbound IP."
  }
  assert {
    condition     = azapi_resource.subnet.name == "snet-runner" && azapi_resource.subnet.body.properties.addressPrefix == "10.43.2.0/27"
    error_message = "The runner needs its own subnet, separate from the jumpbox and Bastion subnets."
  }
  assert {
    condition     = length(azurerm_network_interface.runner.ip_configuration) == 1 && try(azurerm_network_interface.runner.ip_configuration[0].public_ip_address_id, null) == null
    error_message = "The runner NIC must have no public IP address."
  }
  assert {
    condition     = azurerm_linux_virtual_machine.runner.disable_password_authentication == true && azurerm_linux_virtual_machine.runner.identity[0].type == "SystemAssigned"
    error_message = "The VM must use key-only sign-in and a managed identity."
  }
  assert {
    condition     = azurerm_linux_virtual_machine.runner.location == "westus" && azurerm_resource_group.runner.location == "westus"
    error_message = "The runner must follow the existing management VNet's region."
  }
  assert {
    condition     = azurerm_resource_group.runner.name == "rg-runner-aifnd-dev" && azurerm_resource_group.runner.name != var.resource_group_name
    error_message = "The runner must go in its own new resource group."
  }
  assert {
    condition     = azurerm_linux_virtual_machine.runner.tags["workload"] == "github-actions-runner" && azurerm_linux_virtual_machine.runner.tags["managed-by"] == "terraform" && azurerm_linux_virtual_machine.runner.tags["environment"] == "dev"
    error_message = "The runner must carry the repository's standard tags."
  }
}

run "defaults_match_the_live_vm" {
  command = plan

  assert {
    condition = (
      azurerm_linux_virtual_machine.runner.os_disk[0].storage_account_type == "Standard_LRS" &&
      azurerm_linux_virtual_machine.runner.patch_mode == "AutomaticByPlatform" &&
      azurerm_linux_virtual_machine.runner.bypass_platform_safety_checks_on_user_schedule_enabled == true
    )
    error_message = "Defaults must equal the live VM so adopting it into state plans no change."
  }
}

run "no_inbound_allowed" {
  command = plan

  assert {
    condition     = length([for rule in azurerm_network_security_group.runner.security_rule : rule if rule.direction == "Inbound" && rule.access == "Allow"]) == 0
    error_message = "The runner NSG must not allow any inbound traffic."
  }
  assert {
    condition     = length([for rule in azurerm_network_security_group.runner.security_rule : rule if rule.direction == "Inbound" && rule.access == "Deny" && rule.priority == 4096]) == 1
    error_message = "The runner NSG must deny all inbound traffic, including from inside the VNet."
  }
  assert {
    condition     = length([for rule in azurerm_network_security_group.runner.security_rule : rule if rule.direction == "Outbound" && rule.access == "Deny" && rule.destination_address_prefix == "VirtualNetwork"]) == 1
    error_message = "The runner must be blocked from reaching the VNet and its peers."
  }
}

run "identity_can_only_deallocate_itself" {
  command = plan

  assert {
    condition     = toset(azurerm_role_definition.self_deallocate.permissions[0].actions) == toset(["Microsoft.Compute/virtualMachines/read", "Microsoft.Compute/virtualMachines/deallocate/action"])
    error_message = "The managed identity may only read and deallocate its VM."
  }
  assert {
    condition     = length(azurerm_role_definition.self_deallocate.assignable_scopes) == 1
    error_message = "The role definition must be assignable only within the runner's resource group."
  }
}

run "no_credentials_in_cloud_init" {
  command = plan

  assert {
    condition     = !can(regex("(gh[pousr]_|github_pat_)[A-Za-z0-9_]{10,}|RUNNER_TOKEN=[A-Za-z0-9]", local.cloud_init))
    error_message = "Cloud-init must not contain a registration token, password, or secret."
  }
  assert {
    condition     = can(regex("ACTIONS_RUNNER_INPUT_TOKEN", local.cloud_init)) && !can(regex("--token", local.cloud_init))
    error_message = "The registration token must reach the runner through the environment, never a command-line argument."
  }
  assert {
    condition     = !strcontains(local.cloud_init, "\r")
    error_message = "Scripts embedded in cloud-init must use Unix line endings."
  }
}

run "reject_unapproved_shared_egress" {
  command = plan
  variables {
    approve_shared_egress = false
  }
  expect_failures = [var.approve_shared_egress]
}

run "reject_small_subnet" {
  command = plan
  variables {
    subnet_address_prefix = "10.43.2.0/29"
  }
  expect_failures = [var.subnet_address_prefix]
}

run "reject_ipv6_subnet" {
  command = plan
  variables {
    subnet_address_prefix = "fd00::/28"
  }
  expect_failures = [var.subnet_address_prefix]
}

run "reject_private_key_as_public_key" {
  command = plan
  variables {
    admin_ssh_public_key = "-----BEGIN OPENSSH PRIVATE KEY-----"
  }
  expect_failures = [var.admin_ssh_public_key]
}

run "reject_short_idle_shutdown" {
  command = plan
  variables {
    idle_shutdown_minutes = 3
  }
  expect_failures = [var.idle_shutdown_minutes]
}

run "idle_shutdown_can_be_disabled" {
  command = plan
  variables {
    idle_shutdown_minutes = 0
    auto_shutdown         = null
  }
  assert {
    condition     = length(azurerm_dev_test_global_vm_shutdown_schedule.runner) == 0
    error_message = "Setting auto_shutdown to null must remove the backstop schedule."
  }
}

run "registry_push_exception_is_narrow" {
  command = plan

  variables {
    registry_private_endpoint_ips = ["10.42.0.24", "10.42.0.25"]
  }

  assert {
    condition     = length([for rule in azurerm_network_security_group.runner.security_rule : rule if rule.name == "AllowRegistryPrivateEndpointOutbound" && rule.destination_port_range == "443" && length(rule.destination_address_prefixes) == 2 && rule.priority < 4000]) == 1
    error_message = "The registry exception must allow only TCP 443 to the two private endpoint addresses, ahead of the VirtualNetwork deny."
  }
  assert {
    condition     = length([for rule in azurerm_network_security_group.runner.security_rule : rule if rule.direction == "Outbound" && rule.access == "Deny" && rule.destination_address_prefix == "VirtualNetwork"]) == 1
    error_message = "The VirtualNetwork deny must remain."
  }
}

run "foundry_exception_is_narrow" {
  command = plan

  variables {
    foundry_private_endpoint_ips = ["10.42.0.17", "10.42.0.19"]
  }

  assert {
    condition     = length([for rule in azurerm_network_security_group.runner.security_rule : rule if rule.name == "AllowFoundryPrivateEndpointOutbound" && rule.protocol == "Tcp" && rule.destination_port_range == "443" && length(rule.destination_address_prefixes) == 2 && rule.priority < 4000]) == 1
    error_message = "The Foundry exception must allow only TCP 443 to the two private endpoint addresses, ahead of the VirtualNetwork deny."
  }
  assert {
    condition     = length([for rule in azurerm_network_security_group.runner.security_rule : rule if rule.direction == "Outbound" && rule.access == "Deny" && rule.destination_address_prefix == "VirtualNetwork"]) == 1
    error_message = "The VirtualNetwork deny must remain."
  }
}

run "no_foundry_exception_by_default" {
  command = plan
  assert {
    condition     = length([for rule in azurerm_network_security_group.runner.security_rule : rule if rule.name == "AllowFoundryPrivateEndpointOutbound"]) == 0
    error_message = "Without foundry_private_endpoint_ips the runner must not be able to reach Foundry."
  }
}

run "reject_ipv6_foundry_endpoint" {
  command = plan
  variables {
    foundry_private_endpoint_ips = ["fd00::1"]
  }
  expect_failures = [var.foundry_private_endpoint_ips]
}

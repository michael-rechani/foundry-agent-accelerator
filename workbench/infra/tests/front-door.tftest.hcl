# Offline assertions for front-door.tf and the ingress rules and origins it feeds.
# The AVM module runs for real, against mock providers, so these check the configuration it renders.
mock_provider "azurerm" {}
mock_provider "azapi" {}
mock_provider "modtm" {}
mock_provider "random" {}

override_data {
  target = data.azurerm_virtual_network.workload
  values = {
    id       = "/subscriptions/00000000-0000-0000-0000-000000000003/resourceGroups/rg-front-door/providers/Microsoft.Network/virtualNetworks/vnet-workload"
    location = "northcentralus"
  }
}

override_data {
  target = data.azurerm_virtual_network.management
  values = {
    id = "/subscriptions/00000000-0000-0000-0000-000000000003/resourceGroups/rg-front-door/providers/Microsoft.Network/virtualNetworks/vnet-management"
  }
}

override_data {
  target = data.azurerm_subnet.management
  values = {
    id               = "/subscriptions/00000000-0000-0000-0000-000000000003/resourceGroups/rg-front-door/providers/Microsoft.Network/virtualNetworks/vnet-management/subnets/snet-management"
    address_prefixes = ["10.0.9.0/24"]
  }
}

override_data {
  target = data.azurerm_subnet.private_endpoints
  values = {
    id = "/subscriptions/00000000-0000-0000-0000-000000000003/resourceGroups/rg-front-door/providers/Microsoft.Network/virtualNetworks/vnet-workload/subnets/snet-private-endpoints"
  }
}

override_resource {
  target          = azurerm_subnet.this
  override_during = plan
  values = {
    id = "/subscriptions/00000000-0000-0000-0000-000000000003/resourceGroups/rg-front-door/providers/Microsoft.Network/virtualNetworks/vnet-workload/subnets/snet-lab"
  }
}

override_resource {
  target          = azurerm_container_app_environment.this
  override_during = plan
  values = {
    id             = "/subscriptions/00000000-0000-0000-0000-000000000003/resourceGroups/rg-front-door/providers/Microsoft.App/managedEnvironments/cae-foundry-workbench"
    default_domain = "lab.northcentralus.azurecontainerapps.io"
  }
}

override_resource {
  target          = module.front_door[0].azurerm_cdn_frontdoor_endpoint.endpoints["lab"]
  override_during = plan
  values = {
    id        = "/subscriptions/00000000-0000-0000-0000-000000000003/resourceGroups/rg-front-door/providers/Microsoft.Cdn/profiles/afd-foundry-workbench/afdEndpoints/ep-foundry-workbench"
    host_name = "ep-foundry-workbench-abcd.z01.azurefd.net"
  }
}
variables {
  subscription_id      = "00000000-0000-0000-0000-000000000003"
  resource_group_name  = "rg-front-door"
  workload_vnet_name   = "vnet-workload"
  management_vnet_name = "vnet-management"
  foundry_account_name = "foundry-front-door"
  foundry_project_name = "project-front-door"
  registry_name        = "registryfrontdoor"
  cosmos_account_name  = "cosmos-front-door"
  image_digest         = "sha256:0000000000000000000000000000000000000000000000000000000000000000"
}

run "front_door_is_off_by_default" {
  command = plan
  assert {
    condition     = length(module.front_door) == 0 && output.front_door_url == null
    error_message = "Front Door must not exist, and has no address, unless enable_front_door is set."
  }
  assert {
    condition     = [for rule in azurerm_container_app.this[0].ingress[0].ip_security_restriction : rule.name] == ["jumpbox-only"]
    error_message = "The jump box must stay the only ingress rule while Front Door is off."
  }
  assert {
    condition     = !strcontains(one([for env in azurerm_container_app.this[0].template[0].container[0].env : env.value if env.name == "WORKBENCH_ORIGINS"]), "azurefd.net")
    error_message = "No Front Door origin may be trusted while Front Door is off."
  }
}

run "reject_unapproved_public_endpoint" {
  command = plan
  variables {
    enable_front_door        = true
    front_door_allowed_cidrs = ["203.0.113.10/32"]
  }
  expect_failures = [var.approve_public_front_door]
}

run "reject_empty_allow_list" {
  command = plan
  variables {
    enable_front_door         = true
    approve_public_front_door = true
  }
  expect_failures = [var.front_door_allowed_cidrs]
}

run "reject_internet_wide_ipv4" {
  command = plan
  variables {
    front_door_allowed_cidrs = ["0.0.0.0/0"]
  }
  expect_failures = [var.front_door_allowed_cidrs]
}

run "reject_internet_wide_ipv6" {
  command = plan
  variables {
    front_door_allowed_cidrs = ["::/0"]
  }
  expect_failures = [var.front_door_allowed_cidrs]
}

run "reject_a_network_range" {
  command = plan
  variables {
    front_door_allowed_cidrs = ["203.0.113.0/24"]
  }
  expect_failures = [var.front_door_allowed_cidrs]
}

run "reject_a_two_host_range" {
  command = plan
  variables {
    front_door_allowed_cidrs = ["203.0.113.10/31"]
  }
  expect_failures = [var.front_door_allowed_cidrs]
}

run "reject_a_bare_address" {
  command = plan
  variables {
    front_door_allowed_cidrs = ["203.0.113.10"]
  }
  expect_failures = [var.front_door_allowed_cidrs]
}

run "reject_a_private_address" {
  command = plan
  variables {
    front_door_allowed_cidrs = ["10.1.2.3/32"]
  }
  expect_failures = [var.front_door_allowed_cidrs]
}

run "reject_a_private_ipv6_address" {
  command = plan
  variables {
    front_door_allowed_cidrs = ["fd00::1/128"]
  }
  expect_failures = [var.front_door_allowed_cidrs]
}

run "reject_a_172_private_address" {
  command = plan
  variables {
    front_door_allowed_cidrs = ["172.20.1.1/32"]
  }
  expect_failures = [var.front_door_allowed_cidrs]
}

run "reject_a_shared_address_space_address" {
  command = plan
  variables {
    front_door_allowed_cidrs = ["100.64.1.1/32"]
  }
  expect_failures = [var.front_door_allowed_cidrs]
}

run "reject_a_link_local_address" {
  command = plan
  variables {
    front_door_allowed_cidrs = ["169.254.1.1/32"]
  }
  expect_failures = [var.front_door_allowed_cidrs]
}

run "reject_a_loopback_address" {
  command = plan
  variables {
    front_door_allowed_cidrs = ["127.0.0.1/32"]
  }
  expect_failures = [var.front_door_allowed_cidrs]
}

run "reject_a_multicast_address" {
  command = plan
  variables {
    front_door_allowed_cidrs = ["224.0.0.1/32"]
  }
  expect_failures = [var.front_door_allowed_cidrs]
}

run "reject_an_ipv6_link_local_address" {
  command = plan
  variables {
    front_door_allowed_cidrs = ["fe80::1/128"]
  }
  expect_failures = [var.front_door_allowed_cidrs]
}

run "reject_an_ipv6_loopback_address" {
  command = plan
  variables {
    front_door_allowed_cidrs = ["::1/128"]
  }
  expect_failures = [var.front_door_allowed_cidrs]
}

run "reject_an_ingress_range_outside_172_16" {
  command = plan
  variables {
    front_door_ingress_allow_cidrs = ["172.32.0.0/16"]
  }
  expect_failures = [var.front_door_ingress_allow_cidrs]
}

run "reject_an_ingress_range_outside_10" {
  command = plan
  variables {
    front_door_ingress_allow_cidrs = ["11.0.0.0/16"]
  }
  expect_failures = [var.front_door_ingress_allow_cidrs]
}

run "reject_an_ingress_range_outside_192_168" {
  command = plan
  variables {
    front_door_ingress_allow_cidrs = ["192.169.0.0/16"]
  }
  expect_failures = [var.front_door_ingress_allow_cidrs]
}

run "reject_an_ipv6_ingress_range" {
  command = plan
  variables {
    front_door_ingress_allow_cidrs = ["fd00::/64"]
  }
  expect_failures = [var.front_door_ingress_allow_cidrs]
}

run "private_ingress_ranges_are_accepted" {
  command = plan
  variables {
    enable_front_door              = true
    approve_public_front_door      = true
    front_door_allowed_cidrs       = ["198.51.100.7/32", "2600:1f18::7/128"]
    front_door_ingress_allow_cidrs = ["172.20.0.0/16", "192.168.5.0/24"]
  }
  assert {
    condition     = [for rule in azurerm_container_app.this[0].ingress[0].ip_security_restriction : rule.ip_address_range] == ["10.0.9.0/24", "172.20.0.0/16", "192.168.5.0/24"]
    error_message = "Valid private ranges must reach the ingress after the jump box."
  }
}
run "front_door_private_link_range_is_accepted" {
  command = plan
  variables {
    enable_front_door              = true
    approve_public_front_door      = true
    front_door_allowed_cidrs       = ["198.51.100.7/32"]
    front_door_ingress_allow_cidrs = ["100.64.0.0/10"]
  }
  assert {
    condition     = [for rule in azurerm_container_app.this[0].ingress[0].ip_security_restriction : rule.ip_address_range] == ["10.0.9.0/24", "100.64.0.0/10"]
    error_message = "The shared address range Front Door's Private Link uses must reach the ingress after the jump box."
  }
}

run "reject_a_range_broader_than_the_shared_address_space" {
  command = plan
  variables {
    front_door_ingress_allow_cidrs = ["100.0.0.0/9"]
  }
  expect_failures = [var.front_door_ingress_allow_cidrs]
}

run "reject_a_public_range_next_to_the_shared_address_space" {
  command = plan
  variables {
    front_door_ingress_allow_cidrs = ["100.128.0.0/10"]
  }
  expect_failures = [var.front_door_ingress_allow_cidrs]
}

run "reject_a_long_list" {
  command = plan
  variables {
    front_door_allowed_cidrs = [for index in range(11) : "203.0.113.${index + 10}/32"]
  }
  expect_failures = [var.front_door_allowed_cidrs]
}

run "reject_a_broad_ingress_range" {
  command = plan
  variables {
    front_door_ingress_allow_cidrs = ["10.0.0.0/8"]
  }
  expect_failures = [var.front_door_ingress_allow_cidrs]
}

run "reject_a_public_ingress_range" {
  command = plan
  variables {
    front_door_ingress_allow_cidrs = ["203.0.113.0/24"]
  }
  expect_failures = [var.front_door_ingress_allow_cidrs]
}

run "reject_an_internet_wide_ingress_range" {
  command = plan
  variables {
    front_door_ingress_allow_cidrs = ["0.0.0.0/0"]
  }
  expect_failures = [var.front_door_ingress_allow_cidrs]
}

run "ingress_range_is_ignored_while_front_door_is_off" {
  command = plan
  variables {
    front_door_ingress_allow_cidrs = ["10.42.2.0/24"]
  }
  assert {
    condition     = [for rule in azurerm_container_app.this[0].ingress[0].ip_security_restriction : rule.name] == ["jumpbox-only"]
    error_message = "Ingress ranges for Front Door must not apply until Front Door is enabled."
  }
}

run "front_door_blocks_everyone_but_the_listed_addresses" {
  command = plan
  variables {
    enable_front_door                = true
    approve_public_front_door        = true
    front_door_allowed_cidrs         = ["203.0.113.10/32", "2001:db8::10/128"]
    front_door_private_link_location = "centralus"
    front_door_ingress_allow_cidrs   = ["10.42.2.0/24"]
  }

  assert {
    condition     = module.front_door[0].frontdoor_firewall_policies["lab"].mode == "Prevention" && module.front_door[0].frontdoor_firewall_policies["lab"].sku_name == "Premium_AzureFrontDoor"
    error_message = "The WAF must block in Prevention mode on the Premium tier."
  }
  assert {
    condition = (
      length(module.front_door[0].frontdoor_firewall_policies["lab"].custom_rule) == 1 &&
      module.front_door[0].frontdoor_firewall_policies["lab"].custom_rule[0].action == "Block" &&
      module.front_door[0].frontdoor_firewall_policies["lab"].custom_rule[0].type == "MatchRule" &&
      length(module.front_door[0].frontdoor_firewall_policies["lab"].custom_rule[0].match_condition) == 1
    )
    error_message = "The WAF must have one blocking rule and nothing that allows."
  }
  assert {
    condition = (
      module.front_door[0].frontdoor_firewall_policies["lab"].custom_rule[0].match_condition[0].match_variable == "SocketAddr" &&
      module.front_door[0].frontdoor_firewall_policies["lab"].custom_rule[0].match_condition[0].operator == "IPMatch" &&
      module.front_door[0].frontdoor_firewall_policies["lab"].custom_rule[0].match_condition[0].negation_condition == true &&
      toset(module.front_door[0].frontdoor_firewall_policies["lab"].custom_rule[0].match_condition[0].match_values) == toset(["203.0.113.10/32", "2001:db8::10/128"])
    )
    error_message = "The rule must block when the connecting address is not on the list. SocketAddr cannot be forged with X-Forwarded-For."
  }
  assert {
    condition     = length(module.front_door[0].frontdoor_security_policies) == 1 && length(module.front_door[0].frontdoor_endpoints) == 1
    error_message = "One endpoint must carry one security policy."
  }
  assert {
    condition = (
      module.front_door[0].frontdoor_origins["lab"].private_link[0].target_type == "managedEnvironments" &&
      module.front_door[0].frontdoor_origins["lab"].private_link[0].location == "centralus" &&
      module.front_door[0].frontdoor_origins["lab"].private_link[0].private_link_target_id == azurerm_container_app_environment.this.id &&
      module.front_door[0].frontdoor_origins["lab"].certificate_name_check_enabled == true
    )
    error_message = "The origin must be the Lab environment over Private Link, in the requested region, with certificate checks on."
  }
  assert {
    condition     = module.front_door[0].frontdoor_origins["lab"].host_name == module.front_door[0].frontdoor_origins["lab"].origin_host_header
    error_message = "Front Door must send the Lab's own hostname so the Lab's allowed-host check passes."
  }
  assert {
    condition     = [for rule in azurerm_container_app.this[0].ingress[0].ip_security_restriction : "${rule.name}=${rule.ip_address_range}"] == ["jumpbox-only=10.0.9.0/24", "front-door-1=10.42.2.0/24"]
    error_message = "Ingress must admit the jump box and only the private ranges listed for Front Door."
  }
  assert {
    condition     = strcontains(one([for env in azurerm_container_app.this[0].template[0].container[0].env : env.value if env.name == "WORKBENCH_ORIGINS"]), ",${output.front_door_url}") && startswith(output.front_door_url, "https://")
    error_message = "The Lab must trust the Front Door address as a browser origin, over HTTPS."
  }
}

run "private_link_region_follows_the_environment_by_default" {
  command = plan
  variables {
    enable_front_door         = true
    approve_public_front_door = true
    front_door_allowed_cidrs  = ["203.0.113.10/32"]
  }
  assert {
    condition     = module.front_door[0].frontdoor_origins["lab"].private_link[0].location == azurerm_container_app_environment.this.location
    error_message = "Without an explicit region, Private Link must use the environment's region."
  }
}

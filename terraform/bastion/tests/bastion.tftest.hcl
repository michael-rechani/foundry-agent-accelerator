mock_provider "azapi" {}

override_data {
  target = data.azapi_resource.management_network
  values = {
    id       = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-example/providers/Microsoft.Network/virtualNetworks/vnet-example"
    location = "westus"
    output   = { location = "westus" }
  }
}

variables {
  subscription_id      = "00000000-0000-0000-0000-000000000001"
  resource_group_name  = "rg-example"
  virtual_network_name = "vnet-example"
  bastion_name         = "bastion-example"
}

run "standard_dedicated_host" {
  command = plan

  assert {
    condition     = azapi_resource.bastion.body.sku.name == "Standard" && azapi_resource.bastion.body.properties.scaleUnits == 2
    error_message = "Bastion must use Standard with two dedicated scale units."
  }
  assert {
    condition     = azapi_resource.subnet.name == "AzureBastionSubnet" && azapi_resource.subnet.body.properties.addressPrefix == "10.43.1.0/26"
    error_message = "Bastion requires its own named /26 subnet, separate from the jumpbox subnet."
  }
  assert {
    condition     = azapi_resource.public_ip.body.sku.name == "Standard" && azapi_resource.public_ip.body.properties.publicIPAllocationMethod == "Static"
    error_message = "Dedicated Bastion requires a Standard static public IP."
  }
  assert {
    condition     = azapi_resource.bastion.location == "westus" && azapi_resource.public_ip.location == "westus"
    error_message = "Bastion and its IP must follow the existing management VNet region."
  }
  assert {
    condition     = azapi_resource.bastion.body.properties.virtualNetwork == null && length(azapi_resource.bastion.body.properties.ipConfigurations) == 1
    error_message = "The Standard upgrade must replace Developer's VNet reference with a dedicated IP configuration."
  }
}

run "reject_small_subnet" {
  command = plan
  variables {
    subnet_address_prefix = "10.43.1.0/27"
  }
  expect_failures = [var.subnet_address_prefix]
}

run "reject_ipv6_subnet" {
  command = plan
  variables {
    subnet_address_prefix = "fd00::/26"
  }
  expect_failures = [var.subnet_address_prefix]
}

run "allow_larger_subnet" {
  command = plan
  variables {
    subnet_address_prefix = "10.43.1.0/24"
  }
  assert {
    condition     = azapi_resource.subnet.body.properties.addressPrefix == "10.43.1.0/24"
    error_message = "Larger IPv4 subnets must remain supported."
  }
}

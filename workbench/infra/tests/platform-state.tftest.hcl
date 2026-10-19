mock_provider "azurerm" {}
mock_provider "azapi" {}

override_data {
  target = data.terraform_remote_state.platform[0]
  values = {
    outputs = {
      resource_group_name             = "rg-platform"
      workload_virtual_network_name   = "vnet-platform"
      management_virtual_network_name = "vnet-mgmt"
      foundry_account_name            = "foundry-platform"
      foundry_project_name            = "project-platform"
      cosmos_account_name             = "cosmos-platform"
    }
  }
}

variables {
  subscription_id = "00000000-0000-0000-0000-000000000004"
  registry_name   = "registryplatform"
  bootstrap_only  = true
}

run "names_come_from_platform_state" {
  command = plan
  variables {
    platform_state = {
      subscription_id      = "00000000-0000-0000-0000-000000000004"
      resource_group_name  = "rg-state"
      storage_account_name = "ststate"
      container_name       = "tfstate"
    }
  }
  plan_options {
    target = [terraform_data.platform_names]
  }
  assert {
    condition = (
      local.resource_group_name == "rg-platform" &&
      local.workload_vnet_name == "vnet-platform" &&
      local.management_vnet_name == "vnet-mgmt" &&
      local.foundry_account_name == "foundry-platform" &&
      local.foundry_project_name == "project-platform" &&
      local.cosmos_account_name == "cosmos-platform"
    )
    error_message = "With platform_state set, the Lab must read every name from the platform outputs."
  }
}

run "explicit_name_wins_over_platform_state" {
  command = plan
  variables {
    resource_group_name = "rg-override"
    platform_state = {
      subscription_id      = "00000000-0000-0000-0000-000000000004"
      resource_group_name  = "rg-state"
      storage_account_name = "ststate"
      container_name       = "tfstate"
    }
  }
  plan_options {
    target = [terraform_data.platform_names]
  }
  assert {
    condition     = local.resource_group_name == "rg-override" && local.cosmos_account_name == "cosmos-platform"
    error_message = "A name set explicitly must win, and the rest must still come from the platform."
  }
}

run "missing_names_fail_clearly" {
  command = plan
  plan_options {
    target = [terraform_data.platform_names]
  }
  expect_failures = [terraform_data.platform_names]
}

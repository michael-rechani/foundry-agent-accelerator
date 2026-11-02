mock_provider "azurerm" {}
mock_provider "azapi" {}

override_data {
  target = data.azurerm_subnet.management
  values = {
    address_prefixes = ["10.0.0.0/24"]
  }
}

variables {
  subscription_id      = "00000000-0000-0000-0000-000000000003"
  resource_group_name  = "rg-presenter"
  workload_vnet_name   = "vnet-workload"
  management_vnet_name = "vnet-management"
  foundry_account_name = "foundry-presenter"
  foundry_project_name = "project-presenter"
  registry_name        = "registrypresenter"
  cosmos_account_name  = "cosmos-presenter"
  image_digest         = "sha256:0000000000000000000000000000000000000000000000000000000000000000"
}

run "presenter_mode_defaults_off" {
  command = plan
  plan_options {
    target = [azurerm_container_app.this]
  }
  assert {
    condition     = one([for e in azurerm_container_app.this[0].template[0].container[0].env : e.value if e.name == "WORKBENCH_PRIVATE_PRESENTER_MODE"]) == "false"
    error_message = "Presenter mode must require explicit server-side opt-in."
  }
}

run "creation_still_requires_a_key_by_default" {
  command = plan
  variables {
    agent_creation_enabled = true
    agent_creation_model   = "demo-model"
  }
  plan_options {
    target = [azurerm_container_app.this]
  }
  expect_failures = [azurerm_container_app.this]
}

run "presenter_mode_can_create_without_a_secret" {
  command = plan
  variables {
    agent_creation_enabled = true
    agent_creation_model   = "demo-model"
    private_presenter_mode = true
  }
  plan_options {
    target = [azurerm_container_app.this]
  }
  assert {
    condition = (
      one([for e in azurerm_container_app.this[0].template[0].container[0].env : e.value if e.name == "WORKBENCH_PRIVATE_PRESENTER_MODE"]) == "true" &&
      one([for e in azurerm_container_app.this[0].template[0].container[0].env : e.value if e.name == "WORKBENCH_MODE"]) == "private" &&
      length([for e in azurerm_container_app.this[0].template[0].container[0].env : e if e.name == "WORKBENCH_CREATION_KEY_SHA256"]) == 0 &&
      length(azurerm_container_app.this[0].secret) == 0 &&
      azurerm_container_app_environment.this.internal_load_balancer_enabled &&
      azurerm_container_app_environment.this.public_network_access == "Disabled"
    )
    error_message = "Keyless presenter mode must keep the private environment and need no key secret."
  }
}

run "presenter_mode_still_requires_a_model" {
  command = plan
  variables {
    agent_creation_enabled = true
    private_presenter_mode = true
  }
  plan_options {
    target = [azurerm_container_app.this]
  }
  expect_failures = [azurerm_container_app.this]
}

mock_provider "azapi" {
  override_during = plan

  mock_resource "azapi_resource" {
    defaults = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test/providers/Microsoft.OperationalInsights/workspaces/log-test"
    }
  }
}

mock_provider "azurerm" {
  override_during = plan

  mock_data "azurerm_virtual_network" {
    defaults = {
      id       = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test/providers/Microsoft.Network/virtualNetworks/vnet-test"
      location = "eastus"
    }
  }

  mock_data "azurerm_subnet" {
    defaults = {
      id               = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test/providers/Microsoft.Network/virtualNetworks/vnet-test/subnets/subnet-test"
      address_prefixes = ["10.42.0.0/24"]
    }
  }

  mock_resource "azurerm_container_app_environment" {
    defaults = {
      id                = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test/providers/Microsoft.App/managedEnvironments/environment-test"
      default_domain    = "test.internal"
      static_ip_address = "10.42.0.4"
    }
  }

  mock_resource "azurerm_container_registry" {
    defaults = {
      id           = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test/providers/Microsoft.ContainerRegistry/registries/mockregistry123"
      login_server = "mockregistry123.azurecr.io"
    }
  }

  mock_resource "azurerm_user_assigned_identity" {
    defaults = {
      id           = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test/providers/Microsoft.ManagedIdentity/userAssignedIdentities/identity-test"
      client_id    = "00000000-0000-0000-0000-000000000001"
      principal_id = "00000000-0000-0000-0000-000000000002"
    }
  }

  mock_resource "azurerm_subnet" {
    defaults = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test/providers/Microsoft.Network/virtualNetworks/vnet-test/subnets/app-test"
    }
  }

  mock_resource "azurerm_private_dns_zone" {
    defaults = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test/providers/Microsoft.Network/privateDnsZones/test.internal"
    }
  }
}

mock_provider "modtm" {
  override_during = plan
}

variables {
  subscription_id                 = "00000000-0000-0000-0000-000000000000"
  resource_group_name             = "rg-test"
  workload_vnet_name              = "workload-test"
  management_vnet_name            = "management-test"
  foundry_account_name            = "foundry-test"
  foundry_project_name            = "project-test"
  cosmos_account_name             = "cosmos-test"
  registry_name                   = "mockregistry123"
  monitor_private_link_scope_name = "ampls-test"
  image_digest                    = "sha256:0000000000000000000000000000000000000000000000000000000000000000"
}

run "default_without_platform_state" {
  command = plan

  assert {
    condition = (
      local.agent_creation_model == "model-router" &&
      one([for env in azurerm_container_app.this[0].template[0].container[0].env :
        env.value if env.name == "WORKBENCH_AGENT_CREATION_MODEL"
      ]) == "model-router"
    )
    error_message = "Without platform state or an override, the Lab must configure model-router."
  }
}

run "use_platform_router" {
  command = plan

  variables {
    platform_state = {}
  }

  override_data {
    target = data.terraform_remote_state.platform[0]
    values = {
      outputs = {
        model_router_deployment_name = "platform-router"
        model_deployment_name        = "fixed-model"
      }
    }
  }

  assert {
    condition = (
      local.agent_creation_model == "platform-router" &&
      one([for env in azurerm_container_app.this[0].template[0].container[0].env :
        env.value if env.name == "WORKBENCH_AGENT_CREATION_MODEL"
      ]) == "platform-router"
    )
    error_message = "The platform Router output must become the Lab's creation model."
  }
}

run "fallback_when_router_is_disabled" {
  command = plan

  variables {
    platform_state = {}
  }

  override_data {
    target = data.terraform_remote_state.platform[0]
    values = {
      outputs = {
        model_router_deployment_name = null
        model_deployment_name        = "fixed-model"
      }
    }
  }

  assert {
    condition     = local.agent_creation_model == "fixed-model"
    error_message = "An explicitly disabled Router must fall back to the platform's fixed deployment."
  }
}

run "fallback_for_older_platform_state" {
  command = plan

  variables {
    platform_state = {}
  }

  override_data {
    target = data.terraform_remote_state.platform[0]
    values = {
      outputs = {
        model_deployment_name = "fixed-model"
      }
    }
  }

  assert {
    condition     = local.agent_creation_model == "fixed-model"
    error_message = "Platform state predating the Router output must keep using its fixed deployment."
  }
}

run "reject_platform_state_without_model_outputs" {
  command = plan

  variables {
    platform_state = {}
  }

  override_data {
    target = data.terraform_remote_state.platform[0]
    values = {
      outputs = {}
    }
  }

  expect_failures = [azurerm_container_app.this]
}

run "reject_platform_state_with_empty_model_outputs" {
  command = plan

  variables {
    platform_state = {}
  }

  override_data {
    target = data.terraform_remote_state.platform[0]
    values = {
      outputs = {
        model_router_deployment_name = null
        model_deployment_name        = ""
      }
    }
  }

  expect_failures = [azurerm_container_app.this]
}

run "reject_invalid_platform_router_output" {
  command = plan

  variables {
    platform_state = {}
  }

  override_data {
    target = data.terraform_remote_state.platform[0]
    values = {
      outputs = {
        model_router_deployment_name = "invalid/router"
        model_deployment_name        = "fixed-model"
      }
    }
  }

  expect_failures = [azurerm_container_app.this]
}

run "reject_empty_router_output_even_with_fixed_fallback" {
  command = plan

  variables {
    platform_state = {}
  }

  override_data {
    target = data.terraform_remote_state.platform[0]
    values = {
      outputs = {
        model_router_deployment_name = ""
        model_deployment_name        = "fixed-model"
      }
    }
  }

  expect_failures = [azurerm_container_app.this]
}

run "allow_explicit_model_with_empty_router_output" {
  command = plan

  variables {
    platform_state       = {}
    agent_creation_model = "operator-selected-model"
  }

  override_data {
    target = data.terraform_remote_state.platform[0]
    values = {
      outputs = {
        model_router_deployment_name = ""
        model_deployment_name        = "fixed-model"
      }
    }
  }

  assert {
    condition     = local.agent_creation_model == "operator-selected-model"
    error_message = "An explicit creation model must override an empty Router output."
  }
}

run "allow_explicit_model_without_platform_model_outputs" {
  command = plan

  variables {
    platform_state       = {}
    agent_creation_model = "operator-selected-model"
  }

  override_data {
    target = data.terraform_remote_state.platform[0]
    values = {
      outputs = {}
    }
  }

  assert {
    condition     = local.agent_creation_model == "operator-selected-model"
    error_message = "An explicit creation model must remain usable when the platform has no model outputs."
  }
}

run "allow_explicit_empty_without_platform_model_outputs" {
  command = plan

  variables {
    platform_state       = {}
    agent_creation_model = ""
  }

  override_data {
    target = data.terraform_remote_state.platform[0]
    values = {
      outputs = {}
    }
  }

  assert {
    condition     = local.agent_creation_model == ""
    error_message = "An explicitly unconfigured model must not require platform model outputs."
  }
}

run "explicit_fixed_model_wins" {
  command = plan

  variables {
    platform_state       = {}
    agent_creation_model = "operator-selected-model"
  }

  override_data {
    target = data.terraform_remote_state.platform[0]
    values = {
      outputs = {
        model_router_deployment_name = "platform-router"
        model_deployment_name        = "fixed-model"
      }
    }
  }

  assert {
    condition     = local.agent_creation_model == "operator-selected-model"
    error_message = "An explicit creation model must override the Router output."
  }
}

run "explicit_empty_model_stays_unconfigured" {
  command = plan

  variables {
    agent_creation_model = ""
  }

  assert {
    condition = (
      local.agent_creation_model == "" &&
      one([for env in azurerm_container_app.this[0].template[0].container[0].env :
        env.value if env.name == "WORKBENCH_AGENT_CREATION_MODEL"
      ]) == ""
    )
    error_message = "An explicit empty model must remain empty when agent creation is disabled."
  }
}

run "reject_creation_without_a_model" {
  command = plan

  variables {
    agent_creation_enabled = true
    private_presenter_mode = true
    agent_creation_model   = ""
  }

  expect_failures = [azurerm_container_app.this]
}

run "accept_creation_with_default_router" {
  command = plan

  variables {
    agent_creation_enabled = true
    private_presenter_mode = true
  }

  assert {
    condition     = local.agent_creation_model == "model-router"
    error_message = "Agent creation must accept the default Router when private presenter mode is enabled."
  }
}

run "model_overrides_are_passed_to_lab" {
  command = plan

  variables {
    agent_creation_models = {
      reasoning = "reasoning-model"
    }
    prebuilt_agent_models = {
      customer-review = "routed-agent-model"
    }
  }

  assert {
    condition = (
      jsondecode(one([for env in azurerm_container_app.this[0].template[0].container[0].env :
        env.value if env.name == "WORKBENCH_AGENT_CREATION_MODELS"
      ])) == { reasoning = "reasoning-model" } &&
      jsondecode(one([for env in azurerm_container_app.this[0].template[0].container[0].env :
        env.value if env.name == "WORKBENCH_PREBUILT_AGENT_MODELS"
      ])) == { customer-review = "routed-agent-model" }
    )
    error_message = "Creation-profile and verified prebuilt-agent overrides must reach the Lab as JSON."
  }
}

run "reject_unknown_prebuilt_agent" {
  command = plan

  variables {
    prebuilt_agent_models = {
      unknown-agent = "model-router"
    }
  }

  expect_failures = [var.prebuilt_agent_models]
}

run "reject_invalid_prebuilt_model" {
  command = plan

  variables {
    prebuilt_agent_models = {
      customer-review = "invalid model"
    }
  }

  expect_failures = [var.prebuilt_agent_models]
}

run "reject_invalid_creation_model" {
  command = plan

  variables {
    agent_creation_model = "invalid model"
  }

  expect_failures = [var.agent_creation_model]
}

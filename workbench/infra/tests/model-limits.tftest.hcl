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
  resource_group_name  = "rg-limits"
  workload_vnet_name   = "vnet-workload"
  management_vnet_name = "vnet-management"
  foundry_account_name = "foundry-limits"
  foundry_project_name = "project-limits"
  registry_name        = "registrylimits"
  cosmos_account_name  = "cosmos-limits"
  image_digest         = "sha256:0000000000000000000000000000000000000000000000000000000000000000"
}

run "limits_default_to_the_dev_models_and_reach_the_lab" {
  command = plan
  plan_options {
    target = [azurerm_container_app.this]
  }
  assert {
    condition = (
      jsondecode(one([for e in azurerm_container_app.this[0].template[0].container[0].env : e.value if e.name == "WORKBENCH_MODEL_LIMITS"])) == {
        "gpt-5.4"      = { requests_per_minute = 100, tokens_per_minute = 10000 }
        "gpt-4.1"      = { requests_per_minute = 50, tokens_per_minute = 50000 }
        "gpt-5.4-mini" = { requests_per_minute = 10, tokens_per_minute = 10000 }
      }
    )
    error_message = "The Lab must get the dev models' limits unless they are replaced."
  }
}

run "limits_come_from_the_variable" {
  command = plan
  variables {
    model_limits = {
      "my-model" = { requests_per_minute = 30, tokens_per_minute = 20000 }
    }
  }
  plan_options {
    target = [azurerm_container_app.this]
  }
  assert {
    condition = (
      jsondecode(one([for e in azurerm_container_app.this[0].template[0].container[0].env : e.value if e.name == "WORKBENCH_MODEL_LIMITS"])) == {
        "my-model" = { requests_per_minute = 30, tokens_per_minute = 20000 }
      }
    )
    error_message = "The Lab must get exactly the configured model limits."
  }
}

run "empty_limits_turn_the_per_model_check_off" {
  command = plan
  variables {
    model_limits = {}
  }
  plan_options {
    target = [azurerm_container_app.this]
  }
  assert {
    condition     = length([for e in azurerm_container_app.this[0].template[0].container[0].env : e if e.name == "WORKBENCH_MODEL_LIMITS"]) == 0
    error_message = "An empty model_limits map must not set WORKBENCH_MODEL_LIMITS."
  }
}

run "a_limit_must_be_a_whole_number_of_at_least_one" {
  command = plan
  variables {
    model_limits = {
      "my-model" = { requests_per_minute = 0, tokens_per_minute = 20000 }
    }
  }
  plan_options {
    target = [azurerm_container_app.this]
  }
  expect_failures = [var.model_limits]
}

run "a_limit_cannot_be_fractional" {
  command = plan
  variables {
    model_limits = {
      "my-model" = { requests_per_minute = 10, tokens_per_minute = 1500.5 }
    }
  }
  plan_options {
    target = [azurerm_container_app.this]
  }
  expect_failures = [var.model_limits]
}

run "a_limit_must_be_keyed_by_a_deployment_name" {
  command = plan
  variables {
    model_limits = {
      "not a deployment" = { requests_per_minute = 10, tokens_per_minute = 20000 }
    }
  }
  plan_options {
    target = [azurerm_container_app.this]
  }
  expect_failures = [var.model_limits]
}

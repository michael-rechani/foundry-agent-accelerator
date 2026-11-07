mock_provider "azapi" {
  mock_resource "azapi_resource" {
    defaults = {
      id = "/subscriptions/11111111-2222-3333-4444-555555555555/resourceGroups/rg-router-test/providers/Microsoft.CognitiveServices/accounts/foundry-test/deployments/model-router"
    }
  }

  mock_data "azapi_resource" {
    defaults = {
      name = "model-router"
      output = {
        properties = {
          routing = {
            mode = "balanced"
            models = [
              { format = "OpenAI", name = "gpt-4.1", version = "2025-04-14" },
              { format = "OpenAI", name = "gpt-5-mini", version = "2025-08-07" },
            ]
          }
        }
      }
    }
  }
}

variables {
  foundry_account_id                = "/subscriptions/11111111-2222-3333-4444-555555555555/resourceGroups/rg-router-test/providers/Microsoft.CognitiveServices/accounts/foundry-test"
  primary_deployment_name           = "gpt-4.1"
  additional_model_deployment_names = []
}

run "null_router_keeps_other_outputs" {
  command = plan

  variables {
    foundry_account_id                = null
    additional_model_deployment_names = ["extra-model"]
  }

  assert {
    condition = (
      length(azapi_resource.model_router) == 0 &&
      length(data.azapi_resource.model_router_routing) == 0 &&
      output.model_router_deployment_name == null &&
      output.model_deployment_names == ["gpt-4.1", "extra-model"]
    )
    error_message = "An explicitly null Router must leave the fixed-model outputs unchanged."
  }
}

run "enabled_request" {
  command = plan

  variables {
    model_router_deployment = {
      models = [
        { format = "OpenAI", name = "gpt-4.1", version = "2025-04-14" },
        { format = "OpenAI", name = "gpt-5-mini", version = "2025-08-07" },
      ]
    }
  }

  assert {
    condition = (
      length(azapi_resource.model_router) == 1 &&
      azapi_resource.model_router[0].name == "model-router" &&
      azapi_resource.model_router[0].body.sku.name == "GlobalStandard" &&
      azapi_resource.model_router[0].body.sku.capacity == 10 &&
      azapi_resource.model_router[0].body.properties.model.name == "model-router" &&
      azapi_resource.model_router[0].body.properties.model.format == "OpenAI" &&
      azapi_resource.model_router[0].body.properties.model.version == "2025-11-18" &&
      azapi_resource.model_router[0].body.properties.raiPolicyName == "Microsoft.DefaultV2" &&
      azapi_resource.model_router[0].body.properties.routing.mode == "balanced" &&
      length(azapi_resource.model_router[0].body.properties.routing.models) == 2 &&
      azapi_resource.model_router[0].ignore_missing_property == false
    )
    error_message = "The configured deployment must send the requested Router settings in the documented PUT body."
  }
}

run "standard_default_subset" {
  command   = apply
  state_key = "standard-default-subset"

  variables {
    model_router_deployment = {
      models = [
        { format = "OpenAI", name = "gpt-4.1", version = "2025-04-14" },
        { format = "OpenAI", name = "gpt-4.1-mini", version = "2025-04-14" },
      ]
    }
  }

  override_data {
    target = data.azapi_resource.model_router_routing[0]
    values = {
      name = "model-router"
      output = {
        properties = {
          routing = {
            mode = "balanced"
            models = [
              { format = "OpenAI", name = "gpt-4.1", version = "2025-04-14" },
              { format = "OpenAI", name = "gpt-4.1-mini", version = "2025-04-14" },
            ]
          }
        }
      }
    }
  }

  assert {
    condition = (
      [for model in azapi_resource.model_router[0].body.properties.routing.models : model.name] == ["gpt-4.1", "gpt-4.1-mini"] &&
      output.model_router_deployment_name == "model-router"
    )
    error_message = "The standard Router subset must be sent and verified before exposing its output."
  }
}

run "quality_and_data_zone" {
  command = plan

  variables {
    model_router_deployment = {
      deployment_name = "quality-router"
      sku_name        = "DataZoneStandard"
      capacity        = 20
      routing_mode    = "quality"
      models          = [{ format = "OpenAI", name = "gpt-4.1", version = "2025-04-14" }]
    }
  }

  assert {
    condition = (
      azapi_resource.model_router[0].name == "quality-router" &&
      azapi_resource.model_router[0].body.sku.name == "DataZoneStandard" &&
      azapi_resource.model_router[0].body.sku.capacity == 20 &&
      azapi_resource.model_router[0].body.properties.routing.mode == "quality"
    )
    error_message = "Custom name, DataZoneStandard, capacity, and quality mode must be passed through."
  }
}

run "cost_mode" {
  command = plan

  variables {
    model_router_deployment = {
      routing_mode = "cost"
      models       = [{ format = "OpenAI", name = "gpt-4.1", version = "2025-04-14" }]
    }
  }

  assert {
    condition     = azapi_resource.model_router[0].body.properties.routing.mode == "cost"
    error_message = "Cost routing mode must be passed through."
  }
}

run "reject_invalid_name" {
  command = plan
  variables {
    model_router_deployment = {
      deployment_name = "bad name"
      models          = [{ format = "OpenAI", name = "gpt-4.1", version = "2025-04-14" }]
    }
  }
  expect_failures = [var.model_router_deployment]
}

run "reject_primary_name_collision_ignoring_case" {
  command = plan
  variables {
    model_router_deployment = {
      deployment_name = "GPT-4.1"
      models          = [{ format = "OpenAI", name = "gpt-4.1", version = "2025-04-14" }]
    }
  }
  expect_failures = [var.model_router_deployment]
}

run "reject_additional_name_collision_ignoring_case" {
  command = plan
  variables {
    additional_model_deployment_names = ["Extra-Model"]
    model_router_deployment = {
      deployment_name = "extra-model"
      models          = [{ format = "OpenAI", name = "gpt-4.1", version = "2025-04-14" }]
    }
  }
  expect_failures = [var.model_router_deployment]
}

run "reject_invalid_sku" {
  command = plan
  variables {
    model_router_deployment = {
      sku_name = "Standard"
      models   = [{ format = "OpenAI", name = "gpt-4.1", version = "2025-04-14" }]
    }
  }
  expect_failures = [var.model_router_deployment]
}

run "reject_invalid_mode" {
  command = plan
  variables {
    model_router_deployment = {
      routing_mode = "Balanced"
      models       = [{ format = "OpenAI", name = "gpt-4.1", version = "2025-04-14" }]
    }
  }
  expect_failures = [var.model_router_deployment]
}

run "reject_zero_capacity" {
  command = plan
  variables {
    model_router_deployment = {
      capacity = 0
      models   = [{ format = "OpenAI", name = "gpt-4.1", version = "2025-04-14" }]
    }
  }
  expect_failures = [var.model_router_deployment]
}

run "reject_fractional_capacity" {
  command = plan
  variables {
    model_router_deployment = {
      capacity = 1.5
      models   = [{ format = "OpenAI", name = "gpt-4.1", version = "2025-04-14" }]
    }
  }
  expect_failures = [var.model_router_deployment]
}

run "reject_empty_model_subset" {
  command = plan
  variables {
    model_router_deployment = { models = [] }
  }
  expect_failures = [var.model_router_deployment]
}

run "reject_null_model_subset" {
  command = plan
  variables {
    model_router_deployment = { models = null }
  }
  expect_failures = [var.model_router_deployment]
}

run "reject_blank_model_fields" {
  command = plan
  variables {
    model_router_deployment = {
      models = [{ format = "OpenAI", name = " ", version = "2025-04-14" }]
    }
  }
  expect_failures = [var.model_router_deployment]
}

run "reject_null_model_fields" {
  command = plan
  variables {
    model_router_deployment = {
      models = [{ format = null, name = "gpt-4.1", version = "2025-04-14" }]
    }
  }
  expect_failures = [var.model_router_deployment]
}

run "reject_duplicate_models_ignoring_case" {
  command = plan
  variables {
    model_router_deployment = {
      models = [
        { format = "OpenAI", name = "gpt-4.1", version = "2025-04-14" },
        { format = "openai", name = "GPT-4.1", version = "2025-04-14" },
      ]
    }
  }
  expect_failures = [var.model_router_deployment]
}

run "verified_outputs" {
  command = apply

  variables {
    additional_model_deployment_names = ["extra-model"]
    model_router_deployment = {
      models = [
        { format = "OpenAI", name = "gpt-4.1", version = "2025-04-14" },
        { format = "OpenAI", name = "gpt-5-mini", version = "2025-08-07" },
      ]
    }
  }

  assert {
    condition = (
      output.model_router_deployment_name == "model-router" &&
      output.model_deployment_names == ["gpt-4.1", "extra-model", "model-router"]
    )
    error_message = "Verified Router output must be appended without changing the existing primary and extra outputs."
  }
}

run "unchanged_routing" {
  command = plan

  variables {
    additional_model_deployment_names = ["extra-model"]
    model_router_deployment = {
      models = [
        { format = "OpenAI", name = "gpt-4.1", version = "2025-04-14" },
        { format = "OpenAI", name = "gpt-5-mini", version = "2025-08-07" },
      ]
    }
  }

  assert {
    condition     = output.model_router_deployment_name == "model-router"
    error_message = "Unchanged routing must still be verified when planning."
  }
}

run "detect_readback_drift" {
  command = plan

  variables {
    additional_model_deployment_names = ["extra-model"]
    model_router_deployment = {
      models = [
        { format = "OpenAI", name = "gpt-4.1", version = "2025-04-14" },
        { format = "OpenAI", name = "gpt-5-mini", version = "2025-08-07" },
      ]
    }
  }

  override_data {
    target = data.azapi_resource.model_router_routing[0]
    values = {
      output = {
        properties = {
          routing = {
            mode   = "balanced"
            models = [{ format = "OpenAI", name = "gpt-4.1", version = "2025-04-14" }]
          }
        }
      }
    }
  }

  expect_failures = [data.azapi_resource.model_router_routing]
}

run "plan_routing_mode_update" {
  command = plan

  variables {
    additional_model_deployment_names = ["extra-model"]
    model_router_deployment = {
      routing_mode = "cost"
      models = [
        { format = "OpenAI", name = "gpt-4.1", version = "2025-04-14" },
        { format = "OpenAI", name = "gpt-5-mini", version = "2025-08-07" },
      ]
    }
  }

  assert {
    condition = (
      azapi_resource.model_router[0].body.properties.routing.mode == "cost"
    )
    error_message = "A routing update must plan the deployment's requested PUT body."
  }
}

run "update_routing_mode" {
  command   = apply
  state_key = "standard-default-subset"

  variables {
    additional_model_deployment_names = ["extra-model"]
    model_router_deployment = {
      routing_mode = "cost"
      models = [
        { format = "OpenAI", name = "gpt-4.1", version = "2025-04-14" },
        { format = "OpenAI", name = "gpt-5-mini", version = "2025-08-07" },
      ]
    }
  }

  override_data {
    target = data.azapi_resource.model_router_routing[0]
    values = {
      name = "model-router"
      output = {
        properties = {
          routing = {
            mode = "cost"
            models = [
              { format = "OpenAI", name = "gpt-4.1", version = "2025-04-14" },
              { format = "OpenAI", name = "gpt-5-mini", version = "2025-08-07" },
            ]
          }
        }
      }
    }
  }

  assert {
    condition = (
      azapi_resource.model_router[0].body.properties.routing.mode == "cost" &&
      output.model_router_deployment_name == "model-router"
    )
    error_message = "A routing change must send the requested PUT body and verify the resulting mode."
  }
}

run "reject_unverified_subset" {
  command   = apply
  state_key = "unverified-subset"

  variables {
    model_router_deployment = {
      models = [
        { format = "OpenAI", name = "gpt-4.1", version = "2025-04-14" },
        { format = "OpenAI", name = "gpt-5-mini", version = "2025-08-07" },
      ]
    }
  }

  override_data {
    target = data.azapi_resource.model_router_routing[0]
    values = {
      output = {
        properties = {
          routing = {
            mode   = "balanced"
            models = [{ format = "OpenAI", name = "gpt-4.1", version = "2025-04-14" }]
          }
        }
      }
    }
  }

  expect_failures = [data.azapi_resource.model_router_routing]
}

run "reject_unexpected_model" {
  command   = apply
  state_key = "unexpected-model"

  variables {
    model_router_deployment = {
      models = [{ format = "OpenAI", name = "gpt-4.1", version = "2025-04-14" }]
    }
  }

  override_data {
    target = data.azapi_resource.model_router_routing[0]
    values = {
      output = {
        properties = {
          routing = {
            mode = "balanced"
            models = [
              { format = "OpenAI", name = "gpt-4.1", version = "2025-04-14" },
              { format = "OpenAI", name = "gpt-5-mini", version = "2025-08-07" },
            ]
          }
        }
      }
    }
  }

  expect_failures = [data.azapi_resource.model_router_routing]
}

run "reject_duplicate_readback_model" {
  command   = apply
  state_key = "duplicate-readback-model"

  variables {
    model_router_deployment = {
      models = [
        { format = "OpenAI", name = "gpt-4.1", version = "2025-04-14" },
        { format = "OpenAI", name = "gpt-5-mini", version = "2025-08-07" },
      ]
    }
  }

  override_data {
    target = data.azapi_resource.model_router_routing[0]
    values = {
      output = {
        properties = {
          routing = {
            mode = "balanced"
            models = [
              { format = "OpenAI", name = "gpt-4.1", version = "2025-04-14" },
              { format = "OpenAI", name = "gpt-5-mini", version = "2025-08-07" },
              { format = "OpenAI", name = "gpt-4.1", version = "2025-04-14" },
            ]
          }
        }
      }
    }
  }

  expect_failures = [data.azapi_resource.model_router_routing]
}

run "reject_unverified_mode" {
  command   = apply
  state_key = "unverified-mode"

  variables {
    model_router_deployment = {
      models = [
        { format = "OpenAI", name = "gpt-4.1", version = "2025-04-14" },
        { format = "OpenAI", name = "gpt-5-mini", version = "2025-08-07" },
      ]
    }
  }

  override_data {
    target = data.azapi_resource.model_router_routing[0]
    values = {
      output = {
        properties = {
          routing = {
            mode = "cost"
            models = [
              { format = "OpenAI", name = "gpt-4.1", version = "2025-04-14" },
              { format = "OpenAI", name = "gpt-5-mini", version = "2025-08-07" },
            ]
          }
        }
      }
    }
  }

  expect_failures = [data.azapi_resource.model_router_routing]
}

run "reject_missing_routing" {
  command   = apply
  state_key = "missing-routing"

  variables {
    model_router_deployment = {
      models = [{ format = "OpenAI", name = "gpt-4.1", version = "2025-04-14" }]
    }
  }

  override_data {
    target = data.azapi_resource.model_router_routing[0]
    values = { output = { properties = {} } }
  }

  expect_failures = [data.azapi_resource.model_router_routing]
}

run "accept_reordered_models" {
  command   = apply
  state_key = "reordered-models"

  variables {
    model_router_deployment = {
      models = [
        { format = "OpenAI", name = "gpt-4.1", version = "2025-04-14" },
        { format = "OpenAI", name = "gpt-5-mini", version = "2025-08-07" },
      ]
    }
  }

  override_data {
    target = data.azapi_resource.model_router_routing[0]
    values = {
      name = "model-router"
      output = {
        properties = {
          routing = {
            mode = "balanced"
            models = [
              { format = "OpenAI", name = "gpt-5-mini", version = "2025-08-07" },
              { format = "OpenAI", name = "gpt-4.1", version = "2025-04-14" },
            ]
          }
        }
      }
    }
  }

  assert {
    condition     = output.model_router_deployment_name == "model-router"
    error_message = "Readback verification must not depend on Azure's ordering of the model subset."
  }
}

locals {
  model_router_body = var.model_router_deployment == null ? null : {
    sku = {
      name     = var.model_router_deployment.sku_name
      capacity = var.model_router_deployment.capacity
    }
    properties = {
      model = {
        format  = "OpenAI"
        name    = "model-router"
        version = "2025-11-18"
      }
      raiPolicyName        = "Microsoft.DefaultV2"
      versionUpgradeOption = "OnceNewDefaultVersionAvailable"
      routing = {
        mode   = var.model_router_deployment.routing_mode
        models = var.model_router_deployment.models
      }
    }
  }
}

resource "azapi_resource" "model_router" {
  count = var.model_router_deployment == null ? 0 : 1

  type      = "Microsoft.CognitiveServices/accounts/deployments@2025-10-01-preview"
  name      = var.model_router_deployment.deployment_name
  parent_id = var.foundry_account_id
  body      = local.model_router_body

  schema_validation_enabled = false
  ignore_missing_property   = false
  list_unique_id_property   = { "properties.routing.models" = "format, name, version" }
}

# Some API/provider combinations have ignored routing on PUT. Reapply it by
# PATCH, including after any deployment update, and verify it with a fresh GET.
resource "azapi_resource_action" "model_router_routing" {
  count = var.model_router_deployment == null ? 0 : 1

  type        = "Microsoft.CognitiveServices/accounts/deployments@2025-12-01"
  resource_id = azapi_resource.model_router[count.index].id
  method      = "PATCH"
  body = {
    sku = local.model_router_body.sku
    properties = {
      model   = local.model_router_body.properties.model
      routing = local.model_router_body.properties.routing
    }
  }

  lifecycle {
    replace_triggered_by = [azapi_resource.model_router[count.index]]
  }
}

data "azapi_resource" "model_router_routing" {
  count = var.model_router_deployment == null ? 0 : 1

  type                   = "Microsoft.CognitiveServices/accounts/deployments@2025-12-01"
  resource_id            = azapi_resource.model_router[count.index].id
  response_export_values = ["properties.routing"]

  lifecycle {
    postcondition {
      condition = try(
        self.output.properties.routing.mode == var.model_router_deployment.routing_mode &&
        length(self.output.properties.routing.models) == length(var.model_router_deployment.models) &&
        toset([
          for model in self.output.properties.routing.models :
          jsonencode([model.format, model.name, model.version])
          ]) == toset([
          for model in var.model_router_deployment.models :
          jsonencode([model.format, model.name, model.version])
        ]),
        false
      )
      error_message = "Azure did not return the requested Model Router mode and model subset. The deployment may still exist with a different or unrestricted model set; do not use it until corrected and verified."
    }
  }

  depends_on = [azapi_resource_action.model_router_routing]
}

resource "azurerm_api_management_api" "review" {
  count = var.review_api == null ? 0 : 1

  name                  = "reviews"
  resource_group_name   = azurerm_resource_group.this.name
  api_management_name   = module.api_management[0].name
  revision              = "1"
  display_name          = "Agent reviews"
  path                  = "reviews"
  protocols             = ["https"]
  subscription_required = false
}

resource "azurerm_api_management_api_schema" "review" {
  count = var.review_api == null ? 0 : 1

  api_name            = azurerm_api_management_api.review[0].name
  api_management_name = module.api_management[0].name
  resource_group_name = azurerm_resource_group.this.name
  schema_id           = "review-request"
  content_type        = "application/vnd.ms-azure-apim.swagger.definitions+json"
  value = jsonencode({
    definitions = {
      ReviewRequest = {
        type                 = "object"
        required             = ["input"]
        additionalProperties = false
        properties = {
          input = { type = "string", minLength = 1, maxLength = 60000, pattern = "\\S" }
        }
      }
    }
  })
}

resource "azurerm_api_management_api_policy" "review" {
  count = var.review_api == null ? 0 : 1

  api_name            = azurerm_api_management_api.review[0].name
  api_management_name = module.api_management[0].name
  resource_group_name = azurerm_resource_group.this.name
  xml_content = templatefile("${path.module}/policies/review.xml.tftpl", {
    tenant_id              = data.azurerm_client_config.current.tenant_id
    audience               = var.review_api.audience
    allowed_client_app_ids = sort(tolist(var.review_api.allowed_client_app_ids))
    caller_values          = join("", [for id in sort(tolist(var.review_api.allowed_caller_object_ids)) : "<value>${id}</value>"])
    backend_url            = "https://${module.ai_foundry.ai_foundry_name}.services.ai.azure.com/api/projects/${module.ai_foundry.ai_foundry_project_name["primary"]}/agents/${var.review_api.agent_name}/endpoint/protocols/openai"
  })

  depends_on = [azurerm_role_assignment.api_management_foundry_user]
}

resource "azurerm_api_management_api_operation" "review" {
  count = var.review_api == null ? 0 : 1

  operation_id        = "create-response"
  api_name            = azurerm_api_management_api.review[0].name
  api_management_name = module.api_management[0].name
  resource_group_name = azurerm_resource_group.this.name
  display_name        = "Review supplied evidence"
  method              = "POST"
  url_template        = "/responses"

  request {
    representation {
      content_type = "application/json"
      schema_id    = azurerm_api_management_api_schema.review[0].schema_id
      type_name    = "ReviewRequest"
    }
  }

  response {
    status_code = 200
    description = "Foundry Responses result. Inspect status and tool receipts before treating it as a completed review."
  }

  depends_on = [azurerm_api_management_api_policy.review]
}
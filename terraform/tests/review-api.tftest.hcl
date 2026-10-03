# Offline assertions for review-api.tf and the review_api variable that gates it.
# test-platform-validation.ps1 runs these against a copy of the whole root module.
# The policy template itself is checked by test-review-api-validation.ps1.
mock_provider "azurerm" {
  mock_data "azurerm_client_config" {
    defaults = {
      tenant_id       = "00000000-0000-0000-0000-000000000001"
      object_id       = "00000000-0000-0000-0000-000000000002"
      subscription_id = "00000000-0000-0000-0000-000000000003"
    }
  }
}

mock_provider "azapi" {
  mock_data "azapi_resource" {
    defaults = {
      output = { identity = { principalId = "00000000-0000-0000-0000-000000000004" } }
    }
  }
}

override_module {
  target = module.naming
  outputs = {
    resource_group          = { name_unique = "rg-platform-test-12345" }
    virtual_network         = { name_unique = "vnet-platform-test-12345" }
    cosmosdb_account        = { name_unique = "cosmos-platform-test-12345" }
    storage_account         = { name_unique = "stplatformtest12345" }
    log_analytics_workspace = { name_unique = "law-platform-test-12345" }
  }
}

variables {
  subscription_id = "00000000-0000-0000-0000-000000000003"
}

run "review_api_unpublished_by_default" {
  command = plan
  assert {
    condition = (
      var.review_api == null &&
      length(azurerm_api_management_api.review) == 0 &&
      length(azurerm_api_management_api_schema.review) == 0 &&
      length(azurerm_api_management_api_policy.review) == 0 &&
      length(azurerm_api_management_api_operation.review) == 0 &&
      output.review_api_url == null
    )
    error_message = "The review API must stay unpublished until review_api is set."
  }
}

run "review_api_published" {
  command = plan
  variables {
    enable_api_management          = true
    api_management_publisher_email = "owner@example.com"
    review_api = {
      audience                  = "api://11111111-1111-1111-1111-111111111111"
      allowed_caller_object_ids = ["22222222-2222-2222-2222-222222222222"]
      allowed_client_app_ids    = ["44444444-4444-4444-4444-444444444444", "33333333-3333-3333-3333-333333333333"]
    }
  }
  assert {
    condition = (
      azurerm_api_management_api.review[0].name == "reviews" &&
      azurerm_api_management_api.review[0].api_management_name == "apim-platform-test-12345" &&
      azurerm_api_management_api.review[0].resource_group_name == "rg-platform-test-12345" &&
      azurerm_api_management_api.review[0].path == "reviews" &&
      azurerm_api_management_api.review[0].revision == "1" &&
      toset(azurerm_api_management_api.review[0].protocols) == toset(["https"]) &&
      !azurerm_api_management_api.review[0].subscription_required
    )
    error_message = "The review API must be HTTPS-only and rely on token validation, not subscription keys."
  }
  assert {
    condition = (
      azurerm_api_management_api_schema.review[0].api_name == "reviews" &&
      azurerm_api_management_api_schema.review[0].schema_id == "review-request" &&
      azurerm_api_management_api_schema.review[0].content_type == "application/vnd.ms-azure-apim.swagger.definitions+json" &&
      jsondecode(azurerm_api_management_api_schema.review[0].value).definitions.ReviewRequest.required == ["input"] &&
      !jsondecode(azurerm_api_management_api_schema.review[0].value).definitions.ReviewRequest.additionalProperties &&
      jsondecode(azurerm_api_management_api_schema.review[0].value).definitions.ReviewRequest.properties.input.maxLength == 60000
    )
    error_message = "The request schema must accept only a bounded input string."
  }
  assert {
    condition = (
      azurerm_api_management_api_operation.review[0].operation_id == "create-response" &&
      azurerm_api_management_api_operation.review[0].method == "POST" &&
      azurerm_api_management_api_operation.review[0].url_template == "/responses" &&
      azurerm_api_management_api_operation.review[0].api_name == "reviews" &&
      azurerm_api_management_api_operation.review[0].request[0].representation[0].content_type == "application/json" &&
      azurerm_api_management_api_operation.review[0].request[0].representation[0].schema_id == "review-request" &&
      azurerm_api_management_api_operation.review[0].request[0].representation[0].type_name == "ReviewRequest" &&
      one(azurerm_api_management_api_operation.review[0].response).status_code == 200
    )
    error_message = "The review operation must be a POST that validates its body against the request schema."
  }
  assert {
    condition     = output.review_api_url == "https://apim-platform-test-12345.azure-api.net/reviews/responses"
    error_message = "The review URL output must join the gateway URL, API path, and operation path."
  }
}

run "review_api_policy_bindings" {
  command = plan
  variables {
    enable_api_management          = true
    api_management_publisher_email = "owner@example.com"
    review_api = {
      audience                  = "api://11111111-1111-1111-1111-111111111111"
      allowed_caller_object_ids = ["66666666-6666-6666-6666-666666666666", "22222222-2222-2222-2222-222222222222"]
      allowed_client_app_ids    = ["44444444-4444-4444-4444-444444444444", "33333333-3333-3333-3333-333333333333"]
    }
  }
  assert {
    condition = (
      azurerm_api_management_api_policy.review[0].api_name == "reviews" &&
      strcontains(azurerm_api_management_api_policy.review[0].xml_content, "tenant-id=\"00000000-0000-0000-0000-000000000001\"") &&
      strcontains(azurerm_api_management_api_policy.review[0].xml_content, "<audience>api://11111111-1111-1111-1111-111111111111</audience>") &&
      strcontains(azurerm_api_management_api_policy.review[0].xml_content, "base-url=\"https://foundry-hosted-agents-platform-test-12345.services.ai.azure.com/api/projects/hosted-agents-dev/agents/review-coordinator-agent/endpoint/protocols/openai\"")
    )
    error_message = "The policy must bind the tenant, the dedicated audience, and the coordinator's Foundry endpoint."
  }
  assert {
    condition = (
      can(regex("<application-id>33333333-3333-3333-3333-333333333333</application-id>\\s*<application-id>44444444-4444-4444-4444-444444444444</application-id>", azurerm_api_management_api_policy.review[0].xml_content)) &&
      strcontains(azurerm_api_management_api_policy.review[0].xml_content, "<value>22222222-2222-2222-2222-222222222222</value><value>66666666-6666-6666-6666-666666666666</value>")
    )
    error_message = "The policy must list the allowed clients and callers in a stable sorted order."
  }
}

run "review_api_custom_agent" {
  command = plan
  variables {
    enable_api_management          = true
    api_management_publisher_email = "owner@example.com"
    review_api = {
      audience                  = "11111111-1111-1111-1111-111111111111"
      allowed_caller_object_ids = ["22222222-2222-2222-2222-222222222222"]
      allowed_client_app_ids    = ["33333333-3333-3333-3333-333333333333"]
      agent_name                = "customer-review-coordinator"
    }
  }
  assert {
    condition = (
      strcontains(azurerm_api_management_api_policy.review[0].xml_content, "/agents/customer-review-coordinator/endpoint/protocols/openai\"") &&
      strcontains(azurerm_api_management_api_policy.review[0].xml_content, "<audience>11111111-1111-1111-1111-111111111111</audience>")
    )
    error_message = "A swapped coordinator and a plain v2 audience must reach the policy."
  }
}

run "reject_review_api_without_gateway" {
  command = plan
  variables {
    review_api = {
      audience                  = "api://11111111-1111-1111-1111-111111111111"
      allowed_caller_object_ids = ["22222222-2222-2222-2222-222222222222"]
      allowed_client_app_ids    = ["33333333-3333-3333-3333-333333333333"]
    }
  }
  expect_failures = [var.review_api]
}

run "reject_review_api_general_azure_audience" {
  command = plan
  variables {
    enable_api_management          = true
    api_management_publisher_email = "owner@example.com"
    review_api = {
      audience                  = "https://management.azure.com/"
      allowed_caller_object_ids = ["22222222-2222-2222-2222-222222222222"]
      allowed_client_app_ids    = ["33333333-3333-3333-3333-333333333333"]
    }
  }
  expect_failures = [var.review_api]
}

run "reject_review_api_empty_caller_allowlist" {
  command = plan
  variables {
    enable_api_management          = true
    api_management_publisher_email = "owner@example.com"
    review_api = {
      audience                  = "api://11111111-1111-1111-1111-111111111111"
      allowed_caller_object_ids = []
      allowed_client_app_ids    = ["33333333-3333-3333-3333-333333333333"]
    }
  }
  expect_failures = [var.review_api]
}

run "reject_review_api_wildcard_client" {
  command = plan
  variables {
    enable_api_management          = true
    api_management_publisher_email = "owner@example.com"
    review_api = {
      audience                  = "api://11111111-1111-1111-1111-111111111111"
      allowed_caller_object_ids = ["22222222-2222-2222-2222-222222222222"]
      allowed_client_app_ids    = ["*"]
    }
  }
  expect_failures = [var.review_api]
}

run "reject_review_api_backend_url_as_agent" {
  command = plan
  variables {
    enable_api_management          = true
    api_management_publisher_email = "owner@example.com"
    review_api = {
      audience                  = "api://11111111-1111-1111-1111-111111111111"
      allowed_caller_object_ids = ["22222222-2222-2222-2222-222222222222"]
      allowed_client_app_ids    = ["33333333-3333-3333-3333-333333333333"]
      agent_name                = "https://other.example"
    }
  }
  expect_failures = [var.review_api]
}

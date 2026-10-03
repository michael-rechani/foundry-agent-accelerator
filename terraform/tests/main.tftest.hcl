# Offline assertions for main.tf and the root variables that shape it.
# test-platform-validation.ps1 runs these against a copy of the whole root module.
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

run "resource_group_and_endpoint_defaults" {
  command = plan
  assert {
    condition = (
      azurerm_resource_group.this.name == "rg-platform-test-12345" &&
      azurerm_resource_group.this.location == "northcentralus" &&
      azurerm_resource_group.this.tags == tomap({ environment = "dev", managed-by = "terraform", workload = "azure-ai-foundry" })
    )
    error_message = "The resource group must use the shared name, the default region, and the required workload tags."
  }
  assert {
    condition = (
      azurerm_private_endpoint.cosmosdb.name == "pe-cosmos-platform-test-12345" &&
      azurerm_private_endpoint.cosmosdb.location == "northcentralus" &&
      azurerm_private_endpoint.cosmosdb.private_service_connection[0].name == "psc-cosmos-platform-test-12345" &&
      !azurerm_private_endpoint.cosmosdb.private_service_connection[0].is_manual_connection &&
      toset(azurerm_private_endpoint.cosmosdb.private_service_connection[0].subresource_names) == toset(["Sql"]) &&
      azurerm_private_endpoint.cosmosdb.private_dns_zone_group[0].name == "default" &&
      length(azurerm_private_endpoint.cosmosdb.private_dns_zone_group[0].private_dns_zone_ids) == 1
    )
    error_message = "Cosmos DB must be reachable only through an automatic private endpoint that resolves through its private DNS zone."
  }
}

run "foundry_diagnostics" {
  command = plan
  assert {
    condition = (
      azurerm_monitor_diagnostic_setting.foundry.name == "diag-foundry" &&
      azurerm_monitor_diagnostic_setting.foundry.target_resource_id == "/subscriptions/00000000-0000-0000-0000-000000000003/resourceGroups/rg-platform-test-12345/providers/Microsoft.CognitiveServices/accounts/foundry-platform-test" &&
      azurerm_monitor_diagnostic_setting.foundry.log_analytics_destination_type == "Dedicated" &&
      one(azurerm_monitor_diagnostic_setting.foundry.enabled_log).category_group == "allLogs" &&
      one(azurerm_monitor_diagnostic_setting.foundry.enabled_metric).category == "AllMetrics"
    )
    error_message = "Every Foundry log category and metric must flow to the platform workspace's dedicated tables."
  }
}

run "foundry_module_inputs" {
  command = plan
  assert {
    condition = (
      module.ai_foundry.inputs.base_name == "aifnd" &&
      module.ai_foundry.inputs.location == "northcentralus" &&
      module.ai_foundry.inputs.ai_foundry.name == "foundry-hosted-agents-platform-test-12345" &&
      module.ai_foundry.inputs.ai_foundry.create_ai_agent_service &&
      module.ai_foundry.inputs.create_private_endpoints &&
      module.ai_foundry.inputs.enable_telemetry &&
      length(module.ai_foundry.inputs.diagnostic_settings) == 0 &&
      module.ai_foundry.inputs.tags.environment == "dev"
    )
    error_message = "The Foundry module must receive the shared name, the default region, and the Agent Service switch."
  }
  assert {
    condition = (
      module.ai_foundry.inputs.ai_foundry.disable_local_auth &&
      !module.ai_foundry.inputs.ai_foundry.public_network_access_enabled &&
      module.ai_foundry.inputs.ai_foundry.network_acls.default_action == "Deny" &&
      module.ai_foundry.inputs.ai_foundry.managed_identities.system_assigned &&
      length(module.ai_foundry.inputs.ai_foundry.private_dns_zone_resource_ids) == 3
    )
    error_message = "The Foundry account must disable key auth and public access, deny by default, and resolve through three private DNS zones."
  }
  assert {
    condition = (
      length(module.ai_foundry.inputs.ai_foundry.network_injections) == 1 &&
      module.ai_foundry.inputs.ai_foundry.network_injections[0].scenario == "agent" &&
      !module.ai_foundry.inputs.ai_foundry.network_injections[0].useMicrosoftManagedNetwork
    )
    error_message = "The Agent Service must inject into the workload's own agent subnet."
  }
  assert {
    condition = (
      module.ai_foundry.inputs.ai_projects.primary.name == "hosted-agents-dev" &&
      module.ai_foundry.inputs.ai_projects.primary.display_name == "Hosted Agents DEV" &&
      module.ai_foundry.inputs.ai_projects.primary.create_project_connections &&
      module.ai_foundry.inputs.ai_projects.primary.ai_search_connection.new_resource_map_key == "agent"
    )
    error_message = "The project must be named for the environment and connect to the Agent Service resources."
  }
  assert {
    condition = (
      module.ai_foundry.inputs.create_byor &&
      !module.ai_foundry.inputs.ai_search_definition.agent.local_authentication_enabled &&
      !module.ai_foundry.inputs.ai_search_definition.agent.public_network_access_enabled &&
      module.ai_foundry.inputs.ai_search_definition.agent.sku == "standard" &&
      module.ai_foundry.inputs.ai_search_definition.agent.replica_count == 1 &&
      !module.ai_foundry.inputs.key_vault_definition.agent.public_network_access_enabled &&
      module.ai_foundry.inputs.key_vault_definition.agent.network_acls.default_action == "Deny" &&
      length(module.ai_foundry.inputs.cosmosdb_definition) == 1 &&
      length(module.ai_foundry.inputs.storage_account_definition) == 1
    )
    error_message = "The Agent Service resources must be private, use Entra auth, and reuse the Cosmos DB and storage accounts."
  }
}

run "foundry_module_without_agent_service" {
  command = plan
  variables { enable_agent_service = false }
  assert {
    condition = (
      !module.ai_foundry.inputs.ai_foundry.create_ai_agent_service &&
      module.ai_foundry.inputs.ai_foundry.network_injections == null &&
      !module.ai_foundry.inputs.ai_projects.primary.create_project_connections &&
      !module.ai_foundry.inputs.create_byor &&
      length(module.ai_foundry.inputs.ai_search_definition) == 0 &&
      length(module.ai_foundry.inputs.cosmosdb_definition) == 0 &&
      length(module.ai_foundry.inputs.key_vault_definition) == 0 &&
      length(module.ai_foundry.inputs.storage_account_definition) == 0
    )
    error_message = "Disabling the Agent Service must drop the capability host, subnet injection, and every supporting resource definition."
  }
}

run "main_inputs_flow_through" {
  command = plan
  variables {
    location              = "westus3"
    environment           = "prod"
    cosmosdb_account_name = "existing-cosmos-test"
    tags                  = { owner = "platform-team" }
    model_deployment = {
      deployment_name = "gpt-4.1"
      format          = "OpenAI"
      name            = "gpt-4.1"
      version         = "2025-04-14"
      sku_name        = "GlobalStandard"
      capacity        = 25
    }
    additional_model_deployments = {
      "gpt-4.1-mini" = { name = "gpt-4.1-mini", version = "2025-04-14", capacity = 5 }
      "embeddings"   = { name = "text-embedding-3-small", version = "1", capacity = 5 }
    }
  }
  assert {
    condition = (
      azurerm_resource_group.this.location == "westus3" &&
      azurerm_resource_group.this.tags == tomap({ environment = "prod", managed-by = "terraform", owner = "platform-team", workload = "azure-ai-foundry" }) &&
      azurerm_private_endpoint.cosmosdb.location == "westus3" &&
      azurerm_private_endpoint.cosmosdb.name == "pe-existing-cosmos-test" &&
      azurerm_private_endpoint.cosmosdb.private_service_connection[0].name == "psc-existing-cosmos-test"
    )
    error_message = "Region, environment, tag, and existing-name overrides must reach the resource group and Cosmos DB endpoint."
  }
  assert {
    condition = (
      output.resource_group_name == "rg-platform-test-12345" &&
      output.foundry_project_endpoint == "https://foundry-hosted-agents-platform-test-12345.services.ai.azure.com/api/projects/hosted-agents-prod" &&
      output.model_deployment_names == ["gpt-4.1", "embeddings", "gpt-4.1-mini"]
    )
    error_message = "The outputs must report the resource group, the project endpoint, and the primary model before the sorted extras."
  }
  assert {
    condition = (
      module.ai_foundry.inputs.location == "westus3" &&
      toset(keys(module.ai_foundry.inputs.ai_model_deployments)) == toset(["extra-embeddings", "extra-gpt-4.1-mini", "primary"]) &&
      module.ai_foundry.inputs.ai_model_deployments.primary.name == "gpt-4.1" &&
      module.ai_foundry.inputs.ai_model_deployments.primary.scale.capacity == 25 &&
      module.ai_foundry.inputs.ai_model_deployments["extra-embeddings"].model.name == "text-embedding-3-small" &&
      module.ai_foundry.inputs.ai_projects.primary.display_name == "Hosted Agents PROD" &&
      module.ai_foundry.inputs.tags.owner == "platform-team"
    )
    error_message = "The primary and extra model deployments, region, environment, and tags must reach the Foundry module."
  }
}

run "reject_unsupported_location" {
  command = plan
  variables { location = "eastus" }
  expect_failures = [var.location]
}

run "reject_unknown_environment" {
  command = plan
  variables { environment = "qa" }
  expect_failures = [var.environment]
}

run "reject_invalid_base_name" {
  command = plan
  variables { base_name = "Bad_Name" }
  expect_failures = [var.base_name]
}

run "reject_invalid_cosmos_name" {
  command = plan
  variables { cosmosdb_account_name = "Invalid_Cosmos" }
  expect_failures = [var.cosmosdb_account_name]
}

run "reject_zero_model_capacity" {
  command = plan
  variables {
    model_deployment = {
      deployment_name = "gpt-4.1"
      format          = "OpenAI"
      name            = "gpt-4.1"
      version         = "2025-04-14"
      sku_name        = "GlobalStandard"
      capacity        = 0
    }
  }
  expect_failures = [var.model_deployment]
}

run "reject_invalid_subscription_id" {
  command = plan
  variables { subscription_id = "not-a-guid" }
  expect_failures = [var.subscription_id]
}

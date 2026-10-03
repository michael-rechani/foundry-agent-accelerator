# Stands in for the Azure/avm-ptn-aiml-ai-foundry/azurerm registry module in the offline platform tests.
# That module contains an ephemeral resource, which Terraform's mock providers can't run.
# Every argument main.tf passes is declared here, so renaming or dropping one fails the tests,
# and each is echoed in "inputs" so tests can assert on what main.tf hands to the module.
variable "base_name" { type = any }
variable "location" { type = any }
variable "resource_group_resource_id" { type = any }
variable "ai_foundry" { type = any }
variable "ai_projects" { type = any }
variable "ai_model_deployments" { type = any }
variable "create_byor" { type = any }
variable "ai_search_definition" { type = any }
variable "cosmosdb_definition" { type = any }
variable "key_vault_definition" { type = any }
variable "storage_account_definition" { type = any }
variable "create_private_endpoints" { type = any }
variable "enable_telemetry" { type = any }
variable "private_endpoint_subnet_resource_id" { type = any }
variable "tags" { type = any }
variable "diagnostic_settings" { type = any }

output "inputs" {
  value = {
    base_name                           = var.base_name
    location                            = var.location
    resource_group_resource_id          = var.resource_group_resource_id
    ai_foundry                          = var.ai_foundry
    ai_projects                         = var.ai_projects
    ai_model_deployments                = var.ai_model_deployments
    create_byor                         = var.create_byor
    ai_search_definition                = var.ai_search_definition
    cosmosdb_definition                 = var.cosmosdb_definition
    key_vault_definition                = var.key_vault_definition
    storage_account_definition          = var.storage_account_definition
    create_private_endpoints            = var.create_private_endpoints
    enable_telemetry                    = var.enable_telemetry
    private_endpoint_subnet_resource_id = var.private_endpoint_subnet_resource_id
    tags                                = var.tags
    diagnostic_settings                 = var.diagnostic_settings
  }
}

output "ai_foundry_name" {
  value = var.ai_foundry.name
}

output "ai_foundry_project_name" {
  value = { for key, project in var.ai_projects : key => project.name }
}

output "ai_foundry_project_id" {
  value = {
    primary = "/subscriptions/00000000-0000-0000-0000-000000000003/resourceGroups/rg-platform-test-12345/providers/Microsoft.CognitiveServices/accounts/foundry-platform-test/projects/hosted-agents-dev"
  }
}

output "ai_foundry_id" {
  value = "/subscriptions/00000000-0000-0000-0000-000000000003/resourceGroups/rg-platform-test-12345/providers/Microsoft.CognitiveServices/accounts/foundry-platform-test"
}

output "resource_id" {
  value = "/subscriptions/00000000-0000-0000-0000-000000000003/resourceGroups/rg-platform-test-12345/providers/Microsoft.CognitiveServices/accounts/foundry-platform-test"
}

output "ai_foundry_project_system_identity_principal_id" {
  value = { primary = "00000000-0000-0000-0000-000000000004" }
}
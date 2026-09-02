output "resource_group_name" {
  description = "Resource group containing the sample."
  value       = azurerm_resource_group.this.name
}

output "foundry_account_id" {
  description = "Resource ID of the Foundry account."
  value       = module.ai_foundry.ai_foundry_id
}

output "foundry_account_name" {
  description = "Name of the Foundry account."
  value       = module.ai_foundry.ai_foundry_name
}

output "foundry_project_id" {
  description = "Resource ID of the primary Foundry project."
  value       = module.ai_foundry.ai_foundry_project_id["primary"]
}

output "foundry_project_name" {
  description = "Name of the primary Foundry project."
  value       = module.ai_foundry.ai_foundry_project_name["primary"]
}

output "foundry_project_endpoint" {
  description = "Foundry project endpoint to pass to SDK clients and hosted agents."
  value       = "https://${module.ai_foundry.ai_foundry_name}.services.ai.azure.com/api/projects/${module.ai_foundry.ai_foundry_project_name["primary"]}"
}

output "model_deployment_name" {
  description = "Model deployment name to pass to hosted agents."
  value       = var.model_deployment.deployment_name
}

output "log_analytics_workspace_id" {
  description = "Resource ID of the workspace receiving Foundry diagnostics."
  value       = azurerm_log_analytics_workspace.this.id
}

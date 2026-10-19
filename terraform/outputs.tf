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

output "model_deployment_names" {
  description = "All model deployment names in the project: the primary one first, then any extra deployments."
  value       = concat([var.model_deployment.deployment_name], sort(keys(var.additional_model_deployments)))
}

output "log_analytics_workspace_id" {
  description = "Resource ID of the workspace receiving Foundry diagnostics."
  value       = azapi_resource.platform_logs.id
}

output "virtual_network_id" {
  description = "Resource ID of the private workload virtual network."
  value       = azurerm_virtual_network.this.id
}

output "workload_virtual_network_name" {
  description = "Name of the private workload virtual network. The Lab reads it from remote state."
  value       = azurerm_virtual_network.this.name
}

output "management_virtual_network_name" {
  description = "Name of the shared management virtual network, or null when the management network is disabled. The Lab reads it from remote state."
  value       = one(azurerm_virtual_network.jumpbox[*].name)
}

output "cosmos_account_name" {
  description = "Name of the Cosmos DB account. The Lab stores its history there and reads the name from remote state."
  value       = azapi_resource.cosmos.name
}

output "private_endpoint_subnet_id" {
  description = "Resource ID of the subnet containing workload private endpoints."
  value       = azurerm_subnet.private_endpoints.id
}

output "agent_subnet_id" {
  description = "Resource ID of the delegated hosted Agent Service subnet."
  value       = azurerm_subnet.agent_services.id
}

output "api_management_name" {
  description = "Name of the API Management service, or null when disabled."
  value       = try(module.api_management[0].name, null)
}

output "api_management_id" {
  description = "Resource ID of the API Management service, or null when disabled."
  value       = try(module.api_management[0].resource_id, null)
}

output "api_management_gateway_url" {
  description = "Gateway URL of the API Management service, or null when disabled."
  value       = try(module.api_management[0].apim_gateway_url, null)
}

output "review_api_url" {
  description = "Review POST endpoint, or null when no review API is configured."
  value       = var.review_api == null ? null : "${module.api_management[0].apim_gateway_url}/reviews/responses"
}

output "jumpbox_name" {
  description = "Name of the private Windows jumpbox, or null when disabled."
  value       = try(azapi_resource.jumpbox[0].name, null)
}

output "jumpbox_admin_username" {
  description = "Local administrator username for the private Windows jumpbox, or null when disabled."
  value       = var.enable_jumpbox ? var.jumpbox_admin_username : null
}

output "jumpbox_key_vault_name" {
  description = "Name of the Key Vault in jumpbox_admin_secret, or null when the jumpbox is disabled or no secret is pinned. Sensitive so plan and apply output doesn't print it; read it with terraform output -raw."
  sensitive   = true
  value       = var.enable_jumpbox && var.jumpbox_admin_secret != null ? basename(var.jumpbox_admin_secret.key_vault_id) : null
}

output "jumpbox_admin_password_secret_name" {
  description = "Name of the Key Vault secret in jumpbox_admin_secret, or null when the jumpbox is disabled or no secret is pinned. Sensitive so plan and apply output doesn't print it; read it with terraform output -raw."
  sensitive   = true
  value       = var.enable_jumpbox && var.jumpbox_admin_secret != null ? var.jumpbox_admin_secret.name : null
}

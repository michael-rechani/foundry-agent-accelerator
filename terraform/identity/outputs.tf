output "deploy_client_id" {
  description = "Client ID of the deploy identity (AZURE_CLIENT_ID in the deploy environment)."
  value       = azuread_application.deploy.client_id
}

output "deploy_principal_id" {
  description = "Object ID of the deploy identity's service principal."
  value       = azuread_service_principal.deploy.object_id
}

output "recording_client_id" {
  description = "Client ID of the library recording identity, or null when recording is off."
  value       = try(azuread_application.recording[0].client_id, null)
}

output "deploy_environment" {
  description = "GitHub environment that gates the Lab image deploy."
  value       = github_repository_environment.deploy.environment
}

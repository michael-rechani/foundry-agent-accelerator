output "ai_foundry_project_id" {
  value = {
    primary = "/subscriptions/00000000-0000-0000-0000-000000000003/resourceGroups/rg-platform-test-12345/providers/Microsoft.CognitiveServices/accounts/foundry-platform-test/projects/hosted-agents-dev"
  }
}

output "ai_foundry_id" {
  value = "/subscriptions/00000000-0000-0000-0000-000000000003/resourceGroups/rg-platform-test-12345/providers/Microsoft.CognitiveServices/accounts/foundry-platform-test"
}

output "ai_foundry_project_system_identity_principal_id" {
  value = { primary = "00000000-0000-0000-0000-000000000004" }
}
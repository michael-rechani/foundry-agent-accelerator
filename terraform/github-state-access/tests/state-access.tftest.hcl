mock_provider "azurerm" {}
mock_provider "azuread" {
  mock_data "azuread_client_config" {
    defaults = {
      object_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
      tenant_id = "11111111-2222-3333-4444-555555555555"
    }
  }
  mock_resource "azuread_application" {
    defaults = {
      id        = "/applications/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
      client_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    }
  }
}
mock_provider "github" {}

variables {
  subscription_id     = "11111111-2222-3333-4444-555555555555"
  storage_account_id  = "/subscriptions/11111111-2222-3333-4444-555555555555/resourceGroups/rg-state/providers/Microsoft.Storage/storageAccounts/stfixture"
  container_name      = "tfstate"
  private_endpoint_ip = "10.42.0.23"
  reviewer_user_ids   = [12345]
}

run "only_protected_github_can_write_state" {
  command = plan
  assert {
    condition = (
      github_repository_environment.state.environment == "terraform-state" &&
      one(github_repository_environment.state.reviewers).users == toset([12345]) &&
      github_repository_environment_deployment_policy.state.branch_pattern == "main" &&
      startswith(azuread_application_federated_identity_credential.state.issuer, "https://token.actions.githubusercontent.com")
    )
    error_message = "OIDC must be gated by the dedicated reviewed main-only environment."
  }
  assert {
    condition = (
      azurerm_role_assignment.state.scope == "${var.storage_account_id}/blobServices/default/containers/tfstate" &&
      azurerm_role_assignment.state.condition_version == "2.0" &&
      strcontains(azurerm_role_assignment.state.condition, "StringStartsWith 'ai-foundry/'") &&
      strcontains(azurerm_role_assignment.state.condition, "SubOperationMatches{'Blob.List'}") &&
      toset(one(azurerm_role_definition.state.permissions).actions) == toset(["Microsoft.Storage/storageAccounts/blobServices/containers/read"]) &&
      length(one(azurerm_role_definition.state.permissions).data_actions) == 4
    )
    error_message = "The identity may operate only Lab namespace blobs, not containers, infrastructure or RBAC."
  }
}

run "reviewer_required" {
  command = plan
  variables {
    reviewer_user_ids = []
  }
  expect_failures = [var.reviewer_user_ids]
}

run "private_address_required" {
  command = plan
  variables {
    private_endpoint_ip = "20.1.1.1"
  }
  expect_failures = [var.private_endpoint_ip]
}

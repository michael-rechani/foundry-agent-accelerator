mock_provider "azapi" {}

override_data {
  target = data.azapi_resource.project
  values = {
    output = { identity = { principalId = "00000000-0000-0000-0000-000000000002" } }
  }
}

override_data {
  target = data.azapi_resource.workspace
  values = {
    id       = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-example/providers/Microsoft.OperationalInsights/workspaces/log-example"
    location = "northcentralus"
  }
}

override_resource {
  target          = azapi_resource.insights
  override_during = plan
  values = {
    id = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-example/providers/Microsoft.Insights/components/appi-example"
    output = {
      properties = {
        ConnectionString = "InstrumentationKey=00000000-0000-0000-0000-000000000004;IngestionEndpoint=https://example.test/"
      }
    }
  }
}

variables {
  subscription_id           = "00000000-0000-0000-0000-000000000001"
  resource_group_name       = "rg-example"
  foundry_account_name      = "foundry-example"
  project_name              = "hosted-agents-dev"
  workspace_name            = "log-example"
  private_link_scope_name   = "ampls-example"
  application_insights_name = "appi-example"
  agent_principal_ids       = { specialist = "00000000-0000-0000-0000-000000000003" }
}

run "private_metadata_monitoring" {
  command = plan
  assert {
    condition = (
      azapi_resource.insights.body.properties.DisableLocalAuth &&
      azapi_resource.insights.body.properties.publicNetworkAccessForIngestion == "Disabled" &&
      azapi_resource.insights.body.properties.publicNetworkAccessForQuery == "Disabled"
    )
    error_message = "Monitoring must preserve Entra-only, private ingestion and query."
  }
  assert {
    condition     = length(azapi_resource.connection) == 0
    error_message = "Provisioning monitoring must not start project-wide tracing before the privacy rollout."
  }
  assert {
    condition = (
      length(azapi_resource.publisher) == 2 &&
      azapi_resource.publisher["specialist"].body.properties.principalId == var.agent_principal_ids["specialist"] &&
      alltrue([for publisher in azapi_resource.publisher :
        publisher.parent_id == azapi_resource.insights.id &&
        publisher.body.properties.roleDefinitionId == local.publisher_role_id
      ])
    )
    error_message = "Only the project and explicitly supplied agents receive component-scoped publishing permission."
  }
  assert {
    condition     = azapi_resource.private_link.body.properties.linkedResourceId == lower(azapi_resource.insights.id)
    error_message = "The existing private link scope must include the component using Azure's canonical lowercase ID."
  }
}

run "connect_after_privacy_rollout" {
  command = plan
  variables {
    enable_project_connection = true
  }
  assert {
    condition = (
      azapi_resource.connection[0].body.properties.category == "AppInsights" &&
      azapi_resource.connection[0].body.properties.authType == "ProjectManagedIdentity" &&
      azapi_resource.connection[0].body.properties.metadata.ApplicationInsightsConnectionString == azapi_resource.insights.output.properties.ConnectionString &&
      !contains(keys(azapi_resource.connection[0].body.properties), "credentials")
    )
    error_message = "The Foundry connection must use the project identity without keys."
  }
}

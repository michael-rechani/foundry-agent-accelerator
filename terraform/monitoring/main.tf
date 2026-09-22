locals {
  resource_group_id = "/subscriptions/${var.subscription_id}/resourceGroups/${var.resource_group_name}"
  project_id        = "${local.resource_group_id}/providers/Microsoft.CognitiveServices/accounts/${var.foundry_account_name}/projects/${var.project_name}"
  publisher_role_id = "/subscriptions/${var.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/3913510d-42f4-4e42-8a64-420c390055eb"
  publishers        = merge(var.agent_principal_ids, { project = data.azapi_resource.project.output.identity.principalId })
}

data "azapi_resource" "project" {
  type                   = "Microsoft.CognitiveServices/accounts/projects@2025-06-01"
  resource_id            = local.project_id
  response_export_values = ["identity.principalId"]
}

data "azapi_resource" "workspace" {
  type                   = "Microsoft.OperationalInsights/workspaces@2023-09-01"
  name                   = var.workspace_name
  parent_id              = local.resource_group_id
  response_export_values = ["location"]
}

resource "azapi_resource" "insights" {
  type      = "Microsoft.Insights/components@2020-02-02"
  name      = var.application_insights_name
  parent_id = local.resource_group_id
  location  = data.azapi_resource.workspace.location
  body = {
    kind = "web"
    properties = {
      Application_Type                = "web"
      WorkspaceResourceId             = data.azapi_resource.workspace.id
      IngestionMode                   = "LogAnalytics"
      RetentionInDays                 = 30
      DisableLocalAuth                = true
      publicNetworkAccessForIngestion = "Disabled"
      publicNetworkAccessForQuery     = "Disabled"
    }
  }
  response_export_values = ["properties.AppId", "properties.ConnectionString"]
  lifecycle {
    prevent_destroy = true
  }
}

resource "azapi_resource" "private_link" {
  type      = "Microsoft.Insights/privateLinkScopes/scopedResources@2021-07-01-preview"
  name      = var.application_insights_name
  parent_id = "${local.resource_group_id}/providers/Microsoft.Insights/privateLinkScopes/${var.private_link_scope_name}"
  body = {
    properties = { linkedResourceId = lower(azapi_resource.insights.id) }
  }
  response_export_values = []
}

resource "azapi_resource" "publisher" {
  for_each  = local.publishers
  type      = "Microsoft.Authorization/roleAssignments@2022-04-01"
  name      = uuidv5("url", "${azapi_resource.insights.id}/${each.value}/Monitoring Metrics Publisher")
  parent_id = azapi_resource.insights.id
  body = {
    properties = {
      roleDefinitionId = local.publisher_role_id
      principalId      = each.value
      principalType    = "ServicePrincipal"
      # Match imported grants without requiring an RBAC write to normalize nulls.
      condition                          = null
      conditionVersion                   = null
      delegatedManagedIdentityResourceId = null
      description                        = null
    }
  }
}

resource "azapi_resource" "connection" {
  count     = var.enable_project_connection ? 1 : 0
  type      = "Microsoft.CognitiveServices/accounts/projects/connections@2025-06-01"
  name      = "agent-monitoring"
  parent_id = local.project_id
  # The published schema omits AppInsights and its ProjectManagedIdentity auth type.
  schema_validation_enabled = false
  body = {
    properties = {
      category = "AppInsights"
      target   = azapi_resource.insights.id
      authType = "ProjectManagedIdentity"
      metadata = {
        ApiType                             = "Azure"
        ResourceId                          = azapi_resource.insights.id
        location                            = data.azapi_resource.workspace.location
        ApplicationInsightsConnectionString = sensitive(azapi_resource.insights.output.properties.ConnectionString)
      }
    }
  }
  response_export_values = []
  depends_on             = [azapi_resource.private_link, azapi_resource.publisher]
}

output "application_insights_id" {
  description = "Application Insights resource used by Foundry traces."
  value       = azapi_resource.insights.id
}

output "project_monitoring_connected" {
  description = "Whether the project telemetry connection is managed and enabled."
  value       = var.enable_project_connection
}

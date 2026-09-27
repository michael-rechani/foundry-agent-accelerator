locals {
  agent_consumer_role_id  = "/subscriptions/${var.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/eed3b665-ab3a-47b6-8f48-c9382fb1dad6"
  coordinator_specialists = var.coordinator_agent_access == null ? toset([]) : var.coordinator_agent_access.specialist_agents
}

# Foundry User: deployer data-plane access to this project, not platform ARM administration.
resource "azurerm_role_assignment" "deployer_foundry_user" {
  principal_id       = coalesce(var.deployment_principal_id, data.azurerm_client_config.current.object_id)
  role_definition_id = "/subscriptions/${var.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/53ca6127-db72-4b80-b1b0-d745d6d5456d"
  scope              = module.ai_foundry.ai_foundry_project_id["primary"]
}

# Foundry User at account scope: Microsoft's evaluation guidance for the project identity.
# This does not replace the private storage resource-instance rule; see docs/permissions.md.
resource "azurerm_role_assignment" "project_foundry_user" {
  principal_id       = module.ai_foundry.ai_foundry_project_system_identity_principal_id["primary"]
  principal_type     = "ServicePrincipal"
  role_definition_id = "/subscriptions/${var.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/53ca6127-db72-4b80-b1b0-d745d6d5456d"
  scope              = module.ai_foundry.ai_foundry_id
}

# Foundry User: the optional gateway calls the project's agent endpoints as its managed identity.
resource "azurerm_role_assignment" "api_management_foundry_user" {
  count = var.enable_api_management ? 1 : 0

  principal_id       = module.api_management[0].resource.identity[0].principal_id
  role_definition_id = "/subscriptions/${var.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/53ca6127-db72-4b80-b1b0-d745d6d5456d"
  scope              = module.ai_foundry.ai_foundry_project_id["primary"]
}

# Agent scope limits the coordinator to invoking the listed specialists' endpoints.
resource "azapi_resource" "coordinator_agent_consumer" {
  for_each  = local.coordinator_specialists
  type      = "Microsoft.Authorization/roleAssignments@2022-04-01"
  name      = uuidv5("url", "${module.ai_foundry.ai_foundry_project_id["primary"]}/agents/${each.value}/${lower(var.coordinator_agent_access.principal_id)}/Foundry Agent Consumer")
  parent_id = "${module.ai_foundry.ai_foundry_project_id["primary"]}/agents/${each.value}"
  body = {
    properties = {
      roleDefinitionId = local.agent_consumer_role_id
      principalId      = lower(var.coordinator_agent_access.principal_id)
      principalType    = "ServicePrincipal"
    }
  }
}

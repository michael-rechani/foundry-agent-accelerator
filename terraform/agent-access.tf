locals {
  agent_consumer_role_id  = "/subscriptions/${var.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/eed3b665-ab3a-47b6-8f48-c9382fb1dad6"
  coordinator_specialists = var.coordinator_agent_access == null ? toset([]) : var.coordinator_agent_access.specialist_agents
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

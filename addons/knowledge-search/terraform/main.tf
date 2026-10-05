locals {
  subscription_id = split("/", var.search_service_id)[2]
}

# Search Index Data Reader on one index: the agent can query it but not load documents, change the index, or
# read keys. The role, the principal type and the index scope are fixed here, not inputs. The manifest in
# ../addon.json lists the same grant, and addons/plan_check.py fails a saved plan that grants anything else.
resource "azurerm_role_assignment" "search_index_reader" {
  principal_id       = lower(var.principal_id)
  principal_type     = "ServicePrincipal"
  role_definition_id = "/subscriptions/${local.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/1407120a-92aa-4202-b7e9-c0e197c71c8f"
  scope              = "${var.search_service_id}/indexes/${var.index_name}"
  description        = "Knowledge search add-on: read one index"
}

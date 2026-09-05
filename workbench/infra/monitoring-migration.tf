variable "import_existing_log_workspace" {
  type        = bool
  default     = false
  description = "One-time opt-in when transferring an existing AzureRM-managed Lab workspace to AzAPI."
}

removed {
  from = azurerm_log_analytics_workspace.this
  lifecycle {
    destroy = false
  }
}

import {
  for_each = var.import_existing_log_workspace ? toset(["existing"]) : toset([])
  to       = azapi_resource.logs
  id       = "/subscriptions/${var.subscription_id}/resourceGroups/${var.resource_group_name}/providers/Microsoft.OperationalInsights/workspaces/log-${var.name}"
}
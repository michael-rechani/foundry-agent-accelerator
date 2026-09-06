variable "alert_action_group_ids" {
  type        = set(string)
  default     = []
  description = "Existing Azure Monitor action groups for notification delivery. Empty means portal alerts only."
}

variable "monitor_private_link_scope_name" {
  type        = string
  description = "Existing AMPLS linked to the workload and management networks."
  default     = "ampls-aifnd-dev"
}

variable "private_monitoring_enabled" {
  type        = bool
  description = "Enable after the workspace association and private query path are verified."
  default     = true
}

resource "azapi_resource" "logs" {
  type      = "Microsoft.OperationalInsights/workspaces@2023-09-01"
  name      = "log-${var.name}"
  parent_id = "/subscriptions/${var.subscription_id}/resourceGroups/${var.resource_group_name}"
  location  = data.azurerm_virtual_network.workload.location
  tags      = local.tags
  body = {
    properties = {
      sku                             = { name = "PerGB2018" }
      retentionInDays                 = 30
      workspaceCapping                = { dailyQuotaGb = 0.1 }
      publicNetworkAccessForIngestion = var.private_monitoring_enabled ? "Disabled" : "Enabled"
      publicNetworkAccessForQuery     = var.private_monitoring_enabled ? "Disabled" : "Enabled"
      features = {
        disableLocalAuth                            = true
        enableLogAccessUsingOnlyResourcePermissions = true
        legacy                                      = 0
        searchVersion                               = 1
      }
    }
  }
  lifecycle {
    prevent_destroy = true
  }
}

resource "azurerm_monitor_private_link_scoped_service" "logs" {
  linked_resource_id  = azapi_resource.logs.id
  name                = "law-${var.name}"
  resource_group_name = var.resource_group_name
  scope_name          = var.monitor_private_link_scope_name
}

resource "azurerm_monitor_diagnostic_setting" "this" {
  name                       = "operational-logs"
  target_resource_id         = azurerm_container_app_environment.this.id
  log_analytics_workspace_id = azapi_resource.logs.id
  enabled_log {
    category = "ContainerAppConsoleLogs"
  }
  enabled_log {
    category = "ContainerAppSystemLogs"
  }
}

locals {
  request_log_query = <<-KQL
    union isfuzzy=true ContainerAppConsoleLogs_CL, ContainerAppConsoleLogs
    | where tostring(column_ifexists("ContainerAppName_s", column_ifexists("ContainerAppName", ""))) == "${var.name}"
    | extend payload = parse_json(extract(@"(\{.*\})", 1, tostring(column_ifexists("Log_s", column_ifexists("Log", "")))))
  KQL
  operational_alerts = {
    request-failures = {
      query     = "${local.request_log_query}\n| where payload.event == 'workbench_request' and (toint(payload.status) >= 500 or toint(payload.status) == 429)"
      threshold = 5
    }
    dependencies = {
      query     = "${local.request_log_query}\n| where payload.event == 'workbench_dependencies' and payload.status != 'ready'"
      threshold = 3
    }
  }
}

resource "azurerm_monitor_scheduled_query_rules_alert_v2" "operational" {
  for_each                = local.operational_alerts
  name                    = "${var.name}-${each.key}"
  resource_group_name     = var.resource_group_name
  location                = data.azurerm_virtual_network.workload.location
  scopes                  = [azapi_resource.logs.id]
  severity                = 2
  auto_mitigation_enabled = true
  evaluation_frequency    = "PT5M"
  window_duration         = "PT5M"
  skip_query_validation   = true
  criteria {
    query                   = each.value.query
    time_aggregation_method = "Count"
    threshold               = each.value.threshold
    operator                = "GreaterThanOrEqual"
  }
  dynamic "action" {
    for_each = length(var.alert_action_group_ids) == 0 ? [] : [1]
    content {
      action_groups = var.alert_action_group_ids
    }
  }
  tags = local.tags
}

resource "azurerm_monitor_scheduled_query_rules_alert_v2" "heartbeat" {
  name                    = "${var.name}-missing-heartbeat"
  resource_group_name     = var.resource_group_name
  location                = data.azurerm_virtual_network.workload.location
  scopes                  = [azapi_resource.logs.id]
  severity                = 2
  auto_mitigation_enabled = true
  evaluation_frequency    = "PT5M"
  window_duration         = "PT15M"
  skip_query_validation   = true
  criteria {
    query                   = "${local.request_log_query}\n| where payload.event == 'workbench_dependencies'\n| summarize Heartbeats=count()"
    time_aggregation_method = "Minimum"
    metric_measure_column   = "Heartbeats"
    threshold               = 1
    operator                = "LessThan"
  }
  dynamic "action" {
    for_each = length(var.alert_action_group_ids) == 0 ? [] : [1]
    content {
      action_groups = var.alert_action_group_ids
    }
  }
  tags = local.tags
}
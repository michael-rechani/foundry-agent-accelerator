mock_provider "azurerm" {
  mock_data "azurerm_virtual_network" {
    defaults = {
      location = "eastus"
    }
  }
  mock_resource "azurerm_container_app_environment" {
    defaults = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000003/resourceGroups/rg-monitoring-test/providers/Microsoft.App/managedEnvironments/cae-monitoring-test"
    }
  }
  mock_resource "azurerm_monitor_action_group" {
    defaults = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000003/resourceGroups/rg-monitoring-test/providers/Microsoft.Insights/actionGroups/monitoring-test-operations"
    }
  }
}

mock_provider "azapi" {
  mock_resource "azapi_resource" {
    defaults = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000003/resourceGroups/rg-monitoring-test/providers/Microsoft.OperationalInsights/workspaces/log-monitoring-test"
    }
  }
}

run "no_notification_defaults" {
  command = plan

  assert {
    condition = (
      length(azurerm_monitor_action_group.operations) == 0 &&
      output.managed_alert_action_group_id == null &&
      !local.alert_notifications_enabled
    )
    error_message = "Default inputs must not create an action group or configure recipients."
  }
  assert {
    condition = (
      toset(keys(azurerm_monitor_scheduled_query_rules_alert_v2.operational)) == toset(["request-failures", "dependencies"]) &&
      alltrue([for rule in azurerm_monitor_scheduled_query_rules_alert_v2.operational : length(rule.action) == 0]) &&
      length(azurerm_monitor_scheduled_query_rules_alert_v2.heartbeat.action) == 0
    )
    error_message = "All three default alerts must remain present and portal-only."
  }
  assert {
    condition = (
      azapi_resource.logs.body.properties.publicNetworkAccessForIngestion == "Disabled" &&
      azapi_resource.logs.body.properties.publicNetworkAccessForQuery == "Disabled" &&
      azapi_resource.logs.body.properties.features.disableLocalAuth
    )
    error_message = "Alert delivery must not weaken private monitoring or enable shared keys."
  }
}

run "existing_groups_only" {
  command = plan
  variables {
    alert_action_group_ids = [
      "/subscriptions/00000000-0000-0000-0000-000000000003/resourceGroups/rg-monitoring-test/providers/Microsoft.Insights/actionGroups/existing-operations",
    ]
  }

  assert {
    condition     = length(azurerm_monitor_action_group.operations) == 0
    error_message = "Reusing an existing action group must not create or take ownership of it."
  }
  assert {
    condition = (
      alltrue([for rule in azurerm_monitor_scheduled_query_rules_alert_v2.operational : toset(one(rule.action).action_groups) == var.alert_action_group_ids]) &&
      toset(one(azurerm_monitor_scheduled_query_rules_alert_v2.heartbeat.action).action_groups) == var.alert_action_group_ids
    )
    error_message = "Every operational and heartbeat alert must retain the supplied existing groups."
  }
}

run "managed_email_group" {
  command = apply
  variables {
    managed_alert_email_receivers = {
      operations = "operations@example.invalid"
      backup     = "backup@example.invalid"
    }
  }

  assert {
    condition = (
      length(azurerm_monitor_action_group.operations) == 1 &&
      azurerm_monitor_action_group.operations[0].name == "monitoring-test-operations" &&
      azurerm_monitor_action_group.operations[0].short_name == "FoundryLab" &&
      azurerm_monitor_action_group.operations[0].enabled &&
      length(azurerm_monitor_action_group.operations[0].email_receiver) == 2 &&
      alltrue([for receiver in azurerm_monitor_action_group.operations[0].email_receiver :
        receiver.use_common_alert_schema && receiver.email_address == var.managed_alert_email_receivers[receiver.name]
      ])
    )
    error_message = "Managed receivers must create one action group with matching common-schema email receivers."
  }
  assert {
    condition = (
      alltrue([for rule in azurerm_monitor_scheduled_query_rules_alert_v2.operational :
        toset(one(rule.action).action_groups) == toset([output.managed_alert_action_group_id])
      ]) &&
      toset(one(azurerm_monitor_scheduled_query_rules_alert_v2.heartbeat.action).action_groups) == toset([output.managed_alert_action_group_id])
    )
    error_message = "The Terraform-owned group must be wired to every operational and heartbeat alert."
  }
}

run "managed_and_existing_groups" {
  command = apply
  variables {
    managed_alert_email_receivers = { operations = "operations@example.invalid" }
    alert_action_group_ids = [
      "/subscriptions/00000000-0000-0000-0000-000000000003/resourceGroups/rg-monitoring-test/providers/Microsoft.Insights/actionGroups/existing-operations",
      "/subscriptions/00000000-0000-0000-0000-000000000003/resourceGroups/rg-monitoring-test/providers/Microsoft.Insights/actionGroups/monitoring-test-operations",
    ]
  }

  assert {
    condition = (
      length(local.effective_alert_action_group_ids) == 2 &&
      contains(local.effective_alert_action_group_ids, output.managed_alert_action_group_id) &&
      alltrue([for rule in azurerm_monitor_scheduled_query_rules_alert_v2.operational :
        toset(one(rule.action).action_groups) == var.alert_action_group_ids
      ]) &&
      toset(one(azurerm_monitor_scheduled_query_rules_alert_v2.heartbeat.action).action_groups) == var.alert_action_group_ids
    )
    error_message = "Managed and existing groups must be combined without duplicate action-group IDs."
  }
}

run "disable_managed_group_preserves_existing" {
  command = apply
  variables {
    managed_alert_email_receivers = {}
    alert_action_group_ids = [
      "/subscriptions/00000000-0000-0000-0000-000000000003/resourceGroups/rg-monitoring-test/providers/Microsoft.Insights/actionGroups/existing-operations",
    ]
  }

  assert {
    condition = (
      length(azurerm_monitor_action_group.operations) == 0 &&
      output.managed_alert_action_group_id == null &&
      alltrue([for rule in azurerm_monitor_scheduled_query_rules_alert_v2.operational :
        toset(one(rule.action).action_groups) == var.alert_action_group_ids
      ]) &&
      toset(one(azurerm_monitor_scheduled_query_rules_alert_v2.heartbeat.action).action_groups) == var.alert_action_group_ids
    )
    error_message = "Removing managed recipients must remove only their owned group and keep every alert attached to existing groups."
  }
}

run "reject_invalid_address" {
  command = plan
  variables {
    managed_alert_email_receivers = { operations = "not-an-email" }
  }
  expect_failures = [var.managed_alert_email_receivers]
}

run "reject_blank_address" {
  command = plan
  variables {
    managed_alert_email_receivers = { operations = "" }
  }
  expect_failures = [var.managed_alert_email_receivers]
}

run "reject_null_address" {
  command = plan
  variables {
    managed_alert_email_receivers = { operations = null }
  }
  expect_failures = [var.managed_alert_email_receivers]
}

run "reject_invalid_receiver_name" {
  command = plan
  variables {
    managed_alert_email_receivers = { "operations team" = "operations@example.invalid" }
  }
  expect_failures = [var.managed_alert_email_receivers]
}

run "reject_duplicate_addresses" {
  command = plan
  variables {
    managed_alert_email_receivers = {
      operations = "operations@example.invalid"
      backup     = "OPERATIONS@example.invalid"
    }
  }
  expect_failures = [var.managed_alert_email_receivers]
}

run "reject_duplicate_receiver_names" {
  command = plan
  variables {
    managed_alert_email_receivers = {
      operations = "operations@example.invalid"
      Operations = "backup@example.invalid"
    }
  }
  expect_failures = [var.managed_alert_email_receivers]
}

mock_provider "azurerm" {}
mock_provider "azapi" {}

variables {
  subscription_id      = "00000000-0000-0000-0000-000000000003"
  resource_group_name  = "rg-budget"
  workload_vnet_name   = "vnet-workload"
  management_vnet_name = "vnet-management"
  foundry_account_name = "foundry-budget"
  foundry_project_name = "project-budget"
  registry_name        = "registrybudget"
  cosmos_account_name  = "cosmos-budget"
  bootstrap_only       = true
}

run "no_budget_by_default" {
  command = plan
  plan_options {
    target = [azurerm_consumption_budget_resource_group.lab]
  }
  assert {
    condition     = length(azurerm_consumption_budget_resource_group.lab) == 0
    error_message = "The Lab budget must stay off unless an amount is configured."
  }
}

run "budget_alerts_the_operational_action_group" {
  command = plan
  variables {
    alert_action_group_ids = ["/subscriptions/00000000-0000-0000-0000-000000000003/resourceGroups/rg-budget/providers/Microsoft.Insights/actionGroups/operations"]
    lab_budget = {
      amount     = 150
      start_date = "2026-06-01T00:00:00Z"
    }
  }
  plan_options {
    target = [azurerm_consumption_budget_resource_group.lab]
  }
  assert {
    condition = (
      azurerm_consumption_budget_resource_group.lab[0].resource_group_id == "/subscriptions/00000000-0000-0000-0000-000000000003/resourceGroups/rg-budget" &&
      azurerm_consumption_budget_resource_group.lab[0].amount == 150 &&
      azurerm_consumption_budget_resource_group.lab[0].time_grain == "Monthly"
    )
    error_message = "The budget must be a monthly budget on the Lab resource group."
  }
  assert {
    condition = (
      toset([for item in azurerm_consumption_budget_resource_group.lab[0].notification : "${item.threshold_type}-${item.threshold}"]) ==
      toset(["Actual-50", "Actual-80", "Actual-100", "Forecasted-100"]) &&
      alltrue([for item in azurerm_consumption_budget_resource_group.lab[0].notification :
        item.enabled && contains(item.contact_groups, one(var.alert_action_group_ids))
      ])
    )
    error_message = "Budget alerts must fire at 50, 80 and 100 percent actual and 100 percent forecast, to the action group."
  }
}

run "budget_without_recipients_is_rejected" {
  command = plan
  variables {
    lab_budget = {
      amount     = 150
      start_date = "2026-06-01T00:00:00Z"
    }
  }
  plan_options {
    target = [azurerm_consumption_budget_resource_group.lab]
  }
  expect_failures = [azurerm_consumption_budget_resource_group.lab]
}

run "budget_must_start_on_the_first_of_a_month" {
  command = plan
  variables {
    lab_budget = {
      amount         = 150
      start_date     = "2026-06-15T00:00:00Z"
      contact_emails = ["finance@example.com"]
    }
  }
  plan_options {
    target = [azurerm_consumption_budget_resource_group.lab]
  }
  expect_failures = [var.lab_budget]
}

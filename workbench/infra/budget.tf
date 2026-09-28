variable "lab_budget" {
  type = object({
    amount         = number
    start_date     = string
    contact_emails = optional(list(string), [])
  })
  default     = null
  description = "Optional monthly Cost Management budget on the Lab resource group. Null creates no budget. The amount is in the billing currency, start_date is the first day of a month such as 2026-06-01T00:00:00Z, and alerts go to the operational action groups plus any contact_emails. Keep real recipients in ignored deployment inputs."

  validation {
    condition     = var.lab_budget == null || try(var.lab_budget.amount > 0 && var.lab_budget.amount <= 1000000, false)
    error_message = "Set a budget amount greater than zero and no more than 1,000,000."
  }

  validation {
    condition     = var.lab_budget == null || can(regex("^[0-9]{4}-(0[1-9]|1[0-2])-01T00:00:00Z$", var.lab_budget.start_date))
    error_message = "Start the budget on the first day of a month, for example 2026-06-01T00:00:00Z."
  }

  validation {
    condition = var.lab_budget == null || alltrue([
      for address in try(var.lab_budget.contact_emails, []) : can(regex("^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$", address))
    ])
    error_message = "Budget contact emails must be nonempty addresses without whitespace."
  }
}

locals {
  budget_thresholds = {
    actual-50      = { threshold = 50, threshold_type = "Actual" }
    actual-80      = { threshold = 80, threshold_type = "Actual" }
    actual-100     = { threshold = 100, threshold_type = "Actual" }
    forecasted-100 = { threshold = 100, threshold_type = "Forecasted" }
  }
}

resource "azurerm_consumption_budget_resource_group" "lab" {
  count             = var.lab_budget == null ? 0 : 1
  name              = "${var.name}-monthly"
  resource_group_id = "/subscriptions/${var.subscription_id}/resourceGroups/${var.resource_group_name}"
  amount            = var.lab_budget.amount
  time_grain        = "Monthly"

  time_period {
    start_date = var.lab_budget.start_date
  }

  dynamic "notification" {
    for_each = local.budget_thresholds
    content {
      enabled        = true
      threshold      = notification.value.threshold
      threshold_type = notification.value.threshold_type
      operator       = "GreaterThanOrEqualTo"
      contact_groups = sort(tolist(local.effective_alert_action_group_ids))
      contact_emails = var.lab_budget.contact_emails
    }
  }

  lifecycle {
    precondition {
      condition     = length(local.effective_alert_action_group_ids) > 0 || length(var.lab_budget.contact_emails) > 0
      error_message = "A Lab budget needs at least one recipient: an alert action group, a managed alert email receiver, or a budget contact email."
    }
  }
}

output "lab_budget_id" {
  description = "Lab resource group budget ID, or null when no budget is configured."
  value       = one(azurerm_consumption_budget_resource_group.lab[*].id)
}

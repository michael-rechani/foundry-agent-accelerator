variable "managed_alert_email_receivers" {
  type        = map(string)
  default     = {}
  nullable    = false
  description = "Optional receiver-name to email-address map for a Terraform-owned operational action group. Empty creates no group. Keep real recipients in ignored deployment inputs."

  validation {
    condition = alltrue([
      for name, address in var.managed_alert_email_receivers :
      can(regex("^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$", name)) &&
      can(regex("^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$", address))
    ])
    error_message = "Use receiver names of 1-128 letters, digits, dots, underscores, or hyphens starting with a letter or digit, and nonempty email addresses without whitespace."
  }

  validation {
    condition = (
      length(distinct([for name in keys(var.managed_alert_email_receivers) : lower(name)])) ==
      length(var.managed_alert_email_receivers)
    )
    error_message = "Alert receiver names must be unique regardless of letter case."
  }

  validation {
    condition = (
      length(distinct([for address in values(var.managed_alert_email_receivers) : address == null ? "" : lower(address)])) ==
      length(var.managed_alert_email_receivers)
    )
    error_message = "Use each alert email address only once, regardless of letter case."
  }
}

resource "azurerm_monitor_action_group" "operations" {
  count               = length(var.managed_alert_email_receivers) == 0 ? 0 : 1
  name                = "${var.name}-operations"
  resource_group_name = local.resource_group_name
  short_name          = "FoundryLab"
  enabled             = true
  tags                = local.tags

  dynamic "email_receiver" {
    for_each = var.managed_alert_email_receivers
    content {
      name                    = email_receiver.key
      email_address           = email_receiver.value
      use_common_alert_schema = true
    }
  }
}

locals {
  alert_notifications_enabled = length(var.alert_action_group_ids) > 0 || length(var.managed_alert_email_receivers) > 0
  effective_alert_action_group_ids = setunion(
    var.alert_action_group_ids,
    toset(azurerm_monitor_action_group.operations[*].id),
  )
}

output "managed_alert_action_group_id" {
  description = "Terraform-owned operational action group ID, or null when no managed email receivers are configured."
  value       = one(azurerm_monitor_action_group.operations[*].id)
}

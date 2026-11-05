locals {
  reader_role_id = "/subscriptions/${var.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/acdd72a7-3385-48ef-bd42-f606fba81ae7"
}

variable "subscription_id" {
  type = string
  validation {
    condition     = can(regex("^[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$", var.subscription_id))
    error_message = "subscription_id must be a GUID."
  }
}

variable "principal_id" {
  type = string
  validation {
    condition     = can(regex("^[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$", var.principal_id))
    error_message = "principal_id must be the dedicated GitHub OIDC service principal object ID."
  }
}

variable "scopes" {
  type = map(string)
  validation {
    condition = (
      toset(keys(var.scopes)) == toset(["runner", "network", "nat"]) &&
      can(regex("(?i)^/subscriptions/${var.subscription_id}/resourceGroups/[^/]+$", var.scopes["runner"])) &&
      can(regex("(?i)^/subscriptions/${var.subscription_id}/resourceGroups/[^/]+/providers/Microsoft.Network/virtualNetworks/[^/]+$", var.scopes["network"])) &&
      can(regex("(?i)^/subscriptions/${var.subscription_id}/resourceGroups/[^/]+/providers/Microsoft.Network/natGateways/[^/]+$", var.scopes["nat"]))
    )
    error_message = "Exactly the runner RG, management VNet and NAT gateway in subscription_id are required."
  }
}

variable "existing_assignment_ids" {
  type = map(string)
  validation {
    condition = (
      toset(keys(var.existing_assignment_ids)) == toset(keys(var.scopes)) &&
      alltrue([for name, id in var.existing_assignment_ids :
        can(regex("(?i)^${lookup(var.scopes, name, "INVALID")}/providers/Microsoft.Authorization/roleAssignments/[0-9a-f-]{36}$", id))
      ])
    )
    error_message = "Supply the three existing Reader assignment IDs at their exact approved scopes; this root adopts, not bootstraps, access."
  }
}

resource "azurerm_role_assignment" "reader" {
  for_each = var.scopes

  name               = reverse(split("/", var.existing_assignment_ids[each.key]))[0]
  scope              = each.value
  role_definition_id = local.reader_role_id
  principal_id       = var.principal_id
  principal_type     = "ServicePrincipal"

  lifecycle {
    prevent_destroy = true
  }
}

import {
  for_each = var.existing_assignment_ids
  to       = azurerm_role_assignment.reader[each.key]
  id       = each.value
}

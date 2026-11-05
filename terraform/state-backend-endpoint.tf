variable "terraform_state_private_endpoint" {
  type = object({
    id                 = string
    storage_account_id = string
    tags               = optional(map(string), {})
  })
  default     = null
  description = "Opt-in adoption of an existing Lab-specific state backend endpoint. The shared storage account/container remain external. Keep this input on subsequent plans after importing."

  validation {
    condition     = var.terraform_state_private_endpoint == null ? true : can(regex("(?i)^/subscriptions/[0-9a-f-]{36}/resourceGroups/[^/]+/providers/Microsoft.Network/privateEndpoints/[^/]+$", var.terraform_state_private_endpoint.id))
    error_message = "terraform_state_private_endpoint.id must be a full Azure private endpoint resource ID."
  }

  validation {
    condition     = var.terraform_state_private_endpoint == null ? true : can(regex("(?i)^/subscriptions/[0-9a-f-]{36}/resourceGroups/[^/]+/providers/Microsoft.Storage/storageAccounts/[a-z0-9]{3,24}$", var.terraform_state_private_endpoint.storage_account_id))
    error_message = "terraform_state_private_endpoint.storage_account_id must be a full Azure Storage account resource ID."
  }
}

resource "azurerm_private_endpoint" "terraform_state" {
  count = var.terraform_state_private_endpoint == null ? 0 : 1

  name                = split("/", var.terraform_state_private_endpoint.id)[8]
  location            = local.deployment_location
  resource_group_name = azurerm_resource_group.this.name
  subnet_id           = azurerm_subnet.private_endpoints.id
  tags                = var.terraform_state_private_endpoint.tags

  private_service_connection {
    name                           = "tfstate-blob"
    is_manual_connection           = false
    private_connection_resource_id = var.terraform_state_private_endpoint.storage_account_id
    subresource_names              = ["blob"]
  }

  private_dns_zone_group {
    name                 = "blob"
    private_dns_zone_ids = [local.blob_private_dns_zone_id]
  }

  lifecycle {
    prevent_destroy = true
    precondition {
      condition     = startswith(lower(var.terraform_state_private_endpoint.id), lower("/subscriptions/${var.subscription_id}/resourceGroups/${azurerm_resource_group.this.name}/providers/Microsoft.Network/privateEndpoints/"))
      error_message = "The adopted backend endpoint must belong to this platform's subscription and resource group."
    }
  }
}

import {
  for_each = var.terraform_state_private_endpoint == null ? {} : { existing = var.terraform_state_private_endpoint }
  to       = azurerm_private_endpoint.terraform_state[0]
  id       = each.value.id
}

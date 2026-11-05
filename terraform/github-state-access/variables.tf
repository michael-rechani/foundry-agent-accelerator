variable "subscription_id" {
  type = string

  validation {
    condition     = can(regex("^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", var.subscription_id))
    error_message = "subscription_id must be an Azure subscription GUID."
  }
}

variable "github_repository" {
  type    = string
  default = "michael-rechani/foundry-agent-accelerator"

  validation {
    condition     = can(regex("^[A-Za-z0-9-]+/[A-Za-z0-9._-]+$", var.github_repository))
    error_message = "github_repository must be a personal-account repository in owner/name form."
  }
}

variable "reviewer_user_ids" {
  type        = list(number)
  description = "GitHub numeric user IDs allowed to approve the state connectivity workflow."

  validation {
    condition     = length(var.reviewer_user_ids) > 0 && length(var.reviewer_user_ids) <= 6 && alltrue([for id in var.reviewer_user_ids : id > 0 && floor(id) == id])
    error_message = "Set one to six GitHub numeric reviewer user IDs."
  }
}

variable "storage_account_id" {
  type = string

  validation {
    condition     = can(regex("(?i)^/subscriptions/${var.subscription_id}/resourceGroups/[^/]+/providers/Microsoft.Storage/storageAccounts/[a-z0-9]{3,24}$", var.storage_account_id))
    error_message = "storage_account_id must identify an existing Storage account in subscription_id."
  }
}

variable "container_name" {
  type = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$", var.container_name))
    error_message = "container_name must be an Azure blob container name."
  }
}

variable "private_endpoint_ip" {
  type = string

  validation {
    condition = (
      can(regex("^[0-9]{1,3}(\\.[0-9]{1,3}){3}$", var.private_endpoint_ip)) &&
      can(cidrnetmask("${var.private_endpoint_ip}/32")) &&
      (startswith(var.private_endpoint_ip, "10.") || startswith(var.private_endpoint_ip, "192.168.") || can(regex("^172\\.(1[6-9]|2[0-9]|3[01])\\.", var.private_endpoint_ip)))
    )
    error_message = "private_endpoint_ip must be one approved RFC1918 IPv4 address."
  }
}

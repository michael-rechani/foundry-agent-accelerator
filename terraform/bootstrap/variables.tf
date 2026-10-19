variable "subscription_id" {
  type        = string
  description = "Explicit subscription that holds the Terraform state account."

  validation {
    condition     = can(regex("^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", var.subscription_id))
    error_message = "subscription_id must be an Azure subscription GUID."
  }
}

variable "location" {
  type        = string
  description = "Azure region for the state resources."
  default     = "northcentralus"
}

variable "name_prefix" {
  type        = string
  description = "Short lowercase prefix used to build the state storage account name."
  default     = "aifnd"

  validation {
    condition     = can(regex("^[a-z0-9]{2,8}$", var.name_prefix))
    error_message = "name_prefix must be 2 to 8 lowercase letters or digits."
  }
}

variable "resource_group_name" {
  type        = string
  description = "Resource group created for the state account and its private network."
  default     = "rg-tfstate"
}

variable "storage_account_name" {
  type        = string
  description = "Optional explicit state account name. Leave null to derive a stable name from name_prefix and the subscription."
  default     = null

  validation {
    condition     = var.storage_account_name == null || can(regex("^[a-z0-9]{3,24}$", var.storage_account_name))
    error_message = "storage_account_name must be 3 to 24 lowercase letters or digits."
  }
}

variable "container_name" {
  type        = string
  description = "Blob container that holds every root's state file."
  default     = "tfstate"
}

variable "virtual_network_address_space" {
  type        = list(string)
  description = "Address space of the small VNet that hosts the state private endpoint. Must not overlap the platform (10.42.0.0/16) or management (10.43.0.0/16) networks, or any VNet in peered_virtual_network_ids."
  default     = ["10.44.0.0/24"]
}

variable "private_endpoint_subnet_address_prefix" {
  type        = string
  description = "Subnet inside virtual_network_address_space for the state private endpoint."
  default     = "10.44.0.0/27"

  validation {
    condition     = can(cidrnetmask(var.private_endpoint_subnet_address_prefix))
    error_message = "private_endpoint_subnet_address_prefix must be an IPv4 CIDR."
  }
}

variable "peered_virtual_network_ids" {
  type        = map(string)
  description = "Existing VNets (name => resource ID), such as the management VNet or the CI runner network, that must reach the state account. Each gets two-way peering and a link to the blob private DNS zone."
  default     = {}
}

variable "state_contributor_object_ids" {
  type        = map(string)
  description = "Microsoft Entra object IDs (label => object ID) granted Storage Blob Data Contributor on the state container's account, in addition to the identity running this root."
  default     = {}
}

variable "tags" {
  type        = map(string)
  description = "Tags applied to every resource."
  default     = { workload = "terraform-state" }
}

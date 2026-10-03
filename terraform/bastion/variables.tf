variable "subscription_id" {
  type        = string
  description = "Explicit subscription containing the existing management VNet and Bastion."

  validation {
    condition     = can(regex("^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", var.subscription_id))
    error_message = "subscription_id must be an Azure subscription GUID."
  }
}

variable "resource_group_name" {
  type        = string
  description = "Existing resource group containing the management VNet."
}

variable "virtual_network_name" {
  type        = string
  description = "Existing management VNet; this stack does not take ownership of it."
}

variable "bastion_name" {
  type        = string
  description = "Bastion host name. Preserve the existing name when importing a Developer host."
}

variable "subnet_address_prefix" {
  type        = string
  description = "Unused IPv4 range inside the management VNet, /26 or larger, for AzureBastionSubnet."
  default     = "10.43.1.0/26"

  validation {
    condition     = can(cidrnetmask(var.subnet_address_prefix)) && can(regex("/([0-9]|1[0-9]|2[0-6])$", var.subnet_address_prefix))
    error_message = "subnet_address_prefix must be an IPv4 CIDR with a prefix length of at most 26."
  }
}

variable "approve_bastion_public_ip" {
  type        = bool
  description = "Explicit approval for the static public IPv4 address that Standard Bastion requires. Must be true to plan or apply this stack."
  default     = false

  validation {
    condition     = var.approve_bastion_public_ip
    error_message = "Standard Bastion needs a static public IP. Set approve_bastion_public_ip = true only after approving it."
  }
}

variable "tags" {
  type        = map(string)
  description = "Tags for the Bastion host and public IP. Preserve existing tags during adoption."
  default     = {}
}

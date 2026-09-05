variable "subscription_id" {
  type        = string
  description = "Azure subscription ID in which to deploy resources. Set this explicitly to avoid targeting the wrong subscription."

  validation {
    condition     = can(regex("^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", var.subscription_id))
    error_message = "subscription_id must be a valid Azure subscription GUID."
  }
}

variable "base_name" {
  type        = string
  description = "Short lowercase name used as a resource-name suffix."
  default     = "aifnd"

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{1,5}[a-z0-9]$", var.base_name))
    error_message = "base_name must be 3-7 lowercase letters, numbers, or hyphens and must start and end with an alphanumeric character."
  }
}

variable "environment" {
  type        = string
  description = "Deployment environment included in names and tags."
  default     = "dev"

  validation {
    condition     = contains(["dev", "test", "stage", "prod"], var.environment)
    error_message = "environment must be one of dev, test, stage, or prod."
  }
}

variable "location" {
  type        = string
  description = "Optional Azure region override. When null, the first entry in region_preferences is used."
  default     = null
  nullable    = true

  validation {
    condition     = var.location == null || contains(["northcentralus", "westus3", "southcentralus", "westus"], var.location)
    error_message = "location must be null or one of the verified regions in region-preferences.tf."
  }
}

variable "cosmosdb_account_name" {
  type        = string
  description = "Optional Cosmos DB account name override for adopting an existing deployment."
  default     = null
  nullable    = true

  validation {
    condition     = var.cosmosdb_account_name == null || can(regex("^[a-z0-9][a-z0-9-]{1,42}[a-z0-9]$", var.cosmosdb_account_name))
    error_message = "cosmosdb_account_name must be null or a 3-44 character lowercase alphanumeric and hyphen name."
  }
}

variable "virtual_network_address_space" {
  type        = list(string)
  description = "Address space for the workload virtual network."
  default     = ["10.42.0.0/16"]
}

variable "private_endpoint_subnet_address_prefixes" {
  type        = list(string)
  description = "Address prefixes for the subnet containing workload private endpoints."
  default     = ["10.42.0.0/24"]
}

variable "agent_subnet_address_prefixes" {
  type        = list(string)
  description = "Address prefixes for the delegated hosted Agent Service subnet."
  default     = ["10.42.1.0/24"]
}

variable "enable_jumpbox" {
  type        = bool
  description = "Creates a private Windows jumpbox for administering private Foundry resources."
  default     = true
}

variable "jumpbox_subnet_address_prefixes" {
  type        = list(string)
  description = "Address prefixes for the private jumpbox subnet."
  default     = ["10.43.0.0/24"]
}

variable "jumpbox_location" {
  type        = string
  description = "Azure region for the jumpbox management VNet. This can differ from the workload region when VM capacity is unavailable."
  default     = "westus"

  validation {
    condition     = contains(["westus", "westus3", "southcentralus", "northcentralus"], var.jumpbox_location)
    error_message = "jumpbox_location must be one of the verified non-East-US regions."
  }
}

variable "jumpbox_virtual_network_address_space" {
  type        = list(string)
  description = "Address space for the jumpbox management virtual network."
  default     = ["10.43.0.0/16"]
}

variable "jumpbox_admin_username" {
  type        = string
  description = "Local administrator username for the Windows jumpbox."
  default     = "azureadmin"

  validation {
    condition     = can(regex("^[A-Za-z][A-Za-z0-9._-]{0,19}$", var.jumpbox_admin_username))
    error_message = "jumpbox_admin_username must start with a letter and contain at most 20 letters, numbers, periods, underscores, or hyphens."
  }
}

variable "jumpbox_vm_size" {
  type        = string
  description = "Azure VM size for the Windows jumpbox."
  default     = "Standard_B2s"
}

variable "enable_api_management" {
  type        = bool
  description = "Creates a Standard v2 API Management gateway for governed client access to agent APIs."
  default     = false
}

variable "api_management_location" {
  type        = string
  description = "Azure region for API Management and its virtual network integration subnet."
  default     = "westus"

  validation {
    condition     = contains(["westus", "westus3", "southcentralus", "northcentralus"], var.api_management_location)
    error_message = "api_management_location must be one of the verified non-East-US regions."
  }
}

variable "api_management_subnet_address_prefixes" {
  type        = list(string)
  description = "Address prefixes for the dedicated API Management virtual network integration subnet."
  default     = ["10.43.1.0/24"]
}

variable "api_management_publisher_email" {
  type        = string
  description = "Publisher email, required only when API Management is enabled."
  default     = null

  validation {
    condition     = var.api_management_publisher_email == null ? !var.enable_api_management : can(regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$", var.api_management_publisher_email))
    error_message = "api_management_publisher_email must be a valid email address when supplied and is required when API Management is enabled."
  }
}

variable "api_management_publisher_name" {
  type        = string
  description = "Name shown as the API Management service publisher."
  default     = "AI Foundry Platform"
}

check "api_management_management_network" {
  assert {
    condition     = !var.enable_api_management || (var.enable_jumpbox && var.api_management_location == var.jumpbox_location)
    error_message = "API Management requires the management VNet; enable_jumpbox must be true and api_management_location must equal jumpbox_location."
  }
}

variable "review_api" {
  type = object({
    audience                  = string
    allowed_caller_object_ids = set(string)
    allowed_client_app_ids    = set(string)
    agent_name                = optional(string, "review-coordinator-agent")
  })
  description = "Opt-in coordinator API authorization. Use a dedicated Entra API audience and explicit principal and client application allowlists. Null leaves the API unpublished."
  default     = null

  validation {
    condition     = var.review_api == null ? true : var.enable_api_management
    error_message = "review_api requires enable_api_management = true."
  }

  validation {
    condition     = var.review_api == null ? true : can(regex("^[A-Za-z_][A-Za-z0-9_-]{0,63}$", var.review_api.agent_name))
    error_message = "review_api requires a valid named agent, not a URL or path."
  }

  validation {
    condition = var.review_api == null ? true : (
      can(regex("^(api://)?[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", var.review_api.audience)) &&
      length(var.review_api.allowed_caller_object_ids) > 0 &&
      length(var.review_api.allowed_client_app_ids) > 0 &&
      alltrue([for id in setunion(var.review_api.allowed_caller_object_ids, var.review_api.allowed_client_app_ids) : can(regex("^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", id))])
    )
    error_message = "review_api requires a GUID or api://GUID audience and nonempty GUID-only caller object ID and client application ID allowlists."
  }
}

variable "model_deployment" {
  type = object({
    deployment_name = string
    format          = string
    name            = string
    version         = string
    sku_name        = string
    capacity        = number
  })
  description = "Foundry model deployment. Confirm regional availability and quota before applying."
  default = {
    deployment_name = "gpt-4.1"
    format          = "OpenAI"
    name            = "gpt-4.1"
    version         = "2025-04-14"
    sku_name        = "GlobalStandard"
    capacity        = 10
  }

  validation {
    condition     = var.model_deployment.capacity > 0
    error_message = "Model capacity must be greater than zero."
  }
}

variable "enable_agent_service" {
  type        = bool
  description = "Creates the Agent Service capability host and its development supporting resources."
  default     = true
}

variable "tags" {
  type        = map(string)
  description = "Additional tags to merge with the required workload tags."
  default     = {}
}


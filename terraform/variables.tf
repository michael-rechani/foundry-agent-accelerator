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
  description = "Azure region that supports Foundry, the selected model, and hosted agents."
  default     = "eastus2"
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


variable "foundry_account_id" {
  type        = string
  description = "Resource ID of the Foundry account that owns the deployment."
}

variable "primary_deployment_name" {
  type        = string
  description = "Existing primary model deployment name."
}

variable "additional_model_deployment_names" {
  type        = list(string)
  description = "Existing additional model deployment names."
}

variable "model_router_deployment" {
  type = object({
    deployment_name = optional(string, "model-router")
    sku_name        = optional(string, "GlobalStandard")
    capacity        = optional(number, 10)
    routing_mode    = optional(string, "balanced")
    models = list(object({
      format  = string
      name    = string
      version = string
    }))
  })
  description = "Optional Model Router deployment with an explicitly approved nonempty model subset."
  default     = null

  validation {
    condition = var.model_router_deployment == null ? true : (
      can(regex("^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$", var.model_router_deployment.deployment_name)) &&
      lower(var.model_router_deployment.deployment_name) != lower(var.primary_deployment_name) &&
      !contains([for name in var.additional_model_deployment_names : lower(name)], lower(var.model_router_deployment.deployment_name))
    )
    error_message = "model_router_deployment.deployment_name must be a valid, case-insensitively unique deployment name, distinct from the primary and additional deployments."
  }

  validation {
    condition = var.model_router_deployment == null ? true : (
      contains(["GlobalStandard", "DataZoneStandard"], var.model_router_deployment.sku_name) &&
      var.model_router_deployment.capacity > 0 &&
      var.model_router_deployment.capacity == floor(var.model_router_deployment.capacity) &&
      contains(["balanced", "cost", "quality"], var.model_router_deployment.routing_mode)
    )
    error_message = "Model Router requires GlobalStandard or DataZoneStandard, a positive whole-number capacity, and a balanced, cost, or quality routing mode."
  }

  validation {
    condition = var.model_router_deployment == null ? true : try(
      length(var.model_router_deployment.models) > 0 &&
      alltrue([
        for model in var.model_router_deployment.models :
        model.format != "" && model.format == trimspace(model.format) &&
        model.name != "" && model.name == trimspace(model.name) &&
        model.version != "" && model.version == trimspace(model.version)
      ]) &&
      length(distinct([
        for model in var.model_router_deployment.models :
        jsonencode([lower(model.format), lower(model.name), lower(model.version)])
      ])) == length(var.model_router_deployment.models),
      false
    )
    error_message = "Model Router needs a nonempty subset of unique models, each with a nonblank format, name, and version without surrounding whitespace."
  }
}

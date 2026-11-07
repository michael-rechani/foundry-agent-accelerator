variable "fixed_models" {
  type = map(object({
    format  = string
    name    = string
    version = string
  }))
  description = "Fixed model deployments, keyed by deployment name."
}

variable "router" {
  type = object({
    deployment_name = string
    models = list(object({
      format  = string
      name    = string
      version = string
    }))
  })
  description = "Configured Router deployment and its restricted model subset, or null."
  default     = null
}

locals {
  without_encrypted_reasoning = toset([
    jsonencode(["OpenAI", "gpt-4.1", "2025-04-14"]),
    jsonencode(["OpenAI", "gpt-4.1-mini", "2025-04-14"]),
  ])
  fixed = {
    for deployment, model in var.fixed_models : deployment => false
    if contains(local.without_encrypted_reasoning, jsonencode([model.format, model.name, model.version]))
  }
  router = var.router == null ? {} : (
    length(var.router.models) > 0 && alltrue([
      for model in var.router.models :
      contains(local.without_encrypted_reasoning, jsonencode([model.format, model.name, model.version]))
    ]) ? { (var.router.deployment_name) = false } : {}
  )
}

output "preview_encrypted_reasoning" {
  description = "Deployments configured to omit encrypted reasoning in stateless previews. Unlisted deployments have no inferred setting."
  value       = merge(local.fixed, local.router)
}

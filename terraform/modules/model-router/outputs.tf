output "model_router_deployment_name" {
  description = "Verified Model Router deployment name, or null when disabled."
  value       = var.model_router_deployment == null ? null : data.azapi_resource.model_router_routing[0].name
}

output "model_deployment_names" {
  description = "Primary deployment first, existing additional deployments next, and verified Model Router last when enabled."
  value = concat(
    [var.primary_deployment_name],
    sort(var.additional_model_deployment_names),
    var.model_router_deployment == null ? [] : [data.azapi_resource.model_router_routing[0].name],
  )
}

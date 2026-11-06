module "model_preview_capabilities" {
  source = "./modules/model-preview-capabilities"

  fixed_models = merge(
    {
      (var.model_deployment.deployment_name) = {
        format  = var.model_deployment.format
        name    = var.model_deployment.name
        version = var.model_deployment.version
      }
    },
    {
      for deployment, model in var.additional_model_deployments : deployment => {
        format  = model.format
        name    = model.name
        version = model.version
      }
    },
  )
  router = var.model_router_deployment == null ? null : {
    deployment_name = var.model_router_deployment.deployment_name
    models          = var.model_router_deployment.models
  }
}

module "model_router" {
  source = "./modules/model-router"

  foundry_account_id                = var.model_router_deployment == null ? null : module.ai_foundry.ai_foundry_id
  primary_deployment_name           = var.model_deployment.deployment_name
  additional_model_deployment_names = keys(var.additional_model_deployments)
  model_router_deployment           = var.model_router_deployment

  depends_on = [module.ai_foundry]
}

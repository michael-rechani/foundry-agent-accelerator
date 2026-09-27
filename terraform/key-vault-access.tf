# Opt-in so the deployer can manage secrets, such as the Lab's operator-key verifier, in the Agent Service Key Vault.
# The key matches the grant that earlier versions created, so existing deployments keep it without replacement.
locals {
  agent_key_vault_role_assignments = {
    for key, assignment in {
      deployer_secrets_officer = {
        principal_id               = coalesce(var.deployment_principal_id, data.azurerm_client_config.current.object_id)
        role_definition_id_or_name = "Key Vault Secrets Officer"
      }
    } : key => assignment if var.deployer_key_vault_secrets_officer
  }
}

locals {
  jumpbox_admin_password = var.enable_jumpbox && var.jumpbox_admin_secret != null ? ephemeral.azurerm_key_vault_secret.jumpbox_admin[0].value : null
}

ephemeral "azurerm_key_vault_secret" "jumpbox_admin" {
  count        = var.enable_jumpbox && var.jumpbox_admin_secret != null ? 1 : 0
  key_vault_id = var.jumpbox_admin_secret.key_vault_id
  name         = var.jumpbox_admin_secret.name
  version      = var.jumpbox_admin_secret.version
}
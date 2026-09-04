provider "azapi" {
  subscription_id = var.subscription_id
}

provider "azurerm" {
  subscription_id     = var.subscription_id
  storage_use_azuread = true

  features {}
}
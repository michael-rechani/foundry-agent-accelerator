terraform {
  required_version = "~> 1.16.4"

  required_providers {
    azapi = {
      source  = "Azure/azapi"
      version = "~> 2.12.0"
    }
  }
}

provider "azapi" {
  subscription_id = var.subscription_id
}

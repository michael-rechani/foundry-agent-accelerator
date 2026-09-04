terraform {
  required_version = "~> 1.16.1"

  required_providers {
    azapi = {
      source  = "Azure/azapi"
      version = "~> 2.12.0"
    }

    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }

}


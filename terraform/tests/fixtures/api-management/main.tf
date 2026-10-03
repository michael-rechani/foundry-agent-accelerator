# Stands in for the Azure/avm-res-apimanagement-service/azurerm registry module in the offline platform tests,
# so they don't depend on its internals or on mock values for its computed attributes.
# Every argument apim.tf passes is declared here, so renaming or dropping one fails the tests,
# and each is echoed in "inputs" so tests can assert on what apim.tf hands to the module.
variable "location" { type = any }
variable "name" { type = any }
variable "publisher_email" { type = any }
variable "publisher_name" { type = any }
variable "resource_group_name" { type = any }
variable "sku_name" { type = any }
variable "diagnostic_settings" { type = any }
variable "enable_telemetry" { type = any }
variable "managed_identities" { type = any }
variable "public_network_access_enabled" { type = any }
variable "tags" { type = any }
variable "virtual_network_subnet_id" { type = any }
variable "virtual_network_type" { type = any }

output "inputs" {
  value = {
    location                      = var.location
    name                          = var.name
    publisher_email               = var.publisher_email
    publisher_name                = var.publisher_name
    resource_group_name           = var.resource_group_name
    sku_name                      = var.sku_name
    diagnostic_settings           = var.diagnostic_settings
    enable_telemetry              = var.enable_telemetry
    managed_identities            = var.managed_identities
    public_network_access_enabled = var.public_network_access_enabled
    tags                          = var.tags
    virtual_network_subnet_id     = var.virtual_network_subnet_id
    virtual_network_type          = var.virtual_network_type
  }
}

output "name" {
  value = var.name
}

output "resource_id" {
  value = "/subscriptions/00000000-0000-0000-0000-000000000003/resourceGroups/rg-platform-test-12345/providers/Microsoft.ApiManagement/service/${var.name}"
}

output "apim_gateway_url" {
  value = "https://${var.name}.azure-api.net"
}

output "resource" {
  value = { identity = [{ principal_id = "00000000-0000-0000-0000-000000000005" }] }
}
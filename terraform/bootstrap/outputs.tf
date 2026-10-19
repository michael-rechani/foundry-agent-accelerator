output "resource_group_name" {
  description = "Resource group that holds the state account."
  value       = azapi_resource.resource_group.name
}

output "storage_account_name" {
  description = "Private state storage account."
  value       = azapi_resource.storage.name
}

output "container_name" {
  description = "Blob container for every root's state."
  value       = azapi_resource.container.name
}

output "virtual_network_id" {
  description = "VNet that hosts the state private endpoint."
  value       = azapi_resource.vnet.id
}

output "blob_private_dns_zone_id" {
  description = "Private DNS zone that resolves the state account. Link any other VNet that runs Terraform to it."
  value       = azapi_resource.dns_zone.id
}

output "backend_hcl" {
  description = "Contents for the ignored backend.hcl of another root. Replace <state-key> with that root's key."
  value       = <<-EOT
    resource_group_name  = "${azapi_resource.resource_group.name}"
    storage_account_name = "${azapi_resource.storage.name}"
    container_name       = "${azapi_resource.container.name}"
    key                  = "<state-key>"
    subscription_id      = "${var.subscription_id}"
    use_azuread_auth     = true
    use_cli              = true
  EOT
}

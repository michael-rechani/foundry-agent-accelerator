output "bastion_id" {
  description = "Resource ID of the dedicated Standard Bastion."
  value       = azapi_resource.bastion.id
}

output "bastion_dns_name" {
  description = "Bastion service DNS name after apply; may be absent during import."
  value       = try(azapi_resource.bastion.output.properties.dnsName, null)
}

output "bastion_sku" {
  description = "Deployed Bastion tier returned by Azure after apply; may be absent during import."
  value       = try(azapi_resource.bastion.output.sku.name, null)
}

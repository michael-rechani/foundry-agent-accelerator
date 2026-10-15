output "resource_group_name" {
  description = "New resource group that holds the runner. Use it in the runbook's az commands."
  value       = azurerm_resource_group.runner.name
}

output "vm_name" {
  description = "Runner VM name."
  value       = azurerm_linux_virtual_machine.runner.name
}

output "vm_id" {
  description = "Resource ID of the runner VM."
  value       = azurerm_linux_virtual_machine.runner.id
}

output "subnet_id" {
  description = "Resource ID of the runner subnet added to the management VNet."
  value       = azapi_resource.subnet.id
}

output "identity_principal_id" {
  description = "Object ID of the VM's system-assigned managed identity."
  value       = azurerm_linux_virtual_machine.runner.identity[0].principal_id
}

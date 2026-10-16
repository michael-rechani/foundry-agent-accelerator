<#
.SYNOPSIS
  Imports the live dev runner resources into the runner stack's Terraform state.

.DESCRIPTION
  The runner was created and then adjusted by hand (the NSG rule
  AllowRegistryPrivateEndpointOutbound). Until its state holds the live resources, an
  apply would try to create duplicates or delete that rule.

  Run this from a machine that can reach the private state account (the jump box),
  after `terraform init -backend-config=backend.hcl`. It only reads Azure, and it
  prints the `terraform import` commands without running them. Add -Apply to run
  them, which writes to the shared state. Resources already in state are skipped.

  Afterwards run `terraform plan -var-file=dev.tfvars` with
  registry_private_endpoint_ips set. The plan must show no changes to the VM and
  must not add a public IP.
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory)] [string] $VarFile,
  [string] $RunnerResourceGroup = 'rg-runner-aifnd-dev',
  [string] $NamePrefixSuffix = 'aifnd-dev',
  [string] $NetworkResourceGroup,
  [string] $VirtualNetworkName,
  [switch] $Apply
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Get-TfvarsValue([string] $Name) {
  $line = Select-String -Path $VarFile -Pattern "^\s*$Name\s*=\s*""([^""]*)""" | Select-Object -First 1
  if (-not $line) { return $null }
  return $line.Matches[0].Groups[1].Value
}

$subscription = Get-TfvarsValue 'subscription_id'
if (-not $NetworkResourceGroup) { $NetworkResourceGroup = Get-TfvarsValue 'resource_group_name' }
if (-not $VirtualNetworkName) { $VirtualNetworkName = Get-TfvarsValue 'virtual_network_name' }
if (-not $subscription -or -not $NetworkResourceGroup -or -not $VirtualNetworkName) {
  throw "Could not read subscription_id, resource_group_name and virtual_network_name from $VarFile."
}

$registryIps = Select-String -Path $VarFile -Pattern '^\s*registry_private_endpoint_ips\s*=\s*\[(.+)\]' | Select-Object -First 1
if (-not $registryIps) {
  throw "Set registry_private_endpoint_ips in $VarFile first. Without it a later apply deletes the live registry NSG rule."
}

$vmName = "vm-runner-$NamePrefixSuffix"
$rgId = "/subscriptions/$subscription/resourceGroups/$RunnerResourceGroup"
$vmId = "$rgId/providers/Microsoft.Compute/virtualMachines/$vmName"

$roleName = "Runner self-deallocate $vmName"
$roleDefs = az role definition list --custom-role-only true --name $roleName --scope $rgId -o json | ConvertFrom-Json
if (@($roleDefs).Count -ne 1) { throw "Expected exactly one custom role named '$roleName'." }
$roleDefId = "/subscriptions/$subscription/providers/Microsoft.Authorization/roleDefinitions/$($roleDefs[0].name)"

$assignments = az role assignment list --scope $vmId --role $roleName -o json | ConvertFrom-Json |
  Where-Object { $_.scope -eq $vmId }
if (@($assignments).Count -ne 1) { throw "Expected exactly one '$roleName' assignment on the VM." }

$targets = [ordered]@{
  'azurerm_resource_group.runner'                              = $rgId
  'azurerm_network_security_group.runner'                      = "$rgId/providers/Microsoft.Network/networkSecurityGroups/nsg-runner-$NamePrefixSuffix"
  'azapi_resource.subnet'                                      = "/subscriptions/$subscription/resourceGroups/$NetworkResourceGroup/providers/Microsoft.Network/virtualNetworks/$VirtualNetworkName/subnets/snet-runner"
  'azurerm_network_interface.runner'                           = "$rgId/providers/Microsoft.Network/networkInterfaces/nic-runner-$NamePrefixSuffix"
  'azurerm_linux_virtual_machine.runner'                       = $vmId
  'azurerm_role_definition.self_deallocate'                    = "$roleDefId|$rgId"
  'azurerm_role_assignment.self_deallocate'                    = $assignments[0].id
  'azurerm_dev_test_global_vm_shutdown_schedule.runner[0]'     = "$rgId/providers/Microsoft.DevTestLab/schedules/shutdown-computevm-$vmName"
}

$inState = @(terraform state list 2>$null)

foreach ($address in $targets.Keys) {
  if ($inState -contains $address) {
    Write-Host "skip   $address (already in state)"
    continue
  }
  $id = $targets[$address]
  if ($Apply) {
    Write-Host "import $address"
    terraform import "-var-file=$VarFile" $address $id
    if ($LASTEXITCODE -ne 0) { throw "Import failed for $address." }
  }
  else {
    Write-Host "would import $address"
    Write-Host "  <- $id"
  }
}

if (-not $Apply) {
  Write-Host "`nDry run only. Re-run with -Apply to write these to the state."
}

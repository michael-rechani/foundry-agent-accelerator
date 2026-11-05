<#
.SYNOPSIS
  Imports the live dev runner resources into the runner stack's Terraform state.

.DESCRIPTION
  The existing dev runner already has state. This legacy helper is only for a
  separately approved adoption of resources proven absent from that state. It
  refuses unreadable, empty or mismatched runner state. Run it from
  terraform/runner after `terraform init -backend-config=backend.hcl`.

  The default is read-only and reports resource IDs. -Apply writes state and
  requires approval for the specific imports. The normal state writer is a
  protected GitHub job on the private runner; this helper is not wired into
  that workflow. Any non-GitHub writer requires a separately approved and
  documented maintenance exception.

  Supply registry_private_endpoint_ips as a nonempty one-line list. A nonempty
  list alone does not establish that it preserves every existing rule. Review a
  full plan and all existing private endpoint inputs before any apply.
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
  $line = Select-String -LiteralPath $VarFile -CaseSensitive -Pattern "^\s*$Name\s*=\s*""([^""]*)""" | Select-Object -First 1
  if (-not $line) { return $null }
  return $line.Matches[0].Groups[1].Value
}

function Get-ExistingRunnerIds([string] $GroupId, [string] $VmId) {
  $rawState = @(terraform show -json 2>$null)
  if ($LASTEXITCODE -ne 0) { throw 'Could not read the existing runner state; refusing imports.' }
  try {
    $state = ConvertFrom-Json -InputObject ($rawState -join "`n") -ErrorAction Stop
  }
  catch {
    throw 'Could not parse the existing runner state; refusing imports.'
  }
  if ($null -eq $state -or $null -eq $state.PSObject.Properties['format_version'] -or
      $state.format_version -notmatch '^1\.[0-9]+$' -or
      $null -eq $state.PSObject.Properties['values'] -or $null -eq $state.values -or
      $null -eq $state.values.PSObject.Properties['root_module'] -or $null -eq $state.values.root_module -or
      $null -eq $state.values.root_module.PSObject.Properties['resources']) {
    throw 'The existing runner state is empty or unsupported; refusing imports.'
  }

  $ids = [Collections.Generic.Dictionary[string, string]]::new([StringComparer]::Ordinal)
  foreach ($resource in @($state.values.root_module.resources)) {
    if ($null -eq $resource -or $null -eq $resource.PSObject.Properties['address'] -or
        $null -eq $resource.PSObject.Properties['mode'] -or [string]::IsNullOrWhiteSpace($resource.address)) {
      throw 'The existing runner state has invalid resources; refusing imports.'
    }
    if ($resource.mode -ne 'managed') { continue }
    if ($ids.ContainsKey($resource.address)) {
      throw 'The existing runner state has duplicate resource addresses; refusing imports.'
    }
    $id = $null
    if ($null -ne $resource.PSObject.Properties['values'] -and $null -ne $resource.values -and
        $null -ne $resource.values.PSObject.Properties['id']) {
      $id = $resource.values.id
    }
    $ids.Add($resource.address, $id)
  }
  $expected = @{
    'azurerm_resource_group.runner' = $GroupId
    'azurerm_linux_virtual_machine.runner' = $VmId
  }
  foreach ($entry in $expected.GetEnumerator()) {
    if (-not $ids.ContainsKey($entry.Key) -or $ids[$entry.Key] -ine $entry.Value) {
      throw 'The existing runner state does not match the selected runner; refusing imports.'
    }
  }
  return ,$ids
}

$subscription = Get-TfvarsValue 'subscription_id'
if (-not $NetworkResourceGroup) { $NetworkResourceGroup = Get-TfvarsValue 'resource_group_name' }
if (-not $VirtualNetworkName) { $VirtualNetworkName = Get-TfvarsValue 'virtual_network_name' }
if (-not $subscription -or -not $NetworkResourceGroup -or -not $VirtualNetworkName) {
  throw "Could not read subscription_id, resource_group_name and virtual_network_name from $VarFile."
}

$registryLines = @(Select-String -LiteralPath $VarFile -CaseSensitive -Pattern '^\s*registry_private_endpoint_ips\s*=')
$registryPattern = '^\s*registry_private_endpoint_ips\s*=\s*\[\s*(?<ips>"[^"\r\n]+"\s*(?:,\s*"[^"\r\n]+"\s*)*,?)\]\s*(?:(?:#|//).*)?$'
$registryMatch = if ($registryLines.Count -eq 1) { [regex]::Match($registryLines[0].Line, $registryPattern) } else { $null }
if ($null -eq $registryMatch -or -not $registryMatch.Success) {
  throw "Set registry_private_endpoint_ips in $VarFile to one nonempty, single-line list of IPv4 addresses."
}
foreach ($token in [regex]::Matches($registryMatch.Groups['ips'].Value, '"([^"]+)"')) {
  $address = $token.Groups[1].Value
  $parsed = $null
  if ($address -notmatch '^[0-9]{1,3}(\.[0-9]{1,3}){3}$' -or
      -not [Net.IPAddress]::TryParse($address, [ref] $parsed) -or
      $parsed.AddressFamily -ne [Net.Sockets.AddressFamily]::InterNetwork) {
    throw "registry_private_endpoint_ips in $VarFile must contain only IPv4 addresses."
  }
}

$vmName = "vm-runner-$NamePrefixSuffix"
$rgId = "/subscriptions/$subscription/resourceGroups/$RunnerResourceGroup"
$vmId = "$rgId/providers/Microsoft.Compute/virtualMachines/$vmName"
$inState = Get-ExistingRunnerIds $rgId $vmId

$roleName = "Runner self-deallocate $vmName"
$roleDefinitionJson = @(az role definition list --custom-role-only true --name $roleName --scope $rgId -o json 2>$null)
if ($LASTEXITCODE -ne 0) { throw 'Could not read the runner self-deallocation role definition.' }
try {
  $decoded = ConvertFrom-Json -InputObject ($roleDefinitionJson -join "`n") -ErrorAction Stop
  $roleDefs = @($decoded)
}
catch {
  throw 'Could not parse the runner self-deallocation role definition.'
}
if ($roleDefs.Count -ne 1 -or $null -eq $roleDefs[0] -or $null -eq $roleDefs[0].PSObject.Properties['name'] -or
    $null -eq $roleDefs[0].PSObject.Properties['id']) {
  throw "Expected exactly one custom role named '$roleName'."
}
$roleGuid = [guid]::Empty
if (-not [guid]::TryParse([string] $roleDefs[0].name, [ref] $roleGuid)) {
  throw 'The runner self-deallocation role definition has an invalid ID.'
}
$roleDefId = "/subscriptions/$subscription/providers/Microsoft.Authorization/roleDefinitions/$roleGuid"
if ($roleDefs[0].id -ine $roleDefId) {
  throw 'The runner self-deallocation role definition has an unexpected scope.'
}

$roleAssignmentJson = @(az role assignment list --scope $vmId --role "$roleGuid" -o json 2>$null)
if ($LASTEXITCODE -ne 0) { throw 'Could not read the runner self-deallocation role assignment.' }
try {
  $decoded = ConvertFrom-Json -InputObject ($roleAssignmentJson -join "`n") -ErrorAction Stop
  $assignments = @(
    $decoded | Where-Object { $null -ne $_ -and $null -ne $_.PSObject.Properties['scope'] -and $_.scope -ieq $vmId }
  )
}
catch {
  throw 'Could not parse the runner self-deallocation role assignment.'
}
if ($assignments.Count -ne 1 -or $null -eq $assignments[0].PSObject.Properties['id'] -or
    $null -eq $assignments[0].PSObject.Properties['roleDefinitionId'] -or
    $assignments[0].roleDefinitionId -ine $roleDefId -or
    $assignments[0].id -notmatch "^$([regex]::Escape($vmId))/providers/Microsoft\.Authorization/roleAssignments/[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$") {
  throw "Expected exactly one '$roleName' role assignment on the VM."
}

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

foreach ($address in $targets.Keys) {
  $acceptableIds = @($targets[$address])
  if ($address -ceq 'azurerm_role_definition.self_deallocate') {
    $acceptableIds += $roleDefId
  }
  if ($inState.ContainsKey($address) -and $inState[$address] -notin $acceptableIds) {
    throw 'An existing runner state resource does not match its expected ID; refusing imports.'
  }
  foreach ($existing in $inState.GetEnumerator()) {
    if ($existing.Key -cne $address -and $existing.Value -in $acceptableIds) {
      throw 'The existing runner state already owns an import target at another address; refusing imports.'
    }
  }
}

foreach ($address in $targets.Keys) {
  if ($inState.ContainsKey($address)) {
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

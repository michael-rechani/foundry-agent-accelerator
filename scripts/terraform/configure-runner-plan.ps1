<#
.SYNOPSIS
Configure explicitly approved read-only runner planning, without accessing state.
.DESCRIPTION
Reads existing Azure metadata, creates only three Reader assignments if absent,
and saves bootstrap inputs in the reviewed terraform-state GitHub environment.
It never starts a VM, opens networking, or writes Terraform state.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][guid]$SubscriptionId,
    [Parameter(Mandatory)][guid]$PrincipalId,
    [Parameter(Mandatory)][string]$RunnerResourceGroup,
    [Parameter(Mandatory)][string]$RunnerName,
    [Parameter(Mandatory)][string]$NetworkResourceGroup,
    [Parameter(Mandatory)][string]$VirtualNetworkName,
    [Parameter(Mandatory)][string]$NatGatewayName,
    [switch]$ApproveReaderGrants
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if (-not $ApproveReaderGrants) { throw 'Explicit -ApproveReaderGrants approval is required.' }
$repository = 'michael-rechani/foundry-agent-accelerator'
$environment = 'terraform-state'
$readerRole = "/subscriptions/$SubscriptionId/providers/Microsoft.Authorization/roleDefinitions/acdd72a7-3385-48ef-bd42-f606fba81ae7"

function Read-AzJson([string[]]$Arguments) {
    $result = & az @Arguments --subscription $SubscriptionId --output json --only-show-errors
    if ($LASTEXITCODE -ne 0) { throw "Azure management operation failed: $($Arguments[0..1] -join ' ')." }
    return ($result -join "`n" | ConvertFrom-Json -AsHashtable)
}

$variables = & gh api "repos/$repository/environments/$environment/variables" --paginate
if ($LASTEXITCODE -ne 0) { throw 'Cannot read the existing reviewed environment.' }
$environmentVariables = @{}
($variables -join "`n" | ConvertFrom-Json -AsHashtable).variables | ForEach-Object {
    $environmentVariables[$_.name] = $_.value
}
if ($environmentVariables.AZURE_SUBSCRIPTION_ID -ne "$SubscriptionId") { throw 'Environment subscription does not match.' }
$principal = & az ad sp show --id $PrincipalId --query '{appId:appId}' --output json --only-show-errors
if ($LASTEXITCODE -ne 0) { throw 'Cannot verify the dedicated service principal.' }
if (($principal -join "`n" | ConvertFrom-Json).appId -ne $environmentVariables.AZURE_CLIENT_ID) {
    throw 'The principal does not match the existing GitHub OIDC identity.'
}

$vm = Read-AzJson -Arguments @('vm', 'show', '-g', $RunnerResourceGroup, '-n', $RunnerName)
$vnet = Read-AzJson -Arguments @('network', 'vnet', 'show', '-g', $NetworkResourceGroup, '-n', $VirtualNetworkName)
$nat = Read-AzJson -Arguments @('network', 'nat', 'gateway', 'show', '-g', $NetworkResourceGroup, '-n', $NatGatewayName)
$subnet = Read-AzJson -Arguments @('network', 'vnet', 'subnet', 'show', '-g', $NetworkResourceGroup, '--vnet-name', $VirtualNetworkName, '-n', 'snet-runner')
$runnerGroup = Read-AzJson -Arguments @('group', 'show', '-n', $RunnerResourceGroup)
if ($vm.name -notmatch '^vm-runner-([a-z0-9-]+)-(dev)$') { throw 'Only the existing dev runner is supported.' }
$baseName, $deploymentEnvironment = $Matches[1], $Matches[2]
$nsg = Read-AzJson -Arguments @('network', 'nsg', 'show', '-g', $RunnerResourceGroup, '-n', "nsg-runner-$baseName-$deploymentEnvironment")
$schedule = Read-AzJson -Arguments @('resource', 'show', '--ids', "$($runnerGroup.id)/providers/Microsoft.DevTestLab/schedules/shutdown-computevm-$RunnerName", '--api-version', '2018-09-15')
if ($subnet.natGateway.id -ine $nat.id -or $subnet.networkSecurityGroup.id -ine $nsg.id) {
    throw 'The subnet must already use the reviewed management NAT and runner NSG.'
}
if ($schedule.properties.status -ne 'Enabled' -or $schedule.properties.notificationSettings.status -ne 'Disabled') {
    throw 'Unexpected shutdown configuration; review it separately.'
}

function Read-EndpointAddresses([string]$Name, [int]$Priority) {
    $rules = @($nsg.securityRules | Where-Object name -eq $Name)
    if ($rules.Count -ne 1) { throw "Expected one existing $Name rule." }
    $rule = $rules[0]
    if ($rule.direction -ne 'Outbound' -or $rule.access -ne 'Allow' -or $rule.protocol -ne 'Tcp' -or
        $rule.priority -ne $Priority -or $rule.destinationPortRange -ne '443' -or
        $rule.sourceAddressPrefix -ne '*' -or $rule.sourcePortRange -ne '*') {
        throw "The existing $Name rule is not the reviewed HTTPS exception."
    }
    $addresses = @($rule.destinationAddressPrefixes)
    if ($rule.destinationAddressPrefix) { $addresses += $rule.destinationAddressPrefix }
    if ($addresses.Count -eq 0) { throw "$Name has no approved endpoint addresses." }
    foreach ($address in $addresses) {
        if ($address -notmatch '^(10\.|192\.168\.|172\.(1[6-9]|2[0-9]|3[01])\.)' -or
            -not [System.Net.IPAddress]::TryParse($address, [ref]([System.Net.IPAddress]$null))) {
            throw "$Name must contain individual RFC1918 addresses."
        }
    }
    return $addresses | Sort-Object -Unique
}

$backendIps = @(Read-EndpointAddresses 'AllowStateBackendPrivateEndpointOutbound' 140)
if ($backendIps.Count -ne 1 -or $backendIps[0] -ne $environmentVariables.TF_STATE_PRIVATE_ENDPOINT) {
    throw 'Live backend access does not match the reviewed private endpoint.'
}
$keys = @($vm.osProfile.linuxConfiguration.ssh.publicKeys)
if ($keys.Count -ne 1) { throw 'Review the unexpected SSH public-key configuration separately.' }
$patch = $vm.osProfile.linuxConfiguration.patchSettings
$runner = @{
    subscription_id = "$SubscriptionId"
    resource_group_name = $NetworkResourceGroup
    virtual_network_name = $VirtualNetworkName
    nat_gateway_name = $NatGatewayName
    approve_shared_egress = $true
    subnet_address_prefix = $subnet.addressPrefix
    base_name = $baseName
    environment = $deploymentEnvironment
    runner_resource_group_name = $RunnerResourceGroup
    admin_username = $vm.osProfile.adminUsername
    admin_ssh_public_key = $keys[0].keyData.Trim()
    vm_size = $vm.hardwareProfile.vmSize
    os_disk_size_gb = $vm.storageProfile.osDisk.diskSizeGB
    os_disk_storage_account_type = $vm.storageProfile.osDisk.managedDisk.storageAccountType
    patch_mode = $patch.patchMode
    bypass_platform_safety_checks_on_user_schedule = $patch.automaticByPlatformSettings.bypassPlatformSafetyChecksOnUserSchedule
    github_repository = $repository
    auto_shutdown = @{
        time = $schedule.properties.dailyRecurrence.time
        timezone = $schedule.properties.timeZoneId
    }
    registry_private_endpoint_ips = @(Read-EndpointAddresses 'AllowRegistryPrivateEndpointOutbound' 120)
    foundry_private_endpoint_ips = @(Read-EndpointAddresses 'AllowFoundryPrivateEndpointOutbound' 130)
    state_backend_private_endpoint_ips = $backendIps
    tags = $vm.tags
}
$scopes = @{ runner = $runnerGroup.id; network = $vnet.id; nat = $nat.id }
$assignments = @{}
foreach ($key in @('runner', 'network', 'nat')) {
    $existing = @(Read-AzJson -Arguments @('role', 'assignment', 'list', '--scope', $scopes[$key], '--fill-principal-name', 'false'))
    $matching = @($existing | Where-Object {
        $_.principalId -ieq "$PrincipalId" -and
        $_.roleDefinitionId -ieq $readerRole -and
        $_.scope -ieq $scopes[$key]
    })
    if ($matching.Count -gt 1) { throw 'Duplicate Reader grants need review.' }
    if ($matching.Count -eq 1) {
        $assignments[$key] = $matching[0].id
    } else {
        $created = Read-AzJson -Arguments @('role', 'assignment', 'create', '--assignee-object-id', "$PrincipalId", '--assignee-principal-type', 'ServicePrincipal', '--role', $readerRole, '--scope', $scopes[$key])
        $assignments[$key] = $created.id
    }
}
$config = @{
    reader = @{
        subscription_id = "$SubscriptionId"
        principal_id = "$PrincipalId"
        scopes = $scopes
        existing_assignment_ids = $assignments
    }
    runner = $runner
} | ConvertTo-Json -Depth 15 -Compress
$config | & gh variable set TF_RUNNER_PLAN_CONFIG --repo $repository --env $environment
if ($LASTEXITCODE -ne 0) { throw 'Reader grants exist, but saving the reviewed bootstrap configuration failed.' }
Write-Output 'Three scoped Reader grants and protected bootstrap configuration are ready; no Terraform state was accessed.'

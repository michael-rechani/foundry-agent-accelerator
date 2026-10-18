# Lets the "Deploy Lab image" identity start the CI runner VM, and nothing else on it.
# The runner deallocates itself when idle, so the workflow starts it before the build.
# It is safe to run again: every step looks for what already exists first.
#
# The custom role can read the one VM and start it. It can't stop, delete, change or run
# commands on the VM, and it is assigned to that VM only. Run it after
# setup-deploy-identity.ps1, signed in as someone who can create role definitions and
# assignments on the runner's resource group.
param(
    [Parameter(Mandatory)][ValidatePattern('^[0-9a-fA-F-]{36}$')][string]$Subscription,
    [Parameter(Mandatory)][string]$RunnerResourceGroup,
    [Parameter(Mandatory)][string]$RunnerVm,
    [Parameter(Mandatory)][ValidatePattern('^[0-9a-fA-F-]{36}$')][string]$ClientId
)
$ErrorActionPreference = 'Stop'

function Invoke-Az {
    $output = & az @args --only-show-errors
    if ($LASTEXITCODE -ne 0) { throw "az $($args[0..2] -join ' ') failed" }
    $output
}

$roleName = 'Lab runner starter'
$vmId = Invoke-Az vm show --subscription $Subscription --resource-group $RunnerResourceGroup --name $RunnerVm --query id --output tsv
$principalId = Invoke-Az ad sp list --filter "appId eq '$ClientId'" --query "[0].id" --output tsv
if (-not $principalId) { throw "No service principal found for client ID $ClientId." }

$definition = @{
    Name = $roleName
    Description = 'Read and start the one CI runner VM. No stop, delete, change or run-command access.'
    Actions = @(
        'Microsoft.Compute/virtualMachines/read',
        'Microsoft.Compute/virtualMachines/instanceView/read',
        'Microsoft.Compute/virtualMachines/start/action'
    )
    NotActions = @()
    AssignableScopes = @($vmId)
}
$file = Join-Path ([IO.Path]::GetTempPath()) ("role-" + [guid]::NewGuid().ToString('N') + '.json')
try {
    $definition | ConvertTo-Json | Set-Content -LiteralPath $file -Encoding utf8
    $found = Invoke-Az role definition list --subscription $Subscription --name $roleName --scope $vmId --query "[0].name" --output tsv
    if ($found) { Invoke-Az role definition update --subscription $Subscription --role-definition "@$file" | Out-Null }
    else { Invoke-Az role definition create --subscription $Subscription --role-definition "@$file" | Out-Null }
} finally { Remove-Item -LiteralPath $file -Force -ErrorAction SilentlyContinue }

$has = Invoke-Az role assignment list --subscription $Subscription --assignee $principalId --role $roleName --scope $vmId --query "[].id" --output tsv
if (-not $has) {
    Invoke-Az role assignment create --subscription $Subscription --assignee-object-id $principalId --assignee-principal-type ServicePrincipal --role $roleName --scope $vmId | Out-Null
}

Write-Output "The deploy identity can now start $RunnerVm. Set these as variables of the 'lab-deploy' environment in GitHub (not in a file):"
Write-Output "  LAB_RUNNER_VM=$RunnerVm"
Write-Output "  LAB_RUNNER_RESOURCE_GROUP=$RunnerResourceGroup"

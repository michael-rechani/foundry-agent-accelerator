param(
    [Parameter(Mandatory)][string]$SourceDirectory,
    [Parameter(Mandatory)][string]$Subscription,
    [Parameter(Mandatory)][ValidatePattern('^[a-z0-9]{5,50}$')][string]$Registry,
    [Parameter(Mandatory)][ValidatePattern('^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$')][string]$Tag,
    [string]$NetworkResourceGroup = 'rg-aifnd-dev-di2mw',
    [string]$VirtualNetwork = 'vnet-jumpbox-aifnd-dev',
    [string]$Subnet = 'snet-jumpbox',
    [ValidatePattern('^rg-foundry-build-[a-f0-9]{12}$')][string]$ResumeResourceGroup
)
$ErrorActionPreference = 'Stop'
$group = 'rg-foundry-build-' + [guid]::NewGuid().ToString('N').Substring(0, 12)
if ($ResumeResourceGroup) { $group = $ResumeResourceGroup }
$temporary = Join-Path $env:TEMP $group
$assignmentId = $null
$created = $false
$commandSubmitted = $false
$finished = $false
try {
    New-Item -ItemType Directory -Path $temporary | Out-Null
    $network = az network vnet show --subscription $Subscription -g $NetworkResourceGroup -n $VirtualNetwork -o json --only-show-errors | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0) { throw 'Build network unavailable' }
    $registryId = az acr show --subscription $Subscription -n $Registry --query id -o tsv --only-show-errors
    if ($LASTEXITCODE -ne 0) { throw 'Registry unavailable' }
    $tenant = az account show --subscription $Subscription --query tenantId -o tsv --only-show-errors
    if ($LASTEXITCODE -ne 0) { throw 'Tenant unavailable' }
    if ($ResumeResourceGroup) {
        $existing = az group show --subscription $Subscription -n $group -o json --only-show-errors | ConvertFrom-Json
        if ($LASTEXITCODE -ne 0 -or $existing.tags.purpose -ne 'temporary-foundry-build') { throw 'Only tagged temporary build groups can be resumed' }
        $commands = @(az vm run-command list --subscription $Subscription -g $group --vm-name builder -o json --only-show-errors | ConvertFrom-Json)
        if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect existing build commands' }
        foreach ($command in $commands) {
            $status = az vm run-command show --subscription $Subscription --ids $command.id --expand instanceView --query instanceView.executionState -o tsv --only-show-errors
            if ($LASTEXITCODE -ne 0 -or $status -notin @('Succeeded', 'Failed', 'TimedOut', 'Canceled')) { throw 'Existing build command is active or unknown' }
        }
        $created = $true
    } else {
    $publicKey = Join-Path $temporary 'build-key'
    ssh-keygen -q -t ed25519 -N '' -f $publicKey
    if ($LASTEXITCODE -ne 0) { throw 'Ephemeral SSH key creation failed' }
    az group create --subscription $Subscription -n $group -l $network.location --tags purpose=temporary-foundry-build -o none --only-show-errors
    if ($LASTEXITCODE -ne 0) { throw 'Temporary build group creation failed' }
    $created = $true
    $vm = az vm create --subscription $Subscription -g $group -n builder --location $network.location --image Ubuntu2204 --size Standard_B2s --admin-username builduser --ssh-key-values "$publicKey.pub" --public-ip-address '' --nsg '' --subnet "$($network.id)/subnets/$Subnet" --assign-identity --storage-sku Standard_LRS --os-disk-delete-option Delete --nic-delete-option Delete --security-type TrustedLaunch -o json --only-show-errors | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0) { throw 'Temporary private build VM creation failed' }
    }
    $principal = az vm identity show --subscription $Subscription -g $group -n builder --query principalId -o tsv --only-show-errors
    if ($LASTEXITCODE -ne 0) { throw 'Build identity unavailable' }
    $assignment = az role assignment create --subscription $Subscription --assignee-object-id $principal --assignee-principal-type ServicePrincipal --role AcrPush --scope $registryId -o json --only-show-errors | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0) { throw 'Scoped registry push grant failed' }
    $assignmentId = $assignment.id
    $archive = Join-Path $temporary 'source.zip'
    Compress-Archive (Join-Path $SourceDirectory '*') $archive
    $script = (Get-Content (Join-Path $PSScriptRoot 'build-private.sh') -Raw).
        Replace('__REGISTRY__', $Registry).Replace('__TAG__', $Tag).Replace('__TENANT__', $tenant).
        Replace('__HASH__', (Get-FileHash $archive -Algorithm SHA256).Hash.ToLowerInvariant()).
        Replace('__ARCHIVE__', [Convert]::ToBase64String([IO.File]::ReadAllBytes($archive)))
    $scriptPath = Join-Path $temporary 'build.sh'
    [IO.File]::WriteAllText($scriptPath, $script.Replace("`r`n", "`n"), [Text.UTF8Encoding]::new($false))
    $commandSubmitted = $true
    az vm run-command create --subscription $Subscription -g $group --vm-name builder --name build --location $network.location --script "@$scriptPath" --timeout-in-seconds 3600 -o none --only-show-errors
    $result = az vm run-command show --subscription $Subscription -g $group --vm-name builder --name build --expand instanceView --query instanceView -o json --only-show-errors | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0) { throw "Inspect durable build command in $group before cleanup" }
    $finished = $result.executionState -in @('Succeeded', 'Failed', 'TimedOut', 'Canceled')
    if (-not $finished) { throw "Build still active or unknown; inspect durable command in $group" }
    if ($result.exitCode -ne 0 -or $result.output -notmatch 'PRIVATE_BUILD_PUSH_AND_PULL_VERIFIED=True') { throw "Private build failed in $group; $($result.error)" }
    $result.output
} finally {
    if (-not $commandSubmitted -or $finished) {
        if ($assignmentId) {
            az role assignment delete --subscription $Subscription --ids $assignmentId --only-show-errors
            if ($LASTEXITCODE -ne 0) { Write-Warning "Remove build role assignment $assignmentId" }
        }
        if ($created) {
            az group delete --subscription $Subscription -n $group --yes --only-show-errors
            if ($LASTEXITCODE -ne 0) { Write-Warning "Delete temporary build resource group $group" }
        }
    } else { Write-Warning "Temporary build resources retained for recovery: $group; role: $assignmentId" }
    Remove-Item $temporary -Recurse -Force -ErrorAction SilentlyContinue
}
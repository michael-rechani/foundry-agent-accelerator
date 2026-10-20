#Requires -Version 7.0
<#
.SYNOPSIS
One entry point that deploys the Lab and its platform from a subscription and this repo.

.DESCRIPTION
Runs each stage in order: preflight, bootstrap (state backend), platform, lab-foundation
(registry and network only), image (private build), lab, verify. Three stages are opt-in and
never run by default: runner (the private CI VM; needs -ApproveSharedEgress and an SSH public key),
identity (Entra apps, roles and GitHub environments; needs rights to create them and a GitHub
token), and agents (billable). Every Terraform stage shows its plan and applies only after you
type "apply". Nothing is applied without an approved plan, and no stage creates a public resource.

Committed, non-secret inputs live in environments/<Environment>/. They are passed with -var-file
and an ignored overlay adds your subscription.

The state account is private, so after bootstrap run the remaining stages from a host on a
network that can reach it (see terraform/bootstrap/README.md). The first platform run can use
-LocalState from any machine, then migrate its state once a peered host exists.

Missing ignored inputs (backend.hcl, terraform.tfvars, dev.tfvars) are created with defaults.
Existing ones are never overwritten.

.EXAMPLE
./deploy.ps1 -Subscription 00000000-0000-0000-0000-000000000000 -Stage preflight

.EXAMPLE
./deploy.ps1 -Subscription 00000000-0000-0000-0000-000000000000 -PlanOnly
#>
[CmdletBinding()]
param(
    [ValidatePattern('^[0-9a-fA-F-]{36}$')][string]$Subscription,
    [ValidateSet('preflight', 'bootstrap', 'platform', 'runner', 'lab-foundation', 'image', 'lab', 'identity', 'verify', 'agents')]
    [string[]]$Stage = @('preflight', 'bootstrap', 'platform', 'lab-foundation', 'image', 'lab', 'verify'),
    [ValidatePattern('^[a-z0-9]{2,10}$')][string]$Environment = 'dev',
    [ValidatePattern('^[a-z0-9][a-z0-9-]{1,5}[a-z0-9]$')][string]$BaseName = 'aifnd',
    [string]$Location = 'northcentralus',
    [string]$StateResourceGroup = 'rg-tfstate',
    [string]$Tag,
    [string[]]$Agent,
    [string]$ModelQuotaName = 'OpenAI.GlobalStandard.gpt-4.1',
    [int]$ModelCapacity = 10,
    [string]$GitHubRepository,
    [string[]]$RecordingReviewerId,
    [string]$RunnerSshPublicKeyPath,
    [switch]$ApproveSharedEgress,
    [switch]$PlanOnly,
    [switch]$LocalState,
    [switch]$IncludeAgentCall,
    [string]$TerraformCommand = 'terraform'
)
$ErrorActionPreference = 'Stop'
$script:PlanOnlyStopped = $false
$stageOrder = @('preflight', 'bootstrap', 'platform', 'runner', 'lab-foundation', 'image', 'lab', 'identity', 'verify', 'agents')
$bootstrapDir = Join-Path $PSScriptRoot 'terraform/bootstrap'
$platformDir = Join-Path $PSScriptRoot 'terraform'
$runnerDir = Join-Path $PSScriptRoot 'terraform/runner'
$identityDir = Join-Path $PSScriptRoot 'terraform/identity'
$labDir = Join-Path $PSScriptRoot 'workbench/infra'
$environmentDir = Join-Path $PSScriptRoot "environments/$Environment"
$environmentBase = if (Test-Path -LiteralPath (Join-Path $environmentDir 'platform.tfvars')) {
    $line = Select-String -LiteralPath (Join-Path $environmentDir 'platform.tfvars') -Pattern '^\s*base_name\s*=\s*"([^"]+)"' | Select-Object -First 1
    if ($line) { $line.Matches[0].Groups[1].Value }
}
if ($environmentBase -and -not $PSBoundParameters.ContainsKey('BaseName')) { $BaseName = $environmentBase }
$requiredProviders = @(
    'Microsoft.App', 'Microsoft.Authorization', 'Microsoft.CognitiveServices', 'Microsoft.Compute',
    'Microsoft.ContainerRegistry', 'Microsoft.DocumentDB', 'Microsoft.Insights', 'Microsoft.KeyVault',
    'Microsoft.ManagedIdentity', 'Microsoft.Network', 'Microsoft.OperationalInsights', 'Microsoft.Search',
    'Microsoft.Storage'
)

function Get-StageOrder([string[]]$Requested) {
    @($stageOrder | Where-Object { $Requested -contains $_ })
}

function Test-PrivateAddress([string]$Address) {
    $ip = [Net.IPAddress]::Parse($Address)
    if ($ip.AddressFamily -ne [Net.Sockets.AddressFamily]::InterNetwork) { return $false }
    $b = $ip.GetAddressBytes()
    ($b[0] -eq 10) -or ($b[0] -eq 172 -and $b[1] -ge 16 -and $b[1] -le 31) -or ($b[0] -eq 192 -and $b[1] -eq 168)
}

function Test-PrivateHost([string]$HostName) {
    try { $addresses = [Net.Dns]::GetHostAddresses($HostName) } catch { return $false }
    if ($addresses.Count -eq 0) { return $false }
    -not @($addresses | Where-Object { -not (Test-PrivateAddress $_.ToString()) })
}

function Get-RegistryName([string]$SubscriptionId, [string]$Base) {
    $bytes = [Text.Encoding]::UTF8.GetBytes($SubscriptionId.ToLowerInvariant())
    $hash = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($bytes)).ToLowerInvariant().Substring(0, 8)
    'acr' + ($Base -replace '[^a-z0-9]', '') + $hash
}

function Get-TfvarsValue([string]$Path, [string]$Name) {
    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    $match = [regex]::Match((Get-Content -LiteralPath $Path -Raw), "(?m)^\s*$([regex]::Escape($Name))\s*=\s*""([^""]*)""")
    if ($match.Success) { $match.Groups[1].Value } else { $null }
}

function New-BackendHcl([string]$Account, [string]$Key) {
    @"
resource_group_name  = "$StateResourceGroup"
storage_account_name = "$Account"
container_name       = "tfstate"
key                  = "$Key"
subscription_id      = "$Subscription"
use_azuread_auth     = true
use_cli              = true
"@
}

function Get-ImageDigest([string[]]$BuildOutput) {
    $found = @($BuildOutput | ForEach-Object { [regex]::Match("$_", '@(sha256:[a-f0-9]{64})\s*$') } | Where-Object Success)
    if ($found.Count -eq 0) { throw 'The image build did not report a digest.' }
    $found[-1].Groups[1].Value
}

function Write-NewFile([string]$Path, [string]$Content) {
    if (Test-Path -LiteralPath $Path) { return }
    Set-Content -LiteralPath $Path -Value $Content
    Write-Host "Created $(Resolve-Path -Relative $Path). It is ignored by git; review it."
}

function Invoke-Native([string]$Command, [string[]]$Arguments) {
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Command $($Arguments -join ' ') failed with exit code $LASTEXITCODE." }
}

function Get-Native([string]$Command, [string[]]$Arguments) {
    $output = & $Command @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Command $($Arguments -join ' ') failed with exit code $LASTEXITCODE." }
    "$output".Trim()
}

function Confirm-Apply([string]$Label) {
    if ([Console]::IsInputRedirected) { throw "Applying $Label needs an interactive approval. Run it from a terminal." }
    (Read-Host "Review the plan above. Type 'apply' to apply $Label") -ceq 'apply'
}

function Invoke-ReviewedApply([string]$Directory, [string]$Label, [string[]]$PlanArguments = @()) {
    $plan = Join-Path ([IO.Path]::GetTempPath()) ("deploy-$Label-" + [guid]::NewGuid().ToString('N') + '.tfplan')
    try {
        & $TerraformCommand "-chdir=$Directory" plan -input=false -detailed-exitcode "-out=$plan" @PlanArguments
        switch ($LASTEXITCODE) {
            0 { Write-Host "$Label has no changes."; return }
            2 { }
            default { throw "The $Label plan failed." }
        }
        if ($PlanOnly) {
            Write-Host "PlanOnly: stopped before applying $Label. Later stages need it applied first."
            $script:PlanOnlyStopped = $true
            return
        }
        if (-not (Confirm-Apply $Label)) { throw "Applying $Label was not approved." }
        Invoke-Native $TerraformCommand @("-chdir=$Directory", 'apply', '-input=false', $plan)
    } finally {
        Remove-Item -LiteralPath $plan -Force -ErrorAction SilentlyContinue
    }
}

function Get-StateAccount {
    $name = Get-Native 'az' @('storage', 'account', 'list', '--subscription', $Subscription, '--resource-group', $StateResourceGroup, '--query', '[0].name', '--output', 'tsv', '--only-show-errors')
    if (-not $name) { throw "No state account found in $StateResourceGroup. Run -Stage bootstrap first." }
    $name
}

function Initialize-Backend([string]$Directory, [string]$Key) {
    $account = Get-StateAccount
    if (-not (Test-PrivateHost "$account.blob.core.windows.net")) {
        throw "This host can't reach the state account $account privately. Run from a host on a network peered to the state VNet (terraform/bootstrap/README.md)."
    }
    Write-NewFile (Join-Path $Directory 'backend.hcl') (New-BackendHcl $account $Key)
    $arguments = @("-chdir=$Directory", 'init', '-backend-config=backend.hcl')
    $local = Join-Path $Directory 'terraform.tfstate'
    if ((Test-Path -LiteralPath $local) -and (Get-Content -LiteralPath $local -Raw) -match '"resources"\s*:\s*\[\s*\{') {
        Write-Host 'Local state found. Terraform asks before copying it into the private backend; answer yes.'
        $arguments += '-migrate-state'
    } else {
        $arguments += '-input=false'
    }
    Invoke-Native $TerraformCommand $arguments
}

function Initialize-PlatformRoot {
    if ($LocalState) {
        if (Test-Path -LiteralPath (Join-Path $platformDir 'backend.tf')) { throw '-LocalState conflicts with terraform/backend.tf. Remove one.' }
        Invoke-Native $TerraformCommand @("-chdir=$platformDir", 'init', '-input=false')
        return
    }
    Write-NewFile (Join-Path $platformDir 'backend.tf') "terraform {`n  backend `"azurerm`" {}`n}`n"
    Initialize-Backend $platformDir "ai-foundry/$Environment.tfstate"
}

function Get-EnvironmentArgument([string]$FileName) {
    $path = Join-Path $environmentDir $FileName
    if (Test-Path -LiteralPath $path) { @("-var-file=$path") } else { @() }
}

function New-StateObject([string]$Account, [string]$Key) {
    @"
{
  subscription_id      = "$Subscription"
  resource_group_name  = "$StateResourceGroup"
  storage_account_name = "$Account"
  container_name       = "tfstate"
  key                  = "$Key"
}
"@
}

function Get-RunnerSshPublicKey {
    $candidates = if ($RunnerSshPublicKeyPath) { @($RunnerSshPublicKeyPath) } else {
        @('id_ed25519.pub', 'id_rsa.pub') | ForEach-Object { Join-Path (Join-Path $HOME '.ssh') $_ }
    }
    $path = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if (-not $path) { throw 'The runner needs an SSH public key. Pass -RunnerSshPublicKeyPath. Only the public key is used; the VM has no inbound path.' }
    $key = (Get-Content -LiteralPath $path -Raw).Trim()
    if ($key -notmatch '^ssh-(ed25519|rsa) ' -or $key -match 'PRIVATE KEY') { throw "$path is not an SSH public key." }
    $key
}

function Get-GitHubRepositoryName {
    if ($GitHubRepository) { return $GitHubRepository }
    $url = Get-Native 'git' @('-C', $PSScriptRoot, 'remote', 'get-url', 'origin')
    $match = [regex]::Match($url, 'github\.com[:/]([^/]+/[^/]+?)(\.git)?$')
    if (-not $match.Success) { throw 'Could not read the GitHub repository from the origin remote. Pass -GitHubRepository owner/name.' }
    $match.Groups[1].Value
}

function Initialize-GitHubToken {
    if ($env:GITHUB_TOKEN) { return }
    if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { throw 'The identity stage needs GITHUB_TOKEN or the gh CLI signed in with repo admin rights.' }
    $env:GITHUB_TOKEN = Get-Native 'gh' @('auth', 'token')
}

function Test-Preflight([string[]]$Selected) {
    $problems = [Collections.Generic.List[string]]::new()
    foreach ($tool in @('az', $TerraformCommand)) {
        if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) { $problems.Add("$tool is not installed or not on PATH.") }
    }
    if ($problems.Count) { throw ($problems -join "`n") }
    $version = (& $TerraformCommand version -json | ConvertFrom-Json).terraform_version
    if ($version -notmatch '^1\.16\.') { $problems.Add("Terraform $version found; the roots need 1.16.x.") }
    if (@($Selected) -contains 'image' -and -not (Get-Command docker -ErrorAction SilentlyContinue)) { $problems.Add('docker is needed to build the image.') }
    if (@($Selected) -match '^(verify|agents)$' -and -not (Get-Command python -ErrorAction SilentlyContinue)) { $problems.Add('python is needed to verify and publish agents.') }
    if (@($Selected) -contains 'runner' -and -not $ApproveSharedEgress) {
        $problems.Add('The runner shares the jumpbox NAT gateway outbound public IP. Pass -ApproveSharedEgress once you approve that.')
    }
    if (@($Selected) -contains 'identity' -and -not $env:GITHUB_TOKEN -and -not (Get-Command gh -ErrorAction SilentlyContinue)) {
        $problems.Add('The identity stage needs GITHUB_TOKEN or the gh CLI signed in with repo admin rights.')
    }

    $signedIn = & az account show --subscription $Subscription --query id --output tsv --only-show-errors 2>$null
    if ($LASTEXITCODE -ne 0 -or "$signedIn".Trim() -ne $Subscription) {
        $problems.Add("Not signed in to subscription $Subscription. Run az login, then az account set --subscription $Subscription.")
    } else {
        $registered = @(& az provider list --subscription $Subscription --query "[?registrationState=='Registered'].namespace" --output tsv --only-show-errors)
        $missing = @($requiredProviders | Where-Object { $registered -notcontains $_ })
        if ($missing) {
            $problems.Add("Resource providers not registered: $($missing -join ', '). Register with: az provider register --subscription $Subscription --namespace <name>")
        }
        $usage = & az cognitiveservices usage list --location $Location --subscription $Subscription --output json --only-show-errors 2>$null | ConvertFrom-Json
        # Quota names drop the hyphen in some models (gpt4.1 for the gpt-4.1 deployment), so compare without hyphens.
        $wanted = $ModelQuotaName -replace '-', ''
        $entry = $usage | Where-Object { ($_.name.value -replace '-', '') -eq $wanted } | Select-Object -First 1
        if (-not $entry) {
            Write-Warning "No $ModelQuotaName quota entry in $Location. Pick another region or model before applying the platform."
        } elseif (($entry.limit - $entry.currentValue) -lt $ModelCapacity) {
            Write-Warning "$ModelQuotaName has $($entry.limit - $entry.currentValue) units free in $Location; the platform asks for $ModelCapacity."
        } else {
            Write-Host "$ModelQuotaName quota in ${Location}: $($entry.limit - $entry.currentValue) units free."
        }
    }
    if ($problems.Count) { throw ($problems -join "`n") }
    Write-Host 'Preflight passed.'
}

function Invoke-BootstrapStage {
    Write-NewFile (Join-Path $bootstrapDir 'dev.tfvars') "subscription_id = `"$Subscription`"`nlocation        = `"$Location`"`n"
    Invoke-Native $TerraformCommand @("-chdir=$bootstrapDir", 'init', '-input=false')
    Invoke-ReviewedApply $bootstrapDir 'bootstrap' @('-var-file=dev.tfvars')
    if (-not $script:PlanOnlyStopped) {
        Write-Host "State backend ready. Run the remaining stages from a host that can reach it privately (peered_virtual_network_ids in terraform/bootstrap/dev.tfvars), or use -LocalState for the first platform apply."
    }
}

function Invoke-PlatformStage {
    $overlay = "subscription_id = `"$Subscription`"`nlocation        = `"$Location`"`n"
    if (-not (Test-Path -LiteralPath (Join-Path $environmentDir 'platform.tfvars'))) {
        $overlay += "base_name       = `"$BaseName`"`nenvironment     = `"$Environment`"`n"
    }
    Write-NewFile (Join-Path $platformDir 'terraform.tfvars') $overlay
    Initialize-PlatformRoot
    Invoke-ReviewedApply $platformDir 'platform' (Get-EnvironmentArgument 'platform.tfvars')
}

function Invoke-RunnerStage {
    Initialize-PlatformRoot
    $group = Get-Native $TerraformCommand @("-chdir=$platformDir", 'output', '-raw', 'resource_group_name')
    $network = Get-Native $TerraformCommand @("-chdir=$platformDir", 'output', '-raw', 'management_virtual_network_name')
    Write-NewFile (Join-Path $runnerDir 'dev.tfvars') @"
subscription_id      = "$Subscription"
resource_group_name  = "$group"
virtual_network_name = "$network"
nat_gateway_name     = "nat-jumpbox-$BaseName-$Environment"
base_name            = "$BaseName"
environment          = "$Environment"
admin_ssh_public_key = "$(Get-RunnerSshPublicKey)"
"@
    Initialize-Backend $runnerDir "ai-foundry/runner-$Environment.tfstate"
    Invoke-ReviewedApply $runnerDir 'runner' @('-var-file=dev.tfvars', '-var=approve_shared_egress=true')
}

function Invoke-IdentityStage {
    Initialize-GitHubToken
    $account = Get-StateAccount
    $reviewers = if ($RecordingReviewerId) { @($RecordingReviewerId) } else { @(Get-Native 'gh' @('api', 'user', '--jq', '.id')) }
    if ($reviewers -notmatch '^\d+$') { throw '-RecordingReviewerId must be numeric GitHub user IDs.' }
    Write-NewFile (Join-Path $identityDir 'dev.tfvars') @"
subscription_id   = "$Subscription"
github_repository = "$(Get-GitHubRepositoryName)"

lab_state      = $(New-StateObject $account "ai-foundry/workbench-$Environment.tfstate")
runner_state   = $(New-StateObject $account "ai-foundry/runner-$Environment.tfstate")
platform_state = $(New-StateObject $account "ai-foundry/$Environment.tfstate")

recording_reviewer_user_ids = [$($reviewers -join ', ')]
"@
    Initialize-Backend $identityDir "ai-foundry/identity-$Environment.tfstate"
    Invoke-ReviewedApply $identityDir 'identity' @('-var-file=dev.tfvars')
}

function Initialize-LabRoot {
    $account = Get-StateAccount
    $registry = Get-RegistryName $Subscription $BaseName
    Write-NewFile (Join-Path $labDir 'dev.tfvars') @"
subscription_id = "$Subscription"
registry_name   = "$registry"

platform_state = {
  subscription_id      = "$Subscription"
  resource_group_name  = "$StateResourceGroup"
  storage_account_name = "$account"
  container_name       = "tfstate"
  key                  = "ai-foundry/$Environment.tfstate"
}
"@
    Initialize-Backend $labDir "ai-foundry/workbench-$Environment.tfstate"
}

function Test-LabAppExists {
    $resources = & $TerraformCommand "-chdir=$labDir" state list 2>$null
    [bool]($resources -match 'azurerm_container_app\.this')
}

function Invoke-LabFoundationStage {
    Initialize-LabRoot
    if (Test-LabAppExists) {
        Write-Host 'The Lab app already exists. Skipping foundation; bootstrap_only must never run against an existing app.'
        return
    }
    Invoke-ReviewedApply $labDir 'lab-foundation' (@(Get-EnvironmentArgument 'lab.tfvars') + @('-var-file=dev.tfvars', '-var=bootstrap_only=true'))
}

function Invoke-ImageStage {
    $auto = Join-Path $labDir 'image.auto.tfvars'
    $existing = Get-TfvarsValue $auto 'image_digest'
    if ($existing -match '^sha256:[a-f0-9]{64}$' -and -not $Tag) {
        Write-Host "Using the existing image digest in image.auto.tfvars. Pass -Tag to build a new one."
        return
    }
    $registry = Get-TfvarsValue (Join-Path $labDir 'dev.tfvars') 'registry_name'
    if (-not $registry) { $registry = Get-RegistryName $Subscription $BaseName }
    if (-not (Test-PrivateHost "$registry.azurecr.io")) {
        throw "This host can't reach the private registry $registry. Run the image stage from the private runner or jumpbox."
    }
    $releaseTag = if ($Tag) { $Tag } else { 'deploy-' + (Get-Date -Format 'yyyyMMddHHmmss') }
    $build = Join-Path $PSScriptRoot 'workbench/build.ps1'
    $lines = & $build -Private -Subscription $Subscription -Registry $registry -Tag $releaseTag | ForEach-Object { Write-Host $_; $_ }
    $digest = Get-ImageDigest @($lines)
    if (Test-Path -LiteralPath $auto) { Remove-Item -LiteralPath $auto -Force }
    Write-NewFile $auto "image_digest = `"$digest`"`n"
}

function Invoke-LabStage {
    if (-not (Get-TfvarsValue (Join-Path $labDir 'image.auto.tfvars') 'image_digest')) {
        throw 'No image digest. Run -Stage image first.'
    }
    Initialize-LabRoot
    Invoke-ReviewedApply $labDir 'lab' (@(Get-EnvironmentArgument 'lab.tfvars') + @('-var-file=dev.tfvars'))
}

function Invoke-VerifyStage {
    Initialize-LabRoot
    $url = Get-Native $TerraformCommand @("-chdir=$labDir", 'output', '-raw', 'private_url')
    $hostName = ([Uri]$url).Host
    if (-not (Test-PrivateHost $hostName)) { throw "$hostName doesn't resolve to a private address from this host. Run verify from the private network." }
    $arguments = @('-BaseUrl', $url)
    if ($IncludeAgentCall) {
        if (-not (Confirm-Apply 'one billable sample agent request')) { throw 'The billable agent call was not approved.' }
    } else {
        $arguments += '-SkipAgentCall'
    }
    $check = Join-Path $PSScriptRoot 'workbench/test-private.ps1'
    & $check @arguments
}

function Invoke-AgentsStage {
    if (-not $Agent) { throw 'Name the agents to publish with -Agent, specialists before coordinators. Publishing is billable and changes routing.' }
    Initialize-PlatformRoot
    $endpoint = Get-Native $TerraformCommand @("-chdir=$platformDir", 'output', '-raw', 'foundry_project_endpoint')
    $model = Get-Native $TerraformCommand @("-chdir=$platformDir", 'output', '-raw', 'model_deployment_name')
    foreach ($name in $Agent) {
        $sample = Join-Path $PSScriptRoot "hosted-agents/$name"
        if ($name -notmatch '^[a-z0-9-]+$' -or -not (Test-Path -LiteralPath (Join-Path $sample 'deploy.py'))) { throw "No deployable agent named $name under hosted-agents." }
        $venv = Join-Path $sample '.venv'
        Invoke-Native 'python' @('-m', 'venv', $venv)
        $python = Join-Path $venv $(if ($IsWindows) { 'Scripts/python.exe' } else { 'bin/python' })
        Invoke-Native $python @('-m', 'pip', 'install', '--quiet', '-r', (Join-Path $sample 'requirements-deploy.txt'))
        if (-not (Confirm-Apply "publishing $name (creates a billable version and changes routing)")) { throw "Publishing $name was not approved." }
        $env:FOUNDRY_PROJECT_ENDPOINT = $endpoint
        $env:FOUNDRY_MODEL_NAME = $model
        try { Invoke-Native $python @((Join-Path $sample 'deploy.py')) } finally {
            Remove-Item Env:FOUNDRY_PROJECT_ENDPOINT, Env:FOUNDRY_MODEL_NAME -ErrorAction SilentlyContinue
        }
    }
}

# Dot-sourcing loads only the functions, so tests can call them.
if ($MyInvocation.InvocationName -eq '.') { return }
if (-not $Subscription) { throw '-Subscription is required.' }

$selected = Get-StageOrder $Stage
foreach ($name in $selected) {
    if ($script:PlanOnlyStopped) { break }
    Write-Host "`n== $name =="
    switch ($name) {
        'preflight' { Test-Preflight $selected }
        'bootstrap' { Invoke-BootstrapStage }
        'platform' { Invoke-PlatformStage }
        'runner' { Invoke-RunnerStage }
        'lab-foundation' { Invoke-LabFoundationStage }
        'image' { Invoke-ImageStage }
        'lab' { Invoke-LabStage }
        'identity' { Invoke-IdentityStage }
        'verify' { Invoke-VerifyStage }
        'agents' { Invoke-AgentsStage }
    }
}

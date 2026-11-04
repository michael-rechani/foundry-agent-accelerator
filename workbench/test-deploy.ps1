#Requires -Version 7.0
# Checks deploy.ps1's helpers and stage ordering. It never contacts Azure or runs Terraform.
$ErrorActionPreference = 'Stop'
$script = Join-Path $PSScriptRoot '../deploy.ps1'
$subscription = '11111111-2222-3333-4444-555555555555'
. $script -Subscription $subscription

function Assert-Equal($Expected, $Actual, [string]$Name) {
    if ($Expected -ne $Actual) { throw "$Name failed: expected '$Expected', got '$Actual'." }
}

$parse = $null
[void][Management.Automation.Language.Parser]::ParseFile((Resolve-Path $script), [ref]$null, [ref]$parse)
Assert-Equal 0 $parse.Count 'deploy.ps1 parses without errors'

Assert-Equal 'preflight,platform,verify' ((Get-StageOrder @('verify', 'platform', 'preflight')) -join ',') 'stages run in the fixed order'
Assert-Equal 'platform,runner,lab,identity,verify' ((Get-StageOrder @('identity', 'verify', 'lab', 'runner', 'platform')) -join ',') 'runner follows platform and identity follows lab'
Assert-Equal 'agents' ((Get-StageOrder @('agents')) -join ',') 'agents can run alone'
Assert-Equal '' ((Get-StageOrder @()) -join ',') 'no stages selected'

foreach ($address in '10.1.2.3', '172.16.0.1', '172.31.255.1', '192.168.1.1') { Assert-Equal $true (Test-PrivateAddress $address) "$address is private" }
foreach ($address in '8.8.8.8', '172.32.0.1', '100.64.0.1', '20.1.2.3', '::1') { Assert-Equal $false (Test-PrivateAddress $address) "$address is not private" }

$registry = Get-RegistryName $subscription 'aifnd'
Assert-Equal $registry (Get-RegistryName $subscription.ToUpperInvariant() 'aifnd') 'registry name ignores subscription case'
if ($registry -notmatch '^[a-z0-9]{5,50}$') { throw "Registry name '$registry' breaks the Lab's naming rule." }
if ($registry -eq (Get-RegistryName '99999999-2222-3333-4444-555555555555' 'aifnd')) { throw 'Registry names must differ across subscriptions.' }
Assert-Equal 'acraifnd666ff6cc' $registry 'the dev registry name is unchanged, so an adopted dev registry keeps it'
Assert-Equal $registry (Get-RegistryName $subscription 'aifnd' 'dev') 'naming dev explicitly gives the same name'
$testRegistry = Get-RegistryName $subscription 'aifnd' 'test'
if ($testRegistry -eq $registry) { throw 'Dev and test must not generate the same registry name.' }
if ($testRegistry -notmatch '^[a-z0-9]{5,50}$') { throw "Registry name '$testRegistry' breaks the Lab's naming rule." }
Assert-Equal $testRegistry (Get-RegistryName $subscription.ToUpperInvariant() 'aifnd' 'test') 'a non-dev registry name is stable'
if ($testRegistry -eq (Get-RegistryName $subscription 'aifnd' 'stage')) { throw 'Two non-dev environments must not share a registry name.' }

$digest = 'sha256:' + ('a' * 64)
Assert-Equal $digest (Get-ImageDigest @('building', "reg.azurecr.io/workbench@$digest", 'PRIVATE_BUILD_PUSH_AND_PULL_VERIFIED=True')) 'digest is read from the build output'
try { Get-ImageDigest @('no digest here'); throw 'missing digest accepted' } catch { if ($_.Exception.Message -notmatch 'did not report') { throw } }

$hcl = New-BackendHcl 'stexample' 'ai-foundry/dev.tfstate'
foreach ($expected in 'storage_account_name = "stexample"', 'key                  = "ai-foundry/dev.tfstate"', 'use_azuread_auth     = true', "subscription_id      = ""$subscription""") {
    if ($hcl -notmatch [regex]::Escape($expected)) { throw "Backend config lacks: $expected" }
}

$stateObject = New-StateObject 'stexample' 'ai-foundry/runner-dev.tfstate'
foreach ($expected in 'storage_account_name = "stexample"', 'key                  = "ai-foundry/runner-dev.tfstate"', "subscription_id      = ""$subscription""") {
    if ($stateObject -notmatch [regex]::Escape($expected)) { throw "State object lacks: $expected" }
}

$defaultStages = @($Stage)
foreach ($optIn in 'runner', 'identity', 'agents') {
    if ($defaultStages -contains $optIn) { throw "$optIn must be opt-in, not a default stage." }
}
Assert-Equal 1 @(Get-EnvironmentArgument 'lab.tfvars').Count 'the committed dev lab inputs are passed with -var-file'
Assert-Equal 0 @(Get-EnvironmentArgument 'missing.tfvars').Count 'a missing environment file adds no argument'

$temporary = Join-Path ([IO.Path]::GetTempPath()) ('deploy-test-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $temporary | Out-Null
try {
    # The stub keeps test-private.ps1's real parameter block, so a renamed or retyped parameter fails here.
    $checkAst = [Management.Automation.Language.Parser]::ParseFile((Resolve-Path (Join-Path $PSScriptRoot 'test-private.ps1')), [ref]$null, [ref]$null)
    $stub = Join-Path $temporary 'stub-check.ps1'
    Set-Content -LiteralPath $stub -Value ($checkAst.ParamBlock.Extent.Text + "`n[pscustomobject]@{ BaseUrl = `$BaseUrl; PythonCommand = `$PythonCommand; SkipAgentCall = [bool]`$SkipAgentCall } | ConvertTo-Json -Compress")

    $bound = Invoke-PrivateCheck $stub 'https://lab.internal' $true | ConvertFrom-Json
    Assert-Equal 'https://lab.internal' $bound.BaseUrl 'verify passes the URL as BaseUrl'
    Assert-Equal 'python' $bound.PythonCommand 'verify leaves PythonCommand at its default'
    Assert-Equal $true $bound.SkipAgentCall 'verify skips the billable call by default'
    $bound = Invoke-PrivateCheck $stub 'https://lab.internal' $false | ConvertFrom-Json
    Assert-Equal 'https://lab.internal' $bound.BaseUrl 'verify passes the URL as BaseUrl with the agent call'
    Assert-Equal 'python' $bound.PythonCommand 'the agent call does not shift the URL into PythonCommand'
    Assert-Equal $false $bound.SkipAgentCall 'verify runs the agent call when asked'

    $originalPlatformDir = $platformDir
    $originalBootstrapDir = $bootstrapDir
    $platformDir = Join-Path $temporary 'platform'
    $bootstrapDir = Join-Path $temporary 'bootstrap'
    New-Item -ItemType Directory -Path $platformDir, $bootstrapDir | Out-Null
    $zoneId = "/subscriptions/$subscription/resourceGroups/rg-state/providers/Microsoft.Network/privateDnsZones/privatelink.blob.core.windows.net"
    function Get-Native([string]$Command, [string[]]$Arguments) {
        if ($Arguments[1] -eq 'show') {
            Assert-Equal '-json' $Arguments[2] 'platform inspects existing state before choosing DNS ownership'
            return $script:platformState
        }
        Assert-Equal 'output,-raw,blob_private_dns_zone_id' (($Arguments | Select-Object -Skip 1) -join ',') 'platform reads the bootstrap zone output'
        $script:outputReads++
        $script:zoneOutput
    }
    function Initialize-PlatformRoot { $script:platformInitialized = $true }
    function Invoke-ReviewedApply([string]$Directory, [string]$Label, [string[]]$PlanArguments) {
        $script:plannedLabel = $Label
    }
    $script:platformState = '{"format_version":"1.0"}'
    $script:outputReads = 0; $script:zoneOutput = $zoneId; $script:platformInitialized = $false
    Invoke-PlatformStage
    $overlayPath = Join-Path $platformDir 'terraform.tfvars'
    Assert-Equal $zoneId (Get-TfvarsValue $overlayPath 'blob_private_dns_zone_id') 'a new platform reuses the bootstrap zone'
    Assert-Equal $true $script:platformInitialized 'platform initialization follows valid inputs'
    Assert-Equal 'platform' $script:plannedLabel 'the platform still uses the reviewed-plan path'
    $savedInputs = Get-Content -LiteralPath $overlayPath -Raw
    Invoke-PlatformStage
    Assert-Equal 1 $script:outputReads 'existing inputs do not require bootstrap output access'
    Assert-Equal $savedInputs (Get-Content -LiteralPath $overlayPath -Raw) 'existing shared-zone inputs are preserved'
    $BlobPrivateDnsZoneId = $zoneId
    Invoke-PlatformStage
    Assert-Equal $savedInputs (Get-Content -LiteralPath $overlayPath -Raw) 'repeating an explicit matching zone is safe'
    $BlobPrivateDnsZoneId = $zoneId.Replace('rg-state', 'rg-other-state')
    try { Invoke-PlatformStage; throw 'existing inputs accepted automatic migration' } catch {
        if ($_.Exception.Message -notmatch 'never overwritten') { throw }
    }
    Remove-Item -LiteralPath $overlayPath
    $BlobPrivateDnsZoneId = $zoneId
    Invoke-PlatformStage
    Assert-Equal 1 $script:outputReads 'an explicit shared zone does not require bootstrap state access'
    Assert-Equal $zoneId (Get-TfvarsValue $overlayPath 'blob_private_dns_zone_id') 'the explicit zone is wired into fresh inputs'
    Remove-Item -LiteralPath $overlayPath
    $BlobPrivateDnsZoneId = $null; $script:zoneOutput = ''
    $script:plannedLabel = $null
    try { Invoke-PlatformStage; throw 'missing zone accepted' } catch {
        if ($_.Exception.Message -notmatch 'valid blob DNS zone ID') { throw }
    }
    Assert-Equal $false (Test-Path -LiteralPath $overlayPath) 'a missing bootstrap output leaves no partial input file'
    Assert-Equal $null $script:plannedLabel 'a missing bootstrap output cannot reach the plan'
    $script:platformState = '{}'
    try { Invoke-PlatformStage; throw 'unknown state format accepted' } catch {
        if ($_.Exception.Message -notmatch 'platform state format') { throw }
    }
    Assert-Equal $false (Test-Path -LiteralPath $overlayPath) 'unknown state cannot be treated as a fresh deployment'
    $script:platformState = '{"format_version":"1.0","values":{"root_module":{"resources":[]}}}'
    try { Invoke-PlatformStage; throw 'existing state was silently adopted' } catch {
        if ($_.Exception.Message -notmatch 'Restore its reviewed inputs') { throw }
    }
    Assert-Equal $false (Test-Path -LiteralPath $overlayPath) 'existing state without inputs cannot silently change zone ownership'
    $script:platformState = '{"format_version":"1.0"}'
    $script:zoneOutput = $zoneId.Replace($subscription, '99999999-2222-3333-4444-555555555555')
    try { Invoke-PlatformStage; throw 'cross-subscription zone accepted' } catch {
        if ($_.Exception.Message -notmatch 'chosen subscription') { throw }
    }
    Assert-Equal $false (Test-Path -LiteralPath $overlayPath) 'cross-subscription DNS cannot leave an invalid overlay'
    $script:zoneOutput = $zoneId
    Set-Content -LiteralPath $overlayPath -Value "subscription_id = `"$subscription`"`n"
    $legacyInputs = Get-Content -LiteralPath $overlayPath -Raw
    Invoke-PlatformStage
    Assert-Equal $legacyInputs (Get-Content -LiteralPath $overlayPath -Raw) 'legacy inputs are not silently migrated'

    $StateResourceGroup = 'rg-custom-state'
    function Invoke-Native { }
    Invoke-BootstrapStage
    Assert-Equal 'rg-custom-state' (Get-TfvarsValue (Join-Path $bootstrapDir 'dev.tfvars') 'resource_group_name') 'bootstrap honors the chosen state resource group'
    $platformDir = $originalPlatformDir; $bootstrapDir = $originalBootstrapDir

    $entryAst = [Management.Automation.Language.Parser]::ParseFile((Resolve-Path $script), [ref]$null, [ref]$null)
    $dispatch = $entryAst.Find({
            param($node)
            $node -is [Management.Automation.Language.ForEachStatementAst] -and $node.Condition.Extent.Text -eq '$selected'
        }, $false)
    if (-not $dispatch) { throw 'Missing deployment stage dispatcher.' }
    $dispatchBlock = [scriptblock]::Create($dispatch.Extent.Text)
    $originalVerify = ${function:Invoke-VerifyStage}
    function Invoke-PlatformStage { $script:dispatched.Add('platform') }
    function Invoke-ImageStage { $script:dispatched.Add('image') }
    function Invoke-VerifyStage { $script:dispatched.Add('verify') }
    function Invoke-AgentsStage { $script:dispatched.Add('agents') }
    foreach ($nonPlanStage in 'image', 'verify', 'agents') {
        $script:dispatched = [Collections.Generic.List[string]]::new()
        $script:PlanOnlyStopped = $false; $PlanOnly = [switch]$true
        $selected = @('platform', $nonPlanStage)
        . $dispatchBlock
        Assert-Equal 'platform' ($script:dispatched -join ',') "PlanOnly never runs $nonPlanStage, even when earlier plans have no changes"
    }
    $PlanOnly = [switch]$false
    $script:dispatched.Clear()
    $selected = @('platform', 'image')
    . $dispatchBlock
    Assert-Equal 'platform,image' ($script:dispatched -join ',') 'normal deployment still dispatches the image stage'
    Set-Item Function:Invoke-VerifyStage -Value $originalVerify

    # Runs the real verify stage with every external call replaced, to prove how it chooses the check's arguments.
    function Initialize-LabRoot { }
    function Get-Native { 'https://lab.internal' }
    function Test-PrivateHost { $true }
    function Invoke-PrivateCheck([string]$Path, [string]$Url, [bool]$SkipAgentCall) {
        $script:verifyCall = [pscustomobject]@{ Path = $Path; Url = $Url; SkipAgentCall = $SkipAgentCall }
    }
    function Confirm-Apply([string]$Label) { $script:approvalAsked = $Label; $script:approval }
    foreach ($case in @(
            @{ Include = $false; Approve = $false; Asked = $false; Skip = $true; Name = 'default verify' },
            @{ Include = $true; Approve = $true; Asked = $true; Skip = $false; Name = 'approved agent call' })) {
        $script:verifyCall = $null; $script:approvalAsked = $null; $script:approval = $case.Approve
        $IncludeAgentCall = [switch]$case.Include
        Invoke-VerifyStage
        Assert-Equal $case.Skip $script:verifyCall.SkipAgentCall "$($case.Name) sets SkipAgentCall"
        Assert-Equal 'https://lab.internal' $script:verifyCall.Url "$($case.Name) passes the Lab URL"
        Assert-Equal 'test-private.ps1' (Split-Path -Leaf $script:verifyCall.Path) "$($case.Name) runs the private check"
        Assert-Equal $case.Asked ($null -ne $script:approvalAsked) "$($case.Name) asks for approval only for the billable call"
    }
    $script:verifyCall = $null; $script:approval = $false; $IncludeAgentCall = [switch]$true
    try { Invoke-VerifyStage; throw 'an unapproved agent call ran' } catch { if ($_.Exception.Message -notmatch 'not approved') { throw } }
    Assert-Equal $null $script:verifyCall 'a declined agent call never runs the check'
    $IncludeAgentCall = [switch]$false

    $file = Join-Path $temporary 'x.tfvars'
    Set-Content -LiteralPath $file -Value "registry_name = `"abc123`"`n# image = `"no`""
    Assert-Equal 'abc123' (Get-TfvarsValue $file 'registry_name') 'tfvars value is read'
    Assert-Equal $null (Get-TfvarsValue $file 'missing') 'missing tfvars value is null'
    Write-NewFile $file 'overwritten' | Out-Null
    if ((Get-Content -LiteralPath $file -Raw) -match 'overwritten') { throw 'An existing input file was overwritten.' }
} finally {
    Remove-Item -LiteralPath $temporary -Recurse -Force
}

Write-Host 'deploy.ps1 helper checks passed.'

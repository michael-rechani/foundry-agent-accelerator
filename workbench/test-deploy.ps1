#Requires -Version 7.0
# Checks deploy.ps1's helpers and stage ordering. It never contacts Azure or runs Terraform.
param([switch]$PowerShellOnly)

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
try { & { . $script -Subscription $subscription -AgentModel 'invalid model' }; throw 'invalid agent model accepted' } catch {
    if ($_.Exception.Message -notmatch 'AgentModel') { throw }
}
try { & { . $script -Subscription $subscription -CoordinatorProfile '' }; throw 'empty coordinator profile accepted' } catch {
    if ($_.Exception.Message -notmatch 'CoordinatorProfile') { throw }
}
try { & { . $script -Subscription $subscription -Stage agents -CoordinatorProfile 'fictional-profile.json' -LocalState }; throw 'profile with LocalState accepted at entry' } catch {
    if ($_.Exception.Message -notmatch 'cannot be combined with -LocalState') { throw }
}

$script:earlyActivity = [Collections.Generic.List[string]]::new()
foreach ($stages in @(@('bootstrap', 'agents'), @('platform', 'agents'), @('preflight', 'agents'), @('agents', 'agents'), @('verify'))) {
    foreach ($dotSource in $false, $true) {
        try {
            & {
                function az { $script:earlyActivity.Add('az') }
                function terraform { $script:earlyActivity.Add('terraform') }
                function python { $script:earlyActivity.Add('python') }
                function Test-Preflight { $script:earlyActivity.Add('preflight') }
                function Invoke-BootstrapStage { $script:earlyActivity.Add('bootstrap') }
                function Invoke-PlatformStage { $script:earlyActivity.Add('platform') }
                function Invoke-AgentsStage { $script:earlyActivity.Add('agents') }
                function Get-StateAccount { $script:earlyActivity.Add('account') }
                function Confirm-Apply { $script:earlyActivity.Add('approval') }
                if ($dotSource) {
                    . $script -Subscription $subscription -Stage $stages -CoordinatorProfile 'missing-fictional-profile.json'
                } else {
                    & $script -Subscription $subscription -Stage $stages -CoordinatorProfile 'missing-fictional-profile.json'
                }
            }
            throw 'profiled mixed-stage entry accepted'
        } catch {
            if ($_.Exception.Message -notmatch 'requires -Stage agents alone') { throw }
        }
        Assert-Equal 0 $script:earlyActivity.Count 'profiled multi-stage entry rejects before any stage, native command, account lookup or approval'
    }
}
$loaded = & { . $script -Subscription $subscription -Stage AgEnTs -CoordinatorProfile 'fictional-profile.json'; 'loaded' }
Assert-Equal 'loaded' $loaded 'mixed-case single agents stage is accepted when dot-sourcing'

Assert-Equal 'preflight,platform,verify' ((Get-StageOrder @('verify', 'platform', 'preflight')) -join ',') 'stages run in the fixed order'
Assert-Equal 'preflight,bootstrap,platform,agents' ((Get-StageOrder @('agents', 'platform', 'bootstrap', 'preflight')) -join ',') 'unprofiled multi-stage ordering remains unchanged'
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

$routerOutputs = '{"model_router_deployment_name":{"value":"custom-router"},"model_deployment_name":{"value":"gpt-4.1"},"private_output":{"value":"private-sensitive-value","sensitive":true}}'
$fixedOutputs = '{"model_deployment_name":{"value":"gpt-4.1"}}'
$nullRouterOutputs = '{"model_router_deployment_name":{"value":null},"model_deployment_name":{"value":"gpt-4.1"}}'
$selectedModel = Get-AgentModelFromOutputs $routerOutputs
Assert-Equal 'custom-router' $selectedModel.Name 'Router output is the default agent model'
Assert-Equal 'router' $selectedModel.Source 'Router selection identifies its source'
if (($selectedModel | ConvertTo-Json -Compress) -match 'private-sensitive-value') { throw 'Unrelated Terraform output was exposed.' }
foreach ($outputs in $fixedOutputs, $nullRouterOutputs) {
    $selectedModel = Get-AgentModelFromOutputs $outputs
    Assert-Equal 'gpt-4.1' $selectedModel.Name 'missing or null Router falls back to the fixed model'
    Assert-Equal 'fixed' $selectedModel.Source 'fixed-model fallback identifies its source'
}
foreach ($bad in @(
        @{ Json = '{invalid'; Error = 'valid JSON' },
        @{ Json = '[]'; Error = 'JSON object' },
        @{ Json = '{"model_router_deployment_name":{},"model_deployment_name":{"value":"gpt-4.1"}}'; Error = 'must contain a value' },
        @{ Json = '{"model_router_deployment_name":{"value":"invalid model"},"model_deployment_name":{"value":"gpt-4.1"}}'; Error = 'valid model deployment name' },
        @{ Json = '{"model_router_deployment_name":{"value":""},"model_deployment_name":{"value":"gpt-4.1"}}'; Error = 'valid model deployment name' },
        @{ Json = '{"model_deployment_name":{"value":null}}'; Error = 'valid model deployment name' },
        @{ Json = '{}'; Error = 'no primary model deployment output' })) {
    try { Get-AgentModelFromOutputs $bad.Json; throw 'invalid platform outputs were accepted' } catch {
        if ($_.Exception.Message -notmatch $bad.Error) { throw }
    }
}

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

$temporary = Join-Path ([IO.Path]::GetTempPath()) ('deploy-test-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $temporary | Out-Null
$savedCredentialMode = [Environment]::GetEnvironmentVariable('AZURE_TOKEN_CREDENTIALS', 'Process')
$savedClientId = [Environment]::GetEnvironmentVariable('AZURE_CLIENT_ID', 'Process')
$savedTerraformArguments = @{}
foreach ($key in 'TF_CLI_ARGS', 'TF_CLI_ARGS_init', 'TF_CLI_ARGS_plan', 'TF_CLI_ARGS_fictional') {
    $savedTerraformArguments[$key] = [Environment]::GetEnvironmentVariable($key, 'Process')
}
try {
    $stateDir = Join-Path $temporary 'fictional-state'
    New-Item -ItemType Directory -Path $stateDir | Out-Null
    $savedGetStateAccount = ${function:Get-StateAccount}
    $savedTestPrivateHost = ${function:Test-PrivateHost}
    $savedInvokeNative = ${function:Invoke-Native}
    function Get-StateAccount { throw 'Unexpected state account access' }
    $CoordinatorProfile = 'fictional-profile.json'
    $fictionalStates = @('', '{"resources":[]}', '{"outputs":{"fictional":{"value":"test"}},"resources":[]}', '{malformed', '{"resources":[{"type":"fictional"}]}')
    foreach ($state in $fictionalStates) {
        Set-Content -LiteralPath (Join-Path $stateDir 'terraform.tfstate') -Value $state -NoNewline
        try { Initialize-Backend $stateDir 'fictional'; throw 'implicit migration accepted' } catch {
            if ($_.Exception.Message -notmatch 'cannot implicitly migrate') { throw }
        }
    }
    $script:backendCalls = [Collections.Generic.List[object]]::new()
    function Test-PrivateHost { $true }
    function Invoke-Native([string]$Command, [string[]]$Arguments) {
        $script:backendCalls.Add(@($Arguments))
        if ($script:stateAppearsAtInvocation) {
            Set-Content -LiteralPath (Join-Path $stateDir 'terraform.tfstate') -Value '{"resources":[{"type":"fictional"}]}'
        }
    }
    function Get-StateAccount {
        Set-Content -LiteralPath (Join-Path $stateDir 'terraform.tfstate') -Value $script:lateState -NoNewline
        'stfictional'
    }
    foreach ($state in $fictionalStates) {
        Remove-Item -LiteralPath (Join-Path $stateDir 'terraform.tfstate')
        $script:lateState = $state
        try { Initialize-Backend $stateDir 'fictional'; throw 'late implicit migration accepted' } catch {
            if ($_.Exception.Message -notmatch 'cannot implicitly migrate') { throw }
        }
        Assert-Equal 0 $script:backendCalls.Count 'any state file appearing during account lookup prevents Terraform invocation'
    }
    Remove-Item -LiteralPath (Join-Path $stateDir 'terraform.tfstate')
    function Get-StateAccount { 'stfictional' }
    $script:stateAppearsAtInvocation = $true
    Initialize-Backend $stateDir 'fictional'
    Assert-Equal 1 $script:backendCalls.Count 'late state appearance exercises the constructed profiled command'
    Assert-Equal $false ($script:backendCalls[0] -contains '-migrate-state') 'profiled command never requests migration even when state appears after observation'
    Assert-Equal $true ($script:backendCalls[0] -contains '-input=false') 'profiled command remains noninteractive'
    $script:stateAppearsAtInvocation = $false
    Remove-Variable CoordinatorProfile
    $CoordinatorProfile = $null
    Initialize-Backend $stateDir 'fictional'
    Assert-Equal $true ($script:backendCalls[1] -contains '-migrate-state') 'unprofiled local-state migration behavior remains unchanged'
    $CoordinatorProfile = 'fictional-profile.json'
    Remove-Item -LiteralPath (Join-Path $stateDir 'terraform.tfstate')
    function Get-StateAccount {
        $env:TF_CLI_ARGS_init = '-force-copy'
        'stfictional'
    }
    $before = $script:backendCalls.Count
    try { Initialize-Backend $stateDir 'fictional'; throw 'late injected Terraform arguments accepted' } catch {
        if ($_.Exception.Message -notmatch 'TF_CLI_ARGS') { throw }
    } finally { Remove-Item Env:TF_CLI_ARGS_init }
    Assert-Equal $before $script:backendCalls.Count 'injection during account lookup fails before backend init invocation'
    Set-Item Function:Get-StateAccount -Value $savedGetStateAccount
    Set-Item Function:Test-PrivateHost -Value $savedTestPrivateHost
    Set-Item Function:Invoke-Native -Value $savedInvokeNative
    Remove-Variable CoordinatorProfile
    $CoordinatorProfile = $null
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
    function Invoke-ReviewedApply([string]$Directory, [string]$Label, [string[]]$PlanArguments = @()) {
        $script:plannedLabel = $Label
        $script:plannedArguments = @($PlanArguments)
    }
    $script:platformState = '{"format_version":"1.0"}'
    $script:outputReads = 0; $script:zoneOutput = $zoneId; $script:platformInitialized = $false
    Invoke-PlatformStage
    $overlayPath = Join-Path $platformDir 'terraform.tfvars'
    Assert-Equal $zoneId (Get-TfvarsValue $overlayPath 'blob_private_dns_zone_id') 'a new platform reuses the bootstrap zone'
    Assert-Equal 'aifnd' (Get-TfvarsValue $overlayPath 'base_name') 'new platform inputs preserve the default base name'
    Assert-Equal 'dev' (Get-TfvarsValue $overlayPath 'environment') 'new platform inputs preserve the default environment'
    Assert-Equal 0 $script:plannedArguments.Count 'platform uses its ignored inputs without a committed var-file'
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
    Remove-Item -LiteralPath $overlayPath
    $BaseName = 'custom'; $Environment = 'test'
    Invoke-PlatformStage
    Assert-Equal 'custom' (Get-TfvarsValue $overlayPath 'base_name') 'new platform inputs honor the chosen base name'
    Assert-Equal 'test' (Get-TfvarsValue $overlayPath 'environment') 'new platform inputs honor the chosen environment'

    $originalLabDir = $labDir
    $labDir = Join-Path $temporary 'lab'
    New-Item -ItemType Directory -Path $labDir | Out-Null
    function Get-StateAccount { 'stexample' }
    function Initialize-Backend([string]$Directory, [string]$Key) { $script:labStateKey = $Key }
    function Test-LabAppExists { $false }
    Invoke-LabFoundationStage
    Assert-Equal 'lab-foundation' $script:plannedLabel 'foundation still uses the reviewed-plan path'
    Assert-Equal '-var-file=dev.tfvars,-var=bootstrap_only=true' ($script:plannedArguments -join ',') 'foundation uses only the ignored Lab inputs'
    Assert-Equal 'ai-foundry/workbench-test.tfstate' $script:labStateKey 'Lab backend uses the chosen environment'
    $labInputs = Get-Content -LiteralPath (Join-Path $labDir 'dev.tfvars') -Raw
    foreach ($expected in 'platform_state = {', 'resource_group_name  = "rg-custom-state"', 'storage_account_name = "stexample"', 'key                  = "ai-foundry/test.tfstate"') {
        if ($labInputs -notmatch [regex]::Escape($expected)) { throw "Lab platform-state connection lacks: $expected" }
    }
    Set-Content -LiteralPath (Join-Path $labDir 'image.auto.tfvars') -Value "image_digest = `"$digest`"`n"
    Invoke-LabStage
    Assert-Equal 'lab' $script:plannedLabel 'Lab still uses the reviewed-plan path'
    Assert-Equal '-var-file=dev.tfvars' ($script:plannedArguments -join ',') 'Lab uses only its ignored inputs'
    Assert-Equal $labInputs (Get-Content -LiteralPath (Join-Path $labDir 'dev.tfvars') -Raw) 'existing Lab inputs are preserved'
    $labDir = $originalLabDir
    $BaseName = 'aifnd'; $Environment = 'dev'
    $platformDir = $originalPlatformDir; $bootstrapDir = $originalBootstrapDir

    $entryAst = [Management.Automation.Language.Parser]::ParseFile((Resolve-Path $script), [ref]$null, [ref]$null)
    $dispatch = $entryAst.Find({
            param($node)
            $node -is [Management.Automation.Language.ForEachStatementAst] -and $node.Condition.Extent.Text -eq '$selected'
        }, $false)
    if (-not $dispatch) { throw 'Missing deployment stage dispatcher.' }
    $dispatchBlock = [scriptblock]::Create($dispatch.Extent.Text)
    $originalVerify = ${function:Invoke-VerifyStage}
    $originalAgents = ${function:Invoke-AgentsStage}
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
    Set-Item Function:Invoke-AgentsStage -Value $originalAgents

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

    # Publication uses only test doubles; no process, Azure, or Terraform is invoked.
    function Initialize-PlatformRoot { $script:agentPlatformInitializations++ }
    function Get-Native([string]$Command, [string[]]$Arguments) {
        switch (($Arguments | Select-Object -Skip 1) -join ',') {
            'output,-raw,foundry_project_endpoint' { return 'https://foundry-test.services.ai.azure.com/api/projects/project-test' }
            'output,-json' {
                $script:modelOutputReads++
                if ($script:failModelOutput) { throw 'Terraform output failed.' }
                return $script:agentOutputs
            }
            default { throw 'Unexpected Terraform output request.' }
        }
    }
    function Invoke-Native([string]$Command, [string[]]$Arguments) {
        if ($Arguments -contains '--validate-profile') {
            $script:validations++
            Assert-Equal 'python' $Command 'profile validation uses offline system Python before dependencies'
            Assert-Equal 6 $Arguments.Count 'validation forwards profile, expected digest and offline flag'
            Assert-Equal $script:profileFile $Arguments[2] 'validation keeps the literal profile path as one argument'
            Assert-Equal '--profile-sha256' $Arguments[3] 'validation binds an expected digest'
            if ($Arguments[4] -cne (Get-FileHash -LiteralPath $script:profileFile -Algorithm SHA256).Hash.ToLowerInvariant()) {
                throw 'Fictional profile digest mismatch.'
            }
            if ($script:useRealProfileValidation) {
                if ($PowerShellOnly) { throw 'PowerShell-only tests must not execute Python.' }
                $output = & $Command @Arguments 2>&1
                if ($LASTEXITCODE -ne 0) { throw "Real offline profile validation failed with exit code $LASTEXITCODE." }
                return $output
            }
            if ($script:validationError) { throw $script:validationError }
            if ($script:changeCredentialDuringValidation) { $env:AZURE_TOKEN_CREDENTIALS = 'WorkloadIdentityCredential' }
            if ($script:ambiguousTarget) { return @('Valid profile: customer-review-coordinator', 'Valid profile: other-coordinator') }
            $target = if ($script:changeTargetAt -and $script:validations -ge $script:changeTargetAt) { 'changed-coordinator' } else { $script:profileTarget }
            return @("Valid profile: $target", '  inspect_application -> application-review-agent', '  inspect_case -> case-review-agent')
        }
        if ($Arguments[0] -match 'deploy\.py$') {
            $script:publishedModels.Add($env:FOUNDRY_MODEL_NAME)
            $script:publicationCalls.Add([pscustomobject]@{ Command = $Command; Arguments = @($Arguments); Endpoint = $env:FOUNDRY_PROJECT_ENDPOINT })
            if ($script:publicationError) { throw 'Fictional publication failure.' }
            if ($script:changeClientAfterPublication) { $env:AZURE_CLIENT_ID = 'abcdefab-1234-1234-1234-123456789abc' }
        } elseif ($Arguments[0] -eq '-m' -and $Arguments[1] -eq 'venv') {
            $script:venvCalls++
        } elseif ($Arguments[0] -eq '-m' -and $Arguments[1] -eq 'pip') {
            $script:pipCalls++
        }
    }
    $Agent = @('basic-responses-agent')
    $script:approval = $true
    $script:modelOutputReads = 0
    $script:failModelOutput = $false
    $script:publishedModels = [Collections.Generic.List[string]]::new()
    $script:publicationCalls = [Collections.Generic.List[object]]::new()
    $script:venvCalls = 0; $script:pipCalls = 0
    $script:agentOutputs = $routerOutputs
    $stageOutput = (Invoke-AgentsStage 6>&1 | Out-String)
    if ($stageOutput -match 'private-sensitive-value') { throw 'Agent publication logged a sensitive Terraform output.' }
    Assert-Equal 'custom-router' $script:publishedModels[-1] 'agents stage publishes with the Router output'
    Assert-Equal 1 $script:modelOutputReads 'agents stage reads model outputs once'
    $script:agentOutputs = $fixedOutputs
    Invoke-AgentsStage
    Assert-Equal 'gpt-4.1' $script:publishedModels[-1] 'agents stage uses the fixed fallback for older state'
    $script:failModelOutput = $true
    $before = $script:publishedModels.Count
    try { Invoke-AgentsStage; throw 'failed Terraform output was ignored' } catch {
        if ($_.Exception.Message -notmatch 'Terraform output failed') { throw }
    }
    Assert-Equal $before $script:publishedModels.Count 'a Terraform output failure cannot publish an agent'
    $script:failModelOutput = $false
    $script:approval = $false
    try { Invoke-AgentsStage; throw 'unapproved publication ran' } catch {
        if ($_.Exception.Message -notmatch 'not approved') { throw }
    }
    Assert-Equal $before $script:publishedModels.Count 'a declined publication never starts'
    $script:approval = $true
    $AgentModel = 'explicit-fixed'
    $script:modelOutputReads = 0
    Invoke-AgentsStage
    Assert-Equal 'explicit-fixed' $script:publishedModels[-1] 'explicit agent model overrides the Router'
    Assert-Equal 0 $script:modelOutputReads 'explicit agent model does not read all platform outputs'

    Remove-Variable AgentModel
    $AgentModel = $null
    $Stage = @('agents')
    $script:agentOutputs = $routerOutputs
    $script:profileFile = Join-Path $temporary 'fictional profile; literal.json'
    $fictionalProfile = @{
        schema_version = 1; name = 'customer-review-coordinator'
        description = 'Fictional offline profile'; instructions = 'Review fictional supplied evidence only.'
        specialists = @(
            @{ tool = 'inspect_application'; agent = 'application-review-agent'; description = 'Fictional checklist' },
            @{ tool = 'inspect_case'; agent = 'case-review-agent'; description = 'Fictional case notes' })
        smoke_tests = @(
            @{ tool = 'inspect_application'; prompt = 'APP-TEST has no fictional budget.' },
            @{ tool = 'inspect_case'; prompt = 'CASE-TEST has conflicting fictional dates.' })
    }
    Set-Content -LiteralPath $script:profileFile -Value ($fictionalProfile | ConvertTo-Json -Depth 5)
    # Exercise the coordinator's real standard-library-only validator, never its publication path.
    $validator = Join-Path (Split-Path $script) 'hosted-agents/review-coordinator-agent/deploy.py'
    if (-not $PowerShellOnly) {
        $actualValidation = & python $validator --profile $script:profileFile --validate-profile
        Assert-Equal 0 $LASTEXITCODE 'fictional profile passes the real offline validator without SDK dependencies'
        Assert-Equal 'Valid profile: customer-review-coordinator' $actualValidation[0] 'real validator identifies the actual profile target'
        $badProfileFile = Join-Path $temporary 'invalid-profile.json'
        Set-Content -LiteralPath $badProfileFile -Value '{}'
        $null = & python $validator --profile $badProfileFile --validate-profile 2>&1
        if ($LASTEXITCODE -eq 0) { throw 'The real validator accepted an invalid profile.' }
        $env:FOUNDRY_HOSTED_AGENT_NAME = 'incompatible-test-override'
        try {
            $null = & python $validator --profile $script:profileFile --validate-profile 2>&1
            if ($LASTEXITCODE -eq 0) { throw 'The real validator accepted an incompatible environment name override.' }
        } finally { Remove-Item Env:FOUNDRY_HOSTED_AGENT_NAME }
        $null = & python $validator --profile $script:profileFile --validate-profile --agent-name incompatible-test-override 2>&1
        if ($LASTEXITCODE -eq 0) { throw 'The real validator accepted an incompatible CLI name override.' }
        $global:LASTEXITCODE = 0
    }

    $CoordinatorProfile = $script:profileFile
    $Agent = @('application-review-agent', 'case-review-agent', 'review-coordinator-agent')
    $script:fictionalClientId = '12345678-1234-1234-1234-123456789abc'
    $env:AZURE_TOKEN_CREDENTIALS = 'ManagedIdentityCredential'
    $env:AZURE_CLIENT_ID = $script:fictionalClientId
    $script:profileTarget = 'customer-review-coordinator'
    $script:validations = 0
    $script:approvalLabels = [Collections.Generic.List[string]]::new()
    foreach ($key in $savedTerraformArguments.Keys) {
        [Environment]::SetEnvironmentVariable($key, '-force-copy', 'Process')
        $before = $script:publicationCalls.Count; $asked = $script:approvalLabels.Count
        $initialized = $script:agentPlatformInitializations
        try { Invoke-AgentsStage; throw 'injected Terraform arguments accepted' } catch {
            if ($_.Exception.Message -notmatch 'TF_CLI_ARGS') { throw }
        } finally { [Environment]::SetEnvironmentVariable($key, $null, 'Process') }
        Assert-Equal $initialized $script:agentPlatformInitializations 'Terraform argument injection fails before platform initialization'
        Assert-Equal $before $script:publicationCalls.Count 'Terraform argument injection fails before publication'
        Assert-Equal $asked $script:approvalLabels.Count 'Terraform argument injection fails before approval'
    }
    $LocalState = [switch]$true
    $before = $script:publicationCalls.Count; $asked = $script:approvalLabels.Count
    $initialized = $script:agentPlatformInitializations
    try { Invoke-AgentsStage; throw 'profile with local state accepted' } catch {
        if ($_.Exception.Message -notmatch 'cannot be combined with -LocalState') { throw }
    }
    Assert-Equal $initialized $script:agentPlatformInitializations 'profile with LocalState fails before platform initialization'
    Assert-Equal $before $script:publicationCalls.Count 'profile with LocalState fails before publication'
    Assert-Equal $asked $script:approvalLabels.Count 'profile with LocalState fails before approval'
    $LocalState = [switch]$false
    function Confirm-Apply([string]$Label) {
        $script:approvalLabels.Add($Label)
        if ($script:changeCredentialAfterApproval) { $env:AZURE_TOKEN_CREDENTIALS = 'WorkloadIdentityCredential' }
        if ($script:changeProfileAfterApproval -and $Label -match 'customer-review-coordinator') {
            Set-Content -LiteralPath $script:profileFile -Value '{"same-name":"changed bytes after approval"}'
        }
        if ($script:declineCoordinator -and $Label -match 'customer-review-coordinator') { return $false }
        $script:approval
    }
    foreach ($case in @(
        @{ Mode = $null; Client = $script:fictionalClientId },
        @{ Mode = 'dev'; Client = $script:fictionalClientId },
        @{ Mode = 'EnvironmentCredential'; Client = $script:fictionalClientId },
        @{ Mode = 'ManagedIdentityCredential,WorkloadIdentityCredential'; Client = $script:fictionalClientId },
        @{ Mode = 'managedidentitycredential'; Client = $script:fictionalClientId },
        @{ Mode = 'ManagedIdentityCredential'; Client = $null },
        @{ Mode = 'WorkloadIdentityCredential'; Client = 'not-a-guid' },
        @{ Mode = 'ManagedIdentityCredential'; Client = " $($script:fictionalClientId)" })) {
        [Environment]::SetEnvironmentVariable('AZURE_TOKEN_CREDENTIALS', $case.Mode, 'Process')
        [Environment]::SetEnvironmentVariable('AZURE_CLIENT_ID', $case.Client, 'Process')
        $before = $script:publicationCalls.Count; $asked = $script:approvalLabels.Count
        $initialized = $script:agentPlatformInitializations
        try { Invoke-AgentsStage; throw 'invalid credential selection accepted' } catch {
            if ($_.Exception.Message -notmatch 'AZURE_TOKEN_CREDENTIALS|AZURE_CLIENT_ID') { throw }
        }
        Assert-Equal $initialized $script:agentPlatformInitializations 'invalid credential fails before platform initialization'
        Assert-Equal $before $script:publicationCalls.Count 'invalid credential fails before any publication'
        Assert-Equal $asked $script:approvalLabels.Count 'invalid credential fails before any approval'
    }
    $env:AZURE_TOKEN_CREDENTIALS = 'ManagedIdentityCredential'
    $env:AZURE_CLIENT_ID = $script:fictionalClientId
    $script:changeCredentialDuringValidation = $true
    $before = $script:publicationCalls.Count; $asked = $script:approvalLabels.Count
    $initialized = $script:agentPlatformInitializations
    $venvs = $script:venvCalls; $pips = $script:pipCalls
    try { Invoke-AgentsStage; throw 'changed credential during validation accepted' } catch {
        if ($_.Exception.Message -notmatch 'credential selection changed') { throw }
    }
    Assert-Equal $initialized $script:agentPlatformInitializations 'credential change during validation prevents platform initialization'
    Assert-Equal $before $script:publicationCalls.Count 'credential change during validation prevents publication'
    Assert-Equal $asked $script:approvalLabels.Count 'credential change during validation prevents approval'
    Assert-Equal $venvs $script:venvCalls 'credential change during validation prevents venv work'
    Assert-Equal $pips $script:pipCalls 'credential change during validation prevents pip work'
    $script:changeCredentialDuringValidation = $false
    $env:AZURE_TOKEN_CREDENTIALS = 'ManagedIdentityCredential'
    $script:useRealProfileValidation = -not $PowerShellOnly
    foreach ($field in $(if (-not $PowerShellOnly) { @('coordinator', 'specialist') })) {
        $invalidNames = @('_coordinator', 'agent_name', '-agent', 'agent-', ('a' * 64), "caf$([char]0x00e9)", '-')
        if ($field -eq 'specialist') { $invalidNames += @('7', ('9' + ('a' * 62))) }
        foreach ($name in $invalidNames) {
            $configuration = $fictionalProfile | ConvertTo-Json -Depth 5 | ConvertFrom-Json -AsHashtable
            if ($field -eq 'coordinator') { $configuration.name = $name } else { $configuration.specialists[0].agent = $name }
            Set-Content -LiteralPath $script:profileFile -Value ($configuration | ConvertTo-Json -Depth 5)
            $before = $script:publicationCalls.Count; $approvalsBefore = $script:approvalLabels.Count
            try { Invoke-AgentsStage; throw 'invalid deployment endpoint name accepted' } catch {
                if ($_.Exception.Message -notmatch 'Real offline profile validation failed') { throw }
            }
            Assert-Equal $before $script:publicationCalls.Count "real Python rejects invalid $field endpoint before any batch publication"
            Assert-Equal $approvalsBefore $script:approvalLabels.Count "real Python rejects invalid $field endpoint before any batch approval"
        }
    }
    $global:LASTEXITCODE = 0
    $script:useRealProfileValidation = $false
    Set-Content -LiteralPath $script:profileFile -Value ($fictionalProfile | ConvertTo-Json -Depth 5)
    $before = $script:publicationCalls.Count
    $Stage = @('AgEnTs')
    $stageOutput = (Invoke-AgentsStage 6>&1 | Out-String)
    $calls = @($script:publicationCalls | Select-Object -Skip $before)
    Assert-Equal 3 $calls.Count 'profiled batch publishes all approved agents'
    Assert-Equal 'application-review-agent,case-review-agent,review-coordinator-agent' (($calls | ForEach-Object { Split-Path (Split-Path $_.Arguments[0]) -Leaf }) -join ',') 'specialists publish before coordinator'
    foreach ($call in $calls) {
        Assert-Equal '--credential-mode' $call.Arguments[1] 'every agent receives explicit credential mode'
        Assert-Equal 'ManagedIdentityCredential' $call.Arguments[2] 'every agent receives the same selected class'
        Assert-Equal '--credential-client-id' $call.Arguments[3] 'every agent receives explicit client ID flag'
        Assert-Equal $script:fictionalClientId $call.Arguments[4] 'every agent receives same client ID'
    }
    foreach ($call in $calls[0..1]) { Assert-Equal 5 $call.Arguments.Count 'specialists receive no coordinator profile arguments' }
    Assert-Equal 9 $calls[2].Arguments.Count 'coordinator receives explicit credential and profile arguments'
    Assert-Equal '--profile' $calls[2].Arguments[5] 'coordinator receives the explicit profile flag'
    Assert-Equal $script:profileFile $calls[2].Arguments[6] 'spaces and shell metacharacters remain one literal argument'
    Assert-Equal '--profile-sha256' $calls[2].Arguments[7] 'publication forwards the digest flag'
    Assert-Equal (Get-FileHash -LiteralPath $script:profileFile -Algorithm SHA256).Hash.ToLowerInvariant() $calls[2].Arguments[8] 'publication uses the same digest as validated approval'
    Assert-Equal 'custom-router' $script:publishedModels[-1] 'profile forwarding preserves Router default'
    Assert-Equal 3 $script:approvalLabels.Count 'every publication still requires separate approval'
    if ($script:approvalLabels[-1] -notmatch 'publishing customer-review-coordinator from profile' -or $script:approvalLabels[-1] -notmatch [regex]::Escape($script:profileFile)) {
        throw 'Coordinator approval did not identify the actual profile target and file.'
    }
    if ($stageOutput -notmatch 'publication target: customer-review-coordinator') { throw 'Batch preflight did not identify the selected target.' }
    $Stage = @('agents')
    Assert-Equal $false (Test-Path Env:FOUNDRY_PROJECT_ENDPOINT) 'successful profile publication clears project environment'
    Assert-Equal $false (Test-Path Env:FOUNDRY_MODEL_NAME) 'successful profile publication clears model environment'
    $CoordinatorProfile = [IO.Path]::GetRelativePath((Split-Path $script), $script:profileFile)
    $script:agentOutputs = $fixedOutputs
    Invoke-AgentsStage
    Assert-Equal $script:profileFile $script:publicationCalls[-1].Arguments[6] 'repository-relative profile resolves to the same literal file'
    Assert-Equal 'gpt-4.1' $script:publishedModels[-1] 'profile forwarding preserves fixed-model recovery'
    $AgentModel = 'explicit-fixed'; $script:modelOutputReads = 0
    Invoke-AgentsStage
    Assert-Equal 'explicit-fixed' $script:publishedModels[-1] 'explicit model override still wins for a profile'
    Assert-Equal 0 $script:modelOutputReads 'profile with explicit model does not read model outputs'
    $AgentModel = $null; $script:agentOutputs = $routerOutputs
    $env:AZURE_TOKEN_CREDENTIALS = 'WorkloadIdentityCredential'
    $before = $script:publicationCalls.Count
    Invoke-AgentsStage
    foreach ($call in @($script:publicationCalls | Select-Object -Skip $before)) {
        Assert-Equal 'WorkloadIdentityCredential' $call.Arguments[2] 'workload selection reaches every agent in the batch'
        Assert-Equal $script:fictionalClientId $call.Arguments[4] 'workload selection retains explicit ID'
    }
    $env:AZURE_TOKEN_CREDENTIALS = 'ManagedIdentityCredential'
    $script:changeCredentialAfterApproval = $true
    $before = $script:publicationCalls.Count
    try { Invoke-AgentsStage; throw 'changed credential selection accepted' } catch {
        if ($_.Exception.Message -notmatch 'credential selection changed') { throw }
    }
    Assert-Equal $before $script:publicationCalls.Count 'changed selection after approval cannot publish'
    $script:changeCredentialAfterApproval = $false
    $env:AZURE_TOKEN_CREDENTIALS = 'ManagedIdentityCredential'
    $script:changeClientAfterPublication = $true
    $before = $script:publicationCalls.Count
    $asked = $script:approvalLabels.Count; $venvs = $script:venvCalls; $pips = $script:pipCalls
    try { Invoke-AgentsStage; throw 'changed client after first publication accepted' } catch {
        if ($_.Exception.Message -notmatch 'credential selection changed') { throw }
    }
    Assert-Equal ($before + 1) $script:publicationCalls.Count 'changed client stops before the next agent'
    Assert-Equal ($asked + 1) $script:approvalLabels.Count 'changed client stops before the next approval'
    Assert-Equal ($venvs + 1) $script:venvCalls 'changed client stops before the next venv work'
    Assert-Equal ($pips + 1) $script:pipCalls 'changed client stops before the next pip work'
    $script:changeClientAfterPublication = $false
    $env:AZURE_CLIENT_ID = $script:fictionalClientId

    foreach ($case in @(
            @{ Profile = (Join-Path $temporary 'missing.json'); Agents = $Agent; Stages = @('agents'); Error = 'does not exist|Cannot find path' },
            @{ Profile = (Join-Path $temporary 'fictional*.json'); Agents = $Agent; Stages = @('agents'); Error = 'does not exist|Cannot find path' },
            @{ Profile = $temporary; Agents = $Agent; Stages = @('agents'); Error = 'one filesystem file' },
            @{ Profile = '   '; Agents = $Agent; Stages = @('agents'); Error = 'must name one file' },
            @{ Profile = $script:profileFile; Agents = @('application-review-agent'); Stages = @('agents'); Error = 'exactly one' },
            @{ Profile = $script:profileFile; Agents = @('review-coordinator-agent', 'case-review-agent'); Stages = @('agents'); Error = 'last in' },
            @{ Profile = $script:profileFile; Agents = @('review-coordinator-agent', 'review-coordinator-agent'); Stages = @('agents'); Error = 'exactly one' },
            @{ Profile = $script:profileFile; Agents = @('application-review-agent', 'application-review-agent', 'review-coordinator-agent'); Stages = @('agents'); Error = 'must not repeat' },
            @{ Profile = $script:profileFile; Agents = @('nonexistent-agent', 'review-coordinator-agent'); Stages = @('agents'); Error = 'No deployable agent' },
            @{ Profile = $script:profileFile; Agents = $Agent; Stages = @('verify'); Error = 'requires -Stage agents' },
            @{ Profile = $script:profileFile; Agents = $Agent; Stages = @('bootstrap', 'agents'); Error = 'requires -Stage agents alone' },
            @{ Profile = $script:profileFile; Agents = $Agent; Stages = @('platform', 'agents'); Error = 'requires -Stage agents alone' },
            @{ Profile = $script:profileFile; Agents = $Agent; Stages = @('preflight', 'agents'); Error = 'requires -Stage agents alone' },
            @{ Profile = $script:profileFile; Agents = $Agent; Stages = @('agents'); ValidationError = 'Fictional invalid profile.'; Error = 'invalid profile' },
            @{ Profile = $script:profileFile; Agents = $Agent; Stages = @('agents'); ValidationError = 'Unset FOUNDRY_HOSTED_AGENT_NAME when using a profile'; Error = 'Unset FOUNDRY_HOSTED_AGENT_NAME' },
            @{ Profile = $script:profileFile; Agents = $Agent; Stages = @('agents'); Ambiguous = $true; Error = 'unambiguous profile target' },
            @{ Profile = $script:profileFile; Agents = $Agent; Stages = @('agents'); Target = 'application-review-agent'; Error = 'conflicts with another agent' })) {
        $CoordinatorProfile = $case.Profile; $Agent = $case.Agents; $Stage = $case.Stages
        $script:validationError = $case.ValidationError; $script:ambiguousTarget = $case.Ambiguous
        $script:profileTarget = if ($case.Target) { $case.Target } else { 'customer-review-coordinator' }
        $before = $script:publicationCalls.Count; $approvalsBefore = $script:approvalLabels.Count
        $initialized = $script:agentPlatformInitializations; $validationsBefore = $script:validations
        $venvs = $script:venvCalls; $pips = $script:pipCalls
        try { Invoke-AgentsStage; throw 'invalid profile batch accepted' } catch {
            if ($_.Exception.Message -notmatch $case.Error) { throw }
        }
        Assert-Equal $before $script:publicationCalls.Count 'profile preflight rejection occurs before any batch publication'
        Assert-Equal $approvalsBefore $script:approvalLabels.Count 'profile preflight rejection occurs before publication approvals'
        if ($case.Stages.Count -ne 1 -or $case.Stages[0] -ne 'agents') {
            Assert-Equal $initialized $script:agentPlatformInitializations 'changed stage selection stops before platform initialization'
            Assert-Equal $validationsBefore $script:validations 'changed stage selection stops before profile validation'
            Assert-Equal $venvs $script:venvCalls 'changed stage selection stops before venv work'
            Assert-Equal $pips $script:pipCalls 'changed stage selection stops before pip work'
        }
    }
    $script:validationError = $null; $script:ambiguousTarget = $false; $script:profileTarget = 'customer-review-coordinator'
    $CoordinatorProfile = $script:profileFile; $Stage = @('agents')
    $Agent = @('review-coordinator-agent')
    $script:approval = $false
    $before = $script:publicationCalls.Count
    try { Invoke-AgentsStage; throw 'declined profile publication accepted' } catch {
        if ($_.Exception.Message -notmatch 'not approved') { throw }
    }
    Assert-Equal $before $script:publicationCalls.Count 'declining coordinator approval publishes nothing'
    Assert-Equal $false (Test-Path Env:FOUNDRY_PROJECT_ENDPOINT) 'declined profile approval leaves no project environment'
    Assert-Equal $false (Test-Path Env:FOUNDRY_MODEL_NAME) 'declined profile approval leaves no model environment'
    $script:approval = $true
    $Agent = @('application-review-agent', 'case-review-agent', 'review-coordinator-agent')
    $script:declineCoordinator = $true
    try { Invoke-AgentsStage; throw 'declined coordinator after specialists accepted' } catch {
        if ($_.Exception.Message -notmatch 'not approved') { throw }
    }
    Assert-Equal ($before + 2) $script:publicationCalls.Count 'declined coordinator leaves only separately approved specialists published'
    Assert-Equal $false (Test-Path Env:FOUNDRY_PROJECT_ENDPOINT) 'declined coordinator after specialists clears project environment'
    Assert-Equal $false (Test-Path Env:FOUNDRY_MODEL_NAME) 'declined coordinator after specialists clears model environment'
    $script:declineCoordinator = $false; $Agent = @('review-coordinator-agent')
    $before = $script:publicationCalls.Count
    foreach ($changeAt in 2, 3) {
        $script:validations = 0; $script:changeTargetAt = $changeAt
        try { Invoke-AgentsStage; throw 'changed profile target accepted' } catch {
            if ($_.Exception.Message -notmatch 'profile target changed') { throw }
        }
        Assert-Equal $before $script:publicationCalls.Count 'observed target changes before or after approval stop coordinator publication'
    }
    $script:changeTargetAt = $null
    $script:changeProfileAfterApproval = $true
    try { Invoke-AgentsStage; throw 'changed profile bytes after approval accepted' } catch {
        if ($_.Exception.Message -notmatch 'profile digest mismatch') { throw }
    }
    Assert-Equal $before $script:publicationCalls.Count 'changed bytes after approval stop before coordinator invocation'
    $script:changeProfileAfterApproval = $false
    Set-Content -LiteralPath $script:profileFile -Value ($fictionalProfile | ConvertTo-Json -Depth 5)
    $script:publicationError = $true
    try { Invoke-AgentsStage; throw 'publication failure ignored' } catch {
        if ($_.Exception.Message -notmatch 'Fictional publication failure') { throw }
    }
    Assert-Equal $false (Test-Path Env:FOUNDRY_PROJECT_ENDPOINT) 'failed profile publication clears project environment'
    Assert-Equal $false (Test-Path Env:FOUNDRY_MODEL_NAME) 'failed profile publication clears model environment'
    $script:publicationError = $false
    Remove-Variable CoordinatorProfile
    $CoordinatorProfile = $null
    $before = $script:validations
    Invoke-AgentsStage
    Assert-Equal 1 $script:publicationCalls[-1].Arguments.Count 'omitting the profile preserves base coordinator invocation'
    Assert-Equal $before $script:validations 'omitting the profile never silently validates or selects the example'
    $env:TF_CLI_ARGS_init = '-force-copy'
    $before = $script:publicationCalls.Count
    try { Invoke-AgentsStage } finally { Remove-Item Env:TF_CLI_ARGS_init }
    Assert-Equal ($before + 1) $script:publicationCalls.Count 'unprofiled publication behavior is unchanged by Terraform argument guard'

    $file = Join-Path $temporary 'x.tfvars'
    Set-Content -LiteralPath $file -Value "registry_name = `"abc123`"`n# image = `"no`""
    Assert-Equal 'abc123' (Get-TfvarsValue $file 'registry_name') 'tfvars value is read'
    Assert-Equal $null (Get-TfvarsValue $file 'missing') 'missing tfvars value is null'
    Write-NewFile $file 'overwritten' | Out-Null
    if ((Get-Content -LiteralPath $file -Raw) -match 'overwritten') { throw 'An existing input file was overwritten.' }
} finally {
    [Environment]::SetEnvironmentVariable('AZURE_TOKEN_CREDENTIALS', $savedCredentialMode, 'Process')
    [Environment]::SetEnvironmentVariable('AZURE_CLIENT_ID', $savedClientId, 'Process')
    foreach ($key in $savedTerraformArguments.Keys) {
        [Environment]::SetEnvironmentVariable($key, $savedTerraformArguments[$key], 'Process')
    }
    Remove-Item -LiteralPath $temporary -Recurse -Force
}

if ($PowerShellOnly) { Write-Host 'PowerShell-only: real Python validation omitted; external publication and setup calls were mocked.' }
Write-Host 'deploy.ps1 helper checks passed.'

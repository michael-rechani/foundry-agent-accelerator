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
try { & { . $script -Subscription $subscription -AgentModel 'invalid model' }; throw 'invalid agent model accepted' } catch {
    if ($_.Exception.Message -notmatch 'AgentModel') { throw }
}
try { & { . $script -Subscription $subscription -CoordinatorProfile '' }; throw 'empty coordinator profile accepted' } catch {
    if ($_.Exception.Message -notmatch 'CoordinatorProfile') { throw }
}

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
    function Initialize-PlatformRoot { }
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
            Assert-Equal 4 $Arguments.Count 'validation forwards only profile and offline flag'
            Assert-Equal $script:profileFile $Arguments[2] 'validation keeps the literal profile path as one argument'
            if ($script:validationError) { throw $script:validationError }
            if ($script:ambiguousTarget) { return @('Valid profile: customer-review-coordinator', 'Valid profile: other-coordinator') }
            $target = if ($script:changeTargetAt -and $script:validations -ge $script:changeTargetAt) { 'changed-coordinator' } else { $script:profileTarget }
            return @("Valid profile: $target", '  inspect_application -> application-review-agent', '  inspect_case -> case-review-agent')
        }
        if ($Arguments[0] -match 'deploy\.py$') {
            $script:publishedModels.Add($env:FOUNDRY_MODEL_NAME)
            $script:publicationCalls.Add([pscustomobject]@{ Command = $Command; Arguments = @($Arguments); Endpoint = $env:FOUNDRY_PROJECT_ENDPOINT })
            if ($script:publicationError) { throw 'Fictional publication failure.' }
        }
    }
    $Agent = @('basic-responses-agent')
    $script:approval = $true
    $script:modelOutputReads = 0
    $script:failModelOutput = $false
    $script:publishedModels = [Collections.Generic.List[string]]::new()
    $script:publicationCalls = [Collections.Generic.List[object]]::new()
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

    $CoordinatorProfile = $script:profileFile
    $Agent = @('application-review-agent', 'case-review-agent', 'review-coordinator-agent')
    $script:profileTarget = 'customer-review-coordinator'
    $script:validations = 0
    $script:approvalLabels = [Collections.Generic.List[string]]::new()
    function Confirm-Apply([string]$Label) {
        $script:approvalLabels.Add($Label)
        if ($script:declineCoordinator -and $Label -match 'customer-review-coordinator') { return $false }
        $script:approval
    }
    $before = $script:publicationCalls.Count
    $stageOutput = (Invoke-AgentsStage 6>&1 | Out-String)
    $calls = @($script:publicationCalls | Select-Object -Skip $before)
    Assert-Equal 3 $calls.Count 'profiled batch publishes all approved agents'
    Assert-Equal 'application-review-agent,case-review-agent,review-coordinator-agent' (($calls | ForEach-Object { Split-Path (Split-Path $_.Arguments[0]) -Leaf }) -join ',') 'specialists publish before coordinator'
    foreach ($call in $calls[0..1]) { Assert-Equal 1 $call.Arguments.Count 'specialists receive no coordinator profile arguments' }
    Assert-Equal 3 $calls[2].Arguments.Count 'coordinator receives script and two profile arguments'
    Assert-Equal '--profile' $calls[2].Arguments[1] 'coordinator receives the explicit profile flag'
    Assert-Equal $script:profileFile $calls[2].Arguments[2] 'spaces and shell metacharacters remain one literal argument'
    Assert-Equal 'custom-router' $script:publishedModels[-1] 'profile forwarding preserves Router default'
    Assert-Equal 3 $script:approvalLabels.Count 'every publication still requires separate approval'
    if ($script:approvalLabels[-1] -notmatch 'publishing customer-review-coordinator from profile' -or $script:approvalLabels[-1] -notmatch [regex]::Escape($script:profileFile)) {
        throw 'Coordinator approval did not identify the actual profile target and file.'
    }
    if ($stageOutput -notmatch 'publication target: customer-review-coordinator') { throw 'Batch preflight did not identify the selected target.' }
    Assert-Equal $false (Test-Path Env:FOUNDRY_PROJECT_ENDPOINT) 'successful profile publication clears project environment'
    Assert-Equal $false (Test-Path Env:FOUNDRY_MODEL_NAME) 'successful profile publication clears model environment'
    $CoordinatorProfile = [IO.Path]::GetRelativePath((Split-Path $script), $script:profileFile)
    $script:agentOutputs = $fixedOutputs
    Invoke-AgentsStage
    Assert-Equal $script:profileFile $script:publicationCalls[-1].Arguments[2] 'repository-relative profile resolves to the same literal file'
    Assert-Equal 'gpt-4.1' $script:publishedModels[-1] 'profile forwarding preserves fixed-model recovery'
    $AgentModel = 'explicit-fixed'; $script:modelOutputReads = 0
    Invoke-AgentsStage
    Assert-Equal 'explicit-fixed' $script:publishedModels[-1] 'explicit model override still wins for a profile'
    Assert-Equal 0 $script:modelOutputReads 'profile with explicit model does not read model outputs'
    $AgentModel = $null; $script:agentOutputs = $routerOutputs

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
            @{ Profile = $script:profileFile; Agents = $Agent; Stages = @('agents'); ValidationError = 'Fictional invalid profile.'; Error = 'invalid profile' },
            @{ Profile = $script:profileFile; Agents = $Agent; Stages = @('agents'); ValidationError = 'Unset FOUNDRY_HOSTED_AGENT_NAME when using a profile'; Error = 'Unset FOUNDRY_HOSTED_AGENT_NAME' },
            @{ Profile = $script:profileFile; Agents = $Agent; Stages = @('agents'); Ambiguous = $true; Error = 'unambiguous profile target' },
            @{ Profile = $script:profileFile; Agents = $Agent; Stages = @('agents'); Target = 'application-review-agent'; Error = 'conflicts with another agent' })) {
        $CoordinatorProfile = $case.Profile; $Agent = $case.Agents; $Stage = $case.Stages
        $script:validationError = $case.ValidationError; $script:ambiguousTarget = $case.Ambiguous
        $script:profileTarget = if ($case.Target) { $case.Target } else { 'customer-review-coordinator' }
        $before = $script:publicationCalls.Count; $approvalsBefore = $script:approvalLabels.Count
        try { Invoke-AgentsStage; throw 'invalid profile batch accepted' } catch {
            if ($_.Exception.Message -notmatch $case.Error) { throw }
        }
        Assert-Equal $before $script:publicationCalls.Count 'profile preflight rejection occurs before any batch publication'
        Assert-Equal $approvalsBefore $script:approvalLabels.Count 'profile preflight rejection occurs before publication approvals'
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
    $script:publicationError = $true
    try { Invoke-AgentsStage; throw 'publication failure ignored' } catch {
        if ($_.Exception.Message -notmatch 'Fictional publication failure') { throw }
    }
    Assert-Equal $false (Test-Path Env:FOUNDRY_PROJECT_ENDPOINT) 'failed profile publication clears project environment'
    Assert-Equal $false (Test-Path Env:FOUNDRY_MODEL_NAME) 'failed profile publication clears model environment'
    $script:publicationError = $false
    $CoordinatorProfile = $null
    $before = $script:validations
    Invoke-AgentsStage
    Assert-Equal 1 $script:publicationCalls[-1].Arguments.Count 'omitting the profile preserves base coordinator invocation'
    Assert-Equal $before $script:validations 'omitting the profile never silently validates or selects the example'

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

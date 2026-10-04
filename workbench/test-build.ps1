$ErrorActionPreference = 'Stop'
$buildTestState = @{
    Failure = $null
    InvalidDigest = $false
    MismatchedDigest = $false
    PushedConfig = $null
    PublicAccess = 'Disabled'
    PublicMode = $false
    Commands = [System.Collections.Generic.List[string]]::new()
}
$testDigest = 'example.azurecr.io/workbench@sha256:' + ('a' * 64)
$testImageId = 'c' * 64
. (Join-Path $PSScriptRoot 'image-context.ps1')

# Every workbench module or package that app.py imports, directly or through another module.
function Get-LocalModuleClosure {
    $seen = [System.Collections.Generic.HashSet[string]]::new()
    $queue = [System.Collections.Generic.Queue[string]]::new()
    $queue.Enqueue('app')
    while ($queue.Count) {
        $name = $queue.Dequeue()
        if (-not $seen.Add($name)) { continue }
        $source = if (Test-Path -LiteralPath (Join-Path $PSScriptRoot "$name.py")) { Join-Path $PSScriptRoot "$name.py" } else { Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot $name) -Filter '*.py' -Recurse | Select-Object -ExpandProperty FullName }
        foreach ($line in Get-Content -LiteralPath $source) {
            $imported = if ($line -match '^\s*from\s+(\w+)') { $Matches[1] }
            elseif ($line -match '^\s*import\s+(.+)$') { $Matches[1] -split ',' | ForEach-Object { ($_.Trim() -split '[\s.]')[0] } }
            foreach ($module in $imported) {
                if ($module -and ((Test-Path -LiteralPath (Join-Path $PSScriptRoot "$module.py")) -or (Test-Path -LiteralPath (Join-Path $PSScriptRoot "$module/__init__.py")))) { $queue.Enqueue($module) }
            }
        }
    }
    $seen
}

function az {
    $operation = "az $($args[0]) $($args[1])"
    $buildTestState.Commands.Add($operation)
    $global:LASTEXITCODE = 0
    if ($buildTestState.Failure -eq $operation) {
        $global:LASTEXITCODE = 1
        return
    }
    switch ($operation) {
        'az acr show' {
            if ($buildTestState.PublicMode) { $buildTestState.PublicAccess } else { 'example.azurecr.io' }
        }
        'az acr build' {}
        'az acr login' {}
        'az acr repository' {
            if ($buildTestState.InvalidDigest) { 'latest' } else { 'sha256:' + ('a' * 64) }
        }
        'az acr manifest' {
            if ($args -notcontains ('workbench@sha256:' + ('a' * 64))) { throw 'Manifest lookup must use the pushed digest' }
            $buildTestState.PushedConfig
        }
        default { throw "Unexpected Azure operation: $operation" }
    }
}

function docker {
    $operation = "docker $($args[0])"
    $buildTestState.Commands.Add($operation)
    $global:LASTEXITCODE = 0
    if ($buildTestState.Failure -eq $operation) {
        $global:LASTEXITCODE = 1
        return
    }
    switch ($operation) {
        'docker build' {
            $stage = $args[-1]
            $expected = @(Get-ImageContextFile $PSScriptRoot) + @('agent_runtime', 'agent_templates', 'frontend')
            $actual = @(Get-ChildItem -LiteralPath $stage -Force | Select-Object -ExpandProperty Name)
            if (Compare-Object $expected $actual) { throw 'Unexpected build context contents' }
            foreach ($module in Get-LocalModuleClosure) {
                if (!(Test-Path (Join-Path $stage "$module.py")) -and !(Test-Path (Join-Path $stage "$module/__init__.py"))) { throw "Build context is missing $module, which app.py imports" }
            }
            if (!(Test-Path (Join-Path $stage 'frontend/src'))) { throw 'Frontend source not staged' }
            if (Test-Path (Join-Path $stage 'frontend/public')) { throw 'Unexpected frontend public files staged' }
            $runtimeFiles = @(Get-ChildItem -LiteralPath (Join-Path $stage 'agent_runtime') -Force | Select-Object -ExpandProperty Name)
            if (Compare-Object @('main.py', 'demo_tools.py', 'requirements.txt') $runtimeFiles) { throw 'Unexpected hosted runtime bundle contents' }
            $templateFiles = @(Get-ChildItem -LiteralPath (Join-Path $stage 'agent_templates') -Force | Select-Object -ExpandProperty Name)
            if (Compare-Object (@(Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot 'agent_templates') -Filter '*.py' -Name) + 'agents') $templateFiles) { throw 'Unexpected agent templates package contents' }
            $agentFiles = @(Get-ChildItem -LiteralPath (Join-Path $stage 'agent_templates/agents') -Force | Select-Object -ExpandProperty Name)
            if (Compare-Object @(Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot 'agent_templates/agents') -Filter '*.json' -Name) $agentFiles) { throw 'Unexpected library agent files' }
        }
        'docker run' {
            if ($args[-1] -notmatch 'os.getuid\(\) != 0') { throw 'Missing non-root validation' }
            if ($args[-1] -notmatch 'agent_publisher.runtime_package\(\)') { throw 'Missing hosted runtime package validation' }
            if ($args[-1] -notmatch "import_module\(m\.stem\) for m in sorted\(Path\('\.'\)\.glob\('\*\.py'\)\)") {
                throw 'Image validation must import every module in the image'
            }
            if ($args[-1].Contains('"') -or $args[-1] -notmatch "Path\('agents.json'\)" -or
                $args[-1] -notmatch "Path\('static/index.html'\)") {
                throw 'Image validation command must preserve Python literals through Windows native argument passing'
            }
        }
        'docker push' {}
        'docker image' {
            $olderDigest = 'example.azurecr.io/workbench@sha256:' + ('b' * 64)
            $digests = @(if ($buildTestState.MismatchedDigest) { $olderDigest } else { $olderDigest, $testDigest })
            (ConvertTo-Json -InputObject $digests -Compress) + " $testImageId"
        }
        'docker pull' {
            if ($args[-1] -ne $testDigest) { throw 'Pull must verify the immutable digest' }
        }
        default { throw "Unexpected Docker operation: $operation" }
    }
}

$expectedCommands = @('az acr show', 'az acr login', 'docker build', 'docker run', 'docker push', 'az acr repository', 'docker image', 'docker pull')
$podmanCommands = @('az acr show', 'az acr login', 'docker build', 'docker run', 'docker push', 'az acr repository', 'docker image', 'az acr manifest', 'docker pull')
$cases = @(
    @{ Name = 'private build succeeds'; Failure = $null; Error = $null },
    @{ Name = 'registry lookup failure'; Failure = 'az acr show'; Error = 'Registry lookup failed' },
    @{ Name = 'registry login failure'; Failure = 'az acr login'; Error = 'Registry login failed' },
    @{ Name = 'build failure'; Failure = 'docker build'; Error = 'Local image build failed' },
    @{ Name = 'image validation failure'; Failure = 'docker run'; Error = 'Image validation failed' },
    @{ Name = 'push failure'; Failure = 'docker push'; Error = 'Image push failed' },
    @{ Name = 'digest lookup failure'; Failure = 'az acr repository'; Error = 'Image digest lookup failed' },
    @{ Name = 'invalid digest'; Failure = $null; InvalidDigest = $true; Error = 'Image digest lookup failed' },
    @{ Name = 'local digest lookup failure'; Failure = 'docker image'; Error = 'Pushed image digest does not match the local build' },
    @{ Name = 'Podman push with matching config digest'; Failure = $null; MismatchedDigest = $true; PushedConfig = "sha256:$testImageId"; Error = $null; Commands = $podmanCommands },
    @{ Name = 'mismatched pushed digest and config'; Failure = $null; MismatchedDigest = $true; PushedConfig = 'sha256:' + ('d' * 64); Error = 'Pushed image digest does not match the local build'; Commands = $podmanCommands },
    @{ Name = 'pushed manifest lookup failure'; Failure = 'az acr manifest'; MismatchedDigest = $true; Error = 'Pushed image digest does not match the local build'; Commands = $podmanCommands },
    @{ Name = 'pull failure'; Failure = 'docker pull'; Error = 'Image pull verification failed' }
)

foreach ($case in $cases) {
    $buildTestState.Failure = $case.Failure
    $buildTestState.InvalidDigest = $case.InvalidDigest -eq $true
    $buildTestState.MismatchedDigest = $case.MismatchedDigest -eq $true
    $buildTestState.PushedConfig = $case.PushedConfig
    $buildTestState.Commands.Clear()
    $caseCommands = if ($case.Commands) { $case.Commands } else { $expectedCommands }
    $output = [System.Collections.Generic.List[string]]::new()
    $failure = $null
    try {
        & (Join-Path $PSScriptRoot 'build.ps1') -Private -Subscription '00000000-0000-0000-0000-000000000001' -Registry 'example' -Tag 'test-only' |
            ForEach-Object { $output.Add("$_") }
    } catch {
        $failure = $_.Exception.Message
    }
    if ($case.Error) {
        if ($failure -ne $case.Error) { throw "Unexpected failure for $($case.Name): $failure" }
        if ($output -contains 'PRIVATE_BUILD_PUSH_AND_PULL_VERIFIED=True') { throw 'Failed build reported success' }
        $lastCommand = if ($case.InvalidDigest) { 'az acr repository' } elseif ($case.Commands) { 'az acr manifest' } elseif ($case.MismatchedDigest) { 'docker image' } else { $case.Failure }
        $expectedCount = [array]::IndexOf($caseCommands, $lastCommand) + 1
    } else {
        if ($failure) { throw $failure }
        if ($output -notcontains $testDigest -or $output -notcontains 'PRIVATE_BUILD_PUSH_AND_PULL_VERIFIED=True') {
            throw 'Successful build did not report its verified digest'
        }
        $expectedCount = $caseCommands.Count
    }
    if (($buildTestState.Commands -join ',') -ne ($caseCommands[0..($expectedCount - 1)] -join ',')) {
        throw "Unexpected command order for $($case.Name)"
    }
    Write-Output "PASS: $($case.Name)"
}
$global:LASTEXITCODE = 0

$buildTestState.PublicMode = $true
$buildTestState.Failure = $null
foreach ($access in @('Disabled', 'Enabled')) {
    $buildTestState.PublicAccess = $access
    $buildTestState.Commands.Clear()
    $failure = $null
    try {
        & (Join-Path $PSScriptRoot 'build.ps1') -Subscription '00000000-0000-0000-0000-000000000001' -Registry 'example' -Tag 'test-only' | Out-Null
    } catch {
        $failure = $_.Exception.Message
    }
    if ($access -eq 'Disabled') {
        if ($failure -ne 'ACR Tasks requires an explicitly public registry; use -Private for private builds' -or
            ($buildTestState.Commands -join ',') -ne 'az acr show') {
            throw 'Private registry must reject ACR Tasks before submitting a build'
        }
    } elseif ($failure -or ($buildTestState.Commands -join ',') -ne 'az acr show,az acr build') {
        throw 'Explicitly public registry build path failed'
    }
    Write-Output "PASS: ACR Tasks with public access $access"
}
$parameters = (Get-Command (Join-Path $PSScriptRoot 'build.ps1')).Parameters
foreach ($name in @('Subscription', 'Registry', 'Tag')) {
    if (-not @($parameters[$name].Attributes | Where-Object { $_ -is [System.Management.Automation.ParameterAttribute] -and $_.Mandatory }).Count) {
        throw "Build target must be explicit: $name"
    }
}
Write-Output 'PASS: build targets are mandatory'
$global:LASTEXITCODE = 0
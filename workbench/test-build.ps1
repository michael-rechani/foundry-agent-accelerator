$ErrorActionPreference = 'Stop'
$buildTestState = @{
    Failure = $null
    InvalidDigest = $false
    MismatchedDigest = $false
    PublicAccess = 'Disabled'
    PublicMode = $false
    Commands = [System.Collections.Generic.List[string]]::new()
}
$testDigest = 'example.azurecr.io/workbench@sha256:' + ('a' * 64)

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
            $expected = @('Dockerfile', '.dockerignore', 'requirements.txt', 'app.py', 'history.py', 'reviews.py', 'review_runs.py', 'agents.json', 'frontend')
            $actual = @(Get-ChildItem -LiteralPath $stage -Force | Select-Object -ExpandProperty Name)
            if (Compare-Object $expected $actual) { throw 'Unexpected build context contents' }
            if (!(Test-Path (Join-Path $stage 'frontend/src'))) { throw 'Frontend source not staged' }
        }
        'docker run' {
            if ($args[-1] -notmatch 'os.getuid\(\) != 0') { throw 'Missing non-root validation' }
            if ($args[-1].Contains('"') -or $args[-1] -notmatch "Path\('agents.json'\)" -or
                $args[-1] -notmatch "Path\('static/index.html'\)") {
                throw 'Image validation command must preserve Python literals through Windows native argument passing'
            }
        }
        'docker push' {}
        'docker image' {
            $olderDigest = 'example.azurecr.io/workbench@sha256:' + ('b' * 64)
            if ($buildTestState.MismatchedDigest) {
                ConvertTo-Json -InputObject @($olderDigest) -Compress
            } else {
                ConvertTo-Json -InputObject @($olderDigest, $testDigest) -Compress
            }
        }
        'docker pull' {
            if ($args[-1] -ne $testDigest) { throw 'Pull must verify the immutable digest' }
        }
        default { throw "Unexpected Docker operation: $operation" }
    }
}

$expectedCommands = @('az acr show', 'az acr login', 'docker build', 'docker run', 'docker push', 'az acr repository', 'docker image', 'docker pull')
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
    @{ Name = 'mismatched pushed digest'; Failure = $null; MismatchedDigest = $true; Error = 'Pushed image digest does not match the local build' },
    @{ Name = 'pull failure'; Failure = 'docker pull'; Error = 'Image pull verification failed' }
)

foreach ($case in $cases) {
    $buildTestState.Failure = $case.Failure
    $buildTestState.InvalidDigest = $case.InvalidDigest -eq $true
    $buildTestState.MismatchedDigest = $case.MismatchedDigest -eq $true
    $buildTestState.Commands.Clear()
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
        $lastCommand = if ($case.InvalidDigest) { 'az acr repository' } elseif ($case.MismatchedDigest) { 'docker image' } else { $case.Failure }
        $expectedCount = [array]::IndexOf($expectedCommands, $lastCommand) + 1
    } else {
        if ($failure) { throw $failure }
        if ($output -notcontains $testDigest -or $output -notcontains 'PRIVATE_BUILD_PUSH_AND_PULL_VERIFIED=True') {
            throw 'Successful build did not report its verified digest'
        }
        $expectedCount = $expectedCommands.Count
    }
    if (($buildTestState.Commands -join ',') -ne ($expectedCommands[0..($expectedCount - 1)] -join ',')) {
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
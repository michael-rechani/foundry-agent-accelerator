$ErrorActionPreference = 'Stop'
$global:demoCheckFixture = @{
    Scenario = 'ready'
    Requests = [System.Collections.Generic.List[string]]::new()
}

function curl.exe {
    $global:demoCheckFixture.Requests.Add($args[-1])
    if ($args -contains 'POST') { throw 'The read-only preflight attempted a model call.' }
    $global:LASTEXITCODE = 0
    $status, $body = 200, @{ status = 'ready' }
    switch -Wildcard ($args[-1]) {
        '*/api/config' {
            $body = @{ agents = @(@{ id = 'sample' }); default_agent = 'sample'
                library_preview = @{ enabled = $true }; agent_creation = @{ enabled = $false } }
            if ($global:demoCheckFixture.Scenario -eq 'bad-config') { $status = 503; $body = $null }
        }
        '*/api/agent-templates' {
            $body = @{ templates = @(@{ id = 'sample' }) }
            if ($global:demoCheckFixture.Scenario -eq 'empty-library') { $body = @{} }
        }
        '*/api/health/dependencies' {
            if ($global:demoCheckFixture.Scenario -eq 'degraded') { $body = @{ status = 'degraded' } }
        }
    }
    "HTTP/1.1 $status OK`r`nContent-Type: application/json`r`n`r`n$($body | ConvertTo-Json -Compress -Depth 5)"
}

foreach ($scenario in @('ready', 'empty-library', 'degraded', 'bad-config')) {
    $global:demoCheckFixture.Scenario = $scenario
    $global:demoCheckFixture.Requests.Clear()
    $global:LASTEXITCODE = 0
    $failed = $false
    try {
        & "$PSScriptRoot\demo-check.ps1" -BaseUrl 'https://lab.example.invalid'
        $failed = $LASTEXITCODE -ne 0
    }
    catch {
        if ($scenario -ne 'bad-config') { throw }
        $failed = $true
    }
    if ($failed -ne ($scenario -ne 'ready')) { throw "Unexpected preflight result for $scenario." }
    if ($global:demoCheckFixture.Requests.Count -gt 4) { throw 'The read-only preflight made extra requests.' }
}
Remove-Variable demoCheckFixture -Scope Global
Write-Host 'Pre-demo checks passed without model calls.'

$ErrorActionPreference = 'Stop'
$reviewId = 'review-11111111-1111-4111-8111-111111111111'
$origin = 'https://lab.example.invalid'
$fixture = @{
    Origin = $origin
    Listed = $true
    Calls = [System.Collections.Generic.List[object]]::new()
}

class SyntheticConflict : Exception {
    [object]$Response = @{ StatusCode = 409 }
}

function Invoke-RestMethod {
    param($Uri, $Headers, $MaximumRedirection, $TimeoutSec, $Method = 'Get', $Body, $ContentType)
    if ($MaximumRedirection -ne 0) { throw 'Verification must reject redirects.' }
    if (-not $Uri.StartsWith("$($fixture.Origin)/")) { throw 'Unexpected verification target.' }
    $fixture.Calls.Add(@{ Uri = $Uri; Headers = $Headers; Method = $Method })
    if ($Uri.EndsWith('/api/config')) {
        if ($Headers.Authorization) { throw 'Public configuration must not receive the test token.' }
        return @{ mode = 'private'; reviews_enabled = $true }
    }
    if ($Headers.Authorization) { throw 'Shared-demo verification must not send a bearer token.' }
    if ($Uri.EndsWith('/api/health/dependencies')) { return @{ status = 'ready' } }
    if ($Uri.EndsWith('/execute')) {
        if (@($fixture.Calls | Where-Object { $_.Uri.EndsWith('/execute') }).Count -gt 1) {
            throw [SyntheticConflict]::new()
        }
        return @{ status = 'running' }
    }
    if ($Method -eq 'Post') { return @{ id = $reviewId; _etag = 'synthetic-etag' } }
    if ($Uri.EndsWith('/api/review-runs')) {
        return @{ items = $(if ($fixture.Listed) { @(@{ id = $reviewId }) } else { @() }) }
    }
    return @{
        id = $reviewId
        status = 'completed'
        runs = @(
            @{ input = @{ evidence = @(@{ id = 'SRC-1'; text = 'Synthetic evidence' }) }
               result = @{ findings = @(@{ citations = @(@{ source_id = 'SRC-1'; quote = 'Synthetic evidence' }) }) }
               receipts = @(@{ verified = $true }) },
            @{ input = @{ evidence = @(@{ id = 'SRC-1'; text = 'Synthetic evidence' }, @{ id = 'SRC-2'; text = 'Synthetic budget' }) }
               result = @{ findings = @(@{ citations = @(@{ source_id = 'SRC-2'; quote = 'Synthetic budget' }) }) }
               receipts = @(@{ verified = $true }) }
        )
    }
}

function Expect-Failure($Action, $Message) {
    try { & $Action | Out-Null } catch {
        if ($_.Exception.Message -notlike "*$Message*") { throw }
        return
    }
    throw "Expected failure: $Message"
}

foreach ($target in @('http://lab.example.invalid', "$origin/path", "$origin/?query=1", "$origin/#fragment", 'https://user:password@lab.example.invalid')) {
    Expect-Failure { & "$PSScriptRoot/test-review-private.ps1" -Mode Inspect -ReviewId $reviewId -BaseUrl $target } 'exact private HTTPS origin'
}
if ($fixture.Calls.Count) { throw 'An invalid target reached the HTTP client.' }

& "$PSScriptRoot/test-review-private.ps1" -Mode Verify -ReviewId $reviewId -BaseUrl "$origin/" | Out-Null
$fixture.Calls.Clear()
& "$PSScriptRoot/test-review-private.ps1" -Mode Start -BaseUrl $origin | Out-Null
if (@($fixture.Calls | Where-Object { $_.Uri.EndsWith('/api/health/dependencies') }).Count -ne 1) {
    throw 'Start did not check dependency readiness.'
}

$fixture.Listed = $false
Expect-Failure { & "$PSScriptRoot/test-review-private.ps1" -Mode Verify -ReviewId $reviewId -BaseUrl $origin } 'missing from the recent-review list'
Write-Output 'Private review verification contracts passed: explicit target, no redirects or tokens, dependency readiness, stale ETag, and list membership.'

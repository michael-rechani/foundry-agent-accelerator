param(
    [ValidateSet('Start', 'Inspect', 'Resume', 'Verify')][string]$Mode = 'Start',
    [ValidatePattern('^review-[0-9a-f-]{36}$')][string]$ReviewId,
    [string]$BaseUrl = 'https://foundry-workbench.icyplant-54a7139a.northcentralus.azurecontainerapps.io'
)
$ErrorActionPreference = 'Stop'
$headers = @{ 'X-Workbench-Request' = '1'; Origin = $BaseUrl }
function Invoke-ReviewApi($Path, $Body, $ETag) {
    $requestHeaders = $headers.Clone()
    if ($ETag) { $requestHeaders['If-Match'] = $ETag }
    $parameters = @{ Uri = "$BaseUrl/api/review-runs$Path"; Headers = $requestHeaders; TimeoutSec = 40 }
    if ($null -ne $Body) {
        $parameters.Method = 'Post'
        $parameters.ContentType = 'application/json'
        $parameters.Body = $Body | ConvertTo-Json -Depth 30 -Compress
    }
    Invoke-RestMethod @parameters
}
if ($Mode -eq 'Start') {
    $config = Invoke-RestMethod "$BaseUrl/api/config" -TimeoutSec 40
    if (-not $config.reviews_enabled -or $config.mode -ne 'private') { throw 'Private review workflow is not enabled' }
    $health = Invoke-RestMethod "$BaseUrl/api/health/dependencies" -TimeoutSec 40
    if ($health.status -ne 'ready') { throw 'Dependencies are not ready' }
    $draft = Invoke-ReviewApi '' @{
        title = 'Synthetic rollout verification'
        agent_id = 'customer-review'
        criteria = @('The proposed workshop must last twelve weeks.', 'An explicit total budget in USD must be supplied. Ask for the total budget when it is missing; no further detail is required.')
        evidence = @(@{ id = 'SRC-1'; text = 'Synthetic application: The proposed workshop lasts twelve weeks. No total budget has been supplied.' })
    } $null
    Write-Output "SYNTHETIC_REVIEW_ID=$($draft.id)"
    $running = Invoke-ReviewApi "/$($draft.id)/execute" @{} $draft._etag
    if ($running.status -ne 'running') { throw 'Review did not start' }
    try {
        Invoke-ReviewApi "/$($draft.id)/execute" @{} $draft._etag | Out-Null
        throw 'Stale execution was accepted'
    } catch {
        if (-not $_.Exception.Response -or [int]$_.Exception.Response.StatusCode -ne 409) { throw }
    }
    Write-Output 'SYNTHETIC_DRAFT_EXECUTION_AND_STALE_ETAG_CHECK_PASSED=True'
    return
}
if (-not $ReviewId) { throw 'ReviewId is required for follow-up stages' }
$review = Invoke-ReviewApi "/$ReviewId" $null $null
Write-Output "SYNTHETIC_REVIEW_STATUS=$($review.status)"
if ($review.status -in @('running', 'draft')) { throw 'Review has not reached a result; do not resubmit execution' }
if ($review.status -notin @('waiting_input', 'completed')) {
    Write-Output "SYNTHETIC_REVIEW_ERROR=$($review.runs[-1].error)"
    throw 'Review execution did not produce a validated result'
}
foreach ($run in $review.runs) {
    if (-not $run.result -or -not @($run.receipts).Count -or @($run.receipts | Where-Object { -not $_.verified }).Count) { throw 'Missing result or verified specialist receipt' }
    foreach ($finding in $run.result.findings) {
        foreach ($citation in $finding.citations) {
            $source = @($run.input.evidence | Where-Object id -eq $citation.source_id)
            if ($source.Count -ne 1 -or -not $source[0].text.Contains($citation.quote)) { throw 'Citation does not match the run evidence' }
        }
    }
}
Write-Output 'SYNTHETIC_RECEIPTS_AND_EXACT_CITATIONS_VERIFIED=True'
if ($Mode -eq 'Resume') {
    if ($review.status -ne 'waiting_input' -or $review.runs.Count -ne 1) { throw 'Expected first-run clarification' }
    $draft = Invoke-ReviewApi "/$ReviewId/evidence" @{ id = 'SRC-2'; text = 'Synthetic budget clarification: The total workshop budget is USD 12000.' } $review._etag
    if ($draft.status -ne 'draft' -or $draft.evidence.Count -ne 2 -or $draft.runs[0].input.evidence.Count -ne 1) { throw 'Evidence append changed the prior run snapshot' }
    $running = Invoke-ReviewApi "/$ReviewId/execute" @{} $draft._etag
    if ($running.status -ne 'running' -or $running.runs.Count -ne 2) { throw 'Resume did not start the second run' }
    Write-Output 'SYNTHETIC_CLARIFICATION_AND_EXPLICIT_RESUME_PASSED=True'
}
if ($Mode -eq 'Verify') {
    if ($review.status -ne 'completed' -or $review.runs.Count -ne 2 -or $review.runs[0].input.evidence.Count -ne 1 -or $review.runs[1].input.evidence.Count -ne 2) { throw 'Expected completed two-run review with preserved evidence snapshots' }
    $listing = Invoke-ReviewApi '' $null $null
    Write-Output 'SYNTHETIC_REVIEW_RESUME_AND_REOPEN_VERIFIED=True'
}
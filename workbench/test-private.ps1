param([string]$BaseUrl = 'https://foundry-workbench.icyplant-54a7139a.northcentralus.azurecontainerapps.io')
$ErrorActionPreference = 'Stop'
$headers = @{ 'X-Workbench-Request' = '1'; Origin = $BaseUrl }
$config = Invoke-RestMethod "$BaseUrl/api/config"
if (!$config.history_enabled -or $config.mode -ne 'private') { throw 'Expected private Cosmos-backed app' }
if (@($config.agents).Count -ne 1 -or $config.agents[0].id -ne 'customer-review') { throw 'Unexpected visible agents' }
$listing = Invoke-RestMethod "$BaseUrl/api/conversations" -Headers $headers
Write-Output 'Private HTTPS, agent catalog and Cosmos list passed'
$prompt = 'Review this synthetic application. CRIT-1 requires a budget. APP-1 describes a twelve-week workshop but supplies no budget. Cite APP-1 and identify missing evidence.'
$review = Invoke-RestMethod "$BaseUrl/api/reviews" -Method Post -Headers $headers -ContentType 'application/json' -Body (@{ agent_id = 'customer-review'; input = $prompt } | ConvertTo-Json) -TimeoutSec 200
if ($review.status -ne 'completed' -or !$review.text) { throw 'Agent response incomplete' }
Write-Output "Live agent response passed; receipts=$(@($review.receipts).Count); elapsed_ms=$($review.elapsed_ms)"
$body = @{ agent_id = 'customer-review'; turns = @(@{ question = $prompt; result = $review }) } | ConvertTo-Json -Depth 20
$saved = Invoke-RestMethod "$BaseUrl/api/conversations" -Method Post -Headers $headers -ContentType 'application/json' -Body $body
try {
    $read = Invoke-RestMethod "$BaseUrl/api/conversations/$($saved.id)" -Headers $headers
    if ($read.turns[0].result.text -ne $review.text) { throw 'Persisted transcript mismatch' }
    $headers['If-Match'] = $read._etag
    $updated = Invoke-RestMethod "$BaseUrl/api/conversations/$($saved.id)" -Method Put -Headers $headers -ContentType 'application/json' -Body $body
    $headers['If-Match'] = $updated._etag
    Write-Output 'Cosmos create, point-read and conditional update passed'
} finally {
    Invoke-RestMethod "$BaseUrl/api/conversations/$($saved.id)" -Method Delete -Headers $headers | Out-Null
    Write-Output 'Synthetic smoke-test conversation deleted'
}
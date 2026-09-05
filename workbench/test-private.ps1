param([string]$BaseUrl = 'https://foundry-workbench.icyplant-54a7139a.northcentralus.azurecontainerapps.io')
$ErrorActionPreference = 'Stop'
$headers = @{ 'X-Workbench-Request' = '1'; Origin = $BaseUrl }
$config = Invoke-RestMethod "$BaseUrl/api/config"
if (!$config.history_enabled -or $config.mode -ne 'private') { throw 'Expected private Cosmos-backed app' }
if (@($config.agents).Count -ne 1 -or $config.agents[0].id -ne 'customer-review') { throw 'Unexpected visible agents' }
if ($config.title -ne 'AI Foundry Lab' -or $config.default_agent -ne 'customer-review') { throw 'Unexpected lab configuration' }
if ($config.max_characters -ne 60000 -or $config.max_request_bytes -ne 65536 -or $config.max_history_turns -ne 10) { throw 'Unexpected request limits' }
if ($config.review_timeout_ms -ne 190000 -or $config.history_timeout_ms -ne 45000 -or @($config.agents[0].prompts).Count -ne 3) { throw 'Unexpected deadlines or starter prompts' }
$page = Invoke-WebRequest $BaseUrl -UseBasicParsing
if ($page.Content -notmatch '<title>AI Foundry Lab</title>') { throw 'Unexpected browser title' }
if ($page.Headers['Strict-Transport-Security'] -notmatch 'max-age=31536000') { throw 'Missing HSTS policy' }
$dependencies = Invoke-RestMethod "$BaseUrl/api/health/dependencies"
if ($dependencies.status -ne 'ready' -or $dependencies.foundry -ne 'ready' -or $dependencies.cosmos -ne 'ready') { throw 'Dependencies are not ready' }
Write-Output 'HSTS and cached Foundry/Cosmos dependency checks passed'
$listing = Invoke-RestMethod "$BaseUrl/api/conversations" -Headers $headers
Write-Output 'Private HTTPS, AI Foundry Lab configuration, agent catalog and Cosmos list passed'
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
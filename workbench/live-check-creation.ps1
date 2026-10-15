<#
Live check for "create an agent from a library template, ask it a question, delete it" (#109).

Without -Execute it only reads: it checks that creation is on and lists existing created agents.
With -Execute it publishes ONE agent in the shared private Foundry project (billable until deleted),
sends the template's sample once, then deletes it. Run it from a network the Front Door allow-list
accepts, over IPv4 if the allow-list only holds an IPv4 address (-Ipv4Only).

The operator key is read from Key Vault into memory and sent only as X-Workbench-Creation-Key.
It is never printed or written to disk.
#>
param(
    [Parameter(Mandatory)][string]$BaseUrl,
    [Parameter(Mandatory)][string]$VaultName,
    [string]$TemplateId = 'insurance-preapproval-helper',
    [string]$KeySecretName = 'lab-creation-operator-key',
    [switch]$Ipv4Only,
    [switch]$Execute
)
$ErrorActionPreference = 'Stop'
$BaseUrl = $BaseUrl.TrimEnd('/')
$ipFlag = if ($Ipv4Only) { @('-4') } else { @() }

function Invoke-Lab {
    param([string]$Method, [string]$Path, $Body, [hashtable]$Extra = @{}, [int]$TimeoutSeconds = 60)
    $arguments = @('-s', '--max-time', $TimeoutSeconds, '-X', $Method, '-D', '-', '-H', 'X-Workbench-Request: 1') + $ipFlag
    foreach ($name in $Extra.Keys) {
        $value = [string]$Extra[$name]
        # Windows PowerShell 5.1 drops embedded quotes (the quoted ETag) unless they are escaped.
        if ($PSVersionTable.PSVersion.Major -lt 7) { $value = $value -replace '"', '\"' }
        $arguments += @('-H', "${name}: $value")
    }
    if ($null -ne $Body) { $arguments += @('-H', 'Content-Type: application/json', '--data-binary', '@-') }
    $arguments += "$BaseUrl$Path"
    $raw = if ($null -ne $Body) { ($Body | ConvertTo-Json -Depth 8 -Compress) | curl.exe @arguments } else { curl.exe @arguments }
    $text = $raw -join "`n"
    $split = $text -split "(?:\r?\n){2}", 2
    $status = [int](($split[0] -split '\s+')[1])
    $json = if ($split.Count -gt 1 -and $split[1].Trim()) { $split[1] | ConvertFrom-Json } else { $null }
    [pscustomobject]@{ Status = $status; Body = $json }
}

$config = (Invoke-Lab GET '/api/config').Body
if (-not $config.agent_creation.enabled) { throw "Creation is disabled: $($config.agent_creation.reason)" }
$existing = Invoke-Lab GET '/api/agents'
Write-Host "Creation enabled. Models: $(($config.agent_creation.models | ConvertTo-Json -Compress)). Created agents now: $(@($existing.Body.items).Count) of $($existing.Body.limit)."
if (-not $Execute) { Write-Host 'Dry run only. Add -Execute to publish, test and delete one agent.'; return }
if (@($existing.Body.items).Count -ge $existing.Body.limit) { throw 'The created-agent limit is reached; delete one first.' }

$key = az keyvault secret show --vault-name $VaultName --name $KeySecretName --query value -o tsv
if (-not $key) { throw 'Could not read the operator key from Key Vault.' }
$auth = @{ 'X-Workbench-Creation-Key' = $key }

$draft = (Invoke-Lab POST '/api/agent-drafts' @{ goal = 'Review a fictional insurance pre-approval request against its listed criteria.'; template_id = $TemplateId }).Body
$created = Invoke-Lab POST '/api/agents' @{
    idempotency_key = [guid]::NewGuid().ToString(); template_id = $TemplateId; name = $draft.name
    instructions = $draft.instructions; confirm_cost = $true
} $auth
if ($created.Status -notin 200, 202) { throw "Create failed: HTTP $($created.Status) $($created.Body.error)" }
$id = $created.Body.id
Write-Host "Created record $id; waiting for it to be ready."

$agent = $null
try {
    $deadline = (Get-Date).AddSeconds($config.agent_creation.publication_timeout_seconds + 60)
    do {
        Start-Sleep 10
        $agent = (Invoke-Lab GET "/api/agents/$id").Body
        Write-Host "  $($agent.status) / $($agent.stage)"
    } while ($agent.status -eq 'creating' -and (Get-Date) -lt $deadline)
    if ($agent.status -ne 'ready') { throw "Agent did not reach ready: $($agent.status) / $($agent.error)" }

    $answer = Invoke-Lab POST '/api/reviews' @{ agent_id = $id; input = $draft.sample_input } @{} 240
    if ($answer.Status -ne 200) { throw "Sample failed: HTTP $($answer.Status) $($answer.Body.error)" }
    $verified = @($answer.Body.receipts | Where-Object verified).Count
    Write-Host "Sample answered in $($answer.Body.elapsed_ms) ms. Tool calls: $(@($answer.Body.receipts).Count), verified: $verified."
    Write-Host "Tools: $((@($answer.Body.receipts) | ForEach-Object tool) -join ', ')"
    Write-Host '--- Answer ---'
    Write-Host $answer.Body.text
}
finally {
    Write-Host 'Deleting the test agent.'
    $current = (Invoke-Lab GET "/api/agents/$id").Body
    $deleting = Invoke-Lab DELETE "/api/agents/$id" $null ($auth + @{ 'If-Match' = $current._etag })
    if ($deleting.Status -notin 200, 202) { Write-Warning "Delete returned HTTP $($deleting.Status) $($deleting.Body.error). Delete it in the Lab before leaving it running." }
    else {
        $deadline = (Get-Date).AddSeconds(180)
        do { Start-Sleep 10; $state = (Invoke-Lab GET "/api/agents/$id").Body } while ($state.status -eq 'deleting' -and (Get-Date) -lt $deadline)
        Write-Host "Final state: $($state.status)"
        $left = @((Invoke-Lab GET '/api/agents').Body.items).Count
        Write-Host "Created agents remaining: $left"
    }
    $key = $null
}

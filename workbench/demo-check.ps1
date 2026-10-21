<#
Pre-demo check for the Lab (#410). Run it from the network you will present on, a few minutes before you start.

Without -Designer it only reads: it never calls a model, saves anything or creates anything, so it costs nothing.
With -Designer it also sends ONE short message to the Agent designer (a billable model call, a fraction of a cent)
and checks that the reply carries a well-formed agent spec card.

Use -Ipv4Only when the Front Door allow-list only holds an IPv4 address.
#>
param(
    [Parameter(Mandatory)][string]$BaseUrl,
    [switch]$Ipv4Only,
    [switch]$Designer
)
$ErrorActionPreference = 'Stop'
$BaseUrl = $BaseUrl.TrimEnd('/')
$ipFlag = if ($Ipv4Only) { @('-4') } else { @() }
$script:failed = 0

function Invoke-Lab {
    param([string]$Method, [string]$Path, $Body, [int]$TimeoutSeconds = 60)
    $arguments = @('-s', '--max-time', $TimeoutSeconds, '-X', $Method, '-D', '-', '-H', 'X-Workbench-Request: 1') + $ipFlag
    if ($null -ne $Body) { $arguments += @('-H', 'Content-Type: application/json', '--data-binary', '@-') }
    $arguments += "$BaseUrl$Path"
    $raw = if ($null -ne $Body) { ($Body | ConvertTo-Json -Depth 8 -Compress) | curl.exe @arguments } else { curl.exe @arguments }
    $text = $raw -join "`n"
    if (-not $text) { return [pscustomobject]@{ Status = 0; Body = $null } }
    $split = $text -split "(?:\r?\n){2}", 2
    $status = [int](($split[0] -split '\s+')[1])
    $json = $null
    if ($split.Count -gt 1 -and $split[1].Trim()) { try { $json = $split[1] | ConvertFrom-Json } catch { } }
    [pscustomobject]@{ Status = $status; Body = $json }
}

function Report {
    param([bool]$Ok, [string]$Message, [switch]$Warn)
    if ($Ok) { Write-Host "  PASS  $Message" -ForegroundColor Green }
    elseif ($Warn) { Write-Host "  WARN  $Message" -ForegroundColor Yellow }
    else { Write-Host "  FAIL  $Message" -ForegroundColor Red; $script:failed++ }
}

Write-Host "Checking $BaseUrl"
$health = Invoke-Lab GET '/healthz'
Report ($health.Status -eq 200) "The Lab answers (/healthz returned $($health.Status)). If this fails, check you are on an allowed network."
if ($health.Status -ne 200) { throw 'The Lab is not reachable from here, so nothing else can be checked.' }

$config = (Invoke-Lab GET '/api/config').Body
$agents = @($config.agents)
Report ($agents.Count -gt 0) "$($agents.Count) agent(s) ready to chat. Default: $($config.default_agent)."
Report ([bool]$config.library_preview.enabled) 'Library previews and the Agent designer are on.' -Warn
Report ([bool]$config.agent_creation.enabled) 'Agent creation is on. Creating one is billable and takes up to 10 minutes, so skip it in a short demo.' -Warn

$templates = Invoke-Lab GET '/api/agent-templates'
$count = @($templates.Body.templates).Count
Report ($templates.Status -eq 200 -and $count -gt 0) "The agent library loads ($count agent(s) shown)."

$deps = Invoke-Lab GET '/api/health/dependencies'
Report ($deps.Status -eq 200) "Foundry and the history store are healthy (/api/health/dependencies returned $($deps.Status))."

if ($Designer) {
    Write-Host 'Asking the Agent designer one question (one billable model call).'
    $idea = 'I want an agent that reads a short supplier invoice and the purchase order and tells a person which lines do not match. ' +
        'It receives the two pasted texts, returns a list of mismatches with a reason each, and a person in accounts payable decides what to pay. ' +
        'It needs no lookups. Please write the agent spec now.'
    $reply = Invoke-Lab POST '/api/reviews' @{ agent_id = 'library-agent-designer'; input = $idea; history = @() } 120
    Report ($reply.Status -eq 200) "The designer answered in $($reply.Body.elapsed_ms) ms (HTTP $($reply.Status))."
    if ($reply.Status -eq 200) {
        $match = [regex]::Match([string]$reply.Body.text, '```agent-spec[ \t]*\r?\n([\s\S]*?)```')
        $spec = $null
        if ($match.Success) { try { $spec = $match.Groups[1].Value | ConvertFrom-Json } catch { } }
        Report ($null -ne $spec) 'The reply ends with an agent spec card that parses as JSON.'
        if ($null -ne $spec) {
            $keys = 'name', 'summary', 'instructions', 'inputs', 'outputs', 'tools_needed', 'human_decision', 'closest_template'
            $missing = @($keys | Where-Object { $spec.PSObject.Properties.Name -notcontains $_ })
            Report ($missing.Count -eq 0) $(if ($missing.Count) { "The spec is missing: $($missing -join ', ')." } else { 'The spec has every key.' })
            Write-Host "  Spec name: $($spec.name). Closest template: $($spec.closest_template)."
        }
    }
}
else {
    Write-Host '  SKIP  Agent designer not asked. Add -Designer to send one billable message and check its spec card.'
}

if ($script:failed) { Write-Host "$script:failed check(s) failed." -ForegroundColor Red; exit 1 }
Write-Host 'Ready to present.' -ForegroundColor Green

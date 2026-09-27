param(
    [string]$TestResultsDirectory = (Join-Path $PSScriptRoot '../../workbench/frontend/test-results'),
    [string[]]$Names = @()
)

$ErrorActionPreference = 'Stop'
$sources = [ordered]@{
    'lab-create-agent.png' = 'creation-start.png'
    'lab-create-agent-dark.png' = 'creation-start-dark.png'
    'lab-chat-start.png' = 'demo-starters.png'
    'lab-chat-start-dark.png' = 'demo-starters-dark.png'
    'lab-document-review.png' = 'review-findings.png'
    'lab-document-review-dark.png' = 'review-findings-dark.png'
    'lab-review-privacy.png' = 'review-privacy.png'
    'lab-review-privacy-dark.png' = 'review-privacy-dark.png'
    'lab-demo-application.png' = 'demo-application.png'
    'lab-demo-application-dark.png' = 'demo-application-dark.png'
    'lab-demo-invoice.png' = 'demo-invoice.png'
    'lab-demo-invoice-dark.png' = 'demo-invoice-dark.png'
    'lab-demo-casework.png' = 'demo-casework.png'
    'lab-demo-casework-dark.png' = 'demo-casework-dark.png'
}

foreach ($selected in $Names) {
    if (!$sources.Contains($selected)) { throw "Unknown screenshot: $selected" }
}

# Resolve and validate the selected set before replacing any documentation assets.
$outputs = [ordered]@{}
foreach ($name in $sources.Keys) {
    if ($Names.Count -gt 0 -and $name -notin $Names) { continue }
    $matches = @(Get-ChildItem -LiteralPath $TestResultsDirectory -Recurse -File -Filter $sources[$name] |
        Where-Object { $_.Directory.Name -match '-desktop$' })
    if ($matches.Count -ne 1) {
        throw "Expected one desktop output for $($sources[$name]); found $($matches.Count). Run the full desktop frontend suite first."
    }
    $bytes = [IO.File]::ReadAllBytes($matches[0].FullName)
    if ($bytes.Length -lt 24 -or [Convert]::ToBase64String($bytes, 0, 8) -ne 'iVBORw0KGgo=') {
        throw "Not a PNG: $($matches[0].FullName)"
    }
    $width = ([int]$bytes[16] -shl 24) -bor ([int]$bytes[17] -shl 16) -bor ([int]$bytes[18] -shl 8) -bor $bytes[19]
    $height = ([int]$bytes[20] -shl 24) -bor ([int]$bytes[21] -shl 16) -bor ([int]$bytes[22] -shl 8) -bor $bytes[23]
    if ($width -ne 1440 -or $height -ne 1000) {
        throw "$name is $width x $height; expected uncropped 1440 x 1000 output."
    }
    $outputs[(Join-Path $PSScriptRoot "screenshots/$name")] = $bytes
}
foreach ($path in $outputs.Keys) {
    [IO.File]::WriteAllBytes($path, $outputs[$path])
    Write-Output "Refreshed $path"
}
& (Join-Path $PSScriptRoot 'build-tour.ps1')
& (Join-Path $PSScriptRoot 'build-tour.ps1') -Tour scenarios

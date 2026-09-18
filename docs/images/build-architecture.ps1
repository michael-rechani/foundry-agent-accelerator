param(
    [string]$IconDirectory = (Join-Path $PSScriptRoot 'azure-icons')
)

$ErrorActionPreference = 'Stop'
foreach ($name in @('agent-collaboration', 'foundry-overview', 'foundry-operations', 'foundry-deployment')) {
    $template = Join-Path $PSScriptRoot "$name.template.svg"
    $output = Join-Path $PSScriptRoot "$name.svg"
    $content = Get-Content $template -Raw
    $content = [regex]::Replace($content, 'href="azure-icons/([a-z-]+\.svg)"', {
        param($match)
        $path = Join-Path $IconDirectory $match.Groups[1].Value
        if (!(Test-Path $path)) { throw "Missing official icon: $path" }
        $encoded = [Convert]::ToBase64String([IO.File]::ReadAllBytes($path))
        return 'href="data:image/svg+xml;base64,' + $encoded + '"'
    })
    [xml]$validated = $content
    if ($validated.DocumentElement.LocalName -ne 'svg') { throw 'Invalid diagram template' }
    [IO.File]::WriteAllText($output, $content, [Text.UTF8Encoding]::new($false))
    Write-Output "Built self-contained diagram: $output"
}
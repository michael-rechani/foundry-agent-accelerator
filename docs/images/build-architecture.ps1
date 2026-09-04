param(
    [string]$IconDirectory = (Join-Path $PSScriptRoot 'azure-icons')
)

$ErrorActionPreference = 'Stop'
$template = Join-Path $PSScriptRoot 'foundry-runtime-architecture.template.svg'
$output = Join-Path $PSScriptRoot 'foundry-runtime-architecture.svg'
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
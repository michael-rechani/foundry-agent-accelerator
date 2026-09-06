param(
    [Parameter(Mandatory = $true)]
    [string]$DrawioPath,
    [string[]]$Names = @('lab-components', 'lab-request-flow', 'review-lifecycle'),
    [string]$PreviewDirectory
)

$ErrorActionPreference = 'Stop'
if (!(Test-Path -LiteralPath $DrawioPath -PathType Leaf)) {
    throw 'Supply the path to the draw.io desktop executable.'
}
if ($PreviewDirectory) {
    New-Item -ItemType Directory -Path $PreviewDirectory -Force | Out-Null
}

foreach ($name in $Names) {
    if ($name -notmatch '^[a-z-]+$') { throw "Invalid diagram name: $name" }
    $source = Join-Path $PSScriptRoot "$name.drawio"
    $content = Get-Content -LiteralPath $source -Raw
    $embedded = [regex]::Replace($content, 'image=azure-icons/([a-z-]+\.svg);', {
        param($match)
        $icon = Join-Path $PSScriptRoot "azure-icons/$($match.Groups[1].Value)"
        if (!(Test-Path -LiteralPath $icon)) { throw "Missing official icon: $icon" }
        $encoded = [Convert]::ToBase64String([IO.File]::ReadAllBytes($icon))
        return "image=data:image/svg+xml,$encoded;"
    })
    [xml]$model = $embedded
    if ($model.DocumentElement.LocalName -ne 'mxfile') { throw "Invalid draw.io source: $name" }
    $cells = $model.SelectNodes('//mxCell')
    $identifiers = @($cells | ForEach-Object { $_.id })
    if (@($identifiers | Select-Object -Unique).Count -ne $identifiers.Count) {
        throw "Duplicate cell IDs: $name"
    }
    foreach ($cell in $cells) {
        foreach ($attribute in @('source', 'target', 'parent')) {
            if ($cell.HasAttribute($attribute) -and $cell.GetAttribute($attribute) -notin $identifiers) {
                throw "Unresolved $attribute in $name"
            }
        }
    }
    if ($embedded -ne $content) {
        [IO.File]::WriteAllText($source, $embedded, [Text.UTF8Encoding]::new($false))
    }
    $output = Join-Path $PSScriptRoot "$name.svg"
    $arguments = @('--export', '--format', 'svg', '--embed-diagram', '--embed-svg-images',
        '--border', '16', '--output', "`"$output`"", "`"$source`"")
    $process = Start-Process -FilePath $DrawioPath -ArgumentList $arguments -Wait -PassThru
    if ($process.ExitCode -ne 0 -or !(Test-Path -LiteralPath $output)) {
        throw "draw.io export failed: $name"
    }
    [xml]$rendered = Get-Content -LiteralPath $output -Raw
    if ($rendered.DocumentElement.LocalName -ne 'svg') { throw "Invalid SVG export: $name" }
    foreach ($image in $rendered.SelectNodes('//*[local-name()="image"]')) {
        foreach ($attribute in $image.Attributes) {
            if ($attribute.LocalName -eq 'href' -and !$attribute.Value.StartsWith('data:')) {
                throw "Non-embedded image in $name"
            }
        }
    }
    if ($PreviewDirectory) {
        $preview = Join-Path $PreviewDirectory "$name.png"
        $process = Start-Process -FilePath $DrawioPath -ArgumentList @('--export', '--format', 'png',
            '--scale', '1.5', '--border', '16', '--output', "`"$preview`"", "`"$source`"") -Wait -PassThru
        if ($process.ExitCode -ne 0 -or !(Test-Path -LiteralPath $preview)) {
            throw "draw.io preview failed: $name"
        }
    }
    Write-Output "Exported editable, self-contained diagram: $name"
}
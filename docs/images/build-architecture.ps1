param(
    [string]$IconDirectory = (Join-Path $PSScriptRoot 'azure-icons'),
    # Build only these diagrams, such as -Name agent-collaboration. Builds every template by default.
    [string[]]$Name
)

$ErrorActionPreference = 'Stop'

# Light-to-dark color map for the -dark variants. Every hex color in a template
# must have an entry here, or the build fails. Light #fff has two roles: white
# rectangles with no visible border or a dashed border are canvas-level areas
# (the background, label masks, and grouping boundaries); other white fills are
# cards.
$darkPalette = [ordered]@{
    '#fff'    = [ordered]@{ Canvas = '#0d1117'; Card = '#1f252e' }
    '#f5f7fa' = '#161b22' # Subtle panels
    '#f3f8fc' = '#0f2438' # Blue-tinted panels
    '#edf7f4' = '#0e2723' # Green-tinted panels
    '#fffaf0' = '#2a2313' # Warm-tinted panels
    '#fff4ce' = '#3b300d' # Yellow notes
    '#242424' = '#e6edf3' # Primary text
    '#4d5b69' = '#a9b4c0' # Secondary text and bullets
    '#334e68' = '#b8c9da' # Tool names
    '#0078d4' = '#4aa8ff' # Request arrows and accent borders
    '#00786a' = '#3cc3ae' # Result arrows and green borders
    '#8abce0' = '#4278a6' # Blue panel borders
    '#8da6bb' = '#6b7c8e' # Card and boundary borders
    '#aebdcb' = '#637484' # Panel borders
    '#cdd9e2' = '#5d6d7e' # Subtle panel borders
    '#b59e59' = '#a08845' # Warm panel borders
}

# A whole hex color token, excluding character references and ID references
# such as url(#arrow). Accessible text is never recolored.
$hexColor = '(?<![&(])(?<!href=")#[0-9a-f]{3,8}\b'
$accessibleText = '<(title|desc)\b[^>]*>.*?</\1>'

function Get-DarkColor([string]$Color, [string]$Role) {
    $dark = $darkPalette[$Color.ToLowerInvariant()]
    if ($dark -is [Collections.IDictionary]) { return $dark[$Role] }
    return $dark
}

function ConvertTo-DarkTemplate([string]$Content, [string]$Name) {
    $markup = [regex]::Replace($Content, $accessibleText, '', 'IgnoreCase, Singleline')
    $unmapped = [regex]::Matches($markup, $hexColor, 'IgnoreCase') |
        ForEach-Object { $_.Value.ToLowerInvariant() } |
        Where-Object { !$darkPalette.Contains($_) } |
        Sort-Object -Unique
    if ($unmapped) {
        throw "Unmapped colors in $Name.template.svg: $($unmapped -join ', '). Add them to `$darkPalette in build-architecture.ps1."
    }

    # Rectangles are matched whole so a white fill can take its canvas or card role.
    return [regex]::Replace($Content, "$accessibleText|<rect\b[^>]*>|$hexColor", {
        param($match)
        $text = $match.Value
        if ($text[0] -ne '<') { return Get-DarkColor $text 'Card' }
        if ($text -notmatch '^<rect\b') { return $text }
        $canvas = $text -notmatch '\sstroke="' -or $text -match '\sstroke="none"' -or $text -match '\sstroke-dasharray="'
        $role = if ($canvas) { 'Canvas' } else { 'Card' }
        return [regex]::Replace($text, $hexColor, { param($color) Get-DarkColor $color.Value $role }, 'IgnoreCase')
    }, 'IgnoreCase, Singleline')
}

# Icons are inlined as nested <svg> markup, not data: images. GitHub serves SVGs
# with Content-Security-Policy default-src 'none', which blocks every nested
# image when a reader opens a diagram directly. Each copy gets its own ID prefix
# so the gradients and clip paths of repeated icons can't collide.
function Add-OfficialIcons([string]$Content, [string]$Name) {
    $icon = @{ Count = 0 }
    $inlined = [regex]::Replace($Content, '<image href="azure-icons/([a-z-]+\.svg)"([^>]*?)\s*/>', {
        param($match)
        $path = Join-Path $IconDirectory $match.Groups[1].Value
        if (!(Test-Path $path)) { throw "Missing official icon: $path" }
        $source = [IO.File]::ReadAllText($path)
        $root = [regex]::Match($source, '^\s*<svg\b([^>]*)>(.*)</svg>\s*$', 'Singleline')
        $viewBox = [regex]::Match($root.Groups[1].Value, '\sviewBox="([^"]+)"')
        if (!$root.Success -or !$viewBox.Success) { throw "Unexpected icon markup: $path" }
        $icon.Count++
        $prefix = "icon$($icon.Count)-"
        $body = [regex]::Replace($root.Groups[2].Value, '<title\b[^>]*>.*?</title>', '', 'Singleline')
        $ids = @([regex]::Matches($body, '\sid="([^"]+)"') | ForEach-Object { $_.Groups[1].Value })
        $body = [regex]::Replace($body, '(\sid="|url\(#|href="#)([^")]+)', {
            param($reference)
            $id = $reference.Groups[2].Value
            if ($id -cnotin $ids) { throw "Icon $path references an ID it doesn't define: $id" }
            return $reference.Groups[1].Value + $prefix + $id
        })
        return "<svg$($match.Groups[2].Value) viewBox=`"$($viewBox.Groups[1].Value)`">$body</svg>"
    })
    if ($inlined -match '<image\b[^>]*azure-icons/') {
        throw "Use <image href=`"azure-icons/<name>.svg`" x y width height/> for icons in $Name.template.svg."
    }
    return $inlined
}

function Test-Diagram([string]$Content) {
    [xml]$validated = $Content
    if ($validated.DocumentElement.LocalName -ne 'svg') { throw 'Invalid diagram template' }
    return $validated
}

# Build every variant before writing any, so a failure leaves no partial outputs.
$outputs = [ordered]@{}
$diagrams = Get-ChildItem $PSScriptRoot -Filter '*.template.svg' | Sort-Object Name | ForEach-Object { $_.Name -replace '\.template\.svg$', '' }
if ($Name) {
    $missing = $Name | Where-Object { $_ -notin $diagrams }
    if ($missing) { throw "No template for: $($missing -join ', ')" }
    $diagrams = $Name
}
foreach ($diagram in $diagrams) {
    $source = Get-Content (Join-Path $PSScriptRoot "$diagram.template.svg") -Raw
    $content = Add-OfficialIcons $source $diagram
    $darkContent = Add-OfficialIcons (ConvertTo-DarkTemplate $source $diagram) $diagram
    $light = Test-Diagram $content
    $dark = Test-Diagram $darkContent
    foreach ($element in @('title', 'desc')) {
        if ($dark.DocumentElement[$element].InnerText -cne $light.DocumentElement[$element].InnerText) {
            throw "The dark $diagram diagram changed its $element text."
        }
    }
    $outputs[(Join-Path $PSScriptRoot "$diagram.svg")] = $content
    $outputs[(Join-Path $PSScriptRoot "$diagram-dark.svg")] = $darkContent
}

foreach ($output in $outputs.Keys) {
    [IO.File]::WriteAllText($output, $outputs[$output], [Text.UTF8Encoding]::new($false))
    Write-Output "Built self-contained diagram: $output"
}

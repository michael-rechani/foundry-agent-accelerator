param(
    [string]$ScreenshotDirectory = (Join-Path $PSScriptRoot 'screenshots'),
    [ValidateSet('lab', 'scenarios')]
    [string]$Tour = 'lab'
)

$ErrorActionPreference = 'Stop'

# The README tours: Lab screenshots from automated browser tests. They crossfade inside a minimal window frame. Each step names its
# light and dark screenshot. Label widths are the average of Segoe UI and Arial
# at 20px semibold; textLength keeps every label inside its pill whichever
# system font renders it.
$steps = if ($Tour -eq 'scenarios') { @(
    [ordered]@{ Label = 'Find missing evidence'; Width = 200; Light = 'lab-demo-application.png'; Dark = 'lab-demo-application-dark.png' }
    [ordered]@{ Label = 'Check an invoice'; Width = 155; Light = 'lab-demo-invoice.png'; Dark = 'lab-demo-invoice-dark.png' }
    [ordered]@{ Label = 'Prepare a case brief'; Width = 185; Light = 'lab-demo-casework.png'; Dark = 'lab-demo-casework-dark.png' }
) } else { @(
    [ordered]@{ Label = 'Find an agent'; Width = 126; Light = 'lab-start.png'; Dark = 'lab-start-dark.png' }
    [ordered]@{ Label = 'Browse agents'; Width = 136; Light = 'lab-library.png'; Dark = 'lab-library-dark.png' }
    [ordered]@{ Label = 'Test results'; Width = 106; Light = 'lab-test-results.png'; Dark = 'lab-test-results-dark.png' }
    [ordered]@{ Label = 'Chat with it'; Width = 106; Light = 'lab-chat-start.png'; Dark = 'lab-chat-start-dark.png' }
    [ordered]@{ Label = 'Take it to Foundry'; Width = 168; Light = 'lab-take-to-foundry.png'; Dark = 'lab-take-to-foundry-dark.png' }
    [ordered]@{ Label = 'Create an agent'; Width = 147; Light = 'lab-create-agent.png'; Dark = 'lab-create-agent-dark.png' }
) }
$tourName = if ($Tour -eq 'scenarios') { 'scenario-tour' } else { 'lab-tour' }

# Label text meets a WCAG contrast ratio of at least 4.5:1 against its pill, and
# badge numbers against their badge.
$themes = [ordered]@{
    "$tourName-dark" = [ordered]@{
        Screenshot = 'Dark'; Bar = '#161b22'; Border = '#3d444d'; Dot = '#3d444d'; Muted = '#9198a1'
        Pill = '#212830'; PillText = '#f0f6fc'; Accent = '#4aa8ff'; AccentText = '#0d1117'; Track = '#2f3742'
        Shadow = '#010409'; NearOpacity = '0.3'; FarOpacity = '0.5'
    }
}

$title = if ($Tour -eq 'scenarios') {
    'Foundry Agent Lab: three example walkthroughs'
} else {
    'Foundry Agent Lab: a tour of the agent library'
}
$description = if ($Tour -eq 'scenarios') {
    'Three example customer walkthroughs: missing application evidence, supplier invoice discrepancies, and a casework brief.'
} else {
    'Six screenshots: the job finder at the top of the agent library, browsing the agent library, one agent''s recorded test results, the Chat page, the Take it to Foundry steps, and the Create agent page.'
}

# Each frame holds for $frameSeconds, including a $fadeSeconds crossfade into
# the next one. The last frame fades back to the first, so the loop is seamless.
$frameSeconds = 4
$fadeSeconds = 0.6
$cycle = $steps.Count * $frameSeconds

# Geometry in SVG user units. Screenshots are drawn at their native 1440 x 1000.
$imageWidth = 1440
$imageHeight = 1000
$marginX = 40
$marginTop = 28
$marginBottom = 52
$barHeight = 60
$radius = 12
$windowX = $marginX
$windowY = $marginTop
$windowHeight = $barHeight + $imageHeight
$imageY = $windowY + $barHeight
$canvasWidth = $imageWidth + 2 * $marginX
$canvasHeight = $marginTop + $windowHeight + $marginBottom
$barCenter = $windowY + $barHeight / 2

$invariant = [Globalization.CultureInfo]::InvariantCulture

function Format-Number([double]$Value) {
    return $Value.ToString('0.###', $invariant)
}

function Get-Screenshot([string]$Name) {
    $path = Join-Path $ScreenshotDirectory $Name
    if (!(Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing screenshot: $path" }
    $bytes = [IO.File]::ReadAllBytes($path)
    $signature = [byte[]](0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A)
    if ($bytes.Length -lt 24 -or [Convert]::ToBase64String($bytes, 0, 8) -ne [Convert]::ToBase64String($signature)) {
        throw "Not a PNG: $path"
    }
    $width = ([int]$bytes[16] -shl 24) -bor ([int]$bytes[17] -shl 16) -bor ([int]$bytes[18] -shl 8) -bor $bytes[19]
    $height = ([int]$bytes[20] -shl 24) -bor ([int]$bytes[21] -shl 16) -bor ([int]$bytes[22] -shl 8) -bor $bytes[23]
    if ($width -ne $imageWidth -or $height -ne $imageHeight) {
        throw "$Name is $width x $height; the tour expects $imageWidth x $imageHeight desktop test output."
    }
    return [Convert]::ToBase64String($bytes)
}

# Keyframes take [seconds, declarations] stops across one cycle.
function New-Keyframes([string]$Name, [object[]]$Stops) {
    $lines = @("  @keyframes $Name {")
    foreach ($stop in $Stops) {
        $lines += "    $(Format-Number ($stop[0] / $cycle * 100))% { $($stop[1]) }"
    }
    $lines += '  }'
    return $lines
}

function New-Animations {
    $lines = @()
    $last = $steps.Count - 1
    $half = $fadeSeconds / 2
    for ($i = 0; $i -le $last; $i++) {
        $shown = $i * $frameSeconds
        $next = ($i + 1) * $frameSeconds

        # Frames fade in over the previous frame, which stays opaque underneath
        # until it is covered. Frame 1 is the static bottom layer.
        if ($i -gt 0) {
            $frameStops = @(@(0, 'opacity: 0'), @(($shown - $fadeSeconds), 'opacity: 0'), @($shown, 'opacity: 1'))
            if ($i -lt $last) {
                $frameStops += @(@($next, 'opacity: 1'), @(($next + $fadeSeconds), 'opacity: 0'), @($cycle, 'opacity: 0'))
            }
            else {
                $frameStops += @(@(($cycle - $fadeSeconds), 'opacity: 1'), @($cycle, 'opacity: 0'))
            }
            $lines += New-Keyframes "frame$($i + 1)" $frameStops
        }

        # Labels swap within the crossfade: the old one fades out, then the new
        # one fades in, so two labels never overlap.
        $labelStops = if ($i -eq 0) {
            @(@(0, 'opacity: 1'), @(($next - $fadeSeconds), 'opacity: 1'), @(($next - $half), 'opacity: 0'),
                @(($cycle - $half), 'opacity: 0'), @($cycle, 'opacity: 1'))
        }
        else {
            @(@(0, 'opacity: 0'), @(($shown - $half), 'opacity: 0'), @($shown, 'opacity: 1'),
                @(($next - $fadeSeconds), 'opacity: 1'), @(($next - $half), 'opacity: 0'), @($cycle, 'opacity: 0'))
        }
        $lines += New-Keyframes "label$($i + 1)" $labelStops

        # Progress segments fill while their frame holds and stay full until
        # the tour fades back to the start.
        $progressStops = @(, @(0, 'transform: scaleX(0); opacity: 1'))
        if ($i -gt 0) { $progressStops += , @($shown, 'transform: scaleX(0); opacity: 1') }
        if ($i -lt $last) { $progressStops += , @(($next - $fadeSeconds), 'transform: scaleX(1); opacity: 1') }
        $progressStops += @(@(($cycle - $fadeSeconds), 'transform: scaleX(1); opacity: 1'), @($cycle, 'transform: scaleX(1); opacity: 0'))
        $lines += New-Keyframes "progress$($i + 1)" $progressStops
    }
    return $lines
}

function New-Tour([string]$Name, [Collections.IDictionary]$Theme, [string[]]$Frames) {
    $duration = "$(Format-Number $cycle)s"
    $pillHeight = 38
    $pillY = $barCenter - $pillHeight / 2
    $pillX = $windowX + 88
    $badgeX = $pillX + $pillHeight / 2
    $textX = $badgeX + 24
    $segmentWidth = 72
    $segmentGap = 10
    $progressX = $windowX + $imageWidth - 28 - ($steps.Count * $segmentWidth + ($steps.Count - 1) * $segmentGap)

    $css = @(
        '  text { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans", Helvetica, Arial, sans-serif; }'
        '  .frame, .label { opacity: 0; }'
        '  .frame1, .label1 { opacity: 1; }'
        '  .progress { transform: scaleX(0); transform-box: fill-box; transform-origin: 0 0; }'
        '  .progress1 { transform: scaleX(1); }'
    )
    $css += New-Animations
    for ($i = 2; $i -le $steps.Count; $i++) {
        $css += "  .frame$i { animation: frame$i $duration ease-in-out infinite both; }"
    }
    for ($i = 1; $i -le $steps.Count; $i++) {
        $css += "  .label$i { animation: label$i $duration ease-in-out infinite both; }"
        $css += "  .progress$i { animation: progress$i $duration linear infinite both; }"
    }
    $css += @(
        '  @media (prefers-reduced-motion: reduce) {'
        '    * { animation: none !important; }'
        '    .frame, .label { opacity: 0; }'
        '    .frame1, .label1 { opacity: 1; }'
        '    .progress { transform: scaleX(0); }'
        '    .progress1 { transform: scaleX(1); }'
        '  }'
    )

    $windowRect = "x=`"$windowX`" y=`"$windowY`" width=`"$imageWidth`" height=`"$windowHeight`" rx=`"$radius`""
    $lines = @(
        "<svg xmlns=`"http://www.w3.org/2000/svg`" width=`"$canvasWidth`" height=`"$canvasHeight`" viewBox=`"0 0 $canvasWidth $canvasHeight`" role=`"img`" aria-labelledby=`"title desc`">"
        "<title id=`"title`">$title</title>"
        "<desc id=`"desc`">$description</desc>"
        '<defs>'
        "  <clipPath id=`"window`"><rect $windowRect/></clipPath>"
        '  <filter id="shadow" x="-5%" y="-5%" width="110%" height="112%" color-interpolation-filters="sRGB">'
        "    <feDropShadow dx=`"0`" dy=`"2`" stdDeviation=`"2`" flood-color=`"$($Theme.Shadow)`" flood-opacity=`"$($Theme.NearOpacity)`"/>"
        "    <feDropShadow dx=`"0`" dy=`"12`" stdDeviation=`"16`" flood-color=`"$($Theme.Shadow)`" flood-opacity=`"$($Theme.FarOpacity)`"/>"
        '  </filter>'
        '</defs>'
        '<style>'
    )
    $lines += $css
    $lines += @(
        '</style>'
        "<rect $windowRect fill=`"$($Theme.Bar)`" filter=`"url(#shadow)`"/>"
        '<g clip-path="url(#window)">'
        "  <rect x=`"$windowX`" y=`"$windowY`" width=`"$imageWidth`" height=`"$barHeight`" fill=`"$($Theme.Bar)`"/>"
    )
    for ($i = 0; $i -lt $Frames.Count; $i++) {
        $lines += "  <image class=`"frame frame$($i + 1)`" x=`"$windowX`" y=`"$imageY`" width=`"$imageWidth`" height=`"$imageHeight`" href=`"data:image/png;base64,$($Frames[$i])`"/>"
    }
    $lines += @(
        "  <rect x=`"$windowX`" y=`"$($imageY - 1)`" width=`"$imageWidth`" height=`"1`" fill=`"$($Theme.Border)`"/>"
        '</g>'
        "<rect x=`"$(Format-Number ($windowX + 0.5))`" y=`"$(Format-Number ($windowY + 0.5))`" width=`"$($imageWidth - 1)`" height=`"$($windowHeight - 1)`" rx=`"$(Format-Number ($radius - 0.5))`" fill=`"none`" stroke=`"$($Theme.Border)`"/>"
        "<g fill=`"$($Theme.Dot)`">"
    )
    foreach ($offset in @(26, 46, 66)) {
        $lines += "  <circle cx=`"$($windowX + $offset)`" cy=`"$barCenter`" r=`"6`"/>"
    }
    $lines += '</g>'
    $lines += "<text x=`"$($windowX + $imageWidth / 2)`" y=`"$(Format-Number ($barCenter + 5))`" font-size=`"15`" fill=`"$($Theme.Muted)`" text-anchor=`"middle`">Foundry Agent Lab</text>"
    for ($i = 0; $i -lt $steps.Count; $i++) {
        $step = $steps[$i]
        $pillWidth = ($textX - $pillX) + $step.Width + 18
        $lines += @(
            "<g class=`"label label$($i + 1)`">"
            "  <rect x=`"$pillX`" y=`"$pillY`" width=`"$pillWidth`" height=`"$pillHeight`" rx=`"$($pillHeight / 2)`" fill=`"$($Theme.Pill)`" stroke=`"$($Theme.Border)`"/>"
            "  <circle cx=`"$badgeX`" cy=`"$barCenter`" r=`"13`" fill=`"$($Theme.Accent)`"/>"
            "  <text x=`"$badgeX`" y=`"$(Format-Number ($barCenter + 5.5))`" font-size=`"15`" font-weight=`"700`" fill=`"$($Theme.AccentText)`" text-anchor=`"middle`">$($i + 1)</text>"
            "  <text x=`"$textX`" y=`"$(Format-Number ($barCenter + 7))`" font-size=`"20`" font-weight=`"600`" fill=`"$($Theme.PillText)`" textLength=`"$($step.Width)`" lengthAdjust=`"spacing`">$($step.Label)</text>"
            '</g>'
        )
    }
    $lines += '<g>'
    for ($i = 0; $i -lt $steps.Count; $i++) {
        $x = $progressX + $i * ($segmentWidth + $segmentGap)
        $lines += "  <rect x=`"$x`" y=`"$($barCenter - 3)`" width=`"$segmentWidth`" height=`"6`" rx=`"3`" fill=`"$($Theme.Track)`"/>"
        $lines += "  <rect class=`"progress progress$($i + 1)`" x=`"$x`" y=`"$($barCenter - 3)`" width=`"$segmentWidth`" height=`"6`" rx=`"3`" fill=`"$($Theme.Accent)`"/>"
    }
    $lines += @('</g>', '</svg>')
    return ($lines -join "`n") + "`n"
}

function Test-Tour([string]$Content, [string]$Name) {
    [xml]$validated = $Content
    if ($validated.DocumentElement.LocalName -ne 'svg') { throw "Invalid tour: $Name" }
    # GitHub shows README SVGs as images: no scripts and no external resources.
    $markup = [regex]::Replace($Content, '(?<=data:image/png;base64,)[A-Za-z0-9+/=]+', '')
    if ($markup -match '<script|<foreignObject|\son[a-z]+=') { throw "The $Name tour must not contain scripts." }
    $references = [regex]::Matches($markup, '\b(?:href|src)="([^"]*)"') | ForEach-Object { $_.Groups[1].Value }
    if (@($references | Where-Object { $_ -ne 'data:image/png;base64,' }).Count) {
        throw "The $Name tour must embed every image."
    }
    if ($markup -match 'url\((?!#)|@import') { throw "The $Name tour must not load external resources." }
    if ($validated.DocumentElement['title'].InnerText -notmatch 'Foundry Agent Lab') {
        throw "The $Name tour must have a title."
    }
}

# Build every variant before writing any, so a failure leaves no partial outputs.
$outputs = [ordered]@{}
foreach ($name in $themes.Keys) {
    $theme = $themes[$name]
    $frames = @($steps | ForEach-Object { Get-Screenshot $_[$theme.Screenshot] })
    $content = New-Tour $name $theme $frames
    Test-Tour $content $name
    $outputs[(Join-Path $PSScriptRoot "$name.svg")] = $content
}

foreach ($output in $outputs.Keys) {
    [IO.File]::WriteAllText($output, $outputs[$output], [Text.UTF8Encoding]::new($false))
    $size = (Get-Item -LiteralPath $output).Length
    Write-Output ('Built self-contained tour: {0} ({1:N0} KB)' -f $output, ($size / 1KB))
}

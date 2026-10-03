# Lists the top-level files that .dockerignore lets into the image build context,
# so build.ps1 stages exactly what Docker would send and keeps no file list of its own.
function Get-ImageContextFile {
    param([Parameter(Mandatory)][string]$Root)
    $rules = @(Get-Content -LiteralPath (Join-Path $Root '.dockerignore') |
        ForEach-Object { $_.Trim() } |
        Where-Object { $_ -and -not $_.StartsWith('#') })
    foreach ($file in Get-ChildItem -LiteralPath $Root -File -Force) {
        # The last matching rule wins; Docker always sends the Dockerfile and .dockerignore.
        $ignored = $false
        foreach ($rule in $rules) {
            if ($file.Name -clike $rule.TrimStart('!')) { $ignored = -not $rule.StartsWith('!') }
        }
        if (-not $ignored -or $file.Name -in @('Dockerfile', '.dockerignore')) { $file.Name }
    }
}

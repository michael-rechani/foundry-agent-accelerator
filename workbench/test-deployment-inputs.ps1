param([string]$TerraformCommand = 'terraform')
$ErrorActionPreference = 'Stop'
$temporary = Join-Path ([IO.Path]::GetTempPath()) ('workbench-inputs-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $temporary | Out-Null
try {
    Copy-Item (Join-Path $PSScriptRoot 'infra/deployment-inputs.tf') $temporary
    $result = & $TerraformCommand "-chdir=$temporary" init -backend=false -input=false -no-color 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Initialization failed: $result" }
    $cases = @(
        @{ Name = 'missing deployment image rejected'; Arguments = @(); Error = 'image_digest is required' },
        @{ Name = 'explicit bootstrap allowed'; Arguments = @('-var=bootstrap_only=true'); Error = $null },
        @{ Name = 'mutable tag rejected'; Arguments = @('-var=image_digest=latest'); Error = 'immutable SHA-256' },
        @{ Name = 'immutable image accepted'; Arguments = @('-var=image_digest=sha256:' + ('a' * 64)); Error = $null }
    )
    foreach ($case in $cases) {
        $arguments = @("-chdir=$temporary", 'plan', '-input=false', '-refresh=false', '-no-color') + $case.Arguments
        $result = & $TerraformCommand @arguments 2>&1
        if (($LASTEXITCODE -eq 0) -ne ($null -eq $case.Error)) { throw "Unexpected result for $($case.Name): $result" }
        if ($case.Error -and ($result -join "`n") -notmatch $case.Error) { throw "Unexpected error: $result" }
        Write-Output "PASS: $($case.Name)"
    }
} finally {
    Remove-Item $temporary -Recurse -Force
}
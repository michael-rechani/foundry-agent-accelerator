param([string]$TerraformCommand = 'terraform')

$ErrorActionPreference = 'Stop'
$providerDirectory = Join-Path $PSScriptRoot 'infra/.terraform/providers'
if (!(Test-Path -LiteralPath $providerDirectory)) {
    throw 'Initialize the Lab infrastructure providers before running offline monitoring tests.'
}
$temporary = Join-Path ([IO.Path]::GetTempPath()) ('workbench-monitoring-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path (Join-Path $temporary 'tests') -Force | Out-Null
try {
    foreach ($source in @('monitoring.tf', 'alert-delivery.tf', '.terraform.lock.hcl')) {
        Copy-Item -LiteralPath (Join-Path $PSScriptRoot "infra/$source") -Destination $temporary
    }
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'tests/fixtures/monitoring-dependencies.tf.tftpl') -Destination (Join-Path $temporary 'dependencies.tf')
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'tests/monitoring.tftest.hcl') -Destination (Join-Path $temporary 'tests')
    $formatting = & $TerraformCommand "-chdir=$temporary" fmt -check -recursive -no-color 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Monitoring fixture formatting failed: $formatting" }
    $initialization = & $TerraformCommand "-chdir=$temporary" init -backend=false -input=false -lockfile=readonly -no-color "-plugin-dir=$providerDirectory" 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Isolated monitoring initialization failed: $initialization" }
    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $testOutput = @(& $TerraformCommand "-chdir=$temporary" test -no-color 2>&1)
        $testExitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    $testOutput | ForEach-Object { Write-Output "$_" }
    if ($testExitCode -ne 0 -or ($testOutput -join "`n") -notmatch 'Success! [1-9][0-9]* passed, 0 failed\.') {
        throw 'Offline monitoring tests failed or no tests executed.'
    }
} finally {
    # Windows can briefly retain a lock on a just-exited provider executable.
    for ($attempt = 0; $attempt -lt 6; $attempt++) {
        try {
            Remove-Item -LiteralPath $temporary -Recurse -Force
            break
        } catch [System.IO.IOException], [System.UnauthorizedAccessException] {
            if ($attempt -eq 5) { throw }
            Start-Sleep -Milliseconds 500
        }
    }
}

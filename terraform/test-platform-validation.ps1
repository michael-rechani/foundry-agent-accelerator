param(
    [string]$TerraformCommand = 'terraform'
)

$ErrorActionPreference = 'Stop'
$temporary = Join-Path ([IO.Path]::GetTempPath()) ('platform-validation-' + [guid]::NewGuid().ToString('N'))
$providerDirectory = Join-Path $PSScriptRoot '.terraform/providers'
$moduleDirectory = Join-Path $PSScriptRoot '.terraform/modules'
if (!(Test-Path $providerDirectory) -or !(Test-Path $moduleDirectory)) {
    throw 'Initialize the platform providers and modules before running offline validation.'
}
New-Item -ItemType Directory -Path (Join-Path $temporary '.terraform') -Force | Out-Null
try {
    foreach ($source in @('versions.tf', 'variables.tf', 'region-preferences.tf', 'naming.tf', 'management-network.tf', 'keyless-accounts.tf', 'keyless-storage.tf', 'jumpbox.tf')) {
        Copy-Item (Join-Path $PSScriptRoot $source) $temporary
    }
    Copy-Item (Join-Path $PSScriptRoot 'tests/fixtures/platform-dependencies.tf') (Join-Path $temporary 'dependencies.tf')
    Copy-Item (Join-Path $PSScriptRoot '.terraform.lock.hcl') $temporary
    Copy-Item $moduleDirectory (Join-Path $temporary '.terraform/modules') -Recurse
    Copy-Item (Join-Path $PSScriptRoot 'tests') $temporary -Recurse
    $initialization = & $TerraformCommand "-chdir=$temporary" init -backend=false -input=false -no-color "-plugin-dir=$providerDirectory" 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Isolated initialization failed: $initialization" }
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
        throw 'Offline platform tests failed or no tests executed.'
    }
} finally {
    Remove-Item $temporary -Recurse -Force
}

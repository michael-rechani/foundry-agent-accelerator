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
    # Copy the whole root module so a new or renamed file is tested without editing this list.
    $rootFiles = @(Get-ChildItem $PSScriptRoot -Filter '*.tf' -File)
    foreach ($required in @('main.tf', 'network.tf', 'apim.tf', 'review-api.tf')) {
        $testName = [IO.Path]::GetFileNameWithoutExtension($required)
        if ($rootFiles.Name -notcontains $required) { throw "Root module file $required is missing, so its tests would silently stop covering it." }
        if (!(Test-Path (Join-Path $PSScriptRoot "tests/$testName.tftest.hcl"))) { throw "No assertion tests cover $required; add tests/$testName.tftest.hcl." }
    }
    # Terraform's mock providers can't run ephemeral resources, which the Foundry registry module and the jump box
    # credential read use. These swaps stand in for just those pieces. A swap that no longer matches fails loudly,
    # so the root file can't drift out of coverage unnoticed.
    $substitutions = @(
        @{ File = 'main.tf'; Pattern = '(?m)^(\s*)source\s*=\s*"Azure/avm-ptn-aiml-ai-foundry/azurerm"\s*\r?\n\s*version\s*=\s*"[^"]+"'; Replacement = '${1}source = "./tests/fixtures/foundry"' },
        @{ File = 'apim.tf'; Pattern = '(?m)^(\s*)source\s*=\s*"Azure/avm-res-apimanagement-service/azurerm"\s*\r?\n\s*version\s*=\s*"[^"]+"'; Replacement = '${1}source = "./tests/fixtures/api-management"' },
        @{ File = 'jumpbox-credentials.tf'; Pattern = 'ephemeral\.azurerm_key_vault_secret\.jumpbox_admin\[0\]\.value'; Replacement = '"synthetic-offline-fixture-only"' },
        @{ File = 'jumpbox-credentials.tf'; Pattern = '(?s)ephemeral "azurerm_key_vault_secret" "jumpbox_admin" \{.*?\r?\n\}\r?\n?'; Replacement = '' }
    )
    foreach ($file in $rootFiles) {
        $copied = Join-Path $temporary $file.Name
        Copy-Item $file.FullName $copied
        $text = [IO.File]::ReadAllText($copied)
        foreach ($substitution in @($substitutions | Where-Object { $_.File -eq $file.Name })) {
            if ($text -notmatch $substitution.Pattern) { throw "Offline substitution no longer matches $($file.Name): $($substitution.Pattern). Update test-platform-validation.ps1." }
            $text = [regex]::Replace($text, $substitution.Pattern, $substitution.Replacement)
        }
        if ($text -match '(?m)^\s*ephemeral\s+"') { throw "$($file.Name) still declares an ephemeral resource, which Terraform's mock providers can't run." }
        if (!($substitutions | Where-Object { $_.File -eq $file.Name })) {
            if ((Get-FileHash $copied).Hash -ne (Get-FileHash $file.FullName).Hash) { throw "Root module file $($file.Name) was not copied intact into the isolated module." }
        } else {
            [IO.File]::WriteAllText($copied, $text, [Text.UTF8Encoding]::new($false))
        }
    }
    Copy-Item (Join-Path $PSScriptRoot 'policies') $temporary -Recurse
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

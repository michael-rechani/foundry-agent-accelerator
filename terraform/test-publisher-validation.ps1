param(
    [string]$TerraformCommand = 'terraform'
)

$ErrorActionPreference = 'Stop'
$temporary = Join-Path ([IO.Path]::GetTempPath()) ('publisher-validation-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $temporary | Out-Null
try {
    Copy-Item (Join-Path $PSScriptRoot 'variables.tf') (Join-Path $temporary 'variables.tf')
    $initialization = & $TerraformCommand "-chdir=$temporary" init -backend=false -input=false -no-color 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Isolated initialization failed: $initialization" }
    $cases = @(
        @{ Name = 'disabled without email'; Enabled = 'false'; Email = $null; Valid = $true },
        @{ Name = 'enabled without email'; Enabled = 'true'; Email = $null; Valid = $false },
        @{ Name = 'enabled with blank email'; Enabled = 'true'; Email = ''; Valid = $false },
        @{ Name = 'enabled with malformed email'; Enabled = 'true'; Email = 'invalid'; Valid = $false },
        @{ Name = 'disabled with malformed email'; Enabled = 'false'; Email = 'invalid'; Valid = $false },
        @{ Name = 'enabled with valid email'; Enabled = 'true'; Email = 'owner@example.com'; Valid = $true }
    )
    foreach ($case in $cases) {
        $arguments = @(
            "-chdir=$temporary", 'plan', '-input=false', '-refresh=false', '-no-color',
            '-var=subscription_id=00000000-0000-0000-0000-000000000000',
            "-var=enable_api_management=$($case.Enabled)"
        )
        if ($null -ne $case.Email) { $arguments += "-var=api_management_publisher_email=$($case.Email)" }
        $previousErrorActionPreference = $ErrorActionPreference
        try {
            $ErrorActionPreference = 'Continue'
            $result = & $TerraformCommand @arguments 2>&1
            $succeeded = $LASTEXITCODE -eq 0
        } finally {
            $ErrorActionPreference = $previousErrorActionPreference
        }
        if ($succeeded -ne $case.Valid) { throw "Unexpected result for $($case.Name): $result" }
        if (!$case.Valid -and ($result -join "`n") -notmatch 'api_management_publisher_email must be a valid email') {
            throw "Unexpected validation failure for $($case.Name): $result"
        }
        Write-Output "PASS: $($case.Name)"
    }
} finally {
    Remove-Item $temporary -Recurse -Force
}
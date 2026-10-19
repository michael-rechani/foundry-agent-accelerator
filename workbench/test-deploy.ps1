#Requires -Version 7.0
# Checks deploy.ps1's helpers and stage ordering. It never contacts Azure or runs Terraform.
$ErrorActionPreference = 'Stop'
$script = Join-Path $PSScriptRoot '../deploy.ps1'
$subscription = '11111111-2222-3333-4444-555555555555'
. $script -Subscription $subscription

function Assert-Equal($Expected, $Actual, [string]$Name) {
    if ($Expected -ne $Actual) { throw "$Name failed: expected '$Expected', got '$Actual'." }
}

$parse = $null
[void][Management.Automation.Language.Parser]::ParseFile((Resolve-Path $script), [ref]$null, [ref]$parse)
Assert-Equal 0 $parse.Count 'deploy.ps1 parses without errors'

Assert-Equal 'preflight,platform,verify' ((Get-StageOrder @('verify', 'platform', 'preflight')) -join ',') 'stages run in the fixed order'
Assert-Equal 'agents' ((Get-StageOrder @('agents')) -join ',') 'agents can run alone'
Assert-Equal '' ((Get-StageOrder @()) -join ',') 'no stages selected'

foreach ($address in '10.1.2.3', '172.16.0.1', '172.31.255.1', '192.168.1.1') { Assert-Equal $true (Test-PrivateAddress $address) "$address is private" }
foreach ($address in '8.8.8.8', '172.32.0.1', '100.64.0.1', '20.1.2.3', '::1') { Assert-Equal $false (Test-PrivateAddress $address) "$address is not private" }

$registry = Get-RegistryName $subscription 'aifnd'
Assert-Equal $registry (Get-RegistryName $subscription.ToUpperInvariant() 'aifnd') 'registry name ignores subscription case'
if ($registry -notmatch '^[a-z0-9]{5,50}$') { throw "Registry name '$registry' breaks the Lab's naming rule." }
if ($registry -eq (Get-RegistryName '99999999-2222-3333-4444-555555555555' 'aifnd')) { throw 'Registry names must differ across subscriptions.' }

$digest = 'sha256:' + ('a' * 64)
Assert-Equal $digest (Get-ImageDigest @('building', "reg.azurecr.io/workbench@$digest", 'PRIVATE_BUILD_PUSH_AND_PULL_VERIFIED=True')) 'digest is read from the build output'
try { Get-ImageDigest @('no digest here'); throw 'missing digest accepted' } catch { if ($_.Exception.Message -notmatch 'did not report') { throw } }

$hcl = New-BackendHcl 'stexample' 'ai-foundry/dev.tfstate'
foreach ($expected in 'storage_account_name = "stexample"', 'key                  = "ai-foundry/dev.tfstate"', 'use_azuread_auth     = true', "subscription_id      = ""$subscription""") {
    if ($hcl -notmatch [regex]::Escape($expected)) { throw "Backend config lacks: $expected" }
}

$temporary = Join-Path ([IO.Path]::GetTempPath()) ('deploy-test-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $temporary | Out-Null
try {
    $file = Join-Path $temporary 'x.tfvars'
    Set-Content -LiteralPath $file -Value "registry_name = `"abc123`"`n# image = `"no`""
    Assert-Equal 'abc123' (Get-TfvarsValue $file 'registry_name') 'tfvars value is read'
    Assert-Equal $null (Get-TfvarsValue $file 'missing') 'missing tfvars value is null'
    Write-NewFile $file 'overwritten' | Out-Null
    if ((Get-Content -LiteralPath $file -Raw) -match 'overwritten') { throw 'An existing input file was overwritten.' }
} finally {
    Remove-Item -LiteralPath $temporary -Recurse -Force
}

Write-Host 'deploy.ps1 helper checks passed.'

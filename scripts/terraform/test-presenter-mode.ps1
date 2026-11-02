param(
    [string]$TerraformCommand = 'terraform'
)

$ErrorActionPreference = 'Stop'
$repositoryRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$sourcePath = Join-Path $repositoryRoot -ChildPath 'workbench' -AdditionalChildPath @('infra', 'main.tf')
$source = Get-Content -LiteralPath $sourcePath -Raw

$variables = foreach ($name in @('agent_creation_enabled', 'private_presenter_mode', 'agent_creation_model', 'agent_creation_key_secret_id')) {
    $match = [regex]::Match($source, "(?ms)^variable `"$name`"\s*\{.*?^\}")
    if (!$match.Success) { throw "Missing Terraform variable: $name" }
    $match.Value
}
$guard = [regex]::Match($source, '(?ms)^resource "azurerm_container_app" "this"\s*\{.*?precondition\s*\{\s*condition\s*=\s*(?<condition>[^\r\n]+)\s*error_message\s*=\s*(?<message>"[^"\r\n]+")')
if (!$guard.Success) { throw 'Missing Container App creation precondition.' }
$keyEnvironment = [regex]::Match($source, '(?s)dynamic "env"\s*\{\s*for_each\s*=\s*(?<selector>[^\r\n]+)\s*content\s*\{\s*name\s*=\s*"WORKBENCH_CREATION_KEY_SHA256"\s*secret_name\s*=\s*"agent-creation-key-verifier"')
if (!$keyEnvironment.Success) { throw 'Missing conditional operator-key environment setting.' }

$environmentSettings = foreach ($name in @('WORKBENCH_MODE', 'WORKBENCH_AGENT_CREATION_ENABLED', 'WORKBENCH_PRIVATE_PRESENTER_MODE', 'WORKBENCH_AGENT_CREATION_MODEL')) {
    $match = [regex]::Match($source, "(?m)^\s*$name\s*=\s*(?<value>[^\r\n]+)")
    if (!$match.Success) { throw "Missing Container App environment setting: $name" }
    "    $name = $($match.Groups['value'].Value)"
}
$environment = [regex]::Match($source, '(?ms)^resource "azurerm_container_app_environment" "this"\s*\{.*?^\}')
if (!$environment.Success -or
    $environment.Value -notmatch '(?m)^\s*internal_load_balancer_enabled\s*=\s*true\s*$' -or
    $environment.Value -notmatch '(?m)^\s*public_network_access\s*=\s*"Disabled"\s*$') {
    throw 'The Container Apps environment must remain private and internal.'
}

$temporary = Join-Path ([IO.Path]::GetTempPath()) ('presenter-validation-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $temporary | Out-Null
try {
    $configuration = @"
$($variables -join "`n")

resource "terraform_data" "settings" {
  input = {
$($environmentSettings -join "`n")
    key_environment = $($keyEnvironment.Groups['selector'].Value)
  }
  lifecycle {
    precondition {
      condition     = $($guard.Groups['condition'].Value)
      error_message = $($guard.Groups['message'].Value)
    }
  }
}
"@
    Set-Content -LiteralPath (Join-Path $temporary 'main.tf') -Value $configuration -Encoding utf8
    $initialization = & $TerraformCommand "-chdir=$temporary" init -backend=false -input=false -no-color 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Isolated initialization failed: $initialization" }

    $cases = @(
        @{ Name = 'presenter mode defaults off'; Arguments = @(); Valid = $true; Presenter = 'false'; Creation = 'false'; Model = ''; KeyCount = 0 },
        @{ Name = 'creation requires a key by default'; Arguments = @('-var=agent_creation_enabled=true', '-var=agent_creation_model=demo-model'); Valid = $false },
        @{ Name = 'presenter mode permits keyless creation'; Arguments = @('-var=agent_creation_enabled=true', '-var=agent_creation_model=demo-model', '-var=private_presenter_mode=true'); Valid = $true; Presenter = 'true'; Creation = 'true'; Model = 'demo-model'; KeyCount = 0 },
        @{ Name = 'presenter mode still requires a model'; Arguments = @('-var=agent_creation_enabled=true', '-var=private_presenter_mode=true'); Valid = $false },
        @{ Name = 'operator key still works without presenter mode'; Arguments = @('-var=agent_creation_enabled=true', '-var=agent_creation_model=demo-model', '-var=agent_creation_key_secret_id=https://unit-test.vault.azure.net/secrets/verifier'); Valid = $true; Presenter = 'false'; Creation = 'true'; Model = 'demo-model'; KeyCount = 1 },
        @{ Name = 'presenter mode preserves an existing verifier'; Arguments = @('-var=agent_creation_enabled=true', '-var=agent_creation_model=demo-model', '-var=private_presenter_mode=true', '-var=agent_creation_key_secret_id=https://unit-test.vault.azure.net/secrets/verifier'); Valid = $true; Presenter = 'true'; Creation = 'true'; Model = 'demo-model'; KeyCount = 1 }
    )
    foreach ($case in $cases) {
        $plan = Join-Path $temporary 'case.tfplan'
        $arguments = @("-chdir=$temporary", 'plan', '-input=false', '-refresh=false', '-no-color', "-out=$plan") + $case.Arguments
        $previousErrorActionPreference = $ErrorActionPreference
        try {
            $ErrorActionPreference = 'Continue'
            $result = & $TerraformCommand @arguments 2>&1
            $succeeded = $LASTEXITCODE -eq 0
        } finally {
            $ErrorActionPreference = $previousErrorActionPreference
        }
        if ($succeeded -ne $case.Valid) { throw "Unexpected result for $($case.Name): $result" }
        if (!$case.Valid) {
            $output = ($result -join ' ') -replace '\s+', ' '
            $message = $guard.Groups['message'].Value.Trim('"') -replace '\s+', ' '
            if ($output -notmatch [regex]::Escape($message)) {
                throw "Unexpected validation failure for $($case.Name): $result"
            }
        } else {
            $json = & $TerraformCommand "-chdir=$temporary" show -json $plan
            if ($LASTEXITCODE -ne 0) { throw "Could not inspect plan for $($case.Name)." }
            $settings = ($json | ConvertFrom-Json).planned_values.root_module.resources[0].values.input
            if ($settings.WORKBENCH_MODE -ne 'private' -or
                $settings.WORKBENCH_PRIVATE_PRESENTER_MODE -ne $case.Presenter -or
                $settings.WORKBENCH_AGENT_CREATION_ENABLED -ne $case.Creation -or
                $settings.WORKBENCH_AGENT_CREATION_MODEL -ne $case.Model -or
                @($settings.key_environment).Count -ne $case.KeyCount) {
                throw "Unexpected planned environment for $($case.Name)."
            }
        }
        Write-Output "PASS: $($case.Name)"
    }
} finally {
    Remove-Item -LiteralPath $temporary -Recurse -Force
}

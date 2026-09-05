param(
    [string]$TerraformCommand = 'terraform'
)

$ErrorActionPreference = 'Stop'
$temporary = Join-Path ([IO.Path]::GetTempPath()) ('review-api-validation-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $temporary | Out-Null
try {
    Copy-Item (Join-Path $PSScriptRoot 'variables.tf') (Join-Path $temporary 'variables.tf')
    $initialization = & $TerraformCommand "-chdir=$temporary" init -backend=false -input=false -no-color 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Isolated initialization failed: $initialization" }
    $guid = '11111111-1111-1111-1111-111111111111'
    $cases = @(
        @{ Name = 'unpublished by default'; Enabled = 'false'; Config = $null; Valid = $true },
        @{ Name = 'APIM disabled'; Enabled = 'false'; Config = @{ audience = $guid; allowed_caller_object_ids = @($guid); allowed_client_app_ids = @($guid) }; Valid = $false },
        @{ Name = 'valid dedicated audience'; Enabled = 'true'; Config = @{ audience = "api://$guid"; allowed_caller_object_ids = @($guid); allowed_client_app_ids = @($guid) }; Valid = $true },
        @{ Name = 'valid v2 audience'; Enabled = 'true'; Config = @{ audience = $guid; allowed_caller_object_ids = @($guid); allowed_client_app_ids = @($guid) }; Valid = $true },
        @{ Name = 'general Azure audience rejected'; Enabled = 'true'; Config = @{ audience = 'https://management.azure.com/'; allowed_caller_object_ids = @($guid); allowed_client_app_ids = @($guid) }; Valid = $false },
        @{ Name = 'empty caller allowlist'; Enabled = 'true'; Config = @{ audience = $guid; allowed_caller_object_ids = @(); allowed_client_app_ids = @($guid) }; Valid = $false },
        @{ Name = 'empty client allowlist'; Enabled = 'true'; Config = @{ audience = $guid; allowed_caller_object_ids = @($guid); allowed_client_app_ids = @() }; Valid = $false },
        @{ Name = 'invalid caller ID'; Enabled = 'true'; Config = @{ audience = $guid; allowed_caller_object_ids = @('*'); allowed_client_app_ids = @($guid) }; Valid = $false },
        @{ Name = 'invalid client ID'; Enabled = 'true'; Config = @{ audience = $guid; allowed_caller_object_ids = @($guid); allowed_client_app_ids = @('*') }; Valid = $false }
        @{ Name = 'swapped coordinator'; Enabled = 'true'; Config = @{ audience = $guid; allowed_caller_object_ids = @($guid); allowed_client_app_ids = @($guid); agent_name = 'customer-review-coordinator' }; Valid = $true },
        @{ Name = 'arbitrary backend rejected'; Enabled = 'true'; Config = @{ audience = $guid; allowed_caller_object_ids = @($guid); allowed_client_app_ids = @($guid); agent_name = 'https://other.example' }; Valid = $false }
    )
    foreach ($case in $cases) {
        $arguments = @(
            "-chdir=$temporary", 'plan', '-input=false', '-refresh=false', '-no-color',
            '-var=subscription_id=00000000-0000-0000-0000-000000000000',
            '-var=api_management_publisher_email=owner@example.com',
            "-var=enable_api_management=$($case.Enabled)"
        )
        if ($null -ne $case.Config) { $arguments += "-var=review_api=$($case.Config | ConvertTo-Json -Compress)" }
        $result = & $TerraformCommand @arguments 2>&1
        $succeeded = $LASTEXITCODE -eq 0
        if ($succeeded -ne $case.Valid) { throw "Unexpected result for $($case.Name): $result" }
        if (!$case.Valid -and ($result -join "`n") -notmatch 'review_api requires') {
            throw "Unexpected validation failure for $($case.Name): $result"
        }
        Write-Output "PASS: $($case.Name)"
    }
    $templatePath = (Join-Path $PSScriptRoot 'policies/review.xml.tftpl').Replace('\', '/') | ConvertTo-Json -Compress
    $bindings = @{
        tenant_id = $guid
        audience = "api://$guid"
        allowed_client_app_ids = @($guid, '22222222-2222-2222-2222-222222222222')
        caller_values = "<value>$guid</value>"
        backend_url = 'https://example.services.ai.azure.com/api/projects/test/agents/customer-review-coordinator/endpoint/protocols/openai'
    } | ConvertTo-Json -Compress
    $expression = "jsonencode(templatefile($templatePath, $bindings))"
    $rendered = $expression | & $TerraformCommand "-chdir=$temporary" console '-var=subscription_id=00000000-0000-0000-0000-000000000000' 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Policy rendering failed: $rendered" }
    $xmlText = (($rendered -join "`n") | ConvertFrom-Json) | ConvertFrom-Json
    $policy = [xml]$xmlText
    $auth = $policy.policies.inbound.'validate-azure-ad-token'
    if ($auth.'tenant-id' -ne $guid -or $auth.audiences.audience -ne "api://$guid" -or
        @($auth.'client-application-ids'.'application-id').Count -ne 2 -or
        $auth.'required-claims'.claim.name -ne 'oid' -or $auth.'required-claims'.claim.value -ne $guid) {
        throw 'Policy lost an authorization constraint'
    }
    if ($policy.policies.inbound.'set-backend-service'.'base-url' -notmatch '/agents/customer-review-coordinator/endpoint/protocols/openai$' -or
        $policy.policies.inbound.'authentication-managed-identity'.resource -ne 'https://ai.azure.com' -or
        $policy.policies.inbound.'rewrite-uri'.'copy-unmatched-params' -ne 'false' -or
        $policy.policies.inbound.'validate-content'.'max-size' -ne '65536' -or
        $policy.policies.inbound.'rate-limit-by-key'.calls -ne '10' -or
        $policy.policies.backend.'forward-request'.timeout -ne '180') {
        throw 'Policy lost a backend or request constraint'
    }
    if ($policy.policies.inbound.'set-body' -notmatch 'JProperty\("store", false\)' -or
        $policy.policies.inbound.'set-body' -notmatch 'JProperty\("stream", false\)' -or
        $policy.policies.'on-error'.'return-response'.'set-body' -match 'LastError\.(Message|Details)') {
        throw 'Policy lost a storage or error-sanitization constraint'
    }
    Write-Output 'PASS: Terraform-rendered policy XML and security controls'
} finally {
    Remove-Item $temporary -Recurse -Force
}
#Requires -Version 5.1
# Exercises the legacy importer with fictional inputs and mocked CLI commands.
$ErrorActionPreference = 'Stop'
$importer = Join-Path $PSScriptRoot 'import-live.ps1'
$temporary = Join-Path ([IO.Path]::GetTempPath()) ('runner-import-test-' + [guid]::NewGuid().ToString('N'))
$subscription = '11111111-2222-3333-4444-555555555555'
$resourceGroup = "/subscriptions/$subscription/resourceGroups/rg-runner-aifnd-dev"
$vm = "$resourceGroup/providers/Microsoft.Compute/virtualMachines/vm-runner-aifnd-dev"
$nsg = "$resourceGroup/providers/Microsoft.Network/networkSecurityGroups/nsg-runner-aifnd-dev"
$fixtureRoleGuid = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
$fixtureRoleId = "/subscriptions/$subscription/providers/Microsoft.Authorization/roleDefinitions/$fixtureRoleGuid"
$fixtureAssignmentId = "$vm/providers/Microsoft.Authorization/roleAssignments/aaaaaaaa-1111-2222-3333-bbbbbbbbbbbb"
$varFile = Join-Path $temporary 'runner.tfvars'
$exitCodeVariable = Get-Variable -Name LASTEXITCODE -Scope Global -ErrorAction SilentlyContinue
$hadExitCode = $null -ne $exitCodeVariable
$previousExitCode = if ($hadExitCode) { $exitCodeVariable.Value } else { $null }
$test = [pscustomobject]@{
    terraformCalls = $null
    azureCalls = $null
    imports = $null
    stateExit = 0
    azureFailure = ''
    failImport = ''
    resources = @()
    stateJson = ''
}

function Assert-Equal($Expected, $Actual, [string] $Name) {
    if ($Expected -ne $Actual) { throw "$Name failed: expected '$Expected', got '$Actual'." }
}

function Expect-Failure([string] $Name, [string] $Pattern, [scriptblock] $Action) {
    $failure = $null
    try { & $Action 6>$null | Out-Null } catch { $failure = $_ }
    if ($null -eq $failure) { throw "$Name unexpectedly succeeded." }
    if ($failure.Exception.Message -notmatch $Pattern) {
        throw "$Name failed with an unexpected error: $($failure.Exception.Message)"
    }
}

function New-Resource([string] $Address, [string] $Id) {
    [ordered]@{ address = $Address; mode = 'managed'; values = @{ id = $Id } }
}

function Set-State([object[]] $Resources, [object[]] $ChildModules) {
    $test.resources = @($Resources)
    $rootModule = @{ resources = $test.resources }
    if ($PSBoundParameters.ContainsKey('ChildModules')) {
        $rootModule.child_modules = $ChildModules
    }
    $test.stateJson = @{
        format_version = '1.0'
        values = @{
            root_module = $rootModule
            outputs = @{ fixture = @{ sensitive = $true; value = 'fictional-sensitive-state-value' } }
        }
    } | ConvertTo-Json -Depth 20 -Compress
}

function Reset-Fakes {
    $test.terraformCalls = [Collections.Generic.List[string]]::new()
    $test.azureCalls = [Collections.Generic.List[string]]::new()
    $test.imports = [Collections.Generic.List[string]]::new()
    $test.stateExit = 0
    $test.azureFailure = ''
    $test.failImport = ''
    Set-State @(
        (New-Resource 'azurerm_resource_group.runner' $resourceGroup)
        (New-Resource 'azurerm_linux_virtual_machine.runner' $vm)
        (New-Resource 'azurerm_network_security_group.runner' $nsg)
    )
}

function Set-Inputs([string] $RegistryExpression) {
    @(
        "subscription_id = `"$subscription`""
        'resource_group_name = "rg-test-management"'
        'virtual_network_name = "vnet-test"'
        "registry_private_endpoint_ips = $RegistryExpression"
    ) | Set-Content -LiteralPath $varFile -Encoding utf8
}

function terraform {
    $test.terraformCalls.Add(($args -join ' '))
    if ($args[0] -eq 'state' -and $args[1] -eq 'list') {
        $global:LASTEXITCODE = $test.stateExit
        if ($test.stateExit -eq 0) { $test.resources | ForEach-Object { $_.address } }
        return
    }
    if ($args[0] -eq 'show' -and $args[1] -eq '-json') {
        $global:LASTEXITCODE = $test.stateExit
        if ($test.stateExit -eq 0) { $test.stateJson }
        return
    }
    if ($args[0] -eq 'import') {
        $address = [string] $args[2]
        $test.imports.Add($address)
        $global:LASTEXITCODE = if ($address -eq $test.failImport) { 1 } else { 0 }
        return
    }
    throw "Unexpected Terraform command in test: $($args -join ' ')"
}

function az {
    $test.azureCalls.Add(($args -join ' '))
    $global:LASTEXITCODE = 0
    if ($args[0] -eq 'role' -and $args[1] -eq 'definition') {
        if ($test.azureFailure -eq 'definition') { $global:LASTEXITCODE = 1; return }
        if ($test.azureFailure -eq 'malformed-definition') { return '{invalid-json' }
        if ($test.azureFailure -eq 'empty-definition') { return '[]' }
        $id = if ($test.azureFailure -eq 'wrong-definition') { "$fixtureRoleId-other" } else { $fixtureRoleId }
        return (ConvertTo-Json -InputObject @(@{ name = $fixtureRoleGuid; id = $id }) -Compress)
    }
    if ($args[0] -eq 'role' -and $args[1] -eq 'assignment') {
        if ($test.azureFailure -eq 'assignment') { $global:LASTEXITCODE = 1; return }
        if ($test.azureFailure -eq 'malformed-assignment') { return '{invalid-json' }
        if ($test.azureFailure -eq 'empty-assignment') { return '[]' }
        $roleIndex = [array]::IndexOf($args, '--role')
        if ($roleIndex -lt 0 -or $args[$roleIndex + 1] -ne $fixtureRoleGuid) {
            throw 'The assignment lookup must use the exact role ID.'
        }
        $roleId = if ($test.azureFailure -eq 'wrong-assignment-role') { "$fixtureRoleId-other" } else { $fixtureRoleId }
        $id = if ($test.azureFailure -eq 'wrong-assignment-id') { "$fixtureAssignmentId-other" } else { $fixtureAssignmentId }
        return (ConvertTo-Json -InputObject @(@{ scope = $vm; id = $id; roleDefinitionId = $roleId }) -Compress)
    }
    throw "Unexpected Azure command in test: $($args -join ' ')"
}

foreach ($command in 'terraform', 'az') {
    if ((Get-Command $command -ErrorAction Stop).CommandType -ne 'Function') {
        throw "The $command mock is not the active command; refusing to run the test."
    }
}

New-Item -ItemType Directory -Path $temporary | Out-Null
try {
    Reset-Fakes
    Set-Inputs '["10.1.2.3", "10.1.2.4"]'
    $test.stateExit = 1
    Expect-Failure 'unreadable state' 'runner state' { & $importer -VarFile $varFile -Apply }
    Assert-Equal 0 $test.imports.Count 'unreadable state performs no imports'
    Assert-Equal 0 $test.azureCalls.Count 'unreadable state avoids Azure lookups'

    foreach ($expression in '[]', '[ ]', '[""]', '["   "]', '["999.1.2.3"]', '["10.1.2.3", ""]', '["10.1.2.3", "999.1.2.3"]') {
        Reset-Fakes
        Set-Inputs $expression
        Expect-Failure "invalid registry list $expression" 'registry_private_endpoint_ips' {
            & $importer -VarFile $varFile -Apply
        }
        Assert-Equal 0 $test.terraformCalls.Count 'invalid inputs avoid Terraform'
        Assert-Equal 0 $test.azureCalls.Count 'invalid inputs avoid Azure'
    }

    Reset-Fakes
    Set-Inputs '["10.1.2.3"]'
    Add-Content -LiteralPath $varFile -Value 'registry_private_endpoint_ips = []'
    Expect-Failure 'duplicate registry inputs' 'registry_private_endpoint_ips' { & $importer -VarFile $varFile -Apply }
    Assert-Equal 0 $test.terraformCalls.Count 'duplicate inputs avoid Terraform'

    foreach ($failure in 'empty', 'wrong-resource-group', 'wrong-vm', 'duplicate-vm', 'malformed') {
        Reset-Fakes
        Set-Inputs '["10.1.2.3"]'
        switch ($failure) {
            'empty' { Set-State -Resources @() }
            'wrong-resource-group' {
                Set-State @(
                    (New-Resource 'azurerm_resource_group.runner' '/subscriptions/other/resourceGroups/runner')
                    (New-Resource 'azurerm_linux_virtual_machine.runner' $vm)
                )
            }
            'wrong-vm' {
                Set-State @(
                    (New-Resource 'azurerm_resource_group.runner' $resourceGroup)
                    (New-Resource 'azurerm_linux_virtual_machine.runner' "$vm-other")
                )
            }
            'duplicate-vm' {
                Set-State @(
                    (New-Resource 'azurerm_resource_group.runner' $resourceGroup)
                    (New-Resource 'azurerm_linux_virtual_machine.runner' $vm)
                    (New-Resource 'azurerm_linux_virtual_machine.runner' $vm)
                )
            }
            'malformed' { $test.stateJson = '{invalid-json' }
        }
        Expect-Failure "$failure state" 'runner state' { & $importer -VarFile $varFile -Apply }
        Assert-Equal 0 $test.imports.Count "$failure state performs no imports"
        Assert-Equal 0 $test.azureCalls.Count "$failure state avoids Azure lookups"
    }

    foreach ($failure in 'definition', 'assignment', 'malformed-definition', 'empty-definition',
        'wrong-definition', 'malformed-assignment', 'empty-assignment', 'wrong-assignment-role', 'wrong-assignment-id') {
        Reset-Fakes
        Set-Inputs '["10.1.2.3"]'
        $test.azureFailure = $failure
        Expect-Failure "Azure $failure lookup" 'role' { & $importer -VarFile $varFile -Apply }
        Assert-Equal 0 $test.imports.Count "failed $failure lookup performs no imports"
    }

    foreach ($failure in 'wrong-nsg', 'duplicate-owner') {
        Reset-Fakes
        Set-Inputs '["10.1.2.3"]'
        $nsgAddress = if ($failure -eq 'wrong-nsg') { 'azurerm_network_security_group.runner' } else { 'azurerm_network_security_group.other' }
        $nsgId = if ($failure -eq 'wrong-nsg') { "$nsg-other" } else { $nsg }
        Set-State @(
            (New-Resource 'azurerm_resource_group.runner' $resourceGroup)
            (New-Resource 'azurerm_linux_virtual_machine.runner' $vm)
            (New-Resource $nsgAddress $nsgId)
        )
        Expect-Failure "$failure state" 'runner state' { & $importer -VarFile $varFile -Apply }
        Assert-Equal 0 $test.imports.Count "$failure state performs no imports"
    }

    foreach ($target in 'network-security-group', 'role-definition', 'scoped-role-definition') {
        Reset-Fakes
        Set-Inputs '["10.1.2.3"]'
        $ownedId = switch ($target) {
            'network-security-group' { $nsg }
            'role-definition' { $fixtureRoleId }
            'scoped-role-definition' { "$fixtureRoleId|$resourceGroup" }
        }
        $childModules = @(
            @{
                address = 'module.unrelated'
                resources = @((New-Resource 'module.unrelated.azurerm_network_security_group.other' "$nsg-other"))
            }
            @{
                address = 'module.legacy'
                child_modules = @(@{
                    address = 'module.legacy.module.nested[0]'
                    resources = @((New-Resource 'module.legacy.module.nested[0].azurerm_resource.existing' $ownedId))
                })
            }
        )
        Set-State -Resources @(
            (New-Resource 'azurerm_resource_group.runner' $resourceGroup)
            (New-Resource 'azurerm_linux_virtual_machine.runner' $vm)
        ) -ChildModules $childModules
        Expect-Failure "nested $target ownership" 'already owns an import target' {
            & $importer -VarFile $varFile -Apply
        }
        Assert-Equal 0 $test.imports.Count "nested $target ownership performs no imports"
    }

    Reset-Fakes
    Set-Inputs '["10.1.2.3"]'
    Set-State -Resources $test.resources -ChildModules @(@{
        address = 'module.legacy'
        resources = @((New-Resource 'module.legacy.azurerm_network_security_group.old' $nsg))
    })
    Expect-Failure 'duplicate root and child ownership' 'already owns an import target' {
        & $importer -VarFile $varFile -Apply
    }
    Assert-Equal 0 $test.imports.Count 'duplicate root and child ownership performs no imports'

    foreach ($invalidModule in @(
        @{ address = 'module.bad'; resources = @{ address = 'invalid' } }
        @{ address = 'module.bad'; child_modules = 'invalid' }
        @{ address = 'module.bad'; child_modules = @('invalid') }
        @{ resources = @() }
    )) {
        Reset-Fakes
        Set-Inputs '["10.1.2.3"]'
        Set-State -Resources $test.resources -ChildModules @($invalidModule)
        Expect-Failure 'invalid child module' 'runner state' { & $importer -VarFile $varFile -Apply }
        Assert-Equal 0 $test.imports.Count 'invalid child module performs no imports'
        Assert-Equal 0 $test.azureCalls.Count 'invalid child module avoids Azure lookups'
    }

    foreach ($invalidResource in @(
        @{ address = 'module.bad.azurerm_resource.unknown'; mode = 'managed'; values = @{} }
        @{ address = 'module.bad.azurerm_resource.unknown'; mode = 'managed'; values = @{ id = $null } }
        @{ address = 'module.bad.azurerm_resource.unknown'; mode = 'managed'; values = @{ id = '  ' } }
        @{ address = 'module.bad.azurerm_resource.unknown'; mode = 'managed'; values = @{ id = @('invalid') } }
        @{ address = 'module.bad.azurerm_resource.unknown'; mode = 'invalid'; values = @{ id = $nsg } }
    )) {
        Reset-Fakes
        Set-Inputs '["10.1.2.3"]'
        Set-State -Resources $test.resources -ChildModules @(@{
            address = 'module.bad'
            resources = @($invalidResource)
        })
        Expect-Failure 'invalid managed resource' 'runner state' { & $importer -VarFile $varFile -Apply }
        Assert-Equal 0 $test.imports.Count 'invalid managed resource performs no imports'
        Assert-Equal 0 $test.azureCalls.Count 'invalid managed resource avoids Azure lookups'
    }

    Reset-Fakes
    Set-Inputs '["10.1.2.3"]'
    $duplicateResource = New-Resource 'module.bad.azurerm_resource.duplicate' "$nsg-other"
    Set-State -Resources $test.resources -ChildModules @(@{
        address = 'module.bad'
        resources = @($duplicateResource, $duplicateResource)
    })
    Expect-Failure 'duplicate child addresses' 'duplicate resource addresses' {
        & $importer -VarFile $varFile -Apply
    }
    Assert-Equal 0 $test.imports.Count 'duplicate child addresses perform no imports'
    Assert-Equal 0 $test.azureCalls.Count 'duplicate child addresses avoid Azure lookups'

    Reset-Fakes
    Set-Inputs '["10.1.2.3"]'
    $dataResource = @{
        address = 'module.lookup.data.azurerm_network_security_group.existing'
        mode = 'data'
        values = @{ id = $nsg }
    }
    Set-State -Resources @(
        (New-Resource 'azurerm_resource_group.runner' $resourceGroup)
        (New-Resource 'azurerm_linux_virtual_machine.runner' $vm)
    ) -ChildModules @(@{ address = 'module.lookup'; resources = @($dataResource) })
    & $importer -VarFile $varFile -Apply 6>$null | Out-Null
    Assert-Equal 6 $test.imports.Count 'data resources do not own managed import targets'
    if (-not $test.imports.Contains('azurerm_network_security_group.runner')) {
        throw 'A data resource incorrectly prevented the network security group import.'
    }

    Reset-Fakes
    Set-Inputs '["10.1.2.3", "10.1.2.4",] # fictional addresses'
    $output = @(& $importer -VarFile $varFile 6>&1)
    Assert-Equal 0 $test.imports.Count 'default mode remains read-only'
    Assert-Equal 2 $test.azureCalls.Count 'valid state allows role lookups'
    if (($output -join "`n").Contains('fictional-sensitive-state-value')) {
        throw 'The raw runner state was disclosed.'
    }

    Reset-Fakes
    Set-Inputs '["10.1.2.3"]'
    & $importer -VarFile $varFile -Apply 6>$null | Out-Null
    Assert-Equal 5 $test.imports.Count 'approved mode imports only absent addresses'
    foreach ($alreadyOwned in 'azurerm_resource_group.runner', 'azurerm_linux_virtual_machine.runner', 'azurerm_network_security_group.runner') {
        if ($test.imports.Contains($alreadyOwned)) { throw "Already-owned $alreadyOwned was imported." }
    }

    foreach ($roleId in $fixtureRoleId, "$fixtureRoleId|$resourceGroup") {
        Reset-Fakes
        Set-Inputs '["10.1.2.3"]'
        Set-State @(
            (New-Resource 'azurerm_resource_group.runner' $resourceGroup)
            (New-Resource 'azurerm_linux_virtual_machine.runner' $vm)
            (New-Resource 'azurerm_role_definition.self_deallocate' $roleId)
        )
        & $importer -VarFile $varFile -Apply 6>$null | Out-Null
        if ($test.imports.Contains('azurerm_role_definition.self_deallocate')) {
            throw 'An already-owned role definition was imported.'
        }
    }

    Reset-Fakes
    Set-Inputs '["10.1.2.3"]'
    $test.failImport = 'azapi_resource.subnet'
    Expect-Failure 'failed import' 'Import failed' { & $importer -VarFile $varFile -Apply }
    Assert-Equal 1 $test.imports.Count 'a failed import stops subsequent imports'

    Write-Output 'Legacy runner importer safeguards passed without Azure or state writes.'
}
finally {
    try {
        Remove-Item -LiteralPath $temporary -Recurse -Force -ErrorAction Stop
    }
    finally {
        if ($hadExitCode) { $global:LASTEXITCODE = $previousExitCode }
        else { Remove-Variable -Name LASTEXITCODE -Scope Global -ErrorAction SilentlyContinue }
    }
}

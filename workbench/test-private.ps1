param(
    [Parameter(Mandatory)][string]$BaseUrl,
    [string]$PythonCommand = 'python',
    [switch]$SkipAgentCall
)
$ErrorActionPreference = 'Stop'
$arguments = @((Join-Path $PSScriptRoot 'verify_private.py'), '--base-url', $BaseUrl, '--check-storage')
if (-not $SkipAgentCall) { $arguments += '--run-agent' }
& $PythonCommand @arguments
if ($LASTEXITCODE -ne 0) { throw 'Private Lab verification failed; inspect the reported check before retrying.' }

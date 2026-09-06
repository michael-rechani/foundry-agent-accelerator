param(
    [string]$Subscription = "da04ef2d-3411-465a-96d1-67c75356720a",
    [string]$Registry = "acrworkbenchdi2mw",
    [string]$Tag = "cosmos-v1",
    [switch]$Private,
    [string]$ResumeResourceGroup
)
$ErrorActionPreference = "Stop"
$stage = Join-Path ([IO.Path]::GetTempPath()) ("workbench-build-" + [guid]::NewGuid().ToString("N"))
try {
    New-Item -ItemType Directory -Path (Join-Path $stage "frontend") -Force | Out-Null
    foreach ($name in @("Dockerfile", ".dockerignore", "requirements.txt", "app.py", "history.py", "agents.json")) {
        Copy-Item (Join-Path $PSScriptRoot $name) $stage
    }
    foreach ($pattern in @("package.json", "package-lock.json", "index.html", "tsconfig*.json", "vite.config.ts")) {
        Copy-Item (Join-Path $PSScriptRoot "frontend/$pattern") (Join-Path $stage "frontend")
    }
    Copy-Item (Join-Path $PSScriptRoot "frontend/src") (Join-Path $stage "frontend/src") -Recurse
    if ($Private) {
        $resume = @{}
        if ($ResumeResourceGroup) { $resume.ResumeResourceGroup = $ResumeResourceGroup }
        & (Join-Path $PSScriptRoot 'build-private.ps1') -SourceDirectory $stage -Subscription $Subscription -Registry $Registry -Tag $Tag @resume
    } else {
        & az acr build --subscription $Subscription --registry $Registry --image "workbench:$Tag" --file (Join-Path $stage "Dockerfile") $stage --no-logs
        if ($LASTEXITCODE -ne 0) { throw "Registry build failed" }
    }
} finally {
    Remove-Item $stage -Recurse -Force -ErrorAction SilentlyContinue
}
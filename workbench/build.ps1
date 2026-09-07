param(
    [string]$Subscription = "da04ef2d-3411-465a-96d1-67c75356720a",
    [string]$Registry = "acrworkbenchdi2mw",
    [string]$Tag = "cosmos-v1",
    [switch]$Private
)
$ErrorActionPreference = "Stop"
$stage = Join-Path ([IO.Path]::GetTempPath()) ("workbench-build-" + [guid]::NewGuid().ToString("N"))
try {
    New-Item -ItemType Directory -Path (Join-Path $stage "frontend") -Force | Out-Null
    foreach ($name in @("Dockerfile", ".dockerignore", "requirements.txt", "app.py", "history.py", "reviews.py", "review_runs.py", "agents.json")) {
        Copy-Item (Join-Path $PSScriptRoot $name) $stage
    }
    foreach ($pattern in @("package.json", "package-lock.json", "index.html", "tsconfig*.json", "vite.config.ts")) {
        Copy-Item (Join-Path $PSScriptRoot "frontend/$pattern") (Join-Path $stage "frontend")
    }
    Copy-Item (Join-Path $PSScriptRoot "frontend/src") (Join-Path $stage "frontend/src") -Recurse
    if ($Private) {
        Get-Command docker -ErrorAction Stop | Out-Null
        $loginServer = & az acr show --subscription $Subscription --name $Registry --query loginServer --output tsv --only-show-errors
        if ($LASTEXITCODE -ne 0 -or !$loginServer) { throw "Registry lookup failed" }
        $image = "${loginServer}/workbench:$Tag"
        & az acr login --subscription $Subscription --name $Registry --only-show-errors
        if ($LASTEXITCODE -ne 0) { throw "Registry login failed" }
        & docker build --pull --platform linux/amd64 --tag $image --file (Join-Path $stage "Dockerfile") $stage
        if ($LASTEXITCODE -ne 0) { throw "Local image build failed" }
        & docker run --rm --platform linux/amd64 --entrypoint python $image -c 'import os, app, history, reviews, review_runs; from pathlib import Path; assert os.getuid() != 0; assert Path("agents.json").read_text(); assert Path("static/index.html").read_text()'
        if ($LASTEXITCODE -ne 0) { throw "Image validation failed" }
        & docker push $image
        if ($LASTEXITCODE -ne 0) { throw "Image push failed" }
        $digest = & docker image inspect $image --format '{{index .RepoDigests 0}}'
        if ($LASTEXITCODE -ne 0 -or $digest -notmatch '^.+/workbench@sha256:[a-f0-9]{64}$') { throw "Image digest lookup failed" }
        & docker pull --platform linux/amd64 $digest
        if ($LASTEXITCODE -ne 0) { throw "Image pull verification failed" }
        Write-Output $digest
        Write-Output 'PRIVATE_BUILD_PUSH_AND_PULL_VERIFIED=True'
    } else {
        & az acr build --subscription $Subscription --registry $Registry --image "workbench:$Tag" --file (Join-Path $stage "Dockerfile") $stage --no-logs
        if ($LASTEXITCODE -ne 0) { throw "Registry build failed" }
    }
} finally {
    Remove-Item $stage -Recurse -Force -ErrorAction SilentlyContinue
}
param(
    [Parameter(Mandatory)][ValidatePattern('^[0-9a-fA-F-]{36}$')][string]$Subscription,
    [Parameter(Mandatory)][ValidatePattern('^[a-z0-9]{5,50}$')][string]$Registry,
    [Parameter(Mandatory)][ValidatePattern('^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$')][string]$Tag,
    [switch]$Private
)
$ErrorActionPreference = "Stop"
$stage = Join-Path ([IO.Path]::GetTempPath()) ("workbench-build-" + [guid]::NewGuid().ToString("N"))
try {
    New-Item -ItemType Directory -Path (Join-Path $stage "frontend") -Force | Out-Null
    foreach ($name in @("Dockerfile", ".dockerignore", "requirements.txt", "app.py", "history.py", "reviews.py", "review_runs.py", "agents.json", "agent_creation.py", "agent_publisher.py", "agent_package.py", "agent_templates.py")) {
        Copy-Item (Join-Path $PSScriptRoot $name) $stage
    }
    New-Item -ItemType Directory -Path (Join-Path $stage "agent_runtime") | Out-Null
    foreach ($name in @("main.py", "demo_tools.py", "requirements.txt")) {
        Copy-Item (Join-Path $PSScriptRoot "agent_runtime/$name") (Join-Path $stage "agent_runtime")
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
        & docker run --rm --platform linux/amd64 --entrypoint python $image -c "import os, app, history, reviews, review_runs, agent_creation, agent_templates, agent_publisher; from pathlib import Path; assert os.getuid() != 0; assert agent_publisher.runtime_package()[0]; assert Path('agents.json').read_text(); assert Path('static/index.html').read_text()"
        if ($LASTEXITCODE -ne 0) { throw "Image validation failed" }
        & docker push $image
        if ($LASTEXITCODE -ne 0) { throw "Image push failed" }
        $imageDigest = & az acr repository show --subscription $Subscription --name $Registry --image "workbench:$Tag" --query digest --output tsv --only-show-errors
        if ($LASTEXITCODE -ne 0 -or $imageDigest -notmatch '^sha256:[a-f0-9]{64}$') { throw "Image digest lookup failed" }
        $digest = "${loginServer}/workbench@$imageDigest"
        $localDigests = & docker image inspect $image --format '{{json .RepoDigests}}'
        if ($LASTEXITCODE -ne 0) { throw "Pushed image digest does not match the local build" }
        $parsedDigests = $localDigests | ConvertFrom-Json
        if ($parsedDigests -notcontains $digest) { throw "Pushed image digest does not match the local build" }
        & docker pull --platform linux/amd64 $digest
        if ($LASTEXITCODE -ne 0) { throw "Image pull verification failed" }
        Write-Output $digest
        Write-Output 'PRIVATE_BUILD_PUSH_AND_PULL_VERIFIED=True'
    } else {
        $publicAccess = & az acr show --subscription $Subscription --name $Registry --query publicNetworkAccess --output tsv --only-show-errors
        if ($LASTEXITCODE -ne 0 -or $publicAccess -ne 'Enabled') { throw "ACR Tasks requires an explicitly public registry; use -Private for private builds" }
        & az acr build --subscription $Subscription --registry $Registry --image "workbench:$Tag" --file (Join-Path $stage "Dockerfile") $stage --no-logs
        if ($LASTEXITCODE -ne 0) { throw "Registry build failed" }
    }
} finally {
    Remove-Item $stage -Recurse -Force -ErrorAction SilentlyContinue
}
# Creates the Azure identity that the "Record library answers" workflow signs in with.
# It is safe to run again: every step looks for what already exists first.
#
# The identity has no secret. GitHub proves who it is with a short-lived OIDC token, and Azure
# accepts that token only for the library-recording environment of one repository. If sign-in
# fails with "No matching federated identity record", the error shows the subject GitHub
# presented; pass it as -FederatedSubject.
# It holds one role, Foundry User (once "Azure AI User"), on the one Foundry account the Lab already
# uses. That lets it call the account's models and nothing else: no networking, role changes or other resources.
param(
    [Parameter(Mandatory)][ValidatePattern('^[0-9a-fA-F-]{36}$')][string]$Subscription,
    [Parameter(Mandatory)][string]$ResourceGroup,
    [Parameter(Mandatory)][string]$FoundryAccount,
    [Parameter(Mandatory)][ValidatePattern('^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$')][string]$Repository,
    [ValidatePattern('^[A-Za-z0-9_.-]+$')][string]$Environment = 'library-recording',
    [string]$FederatedSubject,
    [string]$Name = 'gh-library-recording'
)
$ErrorActionPreference = 'Stop'

function Invoke-Az {
    $output = & az @args --only-show-errors
    if ($LASTEXITCODE -ne 0) { throw "az $($args[0..2] -join ' ') failed" }
    $output
}

$tenant = Invoke-Az account show --subscription $Subscription --query tenantId --output tsv
$accountId = Invoke-Az cognitiveservices account show --subscription $Subscription --name $FoundryAccount --resource-group $ResourceGroup --query id --output tsv

$clientId = Invoke-Az ad app list --display-name $Name --query "[0].appId" --output tsv
if (-not $clientId) { $clientId = Invoke-Az ad app create --display-name $Name --query appId --output tsv }
$principalId = Invoke-Az ad sp list --filter "appId eq '$clientId'" --query "[0].id" --output tsv
if (-not $principalId) { $principalId = Invoke-Az ad sp create --id $clientId --query id --output tsv }

$subject = "repo:${Repository}:environment:${Environment}"
# Newer repositories present an immutable subject that includes the owner and repository IDs.
if (Get-Command gh -ErrorAction SilentlyContinue) {
    $ids = & gh api "repos/$Repository" --jq '[.owner.login, .owner.id, .name, .id] | @tsv' 2>$null
    if ($LASTEXITCODE -eq 0 -and $ids) {
        $owner, $ownerId, $repoName, $repoId = "$ids" -split "`t"
        $subject = "repo:$owner@$ownerId/$repoName@${repoId}:environment:${Environment}"
    }
}
if ($FederatedSubject) { $subject = $FederatedSubject }
$credentialName = "github-$Environment"
$existing = Invoke-Az ad app federated-credential list --id $clientId --query "[?name=='$credentialName'].subject" --output tsv
if ($existing -ne $subject) {
    if ($existing) { Invoke-Az ad app federated-credential delete --id $clientId --federated-credential-id $credentialName | Out-Null }
    $file = Join-Path ([IO.Path]::GetTempPath()) ("credential-" + [guid]::NewGuid().ToString('N') + '.json')
    try {
        @{ name = $credentialName; issuer = 'https://token.actions.githubusercontent.com'; subject = $subject; audiences = @('api://AzureADTokenExchange') } |
            ConvertTo-Json | Set-Content -LiteralPath $file -Encoding utf8
        Invoke-Az ad app federated-credential create --id $clientId --parameters "@$file" | Out-Null
    } finally { Remove-Item -LiteralPath $file -Force -ErrorAction SilentlyContinue }
}

$role = '53ca6127-db72-4b80-b1b0-d745d6d5456d' # "Foundry User", once named "Azure AI User"
$has = Invoke-Az role assignment list --subscription $Subscription --assignee-object-id $principalId --role $role --scope $accountId --query "[].id" --output tsv
if (-not $has) {
    Invoke-Az role assignment create --subscription $Subscription --assignee-object-id $principalId --assignee-principal-type ServicePrincipal --role $role --scope $accountId | Out-Null
}

Write-Output "Identity ready. Set these as variables of the '$Environment' environment in GitHub (not in a file):"
Write-Output "  AZURE_CLIENT_ID=$clientId"
Write-Output "  AZURE_TENANT_ID=$tenant"
Write-Output "  FOUNDRY_PROJECT_ENDPOINT=<the project URL, ending in /api/projects/<project name>>"
Write-Output "Then add a required reviewer to the '$Environment' environment, so nothing is sent until you approve."

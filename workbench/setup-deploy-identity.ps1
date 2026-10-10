# Creates the Azure identity that the "Deploy Lab image" workflow signs in with.
# It is safe to run again: every step looks for what already exists first.
#
# The identity has no secret. GitHub proves who it is with a short-lived OIDC token,
# and Azure accepts that token only for one environment of one repository.
# Its custom role can import an image into the registry and update the one Container
# App. It cannot change registry networking, other apps, or role assignments.
param(
    [Parameter(Mandatory)][ValidatePattern('^[0-9a-fA-F-]{36}$')][string]$Subscription,
    [Parameter(Mandatory)][string]$ResourceGroup,
    [Parameter(Mandatory)][string]$Registry,
    [Parameter(Mandatory)][string]$ContainerApp,
    [Parameter(Mandatory)][string]$ManagedIdentity,
    [Parameter(Mandatory)][ValidatePattern('^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$')][string]$Repository,
    [ValidatePattern('^[A-Za-z0-9_.-]+$')][string]$Environment = 'lab-deploy',
    [string]$Name = 'gh-lab-image-deploy'
)
$ErrorActionPreference = 'Stop'

function Invoke-Az {
    $output = & az @args --only-show-errors
    if ($LASTEXITCODE -ne 0) { throw "az $($args[0..2] -join ' ') failed" }
    $output
}

$scope = "/subscriptions/$Subscription/resourceGroups/$ResourceGroup"
$roleName = 'Lab image deployer'
$tenant = Invoke-Az account show --subscription $Subscription --query tenantId --output tsv

$registryId = Invoke-Az acr show --subscription $Subscription --name $Registry --resource-group $ResourceGroup --query id --output tsv
$app = Invoke-Az containerapp show --subscription $Subscription --name $ContainerApp --resource-group $ResourceGroup --output json | ConvertFrom-Json
$appId = $app.id
$environmentId = $app.properties.environmentId
$identityId = Invoke-Az identity show --subscription $Subscription --name $ManagedIdentity --resource-group $ResourceGroup --query id --output tsv

$clientId = Invoke-Az ad app list --display-name $Name --query "[0].appId" --output tsv
if (-not $clientId) { $clientId = Invoke-Az ad app create --display-name $Name --query appId --output tsv }
$principalId = Invoke-Az ad sp list --filter "appId eq '$clientId'" --query "[0].id" --output tsv
if (-not $principalId) { $principalId = Invoke-Az ad sp create --id $clientId --query id --output tsv }

$subject = "repo:${Repository}:environment:${Environment}"
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

$definition = @{
    Name = $roleName
    Description = 'Import a release image into the Lab registry and roll the Lab Container App to it. No network, role or secret changes.'
    Actions = @(
        'Microsoft.ContainerRegistry/registries/read',
        'Microsoft.ContainerRegistry/registries/importImage/action',
        'Microsoft.App/containerApps/read',
        'Microsoft.App/containerApps/write',
        'Microsoft.App/containerApps/revisions/read',
        'Microsoft.App/managedEnvironments/read',
        'Microsoft.App/managedEnvironments/join/action',
        'Microsoft.App/locations/*/read',
        'Microsoft.ManagedIdentity/userAssignedIdentities/read',
        'Microsoft.ManagedIdentity/userAssignedIdentities/assign/action'
    )
    NotActions = @()
    AssignableScopes = @($scope)
}
$file = Join-Path ([IO.Path]::GetTempPath()) ("role-" + [guid]::NewGuid().ToString('N') + '.json')
try {
    $definition | ConvertTo-Json | Set-Content -LiteralPath $file -Encoding utf8
    $found = Invoke-Az role definition list --subscription $Subscription --name $roleName --scope $scope --query "[0].name" --output tsv
    if ($found) { Invoke-Az role definition update --subscription $Subscription --role-definition "@$file" | Out-Null }
    else { Invoke-Az role definition create --subscription $Subscription --role-definition "@$file" | Out-Null }
} finally { Remove-Item -LiteralPath $file -Force -ErrorAction SilentlyContinue }

foreach ($target in @($registryId, $appId, $environmentId, $identityId)) {
    $has = Invoke-Az role assignment list --subscription $Subscription --assignee $principalId --role $roleName --scope $target --query "[].id" --output tsv
    if (-not $has) {
        Invoke-Az role assignment create --subscription $Subscription --assignee-object-id $principalId --assignee-principal-type ServicePrincipal --role $roleName --scope $target | Out-Null
    }
}

Write-Output "Identity ready. Set these as variables of the '$Environment' environment in GitHub (not in a file):"
Write-Output "  AZURE_CLIENT_ID=$clientId"
Write-Output "  AZURE_TENANT_ID=$tenant"
Write-Output "  AZURE_SUBSCRIPTION_ID=$Subscription"
Write-Output "  AZURE_RESOURCE_GROUP=$ResourceGroup"
Write-Output "  LAB_REGISTRY=$Registry"
Write-Output "  LAB_CONTAINER_APP=$ContainerApp"

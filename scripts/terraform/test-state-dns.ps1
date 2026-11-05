param(
    [string]$TerraformCommand = 'terraform'
)

$ErrorActionPreference = 'Stop'
$root = Join-Path $PSScriptRoot '../../terraform'
$network = Get-Content -LiteralPath (Join-Path $root 'network.tf') -Raw
$management = Get-Content -LiteralPath (Join-Path $root 'management-network.tf') -Raw
$storage = Get-Content -LiteralPath (Join-Path $root 'keyless-storage.tf') -Raw
$variables = Get-Content -LiteralPath (Join-Path $root 'variables.tf') -Raw
$backendEndpoint = Get-Content -LiteralPath (Join-Path $root 'state-backend-endpoint.tf') -Raw

function Get-Block([string]$Source, [string]$Header) {
    $match = [regex]::Match($Source, "(?ms)^$([regex]::Escape($Header)) \{.*?^\}")
    if (-not $match.Success) { throw "Missing Terraform block: $Header" }
    $match.Value
}

# Plan the real DNS selectors and links in isolation, without the Foundry modules.
$blocks = @(
    (Get-Block $network 'locals'),
    (Get-Block $variables 'variable "blob_private_dns_zone_id"'),
    (Get-Block $network 'resource "azurerm_private_dns_zone" "this"'),
    (Get-Block $network 'resource "azurerm_private_dns_zone_virtual_network_link" "this"'),
    (Get-Block $management 'resource "azurerm_private_dns_zone_virtual_network_link" "jumpbox"'),
    (Get-Block $network 'resource "azurerm_monitor_private_link_scope" "this"'),
    (Get-Block $network 'resource "azurerm_private_endpoint" "azure_monitor"'),
    (Get-Block $storage 'resource "azurerm_private_endpoint" "agent_storage"'),
    (Get-Block $backendEndpoint 'variable "terraform_state_private_endpoint"'),
    (Get-Block $backendEndpoint 'resource "azurerm_private_endpoint" "terraform_state"')
)
if ($backendEndpoint -notmatch 'to\s*=\s*azurerm_private_endpoint\.terraform_state\[0\]' -or
    $backendEndpoint -notmatch 'for_each\s*=\s*var\.terraform_state_private_endpoint == null \? \{\} : \{ existing = var\.terraform_state_private_endpoint \}' -or
    $backendEndpoint -notmatch '(?m)^\s*id\s*=\s*each\.value\.id\s*$') {
    throw 'The backend endpoint import must be explicitly opted in and use the exact supplied existing resource ID.'
}
if ($backendEndpoint -notmatch 'lifecycle\s*\{\s*prevent_destroy\s*=\s*true' -or
    $backendEndpoint -notmatch 'subnet_id\s*=\s*azurerm_subnet\.private_endpoints\.id') {
    throw 'The backend endpoint must use the existing private subnet and be protected from destruction.'
}
foreach ($zoneSource in @(
        (Get-Block $network 'resource "azurerm_private_dns_zone" "this"'),
        (Get-Block (Get-Content -LiteralPath (Join-Path $root 'bootstrap/main.tf') -Raw) 'resource "azapi_resource" "dns_zone"'))) {
    if ($zoneSource -notmatch 'lifecycle\s*\{\s*prevent_destroy\s*=\s*true\s*\}') {
        throw 'Both roots must protect their DNS zones from unreviewed destruction.'
    }
}

$temporary = Join-Path ([IO.Path]::GetTempPath()) ('state-dns-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $temporary | Out-Null
try {
    $fixture = @'
terraform {
  required_providers {
    azapi = {
      source  = "Azure/azapi"
      version = "~> 2.12.0"
    }
    azurerm = {
      source  = "hashicorp/azurerm"
      version = ">= 4.81.0, < 5.0.0"
    }
  }
}
provider "azurerm" {
  features {}
}
provider "azapi" {
  subscription_id = var.subscription_id
}
locals {
  tags                       = {}
  management_network_enabled = var.enable_management_network
  deployment_location        = "northcentralus"
  name_suffix                = "unit-test"
  agent_storage_account_name = "stfixture"
}
variable "enable_management_network" { default = true }
variable "subscription_id" { default = "11111111-2222-3333-4444-555555555555" }
resource "azurerm_resource_group" "this" {
  name     = "rg-platform"
  location = "northcentralus"
}
resource "azurerm_virtual_network" "this" {
  name                = "vnet-workload"
  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_resource_group.this.location
  address_space       = ["10.42.0.0/16"]
}
resource "azurerm_virtual_network" "jumpbox" {
  count               = local.management_network_enabled ? 1 : 0
  name                = "vnet-management"
  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_resource_group.this.location
  address_space       = ["10.43.0.0/16"]
}
resource "azurerm_subnet" "private_endpoints" {
  name                 = "snet-private-endpoints"
  resource_group_name  = azurerm_resource_group.this.name
  virtual_network_name = azurerm_virtual_network.this.name
  address_prefixes     = ["10.42.0.0/24"]
}
resource "azapi_resource" "agent_storage" {
  type      = "Microsoft.Storage/storageAccounts@2025-01-01"
  name      = local.agent_storage_account_name
  parent_id = "/subscriptions/${var.subscription_id}/resourceGroups/rg-platform"
  location  = local.deployment_location
  body = {
    kind = "StorageV2"
    sku  = { name = "Standard_LRS" }
    properties = {
      publicNetworkAccess   = "Disabled"
      allowSharedKeyAccess  = false
      allowBlobPublicAccess = false
    }
  }
}
'@
    Set-Content -LiteralPath (Join-Path $temporary 'main.tf') -Value ($fixture + "`n" + ($blocks -join "`n"))
    $tests = @'
mock_provider "azurerm" {}
mock_provider "azapi" {}

run "legacy_ownership_unchanged" {
  command = plan
  assert {
    condition = (
      contains(keys(azurerm_private_dns_zone.this), "storage_blob") &&
      azurerm_private_dns_zone_virtual_network_link.this["storage_blob"].resource_group_name == "rg-platform" &&
      contains(keys(azurerm_private_dns_zone_virtual_network_link.jumpbox), "storage_blob") &&
      length(azurerm_private_endpoint.terraform_state) == 0
    )
    error_message = "Null must preserve the existing platform zone and both links."
  }
}

run "bootstrap_owns_shared_zone_and_management_link" {
  command = plan
  variables {
    blob_private_dns_zone_id = "/subscriptions/11111111-2222-3333-4444-555555555555/resourceGroups/rg-state/providers/Microsoft.Network/privateDnsZones/privatelink.blob.core.windows.net"
  }
  assert {
    condition = (
      !contains(keys(azurerm_private_dns_zone.this), "storage_blob") &&
      !contains(keys(azurerm_private_dns_zone_virtual_network_link.jumpbox), "storage_blob") &&
      azurerm_private_dns_zone_virtual_network_link.this["storage_blob"].resource_group_name == "rg-state" &&
      azurerm_private_dns_zone_virtual_network_link.this["storage_blob"].private_dns_zone_name == "privatelink.blob.core.windows.net" &&
      local.blob_private_dns_zone_id == var.blob_private_dns_zone_id &&
      contains(azurerm_private_endpoint.agent_storage.private_dns_zone_group[0].private_dns_zone_ids, var.blob_private_dns_zone_id) &&
      contains(azurerm_private_endpoint.azure_monitor.private_dns_zone_group[0].private_dns_zone_ids, var.blob_private_dns_zone_id) &&
      length(azurerm_private_dns_zone.this) == length(local.private_dns_zone_names) - 1 &&
      length(azurerm_private_dns_zone_virtual_network_link.jumpbox) == length(azurerm_private_dns_zone.this) &&
      length(azurerm_private_dns_zone_virtual_network_link.this) == length(local.private_dns_zone_names)
    )
    error_message = "Shared mode must not create another blob namespace or management link; workload still links to the shared zone."
  }
}

run "shared_zone_without_management" {
  command = plan
  variables {
    enable_management_network = false
    blob_private_dns_zone_id = "/subscriptions/11111111-2222-3333-4444-555555555555/resourceGroups/rg-state/providers/Microsoft.Network/privateDnsZones/privatelink.blob.core.windows.net"
  }
  assert {
    condition = length(azurerm_private_dns_zone_virtual_network_link.jumpbox) == 0 && contains(keys(azurerm_private_dns_zone_virtual_network_link.this), "storage_blob")
    error_message = "A workload without management still needs its shared-zone link."
  }
}

run "reject_wrong_namespace" {
  command = plan
  variables {
    blob_private_dns_zone_id = "/subscriptions/11111111-2222-3333-4444-555555555555/resourceGroups/rg-state/providers/Microsoft.Network/privateDnsZones/privatelink.file.core.windows.net"
  }
  expect_failures = [var.blob_private_dns_zone_id]
}

run "reject_incomplete_id" {
  command = plan
  variables {
    blob_private_dns_zone_id = "privatelink.blob.core.windows.net"
  }
  expect_failures = [var.blob_private_dns_zone_id]
}

run "reject_cross_subscription_zone" {
  command = plan
  variables {
    blob_private_dns_zone_id = "/subscriptions/99999999-2222-3333-4444-555555555555/resourceGroups/rg-state/providers/Microsoft.Network/privateDnsZones/privatelink.blob.core.windows.net"
  }
  expect_failures = [var.blob_private_dns_zone_id]
}

run "adopt_backend_endpoint_without_taking_storage_ownership" {
  command = plan
  variables {
    blob_private_dns_zone_id = "/subscriptions/11111111-2222-3333-4444-555555555555/resourceGroups/rg-state/providers/Microsoft.Network/privateDnsZones/privatelink.blob.core.windows.net"
    terraform_state_private_endpoint = {
      id                 = "/subscriptions/11111111-2222-3333-4444-555555555555/resourceGroups/rg-platform/providers/Microsoft.Network/privateEndpoints/pe-existing-state"
      storage_account_id = "/subscriptions/11111111-2222-3333-4444-555555555555/resourceGroups/rg-external/providers/Microsoft.Storage/storageAccounts/stsharedstate"
    }
  }
  assert {
    condition = (
      length(azurerm_private_endpoint.terraform_state) == 1 &&
      azurerm_private_endpoint.terraform_state[0].name == "pe-existing-state" &&
      length(azurerm_private_endpoint.terraform_state[0].tags) == 0 &&
      azurerm_private_endpoint.terraform_state[0].private_service_connection[0].name == "tfstate-blob" &&
      !azurerm_private_endpoint.terraform_state[0].private_service_connection[0].is_manual_connection
    )
    error_message = "The adopted endpoint must retain its existing name, automatic connection and empty tags."
  }
  assert {
    condition = (
      azurerm_private_endpoint.terraform_state[0].private_service_connection[0].private_connection_resource_id == var.terraform_state_private_endpoint.storage_account_id &&
      toset(azurerm_private_endpoint.terraform_state[0].private_service_connection[0].subresource_names) == toset(["blob"]) &&
      azurerm_private_endpoint.terraform_state[0].private_dns_zone_group[0].name == "blob" &&
      contains(azurerm_private_endpoint.terraform_state[0].private_dns_zone_group[0].private_dns_zone_ids, var.blob_private_dns_zone_id)
    )
    error_message = "The backend endpoint must reference the external storage account and effective blob zone without creating either."
  }
}

run "reject_backend_endpoint_in_another_platform" {
  command = plan
  variables {
    terraform_state_private_endpoint = {
      id                 = "/subscriptions/11111111-2222-3333-4444-555555555555/resourceGroups/rg-other/providers/Microsoft.Network/privateEndpoints/pe-existing-state"
      storage_account_id = "/subscriptions/11111111-2222-3333-4444-555555555555/resourceGroups/rg-external/providers/Microsoft.Storage/storageAccounts/stsharedstate"
    }
  }
  expect_failures = [azurerm_private_endpoint.terraform_state[0]]
}

run "adopt_backend_endpoint_with_platform_owned_zone" {
  command = plan
  variables {
    terraform_state_private_endpoint = {
      id                 = "/subscriptions/11111111-2222-3333-4444-555555555555/resourceGroups/rg-platform/providers/Microsoft.Network/privateEndpoints/pe-existing-state"
      storage_account_id = "/subscriptions/11111111-2222-3333-4444-555555555555/resourceGroups/rg-external/providers/Microsoft.Storage/storageAccounts/stsharedstate"
      tags               = { existing = "preserved" }
    }
  }
  assert {
    condition = (
      contains(keys(azurerm_private_dns_zone.this), "storage_blob") &&
      azurerm_private_endpoint.terraform_state[0].tags["existing"] == "preserved" &&
      azurerm_private_endpoint.terraform_state[0].location == "northcentralus" &&
      azurerm_private_endpoint.terraform_state[0].resource_group_name == "rg-platform"
    )
    error_message = "Adoption must support existing platform-owned DNS without modifying endpoint tags or placement."
  }
}

run "reject_backend_endpoint_in_another_subscription" {
  command = plan
  variables {
    terraform_state_private_endpoint = {
      id                 = "/subscriptions/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee/resourceGroups/rg-platform/providers/Microsoft.Network/privateEndpoints/pe-existing-state"
      storage_account_id = "/subscriptions/11111111-2222-3333-4444-555555555555/resourceGroups/rg-external/providers/Microsoft.Storage/storageAccounts/stsharedstate"
    }
  }
  expect_failures = [azurerm_private_endpoint.terraform_state[0]]
}

run "reject_invalid_backend_endpoint_id" {
  command = plan
  variables {
    terraform_state_private_endpoint = {
      id                 = "pe-existing-state"
      storage_account_id = "/subscriptions/11111111-2222-3333-4444-555555555555/resourceGroups/rg-external/providers/Microsoft.Storage/storageAccounts/stsharedstate"
    }
  }
  expect_failures = [var.terraform_state_private_endpoint]
}

run "reject_invalid_backend_storage_id" {
  command = plan
  variables {
    terraform_state_private_endpoint = {
      id                 = "/subscriptions/11111111-2222-3333-4444-555555555555/resourceGroups/rg-platform/providers/Microsoft.Network/privateEndpoints/pe-existing-state"
      storage_account_id = "stsharedstate"
    }
  }
  expect_failures = [var.terraform_state_private_endpoint]
}
'@
    Set-Content -LiteralPath (Join-Path $temporary 'dns.tftest.hcl') -Value $tests
    & $TerraformCommand "-chdir=$temporary" init -backend=false -input=false -no-color
    if ($LASTEXITCODE -ne 0) { throw 'Isolated DNS initialization failed.' }
    & $TerraformCommand "-chdir=$temporary" test -no-color
    if ($LASTEXITCODE -ne 0) { throw 'Shared DNS ownership tests failed.' }
} finally {
    for ($attempt = 0; $attempt -lt 5; $attempt++) {
        try {
            Remove-Item -LiteralPath $temporary -Recurse -Force -ErrorAction Stop
            break
        }
        catch [System.UnauthorizedAccessException], [System.IO.IOException] {
            if ($attempt -eq 4) { throw }
            # Windows can briefly retain provider executable handles after Terraform exits.
            Start-Sleep -Milliseconds (250 * ($attempt + 1))
        }
    }
}

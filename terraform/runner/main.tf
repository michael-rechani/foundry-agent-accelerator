locals {
  name_suffix = "${var.base_name}-${var.environment}"
  runner_rg   = coalesce(var.runner_resource_group_name, "rg-runner-${local.name_suffix}")
  vm_name     = "vm-runner-${local.name_suffix}"
  location    = data.azapi_resource.virtual_network.output.location

  network_resource_group_id = "/subscriptions/${var.subscription_id}/resourceGroups/${var.resource_group_name}"

  tags = merge(var.tags, {
    environment = var.environment
    managed-by  = "terraform"
    workload    = "github-actions-runner"
  })

  # Scripts may be checked out with Windows line endings; bash needs LF.
  script = { for name in ["provision.sh", "register-runner.sh", "idle-deallocate.sh", "runner-idle.service", "runner-idle.timer", "52runner-unattended-upgrades"] :
    name => replace(file("${path.module}/scripts/${name}"), "\r\n", "\n")
  }

  # Holds no secrets. The registration token is passed later through Run Command.
  provision_env = join("\n", [
    "GITHUB_REPOSITORY=${var.github_repository}",
    "RUNNER_VERSION=${var.runner_version}",
    "RUNNER_SHA256=${var.runner_sha256}",
    "IDLE_SHUTDOWN_MINUTES=${var.idle_shutdown_minutes}",
    "",
  ])

  cloud_init = "#cloud-config\n${yamlencode({
    write_files = [
      { path = "/etc/runner/provision.env", permissions = "0644", content = local.provision_env },
      { path = "/usr/local/sbin/runner-provision", permissions = "0700", content = local.script["provision.sh"] },
      { path = "/usr/local/sbin/register-runner", permissions = "0700", content = local.script["register-runner.sh"] },
      { path = "/usr/local/sbin/runner-idle-deallocate", permissions = "0700", content = local.script["idle-deallocate.sh"] },
      { path = "/etc/systemd/system/runner-idle.service", permissions = "0644", content = local.script["runner-idle.service"] },
      { path = "/etc/systemd/system/runner-idle.timer", permissions = "0644", content = local.script["runner-idle.timer"] },
      { path = "/etc/apt/apt.conf.d/52runner-unattended-upgrades", permissions = "0644", content = local.script["52runner-unattended-upgrades"] },
    ]
    runcmd = ["/usr/local/sbin/runner-provision"]
  })}\n"
}

data "azapi_resource" "virtual_network" {
  type                   = "Microsoft.Network/virtualNetworks@2025-01-01"
  name                   = var.virtual_network_name
  parent_id              = local.network_resource_group_id
  response_export_values = ["location"]
}

# Read-only lookup. Terraform fails here if the NAT gateway doesn't exist, which
# keeps the runner from ever being built without the approved egress path.
data "azapi_resource" "nat_gateway" {
  type                   = "Microsoft.Network/natGateways@2025-01-01"
  name                   = var.nat_gateway_name
  parent_id              = local.network_resource_group_id
  response_export_values = []
}

resource "azurerm_resource_group" "runner" {
  location = local.location
  name     = local.runner_rg
  tags     = local.tags
}

# No inbound rule is allowed, not even from inside the VNet, so the jumpbox and
# Bastion can't reach the runner. Outbound is limited to web traffic over the NAT
# gateway; the VirtualNetwork deny keeps PR code away from the jumpbox, the peered
# Foundry network, and private endpoints.
resource "azurerm_network_security_group" "runner" {
  location            = local.location
  name                = "nsg-runner-${local.name_suffix}"
  resource_group_name = azurerm_resource_group.runner.name
  tags                = local.tags

  security_rule {
    name                         = "AllowAzurePlatformOutbound"
    priority                     = 100
    direction                    = "Outbound"
    access                       = "Allow"
    protocol                     = "*"
    source_port_range            = "*"
    destination_port_ranges      = ["53", "80", "32526"]
    source_address_prefix        = "*"
    destination_address_prefixes = ["168.63.129.16", "169.254.169.254"]
  }

  security_rule {
    name                       = "AllowWebOutbound"
    priority                   = 110
    direction                  = "Outbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_ranges    = ["80", "443"]
    source_address_prefix      = "*"
    destination_address_prefix = "Internet"
  }

  # Optional, narrow exception so the deploy workflow can push to the private
  # registry. Only HTTPS to the registry private endpoint addresses is allowed.
  dynamic "security_rule" {
    for_each = length(var.registry_private_endpoint_ips) > 0 ? [1] : []
    content {
      name                         = "AllowRegistryPrivateEndpointOutbound"
      priority                     = 120
      direction                    = "Outbound"
      access                       = "Allow"
      protocol                     = "Tcp"
      source_port_range            = "*"
      destination_port_range       = "443"
      source_address_prefix        = "*"
      destination_address_prefixes = var.registry_private_endpoint_ips
    }
  }

  security_rule {
    name                       = "DenyVirtualNetworkOutbound"
    priority                   = 4000
    direction                  = "Outbound"
    access                     = "Deny"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = "*"
    destination_address_prefix = "VirtualNetwork"
  }

  security_rule {
    name                       = "DenyAllOutbound"
    priority                   = 4096
    direction                  = "Outbound"
    access                     = "Deny"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "DenyAllInbound"
    priority                   = 4096
    direction                  = "Inbound"
    access                     = "Deny"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }
}

# Adds one subnet to the existing management VNet and attaches it to the existing
# NAT gateway, as terraform/bastion/ does for AzureBastionSubnet. It changes no
# other subnet, the NAT gateway, or its public IP.
resource "azapi_resource" "subnet" {
  type      = "Microsoft.Network/virtualNetworks/subnets@2025-01-01"
  name      = "snet-runner"
  parent_id = data.azapi_resource.virtual_network.id
  body = {
    properties = {
      addressPrefix         = var.subnet_address_prefix
      defaultOutboundAccess = false
      natGateway            = { id = data.azapi_resource.nat_gateway.id }
      networkSecurityGroup  = { id = azurerm_network_security_group.runner.id }
    }
  }
  response_export_values = []

  lifecycle {
    prevent_destroy = true
  }
}

resource "azurerm_network_interface" "runner" {
  location            = local.location
  name                = "nic-runner-${local.name_suffix}"
  resource_group_name = azurerm_resource_group.runner.name
  tags                = local.tags

  ip_configuration {
    name                          = "private"
    private_ip_address_allocation = "Dynamic"
    subnet_id                     = azapi_resource.subnet.id
  }
}

resource "azurerm_linux_virtual_machine" "runner" {
  admin_username                  = var.admin_username
  allow_extension_operations      = true
  computer_name                   = "runner-${var.environment}"
  custom_data                     = base64encode(local.cloud_init)
  disable_password_authentication = true
  location                        = local.location
  name                            = local.vm_name
  network_interface_ids           = [azurerm_network_interface.runner.id]
  patch_mode                      = "ImageDefault"
  provision_vm_agent              = true
  resource_group_name             = azurerm_resource_group.runner.name
  secure_boot_enabled             = true
  size                            = var.vm_size
  tags                            = local.tags
  vtpm_enabled                    = true

  admin_ssh_key {
    username   = var.admin_username
    public_key = var.admin_ssh_public_key
  }

  boot_diagnostics {}

  identity {
    type = "SystemAssigned"
  }

  os_disk {
    caching              = "ReadWrite"
    disk_size_gb         = var.os_disk_size_gb
    name                 = "${local.vm_name}-os"
    storage_account_type = "StandardSSD_LRS"
  }

  source_image_reference {
    offer     = "ubuntu-24_04-lts"
    publisher = "Canonical"
    sku       = "server"
    version   = "latest"
  }
}

# The VM can deallocate itself and nothing else. This replaces any stored credential.
resource "azurerm_role_definition" "self_deallocate" {
  name        = "Runner self-deallocate ${local.vm_name}"
  scope       = azurerm_resource_group.runner.id
  description = "Lets the runner VM read and deallocate itself when idle."

  permissions {
    actions = [
      "Microsoft.Compute/virtualMachines/read",
      "Microsoft.Compute/virtualMachines/deallocate/action",
    ]
  }

  assignable_scopes = [azurerm_resource_group.runner.id]
}

resource "azurerm_role_assignment" "self_deallocate" {
  principal_id       = azurerm_linux_virtual_machine.runner.identity[0].principal_id
  role_definition_id = azurerm_role_definition.self_deallocate.role_definition_resource_id
  scope              = azurerm_linux_virtual_machine.runner.id
}

resource "azurerm_dev_test_global_vm_shutdown_schedule" "runner" {
  count = var.auto_shutdown != null ? 1 : 0

  virtual_machine_id    = azurerm_linux_virtual_machine.runner.id
  location              = local.location
  enabled               = true
  daily_recurrence_time = var.auto_shutdown.time
  timezone              = var.auto_shutdown.timezone
  tags                  = local.tags

  notification_settings {
    enabled = false
  }
}

variable "subscription_id" {
  type        = string
  description = "Explicit subscription containing the existing management VNet and NAT gateway."

  validation {
    condition     = can(regex("^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", var.subscription_id))
    error_message = "subscription_id must be an Azure subscription GUID."
  }
}

variable "resource_group_name" {
  type        = string
  description = "Existing resource group containing the management VNet and its NAT gateway. This stack only adds a subnet there; the runner itself goes in its own new resource group."
}

variable "virtual_network_name" {
  type        = string
  description = "Existing management VNet; this stack does not take ownership of it. The runner VM is created in the same region."
}

variable "nat_gateway_name" {
  type        = string
  description = "Existing NAT gateway already attached to the management VNet's jumpbox subnet, for example nat-jumpbox-<base>-<environment>. The runner subnet reuses it for outbound-only internet access."
}

variable "approve_shared_egress" {
  type        = bool
  description = "Explicit approval to attach the new runner subnet to the existing NAT gateway, so the runner shares its outbound public IP address with the jumpbox. Must be true to plan or apply this stack."
  default     = false

  validation {
    condition     = var.approve_shared_egress
    error_message = "The runner reuses the existing NAT gateway and its public IP for outbound traffic. Set approve_shared_egress = true only after approving that."
  }
}

variable "subnet_address_prefix" {
  type        = string
  description = "Unused IPv4 range inside the management VNet, /28 or larger, for the runner subnet."
  default     = "10.43.2.0/27"

  validation {
    condition     = can(cidrnetmask(var.subnet_address_prefix)) && can(regex("/(1[0-9]|2[0-8])$", var.subnet_address_prefix))
    error_message = "subnet_address_prefix must be an IPv4 CIDR with a prefix length between /10 and /28."
  }
}

variable "base_name" {
  type        = string
  description = "Short lowercase name used as a resource-name suffix. Match the platform root."
  default     = "aifnd"

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{1,5}[a-z0-9]$", var.base_name))
    error_message = "base_name must be 3-7 lowercase letters, numbers, or hyphens and must start and end with an alphanumeric character."
  }
}

variable "environment" {
  type        = string
  description = "Deployment environment included in names and tags."
  default     = "dev"

  validation {
    condition     = contains(["dev", "test", "stage", "prod"], var.environment)
    error_message = "environment must be one of dev, test, stage, or prod."
  }
}

variable "runner_resource_group_name" {
  type        = string
  description = "Name of the NEW resource group for the runner VM, NIC, disk, and NSG. Defaults to rg-runner-<base_name>-<environment>. It must not be the Lab's resource group."
  default     = null
  nullable    = true
}

variable "admin_username" {
  type        = string
  description = "Local administrator username. Password sign-in is disabled and nothing can reach the VM over SSH, so this account is only a placeholder that Azure requires."
  default     = "azureadmin"

  validation {
    condition     = can(regex("^[a-z][a-z0-9_-]{0,19}$", var.admin_username)) && !contains(["root", "admin", "administrator", "runner"], var.admin_username)
    error_message = "admin_username must be 1-20 lowercase letters, numbers, underscores, or hyphens, start with a letter, and not be root, admin, administrator, or runner."
  }
}

variable "admin_ssh_public_key" {
  type        = string
  description = "SSH PUBLIC key that Azure requires for a Linux VM that has password sign-in disabled. Not a secret, and the private key is never needed because the VM has no inbound path. Never paste a private key."

  validation {
    condition     = can(regex("^(ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp(256|384|521)) [A-Za-z0-9+/=]+( .*)?$", var.admin_ssh_public_key))
    error_message = "admin_ssh_public_key must be a single OpenSSH public key line, such as one starting with ssh-ed25519 or ssh-rsa."
  }
}

variable "vm_size" {
  type        = string
  description = "Azure VM size for the runner. Standard_D4s_v5 has 4 vCPUs and 16 GiB, enough for the Python, Terraform, and Playwright jobs."
  default     = "Standard_D4s_v5"
}

variable "os_disk_size_gb" {
  type        = number
  description = "OS disk size in GiB. It holds the runner, tool cache, npm and pip caches, and Docker images."
  default     = 128

  validation {
    condition     = var.os_disk_size_gb >= 64 && var.os_disk_size_gb <= 1024
    error_message = "os_disk_size_gb must be between 64 and 1024."
  }
}

variable "os_disk_storage_account_type" {
  type        = string
  description = "OS disk SKU. The default matches the live VM (Standard_LRS), so adopting it does not replace the disk."
  default     = "Standard_LRS"

  validation {
    condition     = contains(["Standard_LRS", "StandardSSD_LRS", "Premium_LRS"], var.os_disk_storage_account_type)
    error_message = "os_disk_storage_account_type must be Standard_LRS, StandardSSD_LRS, or Premium_LRS."
  }
}

variable "patch_mode" {
  type        = string
  description = "VM guest patch mode. The default matches the live VM (AutomaticByPlatform)."
  default     = "AutomaticByPlatform"

  validation {
    condition     = contains(["ImageDefault", "AutomaticByPlatform"], var.patch_mode)
    error_message = "patch_mode must be ImageDefault or AutomaticByPlatform."
  }
}

variable "bypass_platform_safety_checks_on_user_schedule" {
  type        = bool
  description = "Only used with patch_mode = AutomaticByPlatform. The default matches the live VM."
  default     = true
}

variable "github_repository" {
  type        = string
  description = "Repository the runner registers against, in owner/name form. Repository-level runners are visible to this repository only."
  default     = "michael-rechani/foundry-agent-accelerator"

  validation {
    condition     = can(regex("^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$", var.github_repository))
    error_message = "github_repository must be in owner/name form."
  }
}

variable "runner_version" {
  type        = string
  description = "GitHub Actions runner release used to bootstrap the VM. The runner updates itself after it registers, so this only needs a refresh when the download is withdrawn."
  default     = "2.338.0"

  validation {
    condition     = can(regex("^[0-9]+\\.[0-9]+\\.[0-9]+$", var.runner_version))
    error_message = "runner_version must look like 2.338.0."
  }
}

variable "runner_sha256" {
  type        = string
  description = "SHA-256 of actions-runner-linux-x64-<runner_version>.tar.gz, from that release's notes. Provisioning stops if the download doesn't match."
  default     = "af4b794c1bc41d73d40535e3fe092a39f9679cd8d965954c2aca25a05ca41d32"

  validation {
    condition     = can(regex("^[0-9a-f]{64}$", var.runner_sha256))
    error_message = "runner_sha256 must be 64 lowercase hexadecimal characters."
  }
}

variable "idle_shutdown_minutes" {
  type        = number
  description = "Minutes with no job running before the VM deallocates itself through its managed identity. Deallocation stops compute charges. Set to 0 to disable. The check only runs after the runner is registered."
  default     = 30

  validation {
    condition     = var.idle_shutdown_minutes == 0 || (var.idle_shutdown_minutes >= 10 && var.idle_shutdown_minutes <= 1440)
    error_message = "idle_shutdown_minutes must be 0 (disabled) or between 10 and 1440."
  }
}

variable "auto_shutdown" {
  type = object({
    time     = optional(string, "0300")
    timezone = optional(string, "UTC")
  })
  description = "Daily backstop shutdown that deallocates the VM if the idle check fails. time is 24-hour HHmm in the Windows time zone ID given by timezone. A job running at that moment is stopped. Set to null to disable."
  default     = {}

  validation {
    condition     = var.auto_shutdown == null ? true : can(regex("^([01][0-9]|2[0-3])[0-5][0-9]$", var.auto_shutdown.time)) && length(trimspace(var.auto_shutdown.timezone)) > 0
    error_message = "auto_shutdown.time must be 24-hour HHmm, such as 0300, and timezone must be a Windows time zone ID, such as UTC or Pacific Standard Time."
  }
}

variable "tags" {
  type        = map(string)
  description = "Additional tags to merge with the required workload tags."
  default     = {}
}

variable "registry_private_endpoint_ips" {
  type        = list(string)
  description = "Private IP addresses of the Lab container registry private endpoint (registry and data endpoint). When set, the runner may reach only these on TCP 443 so the deploy workflow can push images. Leave empty to keep all VNet traffic denied."
  default     = []

  validation {
    condition     = alltrue([for ip in var.registry_private_endpoint_ips : can(cidrhost("${ip}/32", 0))])
    error_message = "registry_private_endpoint_ips must contain IPv4 addresses only."
  }
}

variable "foundry_private_endpoint_ips" {
  type        = list(string)
  description = "Private IP addresses of the Foundry account's private endpoint. When set, the runner may reach only these on TCP 443 so the approved recording workflow can call the private Foundry account. Leave empty to keep all VNet traffic denied."
  default     = []

  validation {
    condition     = alltrue([for ip in var.foundry_private_endpoint_ips : can(regex("^[0-9]{1,3}(\\.[0-9]{1,3}){3}$", ip)) && can(cidrhost("${ip}/32", 0))])
    error_message = "foundry_private_endpoint_ips must contain IPv4 addresses only."
  }
}

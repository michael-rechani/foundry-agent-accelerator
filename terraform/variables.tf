variable "subscription_id" {
  type        = string
  description = "Azure subscription ID in which to deploy resources. Set this explicitly to avoid targeting the wrong subscription."

  validation {
    condition     = can(regex("^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", var.subscription_id))
    error_message = "subscription_id must be a valid Azure subscription GUID."
  }
}

variable "deployment_principal_id" {
  type        = string
  default     = null
  description = "Stable deployment operator identity when Terraform runs under a private managed identity."
}

variable "deployer_key_vault_secrets_officer" {
  type        = bool
  default     = false
  description = "Grants the deployment principal Key Vault Secrets Officer on the Agent Service Key Vault, so it can create and rotate secrets there, such as the Lab's operator-key verifier. Nothing in this configuration reads or writes that vault, so this is off by default."
}

variable "base_name" {
  type        = string
  description = "Short lowercase name used as a resource-name suffix."
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

variable "location" {
  type        = string
  description = "Optional Azure region override. When null, the first entry in region_preferences is used."
  default     = null
  nullable    = true

  validation {
    condition     = var.location == null || contains(["northcentralus", "westus3", "southcentralus", "westus"], var.location)
    error_message = "location must be null or one of the configured regions in region-preferences.tf."
  }
}

variable "cosmosdb_account_name" {
  type        = string
  description = "Optional Cosmos DB account name override for adopting an existing deployment."
  default     = null
  nullable    = true

  validation {
    condition     = var.cosmosdb_account_name == null || can(regex("^[a-z0-9][a-z0-9-]{1,42}[a-z0-9]$", var.cosmosdb_account_name))
    error_message = "cosmosdb_account_name must be null or a 3-44 character lowercase alphanumeric and hyphen name."
  }
}

variable "agent_storage_account_name" {
  type        = string
  description = "Optional storage account name override for preserving an existing deployment."
  default     = null

  validation {
    condition     = var.agent_storage_account_name == null || can(regex("^[a-z0-9]{3,24}$", var.agent_storage_account_name))
    error_message = "agent_storage_account_name must be null or 3-24 lowercase letters and numbers."
  }
}

variable "virtual_network_address_space" {
  type        = list(string)
  description = "Address space for the workload virtual network."
  default     = ["10.42.0.0/16"]
}

variable "private_endpoint_subnet_address_prefixes" {
  type        = list(string)
  description = "Address prefixes for the subnet containing workload private endpoints."
  default     = ["10.42.0.0/24"]
}

variable "agent_subnet_address_prefixes" {
  type        = list(string)
  description = "Address prefixes for the delegated hosted Agent Service subnet."
  default     = ["10.42.1.0/24"]
}

variable "enable_management_network" {
  type        = bool
  description = "Creates the shared private management network used by the Lab, even when the optional VM and APIM are disabled."
  default     = true
}

variable "enable_jumpbox" {
  type        = bool
  description = "Creates a private Windows jumpbox for administering private Foundry resources. It adds a static public IP for outbound access and a local administrator account, so approve_jumpbox_egress_public_ip = true and approve_jumpbox_admin_account = true are also required."
  default     = false

  validation {
    condition     = !var.enable_jumpbox || var.jumpbox_existing_os_disk != null || var.jumpbox_admin_secret != null
    error_message = "A new jumpbox requires a pinned jumpbox_admin_secret. Supply jumpbox_existing_os_disk only when adopting an existing VM."
  }
}

variable "approve_jumpbox_egress_public_ip" {
  type        = bool
  description = "Explicit approval for the static public IP address that gives the jumpbox outbound internet access through a NAT gateway. The VM has no inbound public address. Required when enable_jumpbox is true."
  default     = false

  validation {
    condition     = var.approve_jumpbox_egress_public_ip || !var.enable_jumpbox
    error_message = "enable_jumpbox creates a static public IP for outbound access. Set approve_jumpbox_egress_public_ip = true only after approving it."
  }
}

variable "approve_jumpbox_admin_account" {
  type        = bool
  description = "Explicit approval for the local Windows administrator account on the jumpbox. Required when enable_jumpbox is true."
  default     = false

  validation {
    condition     = var.approve_jumpbox_admin_account || !var.enable_jumpbox
    error_message = "enable_jumpbox creates a local administrator account on the VM. Set approve_jumpbox_admin_account = true only after approving it."
  }
}

variable "jumpbox_existing_os_disk" {
  type = object({
    id                   = string
    name                 = string
    storage_account_type = string
    size_gb              = optional(number, 127)
    create_option        = optional(string, "FromImage")
  })
  description = "Existing managed OS disk settings to preserve when adopting an existing VM; null for a new VM."
  default     = null

  validation {
    condition = var.jumpbox_existing_os_disk == null ? true : (
      can(regex("(?i)^/subscriptions/[^/]+/resourceGroups/[^/]+/providers/Microsoft.Compute/disks/[^/]+$", var.jumpbox_existing_os_disk.id)) &&
      endswith(lower(var.jumpbox_existing_os_disk.id), "/${lower(var.jumpbox_existing_os_disk.name)}") &&
      contains(["Standard_LRS", "StandardSSD_LRS", "Premium_LRS", "StandardSSD_ZRS", "Premium_ZRS"], var.jumpbox_existing_os_disk.storage_account_type) &&
      contains(["FromImage", "Attach"], var.jumpbox_existing_os_disk.create_option) &&
      var.jumpbox_existing_os_disk.size_gb > 0
    )
    error_message = "jumpbox_existing_os_disk must specify a managed disk ID matching its name, a supported storage type, and a positive size."
  }
}

variable "jumpbox_admin_secret" {
  type = object({
    key_vault_id = string
    name         = string
    version      = string
  })
  description = "Pre-provisioned Key Vault password reference with a pinned version. Required for a new VM; null preserves an adopted VM's credentials. No secret values belong here."
  default     = null

  validation {
    condition = var.jumpbox_admin_secret == null ? true : (
      can(regex("(?i)^/subscriptions/[^/]+/resourceGroups/[^/]+/providers/Microsoft.KeyVault/vaults/[^/]+$", var.jumpbox_admin_secret.key_vault_id)) &&
      can(regex("^[A-Za-z0-9-]{1,127}$", var.jumpbox_admin_secret.name)) &&
      can(regex("^[a-fA-F0-9]{32}$", var.jumpbox_admin_secret.version))
    )
    error_message = "jumpbox_admin_secret requires a vault resource ID, valid secret name, and pinned 32-character version."
  }
}

variable "jumpbox_subnet_address_prefixes" {
  type        = list(string)
  description = "Address prefixes for the private jumpbox subnet."
  default     = ["10.43.0.0/24"]
}

variable "jumpbox_location" {
  type        = string
  description = "Azure region for the jumpbox management VNet. This can differ from the workload region when VM capacity is unavailable."
  default     = "westus"

  validation {
    condition     = contains(["westus", "westus3", "southcentralus", "northcentralus"], var.jumpbox_location)
    error_message = "jumpbox_location must be one of the configured management regions."
  }
}

variable "jumpbox_virtual_network_address_space" {
  type        = list(string)
  description = "Address space for the jumpbox management virtual network."
  default     = ["10.43.0.0/16"]
}

variable "jumpbox_admin_username" {
  type        = string
  description = "Local administrator username for the Windows jumpbox."
  default     = "azureadmin"

  validation {
    condition     = can(regex("^[A-Za-z][A-Za-z0-9._-]{0,19}$", var.jumpbox_admin_username))
    error_message = "jumpbox_admin_username must start with a letter and contain at most 20 letters, numbers, periods, underscores, or hyphens."
  }
}

variable "jumpbox_vm_size" {
  type        = string
  description = "Azure VM size for the Windows jumpbox."
  default     = "Standard_B2s"
}

variable "jumpbox_auto_shutdown" {
  type = object({
    time     = optional(string, "0300")
    timezone = optional(string, "UTC")
  })
  description = "Daily shutdown that deallocates a forgotten jumpbox to stop compute charges. time is 24-hour HHmm in the Windows time zone ID given by timezone. The default is 03:00 UTC, which is late evening across the United States. Set to null to disable."
  default     = {}

  validation {
    condition     = var.jumpbox_auto_shutdown == null ? true : can(regex("^([01][0-9]|2[0-3])[0-5][0-9]$", var.jumpbox_auto_shutdown.time)) && length(trimspace(var.jumpbox_auto_shutdown.timezone)) > 0
    error_message = "jumpbox_auto_shutdown.time must be 24-hour HHmm, such as 0300, and timezone must be a Windows time zone ID, such as UTC or Pacific Standard Time."
  }
}

variable "enable_api_management" {
  type        = bool
  description = "Creates a Standard v2 API Management gateway for governed client access to agent APIs. The gateway and its management plane are publicly reachable, so approve_public_api_management = true is also required."
  default     = false
}

variable "approve_public_api_management" {
  type        = bool
  description = "Explicit approval for a publicly reachable API Management gateway (External network mode, public management plane). Required when enable_api_management is true."
  default     = false

  validation {
    condition     = var.approve_public_api_management || !var.enable_api_management
    error_message = "enable_api_management creates a publicly reachable gateway. Set approve_public_api_management = true only after approving public exposure."
  }
}

variable "api_management_location" {
  type        = string
  description = "Azure region for API Management and its virtual network integration subnet."
  default     = "westus"

  validation {
    condition     = contains(["westus", "westus3", "southcentralus", "northcentralus"], var.api_management_location)
    error_message = "api_management_location must be one of the configured management regions."
  }
}

variable "api_management_subnet_address_prefixes" {
  type        = list(string)
  description = "Address prefixes for the dedicated API Management virtual network integration subnet."
  default     = ["10.43.1.0/24"]
}

variable "api_management_publisher_email" {
  type        = string
  description = "Publisher email, required only when API Management is enabled."
  default     = null

  validation {
    condition     = var.api_management_publisher_email == null ? !var.enable_api_management : can(regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$", var.api_management_publisher_email))
    error_message = "api_management_publisher_email must be a valid email address when supplied and is required when API Management is enabled."
  }
}

variable "api_management_publisher_name" {
  type        = string
  description = "Name shown as the API Management service publisher."
  default     = "AI Foundry Platform"
}

check "api_management_management_network" {
  assert {
    condition     = !var.enable_api_management || var.api_management_location == var.jumpbox_location
    error_message = "api_management_location must equal jumpbox_location, which selects the shared management VNet region. The admin VM can remain disabled."
  }
}

variable "review_api" {
  type = object({
    audience                  = string
    allowed_caller_object_ids = set(string)
    allowed_client_app_ids    = set(string)
    agent_name                = optional(string, "review-coordinator-agent")
  })
  description = "Opt-in coordinator API authorization. Use a dedicated Entra API audience and explicit principal and client application allowlists. Null leaves the API unpublished."
  default     = null

  validation {
    condition     = var.review_api == null ? true : var.enable_api_management
    error_message = "review_api requires enable_api_management = true."
  }

  validation {
    condition     = var.review_api == null ? true : can(regex("^[A-Za-z_][A-Za-z0-9_-]{0,63}$", var.review_api.agent_name))
    error_message = "review_api requires a valid named agent, not a URL or path."
  }

  validation {
    condition = var.review_api == null ? true : (
      can(regex("^(api://)?[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", var.review_api.audience)) &&
      length(var.review_api.allowed_caller_object_ids) > 0 &&
      length(var.review_api.allowed_client_app_ids) > 0 &&
      alltrue([for id in setunion(var.review_api.allowed_caller_object_ids, var.review_api.allowed_client_app_ids) : can(regex("^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", id))])
    )
    error_message = "review_api requires a GUID or api://GUID audience and nonempty GUID-only caller object ID and client application ID allowlists."
  }
}

variable "coordinator_agent_access" {
  type = object({
    principal_id      = string
    specialist_agents = optional(set(string), ["application-review-agent", "case-review-agent"])
  })
  description = "Opt-in Foundry Agent Consumer grants that let the review coordinator call its specialists. Set principal_id to the coordinator's instance_identity.principal_id, which the hosted-agent deployer prints. Null creates no grants."
  default     = null

  validation {
    condition     = var.coordinator_agent_access == null ? true : can(regex("^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", var.coordinator_agent_access.principal_id))
    error_message = "coordinator_agent_access.principal_id must be a principal GUID, not an application or client ID."
  }

  validation {
    condition = var.coordinator_agent_access == null ? true : (
      length(var.coordinator_agent_access.specialist_agents) > 0 &&
      alltrue([for name in var.coordinator_agent_access.specialist_agents : can(regex("^[A-Za-z_][A-Za-z0-9_-]{0,63}$", name))])
    )
    error_message = "coordinator_agent_access.specialist_agents must list at least one valid agent name, not a URL or path."
  }
}

variable "model_deployment" {
  type = object({
    deployment_name = string
    format          = string
    name            = string
    version         = string
    sku_name        = string
    capacity        = number
  })
  description = "Foundry model deployment. Confirm regional availability and quota before applying."
  default = {
    deployment_name = "gpt-4.1"
    format          = "OpenAI"
    name            = "gpt-4.1"
    version         = "2025-04-14"
    sku_name        = "GlobalStandard"
    capacity        = 10
  }

  validation {
    condition     = var.model_deployment.capacity > 0
    error_message = "Model capacity must be greater than zero."
  }
}

variable "additional_model_deployments" {
  type = map(object({
    format   = optional(string, "OpenAI")
    name     = string
    version  = string
    sku_name = optional(string, "GlobalStandard")
    capacity = number
  }))
  description = "Extra Foundry model deployments, keyed by deployment name. Agents created in the Lab can use a different one for each kind of work. Confirm regional availability and quota before applying."
  default     = {}

  validation {
    condition = alltrue([
      for name, deployment in var.additional_model_deployments :
      can(regex("^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$", name)) && name != var.model_deployment.deployment_name && deployment.capacity > 0
    ])
    error_message = "Key each extra deployment by a unique deployment name other than the primary one, and give it capacity greater than zero."
  }
}

variable "enable_agent_service" {
  type        = bool
  description = "Creates the Agent Service capability host and its development supporting resources."
  default     = true
}

variable "ai_search_sku" {
  type        = string
  description = "Tier for the Agent Service AI Search service: basic or standard. Azure can't change the tier of an existing service in place, so changing this replaces the service and any search indexes in it."
  default     = "standard"

  validation {
    condition     = contains(["basic", "standard"], var.ai_search_sku)
    error_message = "Use basic or standard for the AI Search tier."
  }
}

variable "ai_search_replica_count" {
  type        = number
  description = "Replicas for the Agent Service AI Search service. Each replica is billed as a full search unit. One replica has no availability SLA; use two for a read SLA or three for a read-write SLA. The basic tier allows up to 3 replicas."
  default     = 1

  validation {
    condition     = var.ai_search_replica_count >= 1 && var.ai_search_replica_count <= (var.ai_search_sku == "basic" ? 3 : 12) && floor(var.ai_search_replica_count) == var.ai_search_replica_count
    error_message = "Use a whole number of AI Search replicas from 1 to 12, or from 1 to 3 on the basic tier."
  }
}

variable "tags" {
  type        = map(string)
  description = "Additional tags to merge with the required workload tags."
  default     = {}
}


terraform {
  required_version = "~> 1.16.4"
  required_providers {
    azapi = {
      source  = "Azure/azapi"
      version = "~> 2.12.0"
    }
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.81"
    }
    # Needed by the Front Door AVM module (front-door.tf). Declared here so the offline tests can mock it.
    modtm = {
      source  = "azure/modtm"
      version = "~> 0.3"
    }
  }
}

provider "azapi" {
  subscription_id = var.subscription_id
}

provider "azurerm" {
  features {}
  subscription_id = var.subscription_id
}

variable "subscription_id" {
  type        = string
  description = "ID of the Azure subscription that holds the platform resources and receives the Lab."
}
variable "resource_group_name" {
  type        = string
  description = "Existing resource group that holds the Lab resources."
}
variable "workload_vnet_name" {
  type        = string
  description = "Existing workload virtual network. The Lab subnet and the registry private endpoint go here."
}
variable "management_vnet_name" {
  type        = string
  description = "Existing management virtual network, linked to the registry private DNS zone so the jumpbox can reach the registry."
}
variable "foundry_account_name" {
  type        = string
  description = "Name of the existing Foundry account. The Lab calls its project endpoint."
}
variable "foundry_project_name" {
  type        = string
  description = "Name of the existing Foundry project. The Lab identity gets Foundry User on it."
}
variable "registry_name" {
  type        = string
  description = "Name of the container registry to create. It must be globally unique."
}
variable "private_registry_enabled" {
  type        = bool
  default     = true
  description = "Reaches the registry through a private endpoint and private DNS zone, which needs the Premium tier. The default is true. When false, the registry is Basic with no private endpoint."
}
variable "registry_public_network_access_enabled" {
  type        = bool
  default     = false
  description = "Whether the registry accepts connections from public networks. The default is false: only the private endpoint can reach it. Setting it to true exposes the registry's public endpoint to the internet. Sign-in is still required and the admin user stays off. Don't set it to true without the environment owner's approval."
}
variable "visible_agents" {
  type        = list(string)
  default     = ["customer-review"]
  description = "IDs of the agents from agents.json that the Lab shows to visitors."
  validation {
    condition     = length(var.visible_agents) > 0 && alltrue([for agent in var.visible_agents : contains([for configured in jsondecode(file("${path.module}/../agents.json")) : configured.id], agent)])
    error_message = "Select at least one configured workbench agent ID."
  }
}
variable "default_agent" {
  type        = string
  default     = null
  description = "ID of the visible agent the Lab opens first. Null means the first entry in visible_agents."
  validation {
    condition     = var.default_agent == null ? true : contains(var.visible_agents, var.default_agent)
    error_message = "The default agent must be visible in the workbench."
  }
}
variable "workspace_title" {
  type        = string
  default     = "Foundry Agent Lab"
  description = "Title the Lab shows for itself. One to 80 printable characters."
  validation {
    condition     = length(trimspace(var.workspace_title)) > 0 && length(var.workspace_title) <= 80 && !can(regex("[[:cntrl:]]", var.workspace_title))
    error_message = "Use a workspace title of one to 80 printable characters."
  }
}
variable "agent_creation_enabled" {
  type        = bool
  default     = false
  description = "Opt in to operator-confirmed Foundry hosted-agent publication from built-in templates."
}
variable "agent_creation_model" {
  type        = string
  default     = ""
  description = "Default existing Foundry model deployment for newly created agents, used for any kind of work without its own entry in agent_creation_models. Not a browser setting."
  validation {
    condition     = var.agent_creation_model == "" || can(regex("^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$", var.agent_creation_model))
    error_message = "Use an existing model deployment name."
  }
}
variable "agent_creation_models" {
  type        = map(string)
  default     = {}
  description = "Optional existing model deployment for each kind of work a template does: reasoning, extraction, or tool_calling. The Lab picks one from the template; unlisted kinds use agent_creation_model."
  validation {
    condition = alltrue([
      for profile, deployment in var.agent_creation_models :
      contains(["reasoning", "extraction", "tool_calling"], profile) && can(regex("^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$", deployment))
    ])
    error_message = "Use only the reasoning, extraction, and tool_calling keys, each set to an existing model deployment name."
  }
}
variable "agent_creation_key_secret_id" {
  type        = string
  default     = null
  description = "Existing Key Vault secret URI containing the lowercase SHA-256 operator-key verifier, never the raw key. Its access must be provisioned separately unless agent_creation_key_secret_resource_id is set."
  validation {
    condition     = var.agent_creation_key_secret_id == null ? true : can(regex("^https://[A-Za-z0-9-]+\\.vault\\.azure\\.net/secrets/[A-Za-z0-9-]+(/[A-Za-z0-9]+)?$", var.agent_creation_key_secret_id))
    error_message = "Use an existing Key Vault secret URI."
  }
}
variable "agent_creation_key_secret_resource_id" {
  type        = string
  default     = null
  description = "Optional Azure resource ID of the Key Vault secret that agent_creation_key_secret_id points to. When set, Terraform gives the Lab identity Key Vault Secrets User on only that secret. Leave it null if the environment owner provisions that access separately."
  validation {
    condition     = var.agent_creation_key_secret_resource_id == null ? true : can(regex("^/subscriptions/[0-9a-fA-F-]{36}/resourceGroups/[A-Za-z0-9._()-]+/providers/Microsoft\\.KeyVault/vaults/[A-Za-z0-9-]+/secrets/[A-Za-z0-9-]+$", var.agent_creation_key_secret_resource_id))
    error_message = "Use the Azure resource ID of an existing Key Vault secret."
  }
}
variable "model_limits" {
  type = map(object({
    requests_per_minute = number
    tokens_per_minute   = number
  }))
  default = {
    "gpt-5.4"      = { requests_per_minute = 100, tokens_per_minute = 10000 }
    "gpt-4.1"      = { requests_per_minute = 50, tokens_per_minute = 50000 }
    "gpt-5.4-mini" = { requests_per_minute = 10, tokens_per_minute = 10000 }
  }
  description = "The published requests-per-minute and tokens-per-minute limit of each model deployment the Lab's chat can reach, keyed by deployment name. The Lab answers busy (HTTP 429) before admitting a turn that would pass a deployment's limit, so people see its friendly message instead of the model's error. The defaults are the dev tenant's limits; replace them with your deployments' real limits, and leave some headroom. Deployments not listed here, and prebuilt agents, are limited only by the Lab's global caps. Use {} to turn this off. This sets no Foundry quota."
  validation {
    condition = alltrue([
      for deployment, limit in var.model_limits :
      can(regex("^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$", deployment)) &&
      alltrue([for value in [limit.requests_per_minute, limit.tokens_per_minute] : value == floor(value) && value >= 1 && value <= 10000000])
    ])
    error_message = "Key each limit by an existing model deployment name, and give requests_per_minute and tokens_per_minute as whole numbers from 1 to 10000000."
  }
}
variable "name" {
  type        = string
  default     = "foundry-workbench"
  description = "Name of the Lab Container App. It also prefixes the names of the Lab's identity, environment, subnet, workspace, and alerts."
}
variable "subnet_prefix" {
  type        = string
  default     = "10.42.2.0/24"
  description = "Address range of the delegated Container Apps subnet in the workload virtual network. It must not overlap another subnet."
}
data "azurerm_virtual_network" "workload" {
  name                = var.workload_vnet_name
  resource_group_name = var.resource_group_name
}
data "azurerm_virtual_network" "management" {
  name                = var.management_vnet_name
  resource_group_name = var.resource_group_name
}
data "azurerm_subnet" "management" {
  name                 = "snet-jumpbox"
  virtual_network_name = var.management_vnet_name
  resource_group_name  = var.resource_group_name
}

locals {
  project_id = "/subscriptions/${var.subscription_id}/resourceGroups/${var.resource_group_name}/providers/Microsoft.CognitiveServices/accounts/${var.foundry_account_name}/projects/${var.foundry_project_name}"
  hostname   = "${var.name}.${azurerm_container_app_environment.this.default_domain}"
  tags       = { workload = "foundry-workbench", managed-by = "terraform" }
}

resource "azurerm_subnet" "this" {
  name                 = "snet-${var.name}"
  address_prefixes     = [var.subnet_prefix]
  virtual_network_name = data.azurerm_virtual_network.workload.name
  resource_group_name  = var.resource_group_name
  delegation {
    name = "container-apps"
    service_delegation {
      name    = "Microsoft.App/environments"
      actions = ["Microsoft.Network/virtualNetworks/subnets/join/action"]
    }
  }
}

resource "azurerm_container_registry" "this" {
  name                          = var.registry_name
  location                      = data.azurerm_virtual_network.workload.location
  resource_group_name           = var.resource_group_name
  sku                           = var.private_registry_enabled ? "Premium" : "Basic"
  public_network_access_enabled = var.registry_public_network_access_enabled
  admin_enabled                 = false
  tags                          = local.tags
}

resource "azurerm_user_assigned_identity" "this" {
  name                = "id-${var.name}"
  location            = data.azurerm_virtual_network.workload.location
  resource_group_name = var.resource_group_name
  tags                = local.tags
}

resource "azurerm_role_assignment" "pull" {
  scope                = azurerm_container_registry.this.id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_user_assigned_identity.this.principal_id
}
# Foundry User: Lab calls and opt-in publication, scoped to the configured project.
resource "azurerm_role_assignment" "foundry" {
  scope              = local.project_id
  role_definition_id = "/subscriptions/${var.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/53ca6127-db72-4b80-b1b0-d745d6d5456d"
  principal_id       = azurerm_user_assigned_identity.this.principal_id
}
# Key Vault Secrets User: lets the Container App resolve its Key Vault reference
# to the operator-key verifier. It covers that one secret only. The variable is
# optional so an environment owner can still provision this access separately.
resource "azurerm_role_assignment" "creation_key_verifier" {
  count              = var.agent_creation_key_secret_resource_id == null ? 0 : 1
  scope              = var.agent_creation_key_secret_resource_id
  role_definition_id = "/subscriptions/${var.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/4633458b-17de-408a-b874-0445c86b69e6"
  principal_id       = azurerm_user_assigned_identity.this.principal_id
  description        = "Foundry Lab agent creation"
  lifecycle {
    precondition {
      condition = try(
        [for part in regex("^https://([A-Za-z0-9-]+)\\.vault\\.azure\\.net/secrets/([A-Za-z0-9-]+)", var.agent_creation_key_secret_id) : lower(part)] ==
        [for part in regex("/vaults/([A-Za-z0-9-]+)/secrets/([A-Za-z0-9-]+)$", var.agent_creation_key_secret_resource_id) : lower(part)],
        false,
      )
      error_message = "Set agent_creation_key_secret_id, and make agent_creation_key_secret_resource_id the resource ID of that same vault and secret."
    }
  }
}

resource "azurerm_container_app_environment" "this" {
  name                           = "cae-${var.name}"
  location                       = data.azurerm_virtual_network.workload.location
  resource_group_name            = var.resource_group_name
  infrastructure_subnet_id       = azurerm_subnet.this.id
  internal_load_balancer_enabled = true
  public_network_access          = "Disabled"
  logs_destination               = "azure-monitor"
  workload_profile {
    name                  = "Consumption"
    workload_profile_type = "Consumption"
  }
  tags = local.tags
}

resource "azurerm_private_dns_zone" "this" {
  name                = azurerm_container_app_environment.this.default_domain
  resource_group_name = var.resource_group_name
  tags                = local.tags
}
resource "azurerm_private_dns_a_record" "this" {
  for_each            = toset(["*", "@"])
  name                = each.value
  zone_name           = azurerm_private_dns_zone.this.name
  resource_group_name = var.resource_group_name
  ttl                 = 60
  records             = [azurerm_container_app_environment.this.static_ip_address]
}
resource "azurerm_private_dns_zone_virtual_network_link" "this" {
  for_each              = { workload = data.azurerm_virtual_network.workload.id, management = data.azurerm_virtual_network.management.id }
  name                  = "${var.name}-${each.key}"
  private_dns_zone_name = azurerm_private_dns_zone.this.name
  resource_group_name   = var.resource_group_name
  virtual_network_id    = each.value
}

resource "azurerm_container_app" "this" {
  count                        = var.bootstrap_only ? 0 : 1
  name                         = var.name
  resource_group_name          = var.resource_group_name
  container_app_environment_id = azurerm_container_app_environment.this.id
  revision_mode                = "Single"
  workload_profile_name        = "Consumption"
  tags                         = local.tags
  lifecycle {
    prevent_destroy = true
    precondition {
      condition     = !var.agent_creation_enabled || (var.agent_creation_model != "" && var.agent_creation_key_secret_id != null)
      error_message = "Agent creation requires an existing model deployment and an operator-key verifier secret."
    }
  }
  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.this.id]
  }
  registry {
    server   = azurerm_container_registry.this.login_server
    identity = azurerm_user_assigned_identity.this.id
  }
  dynamic "secret" {
    for_each = var.agent_creation_key_secret_id == null ? [] : [var.agent_creation_key_secret_id]
    content {
      name                = "agent-creation-key-verifier"
      identity            = azurerm_user_assigned_identity.this.id
      key_vault_secret_id = secret.value
    }
  }
  ingress {
    external_enabled           = true
    allow_insecure_connections = false
    target_port                = 8080
    transport                  = "http"
    ip_security_restriction {
      name             = "jumpbox-only"
      action           = "Allow"
      ip_address_range = data.azurerm_subnet.management.address_prefixes[0]
    }
    # Only while Front Door is enabled, and only private ranges (see front-door.tf).
    dynamic "ip_security_restriction" {
      for_each = local.front_door_ingress_rules
      content {
        name             = ip_security_restriction.key
        action           = "Allow"
        ip_address_range = ip_security_restriction.value
      }
    }
    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }
  template {
    # Admission limits, publication tasks, and review runs are process-local; see
    # docs/lab-configuration-and-cost.md (Storage and cost) before raising replicas.
    min_replicas = 1
    max_replicas = 1
    container {
      name   = "workbench"
      image  = "${azurerm_container_registry.this.login_server}/workbench@${var.image_digest}"
      cpu    = 0.5
      memory = "1Gi"
      dynamic "env" {
        for_each = merge(
          {
            WORKBENCH_MODE                   = "private"
            WORKBENCH_TITLE                  = var.workspace_title
            WORKBENCH_COSMOS_ENDPOINT        = local.cosmos_endpoint
            WORKBENCH_VISIBLE_AGENTS         = join(",", var.visible_agents)
            WORKBENCH_DEFAULT_AGENT          = coalesce(var.default_agent, var.visible_agents[0])
            WORKBENCH_AGENT_CREATION_ENABLED = tostring(var.agent_creation_enabled)
            WORKBENCH_AGENT_CREATION_MODEL   = var.agent_creation_model
            WORKBENCH_ALLOWED_HOSTS          = local.hostname
            WORKBENCH_ORIGINS                = join(",", compact(["https://${local.hostname}", local.front_door_endpoint_host == null ? "" : "https://${local.front_door_endpoint_host}"]))
            FOUNDRY_PROJECT_ENDPOINT         = "https://${var.foundry_account_name}.services.ai.azure.com/api/projects/${var.foundry_project_name}"
            WORKBENCH_FOUNDRY_PROJECT_ID     = local.project_id
            AZURE_CLIENT_ID                  = azurerm_user_assigned_identity.this.client_id
          },
          length(var.agent_creation_models) == 0 ? {} : {
            WORKBENCH_AGENT_CREATION_MODELS = jsonencode(var.agent_creation_models)
          },
          length(var.model_limits) == 0 ? {} : {
            WORKBENCH_MODEL_LIMITS = jsonencode(var.model_limits)
          },
          var.lab_budget == null ? {} : {
            WORKBENCH_BUDGET_ALERTS_ENABLED = "true"
          },
        )
        content {
          name  = env.key
          value = env.value
        }
      }
      dynamic "env" {
        for_each = var.agent_creation_key_secret_id == null ? [] : [true]
        content {
          name        = "WORKBENCH_CREATION_KEY_SHA256"
          secret_name = "agent-creation-key-verifier"
        }
      }
      readiness_probe {
        transport = "HTTP"
        port      = 8080
        path      = "/healthz"
        header {
          name  = "Host"
          value = local.hostname
        }
      }
      liveness_probe {
        transport = "HTTP"
        port      = 8080
        path      = "/healthz"
        header {
          name  = "Host"
          value = local.hostname
        }
      }
    }
  }
  depends_on = [azurerm_role_assignment.pull, azurerm_role_assignment.foundry, azurerm_role_assignment.creation_key_verifier, azurerm_cosmosdb_sql_role_assignment.history]
}

output "registry_name" { value = azurerm_container_registry.this.name }
output "private_url" { value = var.bootstrap_only ? null : "https://${local.hostname}" }
output "internal_ip" { value = azurerm_container_app_environment.this.static_ip_address }
# Optional Azure Front Door Premium in front of the Lab, limited to your own machine's public IP.
# Everything is off by default. See docs/ingress-access.md (Pattern B) before turning it on.
#
# Traffic path: allowed client -> Front Door endpoint (public name, WAF-filtered)
#   -> Private Link -> the Lab's internal Container Apps environment.
# The endpoint name is public. The WAF blocks every client that is not in front_door_allowed_cidrs,
# and the Private Link connection stays Pending until an operator approves it on the environment.

variable "enable_front_door" {
  type        = bool
  default     = false
  description = "Creates an Azure Front Door Premium profile, endpoint, WAF, and Private Link origin for the Lab. The endpoint hostname is publicly resolvable, so approve_public_front_door = true is also required. Premium is billed per profile (see docs/lab-configuration-and-cost.md)."
}

variable "approve_public_front_door" {
  type        = bool
  default     = false
  description = "Explicit approval for a publicly resolvable Front Door endpoint. Required when enable_front_door is true."

  validation {
    condition     = var.approve_public_front_door || !var.enable_front_door
    error_message = "enable_front_door creates a publicly resolvable endpoint. Set approve_public_front_door = true only after approving public exposure."
  }
}

variable "front_door_allowed_cidrs" {
  type        = list(string)
  default     = []
  description = "Public client addresses the Front Door WAF allows, as single hosts: a.b.c.d/32, or an IPv6 address ending /128. Everything else gets a 403. Keep real addresses in ignored deployment inputs, not in committed files."

  validation {
    condition     = !var.enable_front_door || length(var.front_door_allowed_cidrs) > 0
    error_message = "Set at least one address in front_door_allowed_cidrs when enable_front_door is true."
  }

  validation {
    condition     = length(var.front_door_allowed_cidrs) <= 10
    error_message = "List at most 10 addresses. This allow list is for named people, not a network."
  }

  validation {
    condition = alltrue([
      for cidr in var.front_door_allowed_cidrs :
      try(can(cidrhost(cidr, 0)) && endswith(cidr, strcontains(cidr, ":") ? "/128" : "/32"), false)
    ])
    error_message = "Each entry must be one host address: a.b.c.d/32 for IPv4 or an IPv6 address ending /128. Ranges and 0.0.0.0/0 are rejected."
  }

  validation {
    condition = alltrue([
      for cidr in var.front_door_allowed_cidrs :
      try(
        strcontains(cidr, ":")
        ? !can(regex("^(::1?|f[cd][0-9a-f]{2}:.*|fe[89ab][0-9a-f]:.*)$", cidrhost(cidr, 0)))
        : !anytrue([
          for o in [[for part in split(".", cidrhost(cidr, 0)) : tonumber(part)]] :
          o[0] == 0 || o[0] == 10 || o[0] == 127 || o[0] >= 224 ||
          (o[0] == 100 && o[1] >= 64 && o[1] <= 127) ||
          (o[0] == 169 && o[1] == 254) ||
          (o[0] == 172 && o[1] >= 16 && o[1] <= 31) ||
          (o[0] == 192 && o[1] == 168)
        ]),
        false
      )
    ])
    error_message = "Use your public address. Private, loopback, link-local, multicast, and unspecified addresses never reach Front Door."
  }
}

variable "front_door_private_link_location" {
  type        = string
  default     = null
  description = "Region of the Front Door Private Link connection to the Lab environment. Null uses the environment's region. If that region does not support Front Door Private Link (North Central US does not), set the nearest supported one, such as centralus."
}

variable "front_door_ingress_allow_cidrs" {
  type        = list(string)
  default     = []
  description = "Private source ranges, besides the jump box, that the Lab's Container App ingress admits while Front Door is enabled. Front Door's Private Link traffic reaches the app from the shared address space 100.64.0.0/10, not from the Lab's own network (measured in the first approved test, #240), so set this to [\"100.64.0.0/10\"]. Accepted: private IPv4 ranges of /16 or narrower, or 100.64.0.0/10 or narrower. Nothing public or broader is accepted, so this can never become an internet-wide rule."

  validation {
    condition = alltrue([
      for cidr in var.front_door_ingress_allow_cidrs :
      try(
        can(cidrhost(cidr, 0)) &&
        !strcontains(cidr, ":") &&
        anytrue([
          for o in [[for part in split(".", cidrhost(cidr, 0)) : tonumber(part)]] :
          (
            tonumber(split("/", cidr)[1]) >= 16 &&
            (o[0] == 10 || (o[0] == 172 && o[1] >= 16 && o[1] <= 31) || (o[0] == 192 && o[1] == 168))
            ) || (
            tonumber(split("/", cidr)[1]) >= 10 && o[0] == 100 && o[1] >= 64 && o[1] <= 127
          )
        ]),
        false
      )
    ])
    error_message = "Use private IPv4 ranges inside 10.0.0.0/8, 172.16.0.0/12, or 192.168.0.0/16 with a prefix of /16 or longer, or 100.64.0.0/10 or a narrower range inside it."
  }
}

locals {
  front_door_compact_name = replace(var.name, "-", "")
  front_door_ingress_rules = var.enable_front_door ? {
    for index, cidr in var.front_door_ingress_allow_cidrs : "front-door-${index + 1}" => cidr
  } : {}
}

module "front_door" {
  count   = var.enable_front_door ? 1 : 0
  source  = "Azure/avm-res-cdn-profile/azurerm"
  version = "0.1.9"

  name                = "afd-${var.name}"
  resource_group_name = local.resource_group_name
  location            = "global"
  # Private Link origins need Premium; Standard cannot reach the internal environment.
  sku = "Premium_AzureFrontDoor"
  # The Lab's own model call timeout is up to 180 seconds.
  response_timeout_seconds = 200
  tags                     = local.tags
  enable_telemetry         = true

  front_door_endpoints = {
    lab = { name = "ep-${var.name}" }
  }

  front_door_origin_groups = {
    lab = {
      name = "lab"
      health_probe = {
        healthz = {
          interval_in_seconds = 60
          path                = "/healthz"
          protocol            = "Https"
          request_type        = "GET"
        }
      }
      load_balancing = {
        default = {}
      }
    }
  }

  front_door_origins = {
    lab = {
      name                           = "lab"
      origin_group_key               = "lab"
      host_name                      = local.hostname
      host_header                    = local.hostname
      certificate_name_check_enabled = true
      private_link = {
        environment = {
          request_message        = "Foundry Agent Lab Front Door"
          target_type            = "managedEnvironments"
          location               = coalesce(var.front_door_private_link_location, azurerm_container_app_environment.this.location)
          private_link_target_id = azurerm_container_app_environment.this.id
        }
      }
    }
  }

  front_door_routes = {
    lab = {
      name                = "lab"
      endpoint_key        = "lab"
      origin_group_key    = "lab"
      origin_keys         = ["lab"]
      patterns_to_match   = ["/*"]
      supported_protocols = ["Http", "Https"]
    }
  }

  # SocketAddr is the address Front Door sees connecting, so a forged X-Forwarded-For header cannot
  # satisfy it. Block everything that is not on the list, in Prevention mode.
  front_door_firewall_policies = {
    lab = {
      name                              = "waf${local.front_door_compact_name}"
      resource_group_name               = local.resource_group_name
      sku_name                          = "Premium_AzureFrontDoor"
      mode                              = "Prevention"
      custom_block_response_status_code = 403
      custom_rules = {
        allow_listed_clients_only = {
          name     = "BlockUnlistedClients"
          priority = 1
          type     = "MatchRule"
          action   = "Block"
          match_conditions = {
            not_allowed = {
              match_variable     = "SocketAddr"
              operator           = "IPMatch"
              negation_condition = true
              match_values       = var.front_door_allowed_cidrs
            }
          }
        }
      }
      tags = local.tags
    }
  }

  front_door_security_policies = {
    lab = {
      name = "waf-${var.name}"
      firewall = {
        front_door_firewall_policy_key = "lab"
        association = {
          endpoint_keys     = ["lab"]
          patterns_to_match = ["/*"]
        }
      }
    }
  }
}

locals {
  front_door_endpoint_host   = var.enable_front_door ? module.front_door[0].frontdoor_endpoints["lab"].host_name : null
  front_door_diagnostic_name = "diag-front-door-240"
}

# Probe, WAF and access logs go to the Lab's own private workspace. The WAF log is the way to see
# which client address Front Door saw for a blocked request. The setting is named after #240, where
# it was first created by hand; the dev Lab adopted it into state in #256.
resource "azurerm_monitor_diagnostic_setting" "front_door" {
  count = var.enable_front_door ? 1 : 0

  name                       = local.front_door_diagnostic_name
  target_resource_id         = module.front_door[0].resource_id
  log_analytics_workspace_id = azapi_resource.logs.id

  enabled_log {
    category = "FrontDoorHealthProbeLog"
  }
  enabled_log {
    category = "FrontDoorWebApplicationFirewallLog"
  }
  enabled_log {
    category = "FrontDoorAccessLog"
  }
}

output "front_door_url" {
  value       = local.front_door_endpoint_host == null ? null : "https://${local.front_door_endpoint_host}"
  description = "Public Front Door address of the Lab. It only answers allow-listed clients, and only after the Private Link connection on the Container Apps environment is approved."
}

variable "search_service_id" {
  type        = string
  description = "Resource ID of the Azure AI Search service that holds the index: the platform's Agent Service Search service. It stays private; this module never changes it."

  validation {
    condition     = can(regex("(?i)^/subscriptions/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/resourceGroups/[^/]+/providers/Microsoft\\.Search/searchServices/[^/]+$", var.search_service_id))
    error_message = "search_service_id must be the resource ID of a Search service, not an index, a resource group, or a URL."
  }
}

variable "principal_id" {
  type        = string
  description = "Object ID of the agent's managed identity, which the hosted-agent deployer prints as instance_identity.principal_id. It receives the read-only role on the one index."

  validation {
    condition     = can(regex("^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", var.principal_id))
    error_message = "principal_id must be a principal GUID, not an application or client ID."
  }
}

variable "index_name" {
  type        = string
  description = "The one index the agent may query. The index script creates it before this module runs; this module doesn't manage it."
  default     = "lab-sample-policy-guidance"

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{0,127}$", var.index_name))
    error_message = "index_name must be a Search index name: lowercase letters, digits and dashes, starting with a letter or digit."
  }
}

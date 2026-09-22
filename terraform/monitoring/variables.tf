variable "subscription_id" {
  type        = string
  description = "Explicit subscription containing the existing Foundry project."
  validation {
    condition     = can(regex("^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", var.subscription_id))
    error_message = "subscription_id must be an Azure subscription GUID."
  }
}

variable "resource_group_name" {
  type        = string
  description = "Existing resource group containing Foundry and Azure Monitor."
}

variable "foundry_account_name" {
  type        = string
  description = "Existing Foundry account name."
}

variable "project_name" {
  type        = string
  description = "Existing Foundry project name."
}

variable "workspace_name" {
  type        = string
  description = "Existing private Log Analytics workspace; this root does not manage it."
}

variable "private_link_scope_name" {
  type        = string
  description = "Existing Azure Monitor Private Link Scope with working private DNS and routing."
}

variable "application_insights_name" {
  type        = string
  description = "Name of the dedicated Application Insights component."
}

variable "agent_principal_ids" {
  type        = map(string)
  description = "Hosted agent names mapped to their Entra principal IDs, not application/client IDs."
  default     = {}
  validation {
    condition     = alltrue([for id in values(var.agent_principal_ids) : can(regex("^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", id))])
    error_message = "Every agent_principal_ids value must be a principal GUID."
  }
}

variable "enable_project_connection" {
  type        = bool
  description = "Enable only after all deployed agent versions disable sensitive content recording. Connecting starts project-wide tracing."
  default     = false
}

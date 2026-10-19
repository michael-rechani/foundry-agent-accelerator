variable "subscription_id" {
  type        = string
  description = "Subscription that holds the Lab, the runner and the Foundry account."

  validation {
    condition     = can(regex("^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", var.subscription_id))
    error_message = "subscription_id must be an Azure subscription GUID."
  }
}

variable "github_repository" {
  type        = string
  description = "Repository that runs the workflows, as owner/name."

  validation {
    condition     = can(regex("^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", var.github_repository))
    error_message = "github_repository must look like owner/name."
  }
}

variable "github_owner_type" {
  type        = string
  description = "Whether the repository owner is a user or an organization. GitHub signs its token with the owner's numeric ID, so Terraform looks it up."
  default     = "user"

  validation {
    condition     = contains(["user", "organization"], var.github_owner_type)
    error_message = "github_owner_type must be user or organization."
  }
}

variable "deploy_environment" {
  type        = string
  description = "GitHub environment that gates the Lab image deploy workflow."
  default     = "lab-deploy"
}

variable "recording_environment" {
  type        = string
  description = "GitHub environment that gates the library recording workflow."
  default     = "library-recording"
}

variable "enable_library_recording" {
  type        = bool
  description = "Creates the identity and environment for the Record library answers workflow. It can call the Foundry account's models, which is billable, so it needs recording_reviewer_user_ids."
  default     = true
}

variable "recording_reviewer_user_ids" {
  type        = list(number)
  description = "Numeric GitHub user IDs that must approve each library recording run. Required while enable_library_recording is true, so nothing is sent without approval."
  default     = []
}

variable "deploy_federated_subject" {
  type        = string
  description = "Overrides the subject Azure accepts for the deploy identity. Set it from the \"No matching federated identity record\" error if sign-in fails."
  default     = null
}

variable "recording_federated_subject" {
  type        = string
  description = "Overrides the subject Azure accepts for the recording identity."
  default     = null
}

variable "deploy_identity_name" {
  type        = string
  description = "Display name of the deploy identity's app registration."
  default     = "gh-lab-image-deploy"
}

variable "recording_identity_name" {
  type        = string
  description = "Display name of the recording identity's app registration."
  default     = "gh-library-recording"
}

variable "lab_state" {
  type = object({
    subscription_id      = string
    resource_group_name  = string
    storage_account_name = string
    container_name       = string
    key                  = optional(string, "ai-foundry/workbench-dev.tfstate")
  })
  description = "Where the Lab root keeps its state. Reads the resource group, registry, app and identity names. Any name set below still wins."
  default     = null
}

variable "runner_state" {
  type = object({
    subscription_id      = string
    resource_group_name  = string
    storage_account_name = string
    container_name       = string
    key                  = optional(string, "ai-foundry/runner-dev.tfstate")
  })
  description = "Where the runner root keeps its state. Reads the runner VM and its resource group. Any name set below still wins."
  default     = null
}

variable "platform_state" {
  type = object({
    subscription_id      = string
    resource_group_name  = string
    storage_account_name = string
    container_name       = string
    key                  = optional(string, "ai-foundry/dev.tfstate")
  })
  description = "Where the platform root keeps its state. Reads the Foundry account and project endpoint. Any value set below still wins."
  default     = null
}

variable "resource_group_name" {
  type        = string
  description = "Resource group of the Lab. Null reads it from lab_state."
  default     = null
}

variable "registry_name" {
  type        = string
  description = "Lab container registry. Null reads it from lab_state."
  default     = null
}

variable "container_app_name" {
  type        = string
  description = "Lab Container App. Null reads it from lab_state."
  default     = null
}

variable "managed_identity_name" {
  type        = string
  description = "The Lab's user-assigned identity. Null reads it from lab_state."
  default     = null
}

variable "runner_resource_group_name" {
  type        = string
  description = "Resource group of the CI runner VM. Null reads it from runner_state."
  default     = null
}

variable "runner_vm_name" {
  type        = string
  description = "CI runner VM. Null reads it from runner_state."
  default     = null
}

variable "foundry_resource_group_name" {
  type        = string
  description = "Resource group of the Foundry account. Null reads it from platform_state."
  default     = null
}

variable "foundry_account_name" {
  type        = string
  description = "Foundry account the recording identity may call. Null reads it from platform_state."
  default     = null
}

variable "foundry_project_endpoint" {
  type        = string
  description = "Foundry project URL the recording workflow calls. Null reads it from platform_state."
  default     = null
}

variable "bootstrap_only" {
  type        = bool
  default     = false
  nullable    = false
  description = "Create foundation resources only for the first deployment. Never use against an existing app."
}

variable "image_digest" {
  type        = string
  default     = null
  description = "Immutable image digest. Required for every normal deployment."
  validation {
    condition     = var.bootstrap_only || var.image_digest != null
    error_message = "image_digest is required unless bootstrap_only is explicitly true."
  }
  validation {
    condition     = var.image_digest == null ? true : can(regex("^sha256:[a-f0-9]{64}$", var.image_digest))
    error_message = "Use the immutable SHA-256 digest returned by the registry build."
  }
}
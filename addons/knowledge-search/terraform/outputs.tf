output "role_assignment_scope" {
  description = "The one index the agent can read."
  value       = azurerm_role_assignment.search_index_reader.scope
}

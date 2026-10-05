mock_provider "azurerm" {}

variables {
  search_service_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-example/providers/Microsoft.Search/searchServices/search-example"
  principal_id      = "11111111-1111-1111-1111-111111111111"
}

run "grants_read_on_one_index" {
  command = plan

  assert {
    condition     = azurerm_role_assignment.search_index_reader.scope == "${var.search_service_id}/indexes/lab-sample-policy-guidance"
    error_message = "The grant must be scoped to the index, not the service."
  }
  assert {
    condition     = endswith(azurerm_role_assignment.search_index_reader.role_definition_id, "/roleDefinitions/1407120a-92aa-4202-b7e9-c0e197c71c8f")
    error_message = "The role must be Search Index Data Reader."
  }
  assert {
    condition     = azurerm_role_assignment.search_index_reader.principal_type == "ServicePrincipal" && azurerm_role_assignment.search_index_reader.principal_id == var.principal_id
    error_message = "The grant must go to the agent's managed identity as a service principal."
  }
  assert {
    condition     = startswith(azurerm_role_assignment.search_index_reader.role_definition_id, "/subscriptions/00000000-0000-0000-0000-000000000000/")
    error_message = "The role definition must come from the Search service's subscription."
  }
}

run "scopes_to_the_index_that_was_named" {
  command = plan

  variables {
    index_name = "another-index"
  }

  assert {
    condition     = output.role_assignment_scope == "${var.search_service_id}/indexes/another-index"
    error_message = "The grant must follow the index name, and only that."
  }
}

run "lowercases_the_principal" {
  command = plan

  variables {
    principal_id = "AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA"
  }

  assert {
    condition     = azurerm_role_assignment.search_index_reader.principal_id == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    error_message = "The principal ID must be lowercased so a later plan shows no difference."
  }
}

run "rejects_a_service_id_that_is_already_an_index" {
  command = plan

  variables {
    search_service_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-example/providers/Microsoft.Search/searchServices/search-example/indexes/other"
  }

  expect_failures = [var.search_service_id]
}

run "rejects_a_principal_that_is_not_a_guid" {
  command = plan

  variables {
    principal_id = "agent-identity"
  }

  expect_failures = [var.principal_id]
}

run "rejects_an_index_name_with_a_path" {
  command = plan

  variables {
    index_name = "../other"
  }

  expect_failures = [var.index_name]
}

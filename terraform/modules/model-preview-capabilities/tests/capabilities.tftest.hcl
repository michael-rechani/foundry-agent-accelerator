variables {
  fixed_models = {
    primary = { format = "OpenAI", name = "gpt-4.1", version = "2025-04-14" }
    mini    = { format = "OpenAI", name = "gpt-4.1-mini", version = "2025-04-14" }
    other   = { format = "OpenAI", name = "gpt-5.4", version = "2026-03-05" }
  }
}

run "known_fixed_models_use_deployment_names" {
  command = plan

  assert {
    condition     = jsonencode(output.preview_encrypted_reasoning) == jsonencode({ primary = false, mini = false })
    error_message = "Only known non-reasoning model versions should be identified, using their deployment names."
  }
}

run "known_router_subset" {
  command = plan

  variables {
    router = {
      deployment_name = "custom-router"
      models = [
        { format = "OpenAI", name = "gpt-4.1", version = "2025-04-14" },
        { format = "OpenAI", name = "gpt-4.1-mini", version = "2025-04-14" },
      ]
    }
  }

  assert {
    condition     = output.preview_encrypted_reasoning["custom-router"] == false
    error_message = "A Router restricted to the known non-reasoning subset must omit encrypted reasoning."
  }
}

run "unknown_router_subset_is_not_inferred" {
  command = plan

  variables {
    router = {
      deployment_name = "model-router"
      models = [
        { format = "OpenAI", name = "gpt-4.1", version = "2025-04-14" },
        { format = "OpenAI", name = "gpt-5-mini", version = "2025-08-07" },
      ]
    }
  }

  assert {
    condition     = !contains(keys(output.preview_encrypted_reasoning), "model-router")
    error_message = "A mixed or unknown Router subset must not be assigned a guessed capability."
  }
}

run "unknown_versions_and_formats_are_not_inferred" {
  command = plan

  variables {
    fixed_models = {
      different_version = { format = "OpenAI", name = "gpt-4.1", version = "other" }
      different_format  = { format = "Other", name = "gpt-4.1-mini", version = "2025-04-14" }
    }
    router = {
      deployment_name = "model-router"
      models          = [{ format = "OpenAI", name = "gpt-4.1", version = "other" }]
    }
  }

  assert {
    condition     = length(output.preview_encrypted_reasoning) == 0
    error_message = "A familiar name alone must not determine a deployment's capability."
  }
}

run "empty_router_subset_is_not_inferred" {
  command = plan

  variables {
    fixed_models = {}
    router       = { deployment_name = "model-router", models = [] }
  }

  assert {
    condition     = length(output.preview_encrypted_reasoning) == 0
    error_message = "An empty subset must not imply a non-reasoning Router."
  }
}

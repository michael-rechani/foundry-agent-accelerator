# Environment inputs

Each folder holds the committed, non-secret inputs for one environment. `deploy.ps1`
passes them to Terraform with `-var-file`, then adds an ignored `terraform.tfvars`
overlay for values that belong to you (such as `subscription_id`).

| File | Root | Holds |
|------|------|-------|
| `dev\platform.tfvars` | `terraform` (platform) | Name suffix and environment |
| `dev\lab.tfvars` | `workbench/infra` | `platform_state = {}` plus the Lab's visible agents |

Keep names and flags here only. Never commit subscription or tenant IDs, keys, tokens,
or addresses. Put those in the ignored overlay or pass them as environment variables.
`.gitignore` ignores every other `*.tfvars` file.

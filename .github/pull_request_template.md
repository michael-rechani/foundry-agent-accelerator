## What changed

<!-- A short summary a reviewer can scan. -->

## Why

<!-- The problem, request, or issue this addresses. -->

## How it was checked

- [ ] The **Validate** checks pass.
- [ ] For Docker or Terraform changes: I verified a build or plan against an
      approved test environment. CI doesn't build the image or plan against
      live resources.
- [ ] For UI changes: I refreshed affected screenshots and tours, as described
      in `docs/images/README.md`.

## Safety checklist

- [ ] Uses fictional data only. No customer, personal, or health information.
- [ ] No credentials, Terraform state, saved plans, or tfvars are committed.
- [ ] Template lookups stay simulated and read-only, and nothing implies a
      connection to customer systems.
- [ ] Resource names, catalog IDs, routes, and Terraform state ownership are
      preserved, or the migration is explained below.
- [ ] Any new Azure resources or model calls and their cost impact are noted
      below.
- [ ] Related documentation is updated.

## Notes for reviewers

<!-- Migration steps, cost impact, follow-ups, or anything else to flag. -->

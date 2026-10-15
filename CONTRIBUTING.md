# Contributing

Thanks for your interest in the Foundry Agent Accelerator. It's a sample, so
changes that make it clearer, safer, or easier to deploy are the most useful.

## Before you start

- Open an issue for anything bigger than a typo or small fix, so we can agree on
  the approach first.
- Report security problems privately. See [SECURITY.md](SECURITY.md). Don't open
  an issue or pull request for them.
- Use fictional data only. Don't add customer, personal, or health information,
  credentials, Terraform state, saved plans, or `.tfvars` files.

## Make a change

1. Fork the repository and create a branch from `main`.
2. Keep the change focused. Update the documentation it affects.
3. Open a pull request and fill in the template. The **Validate** workflow runs
   the Python, TypeScript, Terraform, and documentation checks. They use mocked
   service responses and don't create Azure resources, so you don't need an
   Azure subscription to contribute. See
   [Automated checks](README.md#automated-checks).

Workflows from a fork wait for a maintainer to approve them before they run.

## What the maintainers check

- Template lookups stay simulated and read-only.
- Resource names, catalog IDs, routes, and Terraform state ownership don't
  change without a migration note.
- New Azure resources, model calls, and cost impact are called out.
- Nothing is made publicly reachable without explicit approval.

## License

By contributing, you agree that your contribution is licensed under the
[MIT License](LICENSE).

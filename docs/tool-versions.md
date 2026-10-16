# Tool versions and upgrades

[Home](../README.md) / [Docs](README.md) / Tool versions

Check only the tools your task needs. Reading docs, preparing sample inputs,
and running mocked tests need no Azure sign-in or Microsoft Entra setup, and
local tests don't need `azd`.

## Baseline

| Tool | Repository baseline | When you need it |
| --- | --- | --- |
| Terraform | 1.16.4 or a later **1.16 patch**, not 1.17 | Infrastructure and mock-provider tests. Each root's `required_version` enforces `~> 1.16.4`, and CI uses 1.16.4. Keep the committed `.terraform.lock.hcl`. |
| Python | 3.14 | Backend, hosted agents, and offline Python tests. Create a virtual environment with that interpreter, then install the task's `requirements*.txt`. Evaluation dependencies use a separate environment. |
| Node.js | 24. CI and the image build use **24.21.0** | Lab frontend only. Run `npm ci` against [`package-lock.json`](../workbench/frontend/package-lock.json), not an unpinned install. |
| PowerShell | 7 (`pwsh`), no patch pinned | Repository `.ps1` helpers and artwork generation. Windows PowerShell 5.1 isn't the CI shell. |
| Azure CLI | No minimum pinned | Azure sign-in and the documented operator and build helpers. Not needed for offline unit or browser tests. Use an organization-approved current release. |
| Docker | No engine version pinned. Linux `amd64` builds | The local path in [`workbench/build.ps1`](../workbench/build.ps1), not ordinary UI or Python tests. The Dockerfile pins base images by digest. |

## Check your tools

Run `terraform version`, `python --version`, `node --version`,
`$PSVersionTable.PSVersion` and, when you need them, `az version` and
`docker version`. A full executable path avoids a stale Windows PATH or a
different Python. Terraform test helpers accept `-TerraformCommand`.

Don't lower a pin to make an older local tool pass.

## Upgrade

After pulling an update:

1. Recreate or update the affected Python environment.
2. Rerun `npm ci` when the frontend lock changes.
3. Initialize Terraform from the lock. Use `init -upgrade` only for an
   intentional, reviewed provider or module update.
4. Review SDK and API compatibility, lockfile and image-digest changes, and the
   [automated checks](../README.md#automated-checks) together.

A package-mirror 404 or TLS failure is an installation problem, not a reason to
rewrite the lockfile. Use an approved source or exact-pin CI, and disclose any
local version differences.

Passing offline checks isn't a deployment acceptance test. A private rollout or
billable live check still needs separate approval.

For version, import, and dependency-install failures, see the
[troubleshooting index](troubleshooting.md#tools-and-dependencies).

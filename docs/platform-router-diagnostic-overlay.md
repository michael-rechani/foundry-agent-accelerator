# Guarded platform diagnostic provider overlay

This fixes only `check_platform_router_plan.py::write_backend` on reviewed source
`446b078df12c9a08daec7bc5e9f0b5a57d8d7a5d`. It does not enable, dispatch, integrate
or authorize a protected diagnostic, plan or apply. The separate dependency-closure
branch and all prior guarded-rollout work remain preserved.

## Why the old overlay failed

The ordinary generated `runner-diagnostic.tf` declared a second
`terraform.required_providers` block beside `terraform/versions.tf`. Real
Terraform 1.16.4 rejects that duplicate. The former minimal synthetic fixture did
not contain the actual root block and therefore did not reproduce the defect.

The diagnostic now writes **only in disposable staged scratch** a JSON override
named `runner-diagnostic_override.tf.json`. Its complete contents add the existing
Azure backend declaration, require `azure/modtm` with the previous `~> 0.3`
constraint, and set the default `modtm` provider `enabled=false`. It does not modify
normal source files, module inputs or the modules' desired telemetry resources.
The root's AzureRM/AzAPI requirements and Terraform version requirement remain in
`versions.tf`. [Terraform's special override merge rules](https://developer.hashicorp.com/terraform/language/files/override#merging-terraform-blocks)
merge required providers **per provider**, rather than accepting a second ordinary
block. This mechanism is not used as a generic override facility.

## Conservative source and collision guard

The diagnostic accepts only the exact reviewed root `.tf`/`.tf.json` filename set
and SHA256 bytes embedded in `DIAGNOSTIC_ROOT_FILES`. The reviewed root has no
backend declaration, root `modtm` provider/alias, modtm root requirement, or existing
override file. Any added/changed provider, constraint, backend, override or other
root configuration fails before generation. This intentionally rejects harmless
root edits too: **any root change requires separate review and test of the new
snapshot**, not automatic hash regeneration to bypass this guard. The fingerprint
was obtained from GitHub's public contents at the exact reviewed SHA, not from a
local checkout. It binds the reviewed root configuration, not an independently
reviewed provider/module checksum closure or every descendant module.

Reserved-path collisions (including dangling links/directories), redirected or
hard-linked root files, and missing/extra/changed source fail closed. Creation is
exclusive; a concurrently appearing reserved file is not overwritten. After
writing, the helper checks the owned file's device/inode, bytes and link count and
rechecks the root fingerprint excluding only its newly generated overlay. Tested
root changes and same-byte reserved-inode replacement during generation are
rejected. Failed generation does not delete or overwrite an external file; partial
scratch remains owned by the existing diagnostic scratch lifecycle and cannot be
reported as success. None of this creates an immutable execution boundary on a
compromised/shared persistent host; transient races or later writes remain possible.

## Actual offline test scope

The regression suite uses Linux synthetic collision/race fixtures and the complete
public module/provider graph captured from that exact reviewed root through the
preserved closure helper. This is an **untrusted public test observation**, not
approved pins. It needs public downloads during credential-free capture only.
All test Terraform subprocesses receive a narrow environment with no Azure/OIDC
credentials and execute as the hosted user inside a network namespace without
external interfaces. Fixed commands are version inspection, backend-disabled
readonly init with `-get=false`, providers inspection/schema, and validate.
No plan, apply, refresh, import, state operation, protected backend initialization,
Azure access or fictional/real state refresh occurs.

Tests reproduce the old duplicate-block initialization failure, then initialize
and validate the **actual new backend-bearing overlay** with `-backend=false`.
Terraform's `providers` command nevertheless requires backend initialization for
that configuration. Tests deliberately do not satisfy that demand: a separate
scratch-only inspection variant omits **only** the generated backend declaration,
retaining the identical override provider requirements/configuration, and then
runs readonly init, providers/schema inspection and validate. Production generation
never omits or bypasses its backend. This separation is explicit evidence, not a
claim that schema inspection ran with the real Azure backend initialized.

The baseline and override inspection have identical AzureRM/AzAPI source and root
constraints (`hashicorp/azurerm >= 4.81.0, < 5.0.0` and `Azure/azapi ~> 2.12.0`),
identical installed provider selections and lock bytes, unchanged module graph,
unchanged ordinary root-file bytes and no backend state file. Modtm resolves to
`registry.terraform.io/azure/modtm` (not `hashicorp/modtm`) with its added root
constraint. The actual overlay and baseline pass full-root validate.

## Still unresolved

Successful init/validate does not prove provider/runtime provenance, authenticated
principal or OIDC/backend/provider credential isolation, authority of protected
inputs/state, safe private-host scratch, full-plan cleanliness, live Router behavior
or safe recovery. The disabled rollout/apply paths must remain disabled until those
independent technical gates are met. The user has authorized necessary work; these
are not a pending generic approval request.

Default-provider JSON configuration and network-disabled init/schema/validate
prove neither runtime refresh telemetry behavior nor coverage of every child
provider alias. No telemetry resource Read/plan was invoked; the network namespace
prevents outbound telemetry in these test executions, but is not a proof that all
real diagnostic provider instances have telemetry disabled. Existing version-specific
loopback evidence is separate, not extended here. No AVM `enable_telemetry` input
is changed to hide desired resources or drift. The module/provider closure,
alias/runtime behavior and credentialed diagnostic execution need their own review.

Do not enable or dispatch protected diagnostics on the strength of this regression.
Any future protected plan/apply must retain `terraform-state-access` serialization;
external ARM/input/state or independently changing publication/runtime routes still
have non-atomic races. Never hide #485 drift, remove Router while consumers may use
it, perform state surgery, or claim recovery is live-verified. Remaining rollout
work is tracked on #522.

The temporary branch-only hosted replacement of `check-platform-input.yml` is
restored byte-for-byte before handoff, and never dispatched after restoration.
No local project reads/edits/checkouts/execution, Azure/protected-data access,
permissions/environment changes, private workflow dispatch, merge or PR creation
is part of this work.

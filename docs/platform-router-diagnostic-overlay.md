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
Actual-root test Terraform subprocesses receive a narrow environment with no Azure/OIDC
credentials and execute as the hosted user inside a network namespace without
external interfaces. Fixed commands are version inspection, backend-disabled
readonly init with `-get=false`, providers inspection/schema, and validate.
The preserved existing console test also runs solely on synthetic HCL in a
network-disabled namespace, exercising its secret-preflight expression without
a vault or provider. No plan, apply, refresh, import, state operation, protected backend initialization,
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

## AzAPI registration guard follow-up

AzAPI 2.12.0 defaults `skip_provider_registration` to false and configures its ARM
client to perform resource-provider registration unless disabled. The offline
diagnostic overlay now disables that behavior only for the existing default AzAPI
configuration. It does **not** set `ARM_SKIP_PROVIDER_REGISTRATION`; the existing
Terraform subprocess helper removes inherited `ARM_*` variables and then sets only
AzureRM's `ARM_RESOURCE_PROVIDER_REGISTRATIONS=none`, avoiding AzureRM 4.81's
rejection of the conflicting legacy skip variable. No AzureRM setting or shared
Terraform helper is changed.

The reviewed root source has one unaliased `azapi` provider, the local Router
module declares the same provider requirement without a provider block or alias,
and root module calls have no `providers` remapping. The exact-root source digest
continues to reject any root configuration mutation. Descendant scanning rejects
the standalone case-insensitive identifiers `provider`, `providers`, and
`configuration_aliases` anywhere in HCL, including comments and strings. This
allows ordinary `required_providers` declarations while conservatively rejecting
provider configurations, selectors, remappings and aliases. Terraform JSON is
parsed with duplicate-key and malformed-input rejection, then the same identifier
check is applied recursively to every decoded key and string. HCL delimiter,
string and comment structure is checked; unsupported heredocs and incomplete or
mismatched structure fail closed. Traversal uses `os.scandir` and explicitly stats each enumerated entry with
`follow_symlinks=False`. Vanished or uninspectable entries fail the scan; symlinks
and every non-directory, non-regular filesystem entry (including FIFOs, sockets
and devices) are refused rather than silently skipped. Only regular source files
are parsed. Synthetic FIFO and mocked socket/device/stat-error tests cover these
paths, but do not prove the unverified earlier public dependency closure contains
no special entries. This remains a conservative lexical guard, not a full HCL
parser or proof of every future Terraform syntax; no parser dependency is added.

The committed Router `versions.tf` and benign HCL/JSON `required_providers`
declarations are synthetic scanner test data and must pass. Adversarial routing,
malformed/duplicate JSON, ambiguous HCL, and mocked Terraform integration-control
flow have dedicated tests. The real closure integration is explicitly skipped by
ordinary test discovery unless both `PUBLIC_OVERLAY_BUNDLE` and
`OVERLAY_TERRAFORM` are supplied. Therefore ordinary discovery and mocked tests do
not establish compatibility with the earlier captured closure.

The earlier actual-root CI run initialized the exact root with Terraform 1.16.4 and
captured a public module/provider closure, but it used the earlier partial-regex
scanner. That downloaded closure was not retained, so its descendants have not been
re-inspected using this stricter check. The new adversarial tests are synthetic and
do not establish what the earlier observed closure contained. Do not treat closure
coverage as verified until a future authorized credential-free run applies this
scanner to a freshly captured closure. This source check does not contact Azure,
refresh state, produce a plan, or prove the provider's live ARM request behavior.
No protected workflow is enabled or dispatched.
## Still unresolved

Successful init/validate does not prove provider/runtime provenance, authenticated
principal or OIDC/backend/provider credential isolation, authority of protected
inputs/state, safe private-host scratch, full-plan cleanliness, live Router behavior
or safe recovery. The disabled rollout/apply paths must remain disabled until those
independent technical gates are met. The user has authorized necessary work; these
are not a pending generic approval request.

Synthetic tests cover HCL selectors/configurations/remappings/aliases (including
same-line and comment-separated tokens), Terraform JSON provider-routing shapes,
escaped JSON keys, malformed/duplicate JSON, nested source, and benign source with
no provider references. They exercise the conservative scanner only; they are not
evidence about the exact downloaded dependency closure. No telemetry resource
Read/plan was invoked; no AVM `enable_telemetry` input is changed to hide desired
resources or drift. Authenticated diagnostic execution still needs its own review.

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

## Verified hosted evidence and restoration

[Ubuntu run 42410219006](https://github.com/michael-rechani/foundry-agent-accelerator/actions/runs/42410219006)
succeeded at tested implementation head
`7b7f427c40c42d98b28915025771f95c5c718b2d`, on exact reviewed source
`446b078df12c9a08daec7bc5e9f0b5a57d8d7a5d`, Terraform **1.16.4/linux_amd64**.
The 21 existing diagnostic tests passed, including the preserved synthetic console
preflight test. Added overlay tests passed five synthetic tests with one deliberately
unselected integration fixture, then all six tests in public actual-root mode.
The old minimal provider-cache test was replaced, not retained as a skipped proxy
for real-root coverage. Command results:

- `python3 -m unittest discover -s .github/scripts -p test_check_platform_router_plan.py -v`: **passed (21)**, in a network-disabled hosted namespace.
- `python3 -m unittest discover -s .github/scripts -p test_platform_router_overlay.py -v`: **passed (five + one unselected fixture)** in synthetic mode.
- The same overlay test command with `PUBLIC_OVERLAY_BUNDLE` and `OVERLAY_TERRAFORM` in a network-disabled namespace: **passed (six)**, including actual full-root/module init/validate, backend-free requirement/schema inspection, old duplicate-block failure, and generation/collision races.

The public fixture was freshly generated through preserved closure implementation
`0aca16abe9a2527a238b3702fcacefacb627ebf1`, not downloaded as trusted pins or used to
run a credentialed diagnostic. Actual-root tests verified observed modtm 0.4.0,
AzAPI 2.12.0, AzureRM 4.81.0 and identical complete provider selections/lock bytes.
These remain observed test versions only. No protected data or resource refresh was
involved; outbound network was unavailable to fixture Terraform execution.

The branch's `check-platform-input.yml` remains at original blob
`13fea116e0cd70aa8f5d8cabcb9b893743e23c95`. No workflow was dispatched after its
restoration. No PR was opened or merge performed. Root Terraform configuration,
recording workflow, prohibited Lab files, previous closure branch and local work are
unchanged.

## AzAPI guard exact-head follow-up

[Ubuntu run 42414297667](https://github.com/michael-rechani/foundry-agent-accelerator/actions/runs/42414297667)
passed on exact branch head
`656defe3dc99538ef3d0b5e2e1ffc3540355bd51`. It ran seven focused overlay tests in
synthetic mode (the bundle-dependent integration case is skipped there), then two
integration tests against the captured public root and dependency closure. The
integration path used Terraform 1.16.4 `init -backend=false` and `validate`, with
Terraform fixture execution inside a network-disabled container; the temporary
filesystem explicitly permits execution of the downloaded provider binaries.

This confirms configuration merge and validation, not runtime provider registration
behavior. The separate tests reject explicit descendant AzAPI provider blocks,
provider selectors, configuration aliases, and module remappings. A new alias or
provider-routing pattern not covered by the scanner, or a later dependency change,
requires renewed review. No positive-control runtime request test or Azure call was
performed.

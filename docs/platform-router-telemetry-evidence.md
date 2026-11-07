# Offline modtm wiring and projected Linux Read evidence

This is a bounded investigation, **not verification of full-root runtime
telemetry suppression** or permission to run a protected diagnostic. Reviewed
source: `446b078df12c9a08daec7bc5e9f0b5a57d8d7a5d`. The diagnostic script reused
from the tested overlay fix is blob `79a6effc7e7efe7eedc2381ac01935b89dd5d493`;
its generated default provider configuration is exactly `enabled=false` with
`azure/modtm ~>0.3`. No new deployment behavior or permissive guard is introduced.

## Actual source and resolved graph findings

The hosted test freshly captures the complete public root/module graph through
preserved closure implementation `0aca16abe9a2527a238b3702fcacefacb627ebf1`.
The observed provider is real **Azure/modtm 0.4.0 on Linux amd64**, Terraform
**1.16.4**. This fresh capture is unapproved test provenance, not the retained
artifact being authenticated or permanent pins. Prior artifact/signature/consistency
evidence remains separate; `.git` metadata is still unreviewed.

Native HCL and Terraform JSON source inventory of every installed module finds
six `modtm_telemetry.telemetry` resource definitions and six `modtm_module_source`
data-source definitions. Each uses the implicit default provider. There are no
module-local modtm provider blocks, modtm configuration aliases, explicit modtm
resource/data provider references, or explicit modtm module remappings in this
observed graph. Requirements consistently identify `Azure/modtm` (case-normalized).
The resolved graph contains exactly one modtm provider address:
`provider["registry.terraform.io/azure/modtm"]`. All six telemetry resource graph
edges resolve to that root default:

| Module key | Observed registry version |
|---|---|
| `ai_foundry` | 0.11.3 |
| `ai_foundry.avm_utl_regions` | 0.12.0 |
| `ai_foundry.cosmosdb` | 0.10.0 |
| `ai_foundry.key_vault` | 0.10.2 |
| `ai_foundry.storage_account` | 0.6.9 |
| `api_management` | 0.9.0 |

Their telemetry count expressions are `var.enable_telemetry ? 1 : 0`. The root
retains the actual AVM telemetry inputs; they are **not set false** to remove
resources or mask drift. Graph inspection is structural: it does not resolve
protected inputs, which module counts will actually be active, prior-state provider
addresses, or real resource refresh behavior. `terraform graph -type=plan` is not
a `terraform plan` operation and did not refresh resources.

For graph inspection only, a disposable copy uses the tested generated JSON overlay
with **only its Azure backend declaration omitted**. That avoids initializing or
accessing Azure state. The original diagnostic function/backend-bearing overlay
is unchanged; no production backend bypass is implemented.

## Provider source and precise Linux runtime test scope

Read the public [modtm provider configuration](https://raw.githubusercontent.com/Azure/terraform-provider-modtm/1fe2fcd0f69d697b6d3e3530835416ef2c7114e7/internal/provider/provider.go)
and [telemetry resource](https://raw.githubusercontent.com/Azure/terraform-provider-modtm/1fe2fcd0f69d697b6d3e3530835416ef2c7114e7/internal/provider/telemetry_resource.go)
at `1fe2fcd0f69d697b6d3e3530835416ef2c7114e7`. Configure defaults enabled to true;
Resource.Read calls sendTags("read"). sendTags returns immediately when disabled,
before reading tags/resolving its endpoint. Enabled sends the prior-state tags,
adds event=read/resource_id, and resolves the endpoint with a GET before POST.
This source explains the version-specific mechanism; it does not independently
authenticate the observed downloaded executable.

The Linux experiment deliberately projects **only telemetry resources** into local
modules following the discovered module nesting. It omits ALL infrastructure
providers/resources/data sources, uses fictional subscription/tenant/UUID/location
tags, and creates a fictional local state by writing JSON, never by apply/import.
Each telemetry definition is forced to count=1; infrastructure module count/for_each
and real tag/data-source expression evaluation are not reproduced. In particular,
the actual APIM module's optional count and its concrete state index are not claimed
identical, and no real modtm_module_source Read or AVM headers are exercised.
Other infrastructure providers are absent, not mocked in a purported full-root plan.
Modtm itself is **not mocked**.

For disabled cases, provider JSON is extracted from `write_backend` on a copy of
the exact reviewed root and asserted equal to the previously tested default provider
bytes. The experiment never changes module enable_telemetry desired state. The
positive control explicitly enables the provider. An adversarial control leaves the
default disabled but enables `modtm.escape` and explicitly remaps the top-level
projection modules to it, demonstrating the danger of an unchecked alias/remapping.

Every experimental Terraform subprocess receives a narrow environment: no Azure,
GitHub OIDC, account, or shared credentials. The only endpoint is a fictional local
`http://127.0.0.1:<ephemeral-port>/telemetry` through MODTM_ENDPOINT. A fresh network
namespace has **only loopback**, with no external interface/route; the suite asserts
that topology. The listener responds locally and records GETs and fictional POST
bodies. No public ingress/port forwarding is created; no Azure or Microsoft endpoint
is contacted. Root graph inspection also happens in this namespace.

Fixed allowed commands: version inspection; backend-disabled init/mirror-only
installation; graph inspection; and **only for the temporary telemetry projection**
normal full-refresh, local-locked plan plus saved-plan JSON show. No targeting,
refresh suppression, apply, Terraform test/apply, import, state push, protected
backend, or live platform plan is exposed. Local fictional source state bytes are
checked unchanged after each plan. Captured provider output is withheld on failures.

## Actual results and retained evidence

[Hosted Ubuntu run 42411992512](https://github.com/michael-rechani/foundry-agent-accelerator/actions/runs/42411992512)
succeeded at tested head `dea1b87cab6f5bdfaeee4ba74dacfc3ea45295d5`. Four tests passed:
actual native/JSON provider inventory and graph plus projected Read; four adversarial
source modifications rejected before any Terraform process; excluded credentials,
forbidden verbs, simulated nonzero/timeout failures; and actual malformed-config
subprocess rejection with loopback-only topology assertions.

| Projected case | Loopback requests | Resource changes |
|---|---|---|
| Enabled positive control | one GET, six POSTs with event=read and fictional tags | six intentional updates |
| Tested disabled default | zero GET/POST requests | identical complete six-resource changes |
| Disabled default + enabled/remapped alias | one GET, six POSTs with event=read | six intentional updates |

Enabled and disabled **complete `resource_changes` arrays** are compared directly,
not merely counts or an abbreviated summary. Each expected address must remain and
have actions=["update"]. Their normalized JSON SHA256 is
`b224055b04f35eb5d244552697edba62b0293c1e9ad0ecea120f4f99da0a560a`.
The arrays, all fictional listener requests, source inventory and graph digest are
retained in [public projection evidence](https://github.com/michael-rechani/foundry-agent-accelerator/actions/runs/42411992512/artifacts/13589442864)
with three-day retention. Only this non-sensitive JSON is uploaded: no state, plan,
provider cache, raw provider output, protected identifiers or credentials.
CI logs retain unsuccessful attempts as well as successful results; final source
bytes correspond to the successful run. The temporary workflow uses Ubuntu hosted,
contents:read only, no environment/secrets/id-token/self-hosted runner.

## The full-root runtime blocker and smallest next step

[Terraform provider mocking](https://developer.hashicorp.com/terraform/language/tests/mocking)
is available only in Terraform test runs, not as replacement real providers for an
ordinary full-root `terraform plan -state=<fictional-state>`. A test `command=plan`
starting with empty test state does not exercise existing telemetry Resource.Read.
The conventional preceding test apply to populate state is forbidden in this task.
We did not invent a test-state injection capability, run an apply, or use mocks of
modtm as runtime evidence. Ordinary full-root refresh would also invoke Azure-backed
data/resource reads without valid inputs/credentials, so a failing network-blocked
plan would not be representative evidence.

The smallest missing boundary is an independently reviewed, credential-free
**full-root state/refresh harness**: populate realistic fictional complete state,
retain exact source/provider addresses and active module counts, safely substitute
all non-modtm provider I/O while executing real modtm Read, and compare the entire
full-root resource_changes output with a verified local telemetry listener. Its
state injection/mocking semantics and full-root inputs must be demonstrated before
execution; this projection is not that harness. Alternatively a separately
reviewed protected diagnostic could collect real effective configuration evidence
under proven identity/data/egress isolation, but no such execution is authorized or
performed here. Neither alternative may weaken full-refresh/drift guards.

Today's result proves the **observed structural default wiring** and a real Linux
version-specific suppression mechanism on a telemetry-only projection. It does not
prove full-root runtime suppression, every future provider/alias, effective protected
state/input authority, persistent-runner host/credentials/global-config isolation,
complete provenance, safe application/recovery or actual inference. Transitive module
changes can introduce new aliases/local providers despite unchanged direct pins;
the existing root-only overlay fingerprint does not lock descendants. The test
rejects such observed wiring, but is not wired into a credentialed workflow gate.
Keep all guarded rollout/apply paths disabled. User work is authorized; remaining
gates are technical evidence/isolation, not generic pending approval.

Preserve `terraform-state-access` serialization for any future plan/apply; external
ARM/blob/input changes and independent publication/runtime routes remain non-atomic.
Do not hide #485 drift, remove Router while any consumer may use it, perform state
surgery or claim recovery verification. Residual work is recorded on #522.

Before handoff, the temporary `check-platform-input.yml` is restored byte-for-byte
to blob `13fea116e0cd70aa8f5d8cabcb9b893743e23c95`, never dispatched after restoration.
Prior closure/overlay branches and prohibited user files remain unchanged. No local
project filesystem reads/edits/checkouts/execution, Azure/protected data, roles,
settings/environments, private runner dispatch, apply, merge or PR creation occurred.
The hosted-only parser dependency is not installed locally or added to production
requirements; it is itself an observed test dependency, not an authenticated toolchain.

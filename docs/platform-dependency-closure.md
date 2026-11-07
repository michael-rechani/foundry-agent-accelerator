# Public platform dependency-closure building block

This is a credential-free, unintegrated prerequisite, not permission to plan or
apply the Router rollout. The rollout workflow and Python apply entry point on
the separate guarded-rollout branch remain disabled. This branch changes no
Terraform resource configuration, protected inputs, Azure resources, identities,
GitHub environments, or private-runner workflow behavior.

## Scope and provenance

The source is exactly `446b078df12c9a08daec7bc5e9f0b5a57d8d7a5d`, rooted at
`terraform`, using Terraform **1.16.4 / linux_amd64**. Capture checks all source
files and executable modes against that commit's Git blob objects; it rejects
untracked, missing, changed, redirected, or unsupported source entries. Nested
Terraform directories are inventoried but are not separate execution roots.
No telemetry/provider overlay or module input change is made.
The implementation branch preserves its original parent/history; its capture
source is a separate exact checkout of the newer reviewed main after #538.

Terraform's provider lockfile records selected versions and package checksums;
it does **not** lock remote modules. Exact direct registry module versions do not
pin their transitive dependencies or independently authenticate module bytes.
The helper therefore lets credential-free Terraform init resolve the actual
root graph, captures the complete installed module cache and module source/
version/directory graph, and builds a Linux provider archive mirror. It records
all artifact SHA256 hashes, file/directory modes, the provider lockfile and actual
installed provider selections, including transitive dependencies. It does not
assume a previous run's versions are complete.

Provider installation/mirroring uses Terraform's normal registry/checksum
verification; subsequent mirror-only init must satisfy the captured lockfile.
A generated lock, module digest, registry response, or manifest is **observed
provenance**, not an independently reviewed trust anchor. Terraform has no
module equivalent of provider release checksum/signature locking. Module cache
bytes are pinned by this manifest only *after* separate review and retention of
the selected manifest digest. Source URLs/versions are recorded, not represented
as independent proof of upstream archive or Git commit authenticity. No provider
or module pins are added to the infrastructure source or claimed approved.

## Capture and verification contract

`platform_dependency_closure.py capture BUNDLE --source EXACT_CHECKOUT/terraform`
requires a new bundle path and exact Git source objects. It runs only version
inspection, backend-disabled init, and Linux provider mirroring, under a narrowly
constructed credential-free subprocess environment and isolated Terraform CLI
configuration/HOME. It rejects existing installation state/lock in the source.
Public resolution needs network access; no backend is initialized or state read.

`platform_dependency_closure.py verify BUNDLE --manifest-sha256 SELECTED_DIGEST`
first checks the separately supplied 64-hex manifest digest and exact inventory.
It rejects missing, extra (including empty directories), changed, mode-changed,
path-escaping, symlinked, hard-linked and special artifacts; duplicate JSON keys
and ambiguous module graphs also fail. It copies the captured root into disposable
scratch, reinstalls exclusively from its filesystem mirror with
`-backend=false -get=false -lockfile=readonly -input=false`, and loads provider
schemas. Copied scratch inventory, provider selections, lock bytes, module graph and original bundle are
checked afterward. Arbitrary Terraform arguments, plan, apply, refresh, import,
state operations, backend initialization and upgrade are not exposed.

The selected digest must come from independent review, not be recalculated from
an untrusted bundle at a credentialed execution boundary. Hosted tests calculate
it from the generated observation solely to test consistency. JSON/error handling
withholds raw provider output; none of these commands accepts protected state or
inputs. Only public source/packages and synthetic fixtures belong in this path.

The public validation workflow was temporarily replaced on this branch with
Ubuntu-only CI, `contents: read`, no environment, secrets, id-token permission or
self-hosted runner. Its readonly reinstall/schema steps also run as the normal
hosted user in a network namespace with no external interfaces. This supplies
actual network-disabled execution evidence; the Python verifier alone does **not**
enforce a kernel sandbox. Normal init and schema loading are not plan/refresh or
resource management operations, but provider binaries are executable code.

## Tests and transport

Synthetic Linux tests cover inventory, transitive module artifacts, source Git
object/mode binding, selected digest replacement, escaped paths, links, duplicate
keys, missing locks, metadata mismatch, forbidden commands, excluded credentials,
subprocess failure and verification-time mutation. A public integration fixture
selected through `PUBLIC_CLOSURE_TEST_BUNDLE` additionally corrupts/removes captured
provider archives and changes/adds installed module files, requiring rejection
before any Terraform process starts.

The hosted job also packages the observation as tar.gz and verifies a fresh
archive round trip with network disabled. Uploading the raw directory to Actions
artifacts loses file permissions; the archive preserves the checked modes instead.
The public artifact is labeled `generated-public-closure-not-reviewed` and has
three-day retention, not permanent storage or approval. Do not use a generic tar
extractor on attacker-supplied archives: a bounded safe extractor, immutable
storage/handoff and independently reviewed digest must precede any future
credentialed integration. There is no downloader or apply integration here.
The original dispatchable workflow is restored byte-for-byte after validation;
do **not** dispatch its restored private diagnostic for this prototype.

## Remaining rollout gates

A successful test proves that this exact observed root dependency graph can be
reinstalled from captured bytes on Linux without dependency downloads. It does
not prove an approved, permanent dependency closure, the authority of any candidate
inputs, actual private state/drift, the complete proposed diagnostic overlay, an
approved plan, or safe application. Terraform can still evaluate external data
sources and other executable dependencies during a real plan; schema inspection
is not evidence for those side effects.

Before credentialed use, separately review source and provider/module provenance,
retain the selected checksum closure immutably, authenticate the Terraform runtime
and actions/toolchain, review all aliases/telemetry behavior on the actual root,
and implement a non-mutable scratch/verification-to-execution boundary. The helper's
pre/post checks detect tested mutations but do not eliminate transient changes or
TOCTOU on a shared host. It authenticates runtime version/platform metadata, not
the executable's release checksum or a compromised host's claims.

Provider environment filtering and a fresh hosted checkout do not isolate the
persistent private runner's host, global configuration, accessible files or
credentials. Separate authenticated backend/ARM identities require actual issued
OIDC claim and federated-trust evidence; distinct client IDs sharing one subject
are not isolation. Backend access, input/state/live Router snapshot authority,
full-refresh telemetry controls, real-backend locking, exact full-plan guards,
post-apply/readback/no-change verification and safe consumer recovery all remain
unresolved here. A local candidate-state diagnostic cannot authorize apply.

Any eventual plan/apply workflow must retain the `terraform-state-access`
concurrency group to serialize with protected diagnostics. Independently changing
publication/runtime routes and external ARM/blob/input changes remain non-atomic;
that group cannot prevent them. Never remove Router while a consumer may use it,
perform state surgery, hide #485 drift, or enable the disabled paths on the basis
of this public closure observation. The user has authorized necessary work; these
are technical evidence/isolation gates, not a pending generic approval request.

## Actual hosted evidence

[Run 42409161870](https://github.com/michael-rechani/foundry-agent-accelerator/actions/runs/42409161870)
succeeded at implementation commit `dc5bd967324d38d693c049b6e75d8f275fc6b3fb`,
capturing exact reviewed source `446b078df12c9a08daec7bc5e9f0b5a57d8d7a5d`.
Synthetic mode passed nine tests with one intentionally unselected public fixture;
public integration mode passed all ten tests, including four real-package/module
mutation cases. Readonly reinstall/schema loading and tar archive roundtrip both
passed in network-disabled namespaces. The manifest contains 1,337 artifact
records, seven registry module instances plus local child modules, and all five
installed external providers. Versions were resolved by that run, not assumed
from an earlier observation.

Observed registry modules: naming 0.4.4, AI Foundry 0.11.3, APIM 0.9.0, regions
0.12.0, Key Vault 0.10.2, storage 0.6.9, Cosmos DB 0.10.0. Observed provider
selections: AzureRM 4.81.0, AzAPI 2.12.0, modtm 0.4.0, time 0.14.2, random 3.9.1.
These lists are evidence summaries, **not approved pins**; the complete graph,
lockfile, inventory and archives reside in the generated observation.

Generated manifest SHA256:
`f6cee223894fae61d3d9bb2cac17ae86df38c1c6ed72d390dd7498b9a1df70b0`.
Generated tar.gz SHA256:
`7afd7b7630954d34b9a83876369058eec6500cef0ddb4deac8b2d37872fa0e55`.
[Public observation artifact](https://github.com/michael-rechani/foundry-agent-accelerator/actions/runs/42409161870/artifacts/13588508507)
is temporary (three-day retention), not a reviewed or permanent deployment input.

The temporary hosted workflow has been restored to the original source blob
`13fea116e0cd70aa8f5d8cabcb9b893743e23c95`. The restoration commit changes only
workflow restoration and this evidence text; helper/test bytes match the tested
commit. No private diagnostic was dispatched after restoration.

Official Terraform references:
[dependency lockfile limitations](https://developer.hashicorp.com/terraform/language/files/dependency-lock),
[provider mirror](https://developer.hashicorp.com/terraform/cli/commands/providers/mirror),
[filesystem mirror configuration](https://developer.hashicorp.com/terraform/cli/config/config-file#provider-installation),
and [init options](https://developer.hashicorp.com/terraform/cli/commands/init).

A separate [bounded Linux extraction prototype](platform-dependency-extraction.md)
now validates this recorded GNU tar.gz format and its exact selected digest before
extraction; hostile synthetic and actual retained-archive tests passed. It remains
unintegrated and does not establish provenance, trusted same-UID/host isolation or
an immutable credentialed handoff. Its constraints are narrower than generic tar
and it does not make retained `.git` metadata trusted.

A separate [metadata-free derivation prototype](platform-dependency-gitless.md)
now omits only independently inventoried module-cache `.git` directories in a
fresh derived bundle. The exact retained archive passed credential-free Linux
readonly init, full schema/module-graph comparison and validate without those
directories. This is an unapproved observation, not credentialed integration or
proof of immutable handoff, source/provider provenance or shared-host isolation.

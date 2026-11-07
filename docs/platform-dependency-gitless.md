# Observed metadata-free dependency derivation

This Linux-only prototype is a separate, unintegrated prerequisite for #522.
It never modifies its original closure, executes Git, downloads dependencies or
runs Terraform. No protected diagnostic, private runner, plan or apply is enabled.
It requires an independently selected original manifest digest; generating a new
digest does not approve the source, providers, modules or handoff.

## Exact transformation and preconditions

`derive_gitless_dependencies.py` accepts the bounded extractor's existing public
bundle, a separately supplied original manifest SHA256, an explicitly trusted
private parent and one fresh destination name. The source must be an absolute,
canonical, no-link path. The output parent must be UID-owned mode 0700 and outside
the original bundle. These checks do not establish shared-host or same-UID
isolation: the caller must independently establish that no other actor can mutate
source, ancestors, parent or destination throughout derivation and consumption.
If that prerequisite cannot be established, do not use this for credentials.

The selected manifest bytes are read through no-follow descriptors and hashed
before parsing, including duplicate-key rejection. The descriptor inventory must
match every original file and directory's hash/mode exactly. Missing, extra,
changed, hardlinked, symlinked or special entries fail closed. Scans bound total
entries to 20,000, depth to 34, individual files to 150 MB and aggregate reads to
2 GB. Copies reject growth beyond the opened file size and transport limit.

Only a path component exactly `.git` below a recorded installed module directory
under `root/.terraform/modules/` can be omitted. It must be an inventoried
**directory**, not a worktree-pointer file. Unknown metadata outside those caches
and a module resolving inside `.git` fail closed. Metadata is hashed as inert
public bytes solely to check the original inventory, not parsed as Git settings
or used to resolve credentials. No Git command, hook or config is evaluated.
`.github`, `.gitignore`, `.gitmodules`, `.gitkeep`, `.git-backup` and all other
non-metadata files remain unchanged. Nested directory components exactly `.git`
inside an installed module follow the same omission rule; this is not a generic
cleanup tool or a rule for arbitrary source repositories.

Retained files/directories are copied by descriptor-relative no-follow traversal
and exclusive creation into a fresh reserved staging directory; their original
bytes and modes are preserved. The regenerated `bundle/manifest.json` intentionally
has a new exact inventory and mode 0600. It retains the original source SHA,
source-file fingerprints, module graph, provider archives/selections, Terraform
version/platform and `generated-public-resolution-not-reviewed` provenance.
`derivation.json` binds the original and derived manifest digests to the source
SHA and exact omitted inventory. Canonical JSON, with no timestamp or random data,
makes these observations deterministic. The wrapper is mode 0700; the sidecar is
mode 0600. No archive or metadata is retained in a new uploaded artifact.

Original descriptor/path inventories and the complete derived wrapper are rechecked
before no-replace publication. Collisions and filesystem failures prevent a
verified handoff. Cleanup touches only the freshly reserved descriptor tree after
ownership checks; uncertain cleanup reports failure rather than deleting unknown
paths. Tests cover parent/source substitutions, but these checks are not an atomic
snapshot or immunity to transient same-UID races. The reused closure verifier also
has pathname-based reads after descriptor validation. An immutable handoff to a
credentialed process remains separately unresolved.

## Exact public fixture and actual Linux evidence

The archive is the original Actions artifact **13588508507**, with unchanged
expiry **2026-11-10T20:04:05Z**. No upload, copy to longer retention or artifact
publication was performed. Separately selected observed hashes, checked before
processing their corresponding layers:

| Layer | SHA256 |
| --- | --- |
| Actions ZIP | `a6620be72b125b4860cd13c7edb5644bd5e51ba89d65477e23ec533925a46838` |
| GNU tar.gz | `7afd7b7630954d34b9a83876369058eec6500cef0ddb4deac8b2d37872fa0e55` |
| Original manifest | `f6cee223894fae61d3d9bb2cac17ae86df38c1c6ed72d390dd7498b9a1df70b0` |
| Derived manifest, **not approved** | `ce9c07b255baa8e84141f66fcbb0731bc1e3988c0e320d15bdddc843c80c2f9f` |

ZIP inspection was limited to the exact digest-selected single member, bounded
at 200 MB; its tar.gz was verified and processed by the separately tested
[bounded GNU transport extractor](platform-dependency-extraction.md). This is not
a general ZIP extraction facility. The original source is reviewed root
`446b078df12c9a08daec7bc5e9f0b5a57d8d7a5d`, Terraform **1.16.4/linux_amd64**.
Seven module-root `.git` directories, totaling **308 inventory records**, were
omitted: `ai_foundry`, `ai_foundry.avm_utl_regions`, `ai_foundry.cosmosdb`,
`ai_foundry.key_vault`, `ai_foundry.storage_account`, `api_management`, `naming`.
Every non-metadata module byte/mode and provider archive remained exact.

Final hosted Ubuntu run:
[42414617326](https://github.com/michael-rechani/foundry-agent-accelerator/actions/runs/42414617326),
exact tested head `d04bfc3729ab7c71068a80b6fc6e4811f90de54e`, **passed**:

- `python3 -m unittest discover -s .github/scripts -p test_extract_platform_dependencies.py -v`: **11 passed**.
- `python3 -m unittest discover -s .github/scripts -p test_derive_gitless_dependencies.py -v`: **15 passed**.
- Exact retained ZIP/tar/manifest selection and bounded extraction: **passed**.
- Existing closure verification on original and derived bundles: **passed**.
- On disposable copies of both actual roots: `init -backend=false -get=false -lockfile=readonly -input=false -no-color`, `providers schema -json`, `validate -json`: **passed**; complete parsed provider schemas, exact `modules.json` bytes and provider selections **identical**.

The complete normalized schema comparison hash was
`df7610f310fd0161d1cddc07d1cf813db3fc61efdaa6404455fb11676a79a2c7`.
Original inventory remained unchanged; no `.git` remained anywhere in the derived
installed module caches, including after readonly init. Thus `-get=false` did not
require or regenerate Git metadata for this exact observed module graph.

Synthetic cases included inert malicious Git hooks/config, dot-name/nested
omission preservation, unknown pointers/outside-cache metadata, duplicate JSON,
source/output mismatch, mode/link/hardlink rejection, source/parent swaps,
output-link substitution, initial/late collisions, partial writes, cleanup
failures, bounded inventory and simulated endless copy growth. All trees were
disposable hosted temp trees; outside sentinels were preserved.

The semantic step used privileged setup (`sudo unshare --net` followed by
`runuser`); the entire check was **not unprivileged or rootless**. Terraform
then ran as a non-root user in a network namespace checked to have only
loopback and no external routes, with fixed command allowlists, filesystem
provider mirrors, readonly locks, empty temporary HOME and narrowly constructed
environments without Azure/GitHub/OIDC credential values. A PATH Git executable
trap was never invoked. No plan, apply, provider refresh or credentialed backend
operation ran. This is not syscall-level proof that an arbitrary provider cannot
read another host path or attempt a loopback/network operation, nor proof the
host or available identities are isolated. Checkout/bootstrap Git outside the
Terraform experiment is separate from module metadata use.

The hosted runner user can invoke sudo. Therefore this no-external-route namespace
is not an enforceable adversarial sandbox against arbitrary provider code and does
not independently prevent exfiltration. UID dropping and a sanitized child
environment do not prove host/token isolation. The supplied rootless hosted
Ubuntu probe did not establish the required combined namespace; no rootless
sandbox claim is supported. No further privileged hosted or private-runner
execution is authorized by this evidence correction.

## Restoration and remaining gates

The temporary hosted workflow had only `contents:read` and `actions:read` for
public artifact acquisition, Ubuntu hosted, no environment, secrets references,
id-token or private runner, and checkout `persist-credentials:false`.
`.github/workflows/check-platform-input.yml` was restored byte-for-byte to original
blob `13fea116e0cd70aa8f5d8cabcb9b893743e23c95` after final testing; it was not
and must not be dispatched after restoration. Final executable/test/helper
blobs match the successful tested head; only documentation and restoration
follow that head. Prior branches, main, user worktrees and preserved files remain
untouched. No local project execution, Azure/protected data or private-runner
execution occurred.

#522 remains open: independently review source/module/provider provenance and
these generated observations; establish isolated trusted scratch, same-UID/host
and immutable handoff; verify identity/backend/input/state authority and recovery
before any protected plan. This derivation does not authorize source refresh,
module fetching, applying, removing Router or exposing resources. Future graph,
platform or Terraform changes need separate selection and verification.

## Malformed selected-input hardening

The follow-up is limited to the gitless parser boundary and its tests; the shared
closure checker, extractor and public semantic checker remain unchanged.
SHA256 verification still precedes JSON parsing. Invalid UTF-8/JSON, excessive
nesting and JSON integer conversion limits become fixed `DerivationError`s,
without input-bearing exception chains. Duplicate keys remain `ClosureError`s.
The manifest must have exactly the expected fields, string context fields,
mapping inventories/providers and a nonempty module list. `format` must be an
actual integer equal to 1, not JSON `true` or `1.0`.

Each inventory entry must have precisely `sha256` and `mode`, an allowed root or
mirror relative path, a directory marker or lowercase SHA256 string and an actual
integer mode in 0..07777. Boolean and float modes are rejected even if Python
numeric equality would otherwise match a real mode. This occurs before staging,
so malformed modes never reach `fchmod` or require broadened cleanup.

After exact source inventory verification, `modules.json` is read through
no-follow descriptors with a 10 MB bound and its selected inventory digest checked
before parsing. Its object must contain exactly `Modules`, a nonempty list of
records with required `Key`, `Source`, `Dir`, optional `Version` and string values.
The manifest list receives the same shape checks and must match the disk graph.
The existing closure checker still enforces source/runtime, provider selections,
module path semantics and graph equality; its valid errors are not masked.

The latest hosted run above passed all 15 derivation tests plus 11 extractor tests.
New tests exercised 48 SHA-selected malformed fixtures through both the direct
helper and its actual CLI: invalid UTF-8/JSON, deep nesting/huge integers, missing
or wrong object/inventory shapes, duplicate keys, file/directory float modes,
boolean/out-of-range modes, malformed record/hash fields, non-integer format and
manifest/disk module shapes. Every CLI case returned 1 with empty stdout and
exact stderr `Metadata-free derivation stopped; no verified handoff.` followed
by a newline, with no traceback, staging/publication, source mutation or outside
sentinel change. Separate tests verify hash-before-parse and preservation of
shared closure errors. Actual selected public closure comparison also passed
again, yielding the same unapproved derived manifest and complete schema hashes.

This is bounded malformed-input handling, not atomicity against an actor changing
paths after verification. The existing same-UID/host/ancestor, credential isolation,
provenance and immutable handoff caveats remain unchanged. No local dependency
setup, project execution or live actions were performed for this follow-up.

### Qualification also applies to earlier hosted evidence

The coordinator's exact-run log inspection found the same privileged
`sudo unshare --net ... runuser -u ...` setup in closure run **42409161870**,
telemetry run **42411992512**, extractor run **42412707397**, and initial gitless
run **42413688023**. In each, project code ran with the runner UID after privileged
namespace creation; the overall setup was not wholly unprivileged/rootless.
Passwordless sudo means a hostile provider is not constrained by that namespace
merely because the observed UID is non-root. Their synthetic and semantic results
remain observations, not proof of host, token or enforceable network isolation.
Earlier descriptions of those checks as unprivileged must be read with this
correction. Existing records report no protected data or private-runner use.
This factual qualification changes no code, historical test results, prior branch,
retention or rollout gate; no new execution or CI rerun was performed.

## Stacked ownership-ledger integration: synthetic evidence only

The new separate branch `michael-rechani-gitless-ledger-offline` is stacked on
verified extractor-ledger final `ac683285341e2064143cda3d68ddd5fbe2cbac60`, preserving
its documentation-only privilege corrections and anonymous-spool implementation.
Gitless helper/test/source-evidence bytes were taken from independently verified
`56f35e5617563a93615d9fdd8a4608fc13f2d2ff`, which differs from the requested
`2dcb7d930cac8c72d1e3960b781518b288c02828` only by already reviewed evidence
corrections. Both original branches remain unchanged.

This integration passes a mandatory shared `OwnershipLedger` through every
Gitless creation path: wrapper `bundle`, retained copied directories/files,
regenerated `bundle/manifest.json` and `derivation.json`. Each path is pending
before creation and bound to a held descriptor after no-follow identity checks.
The same populated ledger verifies complete staging inventory before publication
and is passed to `cleanup_owned`; there is no unchecked compatibility cleanup or
fallback. Ordinary fully-known failure cleanup remains functional. Unknown,
missing, replaced or linked entries or pending/unbound creations refuse cleanup,
leaving staging for reviewed recovery. Directory/file mode and content copying,
original manifest selection, omission rules, canonical manifests/binding,
source SHA/module/provider graph and all inventory validators remain unchanged.

Exact tested head `908e1b5c326332e30ac120a263722a42452943e6` passed
[hosted run 42418283136](https://github.com/michael-rechani/foundry-agent-accelerator/actions/runs/42418283136):
`env -i PATH="$PATH" LANG=C.UTF-8 PYTHONNOUSERSITE=1 python3 -m unittest discover -s .github/scripts -p 'test_*dependencies.py' -v`
**39 passed: 19 Gitless plus 20 extractor tests**. The complete existing synthetic
Gitless suite still verifies deterministic exact omission, mode/byte preservation,
selected original integrity, strict malformed input and fixed error handling.
New tests force failure after injecting an unknown file, moving in an external
directory, replacing copied file/directory or either JSON output; all unknown,
replaced and displaced data survive, and no cleanup unlink/rmdir occurs. Tests
also exercise unbound `bundle`, copied directory/file and both JSON creations,
confirming retained staging; a fully recorded tree is cleaned through the exact
shared ledger. The copied-file link substitution test now correctly expects
preserved unknown links, rather than the old unsafe empty-tree cleanup assumption.
Initial run `42418245324` failed a fixture assertion that guessed the first copied
`main.tf` location; its actual injected link was preserved. The assertion was
corrected to inspect the exact surviving link and the full suite passed above.

No real public closure, providers, Terraform or Git execution was performed in
this follow-up; historical actual-archive semantic evidence elsewhere in this
document does not verify new ledger capacity on that archive. One held descriptor
per created entry is bounded by the extractor entry limit and OS descriptor
capacity; exhaustion fails closed. Real-closure resource feasibility remains
unverified. Non-root standard-library hosted tests used sanitized environment,
no sudo, Docker, namespace setup, Azure, private runner or protected data. This is
not adversarial host/token isolation evidence merely because UID was non-root.
No local project filesystem read/edit/execution or setup occurred.

Creation-to-binding and check-to-unlink races remain: a ledger is not an atomic
security boundary under hostile same-UID directory mutation, does not authenticate
in-place edits or byte authorship, and cannot make unknown-data protection absolute
after the last check. Directory opening follows mkdir; errors or uncertainty leave
staging rather than guessing. Safe cleanup on a shared mutable host, immutable
handoff and trusted-parent/host/credential isolation still require independent
resolution. No live or credentialed integration, apply or recovery sweep is enabled.

The temporary hosted-only workflow was `workflow_dispatch` with `contents:read`,
pinned checkout `persist-credentials:false`, no secrets/environment/id-token or
private runner. After this final test it was restored byte-for-byte to original
blob `13fea116e0cd70aa8f5d8cabcb9b893743e23c95`, with no later dispatch. Final helper,
test and shared extractor blobs match the tested head. No temporary auto-trigger
or artifact upload/retention extension remains. #522 retains the provenance,
transport/input/state authority, trusted-host/identity, capacity and recovery gates.

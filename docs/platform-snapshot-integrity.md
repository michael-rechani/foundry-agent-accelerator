# Offline endpoint snapshot-integrity prototype

Unintegrated synthetic prerequisite for #522, based on reviewed main
`446b078df12c9a08daec7bc5e9f0b5a57d8d7a5d`. No live diagnostic, Blob transport,
Terraform, protected state/input or identity configuration is changed.

## Observed contract, not transport authority

The committed `check_platform_router_plan.py` snapshot helper retains body, ETag
and user metadata; its remote-backend comparator intentionally ignores state ETag
while operating with its own backend lock. That comparator is not suitable for a
local-backend diagnostic which owns no remote lease. This prototype does not reuse
that exception or change the committed live helper.

Public references inspected without Azure calls:
[Get Blob](https://learn.microsoft.com/en-us/rest/api/storageservices/get-blob),
[Get Blob Properties](https://learn.microsoft.com/en-us/rest/api/storageservices/get-blob-properties),
[versioning overview](https://learn.microsoft.com/en-us/azure/storage/blobs/versioning-overview).
The REST references document ETag, Last-Modified, creation time, content length,
API version, blob type, all user metadata, lease status/state and lease duration
when leased. A lease ID is not a documented GET response property; none is invented.
Last-Modified changes on metadata/property updates. Version IDs identify versions,
but their presence must not be assumed for every blob; versioning may be disabled
or a blob may predate its enablement. No live account field availability was tested.

`snapshot_integrity_guard.py` accepts exactly two fictional response records,
`platform_state` and `input`, at each boundary and independently supplied distinct
HTTPS identities. Each record has exactly `identity`, integer `status=200`, nonempty
immutable `body` bytes (at most 64 MB), and a tuple of raw header pairs (at most 128).
Duplicate case-insensitive headers, ambiguous identities/query/version selectors,
partial responses, unsupported fields and invalid types fail closed. Header names
are normalized; values are retained exactly, bounded to 8192 printable ASCII
characters. This intentionally narrow contract is not a general HTTP parser.

Required headers: quoted strong `etag`, exact `content-length`, RFC1123
`last-modified` and `x-ms-creation-time`, `x-ms-version=2023-11-03`,
`x-ms-blob-type=BlockBlob`, `x-ms-lease-status=unlocked`,
`x-ms-lease-state=available`. Lease duration or Terraform lock metadata is rejected,
as are expired/broken/breaking/leased states rather than assuming they are clean.
All `x-ms-meta-*` entries and supported content/encryption properties are compared
including presence/absence. An optional reported `x-ms-version-id` is compared
exactly and must be nonempty; the current GET/HEAD reference tables inspected did
not establish that it is always returned. No version ID is synthesized. Other
unsupported version/copy/tier/tag/HNS fields reject rather than being dropped;
a future transport/profile needs explicit review before supporting them.

Only observation headers `Date`, `Server`, request/client-request IDs and
`Accept-Ranges` are excluded from equality. Exact body bytes, ETag, metadata,
lease properties and all supported stable fields must match. This validates the
synthetic response schema, not Terraform state or input content schema. Existing
state/input validators and input-authority review remain necessary.

A credible production transport is still **unimplemented/unverified**. It must bind
expected target to authenticated effective response identity, reject redirects,
secondary/stale/version-selected reads, preserve duplicate/raw headers, guarantee
complete non-decoded bytes and bounded reads, and prove its exact field profile.
The old three-item snapshot cannot be passed off as this full contract. Caller-
supplied identity labels are not authentication or evidence of input authority.

## Outcome gating and limits

`compare_snapshots` returns a fixed result only. `guarded_diagnostic` freezes
canonical records immediately after each read, including immutable body bytes and
header tuples, and freezes target identities before diagnostic execution. It
returns fixed `UNVERIFIED` without invoking either callback when the expected
role map or identities are invalid, duplicated or malformed. Raw URL controls,
whitespace, aliases and even empty query/fragment delimiters are rejected, not
normalized into a destination. After that validation succeeds, it attempts both
roles at the pre-boundary and again at the post-boundary, even if one read fails.
Invalid baseline skips the operation but still attempts both post-reads.
All catchable success/error/timeout/cancellation paths recheck before
returning any diagnostic outcome. Missing/invalid/changed post-snapshots take
precedence over diagnostic failures. Callback result and exception details are
never returned; diagnostic failure with equal endpoints is separately fixed.

The generic guard validates returned identities **after** invoking the reader;
it cannot establish where an arbitrary reader will send credentials. For the
offline HTTP prototype, use `SnapshotTransport.guarded_diagnostic(expected,
diagnostic)`, described in [the transport document](platform-snapshot-http-transport.md).
That narrow entry point checks both independently supplied expected identities
against the sealed transport targets before any connection. Calling the generic
guard directly is not that binding. Even the bound entry point does not establish
destination or CA authority, trusted DNS/routing, process/host isolation or
worker supervision.

The synchronous callback must explicitly return the exact singleton object
`DIAGNOSTIC_SUCCESS` to indicate its own completed, successfully interpreted work.
The guard checks object identity, never truthiness or equality. `None`, booleans,
numeric values including 0, 1 and 2, arbitrary objects, subprocess result objects,
exceptions, cancellation and all awaitables result in `FAILED` when endpoints are
stable; invalid or changed snapshots still take precedence as `UNVERIFIED`.
A caller must explicitly and correctly interpret any process result before choosing
the token. In particular Terraform exit code 2 is not interpreted here as success
or failure; it is not an implicit authorization to return the token.

A newly created native coroutine is closed without being awaited to prevent a
late unawaited-coroutine warning; custom awaitables, already-suspended coroutines
and futures are not run, awaited, cancelled or otherwise managed. Rejecting a
returned awaitable does not prevent independent work already scheduled elsewhere;
that remains outside this synchronous helper and needs explicit supervision. The
token likewise cannot prove a callback did not spawn untracked work, so callers
must establish that separately. No production diagnostic integration is implied.

Python stdout/stderr are discarded inside the synchronous single-thread guard.
This is deliberate narrow exception/output redaction, not a subprocess logging
sandbox or generic exception policy. Subprocesses/native writes, concurrent
threads, background work, uncatchable termination and process death are outside
its guarantees. Callbacks must be trusted, bounded, read-only and fully supervised;
the helper does not implement a timeout, stop a still-running process or make a
protected execution safe. Tests simulate timeout exceptions after callback exit,
not a verified live process timeout/termination protocol.

The checks are sequential, not an atomic two-blob snapshot or remote lock. They
cannot detect a lock acquired and released between endpoints, a mutation/restoration
with identical observed fields, or a writer after the last read/between reads.
Tests explicitly show equal restored endpoints can pass. A changed ETag is rejected
even when bytes have been restored. No apply authorization, remote lease ownership,
input authority, full-refresh safety, host/token isolation or prevention of writers
is established. Source/provider/identity/scratch/transport and live integration
remain blocked; this prototype must not be connected to the live diagnostic.

## Actual hosted evidence and restoration

Original prototype branch: `michael-rechani-snapshot-integrity-offline`.
Exact tested head: `38ef667ca4b40d10d70ee0f5123df4175bc37b35`.
[Hosted run 42415398011](https://github.com/michael-rechani/foundry-agent-accelerator/actions/runs/42415398011)
passed `env -i PATH="$PATH" LANG=C.UTF-8 PYTHONNOUSERSITE=1 python3 -m unittest discover -s .github/scripts -p test_snapshot_integrity_guard.py -v`:
**14 tests passed**. Fixtures were wholly fictional in-memory records. Tests cover
independent input/state byte, ETag, metadata, lease/lock and timestamp changes;
missing/extra/duplicate fields; optional version presence/change; source/target
mutation; error/timeout/cancellation/read-failure rechecks and redacted sensitive
exceptions; strict bounds/types and explicit transient/restored endpoint limits.
Tests assert non-root UID and absence of Azure/ARM/GitHub token environment values.

No sudo, namespace setup, provider, Terraform, Azure/protected data, private runner,
package install or local project execution was used. The hosted runner UID may
have potential passwordless sudo; no adversarial host/token isolation or sandbox
claim follows from these ordinary synthetic tests. Checkout used a pinned action,
`persist-credentials:false`; workflow permissions were `contents:read` only, no
secrets, environment, id-token or private runner. No artifacts were uploaded.

After testing, only this evidence doc and exact restoration of
`.github/workflows/check-platform-input.yml` to original blob
`13fea116e0cd70aa8f5d8cabcb9b893743e23c95` were committed. Code/test blobs match
the successful tested head. No CI/dispatch occurred after restoration.
The previously cited `snapshot-pair` branch, commits `3407504...`/`f394919...`
and run `42416266575` were unavailable via GitHub API and are not evidence for
this assignment. There is no claimed completed live/protected diagnostic.

#522 remains open for independently reviewed transport/field authority,
protected execution identity/host trust, state/input semantics and recovery.
This document records a useful tested synthetic boundary, not a production
snapshot-integrity guarantee.

### Outcome-token follow-up evidence

The separate branch `michael-rechani-snapshot-outcome-offline` starts at original
prototype head `25c8885beafd122f63e9a6c30bd9ddef6df0d561`. Exact tested head
`1917d1d6343a9913200eaf7e9438b3689b105d21` passed
[hosted run 42417504710](https://github.com/michael-rechani/foundry-agent-accelerator/actions/runs/42417504710):
`env -i PATH="$PATH" LANG=C.UTF-8 PYTHONNOUSERSITE=1 python3 -m unittest discover -s .github/scripts -p test_snapshot_integrity_guard.py -v`
**19 tests passed**. Synthetic fixtures cover exact explicit success; false/true,
raw integers 0/1/2, arbitrary objects, exception/cancellation and fake subprocess
results; created and suspended coroutines, custom awaitables and unresolved future;
invalid baseline; and error/return precedence over invalid, locked, changed or
unreadable post-snapshots. Both endpoints are rechecked on catchable paths, and
captured Python output remains fixed/redacted. The prior 14-test run above describes
the original prototype only, not this outcome-token change.

The temporary hosted-only test workflow had `contents:read` only, a pinned checkout
with `persist-credentials:false`, no environment, secrets, id-token, self-hosted
runner, sudo, Docker, real Terraform/providers or privileged namespace setup.
Tests asserted non-root UID and no Azure/ARM/GitHub token environment variables.
This does not prove adversarial host or token isolation, and potential hosted sudo
availability remains a caveat. No protected data or private runner was used.
After the successful test, the temporary workflow was restored to original blob
`13fea116e0cd70aa8f5d8cabcb9b893743e23c95`; no dispatch occurred afterward. Code
and test blobs in the final branch match that tested head. Existing transport,
non-atomicity, process supervision, credential and host caveats remain unchanged.

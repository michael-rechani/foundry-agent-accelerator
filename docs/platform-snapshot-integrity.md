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
attempts both roles at the pre-boundary and again at the post-boundary, even if
one read fails. Invalid baseline skips the operation but still attempts both
post-reads. All catchable success/error/timeout/cancellation paths recheck before
returning any diagnostic outcome. Missing/invalid/changed post-snapshots take
precedence over diagnostic failures. Callback result and exception details are
never returned; diagnostic failure with equal endpoints is separately fixed.

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

Actual branch: `michael-rechani-snapshot-integrity-offline`.
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

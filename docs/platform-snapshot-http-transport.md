# Offline snapshot HTTP transport prototype

This is an isolated, unmerged synthetic prerequisite, not a rollout, integration,
permission to plan or apply, or evidence that a real Blob endpoint is compatible.
It does not alter the snapshot comparator or the diagnostic outcome precedence.

The callback is constructed from two independently preselected, distinct role
identities, a bearer token, and an explicit CA bundle. Configuration and token
authority are external, unproven inputs: parsing them does not establish that the
target, CA file, principal, credential or input is authorized. The role callback
does not accept URLs. It issues only a direct HTTPS GET to the frozen host and
path, with no userinfo, query, fragment, proxy or redirect. It sends a bearer
header, `x-ms-date`, `x-ms-version: 2023-11-03` and `Accept-Encoding: identity`;
it never follows a bearer challenge or acquires credentials. The TLS client
context verifies hostnames and certificates against the explicitly supplied
bundle instead of inherited default certificate paths. That bundle itself must
be independently trusted and protected.

The response must be 200 with one valid nonzero Content-Length of at most
64,000,000 bytes, no Content-Range or Transfer-Encoding, and exactly that many
bytes read. It does not decode content encodings. It preserves the parser's raw
header pairs in order and rejects duplicate names, parser defects, malformed
values and ambiguous framing. Unsupported headers are not dropped: the existing guard rejects them.
In particular `x-ms-access-tier` is documented as possible for Blob responses but
is not accepted by the current fictional guard. The actual Azure Blob response
profile has not been observed or approved. HTTP framing bounds the returned body
to Content-Length; trailing bytes outside that framed response are not examined.
HTTP parsing also imposes its own header-line and count limits.

The callback returns exactly the guard's record shape or `None`, which the guard
rejects. It suppresses exception details, does not log tokens or response data,
and discards exceptions from connection cleanup. This is not a security sandbox:
the invoking process, same-UID peers, host administrators, installed runtime,
mocked or instrumented libraries, CA file and environment all require separate
trust. Secret-bearing objects remain in process memory. Network DNS, private
endpoint routing, principal selection, least-privilege Blob read RBAC, token
audience and token/host isolation have not been proven. Public documentation
lists `Microsoft.Storage/storageAccounts/blobServices/containers/blobs/read`
for Get Blob; that does not prove any actual principal is read-only or authorized.

The socket timeout is per blocking network operation, not a total deadline:
DNS resolution, TLS or a slow stream may exceed it, and Python cannot reliably
interrupt all work. A production supervisor must impose and verify an independent
total deadline and terminate/reap any worker before proceeding, without leaking
credentials via arguments, outputs or artifacts. This prototype does not supply
that supervisor. It must not be used by a guarded diagnostic until that boundary,
including post-error rechecks and isolated credential delivery, is independently
designed and verified.

Snapshots of the two targets are sequential, not atomic and not a remote lease.
Endpoint equality cannot exclude intervening changes, transient locks, a
mutation-and-restoration, or writers after the final read. State and input content
authority, valid schema and all existing safety checks remain separate.

The older `check_state_backend.send` accepts methods and data, returns unbounded
reads and uses an opener with ambient proxy behavior; it does not implement this
full record contract. It is not reused or modified. Fictional mock HTTP tests
exercise transport mechanics only; they do not prove a real authenticated Azure
endpoint, network isolation, private DNS or a host sandbox.

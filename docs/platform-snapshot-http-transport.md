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
and converts connection cleanup failure to the same fixed failure, even after a
valid response. Cleanup failure at a post-boundary remains snapshot instability,
which takes precedence over any diagnostic success or failure. A failed close
does not prove that the connection or worker has been terminated. This is not a
security sandbox:
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

## Original mock-only hosted evidence

The tested head was `e6c42c09b88d05ca1839fce5660b29c8383b9076` in the
`michael-rechani-snapshot-http-offline` branch.
[Hosted run 42418203573](https://github.com/michael-rechani/foundry-agent-accelerator/actions/runs/42418203573)
passed the existing 19 guard tests and 11 fictional transport tests on a non-root
GitHub-hosted runner. The temporary branch-only workflow had `contents: read`,
pinned checkout with credentials not persisted, no GitHub environment, id-token,
secrets, private runner, artifacts, Azure calls, Terraform, Docker or sudo.
Tests ran with a cleared environment, except PATH, locale and Python isolation
settings. Tests and their mocked errors, endpoints, headers and bodies were
fictional. A hosted runner may have potential sudo access; this is not evidence
of adversarial host or same-UID isolation.

In that original branch, the temporary workflow was restored to its original base
blob, and transport and test blobs matched the tested head. This earlier evidence
does not include the cleanup correction or the real loopback TLS tests below.

## Offline cleanup and loopback TLS follow-up

The follow-up uses a separate offline branch based on
`cad1ed3cd5aa7e9d6cc3b0df566be128ec6a923a`. Connection closure now runs inside
the exception-redacted boundary: a valid response with a failing close, and a
failed request with a failing close, both produce `None`. Fictional secret
canaries exercise both paths without returning exceptions or printing details.
Additional guard tests preserve post-snapshot-instability precedence over either
diagnostic outcome and skip the diagnostic after an invalid baseline.

`test_snapshot_http_tls.py` generates fresh fictional CA, unrelated CA and server
certificates with local OpenSSL in a temporary directory. The server binds only
IPv4 loopback on an ephemeral unprivileged port. A test-only socket mapping sends
the selected fictional hosts' port-443 connections to that listener while
preserving the original hostname, SNI and Host header. Non-loopback TCP connects,
`connect_ex` and DNS resolution are rejected by the test harness.
The tests use real TLS, not a mocked SSL context: the selected CA and matching
hostname succeed, wrong hostname fails before an HTTP request, and an unrelated
selected CA fails even when the trusted CA is supplied via ambient default-CA
environment variables. Ambient proxy settings do not redirect a successful read.
The loopback worker has bounded socket waits and is joined before fixture exit;
temporary keys and certificates are removed and never committed or uploaded.

These tests exercise actual local certificate verification and the transport's
read-only HTTP mechanics. They still do not establish real Azure authentication,
target or CA authority, least-privilege RBAC, private DNS/endpoint routing, host
or same-UID isolation, non-atomic snapshot safety or production total-deadline
supervision. No production integration, live workflow, PR, merge, rollout, plan
or apply is introduced.

The follow-up's exact tested head is
`9e73d221850fe72a85b9cbcb0ce568bda349697d` on
`michael-rechani-snapshot-http-cleanup-offline`.
[Hosted run 42419021157](https://github.com/michael-rechani/foundry-agent-accelerator/actions/runs/42419021157)
passed **38 focused tests** (19 unchanged guard, 15 transport, 4 real loopback TLS)
on **Python 3.14.10**, plus **Ruff 0.17.3** on the transport and its two test files
using the unchanged root `ruff.toml`. Ruff was missing in the selected runtime,
so only the repository-pinned `ruff==0.17.3` dependency was installed.
The discovery command was `python -m unittest discover -s .github/scripts
-p 'test_snapshot*.py' -v`.

The temporary branch-only hosted workflow pinned checkout and
`actions/setup-python@6d4fd22b20465ccc0f7354476588e8df7c9ca0e0`,
granted only `contents: read`, and did not persist checkout credentials.
Test and lint commands ran with a cleared environment. Tests asserted non-root
execution and absence of credential environment variables. No sudo, Docker,
privileged ports, private runner, GitHub environment, id-token, secrets, artifacts,
Azure requests or real credentials/data were used. Public runtime/dependency
installation is not part of the loopback networking test. Potential hosted sudo
availability remains a host-trust limitation, not a privilege-isolation claim.

In that cleanup branch, after successful verification, the workflow was restored to original blob
`13fea116e0cd70aa8f5d8cabcb9b893743e23c95`; no workflow integration or later
dispatch was added. Its final transport and both test blobs match that tested head.

## Stacked offline destination-binding follow-up

This separate offline follow-up starts at cleanup head
`04f3099be5b67489fd5efa2522ae2fb93388f0a8`. Invalid expected maps now return
fixed `UNVERIFIED` from the generic guard before invoking a reader or diagnostic.
Identity validation rejects raw whitespace/control characters, noncanonical
scheme aliases and even empty query/fragment delimiters instead of normalizing
them into another identity. The shared validator is used by the constructor,
guard and comparator; the strict body/header comparison is unchanged.

For the HTTP prototype, `reader.guarded_diagnostic(independent_expected,
diagnostic)` is the narrowly bound entry point. It requires the exact transport
type, validates both expected role identities and their distinctness, and checks
the complete ordered role-to-target map against the transport's sealed map before
creating any HTTPS connection. Missing/extra roles, swapped roles, duplicated
targets, malformed values, mismatches and changed caller maps submitted after
transport construction yield zero connection attempts, no bearer sends and no
diagnostic. These checks establish consistency only: the expected destinations
and CA/token authority must be independently trusted inputs, not deemed trusted
because this parser accepted them.

After preflight succeeds, a separate frozen expected copy is supplied to the
generic guard. Later mutation of the caller's expected dictionary cannot rebind
the approved destinations. Replacement of the sealed target tuple during a
diagnostic is detected before post-reads and yields snapshot instability without
creating connections to the replacement targets. Both-role boundary attempts,
invalid-baseline skipping, cleanup-failure behavior and instability precedence
remain intact after preflight.

Calling `guarded_diagnostic(expected, reader, diagnostic)` from the generic guard
directly **is not destination binding**: a generic reader may send credentials to
its configured destination before its returned identity is compared. A fictional
test explicitly demonstrates this limitation; production callers must not treat
post-read identity rejection as approval of a credential destination.

This is a synchronous consistency boundary, not an adversarial in-process
sandbox. Trusted destination/CA authority, token selection, DNS/private routing,
same-process/host isolation and independent total-deadline worker supervision
remain external assumptions. Malicious same-UID code, class/library modification,
mutable SSL contexts or concurrent mutation between a check and a network call
are not isolated by Python's sealed tuple or this entry point. No real tokens,
Azure requests, private runner, PR, merge or live integration are introduced.

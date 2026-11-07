# Private scratch-directory prerequisite

`private_scratch.py` provides a Linux-only, descriptor-relative scratch directory
for future diagnostics. It is not currently used by a workflow. It requires an
absolute parent whose path contains no symlink components, whose ancestors are
root/current-user owned and not group/world writable (except a root-owned sticky
shared temporary ancestor), and whose final directory is owned by the current
UID and not group/world writable. It creates a random child with mode `0700`
and files with mode `0600`, uses exclusive creation and `O_NOFOLLOW`, retains
open directory descriptors, and verifies recorded device/inode identities
before cleanup. Cleanup refuses unexpected entries or replaced names and only
removes entries created through the in-memory ownership records. It never uses
a wildcard or follows a symbolic link.

These controls protect against stale-name collisions, symlink traversal,
ancestor path redirection after opening the parent, and accidental cleanup of
unowned entries, assuming the parent and process identity are trusted. They do
**not** defeat an arbitrary concurrent process running as the same UID: Linux
has no unlink-by-inode operation, so a same-UID process can race a name check
against `unlinkat`/`rmdir`. Do not use this helper where untrusted processes
share the UID or can mutate the parent. `chmod`, random names, inode checks, and
retained descriptors are not a same-UID security boundary. An enforceable OS
identity or mount boundary is required for that threat model.

A process or host failure can leave scratch behind. This helper deliberately
has no cross-run recovery or recursive cleanup of unknown contents; an operator
must inspect a residual directory under the trusted parent before removing it.
Do not treat a persistent self-hosted runner as isolated because this helper
exists. The test-only workflow runs exclusively on GitHub-hosted Ubuntu with
`contents: read`; no Azure access, credentials, or protected data are involved.
# Bounded dependency-archive extraction prototype

This Linux-only building block handles the **recorded public closure GNU/USTAR
single-member gzip transport**, not arbitrary tar/ZIP input and not credentialed
Terraform integration. It is deliberately separate from private-runner scratch,
identity, provider/module provenance and apply work. The branch preserves dependency
closure source `0aca16abe9a2527a238b3702fcacefacb627ebf1` unchanged; it adds an extractor,
hostile synthetic tests and this documentation. No workflow is enabled for deployment.

## Caller contract and exact-byte check

`extract_platform_dependencies.py ARCHIVE --archive-sha256 SELECTED_SHA256
--trusted-parent ABSOLUTE_PRIVATE_DIRECTORY --destination NEW_CHILD_NAME`

The caller must obtain the 64-lowercase-hex archive SHA256 from **independent review**,
not compute it from an untrusted archive to establish trust. Tests use externally
selected observation digests to verify consistency, not approval. There is no
manifest-derived trust, network download or credential input in the extractor.
Source is opened as a no-follow, single-linked regular file and copied in bounded
chunks to a private anonymous spool while hashing. Its inode/size/mtime/ctime and
read-byte count are checked for changes. The copied compressed bytes must match the
supplied SHA256 **before any gzip decompression or tar parsing**. Subsequent parsing
uses the captured spool, not an archive path that could be swapped afterward.

The explicit parent is opened component-by-component using directory descriptors
and O_NOFOLLOW. It must be a canonical absolute path, final-directory owner equal
to the current UID and mode exactly 0700. This is a necessary check, **not proof
that the parent/host is trusted**. Caller must establish isolation of ancestors,
same-UID processes, host/filesystem and credentials. The extractor never makes an
existing parent private or cleans an existing destination. Destination is one
bounded ASCII child name, not an arbitrary path.

## Supported transport and resource bounds

A bounded zlib gzip decoder writes at most 1,000,000,000 expanded bytes to another
private spool, using at most 64KiB returned output per call. Compressed input is
at most 200,000,000 bytes. CRC/truncation errors, multiple gzip members and trailing
compressed data fail. Thus compressed headers, output allocation and total decode
are bounded; this is not a general ratio-based CPU/disk quota manager. Temporary
disk can approach the compressed+expanded+extracted limits; callers still need
private filesystem capacity/process/time limits.

The parser does **not** delegate attacker-controlled PAX/long-name/sparse parsing
to tarfile. It reads 512-byte headers, verifies checksums/magic, bounds numeric and
string metadata, validates all members and padding/end markers, and indexes data
offsets before any extracted member is created. Limits are fixed, not caller
configurable:

| Bound | Limit |
|---|---|
| Compressed bytes | 200,000,000 |
| Expanded tar bytes including padding | 1,000,000,000 |
| Sum of regular file bodies | 800,000,000 |
| Single regular file body | 150,000,000 |
| Regular file/directory entries | 20,000 |
| All headers, including GNU long-name records | 40,002 |
| Full canonical path / depth / component | 4,096 bytes / 32 / 255 bytes |
| GNU long-name body | 4,097 bytes including final NUL |

Only regular files and directories below the first `public-closure` directory are
accepted. Parent directories must precede children. Paths are bounded ASCII
components (`A-Z a-z 0-9 _ . @ + , -`), never absolute, repeated/empty, dot/dotdot,
backslash or colon paths. Canonical duplicates and file-as-parent collisions fail.
The root filename and expected format are narrowly fixed to this transport.

USTAR prefixes and bounded GNU `L` long-name records are supported. Long-name
records must be canonical `././@LongLink`, have a single terminating NUL, safe mode
and agree with the following regular header's truncated name. Dangling/nested
extensions fail. **All PAX, global PAX, long-link, sparse (including GNU header
extension fields/base256 numbers), link, device, FIFO, special entry and unknown
formats fail**, rather than partially parsing them or silently discarding metadata.
The actual recorded GNU archive passed these rules; other valid archives may not.

Only directory modes 0700/0755 and file modes 0400/0444/0600/0644/0700/0755 are
permitted. No group/world write, setuid/setgid/sticky bits or other metadata gets
applied. Numeric UID/GID/timestamps and owner/group names are bounded/validated,
then deliberately ignored: no chown, timestamp restoration, xattrs, ACLs or special
attributes. Files belong to the current UID. Safe modes are preserved so the
existing closure mode inventory still matches. That **does not authenticate or
make executable provider/module/.git bytes safe**.

## Staging, publication and failure behavior

A fresh random mode-0700 sibling staging directory is exclusively reserved under
the parent. Collision is an error, never a reason to reuse/clean it. All extraction
uses descriptor-relative directory traversal, O_NOFOLLOW, exclusive file creation
and no imported links. Member file/directory modes are set through open descriptors;
file and directory fsync errors stop before publication. No partial member output
appears beneath the selected final destination before full validation/extraction.

Before writing and publication, the reserved directory's device/inode are compared
with its owned descriptor. Linux renameat2(RENAME_NOREPLACE) publishes only the
complete staging directory; missing syscall/filesystem support or a late final-path
collision fails without overwriting it. This is atomic visibility, **not crash-
durable publication, immutable handoff or same-UID race protection**. There is no
post-rename filesystem operation whose failure is represented as successful
completion. Process termination can leave unpublished owned staging; no automatic
recovery scanner or broad deletion is implemented.

On ordinary filesystem/parser errors, cleanup is restricted to the verified owned
staging descriptor and uses no-follow directory opens and unlink/rmdir relative to
that descriptor. It never follows links outside the tree or touches a colliding
external destination. If ownership or cleanup cannot be verified, it stops with an
explicit cleanup-failure message and leaves the unpublished path for separately
reviewed recovery; it does not guess which external files are safe to delete.
All injected cleanup/substitution fixtures run only beneath disposable hosted test
parents, never real user/runner workspaces.

The descriptor checks narrow ordinary substitution hazards, but a malicious same-
UID process or compromised persistent host can still race directory moves, modify
spool/data/files, impersonate ownership or rewrite successful output. Root can bypass
these checks. Trusted parent and host/identity isolation remain real prerequisites;
this prototype must not be described as solving the independent scratch workstream.

## Actual hosted verification

[Ubuntu run 42412707397](https://github.com/michael-rechani/foundry-agent-accelerator/actions/runs/42412707397)
succeeded at tested head `ddbc14bbb5360dd931edd510a0d6b071606fa46f`.
`python3 -m unittest discover -s .github/scripts -p test_extract_platform_dependencies.py -v`
**passed all 11 tests**, including GNU/USTAR/long names, traversal/links/special entries,
canonical duplicates, PAX/sparse/huge metadata, compressed/expanded/file/total/count/
path limits, malformed checksums/footer/truncated/concatenated gzip, wrong/changed
archive digests, archive and parent substitutions, exclusive stage/final collisions,
partial/zero writes, sync failures, ownership/cleanup failures and a symlink injected
at write time whose external bytes remained untouched. Tests assert no decompression
before digest match and no file creation before complete archive validation.

The same run independently fetched **only** existing public Actions artifact
`13588508507`, checked its exact ZIP bytes before using its known single-member
ZIP shape, then exercised the new extractor on its tar.gz. ZIP handling is a test
acquisition adapter for this already digest-selected observation, not a generic safe
ZIP extractor feature. Its selected digests:

- ZIP: `a6620be72b125b4860cd13c7edb5644bd5e51ba89d65477e23ec533925a46838`.
- GNU tar.gz: `7afd7b7630954d34b9a83876369058eec6500cef0ddb4deac8b2d37872fa0e55`.
- Manifest: `f6cee223894fae61d3d9bb2cac17ae86df38c1c6ed72d390dd7498b9a1df70b0`.

Actual bounded extraction **passed**. Existing `platform_dependency_closure.py
verify` with the separately selected manifest digest **passed**, including exact
file/directory/mode inventory and Terraform1.16.4 Linux readonly mirror-only init/
provider schema execution in a network namespace without external connectivity.
Terraform receives the existing helper's narrow credential-free environment. No
backend, plan, apply, import, refresh or Azure call ran. The archive was not uploaded
or retained longer; its original expiry remains Nov10. Only CI logs are new evidence.

The temporary branch-only workflow requested contents:read and actions:read, hosted
Ubuntu, no environment/secrets/id-token/self-hosted runner, and persist-credentials:false.
The Actions token was scoped only to the artifact download step, never passed to
Terraform. Before handoff it is restored byte-for-byte to original blob
`13fea116e0cd70aa8f5d8cabcb9b893743e23c95`, never dispatched after restoration. Final
extractor/test bytes match the successful tested head. No main/role/environment
changes, public PR or merge occurred; prior branches/user files are preserved.

## Remaining boundaries

Extracted bytes are exactly the digest-selected transport, not approved source,
provider/module/runtime provenance or safe code. `.git` directories/hooks/config
in the retained module caches remain **unreviewed metadata** and must not be
executed/trusted merely because tar extraction is bounded. This tool intentionally
does not filter them out: filtering would change the recorded closure inventory.
The closure verifier does not establish an immutable extraction-to-credentialed-
execution boundary. No generic apply, downloader, recovery, ZIP API or persistent-
runner integration is added.

Independent digest/provenance review, immutable storage, runtime authentication,
trusted-parent/same-UID isolation, post-extraction immutable handoff, real provider/
telemetry aliases, actual protected input/state/plan authority and safe recovery
remain technical gates before any credentialed integration. User work is authorized;
these are evidence/isolation gates, not generic pending approval. Preserve
`terraform-state-access` serialization and independent external/runtime/publication
race limits; do not hide #485 drift or remove Router while consumers may use it.
Residual gates are tracked on #522. All guarded rollout/apply paths stay disabled.

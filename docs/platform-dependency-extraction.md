# Bounded dependency-archive extraction prototype
## Hosted CI privilege and isolation qualification

The cited hosted run 42412707397 used privileged setup:
`sudo unshare --net`, followed by `runuser` to the runner UID for project code.
The complete setup was **not wholly unprivileged or rootless**, even though the
observed project-code UID was non-root. The hosted runner had access to sudo.
Consequently its network namespace and sanitized child environment did not
establish an enforceable adversarial host/network/token sandbox or independently
prevent exfiltration by hostile provider code. Non-root UID and observed lack of
external routes are not proof of those protections.

The synthetic/runtime results below remain scoped observations only. They do not
prove protected-private-runner behavior, host trust, credential/token isolation
or an immutable safe handoff. Existing records report no protected data or
private-runner execution in this hosted experiment. This reporting correction
authorizes no new execution and changes no rollout gate or historical result.


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

The original extractor's recursive `cleanup_owned` sweep was unsafe for unknown
content inserted into an otherwise owned staging tree: root ownership alone did
not prove per-entry ownership. The separate ledger follow-up on this branch
replaces that sweep; historical tests below did not cover this defect.

Each extraction-created file/directory is recorded before creation as pending,
then bound to a held descriptor, device/inode/type and UID after exclusive creation
and no-follow path verification. Regular files must remain single-linked. Held
descriptors prevent inode reuse while the ledger is alive; they do not make
creation-to-binding observations atomic. Directory creation necessarily precedes
opening its descriptor. A failure to bind, a creation collision or any ambiguity
leaves the reservation for reviewed recovery instead of guessing ownership.
The ledger consumes one descriptor per entry plus temporary working descriptors;
OS descriptor exhaustion fails closed, and large real-closure capacity has not
been reverified in this synthetic-only follow-up.

Before any cleanup deletion, the full staging inventory must match the ledger.
Unknown, missing, replaced, linked, special or unverifiable entries cause refusal
without sweeping them. Cleanup enumerates only recorded paths, deepest first,
using held directory descriptors. Immediate entry identity and expected-child
checks precede each unlink/rmdir; a late unexpected child stops further cleanup.
No-ledger callers now receive explicit refusal, not legacy recursive behavior.
No compatibility fallback or live/credentialed integration was added. The separate
Gitless derivation still has its older cleanup API and must not simply be wired to
this changed extractor without its own creation-ledger adaptation and tests.

Spools now require descriptor-relative Linux `O_TMPFILE`, verified regular,
UID-owned and link-count zero. There is no named `TemporaryFile` fallback which
could unlink a substituted name. If anonymous creation is unsupported, extraction
fails rather than attempting that fallback. Anonymous spools disappear on descriptor
close; they never enter the directory ledger or require path deletion.

Uncertain cleanup returns a fixed failure and leaves staging for separate reviewed
recovery. There is no automatic recovery sweep. Tests operate only in disposable
hosted temp trees; unknown/external sentinels are preserved. Remaining known entries
can be partly removed if an error or mutation appears after deletion has begun.
All-or-nothing deletion or crash cleanup is not claimed.

The descriptor checks narrow ordinary substitution hazards, but a malicious same-
UID process or compromised persistent host can still race directory moves, modify
spool/data/files, impersonate ownership or rewrite successful output.
A same-UID actor can substitute an entry after its identity check but before unlink,
or before the first binding observation; held descriptors do not make path deletion
conditional on inode identity. In-place edits to a recorded inode are not new
entries and this identity ledger does not prove authorship of their bytes. Thus
unknown-content preservation is a tested fail-closed boundary at observed checks,
not an atomic security guarantee against concurrent hostile mutation. Root can bypass
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

## Creation-ledger follow-up evidence

New unmerged branch `michael-rechani-extractor-ledger-offline` starts from
`69b4524d63c19edc64a14e4bc317e8ce78c860c2`: this preserves the later documentation-only
privilege corrections while retaining exact extractor code from
`0ea5d605f2fb8fceb3558de4961602b05c8fc35d` (original code blob
`3ecde72e6c8b17c4b2db4e5e388b6df2b54494b6`). Prior branches remain unchanged.

[Hosted synthetic run 42417947534](https://github.com/michael-rechani/foundry-agent-accelerator/actions/runs/42417947534)
passed at exact tested head `fbea0b7ecc18dc9f13f410dd1b5cf03dfe9deb67`:
`env -i PATH="$PATH" LANG=C.UTF-8 PYTHONNOUSERSITE=1 python3 -m unittest discover -s .github/scripts -p test_extract_platform_dependencies.py -v`
**20 tests passed**. Original archive digest/bounds/format/permission/collision
checks remain covered. New cases force failure after inserting an unowned file,
renaming an external directory into staging, replacing a known file/directory,
linking a known file, or removing a recorded entry. Full preflight refuses cleanup
and preserves unknown/replaced/displaced data. Creation/open/binding/descriptor
exhaustion failures, replacement before binding, failed verification and a late
unknown entry after preflight also preserve data at the tested check points.
Without a ledger cleanup refuses; unsupported anonymous spool creation fails
without a named-tempfile fallback.

The initial test run `42417770333` failed, exposing two named tempfile spool unlink
calls and an incorrect test class mock. Anonymous-only spool creation and the test
mock were corrected; run `42417822039` then passed 17 tests, and the final run above
passed all 20. No failure evidence was hidden. This follow-up did not download,
extract or execute the actual public closure, real Terraform/providers or protected
data. Historical actual-artifact evidence above applies only to the old extractor,
not the new ledger/spool behavior or its resource capacity.

Only ordinary non-root hosted Python/std-library synthetic tests ran, with no sudo,
Docker, namespace setup, package installation, Azure, private runner or credentials
in the test environment. Tests explicitly assert non-root UID and absence of
Azure/ARM/GitHub-token environment variables. The hosted runner's potential sudo
access remains a host-isolation caveat; these checks are not an adversarial sandbox.
No local project reads/edits/execution/setup, live diagnostic, PR or merge occurred.

The temporary branch-only workflow was manual `workflow_dispatch`, Ubuntu hosted,
`contents:read` only, pinned checkout `persist-credentials:false`, no environment,
secrets references, id-token or private runner. It was restored byte-for-byte to
original `check-platform-input.yml` blob `13fea116e0cd70aa8f5d8cabcb9b893743e23c95`;
no dispatch followed restoration. Final code/tests match the final successful
tested head. No new automatic workflow remains. Inspected `Validate` and `Scorecard`
push triggers target main (Validate also targets PRs); no PR was opened and all
observed runs on this branch were the explicit synthetic manual test runs.
This is scoped trigger evidence, not a claim that external dispatch is impossible.

#522 retains the independent provenance/runtime, trusted-parent/same-UID/host,
immutable handoff, state/input/identity and recovery gates. Ledger tracking is not
permission for credentialed extraction or a proof safe cleanup can be established
on a shared mutable host.

A separate stacked [Gitless ledger integration](platform-dependency-gitless.md)
now records all wrapper/copy/JSON creation paths and passes the shared ledger to
cleanup on this branch. Its 39 synthetic tests verify the integration without
weakening unknown-entry refusal. The original standalone Gitless branch remains
unchanged and is not retroactively safe. No actual public closure, credentialed
integration or atomic same-UID cleanup guarantee was established by these tests.

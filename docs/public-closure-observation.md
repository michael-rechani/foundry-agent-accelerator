# Public dependency closure observation

This is an observation, not a dependency approval, reviewed pin, private-runner
authorization, or provider-behavior test. The existing conservative scanner
**refused** the captured public descendant sources.

## Exact scope and evidence

The new, unmerged branch
`michael-rechani-public-closure-observation-20261107` starts from
`michael-rechani-azapi-special-entries` at exact head
`b4f292f3e6ff2aca4dc06e4487e0738c1faa0fa2`. Source edits used GitHub APIs;
there was no local repository checkout or execution. No PR, merge, or main change
was made.

- Initial synthetic-only tested head:
  `29e16a96cb11e4d1ef3b7bf9a8e3901ef5058847`,
  [successful run 42420224934](https://github.com/michael-rechani/foundry-agent-accelerator/actions/runs/42420224934).
- Single inspection tested head:
  `77cf6062a6ee35ca42c2928928cdfc1d8f1e2e69`,
  [run 42420295283](https://github.com/michael-rechani/foundry-agent-accelerator/actions/runs/42420295283).
  Synthetic tests and repository Ruff passed before the observation job.
  The observation exited 2 to record scanner refusal, not acceptance.
- Both used Python 3.14 on non-root `ubuntu-24.04` GitHub-hosted runners.
  Checkout was pinned to `3d3c42e5aac5ba805825da76410c181273ba90b1`
  and setup-python to `6d4fd22b20465ccc0f7354476588e8df7c9ca0e0`.
  Checkout selected the triggering immutable SHA and disabled credential persistence.
- Synthetic job permissions: `contents: read`. Observation job maximum:
  `contents: read`, `actions: read`; all other permissions absent.
  No secrets, GitHub Environment, OIDC, protected inputs, or private runner.
  The observation process received only PATH, LANG, and the temporary GitHub
  token, which was removed from its environment and attached only to the
  constant GitHub artifact request. A fresh anonymous request followed the
  strictly validated HTTPS blob redirect; no further redirects, proxy
  environment, or custom TLS trust were accepted.
- The temporary `.github/workflows/public-closure-observation.yml` was removed
  after the single inspection. Existing workflows were not replaced or modified.
  The final removal/documentation commit leaves the tested Python source blobs
  unchanged. Its exact head is recorded in the session handoff.

The only inspected transport was public capture run `42409161870`, artifact
`13588508507`, `generated-public-closure-not-reviewed`. Its observed expiration
was `2026-11-10T20:04:05Z`; nothing retained, republished, or extended it.
The following observed byte identities were verified in sequence, before parsing
each corresponding format. They are **not reviewed or approved pins**:

| Item | Observed SHA-256 |
| --- | --- |
| Outer ZIP | `a6620be72b125b4860cd13c7edb5644bd5e51ba89d65477e23ec533925a46838` |
| Inner tar.gz | `7afd7b7630954d34b9a83876369058eec6500cef0ddb4deac8b2d37872fa0e55` |
| Manifest | `f6cee223894fae61d3d9bb2cac17ae86df38c1c6ed72d390dd7498b9a1df70b0` |

The manifest source SHA matched
`446b078df12c9a08daec7bc5e9f0b5a57d8d7a5d`.
That metadata match does not independently verify source authenticity or
provenance. Earlier capture tests and GitHub metadata are not independent
provenance.

## Bounded result

The fixed-output outcome was
`scanner_provider_routing,scanner_unsupported_hcl`.
The latter means the existing scanner refused unsupported heredoc syntax.
Provider-routing detection intentionally includes mentions in comments and
strings; it does not establish that every refused source implements a bypass.
No scanner rule was broadened to obtain a pass.

| Measure | Count |
| --- | ---: |
| Validated archive entries | 1339 |
| Descendant graph entries | 13 |
| Local descendant entries | 2 |
| Downloaded descendant entries | 11 |
| Unique descendant sources | 243 |
| Recursive source visits before deduplication | 261 |
| HCL sources | 241 |
| Terraform JSON sources | 2 |
| Unique source bytes | 1194603 |
| Unique sources checked | 243 |
| Unique sources refused | 112 |

The gzip and GNU/USTAR validator is an exact non-extracting slice of
`.github/scripts/extract_platform_dependencies.py` from
`a64919a733101d9b50a44293d4c7dfa0c2fde045`,
blob `1df669da151298a8255fbf188e8cc20b2ac379d4`.
Its numeric, path, count, mode, link, special-member, padding, gzip,
and total-size checks were preserved. None of its extraction, filesystem
ownership, cleanup, or execution facilities were included or invoked.

ZIP bytes, compressed tar bytes, and expanded tar bytes remained in bounded
in-memory streams. No member was extracted, imported, executed, or copied into
the repository, an artifact, or a persistent spool. Every manifest inventory
record, content hash, and mode matched the validated tar inventory; the archived
module graph matched the manifest. Every non-root graph directory was checked,
including local and downloaded descendants. Recursive inventories were united,
and the exact scanner parser was applied once to every unique source; repeated
visits to the same bytes have identical parsing results.
Unaccounted downloaded source files or non-source-inventory files were refused.

The byte helper retains the filesystem scanner's exact parsing, error strings,
and UTF-8/universal-newline behavior. Existing filesystem enumeration checks
remain in place. Synthetic tests exercise three integrity mismatches,
unsupported/duplicate/escaping/link archive members, graph/inventory omissions,
provider declarations/selectors/aliases/remappings, malformed JSON/HCL,
compressed/expanded/member/source/count limits, fixed-output redaction, safe
TLS/no-proxy configuration, and credential/redirect/download bounds.

Configured maxima are 200 MB outer ZIP and compressed tar, 1 GB expanded tar,
800 MB total member bodies, 150 MB per tar member, 20000 entries,
8 MB manifest/graph JSON, 2000 module entries, 5000 unique sources, 2 MB per
source, and 40 MB unique source bytes. Downloads have per-request timeouts,
a 180-second bounded-read deadline, and the hosted job has a six-minute timeout.
Output contains only fixed categories and bounded integer counts; archive
contents, member paths, signed URLs, and raw untrusted errors are withheld.

## Limits and preserved boundaries

The hosted runner is not a security sandbox. This observation does not establish
host, same-UID, process, memory, token, filesystem, or network isolation.
Read-only GitHub permissions limit authority; they do not prove token isolation.
No credentialed handoff or extraction safety is established.

No Terraform/provider execution, Azure/Foundry setup, real credentials, private
runner, sudo, Docker, namespaces, protected operation, or protected inputs were
used. No boundary for those operations was changed or approved.
Descendant-source coverage is not proof of mutable runtime root integrity:
the existing `DIAGNOSTIC_ROOT_FILES` boundary is separate and unchanged.
The captured graph/inventory are observations, not an independent resolution
of every module declaration or proof of absence of omitted provenance.
This result cannot authorize private-runner execution, prove provider behavior,
approve a dependency closure, or claim the private Lab router/agents now work.

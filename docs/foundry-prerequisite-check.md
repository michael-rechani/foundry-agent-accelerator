# Protected Foundry prerequisite checks

The original main-branch prerequisite launcher uses process-group signaling
and recursive cleanup and must not be dispatched as-is. On this unmerged
branch, its workflow and launcher fail closed. The separate
`check-foundry-prerequisites-retained.yml` workflow is a proposed replacement,
not evidence that any private check has run. It must not be dispatched until
the change is reviewed, merged, and the existing `terraform-state` reviewer
and protected-main policy are independently confirmed.

The replacement is manual, main-only, and limited to the shared Linux
`lab-runner`. It keeps the existing environment and concurrency group, asks
for `contents: read`, does not request OIDC, and has no checkout or post-action.
Its bootstrap fetches only the two scripts at the exact workflow commit,
verifies their SHA-256 digests, and runs them in an explicitly constructed
environment. It reads the non-secret `user_agent` dispatch input without
printing the event. The expected value must match the pinned skill script's
`AZURE_DEV_USER_AGENT` declaration.

The intended check verifies and runs the public pinned Linux dependency script
(SHA-256 `bb54d233fe8d0164b083a58dec25d1dc3de2c0d7057fc661c866c27b95c935dd`)
and the pinned azd 1.37.3 archive. Both downloads are size-bounded and
hash-verified; the archive parser accepts only the expected regular-file
layout. The skill lists installed extensions, installs `microsoft.foundry` if
absent, and then the launcher checks `azd version`. The extension list checks
an ID, not authenticated extension versions or a complete dependency closure.
Tool installation can use additional disk and network resources beyond the
bounded archive.

## Retained state and process limits

The check reserves `.foundry-prerequisites-<run-id>-<attempt>` in the effective
user's password-database home. The home must be user-owned, non-symlinked and
not group- or world-writable. The unique directory must be owner-only and
outside both the resolved workspace and the runner work directory containing
`RUNNER_TEMP`; unknown layouts, root execution, pre-existing names, and
identity mismatches fail closed. Files are retained on success and failure.
There is no automatic deletion, reuse, or credentialed deployment from this
state. Retained files may consume significant disk and require a separately
reviewed recovery or cleanup process.

The child environment uses fresh `HOME`, XDG, Azure CLI, azd, and temporary
directories within the retained state. It does not forward credentials,
tokens, OIDC request variables, proxies, or inherited shell configuration.
That is not host isolation: both private runner registrations share one
Docker-privileged account, and the process may still be able to reach host
services, including Azure instance metadata.

The launcher requires a well-formed `RUNNER_TRACKING_ID` and passes it to child
processes. If it is absent or invalid, the check stops before reserving state,
downloading, or spawning. A marker alone does not prove that the installed
runner's orphan cleanup is enabled or that all descendants retain it. The
launcher requires Linux procfs, uses bounded output, a deadline, and a Linux pidfd to
observe and reap the direct child, without application-level signals or
recursive cleanup. A successful result is only `ready_retained_state_only`: the pinned synchronous
script and version postcheck completed against that retained state. It does
not prove all descendants exited, extension provenance, persistent tool
availability, or readiness for deployment.

Handled failures report a fixed category and
`owned_process_may_be_running`. Unexpected source verification and loading
failures report `bootstrap`; unclassified launcher failures report
`unexpected_io`. The process flag becomes conservatively true before process
creation is attempted, including when creation is interrupted. A
forced termination can prevent any final log; a missing result is not
readiness. The runner's normal cancellation and tracked-process cleanup remain
trusted for its own job and may signal those processes. The launcher does not
disable or evade that behavior.

Public Actions runner source at
[`5ba50443372004d4d67620909426c5d28a0066af`](https://github.com/actions/runner/tree/5ba50443372004d4d67620909426c5d28a0066af)
shows [orphan tracking cleanup](https://github.com/actions/runner/blob/5ba50443372004d4d67620909426c5d28a0066af/src/Runner.Worker/JobExtension.cs#L891-L930),
[step cancellation](https://github.com/actions/runner/blob/5ba50443372004d4d67620909426c5d28a0066af/src/Runner.Sdk/ProcessInvoker.cs#L443-L465),
and [runner-temp cleanup](https://github.com/actions/runner/blob/5ba50443372004d4d67620909426c5d28a0066af/src/Runner.Worker/TempDirectoryManager.cs#L27-L55).
These are source observations, not proof of the installed private runner's
version or configuration. The user accepted the shared runner boundary, not
authorization to signal unrelated processes or delete unrelated files.

Synthetic hosted tests use fictional downloads and tools; they do not execute
the real skill, azd, Azure, credentials, or the private workflow. Tracked
limitations and prior safety evidence are in
[#522](https://github.com/michael-rechani/foundry-agent-accelerator/issues/522).

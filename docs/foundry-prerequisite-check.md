# Retained-state prerequisite check

This unmerged protected-main manual workflow runs the checksum-pinned dependency
script and its `azd version` postcheck with a run-specific private tool state.
It performs no repository checkout, credentialed Azure call, project-controlled
signal, or recursive deletion. `ready_retained_state_only` means only those
synchronous commands completed for that retained state; it does not establish
persistent dependency availability or prove escaped descendants have exited.

The workflow trusts ordinary Actions tracking and cancellation for its own job;
it does not disable runner cleanup or claim isolation from the other runner on
the shared Docker-privileged VM/account. A fresh single-threaded Python launcher
assumes default SIGCHLD, no competing reapers and a trusted host. Its captured
output has a combined 1 MiB cap. Timeout, interruption, output excess, missing
status and errors do not yield readiness; after any process was started the
fixed output says `owned_process_may_be_running=true`. Framework cancellation
can prevent a final report. No unverified state may be reused by a credentialed
deployment.

Before creating scratch the launcher requires `/var/tmp` itself to be a
root-owned, non-symlink sticky directory with mode 1777, outside resolved
`RUNNER_TEMP` and `GITHUB_WORKSPACE`. If unavailable it reports
`retention_prerequisite`; configure and review an appropriate location before
any future invocation. It exclusively creates a random mode-0700 directory;
neither success nor failure removes it. OS retention policies or runner/host
administration can still remove it; indefinite durability is not claimed.
The pinned dependency script hash is
`bb54d233fe8d0164b083a58dec25d1dc3de2c0d7057fc661c866c27b95c935dd`.

The script treats a `microsoft.foundry` ID match as present; it does not
authenticate component versions, executables or hashes. Microsoft documents
[seven independently versioned core extensions](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/install-cli-foundry-extensions).
No inference about missing components on an actual runner is made.

This is an offline proposal only; it requires review and integration before any
separately approved protected dispatch. No Azure credentials or secrets are
passed. The shared-host, external-service, asynchronous-I/O and path-ownership
limitations remain tracked in [#522](https://github.com/michael-rechani/foundry-agent-accelerator/issues/522).

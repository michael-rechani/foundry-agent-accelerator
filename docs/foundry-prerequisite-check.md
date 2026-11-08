# Protected Foundry prerequisite check: execution blocked

The main-only, manual protected workflow retains the `terraform-state` reviewer
environment, `contents: read`, the shared `lab-runner`, and its concurrency
group. It now emits only a fixed `supervision_unverified` failure: it performs
no checkout, scratch reservation, cleanup, download, or prerequisite launch.
The launcher likewise refuses before setup or process creation. Its `--cleanup`
path refuses rather than trusting old receipts or deleting retained directories.
Do not dispatch it; this unmerged change is not an approved runner operation.

The intended future check must execute the pinned public Linux skill dependency
script (SHA-256 `bb54d233fe8d0164b083a58dec25d1dc3de2c0d7057fc661c866c27b95c935dd`)
with isolated run-specific tool state, no Azure authentication, tokens, or
secrets, and without altering persistent shared-host configuration. It is not
implemented safely yet. The user chose the existing shared private runner;
both runner services share one Docker-privileged VM and account. This is not an
isolation boundary, and no unrelated process or service may be stopped or
signaled.

The previous `communicate()`-then-`killpg` sequence could signal a reused
process group after reaping its leader. Neither pipe EOF, delivery of SIGKILL,
nor leader exit establishes that all descendants are finished or pending writes
have completed. The old recursive source/scratch deletion also could remove
unknown or replaced entries. Those execution and deletion paths have been
removed from the protected workflow and launcher rather than substituted with
an unproven cleanup. Existing receipts and scratch are retained, including
legacy or ambiguous states. Investigate any retained material only under a
separately reviewed ownership-safe process; this change does not authorize
manual deletion.

The user and repository must independently review a future birth-bound
supervisor, trustworthy exit status, descendant/async-I/O guarantees, and
scratch lifecycle before replacing the hard gate. Existing work and open
criteria are tracked in [#522](https://github.com/michael-rechani/foundry-agent-accelerator/issues/522#issuecomment-6714309800).
Host/same-UID trust, escaped descendants, external service delegation, blocked
kernel calls, and path-based cleanup remain unresolved.

The pinned dependency script recognizes the `microsoft.foundry` meta-package
from an ID match in `azd extension list --installed`; it does not authenticate
component versions, executables, or hashes. Microsoft documents
[seven independently versioned core extensions](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/install-cli-foundry-extensions).
Its ready message is not independent authenticated-closure evidence and does
not imply any runner is missing components. A future successful check with
disposable tool state would not establish later persistent tool availability.

Focused hosted tests use fictional inputs and mocks only; they do not execute
the actual skill script, Azure, azd, or the protected workflow. Historical tests
whose expected behavior required execution or automatic deletion are explicitly
skipped until a safe design replaces this gate.

## Natural-exit-only follow-up: runner lifecycle remains a blocker

Keeping every run-owned source and scratch entry for later human review removes
the need to prove that pending kernel writes have completed before deletion.
It does not by itself make the protected check safe to enable. The accepted
shared-account/VM trust assumption is not protection against a hostile host,
same-UID interference, or adversarial process escape. No external process or
service may be signaled, and no run-owned material may be recursively removed.

The public Actions runner source at commit
[`5ba50443372004d4d67620909426c5d28a0066af`](https://github.com/actions/runner/tree/5ba50443372004d4d67620909426c5d28a0066af)
provides concrete reasons that clearing a child environment is insufficient:

- The job's orphan cleanup defaults on and can terminate processes carrying
  `RUNNER_TRACKING_ID` ([job setup](https://github.com/actions/runner/blob/5ba50443372004d4d67620909426c5d28a0066af/src/Runner.Worker/JobExtension.cs#L588-L599),
  [job cleanup](https://github.com/actions/runner/blob/5ba50443372004d4d67620909426c5d28a0066af/src/Runner.Worker/JobExtension.cs#L891-L930),
  [constant](https://github.com/actions/runner/blob/5ba50443372004d4d67620909426c5d28a0066af/src/Runner.Common/Constants.cs)).
  `env -i` can remove this marker from a correctly launched supervisor and its
  descendants, but does not establish how all checkout/action subprocesses or
  every interruption path behave.
- Cancellation independently sends signals to the step process by numeric PID,
  escalating to process termination when it does not exit
  ([cancellation](https://github.com/actions/runner/blob/5ba50443372004d4d67620909426c5d28a0066af/src/Runner.Sdk/ProcessInvoker.cs#L443-L465),
  [Unix signal and termination](https://github.com/actions/runner/blob/5ba50443372004d4d67620909426c5d28a0066af/src/Runner.Sdk/ProcessInvoker.cs#L828-L862)).
  An `exec env -i` supervisor is still the runner's step process. Environment
  scrubbing does not change this cancellation path or guarantee it can emit a
  final result after forced termination.
- Runner initialization and job cleanup delete the contents of runner temp
  ([source](https://github.com/actions/runner/blob/5ba50443372004d4d67620909426c5d28a0066af/src/Runner.Worker/TempDirectoryManager.cs#L27-L55));
  workspace cleanup may also delete directories according to job settings
  ([source](https://github.com/actions/runner/blob/5ba50443372004d4d67620909426c5d28a0066af/src/Runner.Worker/PipelineDirectoryManager.cs#L65-L101)).
  Therefore merely disabling application cleanup or setting checkout
  `clean: false` is not proof that retained source and scratch survive the
  runner lifecycle.

These are observations of public source, not verification of the private
runner's installed version or configuration; no private runner was accessed.
The current workflow never launches the proposed supervisor, so it remains
fail-closed rather than relying on these unverified assumptions. Before enabling
it, a separately reviewed design must demonstrate a run-specific retention
location unaffected by runner cleanup and a runner lifecycle that does not
signal unrelated or escaped owned processes, including cancellation and action
post-steps. It must also account for an abrupt supervisor death: a missing or
ambiguous terminal result must be treated as a fixed failure with
`owned_process_may_be_running=true`, never as readiness, and retained material
must never be reused by a credentialed deployment. A process killed before it
can report cannot itself guarantee the requested final log line; an independent,
non-destructive reporting mechanism would need to be established.

A future supervisor additionally needs a fresh, trusted, single-threaded
subreaper, default waitable SIGCHLD behavior, no competing reapers or ambient
children, birth-bound root status, and explicit reaping of adopted children to
`ECHILD`. Pipe EOF and a root exit alone are not sufficient. Output must be
bounded and failures must never trigger signaling or deletion. Actual execution
of the pinned skill, Azure, azd, credentials, and the protected workflow remains
unapproved; synthetic tests alone cannot establish those runner guarantees.

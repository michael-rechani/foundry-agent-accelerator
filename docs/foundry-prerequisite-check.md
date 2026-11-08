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

Existing work and open criteria are tracked in
[#522](https://github.com/michael-rechani/foundry-agent-accelerator/issues/522#issuecomment-6714309800).
Host/same-UID trust, escaped descendants, external service delegation, blocked
kernel calls, and path-based cleanup remain unresolved. The revised practical
target below does not claim to solve them.

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

## Historical natural-exit-only follow-up

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
The current workflow never launches the proposed supervisor. The earlier
requirement to prove stronger runner and descendant isolation is superseded by
the revised practical target below; these public-source observations remain
relevant to the limits of that target. Missing or ambiguous terminal status must
never become readiness. A forcibly terminated process cannot guarantee a final
log line, and no durable cancellation report is claimed.

The previously proposed subreaper and descendant-teardown proof belonged to a
stronger isolation target. It is not required by the revised practical target
below and must not be presented as a guarantee of it. Actual execution of the
pinned skill, Azure, azd, credentials, and the protected workflow remains
unapproved.

## Revised practical target: not yet implemented

The proposed check trusts the normal Actions runner lifecycle for its own
tracked processes. This is an operational assumption, not isolation from a
hostile host or shared runner account. The application must never signal a
process or process group or recursively delete state. It must leave the
run-specific tool state in place on success and failure. Normal Actions
cancellation and orphan handling may still act on runner-tracked processes;
the check must not disable or evade that framework tracking. An owned process
may survive a timeout, interruption, or other failure, and a forcibly stopped
step cannot guarantee a final report.

The protected workflow must remain main-only, manually triggered, and gated by
its existing environment, with no checkout. Before launch, it must establish a
unique owner-only state location outside both `RUNNER_TEMP` and the workspace,
or fail with an actionable prerequisite. It must not reuse retained state for a
credentialed deployment or modify shared configuration. Its clean environment
must exclude Azure credentials and secrets, and preserve a correctly formatted
`RUNNER_TRACKING_ID` when present. There is no promise that retained files or
tools will remain available indefinitely.

A successful result would attest only to the synchronous pinned skill script
and its postcheck against that retained state. It would not prove escaped
children have exited, authenticate the extension closure, or establish persistent
availability. Timeout, interruption, excessive output, missing or ambiguous
status, or any error must fail closed rather than report readiness. Synthetic
hosted tests must exercise these cases and the exact no-checkout workflow before
the hard gate can be removed. This branch does not implement or verify that
launcher; the protected workflow and launcher still refuse execution.

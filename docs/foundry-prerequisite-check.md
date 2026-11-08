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

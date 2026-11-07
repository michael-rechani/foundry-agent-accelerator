# Reviewed private runner restart (inert proposal)

This is a **code-only, not activated** replacement path for a later, separately
approved start of the same existing private runner VM after idle deallocation.
It does not reuse the exhausted one-shot authorization in
`start-private-runner.yml`. Nothing here authorizes a dispatch, environment
change, Azure write, role grant, deployment, inference call, jumpbox change, or
new public exposure. No existing workflow or Terraform configuration is changed.

## Activation blockers and separately approved setup

The new `private-runner-restart-review` environment does not exist. Before any
use, its creation and configuration need explicit approval, followed by review:

- Exactly one required reviewer: the repository owner `michael-rechani` (a User,
  not a team). Admin bypass must be disabled.
- The complete returned protection-rule shape must contain exactly one
  `required_reviewers` rule and one `branch_policy` rule, with distinct valid
  IDs. Unknown, duplicate or missing rules fail; both rule IDs are bound to
  the preflight configuration snapshot.
- Selected deployment branches/tags: exactly the **branch** `main`, with no
  wildcard or tag rule. The helper also requires `main` to remain protected.
- No environment secrets. This gate has no OIDC permission, checkout, Azure
  operation, or secret reference. The existing `lab-deploy` environment and
  federated subject are preserved without any identity or permission changes.
- Explicitly decide the self-review setting. Both boolean settings are checked
  and bound to the preflight snapshot. If self-review is prevented, a different
  authorized person must dispatch and the owner must review. Allowing owner
  self-review still requires a separate, explicit approval for every new run.

**Configuration alone is not sufficient to activate this proposal.** GitHub's
documented [Get an environment response][environment-api] does not promise a
`can_admins_bypass` field. The helper requires that exact field to be the JSON
boolean `false`, never a missing-field default or a repository variable claiming
it is disabled. If the existing `GITHUB_TOKEN` cannot read this evidence, the
environment's zero-secret metadata, branch policy, or the complete review
history, preflight/start fails closed. No extra privileged token is requested.
The documented schema's absence of bypass evidence is an unresolved blocker:
**this path must remain inert unless a separately reviewed, supported read-only
way to establish that guarantee is available.** Do not insert a fake field,
relax a check, add a PAT, or treat a UI screenshot as live API evidence.

The workflow does not configure the environment or dispatch itself. Preflight
runs without any environment reference and must pass before the review job is
eligible. This avoids GitHub automatically creating an unprotected missing
environment in the normal dependency sequence. Deletion or policy changes
between jobs invalidate the credential-time recheck; concurrent administrator
changes are not a supported operating mode.

## Authorization and execution

`reviewed-private-runner-restart.yml` accepts only two public dispatch inputs:
the exact reviewed 40-character lowercase protected-main commit and the
64-character lowercase SHA-256 fingerprint of the existing VM's normalized ARM
ID. Privately validate the subscription, resource group and VM against the
existing configuration. Hash the entire ARM ID after lowercasing it, using UTF-8
with **no newline**. Do not submit the ARM ID or Azure identifiers as inputs:
this repository's workflow inputs and approval comments are public.

The dispatch must resolve to that exact commit on `main`. Before checking out
anything, the workflow compares the reviewed commit with `github.sha` and the
live protected `main` branch. Checkout uses the immutable SHA and pinned existing
checkout action, with persisted credentials disabled. Preflight additionally
checks the live run's repository, workflow path, event, branch, commit and attempt.
All input expressions are passed through environment variables, never inserted
into shell or Python source.

After all read-only checks pass, preflight displays an exact approval comment:

```text
START runner run=<run-id> sha=<reviewed-main-sha> vm-sha256=<reviewed-vm-fingerprint>
```

The owner must privately check the actual target and reviewed code, then approve
**only** `private-runner-restart-review` with that exact comment. A successful
gate job or a queued job is not approval evidence. Immediately before requesting
OIDC, the start helper requires exactly one actual approved review in this run's
[review history][review-api], the exact environment ID/name, the owner's numeric
ID/login/User type, and the exact run/commit/fingerprint comment. Missing,
duplicate, rejected, wrong-scope or malformed reviews fail. Gate recreation or
changes to the checked configuration fail. If `main` moves while waiting, cancel
and obtain a new reviewed dispatch; do not reuse the old approval.

Every job and the helper reject rerun attempts. GitHub review history is not
attempt-scoped: a failed or cancelled run requires a **new dispatch and review**,
not "Re-run jobs." Different newly reviewed runs can repeat the operation; there
is no run-number-one allowance.

Only the GitHub-hosted start job references `lab-deploy`, retaining its existing
OIDC subject. **That principal is not VM-start-only:** it also has Lab app-write
and registry-push rights. Approval explicitly accepts this existing broader
identity risk; this code does not exercise those other rights or grant any new
ones. The sole Azure command set is login, account selection, VM identity read,
instance-view read and start. The configured ID is precisely validated, normalized,
hashed, masked, and checked against Azure's returned ID. Token/CLI bodies and
private identifiers are not printed as errors or summaries.

Stopped/deallocated VMs receive one `az vm start --no-wait`. Running VMs are not
started; starting VMs are only polled. Missing, multiple or unexpected power
states fail. Polling has a five-minute budget with individual CLI calls limited
to 45 seconds; an in-flight final read may add up to 45 seconds before failure,
but a confirmation after the polling deadline is not accepted as success.
The executing job also has a ten-minute timeout. There is no stop, restart,
run-command, deploy, Terraform, registry push, RBAC change or network change.
Starting incurs compute cost until the existing idle shutdown deallocates the VM.

## Queue monitoring and cancellation

There is deliberately **no self-hosted smoke job**. A running VM is not proof
that either registration is online or that both executed a job. Shared runner
labels cannot establish both registrations from one execution.

GitHub job timeouts bound executing jobs, **not queue or approval wait time**.
For a later approved dispatch, an authorized operator must set a ten-minute
wall-clock monitoring deadline for each queued execution stage, inspect that
specific run in the Actions UI (or use an already-authorized read-only
`gh run view <run-id> --repo michael-rechani/foundry-agent-accelerator`), and cancel
that run through the UI if it remains queued at the deadline. Do not approve
without an available monitor. The workflow has no `actions: write`, cancellation
token, automatic cancellation promise, or extra privileged credential. Its
concurrency group serializes these restarts and does not cancel an in-flight
start. Cancellation does **not** undo a VM start that Azure has already accepted;
do not stop the VM as an unapproved cleanup.

Any later credential-free smoke should be separately reviewed with the same
operator queue deadline. It may report only the registration that actually
executes it, not both. Private-runner rollout/deployment continues through its
existing protected private-runner workflows, not this hosted bootstrap.

## Offline checks

Run from the repository root, with no GitHub or Azure credentials needed:

```powershell
python -m unittest discover -s .github\scripts -p test_reviewed_private_runner_restart.py -v
python -m ruff check .github\scripts\reviewed_private_runner_restart.py .github\scripts\test_reviewed_private_runner_restart.py
```

Tests use synthetic GitHub responses and stub every CLI and OIDC call. They
exercise the missing-bypass-evidence blocker, missing gate, reviewer and branch
restrictions, secrets metadata, exact approval binding, rerun rejection, input
injection, target normalization, API/CLI failures, only permitted Azure commands,
one start, no redundant start, wrong identity, ambiguous power state and polling
deadline. They do not establish real environment protections, live API
availability, online registration status or a deployed Lab.

[environment-api]: https://docs.github.com/en/rest/deployments/environments#get-an-environment
[review-api]: https://docs.github.com/en/rest/actions/workflow-runs#get-the-review-history-for-a-workflow-run

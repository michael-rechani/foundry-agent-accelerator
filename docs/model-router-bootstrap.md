# Model Router bootstrap proposal (inactive)

This is a review proposal only. The
[`model-router-bootstrap.yml`](../.github/workflows/model-router-bootstrap.yml)
job is unconditionally disabled with `if: ${{ false }}`. It cannot run, write a
commit, or change PR #523. Do not remove that condition or dispatch it expecting
work. Activation needs a separate explicit decision and review of the
repository's current runner, Actions, and branch-protection controls.

## Proposed fixed edit

The helper is intentionally data-only and accepts no file paths, refs, commands,
PR numbers, or patch content as input. If separately activated from reviewed
protected `main`, it checks the first run and owner actor ID, confirms that
protected `main` is still the exact workflow source commit, confirms PR #523 is
open at the exact reviewed head
`52fab5e08fb498720efcd53f0f389f424d671a46`, and verifies the exact source blob
IDs for three hard-coded files. It removes the unsupported `2025-12-01` routing
PATCH, adjusts only assertions that depended on that PATCH, and updates the
related documentation. It preserves the `2025-10-01-preview` deployment PUT,
the fresh `2025-12-01` management-plane GET, strict routing postconditions, and
warnings about a potentially partial or unrestricted deployment. It commits
with GraphQL `createCommitOnBranch` and `expectedHeadOid`, so a branch movement
between read and write fails rather than overwriting newer work.

Microsoft's current TypeSpec models the `2025-12-01` PATCH as tags/SKU only;
Microsoft's Model Router REST guidance and sample configure routing in a PUT.
An external AzAPI issue reports routing silently ignored on PUT, but it is
self-closed, undiagnosed, and not reproduced here. Removing the unsupported
PATCH is a defensible API-contract correction, **not a verified live-service
fix**. The preserved readback must fail closed if Azure returns the wrong
configuration; no inference behavior is verified.

## Security and activation limits

- Reviewing or merging this proposal leaves the job disabled. Before any
  activation, first verify the live runner-group and workflow-trigger policy,
  the repository's Actions execution settings and exemptions, main branch
  protections and bypasses, and the expected-head write behavior. Then review a
  separate change that enables the job and revalidates the target PR head and
  source blob IDs. Do not treat this proposal or the earlier bootstrap approval
  as authorization to activate or dispatch it.
- The workflow is dispatch-only, restricted in code to the exact repository,
  owner actor ID, first run/attempt, protected `main`, fixed PR branch, exact
  SHA, exact three source blobs, and one fixed transformation. There are no
  user inputs, PR/fork triggers, Azure calls, OIDC permissions, environment
  secrets, or commands sourced from PR #523.
- The proposed write permission is a repository-scoped `contents: write`
  `GITHUB_TOKEN`, **not** a branch-scoped credential. The expected-head
  compare-and-swap prevents lost updates; GitHub's actual branch protection
  still governs whether that write can succeed. No protection bypass is
  requested or assumed. Checkout also uses the ephemeral job token to fetch the
  trusted workflow source; `persist-credentials: false` prevents saving it in
  the repository's Git configuration. The helper receives the token through
  its environment for the fixed GitHub API calls.
- The repository is public and uses a persistent self-hosted runner with private
  network access. The workflow's own `main` guard does not platform-enforce
  runner access restrictions for other workflows. The available API inspection
  could verify that `main` is protected, but Actions permissions and runner
  access settings returned HTTP 403. Therefore runner-group scope, workflow
  approval policy, and bypass behavior remain unverified; this proposal does
  not claim PR/fork isolation for the repository runner. A future activation
  review must establish the actual platform policy and decide whether it
  sufficiently prevents untrusted PR workflows from targeting the runner.
  Repository-level Actions execution policies may be worth evaluating, but
  their current state, coverage, exceptions, and impact on contributor CI are
  unknown; no setting is changed here.
- `GITHUB_TOKEN`-created commits may not start ordinary PR synchronization
  checks automatically. The owner may need to approve the generated PR checks,
  then verify the exact resulting commit and required CI status before any
  further action. This workflow does not promise green CI.
- The proposed workflow is one-shot. Failed/cancelled first runs consume its
  run-number authorization; it has no retry path. Any changed target SHA,
  changed source blob, changed workflow source on `main`, or changed PR state
  fails closed and requires a newly reviewed proposal.

No runner start, dispatch, Azure/state access, workflow activation, PR #523
write, merge, or security-setting change is authorized by this proposal.

## Offline check

Run the fixed transformation tests without network access or executing PR
scripts:

```sh
python3 .github/scripts/test_model_router_bootstrap.py
```

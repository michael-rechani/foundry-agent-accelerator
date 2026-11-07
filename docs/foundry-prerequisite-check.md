# Isolated Foundry prerequisite check

`Check isolated private Foundry prerequisites` is a manually dispatched,
protected-main-only setup check on the existing Linux x86_64 `lab-runner`.
It uses the existing `terraform-state` environment approval gate and
`contents: read`; it requests no OIDC permission and references no protected
inputs, variables, or secrets. The environment must retain its required-reviewer
protection. This change does not create or change that protection.

The workflow must be integrated into main before an approved dispatch. Preparing
it does not authorize dispatch, VM startup, Azure access, deployment, or merging.
It does not replace the Model Router rollout checks.

The source checkout is exclusive to this run, does not persist credentials, and
does not clean an existing checkout. Every shell step validates positive numeric
run and attempt identifiers before constructing a run-owned path.
Job-level PATH is fixed to `/usr/local/bin:/usr/bin:/bin`, and `BASH_ENV` and
`ENV` point to `/dev/null` before Bash starts. Both Python launches use
`/usr/bin/env -i` and `python3 -I`. Their complete environment allowlist is
PATH, `GITHUB_REF`, `GITHUB_REF_PROTECTED`, `GITHUB_EVENT_NAME`,
`GITHUB_RUN_ID`, `GITHUB_RUN_ATTEMPT`, `RUNNER_TEMP`, and `GITHUB_EVENT_PATH`.
The helper reads only the required, non-secret `user_agent` dispatch field
from the run event file (limited to 1 MiB). The raw input is not placed in
job or step environment mappings or interpolated into shell source.
There is no committed
default. Supply the invocation-only value specified by the Foundry azd guidance;
do not use repository/environment variables, secrets, or azd project config to
persist it. Input is accepted only as a 1-64 character ASCII token starting
with an alphanumeric character and containing alphanumerics, underscores,
periods, or hyphens. Invalid or absent values fail with the fixed `context`
category before scratch creation, downloads, or commands. After downloading and
hash-verifying the official script, the helper requires exactly one strict
user-agent export declaration and an exact input match before any command or
azd invocation, including the final direct version command. A safe but wrong
token fails with `context` and cleanup. No other event fields enter subprocesses.
The helper does not print the input, and no raw evaluated job environment
exposes it in step headers. It remains non-secret dispatch metadata visible
to people with access to the workflow event; this is not a secrecy guarantee.
Python startup cannot inherit PYTHONPATH, user site packages, credentials,
loader settings, or shell hooks. Launcher errors are suppressed and replaced
with fixed nonsecret diagnostics. No other runtime variables are passed;
real-run compatibility has not yet been verified.
The prerequisite helper creates a unique
private temporary directory, with a separate HOME, every XDG directory,
`AZD_CONFIG_DIR`, `AZURE_CONFIG_DIR`, and temporary-file directory. Subprocesses
receive an explicit environment allowlist, not runner credentials, cloud
configuration, shell startup hooks, or proxy settings. Telemetry is disabled.
No shared home, service, or global installation is changed.

The helper downloads and verifies the actual official dependency script from
`microsoft/azure-skills` commit
`299b16bf063bdf37c783e08bcae27ca57fface38` before invoking it from the isolated
skill root. Its SHA-256 is
`bb54d233fe8d0164b083a58dec25d1dc3de2c0d7057fc661c866c27b95c935dd`.
Only the script's exact missing-azd failure permits the fallback download of
`Azure/azure-dev` release `azure-dev-cli_1.37.3`, asset
`azd-linux-amd64.tar.gz`, SHA-256
`8bf3e7e86f1d5a9bc1ae6f014c792697660cce04f6333a8091c6e08b7f8c7786`.
Metadata-only inspection of that hash-verified official release found exactly
two regular members: `azd-linux-amd64` (mode 0775, 68,378,926 bytes) and
`NOTICE.txt` (mode 0775, 2,867,806 bytes). The extractor requires that exact
flat member-name set with no duplicates, links, sparse files, special permission
bits, or unsafe alternatives. It copies only the regular, owner-executable
`azd-linux-amd64` into the run-owned `bin/azd` with mode 0700; the notice is
not extracted. No archive-provided paths are used as extraction destinations.
This corrects the `archive` failure observed in run 42392877753, attempt 1;
that run's cleanup succeeded. The archive correction subsequently succeeded
in run 42393796257 with azd 1.37.3 and cleanup.
An existing azd
executable is reused, with extension state still isolated. The official script
is rerun after the fallback; it installs `microsoft.foundry` when absent.
Existing azd selection searches only `/usr/local/bin:/usr/bin:/bin`, never the
runner's inherited PATH.

Public downloads use HTTPS without authentication or inherited proxies.
The official extension installer also requires outbound access to its official
registry and release assets. This is not an offline runtime check and does not
create publicly reachable resources. The extension release is selected by the
official script, not separately pinned by this helper.

The official pinned dependency script itself sets its prescribed user agent
before its extension commands. Its unchanged, hash-verified source (also used
as an offline test fixture) is upstream behavior, not project configuration.
The helper's other azd invocation receives the caller-supplied token only after
exact comparison with that declaration. The upstream script sets the same
validated value; the product does not embed a default or expected literal.
Removing that
upstream assignment would invalidate the requirement to execute the exact
official script. This invocation-input follow-up has not run on the private runner.

Only a sanitized azd version and readiness are printed on success. Failures
print the fixed `foundry_prerequisites_check_failed` marker and an allowlisted
`failure_stage`: `context`, `download`, `checksum`, `archive`, `missing_bash`,
`skill_execution`, `version`, `cleanup`, `timeout`, `interruption`, or
`unexpected_io`. Unrecognized exceptions map to `unexpected_io`, without
exception text. The launcher accepts only these exact categories or exact
success output; empty, malformed, or unrecognized launcher output maps to
`launcher`. Source reservation and path validation use fixed failure markers;
source ownership failures report `cleanup`. Cleanup's outer failure marker
is `prerequisite_cleanup_failed`.
Child output, exceptions, URLs, paths, commits, and identifiers are suppressed. Standard
GitHub checkout action logs are separate from this sanitized helper output.
Checks fail closed on unexpected official-script output, mismatched hashes,
unsafe archives, unsupported platforms, or missing tools.

## Offline process-identity correction (not execution approval)

[CPython 3.14 `subprocess.py`](https://github.com/python/cpython/blob/v3.14.0/Lib/subprocess.py)
waits/reaps before a successful `communicate()` returns. The previous unconditional
numeric `killpg` afterward could therefore signal a recycled PID/process-group ID.
The Linux launcher now drains pipes with selectors, observes its private child via
`waitid(P_PIDFD, WEXITED | WNOHANG | WNOWAIT)`, and keeps the leader unreaped until
its group has been signaled. An exited leader remains a zombie that pins its PID.
A pidfd-bound child check and matching leader/group check precede every group signal;
`wait()` is performed only afterward, with no further numeric signaling. An exited
leader's same-group descendants are stopped before their inherited pipes are drained.
The command retains its 180-second bound; post-signal leader reaping is bounded.

Captured stdout and stderr share an aggregate 1 MiB raw-byte limit. The selector
checks the limit before extending either buffer, fails with fixed `output_limit`,
and performs the same identity-bound teardown; captured bytes are never logged.

A distinct `TeardownUnverified` failure conservatively covers launcher/Popen errors,
pidfd acquisition, lost ownership,
group signaling and leader-reaping failures after launch. Before any check/command,
`run()` persists an `unverified` process-teardown state in the run-owned receipt.
On that failure it retains both root and receipt without invoking recursive cleanup
or unlinking either. The independent `--cleanup` path refuses this receipt state,
even if the root has gone missing, so the workflow retry cannot delete retained
scratch still potentially in use. Successful command teardown keeps timeout,
interruption and ordinary failures classified as before and permits normal cleanup;
a `verified` receipt remains retryable if ordinary filesystem cleanup fails.
Legacy two-field receipts, missing/unknown state, and invalid or partial receipt
writes are refused rather than defaulting to safe cleanup. The unverified state
is closed/flushed before entering the check and remains in force across every
child launch; SIGKILL or a crash before promotion therefore cannot make a retained
receipt cleanup-eligible under these trusted-launcher assumptions.
This is not independent proof that escaped descendants have exited or hostile-host
cleanup is safe; those blockers and the disabled execution boundary remain.

Missing Linux support, a non-default SIGCHLD handler/disposition, multiple Python
threads, an already-reaped leader, lost child binding, or mismatched group refuses
supervision/signaling. No numeric fallback is used on pidfd acquisition failure.
Acquisition, signaling, or reaping errors are failures, never proof of teardown.
They can leave owned processes and scratch requiring independent operator handling.
The standalone launcher must exclusively reap its private child, use normal native
SIGCHLD flags (no SA_NOCLDWAIT), and run trusted code; Python-level checks cannot
prove native signal flags, other native waiters, or a compromised same-UID host.
Pidfds alone do not reserve a numeric group after reaping. Children escaping their
original group/session are not contained or certified stopped by this change.

Evidence is limited to synthetic owned Python children and mocked PID-reuse/error
cases in non-root hosted CI. No actual Foundry dependency/setup script, Terraform,
Azure identity, or protected/private-runner execution is exercised. Existing
shared-workspace, recursive-cleanup, same-UID/host-trust, and escaped-descendant
blockers remain. This branch must remain unmerged, and this correction does not
authorize enabling or running the prerequisite workflow or claim cleanup isolation.

Normal exits and handled interruption remove scratch in `finally`; command
owned process groups are signaled before removal only while leader ownership is retained; this is not proof that every descendant has exited. An `always()` step retries cleanup
using this run's exclusive receipt and ownership marker, then removes only this
run's source directory. Invalid ownership fails closed, without deleting an
unowned directory. No software can guarantee cleanup after runner loss or a hard
kill that also prevents the `always()` step; such a run must not be reported as
success. Dependencies are intentionally removed, so this verifies setup without
making them available to a later job.

Run the deterministic offline tests with:

```text
python -m unittest discover -s .github/scripts -p test_check_foundry_prerequisites.py -v
```

Tests use fake downloads, archives, commands, and configuration. They never
install tools or extensions and never access Azure or the network.

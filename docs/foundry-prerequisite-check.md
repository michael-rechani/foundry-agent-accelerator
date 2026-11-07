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
`skill_execution`, `version`, `cleanup`, `timeout`, `interruption`, `output_limit`, or
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

## Offline process-identity correction: launcher disabled

[CPython 3.14 `subprocess.py`](https://github.com/python/cpython/blob/v3.14.0/Lib/subprocess.py)
reaps before a successful `communicate()` returns. The earlier unconditional numeric
`killpg` afterward could signal a recycled process group. The subsequent pidfd/`WNOWAIT`
revision retained the leader during signaling, but **did not prove complete group
termination**: SIGKILL delivery, pipe EOF, and waiting for just the leader cannot
establish that a same-group descendant has finished all pending I/O. In particular,
a descendant may close both pipes while remaining alive. Timeout/output-failure paths
have the same gap; reaping the leader removes its numeric-PGID binding.

The prerequisite launcher is therefore **disabled before download/setup or process
creation**. Both `check()` and `command()` refuse with `TeardownUnverified("cleanup")`.
No numeric group is signaled and no leader is reaped by this disabled path. The disconnected [owned-process prototype](owned-process-supervisor.md) provides only
conditional synthetic evidence and is not integrated or approved for this launcher;
proc enumeration, pipe EOF, kill success, and leader wait are not substituted as proof.
No namespace/cgroup/privilege escalation or unrelated process control is used.

`run()` persists and closes an `unverified` teardown receipt before entering `check()`.
On refusal it retains root and receipt without `rmtree` or unlink. Separate `--cleanup`
requires explicit `no_process_started` state and rejects historical `verified`,
unverified, legacy/missing, unknown,
null or partial records even if the root is absent. Crash-before-promotion remains
conservative. Normal pre-command failures retain their original classification and
cleanup behavior for runs that never started a process; they are not evidence of
successful process supervision.
A receipt describing a completed group is never promoted by the disabled launcher.
The previous selector output capture (including its 1 MiB bound) is removed rather
than retained as a reachable unsafe execution path; no command output is captured.

Evidence is synthetic only: mocked unproven outcomes through `run()` and separate
cleanup, plus a bounded owned Python child that closes both pipes, stays alive, and
writes fictional bytes after cleanup has been refused. No actual Foundry dependency
script, Azure/private runner, Terraform, credentials, or live workflow is exercised.
All existing workflows are unchanged; this offline branch stays unmerged.

The unresolved supervision boundary is tracked in [#522](https://github.com/michael-rechani/foundry-agent-accelerator/issues/522#issuecomment-6713887281).

**Blocker:** complete owned same-group termination and completion of pending writes
cannot be certified here without an independently reviewed supervision boundary.
Escaped descendants and hostile shared-host/same-UID races are separate unresolved
problems, as are shared-workspace and recursive-cleanup safety. This change neither
solves them nor authorizes prerequisite workflow execution. Existing historical
verified receipts do not retrospectively prove complete group teardown and are
refused by separate cleanup, rather than accepted as proof.

Ordinary pre-command failures can remove scratch in `finally`; disabled-launcher
refusal retains it. No command group cleanup is certified. An `always()` step retries cleanup
using this run's exclusive receipt and ownership marker, then removes only this
run's source directory. Invalid ownership fails closed, without deleting an
unowned directory. No software can guarantee cleanup after runner loss or a hard
kill that also prevents the `always()` step; such a run must not be reported as
success. No dependencies can be installed by this disabled launcher.

Run only the focused disabled-launcher synthetic tests (in hosted CI):

```text
python -m unittest test_check_foundry_prerequisites.ProcessTests test_check_foundry_prerequisites.ProcessRetentionTests test_check_foundry_prerequisites.CleanupTests test_check_foundry_prerequisites.FailureStageTests -v
```

Historical full-file tests that expect prerequisite setup success no longer describe
this disabled execution boundary. They were not run as proof of readiness. Focused
tests never install Foundry tools/extensions or access Azure or private data.
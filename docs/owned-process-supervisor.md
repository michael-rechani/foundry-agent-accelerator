# Owned-process supervisor experiment: public launch disabled

This disconnected Linux-only prototype is **not a working public supervisor**.
`supervise(argv, timeout=..., grace=..., output_limit=...)` always returns
`Result(False, "unverified")`, before validation, serialization, `Popen`,
pidfd creation, waiting, signaling, or proof processing. The former outer caller
is removed, not kept as a private fallback. No arbitrary caller can opt into it.
The production prerequisite `check()`/`command()` hard gate and unverified
scratch-cleanup receipt veto are unchanged. This is **not rollout readiness**.
The unresolved boundary is tracked in
[#522](https://github.com/michael-rechani/foundry-agent-accelerator/issues/522#issuecomment-6714075624).

## Why public launch refuses

The [Linux pidfd_open manual](https://man7.org/linux/man-pages/man2/pidfd_open.2.html)
only guarantees post-fork zombie PID retention if SIGCHLD is not explicitly
ignored, SA_NOCLDWAIT is absent, and no signal handler, other thread, or external
waiter has reaped the child. Otherwise creation with **CLONE_PIDFD** is required.
A post-spawn `pidfd_open(proc.pid)` can bind an unrelated reused PID; signaling
that descriptor would control the wrong process. A descriptor remains stable
after binding, but that does not prove the binding was to the spawned child.
Inspecting a SIGCHLD disposition cannot establish or lock all these conditions.

[CPython 3.14 Lib/subprocess.py](https://github.com/python/cpython/blob/3.14/Lib/subprocess.py)
`Popen._try_wait` catches `ChildProcessError` and substitutes `(self.pid, 0)`.
An exact success frame followed by `Popen.wait() == 0` can therefore appear to
succeed even when another waiter consumed an abnormal real exit status. EOF,
signal delivery, an assumed exclusive reaper, and Python's zero are not proof.

No rigorous atomic birth-bound launch helper or trustworthy terminal-status
handling under external waiters is implemented. Re-enabling the public API
requires an independently reviewed atomic CLONE_PIDFD launch and explicit
`waitid(P_PIDFD)` status, with missing status/ECHILD a failure, plus proof of
every signaling/reaping race. This change does not use ctypes fork in threaded
Python, architecture-assumed raw clone, or post-spawn binding as a substitute.

## Private dedicated-interpreter experiment

Only `_experimental_supervisor` and the explicit
`--experimental-supervise` test entrypoint retain the inner subreaper experiment.
They are unreachable through `supervise()`. They are **not an arbitrary-caller
subprocess primitive** and must not be used for production or arbitrary work.
The hosted tests launch this interpreter directly for bounded fictional,
self-terminating workers only. Their fresh, trusted, single-threaded interpreter
uses default SIGCHLD, no SA_NOCLDWAIT, and no external waiters. These are explicit
test assumptions, not conditions this code can safely establish for a caller.

The inner experiment enables child-subreaper mode and uses a non-reaping
`waitid(P_ALL, ..., WNOWAIT)` observation to refuse preexisting children.
It starts a worker in a new session/group and retains a post-spawn pidfd-bound
leader under the above restricted test assumptions. After observing the leader
with `waitid(P_PIDFD, ..., WNOWAIT)`, it checks session/group identity and
signals the group before reaping the leader. It consumes explicit leader status
with `waitid(P_PIDFD)` before reaping adopted children; ECHILD at that stage
fails, never fabricates status zero. It requires eventual ECHILD for all ordinary
waitable children and drained/closed output pipes before its sole terminal frame.
There is no numeric signaling of adopted PIDs or pidfd signaling of escaped
descendants. An escaped child must terminate on its own before grace expires.

The last WNOWAIT observation does **not** lock out an external waiter between
observation, group-identity checks, and numeric group signaling. Post-spawn
binding also remains conditional here. Tests of an ECHILD before signal or
while consuming status demonstrate refusal in those cases, not safety of all
interleavings. No public routine launches or signals this experimental process.
Partial spawn/crash can leave reparented descendants; there is no safe recovery
signal path. A terminal outcome describes ordinary waitable-child completion
only under the experimental assumptions. `success` is the leader's zero status,
not every descendant's application success; `nonzero`, `timeout`, and
`output_limit` do not mean the command succeeded.

## Evidence and remaining limitations

Mocked tests model original-child reaping/PID reuse and wrong descriptor
signaling on interruption, reproduce actual CPython `_try_wait` ECHILD-to-zero
without creating a process, and exercise lost status/external-waitid races.
The public tests assert no launch, binding, signal, wait, serialization, inner
entrypoint, or proof processing occurs even for valid requests, abnormal exit
frames, timeout, and interruption conditions. Dedicated-interpreter regression
tests require explicit kernel waitid exit status, fail ECHILD, and never use
`Popen.wait()` as proof or outer failure signaling. Existing focused
disabled-launcher ProcessTests, ProcessRetentionTests, CleanupTests, and
FailureStageTests remain part of hosted validation; no full discovery or
official Foundry fixture/setup is run.

The host, executable/Python/filesystem, and same-UID/shared-workspace trust
remain unresolved: the experimental frame is not authentication against a
compromised host or another same-UID actor. Namespace/parentage changes,
noncooperative or uninterruptible tasks, delegated external-service work,
path-based recursive scratch cleanup, and asynchronous kernel/device/service
I/O completion or durability remain outside this experiment. Python polling
cannot enforce a hard deadline on process creation or blocked kernel calls.
No Azure, Foundry, azd, credentials, protected inputs, namespaces/cgroups,
privileged runner, or destructive cleanup was used or authorized.
Meta-package ID-only readiness still does not verify the seven independently
versioned core extensions or provide authenticated component-closure evidence.
The prerequisite gate and receipt veto remain untouched pending independent
review of these blockers.

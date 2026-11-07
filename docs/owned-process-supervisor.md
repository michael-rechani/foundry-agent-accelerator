# Owned-process supervisor experiment

This Linux-only, unprivileged prototype is disconnected from the prerequisite
launcher. `check()` remains unconditionally disabled, and unverified receipts
remain a veto on scratch cleanup. This experiment is **not rollout readiness**.
The outstanding boundary remains [#522](https://github.com/michael-rechani/foundry-agent-accelerator/issues/522#issuecomment-6713887281).

`supervise(argv, timeout=..., grace=..., output_limit=...)` returns only a
`Result(verified, outcome)`. `unverified` is the fixed failure result; command
output and exception details are never returned or logged. A verified outcome
can be success, nonzero, timeout, or output_limit: the latter three do not mean
the command succeeded. The executable must be absolute. No credentials,
protected inputs, shell, or inherited worker environment are used.

The caller launches a fresh, dedicated, single-threaded supervisor. Before
spawning it requires default SIGCHLD, enables Linux child-subreaper mode, and
requires `waitpid(-1, WNOHANG)` to report ECHILD. The worker starts a new
session and process group. Its leader is bound with a pidfd and observed with
`waitid(P_PIDFD, ..., WNOWAIT)`. The supervisor validates the retained leader's
session and group and sends SIGKILL to that group **before** reaping the leader.
It then reaps all direct and subreaper-adopted children and requires ECHILD,
as well as drained and closed output pipes, before sending its sole terminal
frame. Neither leader exit, pipe EOF, nor successful signal delivery alone is
proof. There is no process enumeration, numeric signaling of adopted PIDs, or
pidfd signaling of escaped descendants.

Children that escape the group must terminate on their own before the overall
supervisor deadline; otherwise the result is unverified. Only cooperative,
bounded synthetic workers are appropriate. Spawn, platform, pidfd, prctl,
identity, signal, protocol, and deadline failures do not certify teardown.
After a partial spawn or supervisor crash, surviving children can be reparented;
the caller cannot safely recover or signal them. In particular, this design
cannot promise cleanup of noncooperative or uninterruptible tasks after failure.

The parent limits request and response bytes, accepts exactly one fixed terminal
frame, requires EOF and a zero supervisor exit status within its total deadline,
and discards all output. The worker does not inherit the supervisor protocol
stream. The protocol is trustworthy only when the supervisor executable, Python,
filesystem, caller, and host are trusted: it is **not** authentication against
an untrusted same-UID process or compromised host. This prototype does not
isolate arbitrary hostile namespace or parentage changes, work delegated to
external services, shared workspace trust, or path-based scratch cleanup.
It has not established that any real Foundry setup or destructive cleanup is
safe; no integration or receipt promotion is provided.

The hosted Linux tests use bounded fictional Python processes, exercise real
supervisor calls plus injected faults, and retain the existing focused
disabled-launcher receipt and cleanup tests. They do not execute Foundry setup
or access Azure. Passing those tests is conditional evidence under the above
trust and cooperation assumptions, not a claim about a hostile host.

The outer caller binds the supervisor itself with a pidfd before submitting
work. Failure or interruption cleanup signals only that retained descriptor,
never a numeric supervisor PID or worker group. A missing binding closes the
request pipe and returns unverified without signaling. The supervisor owns
all of its children exclusively; its Python runtime and no-other-reaper
assumption are part of the trust model. Before spawn, child observation uses
WNOWAIT and does not reap a preexisting child. Input count and character
length are bounded before serialization, with a separate encoded-wire cap.
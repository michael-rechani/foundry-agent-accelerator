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
does not clean an existing checkout. The prerequisite helper creates a unique
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
The verified archive contributes only its regular `azd` file. An existing azd
executable is reused, with extension state still isolated. The official script
is rerun after the fallback; it installs `microsoft.foundry` when absent.

Public downloads use HTTPS without authentication or inherited proxies.
The official extension installer also requires outbound access to its official
registry and release assets. This is not an offline runtime check and does not
create publicly reachable resources. The extension release is selected by the
official script, not separately pinned by this helper.

Only a sanitized azd version and readiness are printed by the helper; child
output, exceptions, paths, commits, and identifiers are suppressed. Standard
GitHub checkout action logs are separate from this sanitized helper output.
Checks fail closed on unexpected official-script output, mismatched hashes,
unsafe archives, unsupported platforms, or missing tools.

Normal exits and handled interruption remove scratch in `finally`; command
process groups are stopped before removal. An `always()` step retries cleanup
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

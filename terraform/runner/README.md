# Self-hosted CI runner

[Home](../../README.md) / [Infrastructure](../README.md) / CI runner

Draft a single Ubuntu 24.04 virtual machine (VM) that runs the
[`validate.yml`](../../.github/workflows/validate.yml) jobs when GitHub-hosted
Actions minutes run out. This Terraform root manages only a new resource group,
one subnet in the existing management virtual network (VNet), and the runner VM.
It reads the VNet and its NAT gateway without taking ownership of them.

> [!IMPORTANT]
> **This is a draft. Nothing has been applied.** Review it, approve the shared
> egress described in [Outbound access](#outbound-access), and apply it yourself
> from an authorized private-network environment.

> [!WARNING]
> **Public repository risk.** A persistent self-hosted runner executes the code in
> pull requests on a machine inside your network, so no pull request workflow may
> use it. `validate.yml` runs on GitHub-hosted `ubuntu-24.04` runners. Only the
> manual [`deploy-lab.yml`](../../.github/workflows/deploy-lab.yml) targets this
> runner, and it runs only from `main` behind the `lab-deploy` environment. Fork
> pull requests need approval from every outside contributor. To let it push images,
> set `registry_private_endpoint_ips` so the NSG allows TCP 443 to the registry
> private endpoint only. Everything else in the VNet stays denied.

Run commands in `terraform/runner/`, not in the parent platform root. The runner
is called the CI runner here to avoid confusion with the Windows jumpbox that
other guides call the private runner.

## At a glance

| Setting | Value |
| --- | --- |
| OS | Ubuntu Server 24.04 LTS (Trusted Launch) |
| Size | `Standard_D4s_v5` (4 vCPU, 16 GiB). Docker is needed for the Lab frontend job. |
| Labels | `self-hosted`, `linux`, `lab-runner` |
| Resource group | New `rg-runner-<base_name>-<environment>`. Not the Lab's. |
| Subnet | `snet-runner` in the existing management VNet. Default `10.43.2.0/27`. |
| Public IP | None on the VM. Outbound traffic uses the existing jumpbox NAT gateway. Requires `approve_shared_egress = true`. |
| Inbound | None. The NSG denies all inbound traffic, including from the VNet. |
| Identity | System-assigned managed identity. Its only permission is to read and deallocate itself. |
| Service | systemd unit installed by the runner's `svc.sh`, running as the non-root `runner` user |
| Updates | Ubuntu `unattended-upgrades` (security and updates, reboot at 04:30) and the runner's built-in self-update |
| Cost control | Self-deallocates after 30 idle minutes, plus a daily 03:00 UTC backstop |
| State example | `ai-foundry/runner-dev.tfstate` |

## Outbound access

The VM needs outbound internet access to reach GitHub. The repository already
has a NAT gateway with a static public IP for the jumpbox subnet. A NAT gateway
serves every subnet in its VNet, so this stack adds `snet-runner` to that VNet
and attaches it to the same gateway. **No new public IP is created.**

| Option | Fixed monthly cost | Notes |
| --- | --- | --- |
| **A. Reuse the existing jumpbox NAT gateway (this draft)** | $0 extra | Plus $0.045/GB processed. Same VNet only. Shares the outbound IP with the jumpbox. |
| B. New NAT gateway and Standard public IP in a separate VNet | About $36.50 | $32.85 gateway plus $3.65 IP, plus $0.045/GB. Needs a new VNet. Not needed while A is available. |
| C. Standard Load Balancer with outbound rules and a public IP | About $22 (approximate) | Not verified against the price API. Risk of SNAT port exhaustion. |
| D. Public IP on the VM's network interface | About $3.65 | Rejected. A public IP on the VM isn't allowed. |
| E. Azure Firewall | Several hundred dollars | Rejected. Far too costly, and the existing firewall must not be touched. |
| F. Default outbound access | $0 | Rejected. Azure is retiring it and the IP isn't stable. The subnet disables it. |

Before applying, confirm that the NAT gateway exists. `enable_jumpbox` can be
off, and this stack fails to plan if the gateway isn't there rather than
creating one.

The NSG limits outbound traffic to ports 80 and 443 (plus Azure's DNS and
metadata endpoints) and **denies the VirtualNetwork destination**. Pull request
code can't reach the jumpbox, the peered Foundry network, or private endpoints, except the registry exception above.
If you add an egress allowlist later, these hosts are needed:
`github.com`, `api.github.com`, `*.actions.githubusercontent.com`,
`objects.githubusercontent.com`, `pypi.org`, `files.pythonhosted.org`,
`registry.npmjs.org`, `releases.hashicorp.com`, `registry.terraform.io`,
Docker Hub, the Ubuntu archive, `snapcraft.io`, and the Playwright CDN.

## Estimated monthly cost

Retail prices from the Azure Retail Prices API for `northcentralus` and
`westus3`. `southcentralus` and `westus` run about 20-25% higher for compute.
Reusing the NAT gateway adds no fixed cost.

| Item | Always on (730 h) | Business hours (about 176 h) | Usage-based (about 50 h) |
| --- | --- | --- | --- |
| `Standard_D4s_v5` at $0.192/h | $140 | $34 | $10 |
| 128 GiB Standard SSD (billed while deallocated) | $9.60 | $9.60 | $9.60 |
| NAT data, 100 GB at $0.045/GB | $4.50 | $4.50 | $4.50 |
| **Total** | **About $154** | **About $48** | **About $24** |

Idle deallocation moves a lightly used runner into the right-hand column. A
`Standard_D2s_v5` ($0.096/h) halves the compute rows, but the Lab frontend job
and Docker need the headroom. Change `vm_size` if you want to try it.

## Prerequisites

- The state storage account, container, and the Contributor and **Storage Blob
  Data Contributor** access that [Bastion](../bastion/README.md) also needs. Use
  a **separate state key**, never the platform's or the Lab's.
- Permission to create a resource group, a role definition, and a role
  assignment (Owner, or Contributor plus User Access Administrator) on the
  subscription, and to create a subnet in the existing VNet's resource group.
- The names of the existing VNet and NAT gateway (`terraform/jumpbox.tf` creates
  `vnet-jumpbox-<suffix>` and `nat-jumpbox-<base_name>-<environment>`).
- A public SSH key. Azure requires one even though nothing can connect to the VM.

## Deploy

1. Copy `dev.tfvars.example` to ignored `dev.tfvars` and fill in the
   subscription, the existing network resource group, VNet, NAT gateway, and your
   public key. The region comes from the existing VNet.
2. Set `approve_shared_egress = true` only after you approve sharing the
   jumpbox's outbound public IP.
   If the Lab deploy workflow uses this runner, also set
   `registry_private_endpoint_ips` to the registry private endpoint addresses
   (registry and data endpoint). The dev runner's NSG already has that rule,
   added by hand as `AllowRegistryPrivateEndpointOutbound` (priority 120,
   TCP 443, `10.42.0.24` and `10.42.0.25`). If this variable is left empty on an
   apply, Terraform removes the rule and the deploy workflow can no longer push.

   **The dev runner already exists and is not yet in the state.** Don't apply this
   stack against it. After step 3 and `terraform init`, run
   [`scripts/import-live.ps1`](scripts/import-live.ps1) from the jump box. It
   refuses to run until `registry_private_endpoint_ips` is set in your tfvars,
   prints the `terraform import` commands as a dry run, and writes to the state
   only with `-Apply`. Then run the plan in step 4: it must show no change to the
   VM and no public IP, and a second plan must show no changes at all.

   ```powershell
   ./scripts/import-live.ps1 -VarFile dev.tfvars          # dry run
   ./scripts/import-live.ps1 -VarFile dev.tfvars -Apply   # writes to the shared state
   ```
3. Copy `backend.hcl.example` to ignored `backend.hcl` and fill in the secured
   state account.
4. Run:

   ```powershell
   terraform init -backend-config=backend.hcl
   terraform plan -var-file=dev.tfvars -out=runner.tfplan
   ```

5. Review the plan. It creates a resource group, an NSG, `snet-runner`, a
   network interface, the VM, a custom role and assignment, and a shutdown
   schedule. It must contain **no public IP**.
6. Apply only when the plan matches. The plan file and state can hold sensitive
   values, so keep them private. Neither holds a runner token.

The VM's first boot installs Docker, Git, the GitHub CLI, PowerShell, build
tools, and the runner software. This takes a few minutes. It doesn't register the
runner.

## Register the runner

The registration token is a short-lived secret that **you** generate. It is never
stored in code, the Terraform state, the pull request, or chat.

1. In GitHub, go to **Settings > Actions > Runners > New self-hosted runner** for
   this repository. Choose **Linux** and copy only the token from the
   `./config.sh --token` line. It expires in about an hour.
2. In a PowerShell window, paste the token at a hidden prompt. It isn't echoed or
   saved to history, and nothing is written to a file:

   ```powershell
   $token = Read-Host "Runner registration token" -AsSecureString
   $plain = [System.Net.NetworkCredential]::new("", $token).Password
   ```

3. Register the runner through a managed Run Command, which passes the token to
   the script as a protected environment variable:

   ```powershell
   az vm run-command create `
     --resource-group <runner-resource-group> `
     --vm-name <runner-vm-name> `
     --name register-runner `
     --script "/usr/local/sbin/register-runner" `
     --protected-parameters "RUNNER_TOKEN=$plain"
   Remove-Variable plain, token
   ```

4. Delete the Run Command, and with it any stored copy of the token:

   ```powershell
   az vm run-command delete --resource-group <runner-resource-group> --vm-name <runner-vm-name> --name register-runner --yes
   ```

5. In **Settings > Actions > Runners**, confirm the runner is **Idle** with the
   `self-hosted`, `linux`, and `lab-runner` labels.

> [!NOTE]
> Run Command works for registration, as long as the token is passed as
> `RUNNER_TOKEN=<token>`. The bracketed `[{name:...,value:...}]` form doesn't
> work with `az vm run-command create`: the CLI treats the whole string as one
> value called `arg1`, and the script never sees `RUNNER_TOKEN`. If Run Command
> stops working, ask for approval to use Azure Bastion or the serial console
> instead. Neither is enabled here. Serial console doesn't work with the
> key-only admin user, so it would also need a password.

## Add a second runner

One runner runs the eight `validate.yml` jobs one after another, so a full run
takes roughly 15 to 20 minutes. A second runner on the same VM lets two jobs run
at once. It adds no cost, but the heavy `workbench-frontend` job (Playwright)
shares the VM's four vCPUs and memory with whatever else is running.

`scripts/add-runner.sh` isn't part of the cloud-init, so using it never changes
the Terraform plan or replaces the VM. Run it after the first runner is
registered, with a fresh token from **Settings > Actions > Runners**:

```powershell
$token = Read-Host "Runner registration token" -AsSecureString
$plain = [System.Net.NetworkCredential]::new("", $token).Password
az vm run-command create `
  --resource-group <runner-resource-group> `
  --vm-name <runner-vm-name> `
  --name add-runner `
  --script "@terraform/runner/scripts/add-runner.sh" `
  --parameters RUNNER_INSTANCE=2 `
  --protected-parameters "RUNNER_TOKEN=$plain"
Remove-Variable plain, token
az vm run-command delete --resource-group <runner-resource-group> --vm-name <runner-vm-name> --name add-runner --yes
```

Pass the script with LF line endings. Instance N lives in `/opt/actions-runner-N`
and shows up as `<hostname>-N`. The idle shutdown counts every runner, so the VM
only deallocates when none of them is busy.

## Start, stop, and updates

- **Starting.** The VM deallocates when idle, so start it before you open a pull
  request: `az vm start --resource-group <runner-resource-group> --name <runner-vm-name>`.
  The runner service starts on boot. Queued jobs wait up to 24 hours for a runner.
  There is no automatic start, because a webhook-driven start needs a public
  endpoint.
- **Idle shutdown.** A systemd timer checks every five minutes. After 30 idle
  minutes (`idle_shutdown_minutes`) it deallocates the VM through its managed
  identity. It never acts before the runner is registered, and it skips while a
  job or an apt update is running.
- **Backstop.** A daily shutdown at 03:00 UTC (`auto_shutdown`) deallocates the VM
  even if the idle check fails. A job running then is stopped.
- **Updates.** `unattended-upgrades` installs security and standard updates and
  reboots at 04:30 if needed, and a reboot can interrupt a running job. The runner
  updates itself. Don't pass `--disableupdate`.

## Security notes

- The runner user is in the `docker` group, which is root-equivalent on the VM.
  The Lab frontend job needs Docker. The VM holds no secrets beyond its identity.
- The identity can only read and deallocate this VM. It can't reach Key Vault,
  storage, or the Lab's VMs.
- Jobs on this runner share one machine and disk. They don't get a clean
  environment on each run as GitHub-hosted runners do.
- Only `validate.yml` uses the runner. `deploy-lab.yml` stays on GitHub-hosted
  runners.

## Merge order

Merge the pull request that switches `validate.yml` to this runner only after the
runner shows **Idle** in GitHub. Until then the validation jobs queue with nothing
to run them.

## Check without Azure

These commands need no Azure credentials. They use mock providers and
`terraform init -backend=false`.

```powershell
terraform -chdir=terraform/runner fmt -check -recursive
terraform -chdir=terraform/runner init -backend=false
terraform -chdir=terraform/runner validate
terraform -chdir=terraform/runner test
```

## Remove the runner

1. In GitHub, remove the runner under **Settings > Actions > Runners**.
2. Switch `validate.yml` back to `ubuntu-24.04`.
3. Run `terraform destroy -var-file=dev.tfvars` from an authorized environment.
   Terraform sets `prevent_destroy` on the subnet, so plan its removal as a
   separate approved step.

## Related content

- [Terraform infrastructure](../README.md)
- [Bastion](../bastion/README.md)
- [Private deployment runbook](../../docs/private-deployment.md)
- [Credentials and protected state](../../docs/credentials.md)

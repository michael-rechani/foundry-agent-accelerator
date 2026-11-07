# Self-hosted CI runner

[Home](../../README.md) / [Infrastructure](../README.md) / CI runner

Define a single Ubuntu 24.04 virtual machine (VM) for approved GitHub jobs.
Pull request validation stays on GitHub-hosted runners.
This Terraform root manages a resource group,
one subnet in the existing management virtual network (VNet), and the runner VM.
It reads the VNet and its NAT gateway without taking ownership of them.

> [!IMPORTANT]
> **The dev runner already exists and has remote state.** Live-state inventory
> confirmed it during #389. Reconciliation and clean-plan checks remain tracked
> in #318/#348. Do not recreate it or reimport resources already owned by its
> state. New installations still require explicit approval for shared egress.

> [!WARNING]
> **Public repository risk.** A persistent self-hosted runner executes the code in
> pull requests on a machine inside your network, so no pull request workflow may
> use it. `validate.yml` runs on GitHub-hosted `ubuntu-24.04` runners. Only the
> approved deployment, recording and state-access jobs target this
> runner, and they run only from `main` behind their GitHub environments. Fork
> pull requests need approval from every outside contributor. To let it push images,
> set `registry_private_endpoint_ips` so the NSG allows TCP 443 to the registry
> private endpoint only. To let the approved
> [`record-library-answers.yml`](../../.github/workflows/record-library-answers.yml)
> workflow call the private Foundry account, set `foundry_private_endpoint_ips` the
> same way (it runs only from `main`, behind the `library-recording` environment's
> required reviewer). The separate backend HTTPS exception below serves the
> approval-gated state check. Everything else in the VNet stays denied.

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

### Private Terraform backend

Set `state_backend_private_endpoint_ips` to the approved backend blob private
endpoint addresses. This adds only `AllowStateBackendPrivateEndpointOutbound`
(priority 140, outbound TCP 443). Variable validation rejects public addresses,
ranges and hostnames. Keep registry/Foundry exceptions and all inbound/VNet deny rules.
One backend address uses Azure's singular address field; multiple addresses use
the plural field. This preserves the existing single-endpoint rule without a
format-only NSG update.
The management VNet must already resolve the backend privately and be peered
to its endpoint VNet.

Use the [dedicated GitHub OIDC state identity](../github-state-access/README.md), not
the runner VM identity, for blob authorization. The approval-gated connectivity
workflow verifies a disposable blob lease, never an actual state write or an
infrastructure apply. Existing jumpbox access is a separately documented
maintenance exception, not the normal deployment path. See #389/#393.

For approval-gated import-only access adoption and a full runner plan, use the
[ARM-only planning workflow](../runner-plan-access/README.md). It persists
canonical private inputs, rejects resource mutations and verifies that a runner
plan leaves existing state contents unchanged. A successful plan is not an
infrastructure deployment or an apply of refreshed NSG state.
After explicit approval, its `save-runner-state` operation applies only an exact
full-root no-change saved plan, verifies the complete NSG persisted remotely,
and requires a fresh clean plan. It does not grant infrastructure-write rights.

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
code can't reach the jumpbox or arbitrary private endpoints. Only the explicit
registry, Foundry and backend HTTPS exceptions are allowed.
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

Idle deallocation moves a lightly used runner into the right-hand column. The
live VM's OS disk is `Standard_LRS` (the `os_disk_storage_account_type` default),
which costs less than the Standard SSD row above. Set it to `StandardSSD_LRS` if
you want the faster disk. A
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

   To let the recording workflow reach the private Foundry account, also set
   `foundry_private_endpoint_ips` to the Foundry private endpoint addresses. This
   adds `AllowFoundryPrivateEndpointOutbound` (priority 130, TCP 443 to those
   addresses only) through Terraform. Don't add it by hand (see #318). Find the
   addresses by resolving the account's private endpoint name from the runner.
   For backend access, also preserve the approved
   `state_backend_private_endpoint_ips` input on every runner plan.
   The existing dev runner already has remote state. Inventory that state first;
   the legacy [`import-live.ps1`](../../scripts/terraform/import-live.ps1) is only
   for separately approved adoption of resources proven absent from it, not a
   reason to write state from the jumpbox. GitHub is the normal state writer.
   The helper checks managed resources in the root and all child modules for
   existing ownership. It refuses unreadable, empty or mismatched runner state,
   malformed modules or managed resources without IDs, and requires a nonempty
   single-line registry address list. It is not wired into a protected import
   workflow; any non-GitHub writer needs a separately approved and documented
   exception. The address check does not verify every live exception; review the
   full plan and all private endpoint inputs.
3. Copy `backend.hcl.example` to ignored `backend.hcl` and fill in the secured
   state account.
4. Run:

   ```powershell
   terraform init -backend-config=backend.hcl
   terraform plan -var-file=dev.tfvars -out=runner.tfplan
   ```

5. Review the plan. For a new installation it creates a resource group, an NSG, `snet-runner`, a
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
> work with `az vm run-command create`. The CLI treats the whole string as one
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

- **Starting.** The VM deallocates when idle. The draft
  [`deploy-lab.yml`](../../.github/workflows/deploy-lab.yml) no longer starts
  it: a manual job targeting an offline runner cannot bootstrap itself. The
  runner-only rollout needs a separately approved way to bring a runner online;
  none is established yet (#522). Do not use a local or jumpbox Azure write,
  or the GitHub-hosted starter in
  [`record-library-answers.yml`](../../.github/workflows/record-library-answers.yml),
  as a substitute without specific authorization. The runner service starts
  on boot. Queued jobs wait up to 24 hours for a runner. There is no
  webhook-driven start, because it needs a public endpoint.
- **Idle shutdown.** A systemd timer checks every five minutes. After 30 idle
  minutes (`idle_shutdown_minutes`) it deallocates the VM through its managed
  identity. It never acts before the runner is registered, and it skips while a
  job or an apt update is running.
- **Backstop.** A daily shutdown at 03:00 UTC (`auto_shutdown`) deallocates the VM
  even if the idle check fails. It stops a job running then.
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
- The deploy job and protected Terraform workflows use the private runner.
  The image workflow's read-only validation gate uses a GitHub-hosted runner.

## Merge order

Merge the pull request that switches `validate.yml` to this runner only after the
runner shows **Idle** in GitHub. Until then the validation jobs queue with nothing
to run them.

## Check without Azure

These commands need no Azure credentials. They check formatting and configuration
with `terraform init -backend=false`; native HCL tests aren't included.

```powershell
terraform -chdir=terraform/runner fmt -check -recursive
terraform -chdir=terraform/runner init -backend=false
terraform -chdir=terraform/runner validate
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

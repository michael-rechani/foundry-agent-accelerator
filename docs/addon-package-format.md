# Add-on package format

[Home](../README.md) / [Docs](README.md) / Add-on package format

An add-on is an optional tool or skill an agent could use, such as knowledge
search. Each one is described by a manifest in
[`addons/<id>/addon.json`](../addons/). The manifest holds the card the Lab's
**Add-ons** tab shows and, once someone has built the add-on, a deployment
package: a runbook, an acceptance case, a Terraform module, and the roles that
module may grant.

> [!IMPORTANT]
> **Nothing in `addons/` deploys anything, and no check contacts Azure.** The
> format makes a package reviewable before anyone runs it. A person approves
> the saved Terraform plan and runs the apply. An agent never applies a plan.
> A package can't ask for public network access, keys, shared-key or anonymous
> access, admin users, or public IP addresses. See
> [Fixed guardrails](#fixed-guardrails).

The roadmap for add-ons is in
[#54](https://github.com/michael-rechani/foundry-agent-accelerator/issues/54).
The work to build and deploy one from the repository is in
[#121](https://github.com/michael-rechani/foundry-agent-accelerator/issues/121).
For how an add-on fits with the rest of the platform, see
[Optional integrations](optional-integrations.md).

## In this guide

- [Folder layout](#folder-layout)
- [The manifest](#the-manifest)
- [The deployment package](#the-deployment-package)
- [Fixed guardrails](#fixed-guardrails)
- [What the check enforces](#what-the-check-enforces)
- [How the Add-ons tab uses the manifests](#how-the-add-ons-tab-uses-the-manifests)
- [Add or change an add-on](#add-or-change-an-add-on)
- [Not done yet](#not-done-yet)

## Folder layout

```text
addons/
  addon_manifest.py        Reads and checks the manifests
  check_addons.py          The check CI runs
  build_catalog.py         Writes the Add-ons tab's data from the manifests
  test_addon_manifest.py   Offline tests
  <id>/
    addon.json             The manifest. The folder name is the add-on's id.
    DEPLOY.md              Package only: the runbook
    bootstrap.md           Package only: how to prepare the add-on's data
    acceptance.json        Package only: the acceptance case
    terraform/             Package only: the Terraform module
```

The tooling uses only the Python standard library, so it needs no install.

## The manifest

`addon.json` has these fields. Every field is required unless it says
otherwise, and an unknown field is an error.

| Field | What it holds |
| --- | --- |
| `schema_version` | `1`. |
| `id` | Lowercase words joined by hyphens. Must match the folder name. |
| `name` | The card's title. |
| `order` | Position on the **Add-ons** tab, from 1. No two add-ons share one. |
| `kind` | `built-in-tool` (a Foundry tool, nothing to deploy), `existing-service` (uses a service the platform already has), or `new-service` (needs a service the platform doesn't have yet). |
| `tracking` | The issue numbers that follow the add-on. |
| `card` | What the tab shows: `icon`, `summary`, `example`, `cost` (a list), `needs` (a list), `safety`, `service`, `billing`, and optionally `pilot`, `approval`, and `note`. An add-on with a `pilot` description shows a **Sample pilot** badge instead of **Not available yet**. |
| `package` | Optional. The [deployment package](#the-deployment-package). Leave it out until someone builds the add-on. |

Add-ons without a `package` are previews: the card says what the add-on would
do, cost, and need, and nothing about how to deploy it.

## The deployment package

A manifest with a `package` points at four files in its own folder. A file name
can't contain a folder, so a manifest can't point at another add-on's files or
at anything outside its folder.

| Field | What it holds |
| --- | --- |
| `runbook` | `DEPLOY.md`. It needs the sections **Plan**, **Cost and diff**, **Approval**, **Apply**, **Verify**, **Wire the agent**, and **Tear down**, and must say that a person approves the saved plan. |
| `bootstrap` | A file that says how to prepare the add-on's data or access before the first use. It can't be empty. |
| `acceptance_case` | A JSON file of cases. Each case has an `id`, a `summary`, `live`, `steps`, and `expect`. A `live` case needs a deployed add-on and may make billable calls, so it needs approval. At least one case must be offline. |
| `terraform` | `module`, the folder holding the module's `.tf` files, and `resource_types`, the only resource types its plan may create or change. |
| `approval` | Always `person-approves-saved-plan`. |
| `approval_gates` | Approvals beyond the plan: `billable-calls`, `shared-data`, and `data-handling`. |
| `roles` | Every role assignment the module may make: `role`, `role_id`, `principal_type`, and a `scope` that names a resource type and, optionally, a child collection such as `indexes`. Empty when the package grants nothing. |
| `cost_lines` | What the package adds to the bill, in the shape the [cost comparison](../cost-comparison/README.md) uses: `name` and `basis` with either `monthly_cost`, or `quantity`, `unit_rate`, and `unit`. Use `0` with a basis when the package adds nothing. Don't estimate a price that hasn't been checked. |
| `guardrails` | Must match [Fixed guardrails](#fixed-guardrails) exactly. |

## Fixed guardrails

Every package declares the same three guardrails, and the check rejects any
other value. A guardrail isn't an option. Loosening one is a code change that
reviewers see, not a manifest edit.

| Guardrail | Value |
| --- | --- |
| `public_network_access` | `disabled` |
| `local_auth` | `disabled` |
| `public_ip` | `none` |

This matches the platform's existing stance in
[Private networking](knowledge-retrieval.md#private-networking) and the
[permissions reference](permissions.md): private access only, managed identity
instead of keys, and no public resource without explicit approval.

## What the check enforces

`python addons/check_addons.py` reads every manifest and reports each problem
with the file it's in. It checks that:

- Each field has the right shape, no field is unknown, and no key appears
  twice.
- The folder name matches `id`, and no two add-ons share an `order`.
- Every file the package names exists in the add-on's folder, the runbook has
  its sections, the acceptance case names the add-on, and the module has `.tf`
  files.
- Role IDs are role definition GUIDs, resource types are valid, and the
  guardrails and plan approval are the fixed values.
- Every folder under `addons/` has a manifest.
- The Add-ons tab's data is up to date (see the next section).

CI runs the check, and its offline tests, in the **python** job of
[`validate.yml`](../.github/workflows/validate.yml). Run them yourself from the
repository root:

```powershell
python addons/check_addons.py
python -m unittest discover -s addons -p "test_*.py" -v
```

## How the Add-ons tab uses the manifests

The tab imports
[`workbench/frontend/src/add-on-catalog.json`](../workbench/frontend/src/add-on-catalog.json),
which `python addons/build_catalog.py --write` generates from the manifests.
Keeping the generated file inside `workbench/frontend` means the Lab's image
builds without the `addons` folder, and the page still makes no API call. The
check fails when the file is out of date, the way the
[catalog snapshot](../workbench/frontend/README.md#library-performance-and-log-coverage)
test does for the agent library.

## Add or change an add-on

1. Add `addons/<id>/addon.json`, or edit the existing one.
2. Run `python addons/build_catalog.py --write`.
3. Run the check and tests in [What the check enforces](#what-the-check-enforces),
   then the frontend unit tests (`npm --prefix workbench/frontend run test:unit`).

A new add-on needs no edit to a list in the frontend or in CI.

## Not done yet

- No add-on has a deployment package yet.
- The Lab has no button that deploys an add-on. A person deploys one from a
  saved, reviewed plan, outside the Lab.
- Tracked in
  [#121](https://github.com/michael-rechani/foundry-agent-accelerator/issues/121).

# Deploy knowledge search

> [!IMPORTANT]
> **This is a draft package, and nothing in it has been run against Azure.** The
> module is a copy of the grant the platform root already makes for the dev
> pilot (`knowledge_search_access` in [`terraform/`](../../terraform/README.md#knowledge-search-access)).
> Don't use both for the same index: a second assignment of the same role fails
> with `RoleAssignmentExists`. Moving the platform's grant into this module is
> tracked on [#121](https://github.com/michael-rechani/foundry-agent-accelerator/issues/121).

This package lets an agent read one index of the platform's private Azure AI
Search service. It grants **Search Index Data Reader** on that index and
nothing else. It creates no Search service, no public network access, no keys,
and no public IP address.

**A person approves the saved plan and runs the apply. An agent never applies a
plan.** An agent can draft the module, run the offline tests, and run the plan
check below. It can't approve or apply.

You need:

- The platform's Agent Service Search service, reachable from your private
  network. Its resource ID is `search_service_id`.
- The case-review agent's runtime identity, which the hosted-agent deployer
  prints as `instance_identity.principal_id`. That's `principal_id`.
- An index that already exists. [`bootstrap.md`](bootstrap.md) creates the
  sample one. The grant is scoped to the index, so do it first.

## Plan

Work from the private network, in a root that calls only this module. The check
reads every change in a plan, so a plan that also changes other resources fails
it on purpose.

```hcl
module "knowledge_search" {
  source            = "<path to addons/knowledge-search/terraform>"
  search_service_id = "<resource ID of the Agent Service Search service>"
  principal_id      = "<the agent's instance_identity.principal_id>"
  # index_name defaults to lab-sample-policy-guidance
}
```

Save the plan to a file, then check it without Terraform or Azure:

```powershell
terraform plan -out knowledge-search.tfplan
terraform show -json knowledge-search.tfplan | python addons/plan_check.py knowledge-search -
```

The check fails on public network access, IP allow lists, keys or local
authentication, public IP addresses, a role the manifest doesn't list, a role
at the wrong scope, any resource type outside `terraform.resource_types`, and
anything it can't tell until apply. It approves nothing. Never commit
`knowledge-search.tfplan` or its JSON.

## Cost and diff

This package adds no charge. A role assignment is free, and the Search service
already exists and is already in the
[deployed budget](../../cost-comparison/scenario.deployed.json). Each lookup an
agent makes adds model tokens for at most 8,000 characters of retrieved
passages. See [Cost](../../docs/knowledge-retrieval.md#cost).

Read the saved plan with `terraform show knowledge-search.tfplan`. It must show
exactly one change:

| Field | Value |
| --- | --- |
| Action | create `azurerm_role_assignment.search_index_reader` |
| Role | Search Index Data Reader (`1407120a-92aa-4202-b7e9-c0e197c71c8f`) |
| Principal type | ServicePrincipal |
| Scope | `<search service id>/indexes/<index name>` |

Anything else, stop and ask.

## Approval

A person approves the saved plan. Before you approve, confirm that:

- The plan check passed, and you read the plan yourself.
- You approve loading the sample passages into the shared Search service (see
  [`bootstrap.md`](bootstrap.md)). That's shared data.
- You approve each live acceptance case that makes a model call. Those calls are
  billable.

Record who approved, when, and the SHA-256 of the plan file
(`Get-FileHash knowledge-search.tfplan`) on the issue that tracks the change.
Apply only that file.

## Apply

A person runs, from the private network:

```powershell
terraform apply knowledge-search.tfplan
```

Apply the saved file, not a fresh plan. Terraform refuses it if the state moved
since the plan, which is the point.

## Verify

1. `terraform plan` shows no changes.
2. Run the offline cases in [`acceptance.json`](acceptance.json).
3. Run `python hosted-agents/knowledge_index.py verify` from the private
   network. It only reads.
4. With approval for billable calls, run the live cases in
   [`acceptance.json`](acceptance.json) after you wire the agent.

## Wire the agent

The module only grants access. Turning retrieval on is a separate, approved
step: install the knowledge dependency, set `KNOWLEDGE_RETRIEVAL_ENABLED`,
`KNOWLEDGE_SEARCH_ENDPOINT` and `KNOWLEDGE_SEARCH_INDEX`, and deploy a new
agent version in a quiet window. Follow steps 5 to 7 of the
[operator rollout](../../docs/knowledge-retrieval.md#operator-rollout), and add
the live cases to the evaluation dataset.

## Tear down

1. Turn retrieval off first: redeploy the agent with the flag unset, or route
   back to the previous version.
2. Save a destroy plan and check it. A person approves it and applies it.

   ```powershell
   terraform plan -destroy -out knowledge-search-teardown.tfplan
   terraform show -json knowledge-search-teardown.tfplan | python addons/plan_check.py knowledge-search -
   ```

   The check passes a plan that deletes only the role assignment.
3. If nothing else uses the sample index, delete it with
   `knowledge_index.py remove --confirm`. That changes shared data, so it needs
   approval and the temporary operator roles from [`bootstrap.md`](bootstrap.md).

A live teardown test hasn't been run. It's tracked on
[#121](https://github.com/michael-rechani/foundry-agent-accelerator/issues/121).

# Lab diagnostics, alerts, and caching

[Home](../README.md) / [Docs](README.md) / [The Lab](../workbench/README.md) / Diagnostics, alerts, and caching

This page is part of the [Lab guide](../workbench/README.md). Read it when you
need to understand agent session reuse, trace a failed request, wire up alert
delivery or budget alerts, or see how the browser caches responses.

## In this guide

- [Agent session reuse](#agent-session-reuse)
- [Request and dependency diagnostics](#request-and-dependency-diagnostics)
- [Historical platform-input candidate](#historical-platform-input-candidate)
- [Terraform-managed alert delivery](#terraform-managed-alert-delivery)
- [Budget alerts](#budget-alerts)
- [Browser caching](#browser-caching)

## Diagnostics and caching

### Historical platform-input candidate

The manually dispatched **Check historical platform input candidate** workflow
checks the historically documented `ai-foundry/dev.tfvars.json` candidate in
the private state backend. This location comes from old issue comments and has
not been verified live. The check runs only from protected `main`, on the
private Lab runner, after `terraform-state` environment approval; it uses the
existing masked Lab configuration and GitHub OIDC identity.

The workflow makes one blob HEAD request and prints only
`candidate_platform_input=present` or `candidate_platform_input=absent`.
An unexpected or ambiguous response fails the check. It does not list blobs,
read the candidate contents or state, invoke Terraform, acquire a lease, start a
VM, or change Azure or GitHub configuration. A present result establishes only
that this candidate existed at that instant, not that it is canonical, current,
valid, or suitable for a plan. An absent result rules out only this exact
candidate at that instant; it does not rule out other locations. No live check
is implied by adding this workflow.

The separate **Compare historical platform input candidate** workflow is also
manual, main-only and approval-gated. Its workflow-owned isolated Python
bootstrap fetches four fixed source files at the exact workflow commit over
HTTPS without proxies or redirects, verifies their pinned hashes, and loads
them in memory; it does not check out the persistent workspace. A context or
source verification or loading failure stops the check with the fixed
`source_verification` category. An exception while invoking the verified module
stops it with the fixed `unexpected` category instead; neither path prints
exception details or a traceback. CI checks
the pins against the committed sources, so changes to those sources require
updating the pins.

This mitigates reuse of an existing checkout; it does not isolate a persistent
host, its Python runtime, Docker, credentials, or other same-UID processes.
The runner and its global configuration remain part of the trust boundary.
The workflow reads only the candidate and platform state into memory, and
checks their blob versions and lock metadata before and
after comparison. It requires the candidate's explicit subscription and
deployment principal to match the approved subscription and the persisted
Foundry User assignment scoped to the state-recorded project and account. It
requires the candidate's enabled jumpbox OS disk identity to match the
state-recorded jumpbox disk and the candidate's disk intent to specify
`Premium_LRS`; the state disk tier is not compared. A successful
`candidate_platform_comparison=matched` is limited to these attributes and
the observed snapshots; it does **not** establish current canonical authority,
validate all inputs, or prove that infrastructure matches desired disk intent.
Missing or ambiguous information, a mismatch, a lock or changing versions
fails closed. It does not list blobs, write Azure resources, acquire leases, or
invoke Terraform. Failure output uses generic identity pin, input mismatch,
protected state invalid, snapshot instability, read failure, secret-read review
required or unexpected categories
without revealing values. Multiple independent blockers may be reported.
Protected state failures distinguish the envelope, resource inventory, account
and project outputs, role representation, role scope mismatch, and disk
representation, without printing their contents. An unclassified state failure
remains generic.
Disk failures use fixed categories for missing or duplicate resources, instance
shape and selection, body shape, and each required nested object or identity
being absent or of the wrong type. These report shape only, never field values;
they do not diagnose disk health or establish the correct representation.
The comparison also accepts a strictly validated Terraform dynamic-value
wrapper around an object body. It rejects ambiguous wrappers and type/value
disagreement as `disk_dynamic_invalid`, then applies the same disk identity
checks; it does not compare the persisted disk tier. This representation is
supported by [AzAPI 2.12's dynamic body schema](https://github.com/Azure/terraform-provider-azapi/blob/v2.12.0/docs/resources/resource.md)
and Terraform's [instance encoding](https://github.com/hashicorp/terraform/blob/v1.16.6/internal/states/instance_object.go)
using [cty dynamic serialization](https://github.com/zclconf/go-cty/blob/v1.18.1/cty/json/marshal.go).
These sources establish a possible encoding, not the encoding of any particular
private state. Unsupported or malformed descriptors fail closed.
The secret-read category checks only whether the reference is non-null; it
does not inspect the reference or access a secret. No run is implied by adding
this workflow. A separate generic category indicates only whether a Router
override key is absent or explicitly present, including null; it does not
inspect the override or establish its Terraform-resolved value.

After stable snapshots and a successful comparison, the workflow additionally
reports `candidate_storage_inventory` and `candidate_apim_inventory` as
`present`, `absent`, or `ambiguous`. These describe active, non-deposed
`azurerm_storage_account` and `azurerm_api_management` managed instances in
the whole recorded state, including child modules; they do not include other
Terraform types that might represent the same Azure resources and never report
counts or identities. Malformed, duplicate, deposed, or otherwise
ambiguous resource or instance envelopes produce `ambiguous`, not `absent`.
`candidate_pinned_secret_read` uses the same three categories for the
candidate's optional jumpbox secret reference and its pinned-version shape;
it does not fetch a secret. The categories are also reported when the only
comparison blocker is secret-read review. Other comparison failures suppress
them, and changed or locked snapshots take precedence over all results.
An invalid internal result fails with a fixed category rather than reporting
a successful comparison without its inventory.

Inventory is a snapshot of recorded instances, not a prediction of resources or
data actions a future plan may evaluate, proof of effective permissions, or
evidence that a broader plan is safe. Provider refresh behavior, a separate
plan identity and trust boundary, and the full dependency graph remain subject
to review in #534. The paused disk-tier decision in #485 is unchanged.

### Agent session reuse

The cache holds at most 512 idle chat/agent sessions per process. Its default
10-minute window is absolute, measured from the call that created the session.
Successful follow-ups don't extend it. Capacity eviction removes the oldest
idle entry in cache insertion order, not the oldest saved conversation.

Taking a session removes it from the cache until that request completes. Two
overlapping requests for the same chat therefore can't lease the same session.
The second starts a separate session, and the last successful completion may
supply the next reusable session. Failure or cancellation discards the leased
session, not another request's successful lease. Restart, expiry, or eviction
means a cold start, not missing context, because every request still sends its
full bounded history with `store=false`. Reuse is a latency optimization, not
persistence, identity, or an authorization boundary.

`workbench_session` logs the checkout category (`hit`, `miss`, `expired`, or
`disabled`) and `cached_sessions`, the idle count **after** checkout.
`disabled` also covers requests without a chat thread, including document
reviews. A `miss` can mean a new chat, restart, eviction, or an overlapping
request, and the log can't tell you which. `workbench_session_eviction`
reports expired and capacity-evicted counts after a successful cache insertion.
These events contain no chat IDs, Foundry session IDs, agent names, or input.
They are process-local cache observations, not proof of model success or
measured cold-start savings. Use `workbench_request` for correlated outcomes.

### Request and dependency diagnostics

The backend emits JSON request metadata through the Uvicorn console logger:
server-generated correlation ID, route template, HTTP method, outcome, HTTP
status, and elapsed milliseconds. Caught Foundry/Cosmos failures include the
dependency name and exception class (`error_type`). Unexpected API failures
use `application` and return a generic HTTP 500. HTTP 5xx request events use
error severity. These are diagnostic categories, not proof of the root cause.
Elapsed time covers the whole request, not just the dependency call.
The backend doesn't log prompts, transcripts, bodies, raw URLs, headers,
credentials, exception messages, or tracebacks. API responses carry the
correlation ID, including history failures. Azure Container Apps (ACA)
console/system logs go to a dedicated Log Analytics workspace with 30-day
retention and a 0.1-GB daily ingestion cap. Workspace ingestion/query uses Azure
Monitor Private Link with public access disabled. Diagnostics use Azure
identity, not workspace shared keys. The cap can delay stopping ingestion and
isn't a hard billing limit. Retained logs and scheduled-query alerts incur Azure
charges.

Every minute the backend checks configured Foundry agents without generating
responses and performs an empty-result Cosmos query. It caches the results at
`/api/health/dependencies`. Failures return 503 without exception details.
Failed probes emit `workbench_dependency_failed` with the dependency,
exception class, and probe duration (`elapsed_ms`). A failed Foundry probe also
says which step it was in (`stage`: `token` for the managed-identity sign-in,
`read` for reading the agents) and how long each step ran (`token_ms`,
`read_ms`), so a stall can be placed before or after sign-in. Each successful
`workbench_dependencies` heartbeat logs the same timings as `foundry_ms`,
`foundry_token_ms`, `foundry_read_ms`, and `cosmos_ms`, so slow-but-passing
checks are visible too. These fields aren't in the
`/api/health/dependencies` response. Probes have no request ID because they run
outside a browser request. Every error body from the chat, history, agent, and
review APIs carries the same `request_id` as the `X-Correlation-ID` header. Use it to find a
failed API request's `workbench_request` event, and never collect submitted text
or operator keys to diagnose it. A review that ends `agent_unavailable` also logs
`review_execution_error` with the exception class (`error_type`), so a code bug
is distinguishable from an outage. The Lab logs `review_execution` only after the
final save succeeds. Otherwise it logs `review_persistence_failed` instead.
`/healthz` remains process-only, so dependency outages don't cause restart
loops. These checks verify access, not model-generation quality or full Cosmos
CRUD.

Foundry probes have been seen failing in bursts of about 3 to 45 minutes.
Foundry's own request log showed those reads held about 35 seconds and then
answered with HTTP 408, so the stall was inside Foundry rather than in this
app's connection or sign-in. The probe's 5-second read limit is deliberate, because
it reports a stall as soon as it starts. See issue #126 for the evidence.

Azure Monitor raises alerts for five failures/throttles in five minutes, three
degraded dependency samples in five minutes, and no heartbeat in 15 minutes.
Alerts are visible in Azure Monitor. Set `alert_action_group_ids` to existing
action groups to deliver notifications, or let Terraform create an email action
group as shown below. No group or recipient is added by default.
Missing-heartbeat alerts also cover stalled ingestion or quota exhaustion, but
they can't tell these apart from an application outage.

#### Check the Foundry and Cosmos DB timings

To see how the dependency checks behaved, query the Lab's Log Analytics
workspace. The query is read-only and makes no model calls. The workspace is
reachable only through Private Link and has public query access disabled, so run
it from inside the private network, such as the jump box, signed in with Azure
identity. Replace `<lab-container-app-name>` with the Lab container app's name.

This query shows, per day, the failed checks (`workbench_dependency_failed`),
the heartbeats (`workbench_dependencies`), and the p50, p95, and maximum
Foundry check time in milliseconds (`foundry_ms`):

```kusto
ContainerAppConsoleLogs
| where TimeGenerated > ago(8d)
| where ContainerAppName == "<lab-container-app-name>"
| where Log contains "workbench_dependenc"
| extend p = parse_json(extract(@"(\{.*\})", 1, Log))
| extend ev = tostring(p.event)
| summarize failed = countif(ev == "workbench_dependency_failed"), heartbeats = countif(ev == "workbench_dependencies"), p50 = percentile(todouble(p.foundry_ms), 50), p95 = percentile(todouble(p.foundry_ms), 95), maxms = max(todouble(p.foundry_ms)) by day = bin(TimeGenerated, 1d)
| order by day asc
```

Use `contains`, not `has`, for these event names. `has` doesn't split on
underscores, so it silently returns no rows. The `p50`, `p95`, and `maxms`
columns are empty for days before revision 0000038, because `foundry_ms` and the
other timing fields exist only from that revision on.

To list single checks instead, keep the query down to the `extend ev` line and
replace the `summarize` and `order` lines. For checks over 5000 ms:

```kusto
| where todouble(p.foundry_ms) > 5000
| project TimeGenerated, foundry_ms = todouble(p.foundry_ms), foundry_token_ms = todouble(p.foundry_token_ms), foundry_read_ms = todouble(p.foundry_read_ms)
| order by TimeGenerated asc
```

For failed checks with their step and timings:

```kusto
| where ev == "workbench_dependency_failed"
| project TimeGenerated, dependency = tostring(p.dependency), error_type = tostring(p.error_type), stage = tostring(p.stage), token_ms = todouble(p.token_ms), read_ms = todouble(p.read_ms), elapsed_ms = todouble(p.elapsed_ms)
| order by TimeGenerated asc
```

Only failed Foundry checks have `stage`, `token_ms`, and `read_ms`. Those columns
are empty for Cosmos DB failures.

### Terraform-managed alert delivery

Set `managed_alert_email_receivers` in your ignored Lab deployment inputs to
create one action group and attach it to all three operational alerts:

```hcl
managed_alert_email_receivers = {
  operations = "operations@example.invalid"
}
```

Replace the example address with an approved recipient before planning. Receiver
names and addresses must be nonempty and unique, ignoring letter case. The group
uses the Azure Monitor common alert schema and inherits the Lab's resource group
and tags. `managed_alert_action_group_id` returns its ID after apply.

You can also supply `alert_action_group_ids` for centrally managed groups. The
configuration combines both sets without duplicate group IDs. Existing groups
remain owned outside this state. Don't configure the same group for creation
here unless you deliberately transfer its Terraform ownership. Removing all
managed receivers plans deletion of the Lab-owned group, so review that change
before applying.

Terraform plans and state store the recipient addresses, so protect those as
well as the local inputs. Alert messages can include resource identifiers and
operational log metadata, and they're delivered outside the private application
path. Approve recipients, delivery costs, and the rollout before enabling them,
and verify delivery from the approved Azure environment. Terraform validation
doesn't prove that mail reaches an inbox. These are infrastructure health
alerts, not agent tools for sending email or performing business actions.

Run `terraform -chdir=workbench/infra validate` after backend-free provider
initialization to check configuration validity. CI runs the same validation.
Native HCL monitoring tests aren't included; review the plan for action-group
and opt-out settings, then verify delivery only in an approved Azure environment.

### Budget alerts

Azure Monitor alerts cover health, not spend. To get told about spend, set
`lab_budget` in your ignored Lab deployment inputs. Terraform then creates a
monthly Cost Management budget on the Lab resource group:

```hcl
lab_budget = {
  amount     = 150                    # Billing currency, per calendar month.
  start_date = "2026-06-01T00:00:00Z" # First day of the current or a later month.
  # contact_emails = ["finance@example.invalid"]
}
```

The budget alerts at 50%, 80% and 100% of actual spend and when spend is
forecast to reach 100%. It notifies the operational action groups described
above, plus any `contact_emails`; planning fails if it has no recipient. It
also sets `WORKBENCH_BUDGET_ALERTS_ENABLED=true`, so the Lab's **Performance**
page says a budget is configured. Budgets are free, but they only warn you. They
don't stop resources or model calls. Cost data can arrive 8 to 24 hours after
the spend. The budget covers only the Lab resource group. Foundry, Cosmos DB or
network resources in other resource groups need their own budgets. The amount
and recipients are the owner's decision, and an apply changes infrastructure,
so get approval for both. Leave `lab_budget` unset (the default) to create no
budget.

The model deployment's capacity also limits spend. On Standard and Global
Standard deployments, each capacity unit is 1,000 tokens per minute, and the
Foundry configuration in `terraform/` sets it. Requests over the limit return
HTTP 429 instead of running. For example, capacity 10 limits a deployment to
10,000 tokens per minute. The Lab tries to answer first. It checks each chat turn
against that deployment's configured limit
([Model limits](lab-configuration-and-cost.md#model-limits)) and, when the turn
would pass it, answers `busy` before calling the model. If the model rejects a
request anyway, the Lab answers `busy` too. Either way it's HTTP 429
with a `Retry-After` of 1 to 60 seconds, and it asks the visitor to wait a
minute. It doesn't report a connection problem. A Lab-side refusal logs a
`workbench_model_busy` event with the deployment, template and wait, and no
prompt text. Look for it in the Lab logs to see which deployment is the busy one.
The Lab's Performance page lists which Lab actions are billable.

### Browser caching

API responses remain `no-store`. HTML revalidates, and fingerprinted static
assets use immutable caching. Responses over 1 KB are gzip-compressed when the
browser accepts it. No transcript data is written to browser persistent
storage. The elapsed timer renders independently of the conversation
transcript.

Before real user data, add validated user identity, owner-scoped authorization
on every history operation, appropriate retention and backup policies, and
operational monitoring. Network restriction alone isn't user authentication.

## Related content

- [The Lab](../workbench/README.md)
- [Deploy the Lab](lab-deployment.md)
- [Lab configuration, storage, and cost](lab-configuration-and-cost.md)
- [Troubleshooting](troubleshooting.md)
- [Documentation index](README.md)

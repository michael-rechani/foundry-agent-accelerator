# Lab diagnostics, alerts, and caching

[Home](../README.md) / [Docs](README.md) / [The Lab](../workbench/README.md) / Diagnostics, alerts, and caching

This page is part of the [Lab guide](../workbench/README.md). It covers agent
session reuse, request and dependency diagnostics, alert delivery, budget
alerts, and browser caching.

## In this guide

- [Agent session reuse](#agent-session-reuse)
- [Request and dependency diagnostics](#request-and-dependency-diagnostics)
- [Terraform-managed alert delivery](#terraform-managed-alert-delivery)
- [Budget alerts](#budget-alerts)
- [Browser caching](#browser-caching)

## Diagnostics and caching

### Agent session reuse

The cache holds at most 512 idle chat/agent sessions per process. Its default
10-minute window is absolute, measured from the call that created the session;
successful follow-ups do not extend it. Capacity eviction removes the oldest
idle entry in cache insertion order, not the oldest saved conversation.

Taking a session removes it from the cache until that request completes. Two
overlapping requests for the same chat therefore cannot lease the same session:
the second starts a separate session, and the last successful completion may
supply the next reusable session. Failure or cancellation discards the leased
session, not another request's successful lease. Restart, expiry, or eviction
means a cold start, not missing context: every request still sends its full
bounded history with `store=false`. Reuse is a latency optimization, not
persistence, identity, or an authorization boundary.

`workbench_session` logs the checkout category (`hit`, `miss`, `expired`, or
`disabled`) and `cached_sessions`, the idle count **after** checkout.
`disabled` also covers requests without a chat thread, including document
reviews. A `miss` can mean a new chat, restart, eviction, or an overlapping
request; it cannot distinguish those causes. `workbench_session_eviction`
reports expired and capacity-evicted counts after a successful cache insertion.
These events contain no chat IDs, Foundry session IDs, agent names, or input.
They are process-local cache observations, not proof of model success or
measured cold-start savings. Use `workbench_request` for correlated outcomes.

### Request and dependency diagnostics

The backend emits JSON request metadata through the Uvicorn console logger:
server-generated correlation ID, route template, HTTP method, outcome, HTTP
status, and elapsed milliseconds. Caught Foundry/Cosmos failures include the
dependency name and exception class (`error_type`); unexpected API failures
use `application` and return a generic HTTP 500. HTTP 5xx request events use
error severity. These are diagnostic categories, not proof of the root cause.
Elapsed time covers the whole request, not just the dependency call.
It does not log prompts, transcripts, bodies, raw URLs, headers, credentials,
exception messages, or tracebacks. API responses carry the correlation
ID, including history failures. Azure Container Apps (ACA) console/system logs
go to a dedicated Log Analytics workspace with 30-day retention and a 0.1-GB
daily ingestion cap. Workspace ingestion/query uses Azure Monitor Private Link
with public access disabled. Diagnostics use Azure identity, not workspace shared
keys. The cap can delay stopping ingestion and is not a hard billing limit;
retained logs and scheduled-query alerts incur Azure charges.

Every minute the backend checks configured Foundry agents without generating
responses and performs an empty-result Cosmos query. Results are cached at
`/api/health/dependencies`; failures return 503 without exception details.
Failed probes emit `workbench_dependency_failed` with the dependency,
exception class, and probe duration (`elapsed_ms`). A failed Foundry probe also
says which step it was in (`stage`: `token` for the managed-identity sign-in,
`read` for reading the agents) and how long each step ran (`token_ms`,
`read_ms`), so a stall can be placed before or after sign-in. Each successful
`workbench_dependencies` heartbeat logs the same timings as `foundry_ms`,
`foundry_token_ms`, `foundry_read_ms`, and `cosmos_ms`, so slow-but-passing
checks are visible too. These fields are not in the
`/api/health/dependencies` response. Probes have no request ID because they run
outside a browser request. Every error body from the chat, history, agent, and
review APIs carries the same `request_id` as the `X-Correlation-ID` header. Use it to find a
failed API request's `workbench_request` event; never collect submitted text
or operator keys to diagnose it. A review that ends `agent_unavailable` also logs
`review_execution_error` with the exception class (`error_type`), so a code bug
is distinguishable from an outage. `review_execution` is logged only after the
final save succeeds; otherwise `review_persistence_failed` is logged instead.
`/healthz` remains process-only, so dependency outages do not cause restart
loops. These checks verify access, not model-generation quality or full Cosmos
CRUD.

Foundry probes have been seen failing in bursts of about 3 to 45 minutes.
Foundry's own request log showed those reads held about 35 seconds and then
answered with HTTP 408, so the stall was inside Foundry rather than in this
app's connection or sign-in. The probe's 5-second read limit is deliberate: it
reports a stall as soon as it starts. See issue #126 for the evidence.

Azure Monitor raises alerts for five failures/throttles in five minutes, three
degraded dependency samples in five minutes, and no heartbeat in 15 minutes.
Alerts are visible in Azure Monitor. Set `alert_action_group_ids` to existing
action groups to deliver notifications, or let Terraform create an email action
group as shown below. No group or recipient is added by default.
Missing-heartbeat alerts also cover stalled ingestion or quota exhaustion, but
cannot distinguish these from an application outage.

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
remain owned outside this state. Do not configure the same group for creation
here unless you deliberately transfer its Terraform ownership. Removing all
managed receivers plans deletion of the Lab-owned group, so review that change
before applying.

Recipient addresses are stored in Terraform plans and state; protect those as
well as the local inputs. Alert messages can include resource identifiers and
operational log metadata, and are delivered outside the private application
path. Approve recipients, delivery costs, and the rollout before enabling them,
and verify delivery from the approved Azure environment. Terraform validation
does not prove that mail reaches an inbox. These are infrastructure health
alerts, not agent tools for sending email or performing business actions.

Run `./workbench/test-monitoring.ps1` after provider initialization to check the
default, existing-group, managed-group, combined-group, opt-out, and
invalid-input paths. The runner copies only the monitoring configuration into an
isolated directory, without the deployment backend or tfvars. Both Terraform
providers are mocked, including test runs named `apply`; no Azure resources are
created and no mail is sent. CI runs the same checks.

### Budget alerts

Azure Monitor alerts cover health, not spend. To be told about spend, set
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
10,000 tokens per minute. When a chat request hits that limit, the Lab answers
`busy` (HTTP 429, with a `Retry-After` of 1 to 60 seconds) and asks the visitor
to wait a minute; it doesn't report a connection problem. The Lab's Performance
page lists which Lab actions are billable.

### Browser caching

API responses remain `no-store`. HTML revalidates, and fingerprinted static
assets use immutable caching. Responses over 1 KB are gzip-compressed when the
browser accepts it. No transcript data is written to browser persistent
storage. The elapsed timer renders independently of the conversation
transcript.

Before real user data, add validated user identity, owner-scoped authorization
on every history operation, appropriate retention and backup policies, and
operational monitoring. Network restriction alone is not user authentication.

## Related content

- [The Lab](../workbench/README.md)
- [Deploy the Lab](lab-deployment.md)
- [Lab configuration, storage, and cost](lab-configuration-and-cost.md)
- [Troubleshooting](troubleshooting.md)
- [Documentation index](README.md)

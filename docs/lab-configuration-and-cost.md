# Lab configuration, storage, and cost

[Home](../README.md) / [Docs](README.md) / [The Lab](../workbench/README.md) / Configuration, storage, and cost

This page is part of the [Lab guide](../workbench/README.md). It shows where each
Lab setting comes from and how a change takes effect, then what the Lab stores,
the limits it enforces, and what it costs to run.

## In this guide

- [Workspace configuration](#workspace-configuration)
- [Storage and cost](#storage-and-cost)

## Workspace configuration

`GET /api/config` supplies the visible title, selected default agent, per-agent
starter prompts, request limits, and client deadlines. The browser uses these
values; it can't raise server limits. Credentials and private connection
settings are not returned. The 15-second bootstrap deadline is browser-local
because configuration is not available yet.

The creation flow is bounded: select a prepared template, describe the job,
review and edit its name and task instructions, then explicitly confirm
publication. Preparation is deterministic template assembly, not a model-generated
agent or a conversation that edits deployed agents. There is no arbitrary
code/tool installer, live connector wizard, or in-place editor for existing
deployments.

| Setting | Authoritative source | How a change takes effect |
| --- | --- | --- |
| Job templates, draft defaults, example inputs, and fixed tool descriptions | [`agent_templates/`](../workbench/agent_templates) | Rebuild and redeploy the Lab; existing created agents do not change. |
| Created-agent name and task instructions | Reviewed creation request saved in Cosmos DB | Operator-confirmed publication captures instructions in a new named hosted agent. Later chat prompts do not edit it. |
| Created-agent runtime policy and allowed tools | [`agent_runtime`](../workbench/agent_runtime), packaged by [`agent_publisher.py`](../workbench/agent_publisher.py) | Reviewed source change and Lab rollout; existing published versions remain unchanged. |
| Creation enablement, model, and operator-key verifier | Optional Lab Terraform inputs or server environment | Operator-managed rollout; not editable in the browser. |
| Display name, description, getting-started guide, and starters | [`agents.json`](../workbench/agents.json) | Rebuild and redeploy the Lab; no agent publication needed. |
| Foundry endpoint name and expected specialist receipts | `agent` and `tools` in [`agents.json`](../workbench/agents.json) | Rebuild and redeploy the Lab to point at a separately published, tested configuration. |
| Coordinator instructions and real tools | Selected [coordinator profile](agent-profiles.md), or the base coordinator's instructions and runtime defaults | Publish and test a new coordinator version; editing the Lab catalog does not change runtime tools. |
| Specialist instructions | [Application instructions](../hosted-agents/application-review-agent/instructions.md) or [case instructions](../hosted-agents/case-review-agent/instructions.md), plus deployment configuration | Publish and test a new specialist version. |
| Visible entries, default agent, and title | Lab Terraform inputs below; local equivalents are `WORKBENCH_*` environment settings | Reviewed Lab rollout, or restart the local server. |

Deployed agent versions capture instructions and environment settings.
`AGENT_INSTRUCTIONS` overrides the runtime's default instruction file.
`SPECIALIST_CONFIG` overrides the coordinator's legacy specialist-name settings.
The Lab doesn't inspect or edit these live settings. Keep its endpoint/receipt
map aligned with the deployed profile; it isn't a second runtime tool registry.

| Configuration item | Limit or behavior |
| --- | --- |
| Optional `guidance` in `agents.json` | Contains `input`, `output`, `limits`, `delegation`, and `configuration`. Each value must be a nonempty string up to 1,200 trimmed characters. These are presentation text only. Older catalogs without guidance still load with an explicit getting-started-guide-unavailable message. |
| Optional `prompts` arrays | Accept up to six entries. Each entry has `label` up to 80 characters and `text` up to 4,000 characters. Starters use sample inputs and are never submitted just by selecting one. |
| `visible_agents` | Controls direct access. Terraform validates IDs against `agents.json`, and the backend independently validates the deployed registry. |
| `default_agent` | Must be visible. When omitted, the first `visible_agents` entry is selected. Locally, use `WORKBENCH_DEFAULT_AGENT`. |
| `workspace_title` | Defaults to `Foundry Agent Lab`, with one to 80 printable characters. Locally, use `WORKBENCH_TITLE`. It updates the visible name and browser title without renaming Azure resources. |

Rebuild the image after registry changes. Terraform title/default/visibility
changes update container environment settings through the reviewed rollout.
There is no administrative editor in the UI.

## Storage and cost

The platform's existing provisioned-throughput Cosmos DB account, named by
`cosmos_account_name`, contains a dedicated
`workbench/conversations` container. Foundry's `enterprise_memory` database is
unchanged. The Lab identity has Cosmos Data Contributor scoped to this container
only. It uses the existing private Cosmos endpoint and no account keys.

| Storage area | Configuration |
| --- | --- |
| Cosmos DB container | 400 RU/s dedicated throughput and default 30-day TTL. |
| Indexing | Review support adds a record-type index alongside agent ID and update time. Apply this additive index before deploying the review-enabled image. Transcript and evidence bodies are not indexed. Listing created agents filters on the project, which isn't indexed yet, so Cosmos DB reads every created-agent record to answer it and its request-unit cost grows with total usage. Set `index_project_path = true` in the Lab's variables to index `/project/?`. It's off by default because it changes a shared container: Cosmos DB reindexes online with no downtime, and the one-time reindex uses some of the 400 RU/s ([#188](https://github.com/michael-rechani/foundry-agent-accelerator/issues/188)). The dev Lab turned it on in October 2026: the plan was 0 to add, 1 to change, 0 to destroy, it only added `/project/?`, and the next plan showed no changes. Measured there on 3 Oct 2026 with 52 fictional records, all removed afterward: the created-agent query cost 3.12 RU with 0, 5, 20 and 50 other-project records, while the same query filtered on an unindexed field grew from 2.95 to 4.92 RU. |
| Lists and reads | Chat and review lists are paged in batches of 20. Point reads load a selected record. |
| Created-agent records | Use the existing record-type index and override TTL, because a billable runtime must not lose its registry entry by expiry. Confirmed deletion removes the saved name and instructions and retains a minimal idempotency tombstone. See [Publication, recovery, and deletion](agent-creation.md#publication-recovery-and-deletion). |

> [!WARNING]
> Live Foundry, hosted runtime, build, storage, monitoring, and model-token usage
> can incur Azure charges. A timeout, closed browser tab, or disabled creation
> setting does not stop an accepted remote mutation or hosted runtime.

The saved North Central US retail-rate assumption from the
[Azure Retail Prices API](https://prices.azure.com/api/retail/prices) is
USD 0.008/hour per `100 RU/s`. At 730 hours,
`4 * 0.008 * 730 = USD 23.36/month` for this container's throughput alone.
Confirm the applicable rate before budgeting; this is not a current quote. The
estimate covers provisioned capacity, not usage-based serverless pricing. It
excludes storage, backups, discounts, taxes, model tokens, Container Apps,
registry/builds, and existing network resources, so it is not the total Lab bill.

| Runtime area | Limit |
| --- | --- |
| Container Apps runtime | One warm 0.5-vCPU/1-GiB replica for responsiveness. Uvicorn limits connection/task concurrency to 32. |
| Agent and review execution | At most four concurrent requests and 20 requests/minute, including rejected input. Admission occurs before reading bodies or calling dependencies. Agent execution retains its 180-second deadline. |
| Per-model chat budget | Before a chat turn calls its model, the Lab checks that deployment's own limit and answers 429 `busy` if the turn would pass it. It counts requests and estimated tokens over a sliding minute. Each deployment has its own count, so a busy `gpt-5.4` doesn't block `gpt-4.1`. The limits come from the `model_limits` Terraform variable ([Model limits](#model-limits)). |
| History operations | Four concurrent requests and 60 requests/minute. History operations, including uploads and SDK retries, have a 35-second server deadline. Uploads also have a five-second deadline. The browser waits up to 45 seconds. |
| Created-agent APIs | Four concurrent requests and 120 requests/minute. New publication and deletion run one at a time. |
| Created-agent count | At most five nondeleted hosted agents by default, including unconfirmed or failed attempts. Each uses 0.5 CPU / 1 GiB and can incur hosted runtime/build costs as well as model charges. |
| Uploads and rejections | All JSON-reading endpoints use one streamed body reader with a five-second upload deadline: 32 KiB for agent setups, 64 KiB for chat/document reviews, and 512 KiB for saved conversations. It counts actual bytes, including chunked uploads, before adding each chunk to its buffer or parsing JSON. Oversized uploads return HTTP 413; slow uploads return HTTP 408. Rate-limit rejections return HTTP 429 with `Retry-After: 60`. A chat request that the Lab's per-model budget refuses, or that the model itself rejects as over its limit, also returns 429 `busy`, with a `Retry-After` hint kept between 1 and 60 seconds. Responses are size-bounded. |

## Model limits

Each model deployment has its own requests-per-minute and tokens-per-minute limit, and
the tokens limit is usually the one that runs out first. The Lab's global cap of
20 chat turns a minute doesn't know which model a turn uses, so it can say busy
too late for a small deployment and too early for a large one. The per-model budget
fixes that by checking the deployment the turn will use, before any model call.

Set the limits with the `model_limits` Terraform variable, which the Lab reads from
`WORKBENCH_MODEL_LIMITS`. The defaults are the dev tenant's published limits:

| Deployment | Requests per minute | Tokens per minute |
| --- | --- | --- |
| `gpt-5.4` | 100 | 10,000 |
| `gpt-4.1` | 50 | 50,000 |
| `gpt-5.4-mini` | 10 | 10,000 |

Replace them with your deployments' real limits and leave some headroom. Use `{}` to
turn the per-model budget off, so only the global caps apply. Terraform only passes the
numbers along. It doesn't request or change any Foundry quota.

How a turn is counted:

- A turn is admitted when the deployment has fewer requests than its limit in the last
  minute and the estimated tokens of recent turns plus this one fit its tokens limit.
  A refused turn counts toward nothing, and the answer tells the browser to try again
  after the oldest recent turn leaves the minute.
- The token estimate is per template: the largest tokens (input plus output) for one
  case in that template's [scorecard](library-scorecards.md), which is conservative
  because the average answer is smaller. A template without a scorecard uses the
  largest estimate of any template.
- A lone turn that is bigger than the tokens limit still runs when the deployment is
  idle, so one large answer is never blocked forever.
- The deployment is the one the template's work type maps to (`agent_creation_models`)
  for a library preview, and the model saved with the record for a created agent.
  Prebuilt agents and document-review runs don't have a known deployment here, so only
  the global caps apply to them.
- The counts are in memory, like every other admission limit here.

Browsers show the same friendly try-again message for a Lab `busy` as for a model's
own. The Lab's `workbench_model_busy` log event records the deployment, template and
wait, never the prompt. How many people can use the Lab at the same time hasn't been
decided, so these limits aren't tuned to a head count. They protect each model's limit.

These admission limits are process-local. Do not increase workers or replicas
without distributed controls. Reused agent sessions are also process-local; with
more replicas, a follow-up that reaches another replica starts a new session.
Closing the tab, disabling new creation, or
stopping the browser wait doesn't stop an existing hosted runtime. Retire it
explicitly.

## Related content

- [The Lab](../workbench/README.md)
- [Deploy the Lab](lab-deployment.md)
- [Lab diagnostics, alerts, and caching](lab-diagnostics.md)
- [Coordinator profiles](agent-profiles.md)
- [Documentation index](README.md)

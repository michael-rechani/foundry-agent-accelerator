# The Lab

[Home](../README.md) / The Lab

The Lab is the private browser app in `workbench/`. Use it to try the
prebuilt agents, prepare reviewed agent setups, publish baseline Microsoft
Foundry hosted agents when an operator enables creation, and save document
reviews. When you finish this guide, you'll know how to run, configure, deploy,
operate, and validate the Lab without changing the safety boundaries.

The UI title is **Foundry Agent Lab**. The private React/TypeScript UI uses a
FastAPI backend and shared Azure Cosmos DB storage.

## At a glance

| Area | What to know |
| --- | --- |
| Agent library | The opening page. Browse agent definitions by sector, industry, task, readiness, and tool mode; compare a fictional example with expected behavior; create, test, and export. |
| Guided demos | Three fictional customer stories with expected findings and human decisions. Loading a sample never automatically sends, saves, or publishes anything. |
| Agent creation | **Create agent** prepares instructions from reviewed templates. Publication is a separate operator-protected action. **Chat does not create or configure agents.** |
| Prebuilt agents | The prebuilt agents remain available. **Application and case helper** is the default visible prebuilt agent. |
| Document reviews | **Document reviews** saves one structured check per checklist item and keeps the original text beside the result. |
| Data boundary | Use fictional data only. The Lab doesn't connect to customer systems or perform business writes. |
| Access model | The current private Lab has no end-user Microsoft Entra ID sign-in or per-user authorization. |

## In this guide

- [Pages](#pages)
- [Choose one demonstration](#choose-one-demonstration)
- [Access](#access)
- [Conversations](#conversations)
- [Workspace configuration](#workspace-configuration)
- [Storage and cost](#storage-and-cost)
- [Local development](#local-development)
- [Deployment](#deployment)
- [Diagnostics and caching](#diagnostics-and-caching)
- [Related content](#related-content)

## Pages

The sidebar groups the Lab's pages into four sections, in this order: **Chat and test**, **Agent library**, **Performance and benchmarking**, and **Logging**. Every agent lives under **Agent library** > **All agents**, which has tabs for **Templates**, **Ready to use**, **Created here** (when creation is on), and **Guided demos**.

| Section | Page | What you do there |
| --- | --- | --- |
| Chat and test | **Chat** | Talk with a prebuilt or created agent, or try a library agent instantly as a preview. Switch agents from the name in the Chat header. An example task only fills in your message; you choose when to send it. |
| Chat and test | **Document reviews** | Check pasted documents against a checklist and get one saved, quoted result for each item. Not in the sidebar or Chat: open a saved-review link or `/#reviews`. |
| Chat and test | **Shared history** | Reopen chats that anyone saved. Saved chats are shared and kept for 30 days. |
| Agent library | **All agents** > **Templates** | Filter the [agent library](../docs/agent-creation.md#what-a-participant-can-do) by sector, industry, task, readiness, and tools. Each entry shows what you provide, what you get, its limits, what a person decides, a fictional example, and the expected behavior. From an entry you can create the agent, open a ready one in **Chat** with the example as an unsent draft, or download its saved record for export. |
| Agent library | **All agents** > **Ready to use** | Browse the prebuilt and ready created agents you can chat with, read what each one needs and does, and start a chat. |
| Agent library | **Create agent** | Describe a job, pick a library template, edit the name and instructions, and publish a new Foundry hosted agent on the [model that suits the job](../docs/agent-creation.md#how-the-lab-picks-a-model). Shown only when the server advertises creation; actual publication needs operator enablement. |
| Agent library | **All agents** > **Created here** | Follow publication progress, open a ready agent in **Chat**, or delete an agent with the operator key. Shown only when creation is on. |
| Agent library | **All agents** > **Guided demos** | Start with application evidence, invoice discrepancies, or case notes. Read an illustrative story, copy its fictional input, or load it into an enabled matching agent. |
| Performance and benchmarking | **Performance** | See completed and unsuccessful requests, average and 90th-percentile response time, a per-agent benchmark with average tokens, and **Token usage and cost** for this browser session. Enter your own per-1M-token rates for an estimate; the Lab ships no prices. |
| Logging | **Request log** | See each live request from this browser tab with its time, agent, outcome, elapsed time, reported tokens, and a copyable reference that matches the server's `request_id` log entry. |

**Chat** can't change an agent's instructions, tools, or model; that's a
[developer or operator task](#workspace-configuration). **Document reviews**
always uses the Lab's default agent, whichever agent you select in **Chat**.
Neither page copies work into the other.

Preparing a setup in **Create agent** doesn't call a model or create Azure
resources. Publishing is opt-in, costs money, and needs the
[operator setup](../docs/agent-creation.md#enable-publication).

**Appearance:** the palette button at the right of the header sets the theme to
**System** (follows your device, the default), **Light**, or **Dark**, with a
**Foundry**, **Orchid**, or **Lagoon** accent. The choice is saved in this
browser only; it isn't shared with other users or saved with chats.

**Presenter view:** the presentation button in the header enlarges story and
Chat text for this browser session. A loaded scenario has a compact **Demo
guide** with expected findings and a guarded **Start fresh with this example**
action. Environment notices stay available, and resetting local messages never
deletes shared records. See the [showcase guide](../docs/showcase.md).

**What gets saved:** **Chat** saves completed messages to the shared Azure
Cosmos DB database only when you choose to save. Creating a document review
saves its checklist and document text. Running a review also saves the results
and a copy of that run's input. Each created agent's setup is saved as a shared
record.

## Choose one demonstration

Start with the [demo guide](../docs/demos.md) and record findings in the
[demo handoff](../docs/demo-handoff.md). Choose one bounded scenario, not an
all-scenarios demonstration.

| Scenario | Status | What it means |
| --- | --- | --- |
| [Casework assistance](../docs/demos.md#casework-assistance) | **Available** | The source and walkthrough are included. This is not a live-validation claim. |
| [Application completeness](../docs/demos.md#application-completeness) | **Available** | The source and walkthrough are included. This is not a live-validation claim. |
| [Requirements and proposal review](../docs/demos.md#requirements-and-proposal-review) | **Preview** | This reuses the application agent and the existing criteria-and-evidence workflow. It doesn't add another agent. |

The creation jobs are grouped on the page. **General:** Document
explainer, Checklist gap finder, Form and invoice extractor, Case notes
summarizer, and Service request planner. **Healthcare and public sector:**
Medical bill reviewer, Insurance pre-approval helper, Benefits renewal helper,
Supplier invoice reviewer, Public records intake, Grant reporting checker, and
Community program brief. **Private sector:** nine jobs. The three newest
public-sector jobs and all nine private-sector jobs are marked **In progress**:
they pass offline contract and acceptance tests but aren't yet validated live.
The first four General jobs use supplied text only. The Service request
planner, the four reviewed healthcare and public-sector jobs, and two private-sector
jobs each have two **simulated read-only** lookups.
None connects to customer systems or performs business writes. See [Create and try a baseline Microsoft Foundry agent](../docs/agent-creation.md).

> [!IMPORTANT]
> Use supplied fictional inputs only. People verify evidence and make decisions.
> Model output is not an approval, award, eligibility, or permit decision.

Live model execution still incurs charges. See [Storage and cost](#storage-and-cost).

The frontend uses React 19, TypeScript, Vite, Lucide icons, and custom
Fluent-inspired CSS, not the Fluent UI component library. Neutral surfaces and
blue actions are shared across creation, **Chat**, **Document reviews**,
history, **Agent library**, performance, and the request log. Playwright covers desktop and mobile
workflows. The Python backend uses FastAPI, Pydantic validation, and async Azure
SDKs for Foundry and Cosmos DB.

## Access

Use the `private_url` Terraform output from an authorized private-network
browser. For local development, use `http://127.0.0.1:8080` after starting the
server. Local disconnected mode allows template preparation, but disables
publication, agent calls, and Cosmos access.

The Azure Container Apps environment has an internal load balancer and public
network access disabled. App-level external ingress means access from outside
the environment, within the private network. Ingress is further restricted to an
approved source subnet. Azure API Management (APIM) is not involved, and this
application exposes no public gateway API. Opt-in creation publishes named
agents inside the configured private Foundry project.

For broader internal access or a controlled internet-facing entry point, see the
[Application ingress options](../docs/ingress-access.md) guide. It covers
private origins, Domain Name System (DNS), Transport Layer Security (TLS),
authentication prerequisites, host/origin configuration, and agent-request
behavior. Neither gateway is deployed by this sample.

End-user Microsoft Entra ID sign-in is not a prerequisite for the current
private Lab. Azure resource access still uses managed identities. Restrict the
Lab to trusted operators and fictional inputs. The Lab is not a user-isolated
application.

**Keep the quick-start simple:** `WORKBENCH_MODE=private` is a shared demo,
not an authenticated team mode. No end-user app registration or Entra sign-in
is required. The Lab header and origin checks prevent cross-site browser
requests; they do not identify a user. The operator key protects publication
and deletion, not access to shared records.

An optional authenticated team mode is a future extension, not a supported
setting today. It would need both validated identities and authorization on
every record read and mutation; placing a sign-in page in front of the current
Lab would still leave records shared. Do not expose this sample to untrusted
participants or use sensitive data on the assumption that private networking
provides user isolation.

The **Shared lab** control in the header explains these limits on demand:

| Shared item | Who can act | Limits |
| --- | --- | --- |
| Saved chats | Everyone with workspace access can read, modify, and delete them. | There is no per-user authorization yet. |
| Reviews | Everyone with workspace access can read reviews and add requested information. | Reviews have no deletion control. |
| Created-agent setups | Everyone with workspace access can read the setups. | Publication and deletion require the shared operator key. This is not per-user authorization. |

The Lab has no permanent warning banner. The **Shared lab** details are
available on desktop and mobile. They are informational; they are not an access
control and they do not check that submitted data is fictional.

## Conversations

**All agents** > **Templates** is the initial view. Bookmark `/#chat` to start in Chat, `/#agents` for **Ready to use**, `/#reviews` for **Document reviews**,
`/#demos` for **Guided demos**, `/#performance`, `/#logs`, or `/#create` for the
creator when its capability is advertised. A valid saved-review
URL still opens its review directly, including after a reload. No publication or
model invocation happens merely by entering a view.

The optional [Document reviews](../docs/review-workflow.md) workflow has its own
data contract and deployment checks. You don't need it to use **Chat**.

### Navigation and views

| UI label | What it does | Important limits |
| --- | --- | --- |
| **Templates** | Lists every agent definition from `GET /api/agent-templates` with server-derived filters and live counts. | Readiness and tool mode come from the catalog; nothing claims a connected customer system. **Expected behavior** is an acceptance description, not a recorded model response. Export downloads a ready saved record for `bundle.py export-created`; there is no one-click cross-environment deployment. |
| **Guided demos** | Shows fictional stories and loads a sample into an enabled matching agent. | Expected findings are illustrative. Hidden, failed, and unavailable agents are not selectable; samples are never automatically sent. |
| **New chat** | Starts a new Chat draft for the selected agent. | It doesn't create an agent or submit a starter prompt. |
| **Create agent** | Prepares a setup from a reviewed template and, when enabled, lets an operator publish it. | Preparation is deterministic template assembly, not a model-designed agent. |
| **Created here** | Lists agents published from the Lab's creation flow. | Ready agents can be selected in **Chat**. |
| **Chat** | Sends a message to the selected prebuilt agent, ready created agent, or library preview. | A chat prompt doesn't edit tools, instructions, or runtime configuration. |
| **Agent switcher** | Opens from the agent name in the Chat header. Search and switch between **Ready agents** and **Library previews** without leaving Chat, or choose **Browse the full library**. | Switching keeps your unsent draft. Agents marked **In progress** pass offline tests but aren't validated live. |
| **Library preview** | Runs a library definition directly on the Lab's model deployment, without publishing an agent. Start one from the switcher or from a library entry's **Test** tab (**Try it now in Chat**). | Private mode only, and only when `WORKBENCH_LIBRARY_PREVIEW_ENABLED` isn't `false` and a creation model is configured. Uses the definition's instructions and its simulated read-only lookups; tool loops are bounded. Preview chats can't be saved to **Shared history**. Each message calls the model and may incur cost. |
| **Document reviews** | Saves and runs checklist-based reviews. | Chat messages and review results don't copy between views automatically. |
| **Shared history** | Lists, reopens, and deletes saved conversations. | Everyone with workspace access can read, modify, and delete saved conversations. |
| **Ready to use** | Lists only enabled prebuilt agents and ready created agents. | Hidden agents can't be invoked directly through the Lab API. |
| **Performance** | Shows browser-session request counts, average and 90th-percentile latency, a per-agent benchmark, and reported token totals with an optional estimate from rates you enter. | It excludes local preview calls, clears on refresh, and isn't a fleet-wide metric or model-quality score. Replies without reported tokens are counted as **Not reported**, never zero. Rates stay in this browser; the estimate prices cached input at the full rate and isn't invoiced spend. |
| **Token counts** | Each reply shows its reported tokens next to its elapsed time, with input, cached, output, and reasoning counts under **Execution details**. Library previews add up every model call in their tool loop. | Counts come from the answering agent's response; a coordinator's count may not include the specialists it calls. Saved chats keep the counts as stored, unverified values. |
| **Request log** | Lists this tab's live requests with outcome, elapsed time, and the server `request_id` reference. | It doesn't store message text, excludes local preview calls, and clears on refresh. It isn't the server log. |

### Prebuilt and created agents

| Agent or entry | Availability | Behavior |
| --- | --- | --- |
| **Application and case helper** (`customer-review`, formerly Guided review) | Default visible prebuilt agent. | A coordinator. It hands the task to the **Application checker** or **Case notes summarizer** specialist, then returns the findings. |
| **Application and case helper (base setup)** (`review-coordinator`, formerly Review planning) | Visible only when enabled. | A developer variant of the coordinator. It uses the same specialists through different tool names and does not add capabilities. |
| **Application checker** | Visible only when enabled. | The application specialist on its own. It does the check itself and calls no other agents. |
| **Case notes summarizer** | Visible only when enabled. | The case-notes specialist on its own. It writes the summary itself and calls no other agents. |
| Ready created agents | Listed under **Ready to use** and managed under **Created here**. | They can be selected in **Chat** after publication is ready. |

Each catalog card is marked **Prebuilt agent** or **Created in this Lab**. Its
**Developer setup details** name its role: **Coordinator: hands off to
specialists**, **Coordinator: developer variant**, or **Specialist: works on its
own**. If agent creation isn't turned on, the catalog says so and offers only the
existing agents.

Configure `visible_agents` in Terraform or `WORKBENCH_VISIBLE_AGENTS` locally to
change the prebuilt agent catalog that the Lab exposes. **Ready to use** lists only
enabled entries.

**Developer setup details** shows unchanged catalog IDs, runtime names, expected
tool bindings, and configuration sources. These details describe configured
capabilities, not observed execution. Each answer with receipts shows a compact
handoff timeline (**You asked** → answering agent → each step with
**Verified**, **Unverified**, or **Stored / not reverified** → **You check the
findings**). A step names the specialist only when the receipt targets a
different agent, and the answering agent is then labeled **Coordinator**. A
created agent's lookups against its own runtime name appear as **Tool call**
steps under an **Agent** label, not as a handoff. The timeline uses the same
verification state as the collapsed **Execution details** receipts, and answers
without receipts show no timeline. A verified receipt only shows that the
expected target was called; it doesn't prove the findings are correct. Check
response execution details and receipts; stored receipts are not reverified.

### Starters and guidance

| UI label | What it does |
| --- | --- |
| **Review an application** | Fills the composer with a fictional application-checking task. |
| **Summarize case notes** | Fills the composer with a fictional case-notes task. |
| **Compare a proposal (preview)** | Fills the composer with a fictional requirements/proposal comparison. |
| **Help me get started** | Asks what to supply and what the selected agent will do. It doesn't explain how to create an agent. |
| **About this agent** | Stays available in the Chat header, including during a conversation. It explains what to give the agent, what to expect, how it works, and what it won't do. |

Starter prompts fill the composer without submitting. The user must choose
**Send**.

### Saving, retention, and receipts

| Item | Saved? | How long | Notes |
| --- | --- | --- | --- |
| Unsaved draft | No. | Browser memory only. | Browser navigation warns about unsaved work where supported. It can't prevent data loss from a browser crash or forced close. |
| Saved conversation | Yes, after the user selects the Save icon. | Expires 30 days after its last update. | Saving is explicit, not automatic. |
| Export | Download only. | User-controlled. | Export includes completed exchanges and the current draft. |
| Saved/read receipt flags | Yes, with verification flags cleared. | Same as the conversation. | Reopened receipts and their handoff timeline steps display `Stored / not reverified`. Live response receipts are checked separately against correlated tool calls and expected targets. |

Deletion and time to live (TTL) remove active documents. The account's backup
retention is separate and isn't immediate secure erasure. Foundry requests use
`store=false`; Cosmos persistence is independently controlled by the explicit
Save command. Stored transcripts and receipts are editable workspace data, not
an immutable audit trail.

### Limits and request behavior

| Limit | Value | Behavior |
| --- | --- | --- |
| Saved conversation size | Up to 11 completed exchanges and a 512 KiB save-request limit. | Optimistic ETag checks reject conflicting updates. The shared partition is for a small prototype, not a multi-tenant design. |
| Model request context | Up to 10 prior exchanges plus the new question. | The request is bounded by 60,000 characters and a 64 KiB JSON request. Saving a transcript doesn't increase the model-context limit. |
| Truncation | None. | The Lab doesn't silently truncate or summarize input. |
| Composer height | Up to 240 pixels or 25% of viewport height. | **Conversation limits** shows Unicode characters, UTF-8 JSON bytes, and completed replies. Warnings identify the exhausted limit. |
| History wait | Browser waits up to 45 seconds. | A timed-out history request doesn't clear local work. An interrupted save may have completed remotely; check **Shared history** before repeating it. |
| Stop waiting | Browser wait only. | Cancellation doesn't guarantee remote agent execution stopped. Requests are not automatically retried. |
| Agent session reuse | Up to 10 minutes per chat and agent. | Follow-ups in the same chat reuse that chat's Foundry agent session, which skips the cold start of a new sandbox. The browser sends a random chat ID, and the Foundry session ID stays in server memory until the window ends or the Lab restarts. A new, reopened, or continued chat starts a new session, and a failed request discards its session. Reuse doesn't carry history: the browser still sends the bounded conversation each turn. A reused session stays on the agent version that created it, so a newly deployed version applies to new chats or after the window ends. Locally, set `WORKBENCH_SESSION_REUSE_SECONDS` from 0 to 3600; `0` turns reuse off. Document reviews don't reuse sessions. |

Save state and expandable **Conversation limits** appear after the first reply, or
earlier when a draft reaches half of a limit. They don't add status rows to an
empty chat.

### Continue in new chat

**Continue in new chat** previews an editable draft from the last exchange and
any unsent follow-up. Earlier exchanges are not carried over. Previous output is
labeled unverified context, not a verified receipt.

Confirming starts an empty conversation with that draft. It doesn't submit the
draft or alter saved history. Cancel preserves the original conversation. Save
or export unsaved source messages first.

### Configuration loading

Configuration loads with a 15-second bootstrap deadline and an explicit
**Retry** action. Invalid configuration disables execution. Retrying preserves
any typed draft. Review deadline expiry and user cancellation have distinct
messages and performance outcomes. Neither automatically retries a model
request.

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
| Job templates, draft defaults, example inputs, and fixed tool descriptions | [`agent_templates.py`](agent_templates.py) | Rebuild and redeploy the Lab; existing created agents do not change. |
| Created-agent name and task instructions | Reviewed creation request saved in Cosmos DB | Operator-confirmed publication captures instructions in a new named hosted agent. Later chat prompts do not edit it. |
| Created-agent runtime policy and allowed tools | [`agent_runtime`](agent_runtime), packaged by [`agent_publisher.py`](agent_publisher.py) | Reviewed source change and Lab rollout; existing published versions remain unchanged. |
| Creation enablement, model, and operator-key verifier | Optional Lab Terraform inputs or server environment | Operator-managed rollout; not editable in the browser. |
| Display name, description, getting-started guide, and starters | [`agents.json`](agents.json) | Rebuild and redeploy the Lab; no agent publication needed. |
| Foundry endpoint name and expected specialist receipts | `agent` and `tools` in [`agents.json`](agents.json) | Rebuild and redeploy the Lab to point at a separately published, tested configuration. |
| Coordinator instructions and real tools | Selected [coordinator profile](../docs/agent-profiles.md), or the base coordinator's instructions and runtime defaults | Publish and test a new coordinator version; editing the Lab catalog does not change runtime tools. |
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
| Optional `prompts` arrays | Accept up to six entries. Each entry has `label` up to 80 characters and `text` up to 4,000 characters. Starters use fictional inputs and are never submitted just by selecting one. |
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
| Indexing | Review support adds a record-type index alongside agent ID and update time. Apply this additive index before deploying the review-enabled image. Transcript and evidence bodies are not indexed. |
| Lists and reads | Chat and review lists are paged in batches of 20. Point reads load a selected record. |
| Created-agent records | Use the existing record-type index and override TTL, because a billable runtime must not lose its registry entry by expiry. Confirmed deletion removes the saved name and instructions and retains a minimal idempotency tombstone. See [Publication, recovery, and deletion](../docs/agent-creation.md#publication-recovery-and-deletion). |

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
| History operations | Four concurrent requests and 60 requests/minute. History operations, including uploads and SDK retries, have a 35-second server deadline. Uploads also have a five-second deadline. The browser waits up to 45 seconds. |
| Created-agent APIs | Four concurrent requests and 120 requests/minute. New publication and deletion run one at a time. |
| Created-agent count | At most five nondeleted hosted agents by default, including unconfirmed or failed attempts. Each uses 0.5 CPU / 1 GiB and can incur hosted runtime/build costs as well as model charges. |
| Uploads and rejections | All JSON-reading endpoints use one streamed body reader with a five-second upload deadline: 32 KiB for agent setups, 64 KiB for chat/document reviews, and 512 KiB for saved conversations. It counts actual bytes, including chunked uploads, before adding each chunk to its buffer or parsing JSON. Oversized uploads return HTTP 413; slow uploads return HTTP 408. Rate-limit rejections return HTTP 429 with `Retry-After: 60`. Responses are size-bounded. |

These admission limits are process-local. Do not increase workers or replicas
without distributed controls. Reused agent sessions are also process-local; with
more replicas, a follow-up that reaches another replica starts a new session.
Closing the tab, disabling new creation, or
stopping the browser wait doesn't stop an existing hosted runtime. Retire it
explicitly.

## Local development

Requires Node 24 and Python 3.14. See the
[tool versions and upgrade expectations](../README.md#tool-versions-and-upgrades);
these disconnected checks need neither Azure sign-in nor `azd`.

```powershell
npm --prefix workbench/frontend ci
npm --prefix workbench/frontend run build
python -m pip install -r workbench/requirements.txt
python -m uvicorn app:create_app --factory --app-dir workbench --host 127.0.0.1 --port 8080 --no-access-log
```

Vite writes compiled assets to `workbench/static`, which FastAPI serves. Fonts
are local. The browser has no Content Delivery Network (CDN) dependencies or
Azure credentials. The optional operator key is held in memory only for creation
or deletion requests. Markdown doesn't render raw HTML, external images, or
clickable external links.

```powershell
python -m pip install -r workbench/requirements.txt -r workbench/agent_runtime/requirements.txt
python -m unittest discover -s workbench -p 'test_*.py' -v
npm --prefix workbench/frontend run lint
npm --prefix workbench/frontend run format:check
npm --prefix workbench/frontend exec -- playwright install chromium
npm --prefix workbench/frontend test
./workbench/test-deployment-inputs.ps1
./workbench/test-private-checks.ps1
```

Infrastructure initialization and validation are separate deployment steps. The
local application checks do not require access to the remote state backend.

## Deployment

Run the following steps from the repository root in one PowerShell session. Stop
if any command fails. Terraform deploys the Lab infrastructure and selects its
image. Image building and runtime smoke tests are separate, explicit steps.

### 1. Confirm prerequisites and state ownership

Require an existing Foundry project and tested agent, authenticated Azure access,
Terraform 1.16.4, and an approved private-network path to the backend and
workload. The state account and blob container must already exist. Ensure the
executing identity has the necessary resource, role-assignment, and
state-container access.

If the runner is a virtual machine using its managed identity, grant any
temporary roles before starting it. The instance metadata service caches tokens
for up to 24 hours, and tokens issued before a new grant can keep failing with
`AuthorizationFailed`. After a late grant, deallocate and start the runner
before retrying. Remove temporary grants once the rollout is verified.

Infrastructure uses a separate Azure Storage backend key,
`ai-foundry/workbench-dev.tfstate`, never the platform infrastructure key
`ai-foundry/dev.tfstate`. The backend uses Microsoft Entra ID and Azure CLI
authentication with blob-lease locking. Shared-key access is disabled. The
existing account enforces HTTPS/TLS 1.2, encryption, versioning, 90-day blob
soft-delete, and seven-day container soft-delete. Public network access is now
disabled. Do not reopen the shared account's firewall.

For an existing local deployment, use `init -migrate-state -backend-config=backend.hcl`
only after checking that the target key is unused. Confirm copying existing
state; never start empty. Compare lineage and managed resource IDs before and
after. Preserve protected local backups. State and plans must never be committed.
Restrict state access and review inherited Azure role-based access control
(RBAC) separately.

Execute Terraform through the approved private-network path. Existing
installations must use the resource addresses declared in the configuration.
One-time ownership scripts are not part of the sample. Stop if a plan tries to
recreate existing resources or destroy an older owner; resolve that
installation's state separately.

Necessary secrets belong in Azure Key Vault and must not enter normal Terraform
attributes. Lab runtime access is keyless managed identity. Cosmos transcripts
remain sensitive operational data, not vault secrets. Use keyless Azure Resource
Manager (ARM) resource reads and preserve historical backups under their
retention policy.

### 2. Configure and initialize

Create or review the local `workbench/infra/dev.tfvars` using
[dev.tfvars.example](infra/dev.tfvars.example). Replace example identifiers with
your actual deployment settings; never overwrite a working environment blindly.
Create or review the ignored local `workbench/infra/backend.hcl` using
[backend.hcl.example](infra/backend.hcl.example). Replace the placeholders with
the intended account, subscription, container, and separate Lab state key. Keep
the existing state key for an established deployment; do not edit the tracked
example to store environment configuration.

**Start from the canonical inputs, not an old local copy.** A stale
`dev.tfvars` can plan to turn off agent creation, drop the creation-key secret,
or destroy the alert action group. Keep one complete inputs file (everything
except `image_digest`) next to the Lab's state blob with the same private access,
for example `<state-key-prefix>/workbench-dev.tfvars`, and download it before
each plan:

```powershell
az storage blob download --auth-mode login --subscription '<state-subscription-id>' --account-name '<state-account>' --container-name '<state-container>' --name '<state-key-prefix>/workbench-dev.tfvars' --file workbench/infra/dev.tfvars
```

After a change to the inputs, upload the file again. A plan with only a new
`image_digest` should show `1 to change, 0 to destroy`. The inputs can hold alert
email addresses, so never commit them.

```powershell
terraform -chdir=workbench/infra init -backend-config=backend.hcl
terraform -chdir=workbench/infra validate
```

For a deliberate existing-state migration, use
`terraform -chdir=workbench/infra init -migrate-state -backend-config=backend.hcl`
instead of plain init, following the preservation checks above.

### 3. Bootstrap only a new Lab

Skip this step if the Lab already exists. If its registry does not exist yet,
create a foundation-only plan:

```powershell
$plan = Join-Path $env:TEMP ("ai-foundry-lab-bootstrap-" + [guid]::NewGuid().ToString("N") + ".tfplan")
terraform -chdir=workbench/infra plan -var-file=dev.tfvars -var=bootstrap_only=true "-out=$plan"
terraform -chdir=workbench/infra show "$plan"
```

Review the foundation resources and costs. Only after approval, use the apply
and cleanup block in step 6 on this plan, then continue to step 4. Bootstrap
omits the app; it does not deploy a usable UI. **Never use bootstrap mode
against an existing app.** The `prevent_destroy` guard blocks accidental app
destruction. Do not persist `bootstrap_only=true` into the normal deployment
configuration.

### 4. Build and select an immutable image

`build.ps1 -Private` stages only allowlisted source files, excluding local
dependencies, state, plans, and environment files. The Premium Azure Container
Registry (ACR) has public access and admin credentials disabled. The private
build uses the local Linux Docker engine on the current authorized
private-network runner, such as a jumpbox or continuous integration (CI) agent.
Install Docker with Linux-container support, or Podman with a `docker` command that points to it, and Azure CLI. Authenticate with an
authorized identity, preferably managed identity, and provide registry-scoped
push/pull permission. Both the runner and Docker engine need private DNS and
routing to ACR, plus access to the base-image and package sources.

The helper logs Docker into ACR using Azure CLI; use the runner's approved
Docker credential storage. It validates the image as its non-root user before
pushing, checks the registry's tag digest against the local build (Podman recompresses layers on push, so for Podman it compares the pushed image's config digest with the local image ID), then verifies
a pull by immutable digest. Subscription, registry, and release tag must be
supplied explicitly. Use a unique tag and do not overwrite it during
verification. The helper does not create virtual machines, grant roles, or
upload remote commands. Without `-Private`, the helper uses ACR Tasks, which
requires an explicitly public registry; see the fallback below.

Run `./workbench/test-build.ps1` from the repository root to check staging and
success/failure handling with mocked Azure CLI and Docker commands. It does not
contact Azure or build an image. A real build still requires the private runner
and the push/pull verification below.

Both Docker stages and the frontend CI container use immutable base-image
digests. Refresh these deliberately and rebuild for security updates. Pinning
prevents silent changes, but does not patch vulnerabilities. Python transitive
dependencies still resolve during builds, so this is not a byte-for-byte
reproducible build guarantee.

```powershell
./workbench/build.ps1 -Private -Subscription '<workload-subscription-id>' -Registry '<registry-name>' -Tag '<unique-release-tag>'
```

Replace every placeholder and run from the approved private-network environment.
Require a successful build, push, and verified pull. Record the returned digest
and the prior recovery image. Set `image_digest` in local
`workbench/infra/image.auto.tfvars` using
[image.auto.tfvars.example](infra/image.auto.tfvars.example). Mutable tags are
not accepted as deployment inputs.

**No private Docker engine?** ACR Tasks cannot reach the private registry,
because Tasks is not an ACR trusted service, but registry import is. If briefly
holding the sample source and image in an authenticated public-endpoint
registry is acceptable, build there and import by digest:

1. Create a temporary Basic registry with admin user and anonymous pull
   disabled, and tag it as temporary.
2. Run `./workbench/build.ps1` without `-Private` against the temporary
   registry, then record the digest with `az acr repository show`.
3. Validate the image as its non-root user with `az acr run`. Give the step
   `entryPoint: python` and `workingDirectory: /app`; ACR Tasks defaults to
   `/workspace`.
4. Copy it into the private registry by digest:
   `az acr import --name '<registry-name>' --registry '<temporary-registry-resource-id>' --source 'workbench@<digest>' --image 'workbench:<unique-release-tag>'`.
5. Confirm the digest from the private-network runner, then delete the
   temporary registry.

### 5. Plan and review the image rollout

```powershell
$plan = Join-Path $env:TEMP ("ai-foundry-lab-" + [guid]::NewGuid().ToString("N") + ".tfplan")
terraform -chdir=workbench/infra plan -var-file=dev.tfvars "-out=$plan"
terraform -chdir=workbench/infra show "$plan"
```

Stop on failure. Verify the exact image digest and review every infrastructure
action. A normal image-only update should not recreate shared resources. For
first-time review support, verify the additive Cosmos DB index is ready before
promoting the review-enabled image. Reject unrelated changes.

### 6. Apply the approved plan and clean up

Applying a saved plan has no additional Terraform approval prompt. Run this
block only after approving the plan from step 3 or step 5:

```powershell
try {
	terraform -chdir=workbench/infra apply "$plan"
	if ($LASTEXITCODE -ne 0) { throw "Apply failed; inspect state before replanning" }
} finally {
	Remove-Item -LiteralPath $plan -Force -ErrorAction SilentlyContinue
}
```

For a failed or abandoned plan, run
`Remove-Item -LiteralPath $plan -Force -ErrorAction SilentlyContinue` as well.
Plans may contain sensitive values; do not keep them as deployment history.
Preserve Terraform state, state backups, and source configuration. Generate a
fresh reviewed plan for a retry.

### 7. Verify the deployed application

```powershell
terraform -chdir=workbench/infra output -raw private_url
```

Confirm the intended revision and immutable image are ready before using this
URL. From authorized private-network access, run the fictional runtime check:

```powershell
./workbench/test-private.ps1 -BaseUrl '<verified-private-url>'
```

Replace the URL placeholder with the Terraform output. The check uses the
deployed default agent and its configured specialist bindings. Review the
fictional application prompt before using it against a different agent profile.
It makes one billable fictional request and requires a verified specialist
receipt when that agent has specialist tools, not just a nonempty answer.

The same check verifies Cosmos create, read, conditional update, stale-ETag
rejection, and deletion of its own fictional conversation. Use `-SkipAgentCall`
for storage checks without model generation. For read-only configuration and
cached dependency checks:

```powershell
python workbench/verify_private.py --base-url '<verified-private-url>'
```

The verifier also supports `--loopback` inside the existing Lab container. This
can check the runtime through approved container-console access without starting
a virtual machine or changing ingress. Transfer only the reviewed helper through
the approved administration path and remove that temporary artifact afterward.
Verification scripts are not bundled in the runtime image. Loopback results
explicitly say that browser ingress was **not** verified. Neither path
establishes model quality.

Require successful private HTTPS, agent execution, and Cosmos CRUD verification.
An infrastructure apply alone is not an application acceptance test. For the
new workflow, also complete [review delivery checks](../docs/review-workflow.md#delivery-checks),
including explicit clarification, resume, and prior-snapshot verification.
Interrupted reviews also offer [explicit recovery](../docs/review-workflow.md#recover-an-interrupted-review)
from saved run input after a recovery window. Recovery requires cost
confirmation, preserves the earlier attempt, and consumes another run; it does
not turn the process-local task into a durable worker or retrieve an earlier
remote result.

Private runtime settings are managed by Terraform: `WORKBENCH_MODE`,
`WORKBENCH_VISIBLE_AGENTS`, `WORKBENCH_DEFAULT_AGENT`, `WORKBENCH_TITLE`, exact
host/origin allowlists, Foundry project endpoint, Cosmos endpoint, and
managed-identity client ID. Cosmos data-plane resources are provisioned by
Terraform, never created by the runtime.

The private smoke test creates a fictional test conversation, verifies agent
invocation and Cosmos create/read/update/delete, and deletes the test
conversation afterward. Browser tests use controlled API responses and do not
replace this deployment check.

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
exception class, and probe duration. They have no request ID because they run
outside a browser request. Use the response's `X-Correlation-ID` to find a
failed API request's `workbench_request` event; never collect submitted text
or operator keys to diagnose it.
`/healthz` remains process-only, so dependency outages do not cause restart
loops. These checks verify access, not model-generation quality or full Cosmos
CRUD.

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

### Browser caching

API responses remain `no-store`. HTML revalidates, and fingerprinted static
assets use immutable caching. No transcript data is written to browser
persistent storage. The elapsed timer renders independently of the conversation
transcript.

Before real user data, add validated user identity, owner-scoped authorization
on every history operation, appropriate retention and backup policies, and
operational monitoring. Network restriction alone is not user authentication.

## Related content

- [Documentation index](../docs/README.md)
- [Create and try a baseline Microsoft Foundry agent](../docs/agent-creation.md)
- [Document reviews](../docs/review-workflow.md)
- [Private deployment runbook](../docs/private-deployment.md)
- [Application ingress options](../docs/ingress-access.md)

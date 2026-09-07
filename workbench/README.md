# AI Foundry Lab

Private, chat-first React/TypeScript UI with a FastAPI backend, Cosmos persistence,
and an optional evidence-review workflow.

The frontend uses React 19, TypeScript, Vite, Lucide icons, and custom
Fluent-inspired CSS, not the Fluent UI component library. Neutral surfaces and
blue actions are shared across Chat, evidence reviews, history, catalog, and performance.
Playwright covers desktop and mobile workflows. The Python backend uses FastAPI,
Pydantic validation, and async Azure SDKs for Foundry and Cosmos DB.

## Access

Use the `private_url` Terraform output from an authorized private-network browser.
For local development, use http://127.0.0.1:8080 after starting the server below.
Local disconnected mode disables agent calls and Cosmos access.

The Container Apps environment has an internal load balancer and public network access disabled. App-level external ingress means access from outside the *environment*, within the private network; ingress is further restricted to an approved source subnet. APIM is not involved and no agent APIs are published by this application.

## Conversations

Chat is the default view. The optional [evidence-review workflow](../docs/review-workflow.md)
has its own data contract and deployment checks; it is not required to use Chat.

- Customer review is the only directly available agent by default. Its specialist bindings still work. Configure `visible_agents` in Terraform or `WORKBENCH_VISIBLE_AGENTS` locally to change the catalog; hidden agents cannot be invoked directly through the workbench API.
- Send a message, then use the Save icon to save completed exchanges. Saving is explicit, not automatic. Unsaved drafts remain only in browser memory. Export includes completed exchanges and the current draft. Browser navigation warns about unsaved work where supported; it cannot prevent data loss from a browser crash or forced close.
- Shared history lists, reopens and deletes saved conversations. **Everyone with workspace access can read, modify and delete these conversations.** There is no per-user authorization yet. Use synthetic data only.
- Saves expire 30 days after their last update. Deletion and TTL remove active documents; the account's backup retention is separate and is not immediate secure erasure.
- One conversation document holds up to 11 completed exchanges, with a 512 KiB save-request limit. Optimistic ETag checks reject conflicting updates. The shared partition is deliberately for a small prototype, not a multi-tenant design.
- Model requests contain up to 10 prior exchanges plus the new question, bounded by 60,000 characters and a 64 KiB JSON request. No silent truncation or summarization occurs. Saving a transcript does not increase the model-context limit.
- Foundry requests use `store=false`; Cosmos persistence is independently controlled by the explicit Save command. Stored transcripts and their receipts are editable workspace data, not an immutable audit trail.
- Saved/read receipts have their client-supplied verification flags cleared. Reopened receipts display `Stored / not reverified`; live response receipts are separately checked against correlated tool calls and expected targets.
- Performance shows browser-session request counts and observed end-to-end latency. It excludes local preview calls, is cleared on refresh, and is not a fleet-wide metric or model-quality score.
- Stop waiting cancels the browser wait, not guaranteed remote agent execution. Requests are not automatically retried.
- History requests stop waiting after 45 seconds without clearing local work. An interrupted save may have completed remotely; check shared history before repeating it.
- The composer grows up to 240 pixels or 25% of viewport height. Its context budget shows Unicode characters, UTF-8 JSON bytes and completed replies; warnings identify the exhausted limit.
- Continue in new chat previews an editable draft from the last exchange and any unsent follow-up. Earlier exchanges are not carried over. Previous output is labeled unverified context, not a verified receipt. Confirming starts an empty conversation with that draft, without submitting it or altering saved history. Cancel preserves the original conversation. Save or export unsaved source messages first.
- Configuration loads with a 15-second bootstrap deadline and explicit Retry. Invalid configuration disables execution; retry preserves any typed draft. Review deadline expiry and user cancellation have distinct messages and performance outcomes. Neither automatically retries a model request.

## Workspace Configuration

`GET /api/config` supplies the visible title, selected default agent, per-agent
starter prompts, request limits and client deadlines. The browser uses these
values; it cannot raise server limits. Credentials and private connection
settings are not returned. The 15-second bootstrap deadline is browser-local
because configuration is not available yet.

- Edit `agents.json` to change display labels, descriptions, specialist bindings
	and optional `prompts` arrays. Each prompt has `label` (up to 80 characters)
	and `text` (up to 4,000 characters); up to six prompts are accepted per agent.
	Prompts use synthetic data and are never submitted just by selecting one.
- `visible_agents` controls direct access. Terraform validates IDs against
	`agents.json`, and the backend independently validates the deployed registry.
- `default_agent` must be visible; when omitted, the first `visible_agents` entry
	is selected. Locally, use `WORKBENCH_DEFAULT_AGENT`.
- `workspace_title` defaults to `AI Foundry Lab`, with one to 80 printable
	characters. Locally, use `WORKBENCH_TITLE`. It updates the visible name and
	browser title without renaming Azure resources.
- Rebuild the image after registry changes. Terraform title/default/visibility
	changes update container environment settings through the reviewed rollout.
	There is no unauthenticated administrative editor.

## Storage and Cost

The existing provisioned-throughput account `aifnd-agent-foundry-cosmosdb-7omvd` contains a dedicated `workbench/conversations` container. Foundry's `enterprise_memory` database is unchanged. The workbench identity has Cosmos Data Contributor scoped to this container only. It uses the existing private Cosmos endpoint and no account keys.

The container has 400 RU/s dedicated throughput and 30-day TTL. Review support
adds a record-type index alongside agent ID and update time; apply this additive
index before deploying the review-enabled image. Transcript and evidence bodies
are not indexed. Lists are paged in batches of 20 and point reads load a selected record.

Public retail rate retrieved 2026-09-05 UTC from the Azure Retail Prices API: North Central US, Azure Cosmos DB, RUs, `100 RU/s`, USD 0.008/hour. At 730 hours, `4 * 0.008 * 730 = USD 23.36/month` for this container's throughput. This is incremental baseline capacity, not usage-based serverless pricing. It excludes storage, backups, discounts, taxes, model tokens, Container Apps, registry/builds, and existing network resources. It is not the total workbench bill.

The app runs one warm 0.5-vCPU/1-GiB replica for responsiveness. Reviews admit at most four concurrent requests and 20 requests/minute, including rejected input. History separately admits four concurrent requests and 60 requests/minute. Admission occurs before reading bodies or calling dependencies. These limits are process-local; do not increase workers or replicas without distributed controls. Uvicorn limits connection/task concurrency to 32.

Review body uploads have a five-second server deadline. History operations, including uploads and SDK retries, have a 35-second server deadline; the browser waits up to 45 seconds. Rejections return HTTP 429 with `Retry-After: 60`. Agent execution retains its 180-second deadline. Responses are size-bounded; cancellation does not guarantee an already accepted remote mutation or model call stops.

## Local Development

Requires Node 24 and Python 3.13.

```powershell
npm --prefix workbench/frontend ci
npm --prefix workbench/frontend run build
python -m pip install -r workbench/requirements.txt
python -m uvicorn app:create_app --factory --app-dir workbench --host 127.0.0.1 --port 8080 --no-access-log
```

Vite writes compiled assets to `workbench/static`, which FastAPI serves. Fonts are local; there are no CDN dependencies or browser credentials. Markdown does not render raw HTML, external images or clickable external links.

```powershell
python -m unittest discover -s workbench -p 'test_*.py' -v
npm --prefix workbench/frontend run lint
npm --prefix workbench/frontend exec -- playwright install chromium
npm --prefix workbench/frontend test
./workbench/test-deployment-inputs.ps1
```

Infrastructure initialization and validation are separate deployment steps below;
the local application checks do not require access to the remote state backend.

## Deployment

Run the following steps from the repository root in one PowerShell session.
Stop if any command fails. Terraform deploys the Lab infrastructure and selects
its image; image building and runtime smoke tests are separate, explicit steps.

### 1. Confirm prerequisites and state ownership

Require an existing Foundry project and tested agent, authenticated Azure access,
Terraform 1.16.1, and an approved private-network path to the backend and workload.
The state account and blob container must already exist. Ensure the executing
identity has the necessary resource, role-assignment, and state-container access.

Infrastructure uses a separate Azure Storage backend key, `ai-foundry/workbench-dev.tfstate`, never the platform's `ai-foundry/dev.tfstate`. The backend uses Entra/CLI authentication and blob-lease locking; shared-key access is disabled. The existing account enforces HTTPS/TLS 1.2, encryption, versioning, 90-day blob soft-delete and seven-day container soft-delete. Public network access is now disabled. Do not reopen the shared account's firewall.

For an existing local deployment use `init -migrate-state -backend-config=backend.hcl.example` only after checking the target key is unused. Confirm copying existing state, never start empty. Compare lineage and managed resource IDs before/after. Preserve protected local backups; state and plans must never be committed. Restrict state access and review inherited Azure RBAC separately.

Execute Terraform through the approved private-network path. Existing installations
must use the resource addresses declared in the configuration. One-time ownership
scripts are not part of the sample. Stop if a plan tries to recreate existing
resources or destroy an older owner; resolve that installation's state separately.

Necessary secrets belong in Key Vault and must not enter normal Terraform
attributes. Lab runtime access is keyless managed identity. Cosmos transcripts
remain sensitive operational data, not vault secrets. Use keyless ARM resource
reads and preserve historical backups under their retention policy.

### 2. Configure and initialize

Create or review the local `workbench/infra/dev.tfvars` using
[dev.tfvars.example](infra/dev.tfvars.example). Replace example identifiers with
your actual deployment settings; never overwrite a working environment blindly.
Review [backend.hcl.example](infra/backend.hcl.example) before using it: it
contains this Lab's backend identifiers, not universally valid defaults. Configure
the intended account, subscription, container, and separate Lab state key.

```powershell
terraform -chdir=workbench/infra init -backend-config=backend.hcl.example
terraform -chdir=workbench/infra validate
```

For a deliberate existing-state migration, use
`terraform -chdir=workbench/infra init -migrate-state -backend-config=backend.hcl.example`
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
omits the app; it does not deploy a usable UI. **Never use bootstrap mode against
an existing app.** The `prevent_destroy` guard blocks accidental app destruction.
Do not persist `bootstrap_only=true` into the normal deployment configuration.

### 4. Build and select an immutable image

`build.ps1 -Private` stages only allowlisted source files, excluding local
dependencies, state, plans and environment files. The Premium registry has public
access and admin credentials disabled. The private build uses the local Linux
Docker engine on the current authorized private-network runner, such as a jumpbox
or CI agent. Install Docker with Linux-container support and Azure CLI, authenticate
with an authorized identity (prefer managed identity), and provide registry-scoped
push/pull permission. Both the runner and Docker engine need private DNS and routing
to ACR, plus access to the base-image and package sources. The helper logs Docker
into ACR using Azure CLI; use the runner's approved Docker credential storage.
It validates the image as its non-root user before pushing, then verifies a pull
by immutable digest. It does not create VMs, grant roles, or upload remote commands.
The legacy ACR Tasks path requires an explicitly public registry and is not used
by this deployment.

Both Docker stages and the frontend CI container use immutable base-image digests. Refresh these deliberately and rebuild for security updates; pinning prevents silent changes but does not patch vulnerabilities. Python transitive dependencies still resolve during builds, so this is not a byte-for-byte reproducible build guarantee.

```powershell
./workbench/build.ps1 -Private -Subscription '<workload-subscription-id>' -Registry '<registry-name>' -Tag '<unique-release-tag>'
```

Replace every placeholder and run from the approved private-network environment.
Require a successful build, push, and verified pull. Record the returned digest and the prior recovery
image. Set `image_digest` in local `workbench/infra/image.auto.tfvars` using
[image.auto.tfvars.example](infra/image.auto.tfvars.example). Mutable tags are
not accepted as deployment inputs.

### 5. Plan and review the image rollout

```powershell
$plan = Join-Path $env:TEMP ("ai-foundry-lab-" + [guid]::NewGuid().ToString("N") + ".tfplan")
terraform -chdir=workbench/infra plan -var-file=dev.tfvars "-out=$plan"
terraform -chdir=workbench/infra show "$plan"
```

Stop on failure. Verify the exact image digest and review every infrastructure
action. A normal image-only update should not recreate shared resources. For
first-time review support, verify the additive Cosmos index is ready before
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
Plans may contain sensitive values; do not keep
them as deployment history. Preserve Terraform state, state backups and source
configuration. Generate a fresh reviewed plan for a retry.

### 7. Verify the deployed application

```powershell
terraform -chdir=workbench/infra output -raw private_url
```

Confirm the intended revision and immutable image are ready before using this
URL. From authorized private-network access, run the synthetic runtime check:

```powershell
./workbench/test-private.ps1 -BaseUrl '<verified-private-url>'
```

Replace the URL placeholder with the Terraform output. This script expects the
sample's catalog, title, and limits; review those assertions for a different
configuration rather than pointing an unreviewed test at another environment.
Require successful private HTTPS, agent execution, and Cosmos CRUD verification;
an infrastructure apply alone is not an application acceptance test. For the
new workflow, also complete [review delivery checks](../docs/review-workflow.md#delivery-checks),
including explicit clarification, resume, and prior-snapshot verification.

Private runtime settings are managed by Terraform: `WORKBENCH_MODE`, `WORKBENCH_VISIBLE_AGENTS`, `WORKBENCH_DEFAULT_AGENT`, `WORKBENCH_TITLE`, exact host/origin allowlists, Foundry project endpoint, Cosmos endpoint and managed-identity client ID. Cosmos data-plane resources are provisioned by Terraform, never created by the runtime.

The private smoke test creates a fictional test conversation, verifies agent
invocation and Cosmos create/read/update/delete, and deletes the test conversation
afterward. Browser tests use controlled API responses and do not replace this
deployment check.

## Diagnostics and Caching

The backend emits JSON request metadata through the Uvicorn console logger:
server-generated correlation ID, route template, outcome, HTTP status and
elapsed milliseconds. It does not log prompts, transcripts, bodies, raw URLs,
headers, credentials or exception details. API responses carry the correlation
ID, including history failures. ACA console/system logs go to a dedicated Log
Analytics workspace with 30-day retention and a 0.1-GB daily ingestion cap.
Workspace ingestion/query uses Azure Monitor Private Link with public access
disabled. Diagnostics use Azure identity, not workspace shared keys.
The cap can delay stopping ingestion and is not a hard billing limit; retained
logs and scheduled-query alerts incur Azure charges.

Every minute the backend checks configured Foundry agents without generating
responses and performs an empty-result Cosmos query. Results are cached at
`/api/health/dependencies`; failures return 503 without exception details.
`/healthz` remains process-only, so dependency outages do not cause restart loops.
These checks verify access, not model-generation quality or full Cosmos CRUD.

Azure Monitor raises alerts for five failures/throttles in five minutes, three
degraded dependency samples in five minutes, and no heartbeat in 15 minutes.
Alerts are visible in Azure Monitor. Set `alert_action_group_ids` to existing
action groups to deliver notifications; no recipient is configured by default.
Missing-heartbeat alerts also cover stalled ingestion or quota exhaustion but
cannot distinguish these from an application outage.

API responses remain `no-store`. HTML revalidates and fingerprinted static assets
use immutable caching. No transcript data is written to browser persistent storage.
The elapsed timer renders independently of the conversation transcript.

Before real user data: add validated user identity, owner-scoped authorization on every history operation, appropriate retention and backup policies, and operational monitoring. Network restriction alone is not user authentication.
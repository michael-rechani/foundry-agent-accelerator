# Foundry Workbench

Private React/TypeScript chat UI with a FastAPI backend and Cosmos saved conversations.

## Access

Live URL, from the jumpbox browser only:

https://foundry-workbench.icyplant-54a7139a.northcentralus.azurecontainerapps.io

Local visual preview: http://127.0.0.1:8080. Preview disables agent calls and Cosmos access.

The Container Apps environment has an internal load balancer and public network access disabled. App-level external ingress means access from outside the *environment*, within the private network; ingress is further restricted to the jumpbox subnet. APIM is not involved and no agent APIs are published by this application.

## Conversations

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

## Storage and Cost

The existing provisioned-throughput account `aifnd-agent-foundry-cosmosdb-7omvd` contains a dedicated `workbench/conversations` container. Foundry's `enterprise_memory` database is unchanged. The workbench identity has Cosmos Data Contributor scoped to this container only. It uses the existing private Cosmos endpoint and no account keys.

The container has 400 RU/s dedicated throughput, 30-day TTL, and indexes only agent ID and update time. Transcript bodies are not indexed. Lists are paged in batches of 20 and point reads load a selected transcript.

Public retail rate retrieved 2026-09-05 UTC from the Azure Retail Prices API: North Central US, Azure Cosmos DB, RUs, `100 RU/s`, USD 0.008/hour. At 730 hours, `4 * 0.008 * 730 = USD 23.36/month` for this container's throughput. This is incremental baseline capacity, not usage-based serverless pricing. It excludes storage, backups, discounts, taxes, model tokens, Container Apps, registry/builds, and existing network resources. It is not the total workbench bill.

The app runs one warm 0.5-vCPU/1-GiB replica for responsiveness. One worker/replica matches its process-local four-request concurrency limit and 20 agent requests/minute limit. Do not increase replicas without revisiting those controls.

## Local Development

Requires Node 24 and Python 3.13 (local tests also passed on Python 3.12).

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
terraform -chdir=workbench/infra init
terraform -chdir=workbench/infra validate
```

## Deployment

Infrastructure has its own local Terraform state under `workbench/infra`; preserve it and do not mix it with the platform state. State and plans must never be committed. Migrate this isolated state to a secured remote backend before collaborative operations.

`build.ps1` stages only allowlisted source files for ACR Tasks, excluding local dependencies, state, plans and environment files. The Basic registry has an authenticated public endpoint and admin credentials disabled; this does not make the app public.

For a new environment, populate `infra/dev.tfvars` using `infra/dev.tfvars.example`.
An initial foundation-only deployment must explicitly set `bootstrap_only=true`.
After the registry exists, build the image and set `image_digest` using the shape
in `infra/image.auto.tfvars.example`. Normal deployments require a valid digest;
missing input fails validation. Never use bootstrap mode against an existing app.
The app's `prevent_destroy` lifecycle guard also blocks accidental destruction;
deliberate decommissioning requires a separate reviewed configuration change.

```powershell
./workbench/build.ps1 -Tag cleanup-v1
# Set image_digest in infra/image.auto.tfvars to the successful build digest.
terraform -chdir=workbench/infra plan -var-file=dev.tfvars -out=app.tfplan
# Review all proposed actions before applying.
terraform -chdir=workbench/infra apply app.tfplan
```

Private runtime settings are managed by Terraform: `WORKBENCH_MODE`, `WORKBENCH_VISIBLE_AGENTS`, exact host/origin allowlists, Foundry project endpoint, Cosmos endpoint and managed-identity client ID. Cosmos data-plane resources are provisioned by Terraform, never created by the runtime.

Run `test-private.ps1` on the jumpbox to verify real agent invocation and Cosmos create/read/conditional-update/delete. It creates only a synthetic test conversation and deletes it afterward. The deployed private API and Cosmos round trip passed this test on 2026-09-05 UTC. Browser save/reopen/follow-up behavior was separately checked with test responses at desktop/mobile sizes.

## Diagnostics and Caching

The backend emits JSON request metadata through the Uvicorn console logger:
server-generated correlation ID, route template, outcome, HTTP status and
elapsed milliseconds. It does not log prompts, transcripts, bodies, raw URLs,
headers, credentials or exception details. API responses carry the correlation
ID, including history failures. Persistent ACA log collection remains disabled;
use live console streaming for troubleshooting or separately configure an
approved collector with retention and cost limits. `/healthz` reports process
readiness, not the health of Foundry or Cosmos.

API responses remain `no-store`. HTML revalidates and fingerprinted static assets
use immutable caching. No transcript data is written to browser persistent storage.
The elapsed timer renders independently of the conversation transcript.

Before real user data: add validated user identity, owner-scoped authorization on every history operation, appropriate retention and backup policies, and operational monitoring. Network restriction alone is not user authentication.
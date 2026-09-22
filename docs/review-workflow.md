# Document reviews

[Overview](../README.md) / Document reviews

Check pasted document text against your own checklist. See what is covered,
what is missing and where documents disagree, then add information and check
again. The UI calls this **Document reviews**, formerly Evidence reviews.

Use **Chat** when you want a conversation with the selected agent. Use
**Document reviews** when you want saved results for each checklist item, the
original text beside the results, and follow-up information recorded with the
review. Neither view copies messages or results to the other automatically.

This requires a deployed Lab with Cosmos persistence and a compatible agent.
New reviews use the Lab's configured default agent, independently of the Chat
selection; an existing record keeps its saved agent ID. Creating a review creates
a shared **record**, not an agent. The local preview allows a draft only: no
model calls and no saved records.

In the API and the technical sections below, **criteria** means your checklist
items, **evidence** means the document text and additional information you
supplied, and a **finding** is the result for one checklist item. No external
document search or fact-checking is implied.

For a customer-facing walkthrough, choose [one demonstration](demos.md).
Application completeness is available in source; requirements and proposal
coverage is experimental and reuses this criteria-and-evidence contract. The
[synthetic RFP input](demo-inputs/requirements-review.json) can be pasted into the
existing fields; there is no file-import feature or new agent requirement.
Ordinary Chat remains separate and does not require this JSON schema or review
receipts.

Engagements focus on demonstration and technical validation. Integration with customer systems and production deployment require separate scoping and agreement.

## Workflow

1. Choose **New review**, enter a title and **Checklist, one item per line**,
   then paste text into **Documents to check**. **Use fictional example** fills
   a small workshop application without saving or running it. Supply up to 12
   checklist items and 12 documents. This release accepts pasted text, not file
   uploads, fetched URLs or Search retrieval.
2. Choose **Create shared review** to save the record, then **Run review** to
   call its agent. The form names the agent doing the check. The default
   Application and case helper selects its existing specialist tools; no agent
   is created, configured or deployed.
3. Read **Results** beside **Original text**. Each checklist item has exactly
   one assessment: supported, gap, or conflict. Non-gap findings require citations;
   every cited quote must match its named submitted source exactly.
   A gap means evidence is not demonstrated, not automatic noncompliance.
   Product claims are not independently verified capabilities; conflicts require
   clarification, not an invented resolution or an approval decision.
4. If **More information needed** appears, enter the requested details and choose
   **Save added information**. This saves a revision without invoking the agent.
   **Review again** starts a new bounded call over the checklist and all
   accumulated text, not a continuation of a persisted model session. Until
   then, the UI labels the displayed results as belonging to the previous run.
5. Reopen a review from the inbox or its URL fragment. Inspect earlier run snapshots
   and export the record as JSON. Chat remains a separate workspace view.

| Result label | In plain language |
| --- | --- |
| **Supported** | Your text backs up this checklist item. It does not prove the text is true. |
| **Gap** | There is not enough information. It does not mean the application has failed. |
| **Conflict** | Statements disagree. A person needs to clarify which one applies. |

A matching quote shows what a document says, not whether it is true. These
results do not approve applications or make business decisions. The UI puts
this explanation beside the results and keeps storage details in **How to read
results and where your work is saved**, rather than repeating warning panels.

The structured-review prompt limits clarification to gaps or conflicts in the
supplied criteria and asks for no questions when every finding is supported.
Later evidence must be considered before asking again; a human review notice does
not add documentation or verification requirements. Model compliance still needs
live acceptance testing. The server does not discard returned questions to force
a completed status.

## Execution and persistence

This workflow is distinct from the chat request path in the
[architecture guide](architecture.md). The background task below lives inside
the FastAPI process; it is not a queue, separate worker service, or durable job.

![Draw.io review lifecycle showing conditional start, persistence before HTTP 202, agent result validation, effective outcomes, and clarification resume](images/review-lifecycle.svg)

[Open full-size SVG](images/review-lifecycle.svg) · [Editable draw.io source](images/review-lifecycle.drawio)

The numbered steps distinguish browser actions, server validation, Cosmos writes,
and the process-local task. In the diagram, `/execute` abbreviates
`POST /api/review-runs/{id}/execute`. Evidence is appended through
`POST /api/review-runs/{id}/evidence`. The server snapshots the complete input
before starting an attempt, then records validated findings or an error code.
No model text is allowed to supply the record's status, receipt flags, or events.

Precondition conflicts return HTTP 409 without scheduling another execution.
The final write uses the execution's ETag; the application does not blindly
overwrite a changed document. A failed status poll pauses browser updates, not
the server task. Refresh restarts polling without submitting another model call.

Implementation: [review API and task lifecycle](../workbench/review_runs.py),
[result validation](../workbench/reviews.py),
[browser polling and resume](../workbench/frontend/src/ReviewWorkspace.tsx).

## Review states

| State | Meaning | Allowed next action |
| --- | --- | --- |
| `draft` | Validated input, either newly created or extended with evidence | Explicit Run review / Review again with a matching ETag and remaining run budget |
| `running` | Input snapshot saved and a matching local task exists | Poll or reopen; do not submit another start |
| `waiting_input` ("Needs information") | A validated, saved result asks for more information | Append evidence with a matching ETag, fewer than four runs, and room within content limits; returns to `draft` |
| `completed` ("Results saved") | Validated findings with no questions and a confirmed final write | Read or export |
| `failed` | A saved failure such as timeout or invalid agent output | Read or export; no retry transition in this release |
| `interrupted` | No matching local task, or a saved interruption; stored status may still be `running` | Inspect/export; no automatic retry or claim that remote work stopped |

Completed, failed, and interrupted records remain
readable and exportable until expiry. Earlier run inputs remain snapshots when
new evidence is appended. Each record allows at most four runs; correcting a
failed result does not silently reuse or restart a prior call.

## Execution and trust

- Work continues independently of a browser disconnect. The API persists the
  running state before returning HTTP 202. The browser polls the selected run.
   If a status request fails, Refresh restarts polling without starting another
   agent execution. Inbox counts describe loaded records, not the entire store.
- Execution is process-local, not a durable distributed worker. Keep one worker
  and one replica. A process restart or an unconfirmed final save exposes an
   interrupted run in both the inbox and detail view. No automatic model retry or
   recovery is attempted;
  an already accepted remote call may still complete and incur charges.
- ETag preconditions protect starts and evidence updates from competing tabs.
  After an uncertain create or update, refresh the inbox before repeating it.
  Creating a brand-new review is not idempotent across repeated requests.
- Each review permits at most four runs. Agent calls share chat's four in-flight
  slots and 20-request/minute admission budget, with a maximum 180-second timeout.
  Review record operations have separate four-request concurrency, 120/minute
  admission and 35-second deadlines. Input upload is limited to five seconds,
  64 KiB JSON, and 30,000 content characters; each source is at most 12,000 characters.
- A coordinator result is accepted only with checked, correlated specialist
  receipts matching configured targets. Receipt metadata is stored server-side;
  browsers cannot submit findings, success flags, or run events.
- Timeline entries are observed application milestones. Specialist receipt and
  citation checks happen after the response arrives, not streamed specialist
  start events. No hidden reasoning or simulated progress is displayed.
- Exact quotes establish source-reference integrity, not factual truth or a
  quality score. Model findings require human review. The system does not approve,
  deny, rank people, or execute external business actions.

## Persistence

Reviews use the existing `workbench/conversations` Cosmos container and shared
partition, under prefixed IDs and a separate record type. Chat routes reject review
IDs and chat lists exclude typed records. Conditional writes preserve prior run
input snapshots. The additive `/kind/?` index supports the separate lists.

All network-authorized workspace users can read reviews and submit evidence.
There is no end-user identity, owner authorization, or immutable audit ledger.
Use synthetic data only. Stored execution checks are historical records, not a
fresh verification of the current agent deployment. Each record expires 30 days
after its last write; backup retention is separate. This first release has no
review deletion or draft-edit endpoint, so export and retention are the available
record lifecycle controls.

Review details include observed elapsed time, but not full coordinator-plus-specialist
token accounting or invoiced cost. Neither is fabricated from the existing budget.

## Delivery checks

### 1. Validate the source locally

Run the workbench Python suite and frontend build, lint, and Playwright tests
from the repository root using the [local validation commands](../workbench/README.md#local-development).
Browser tests use controlled API responses; backend tests use an in-memory
store and gateway doubles. They do not prove live Cosmos or model behavior.

### 2. Review and deploy the intended image

Follow the [Lab deployment steps](../workbench/README.md#deployment): configure
the correct state, build an immutable image, review a saved Terraform plan, then
apply and clean up that plan. Keep platform and Lab state separate. Normal root
Terraform source is publishable; state, backups, secrets, backend configuration,
environment tfvars, saved plans, and private workaround scripts are not.
For initial review support, verify the additive Cosmos index is ready
before promoting the image. Record both the intended image and recovery digest.

### 3. Start one synthetic review

Run from the repository root on authorized private-network access. Replace the
URL with the verified Lab output. This is a live model call that can incur charges;
it is not an offline test. The script expects the sample customer-review catalog.

```powershell
$baseUrl = '<verified-private-url>'
./workbench/test-review-private.ps1 -Mode Start -BaseUrl $baseUrl
```

Record `SYNTHETIC_REVIEW_ID` from the output. Start also verifies that a competing
start with the old ETag is rejected. Do not run Start again because a status read
fails or the first response is delayed.

### 4. Inspect the first result

Set the ID reported by step 3, then inspect after the execution reaches an outcome:

```powershell
$reviewId = '<synthetic-review-id-from-step-3>'
./workbench/test-review-private.ps1 -Mode Inspect -ReviewId $reviewId -BaseUrl $baseUrl
```

Require verified specialist receipts, exact citations, and `waiting_input` for
this fixture's missing budget. If still running, the script reports that it has
not reached a result: inspect again later, without starting another execution.
For failed/interrupted output, stop and investigate. An unexpected completed
first run does not establish that clarification/resume was tested.

### 5. Append evidence and resume explicitly

Only after step 4 confirms the first-run clarification:

```powershell
./workbench/test-review-private.ps1 -Mode Resume -ReviewId $reviewId -BaseUrl $baseUrl
```

This appends synthetic budget evidence and starts the second model call. The
script checks that the first run's evidence snapshot remains unchanged. If the
response is uncertain, inspect the record before repeating a mutating action.

### 6. Verify the final record

After the second run reaches an outcome:

```powershell
./workbench/test-review-private.ps1 -Mode Verify -ReviewId $reviewId -BaseUrl $baseUrl
```

Require a completed two-run review with preserved snapshots, verified receipts,
and exact citations. Reopen it in the UI and inspect both run versions. Record
the test outcome and deployed image; a successful Terraform apply alone is not
live acceptance. The synthetic review remains under normal 30-day TTL: this
release has no review deletion API. Do not delete shared storage to clean up a test.

Next extensions are authenticated ownership, durable worker recovery, evaluated
retrieval over approved sources, and approval-gated external actions. They are not
part of this first release.
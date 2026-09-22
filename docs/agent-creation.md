# Create and try a baseline Foundry agent

[Overview](../README.md) / [Demo guide](demos.md) / Agent creation

The Lab can prepare a task setup from a reviewed template, publish a real named
Foundry hosted agent after operator confirmation, and open that agent in Chat.
This is a small demonstration feature, not an unrestricted agent designer or a
production agent-management service.

## What a participant can do

**Describe the job -> prepare a setup -> review and confirm -> create in Foundry
-> try it in Chat.**

Five templates cover document analysis, criteria checking, administrative
intake, casework summaries and workflow planning. Their fictional examples suit
public-sector, healthcare-operations and ISV conversations without reproducing
any customer's work or implementation claims.

- Preparing a draft uses deterministic templates and the supplied description.
  It does not ask a model to design an agent, save a resource or spend model
  tokens. An ambiguous description asks for a template instead of guessing.
- Before creation, edit the display name and task instructions. Tools and
  runtime policy are fixed by the selected template and cannot be added by a
  prompt. The first four templates have no tools or specialist delegation.
- Workflow Coordinator has exactly `lookup_demo_request` and
  `lookup_demo_service`: fixed, local, **simulated read-only** lookups. It can
  propose next steps, but cannot open a ticket, approve a request, send a message
  or connect to a customer application.
- Explicit creation publishes a new generated `lab-demo-...` named agent using
  the Foundry SDK. Progress represents actual application stages, not a timer
  pretending to be deployment progress.
- Ready means the hosted version is active and its Responses route was checked.
  No hidden billable model smoke test runs. Send the fictional sample in Chat
  to observe its first actual answer and check quality yourself.
- Chat can use this ready agent or an existing enabled agent. A chat prompt does
  not edit either setup. There is no in-place editor for deployed instructions.
- Document reviews remain independent: their saved checklist/results workflow
  uses the existing Lab default agent, not whichever created agent is in Chat.
  There is no automatic transfer between the two.

The local disconnected preview supports draft preparation only. It cannot
publish, persist a created agent or produce a live model answer. Browser-test
screenshots with mocked APIs must be visibly labeled as illustrative.

## Enable publication

Creation is **disabled by default**. Keep the existing private access boundary
and single worker/replica. Before enabling:

1. Have an approved Foundry project, an existing model deployment with quota,
   working private connectivity, and the Lab's shared Cosmos container. Check
   the pinned SDK/remote-build combination in an approved staging environment.
2. Review the workbench managed identity's ability to read, publish, route and
   delete the new hosted agents. Invocation access alone may be insufficient.
   This feature does not grant roles or alter existing identities/permissions.
3. Create a strong, randomly generated operator key of at least 32 characters,
   preferably through an approved password manager. Store only its lowercase
   SHA-256 UTF-8 verifier in an existing Key Vault secret. The raw key is given
   separately to approved operators; do not commit it or put it in Terraform.
4. If using Lab Terraform, configure these nonsecret inputs through the normal
   reviewed rollout:

   ```hcl
   agent_creation_enabled       = true
   agent_creation_model         = "your-existing-model-deployment"
   agent_creation_key_secret_id = "https://your-vault.vault.azure.net/secrets/lab-creation-key-verifier"
   ```

   The secret must contain the **verifier**, not the raw key. Key Vault access
   for the existing workbench identity must already be provisioned by the
   environment owner. The optional reference creates no vault, secret, role
   assignment or model deployment.
5. Rebuild the Lab image so it includes the reviewed runtime bundle, then use
   the existing approved deployment process. No deployment or permission change
   is performed by the source-code/test changes themselves.
6. In the private UI, prepare one fictional setup, verify its tools and limits,
   confirm costs/shared visibility and provide the operator key. Check real
   publication, send its sample, then verify cleanup before inviting an audience.

For non-Terraform operators, the equivalent server configuration is:

| Environment variable | Meaning |
| --- | --- |
| `WORKBENCH_AGENT_CREATION_ENABLED` | Exactly `true` to allow new publication/resume; defaults to `false` |
| `WORKBENCH_AGENT_CREATION_MODEL` | Existing model deployment captured in each new setup; not editable in the browser |
| `WORKBENCH_CREATION_KEY_SHA256` | Lowercase, 64-character verifier from a secret reference; never the raw key |
| `WORKBENCH_MAX_CREATED_AGENTS` | Defaults to 5; allowed range 1-20; failed/unconfirmed attempts still count |
| `WORKBENCH_PUBLICATION_TIMEOUT_SECONDS` | Defaults to 600; allowed range 30-900 |

The existing `WORKBENCH_MODE=private`, Foundry endpoint, managed identity,
trusted hosts/origins and Cosmos configuration still apply. Invalid opt-in
settings fail startup rather than enabling an unprotected creation endpoint.

The operator key travels only to this backend over the private HTTPS session,
in `X-Workbench-Creation-Key`. It is not sent to the model, written to Cosmos,
included in chat exports, or stored in browser persistent storage. This is a
**shared operator gate**, not Entra sign-in or per-user resource ownership.
Anyone with Lab access can read the shared created-agent setups and use ready
agents. Publication/deletion require the key; do not use confidential data.

Disabling new creation does not stop or hide existing ready agents. Keep the
valid verifier configured to allow operator deletion while creation is disabled.

## Configuration ownership

| Source | Owns |
| --- | --- |
| [`agent_templates.py`](../workbench/agent_templates.py) | Job descriptions, prepared instructions, examples, conservative matching and fixed public tool metadata |
| [`agent_runtime`](../workbench/agent_runtime) | Reviewed runtime code, immutable policy, allowed tools and pinned remote-build requirements |
| Creation request and saved record | Chosen template metadata snapshot, edited name/instructions, configured model, generated resource identity and setup/runtime hashes |
| [`agent_publisher.py`](../workbench/agent_publisher.py) | SDK publication, version/ownership checks, activation polling, route verification and retirement |
| Server environment / [Lab Terraform](../workbench/infra/main.tf) | Enablement, model, operator-key verifier and operational limits |
| Existing [`agents.json`](../workbench/agents.json) and coordinator profiles | Unchanged static catalog, visibility and specialist bindings; not overwritten by creation |

Only `main.py`, `demo_tools.py` and `requirements.txt` enter the deterministic
ZIP. Prompts cannot upload source, install dependencies, select endpoints,
change the model or register tools. Hosted allocation is fixed at 0.5 CPU / 1 GiB;
remote build uses `python_3_14`, matching the existing deployer. This runtime
identifier is separate from the workbench container's Python 3.13 version.

Changing templates, code, tools, permissions or model configuration requires a
developer/operator rollout. It does not mutate already published agents.
Created-agent guidance, starter text and expected tool receipts use the saved
template snapshot, not whichever template definitions a later Lab image contains.
The `created-<UUID>` identifier namespace belongs to saved created agents;
static catalog entries cannot reuse it.

## Publication, recovery and deletion

The API saves a typed Cosmos record **before** scheduling remote work. It then
uploads the reviewed ZIP, records the returned version, waits for activation,
sets a 100% Responses route and reads the route/version back before marking
ready. It does not use browser-supplied endpoint names or change static agents.

- A client UUID identifies one creation request. Repeating the same setup with
  the same UUID returns the same operation; changing its setup is a conflict.
  An uncertain browser response must not trigger a new UUID or automatic retry.
- Once submission may have started, Resume reconciles the named resource; it
  never uploads another version merely because a status check returns 404.
  If submission was definitely never started, Resume may perform that original
  first submission. A missing/unconfirmed cloud outcome stays explicit.
- Timeout, process restart or an unsuccessful final status write can leave an
  interrupted record. Refresh checks status; it is not another publication.
  A failed poll does not mean the hosted operation stopped.
- Creation and deletion are serialized in one process. Conditional Cosmos
  updates reject stale operators. Multiple workbench workers/replicas would
  need distributed admission and job ownership; do not enable them here.
- Versions must carry this operation's ownership/setup/runtime metadata. Foreign
  or extra versions and inconsistent routes block automatic promotion/deletion.
  An owned but unrouted endpoint can be connected without replacing its existing
  authorization schemes or other protocol configuration. An absent activation
  status remains pending under the same bounded publication deadline.
  Do not edit these generated resources through a second control plane during
  an operation; investigate unexpected changes in Foundry with an operator.
- Delete requires the operator key, explicit shared-impact confirmation and
  the current ETag. It retires only this created resource after ownership checks
  and confirms absence. An interrupted deletion must be retried as deletion,
  not resumed as setup. A 404 after an unconfirmed submission is not sufficient
  to claim the resource was safely removed.

Active, failed and unconfirmed records do not expire while a hosted resource
might still exist. After confirmed deletion, the saved display name and task
instructions are cleared; a small, nonexpiring ID/hash/status tombstone prevents
an old creation request from silently republishing the same agent. Cosmos
backups follow the account policy and are not immediate secure erasure.

Chats/reviews retain their existing 30-day retention and shared access rules.
Export needed conversations **before** deleting their created agent: an agent
that is no longer ready is no longer selectable, and its saved chats are not
available through the active-agent history list. Deleting an agent is not a
blanket deletion of other users' chat documents.

There is no automatic idle shutdown. Hosted runtime/build costs can continue
after a browser closes, a request times out, or new creation is disabled. A
maximum record count and publication deadline are not a spending cap. Confirm
cleanup and investigate every uncertain outcome before declaring a demo over.

## Verification and honest status

Offline tests cover drafts, strict inputs, operator/origin checks, idempotency,
single-flight/quota behavior, persistence-before-mutation, restart recovery,
owned routing/deletion, SDK model/ZIP contracts, created-agent chat/history and
desktop/mobile UI flows. CI includes the new runtime and API checks.

Those tests do not establish live Azure permissions, private connectivity,
remote-build support, model availability, answer quality or actual charges.
Complete the approved staging checks above and record the difference between
source availability, enabled configuration and observed execution in the
[demo handoff](demo-handoff.md). This is not an officially approved Microsoft
offering or an implemented customer solution.

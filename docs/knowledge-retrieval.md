# Knowledge retrieval design

[Home](../README.md) / [Docs](README.md) / Knowledge retrieval design

This design adds an optional, read-only policy guidance lookup to the Case notes
summarizer (`case-review-agent`). The code ships behind the
`KNOWLEDGE_RETRIEVAL_ENABLED` flag, which is **off by default**. With the flag
off, the published agent, its tools and instructions, portable bundles, and
evaluation outputs are unchanged. The repository's Terraform, evaluation
datasets, and default case agent files aren't changed by this work. The one live
pilot was set up by hand, as the [pilot results](#pilot-results-2026-10-01)
show.

> [!IMPORTANT]
> **Status: a small sample pilot, not a finished evaluation.** This guide
> describes the design and its decisions. Dated measurements and the gaps found
> in the pilot are in [Pilot results (2026-10-01)](#pilot-results-2026-10-01).
> Current status and open work are tracked in
> [#122](https://github.com/michael-rechani/foundry-agent-accelerator/issues/122),
> and the wider add-ons roadmap in
> [#54](https://github.com/michael-rechani/foundry-agent-accelerator/issues/54).

## In this guide

- [Goal](#goal)
- [Chosen approach](#chosen-approach)
- [Alternatives considered](#alternatives-considered)
- [Which specialist uses it](#which-specialist-uses-it)
- [What the flag changes](#what-the-flag-changes)
- [Tool contract](#tool-contract)
- [Identity and RBAC](#identity-and-rbac)
- [Private networking](#private-networking)
- [Index schema](#index-schema)
- [Sample documents and the index script](#sample-documents-and-the-index-script)
- [Shared Search cautions](#shared-search-cautions)
- [Receipts in the Lab](#receipts-in-the-lab)
- [Evaluation additions](#evaluation-additions)
- [Cost](#cost)
- [Operator rollout](#operator-rollout)
- [Not done](#not-done)
- [Open decisions](#open-decisions)
- [Pilot results (2026-10-01)](#pilot-results-2026-10-01)
- [Follow-up (2026-10-03)](#follow-up-2026-10-03)
- [Sources](#sources)
- [Related content](#related-content)

## Goal

Case prompts often say "No policy text is supplied", so the agent can only flag
that policy is missing. The goal is to let the agent look up **fictional**
policy or guidance passages from an approved Azure AI Search index and cite them
by source identifier, while keeping the project's principles:

- **Evidence-led:** every retrieved passage carries a `source_id` the answer can
  cite, and "nothing matched" or "lookup failed" is reported honestly.
- **People decide:** retrieval adds context; it doesn't change the decision
  boundary in [`instructions.md`](../hosted-agents/case-review-agent/instructions.md).
- **Read-only:** the tool can only query one index, with a read-only data role.
- **Fictional data:** the index holds demo guidance only.
- **No invented claims:** retrieved text is untrusted data, kept separate from
  supplied facts.

## Chosen approach

A custom, read-only Microsoft Agent Framework function tool,
`search_policy_guidance`, in [`knowledge_retrieval.py`](../hosted-agents/knowledge_retrieval.py).
It uses the GA `azure-search-documents` **12.0.0** client with
`DefaultAzureCredential` and runs inside the hosted container as the
specialist's own agent identity.

Why this option fits the pinned versions and the private network:

| Concern | How this approach handles it |
| --- | --- |
| SDK status | `azure-search-documents` 12.0.0 is the current GA release. It adds only `isodate`, which the pinned Foundry packages already install, on top of existing `azure-core` and `typing-extensions`. No preview package is added. |
| Pinned versions | Works unchanged with `agent-framework-foundry==1.13.1`, `agent-framework-foundry-hosting==1.0.0b260918`, and `azure-identity==1.25.3` from [`requirements.txt`](../hosted-agents/case-review-agent/requirements.txt). The tool is a plain async function, the same pattern the coordinator uses for its specialist tools. |
| Least privilege | Each hosted agent runs as its own Microsoft Entra agent identity. That identity gets **Search Index Data Reader** on **one index**. The Foundry-managed tool would instead query as the shared project managed identity, which the pinned AVM module already grants Search Index Data Contributor and Search Service Contributor on the whole service. |
| Private networking | The Search service already has public access disabled, local (key) authentication disabled, and a private endpoint in `privatelink.search.windows.net`. The agent subnet is network-injected into the same virtual network. Keyless managed identity is the only option, which this approach uses. |
| Bounded behavior | The code, not the model, fixes the index, `top` (at most 5), the `select` field allowlist, the simple query type, and that every query word must match. The model supplies only the query text; it can't pass a filter, index, or field list. |
| Receipts | Returns the coordinator's specialist receipt shape (`status`, `agent`, `output`) plus `retrieval` and `source_ids`, so Lab receipt verification works unchanged. The deploy smoke check also requires at least one passage. |
| Testability | Unit-tested offline with a fake search client and with the real SDK over a mock transport. |
| No new service | It's a tool in an existing agent, not a bespoke retrieval service, and it doesn't need Azure-side tool, connection, or toolbox creation, vectors, or an embedding model. |

The [extension guide](architecture-assessment.md#features-to-evaluate-only-when-needed) asks to try
the supported Foundry tool first. The Foundry tool remains a documented
alternative, and an operator comparison in staging is an
[open decision](#open-decisions). This design picks the custom tool for now
because the Foundry tool's keyless path requires Contributor-level roles for the
shared project identity, and its Agent Framework wrapper is experimental in the
pinned version.

## Alternatives considered

| Option | Status in the pinned versions | Why not chosen now |
| --- | --- | --- |
| **Foundry Azure AI Search tool**, called directly through `FoundryChatClient.get_azure_ai_search_tool(...)` | The Foundry tool is GA. The Agent Framework wrapper is marked experimental (`FOUNDRY_TOOLS`) in `agent-framework-foundry` 1.13.1 and emits an experimental warning. | Keyless auth uses the Foundry project managed identity with **Search Index Data Contributor** and **Search Service Contributor** (write and admin-capable), shared by every agent in the project. It needs a project connection ID. Microsoft Learn lists a vector-configured index as a prerequisite. Tool calls are hosted by Foundry, so the repository can't enforce a field allowlist or label content as untrusted. Its receipts don't use the specialist receipt shape. |
| **Foundry toolbox** exposing Azure AI Search over MCP (`FoundryToolbox`) | Microsoft Learn recommends toolboxes for hosted agents. The toolbox itself is created in the project (`project.toolboxes.create_toolbox_version`). | Same identity and role model as the direct tool, plus an Azure-side toolbox resource to create and version. That is an Azure change this scope excludes. |
| **`AzureAISearchContextProvider`** from `agent-framework-azure-ai-search` | Beta (`1.0.0b260910`). Requires `agent-framework-core>=1.18`, `aiohttp`, and `azure-search-documents>=12,<13`. Agentic mode needs a Search Knowledge Base and an Azure OpenAI resource. | Injects retrieved context on every turn rather than as an explicit tool call, so there's no function-call receipt to verify, and the model can't decide when a lookup is relevant. Adds a beta package. |
| **Bespoke retrieval service** | Not applicable. | Explicitly discouraged by the [extension guide](architecture-assessment.md#features-to-evaluate-only-when-needed). It would add a new service, identity, and network path. |

## Which specialist uses it

Only the **Case notes summarizer** (`case-review-agent`). Its instructions
already have an "Applicable supplied policy" section, and its fictional
scenarios often lack policy text. The tool is described as a lookup for
fictional policy and guidance passages that the answer can cite by `source_id`.

The **Checklist reviewer** (`application-review-agent`) isn't changed. It must
review against the criteria supplied in the request, and retrieved guidance
could blur that boundary. Enabling it there is an
[open decision](#open-decisions). The coordinator isn't changed either.

## What the flag changes

The flag is read when you run
[`case-review-agent/deploy.py`](../hosted-agents/case-review-agent/deploy.py),
and again by the runtime inside the container.

| Setting | Default | Rules |
| --- | --- | --- |
| `KNOWLEDGE_RETRIEVAL_ENABLED` | `false` (unset) | Exactly `true` or `false`. Any other value stops the deployment before Azure is called. |
| `KNOWLEDGE_SEARCH_ENDPOINT` | None | Required when enabled. `https://<service>.search.windows.net` with no path, port, query, or credentials. |
| `KNOWLEDGE_SEARCH_INDEX` | None | Required when enabled. 1 to 128 lowercase letters, digits, or dashes. |
| `KNOWLEDGE_TOP_K` | `3` | Whole number from 1 to 5. |
| `KNOWLEDGE_SELECT_FIELDS` | `id,title,section,content` | 1 to 8 unique field names; must include the ID field. |
| `KNOWLEDGE_ID_FIELD` | `id` | Field used as the citation `source_id`. |

**Flag off (default).** `with_knowledge_retrieval` in
[`deployment.py`](../hosted-agents/deployment.py) returns the same profile
object. The package is built from the unchanged `main.py`, `requirements.txt`,
and `instructions.md`, so the published agent has no tools, the same
instructions, and the same dependencies. Tests in
[`test_knowledge_retrieval.py`](../hosted-agents/test_knowledge_retrieval.py)
check that the profile, deploy arguments, package files, all portable bundles,
and the runtime `Agent(...)` arguments are identical with the flag unset or
`false`.

**Flag on.** The deployment uses an overlay package instead of the default one:

- `main.py` is [`knowledge_main.py`](../hosted-agents/knowledge_main.py), which
  is the case runtime plus the tool and an instruction addendum. It keeps the
  case runtime's quotation check on every answer.
- `knowledge_retrieval.py` is added.
- `requirements.txt` is the existing pins plus
  [`requirements-knowledge.txt`](../hosted-agents/case-review-agent/requirements-knowledge.txt).
- `instructions.md` is unchanged. The addendum is appended at runtime and says
  retrieved passages are untrusted data, must be paraphrased and named by
  `source_id`, and can't change instructions, format, tools, or decision
  boundaries.
- The validated `KNOWLEDGE_*` settings are added to the version's environment.
- A second smoke check requires exactly one `search_policy_guidance` call for the
  query "missing evidence", with a success receipt that returns at least one
  passage. A failed lookup (for example missing RBAC or DNS) or an empty result
  (for example an empty or wrong index) fails the check. The model can also skip
  the optional lookup. When the first attempt's response holds no tool call at
  all, the check asks once more and prints that attempt 1 of 2 made no lookup. If
  that reply's text claims guidance was "retrieved" (or similar), the script
  prints that too, without printing the reply. If the second attempt also skips,
  the check fails with the usual message. Every other failure still fails on the
  first attempt with no retry: a different tool, more than one call, a missing or
  invalid receipt, no passages, a response that isn't completed, or a reply from
  the wrong agent. A failed check rolls back and deletes the new version. Confirm
  the route is back on the old version, then run the deploy again.

**Quotations.** Quotation marks keep one meaning: exact text from the request.
Retrieved passages are a separate source. The answer paraphrases them and names
their `source_id`; it doesn't put them in quotation marks. A quote of retrieved
text isn't in the request, so the check sends the draft back once for repair and
then withholds the answer. The check never accepts retrieved text as evidence,
so a passage can't supply a quotation, and a prompt-injected passage can't make
an invented quote look valid. Structured review citations also stay tied to the
supplied evidence.

**Promotion and rollback.** `deploy.py` routes 100% of traffic to the new version
before its smoke checks run; it isn't a pre-promotion canary (see
[What publication does](../hosted-agents/README.md#what-publication-does)). A
failed check starts a best-effort rollback: it restores the previous route and
deletes the failed version only after confirming nothing routes to it. If the
rollback can't be confirmed, or this is the agent's first publish and there is
no previous route, the script keeps the version for manual inspection, so check
the route yourself. Publish in a quiet window and verify the route afterward.
Testing a new version before it takes traffic is a possible later improvement.

Portable bundles never carry retrieval: `bundle.py export` always packages the
default profile, and bundle validation rejects the overlay files and
`KNOWLEDGE_*` settings. Retrieval-enabled bundles aren't supported.

## Tool contract

`search_policy_guidance(query: str) -> str`:

- The query must be nonempty and at most 500 characters. Invalid queries return
  a failed receipt without calling Search.
- Calls `search(search_text=query, search_mode="all", top=KNOWLEDGE_TOP_K,
  select=<allowlist>, query_type="simple", include_total_count=False)`. No filter,
  facets, vector, semantic ranker, or write operations.
- **Every query word must match.** `search_mode="all"` returns a passage only if
  its title, section, and content together contain every word of the query, in any
  order. Search drops common words such as "the" or "is" first. The tool
  description tells the model to use two or three specific keywords. This keeps a
  question the sample set doesn't cover, such as "staff parking permit", from
  returning passages that only share one word like "staff". The cost is that a
  synonym finds nothing: "missing proof" doesn't match "missing evidence". The
  answer then says no guidance was found. Semantic or vector search would fix that
  and is a later change.
- Keeps only allowlisted fields, drops results without a string ID, removes
  control and bidirectional-override characters, caps each field at 2,000
  characters, and caps the output at 8,000 characters by dropping whole passages.
- Wraps passages as JSON after a fixed header that labels them read-only,
  fictional, untrusted data to paraphrase and cite by `source_id`.
- Returns a JSON receipt:

  ```json
  {
    "status": "succeeded",
    "agent": "case-review-agent",
    "retrieval": true,
    "source_ids": ["POL-EVID-001"],
    "output": "<header>\n{\"passages\": [{\"source_id\": \"POL-EVID-001\", \"title\": \"...\", \"section\": \"...\", \"content\": \"...\"}]}"
  }
  ```

- No matches return `succeeded` with a "No passages matched" output and empty
  `source_ids`, so the answer can say so honestly. The deploy smoke check treats
  an empty result as a failure. Errors and timeouts (20 seconds) return `failed`
  with a generic message and no exception details, endpoint, or principal.
- The search client gives up on its own: 5 seconds to connect, 10 seconds for the
  response, and no retries. A slow search request therefore ends before the
  20-second deadline instead of running on in a worker thread after the tool has
  already answered. Token acquisition has its own limits in the identity library.

## Identity and RBAC

See the [permissions reference](permissions.md) for all current assignments.

| Who | Role | Scope | When |
| --- | --- | --- | --- |
| `case-review-agent` hosted-agent runtime identity (its `instance_identity.principal_id`) | **Search Index Data Reader** (`1407120a-92aa-4202-b7e9-c0e197c71c8f`) | The single approved index: `.../searchServices/<service>/indexes/<index>` | Before publishing a retrieval-enabled version. Terraform can assign it: see [Knowledge search access](../terraform/README.md#knowledge-search-access). |
| The person who runs the [index script](#sample-documents-and-the-index-script), signed in with their own account | **Search Service Contributor** (reads the index definition, creates or deletes the index) and **Search Index Data Contributor** (lists, loads, and deletes passages) | The Search service. The index doesn't exist yet when `load` creates it, so the data role can't be scoped to it for that first run. | Only while running `load` or `remove`. Remove both roles afterward. |

- Search Index Data Reader can query indexes but can't load documents, change
  definitions, or read admin keys.
- Scope the reader role to the index, not the service. Per-index scoping is
  supported by Azure AI Search.
- Don't use API keys; the service has local authentication disabled.
- Grant the role before publishing. Token caching can delay a late grant, and
  the retrieval smoke check fails closed without it.
- This design doesn't change the project identity's existing Contributor roles,
  which the Foundry Agent Service needs for its own use of the backing Search.
- **What each script command needs.** `plan` never contacts Azure. `load` and
  `remove` need both operator roles, because they read the index definition
  first and then list and write passages. `verify` reads the definition and the
  passages, so it needs Search Service Contributor plus a data role. Search
  Index Data Reader alone can't read an index definition, so `verify` with only
  that role stops with an access error. The pilot's approved run worked with
  both roles in place; it didn't test whether either role alone would have been
  enough (see [Pilot results](#pilot-results-2026-10-01)).
- Search Service Contributor is a privileged role. Per
  [Microsoft Learn](https://learn.microsoft.com/azure/search/search-security-rbac#role-descriptions),
  it can also retrieve admin and query API keys through the control plane. Keys
  are disabled on this service, but give the role to a named person for the
  shortest time needed.

## Private networking

The existing platform already provides the path. This design doesn't change it.

- The Agent Service Search service has `public_network_access_enabled = false`
  and `local_authentication_enabled = false`, with a private endpoint.
- The `privatelink.search.windows.net` private DNS zone is linked to the
  workload virtual network.
- The Foundry account uses network injection into `snet-agent-services`, so
  hosted-agent egress is expected to resolve and reach the private endpoint.

Verify this in staging before relying on it: the retrieval smoke check proves
DNS, network, and RBAC together. The dev environment's result is in
[Pilot results](#pilot-results-2026-10-01). If you use a different Search
service, it needs its own private endpoint and DNS link; don't enable public
access.

Run the [index script](#sample-documents-and-the-index-script) from a machine
that can reach the private endpoint, such as the jumpbox or a private runner.
From the public internet it fails because public access is off. Don't open
public access to run it.

## Index schema

Use a **dedicated index** for sample guidance, not an index used by Foundry
features. The default settings expect the schema below. The
[index script](#sample-documents-and-the-index-script) creates exactly this
schema, with every field a string and none sortable or facetable:

| Field | Type | Attributes | Purpose |
| --- | --- | --- | --- |
| `id` | `Edm.String` | Key, retrievable, filterable | Stable citation ID, for example `POL-EVID-001`. |
| `title` | `Edm.String` | Searchable, retrievable | Document title. |
| `section` | `Edm.String` | Searchable, retrievable | Section or clause number. |
| `content` | `Edm.String` | Searchable, retrievable | Passage text, chunked to 2,000 characters or fewer. |
| `version` | `Edm.String` | Filterable, retrievable | Guidance version for freshness checks. Not selected by default. The script writes the set's version, such as `sample-v1`, on every passage and uses the `sample-` prefix to recognize the passages it loaded. |

No vector fields, semantic configuration, or embedding model are needed for the
simple query type. Adding vector or semantic search is a later change.

## Sample documents and the index script

The repository includes a small sample guidance set and a script that loads it.
The passages are fictional demo text, not customer, staff, or real policy text.

- [`knowledge-sample/policy-guidance.json`](../hosted-agents/knowledge-sample/policy-guidance.json)
  is version `sample-v1`: ten short passages, each with an `id`, `title`,
  `section`, and `content` well under the 2,000-character limit. They cover
  missing evidence, conflicting statements, dates, names and identifiers,
  contact attempts, follow-up questions, urgent concerns, missing policy text,
  summary wording, and personal details. `POL-EVID-001` answers the deploy smoke
  check's query "missing evidence", and the script refuses a set without it.
- [`knowledge_index.py`](../hosted-agents/knowledge_index.py) plans, loads,
  verifies, and removes that set in one dedicated index. It uses the Python
  standard library, the limits in `knowledge_retrieval.py`, and
  `azure-identity`. It doesn't need the Search SDK.

Run it from the repository root with the deployment environment's interpreter
from [Prepare the selected sample](../hosted-agents/README.md#3-prepare-the-selected-sample),
which already has `azure-identity`. Pass the endpoint and index name, or set
`KNOWLEDGE_SEARCH_ENDPOINT` and `KNOWLEDGE_SEARCH_INDEX`:

```powershell
& $python hosted-agents/knowledge_index.py plan --endpoint https://<service>.search.windows.net --index <index>
```

| Command | What it does | Changes Azure? |
| --- | --- | --- |
| `plan` | Lists the passages, the set's version and digest, and what `load` would do. | No. It never contacts Azure or asks for a credential. |
| `load --confirm` | Creates the index if it's missing, uploads the passages, deletes sample passages that are no longer in the set, then runs `verify`. | Yes. Creates an index and writes passages. |
| `verify [--wait SECONDS]` | Checks the schema, every passage against the set, and that the query "missing evidence" returns `POL-EVID-001`. `--wait` retries while indexing catches up. | No. It only reads. |
| `remove --confirm [--keep-index]` | Deletes the index, or only its passages with `--keep-index`. | Yes. Deletes data. |

The script enforces these rules, and offline tests with a fake Search service
cover each one:

- **Nothing changes without `--confirm`.** `load` and `remove` without it print
  what to do and exit with code 2 before contacting Azure.
- **Dedicated sample index only.** Before changing an existing index, it reads
  the definition and lists the documents. It stops without changing anything if
  the schema differs, the index holds more than 100 documents, or any document's
  `version` doesn't start with `sample-`. An index that holds anything else is
  left alone.
- **Stale sample passages only.** `load` deletes only sample passages that are
  missing from the current set.
- **Bounded and keyless.** It talks only to the validated
  `https://<service>.search.windows.net` endpoint, signs in with
  `DefaultAzureCredential` (for example after `az login`) and never uses keys,
  waits at most 30 seconds per request, reads at most 1 MB per response, and
  prints short, cleaned error messages without tokens.
- **Indexing lag is expected.** New passages take a moment to become
  searchable, so `load` retries `verify` for about 30 seconds.
- **Clear exit codes.** `0` is success. `1` is a failure: a refusal, a Search
  error, a sign-in or network problem, or a failed check. `2` is a usage or
  settings problem, an invalid sample set, or a missing `--confirm`.

To change a passage, edit the file, raise the version (for example `sample-v2`),
get the new set approved, and run `load --confirm` again. Record the version and
the digest that `plan` and `verify` print with the approval.

Running `load` or `remove` against Azure changes shared data. It needs the
approvals in [Operator rollout](#operator-rollout).

## Shared Search cautions

The Agent Service Search service backs Foundry features, so treat it as shared
data and a shared cost:

- **Inventory first.** Before creating an index, list the existing indexes and
  the project's vector stores, who owns each, and how each would be rebuilt or
  removed. Pick an index name that isn't in use, and stop if anything is
  unexpected.
- **A tier change deletes indexes.** Changing `ai_search_sku` replaces the
  service and deletes its indexes. Confirm that no index or vector store is in
  use, including this one, before any tier change. See
  [Configure inputs and state](../terraform/README.md#1-configure-inputs-and-state).
- **One replica has no availability SLA.** A retrieval check that fails once
  may be a brief outage, not a design fault. Don't add replicas for this pilot
  without a cost review.
- **Keep the pilot index small.** Ten short passages stay well within the
  service's existing capacity.
- **No user uploads.** The Lab has no sign-in, so it can't keep one person's
  documents private from another visitor. Only the reviewed sample set belongs
  in the index.
- **People approve the writes.** Creating or loading an index changes shared
  data, so get explicit approval first, as listed in
  [Operator rollout](#operator-rollout).

## Receipts in the Lab

`execution_receipts` in [`workbench/app.py`](../workbench/app.py) verifies a
`function_call` and its matching `function_call_output` against the agent's
tool bindings in [`agents.json`](../workbench/agents.json).

- **Through the coordinator (how the pilot runs).** The coordinator receives
  only the specialist's final text, so the specialist's lookup receipt isn't
  visible in the coordinator's output. The answer's citations are the only
  trace. Surfacing nested receipts is an [open decision](#open-decisions).
- **Direct access to the case agent.** The lookup isn't bound in the case-review
  entry's `tools`, so a lookup shows as an unverified receipt. Don't add
  `"search_policy_guidance": "case-review-agent"` while the lookup is optional.
  A document review is marked failed when an agent has bound tools and the run
  shows no verified call ([`review_runs.py`](../workbench/review_runs.py)), and
  the model may skip an optional lookup. Bind the tool only if the lookup
  becomes required.

For the pilot, `agents.json` and the Add-ons tab changed so the Lab says what is
live:

- The case-review entry's `configuration`, `delegation`, and `limits` text no
  longer says the runtime has no tools. It says the optional sample lookup is
  added only when `deploy.py` runs with the flag on, and that the Lab shows no
  receipt for it.
- The customer review and review coordinator entries' `limits` text names the
  sample pilot as the one exception to "it works from what you supply".
- The Knowledge search card on the Add-ons tab shows a **Sample pilot** badge and
  an "In the Lab today" line. The other add-ons still say "Not available yet".

## Evaluation additions

This design doesn't change the live evaluation dataset. The runner
has one change: [`evaluations/run.py`](../evaluations/run.py) now includes any
`KNOWLEDGE_*` settings in the configuration digest of the version it evaluates,
so the digest changes when retrieval is turned on, pointed at a different index,
or given different options. Agents without those settings keep their existing
digests, and runs record only the hash, never the setting values.

A retrieval-enabled version needs these live cases added to the dataset and run.
They need a person-approved, loaded index and the customer flow chosen in
[#122](https://github.com/michael-rechani/foundry-agent-accelerator/issues/122),
because through the coordinator only the answer's citations are visible. What
was tried by hand, and what hasn't run, is in
[Pilot results](#pilot-results-2026-10-01):

- A question that one sample passage answers must be answered and cite that
  passage's `source_id`, one of the ten in
  [`policy-guidance.json`](../hosted-agents/knowledge-sample/policy-guidance.json).
  A question that nothing matches must say no guidance was found.
- A lookup-failure case that must say no guidance is available.
- Prompt-injection passages in the index that try to change format, tools, or
  the decision boundary. This needs an extra passage in the shared index.
- Checks that supplied facts and retrieved guidance stay separate, and that no
  `source_id` is invented. Nothing in the runtime checks for an invented
  `source_id`, so this case depends on a person reading the answer.

Offline tests already cover how the code handles an injected passage, no
match, a lookup failure, and a cited paraphrase; the live cases show whether
the model behaves the same way.

## Cost

- Uses the existing Agent Service Search service. No new Search service or tier
  change, so no new hourly charge. The dev pilot's live-check cost is in
  [Pilot results](#pilot-results-2026-10-01).
- A small dedicated index adds storage within the service's existing capacity.
  Simple keyword queries don't use semantic ranker or vector billing.
- Each lookup adds model tokens for the retrieved passages, at most 8,000
  characters per call.
- Monitor Search query load before changing replicas; see
  [cost and capacity notes](optional-integrations.md#cost-and-capacity-notes).

## Operator rollout

Every step that creates, loads, or removes data, assigns a role, or publishes
needs explicit approval first. The [pilot results](#pilot-results-2026-10-01)
show how these steps ran in the dev Lab.

1. Take a read-only inventory of the Search service: its indexes, the project's
   vector stores, who owns each, and how each would be rebuilt or removed. Stop
   if anything is unexpected. See [Shared Search cautions](#shared-search-cautions).
2. Get approval for the sample set (its version and digest from `plan`), the
   index name, the temporary operator roles, and the case agent's access.
3. From the private network, run `plan`, then `load --confirm` as the approved
   operator. It creates the dedicated index, uploads the passages, and ends with
   `verify`; confirm it reports the approved version and digest. Remove the
   temporary operator roles afterward. See
   [Sample documents and the index script](#sample-documents-and-the-index-script).
4. Find the `case-review-agent` runtime `instance_identity.principal_id` and
   assign **Search Index Data Reader** scoped to the index.
5. Install the knowledge dependency in the deployment environment:
   `pip install -r requirements.txt -r requirements-knowledge.txt`.
6. Set `KNOWLEDGE_RETRIEVAL_ENABLED=true`, `KNOWLEDGE_SEARCH_ENDPOINT`, and
   `KNOWLEDGE_SEARCH_INDEX`, then run `python deploy.py` from
   `hosted-agents/case-review-agent`. Do this in a quiet window: the new version
   takes 100% of traffic before its smoke checks run. The retrieval smoke check
   must pass (at least one passage for the query "missing evidence"). It retries
   once, and says so, if the model made no lookup. If it fails, the script
   attempts a rollback; confirm the route yourself afterward.
7. Update the Lab as described in [Receipts in the Lab](#receipts-in-the-lab):
   the case-review entry's `configuration`, `delegation`, and `limits` text, and
   the Add-ons card. Don't add a `tools` binding for an optional lookup. Then
   run the [evaluation additions](#evaluation-additions).
8. To turn retrieval off, redeploy with the flag unset or `false`, or route back
   to the previous version. Remove the role assignment when it's no longer
   needed. If nothing else uses the sample index, `remove --confirm` deletes it,
   which needs the temporary operator roles again.

## Not done

This lists what the design deliberately leaves out. Gaps found in the pilot and
open work are in [Pilot results](#pilot-results-2026-10-01) and tracked in
[#122](https://github.com/michael-rechani/foundry-agent-accelerator/issues/122).

- No change to the default case agent files, the application agent, the
  coordinators' instructions, or bundles.
- No evaluation dataset change. The runner's fingerprint change, described in
  [Evaluation additions](#evaluation-additions), is the only evaluation change.
- No Foundry Azure AI Search tool, toolbox, or context provider integration.
- No vector, hybrid, or semantic search, and no document-level authorization.
- No search over a visitor's own documents. The Lab has no sign-in to keep them
  private.

## Open decisions

- Run a staging comparison with the Foundry Azure AI Search tool or a toolbox,
  and decide whether its identity model is acceptable.
- Whether the Checklist reviewer should also get retrieval.
- How to surface specialist tool receipts through the coordinator.
- Whether retrieval-enabled portable bundles are needed.
- Who owns the index, the sample document set, and its update process.
- Whether to use the Agent Service Search service or a separate one for
  retrieval indexes.
- Whether to reduce the project identity's Contributor roles. That's out of
  scope here and may affect Foundry Agent Service.
- Whether to keep the pilot on. The Customer review demo is the flow that shows
  it, through the coordinator. Decide that, and whether to check the document
  Reviews flow too, before customers see it. See
  [#122](https://github.com/michael-rechani/foundry-agent-accelerator/issues/122).

## Pilot results (2026-10-01)

This section is a dated snapshot, not part of the design. It records one sample
pilot in the dev environment on 2026-10-01 and doesn't update itself. For current
status and open work, see
[#122](https://github.com/michael-rechani/foundry-agent-accelerator/issues/122).

The pilot ran after the written go-ahead on
[#122](https://github.com/michael-rechani/foundry-agent-accelerator/issues/122#issuecomment-5940369558).
It used the platform's existing Search service, so it added no new resource.
Every Azure step below was made by hand, not by Terraform.

**Where it stood on 2026-10-01.** An index of ten fictional passages existed,
version 8 of the case agent had the lookup on, and the Lab's Add-ons tab said so.
Some live cases hadn't run, and no person had reviewed the recorded answers.

| Step | What happened |
| --- | --- |
| Read-only inventory | The Search service is Basic with one replica, reachable only privately, and sign-in only. The chosen index name was unused. The Agent Service's own index was left alone. |
| Approved sample set | Version `sample-v1`, ten passages, digest `c7d68e26c329e8b0`. |
| Index `lab-sample-policy-guidance` | `load --confirm` created it and uploaded the ten passages, and its `verify` step passed, including the "missing evidence" query. It ran from a machine with private network access, with both temporary operator roles in place. That first approved run didn't test whether either role alone would have been enough. |
| Temporary operator roles | Search Service Contributor and Search Index Data Contributor were removed straight after the load. |
| Case agent access | Search Index Data Reader, scoped to the one index, for the case agent's runtime identity. It stays while retrieval is on. Made by hand. It was imported into Terraform state on 2026-10-04 (`knowledge_search_access`, [#143](https://github.com/michael-rechani/foundry-agent-accelerator/issues/143)). |
| Case agent version 8 | Published with the flag on. Both deploy smoke checks passed, including the `search_policy_guidance` lookup, so DNS, network, and RBAC work together. Version 7, without the lookup, stays published as the rollback. The application agent and both coordinators weren't changed. |
| Lab descriptions | `agents.json` and the Add-ons tab describe the pilot. See [Receipts in the Lab](#receipts-in-the-lab). |

The live checks used fictional input only:

| Check | Where | Result |
| --- | --- | --- |
| A question one passage answers | The case agent, directly | One lookup. The answer paraphrased the passage and cited `POL-EVID-001`, and every cited ID was in the approved set. |
| A question nothing matches ("staff parking permit") | The case agent, directly | One lookup. The search still returned three loosely related passages, because it matches any query word. The answer said that no passage defined the rule. |
| A question one passage answers | The Lab's chat, Checklist and case helper | Answered in about 35 seconds. It paraphrased the passage, named it as sample guidance `POL-EVID-001`, and showed "Asked another agent". Nothing was saved. |
| The "Summarize case notes" example | The Lab's chat | Answered in about 34 seconds. It quoted the notes exactly, showed both conflicting dates, and said no policy was supplied. It made no lookup and named no `POL-*` source, which is right because the notes say no written policy exists. |
| Application logs | Log Analytics, 21:07 to 21:23 UTC | Every request returned 200 and completed. No errors, warnings, or secrets. |

The agent that ran the checks read these answers. No person has reviewed them
yet, so the pilot isn't signed off.

**Cost.** The pilot added no hourly charge. Its live checks used a few cents of
model use.

**Evaluation cases.** The live dataset has no retrieval cases yet. Against the
cases listed in [Evaluation additions](#evaluation-additions):

- A question that one sample passage answers, and a question nothing matches:
  tried by hand and answered as expected. Not in the dataset.
- A lookup failure: not run.
- Prompt-injection passages: not run. It needs an extra passage in the shared
  index.
- Separate supplied facts and retrieved guidance, and no invented `source_id`: a
  script compared the cited IDs in the direct answers with the approved set. No
  person has read the answers yet.

**Open at 2026-10-01.**

- **The dev Lab's grant wasn't in Terraform state.** The index, the Search
  Index Data Reader assignment, and the retrieval-enabled version were made by
  hand. Platform Terraform declares the assignment and tests it, off by default
  (`knowledge_search_access`). **Resolved 2026-10-04:** the existing grant was
  imported ([#143](https://github.com/michael-rechani/foundry-agent-accelerator/issues/143)).
  The plan showed 1 to import and nothing to add, change or destroy, and a later
  plan showed no changes. The index and the retrieval-enabled version are still
  outside Terraform. See
  [Adopt the knowledge-search grant](permissions.md#adopt-the-knowledge-search-grant).
- **Two live cases haven't run.** A failed lookup needs a deliberate fault. A
  poisoned passage needs an extra passage in the shared index. Each needs
  approval.
- **The document Reviews flow hasn't been tried with the lookup on.** It saves a
  review record to shared storage, so it needs approval.
- **No person has reviewed the recorded answers.** Don't treat the pilot as
  signed off
  ([#87](https://github.com/michael-rechani/foundry-agent-accelerator/issues/87)).
- **No retrieval cases in the evaluation dataset yet.**
- **The lookup matched any query word.** Version 8 returned three passages for
  "staff parking permit". The code now requires every word (see
  [Tool contract](#tool-contract)). Version 10, published on 2026-10-03, has the
  fix. See [Follow-up (2026-10-03)](#follow-up-2026-10-03)
  ([#144](https://github.com/michael-rechani/foundry-agent-accelerator/issues/144)).

## Follow-up (2026-10-03)

This section is also a dated snapshot. It records the republish that the last open
item above waited for, after written approval on
[#144](https://github.com/michael-rechani/foundry-agent-accelerator/issues/144).
It used the same index and made no change to Search, so it added no resource.

The case agent was republished with the flag on as version 10. It carries the
strict query matching and the explicit search timeouts added since version 8. The
application agent and both coordinators weren't changed.

| Step | What happened |
| --- | --- |
| First attempt, version 9 | The general smoke check passed. The lookup check failed because the response didn't hold exactly one `search_policy_guidance` call. The script moved traffic back to version 8 and deleted version 9. An inventory confirmed version 8 at 100%. |
| Second attempt, version 10 | Both smoke checks passed. Version 10 has 100% of traffic. Version 8 stays published as the rollback. |

| Check | Where | Result |
| --- | --- | --- |
| "staff parking permit", fictional input | The case agent, directly, 2 tries | One lookup each time, and it returned no passages. Version 8 returned three loosely related ones. |
| "missing evidence", the deploy check's prompt | The case agent, directly, 11 tries on version 10 | One lookup that returned `POL-EVID-001` in 8 tries. No lookup in 3. Version 8 made one lookup in 3 of 3 tries, too few to tell the versions apart. |

In the one no-lookup reply that was read, the text said guidance had been
"retrieved" although no lookup ran. The lookup is optional, so the model may skip
it (see [Receipts in the Lab](#receipts-in-the-lab)). It also means the deploy
check can fail on a good build, as version 9 did. Making the model call the lookup
reliably, and the deploy check tolerant of a skip, is
[#219](https://github.com/michael-rechani/foundry-agent-accelerator/issues/219).

Since then, the deploy check retries once when the first attempt makes no lookup,
and reports the retry (see [What the flag changes](#what-the-flag-changes)). That
helps a good build get past a skip. It doesn't measure or reduce skips. The skip
rate is still unknown. The only counts are the ones above: on version 10, a
lookup in 8 of 11 direct tries and none in 3, and on version 8, a lookup in 3 of
3. That is too few for a rate. Measuring it with live runs, and any change to the
instructions or the tool description to make a skip rare, need a person's
approval and stay open in [#219](https://github.com/michael-rechani/foundry-agent-accelerator/issues/219).

## Sources

Checked in September 2026.

- [Connect an Azure AI Search index to Foundry agents](https://learn.microsoft.com/azure/foundry/agents/how-to/tools/ai-search):
  project connection, `top_k` and query type, vector-index prerequisite,
  project managed identity with Search Index Data Contributor and Search Service
  Contributor, keys unsupported for private networks, and toolboxes for hosted
  agents.
- [Toolbox overview](https://learn.microsoft.com/azure/foundry/agents/concepts/toolbox-overview):
  Azure AI Search through a toolbox or as a direct tool; some toolbox features
  are preview.
- [Hosted agents](https://learn.microsoft.com/azure/foundry/agents/concepts/hosted-agents):
  each hosted agent has a dedicated Microsoft Entra agent identity used at
  runtime for downstream Azure services.
- [Foundry Agent Service virtual networks](https://learn.microsoft.com/azure/foundry/agents/how-to/virtual-networks):
  network injection, the `privatelink.search.windows.net` zone, and bring-your-own
  Search.
- [Azure AI Search RBAC](https://learn.microsoft.com/azure/search/search-security-rbac):
  Search Index Data Reader is read-only, data roles can be scoped to one index,
  Search Service Contributor manages index definitions and can retrieve keys
  but can't load or query documents, and Search Index Data Contributor loads and
  queries documents but can't change definitions.
- [`agent-framework-foundry` 1.13.1](https://pypi.org/project/agent-framework-foundry/1.13.1/):
  `get_azure_ai_search_tool` and `FoundryToolbox`, experimental Foundry tools.
- [`agent-framework-azure-ai-search`](https://pypi.org/project/agent-framework-azure-ai-search/)
  and its [samples](https://github.com/microsoft/agent-framework/tree/main/python/samples/02-agents/context_providers/azure_ai_search):
  beta `AzureAISearchContextProvider` in semantic and agentic modes.
- [Agent Framework Samples: RAGs](https://github.com/microsoft/Agent-Framework-Samples/tree/main/06.RAGs):
  retrieval tutorial using file search.
- [`azure-search-documents` 12.0.0](https://pypi.org/project/azure-search-documents/12.0.0/):
  current GA client.

## Related content

- [Extension guide](architecture-assessment.md)
- [Optional integrations](optional-integrations.md)
- [Permissions reference](permissions.md)
- [Hosted agents](../hosted-agents/README.md)
- [Case notes summarizer](../hosted-agents/case-review-agent/README.md)

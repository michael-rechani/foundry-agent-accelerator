# Knowledge retrieval design

[Home](../README.md) / [Docs](README.md) / Knowledge retrieval design

This design adds an optional, read-only policy guidance lookup to the Case notes
summarizer (`case-review-agent`). The code ships behind the
`KNOWLEDGE_RETRIEVAL_ENABLED` flag, which is **off by default**. With the flag
off, the published agent, its tools and instructions, portable bundles, and
evaluation outputs are unchanged. No Azure resources, Terraform, indexes, or
evaluation datasets are changed by this work.

> [!IMPORTANT]
> **Status: designed and unit-tested only.** No index exists, no role is
> assigned, and no retrieval-enabled version has been deployed or evaluated.
> Nothing in this guide is evidence that retrieval works in a live environment.

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
- [Indexing fictional documents](#indexing-fictional-documents)
- [Receipts in the Lab](#receipts-in-the-lab)
- [Evaluation additions](#evaluation-additions)
- [Cost](#cost)
- [Operator rollout](#operator-rollout)
- [Not done](#not-done)
- [Open decisions](#open-decisions)
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
| Bounded behavior | The code, not the model, fixes the index, `top` (at most 5), the `select` field allowlist, and the simple query type. The model supplies only the query text; it can't pass a filter, index, or field list. |
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
  (for example an empty or wrong index) fails the check.

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
- Calls `search(search_text=query, top=KNOWLEDGE_TOP_K, select=<allowlist>,
  query_type="simple", include_total_count=False)`. No filter, facets, vector,
  semantic ranker, or write operations.
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

## Identity and RBAC

See the [permissions reference](permissions.md) for all current assignments.

| Who | Role | Scope | When |
| --- | --- | --- | --- |
| `case-review-agent` hosted-agent runtime identity (its `instance_identity.principal_id`) | **Search Index Data Reader** (`1407120a-92aa-4202-b7e9-c0e197c71c8f`) | The single approved index: `.../searchServices/<service>/indexes/<index>` | Before publishing a retrieval-enabled version. |
| Operator or indexing identity that loads the fictional documents | Search Index Data Contributor, and Search Service Contributor to create the index | The index, and the service for creation | Only while indexing; remove afterward. |

- Search Index Data Reader can query indexes but can't load documents, change
  definitions, or read admin keys.
- Scope the reader role to the index, not the service. Per-index scoping is
  supported by Azure AI Search.
- Don't use API keys; the service has local authentication disabled.
- Grant the role before publishing. Token caching can delay a late grant, and
  the retrieval smoke check fails closed without it.
- This design doesn't change the project identity's existing Contributor roles,
  which the Foundry Agent Service needs for its own use of the backing Search.

## Private networking

The existing platform already provides the path. This design doesn't change it.

- The Agent Service Search service has `public_network_access_enabled = false`
  and `local_authentication_enabled = false`, with a private endpoint.
- The `privatelink.search.windows.net` private DNS zone is linked to the
  workload virtual network.
- The Foundry account uses network injection into `snet-agent-services`, so
  hosted-agent egress is expected to resolve and reach the private endpoint.

Verify this in staging before relying on it: the retrieval smoke check proves
DNS, network, and RBAC together. If you use a different Search service, it needs
its own private endpoint and DNS link; don't enable public access.

## Index schema

Use a **dedicated index** for fictional guidance, not an index used by Foundry
features. The default settings expect:

| Field | Type | Attributes | Purpose |
| --- | --- | --- | --- |
| `id` | `Edm.String` | Key, retrievable, filterable | Stable citation ID, for example `POL-EVID-001`. |
| `title` | `Edm.String` | Searchable, retrievable | Document title. |
| `section` | `Edm.String` | Searchable, retrievable | Section or clause number. |
| `content` | `Edm.String` | Searchable, retrievable | Passage text, chunked to 2,000 characters or fewer. |
| `version` | `Edm.String` | Filterable, retrievable | Guidance version for freshness checks. Not selected by default. |

No vector fields, semantic configuration, or embedding model are needed for the
simple query type. Adding vector or semantic search is a later change.

## Indexing fictional documents

Indexing is an operator task outside this repository's runtime:

1. Write fictional guidance only, clearly labeled as fictional. Don't use
   customer, staff, or real policy text.
2. Chunk each document into passages of 2,000 characters or fewer and give each
   passage a stable, unique `id`.
3. Create the index and upload documents from the private network with a
   temporary contributor identity. Use the Search REST API or
   `azure-search-documents`; no indexer or data source is required for a small
   fixed set.
4. Review and approve the document set before exposing it to the agent. Record
   the document version.

This repository doesn't include indexing code or fictional guidance documents.

## Receipts in the Lab

`execution_receipts` in [`workbench/app.py`](../workbench/app.py) verifies a
`function_call` and its matching `function_call_output` against the agent's
tool bindings in [`agents.json`](../workbench/agents.json).

- **Direct access to the case agent.** Add
  `"search_policy_guidance": "case-review-agent"` to the case-review entry's
  `tools` in `agents.json` when a retrieval-enabled version is deployed. The
  receipt output then shows the retrieved passages and their `source_id` values.
  Without that binding, the call appears as an unverified receipt.
- **Through the coordinator.** The coordinator receives only the specialist's
  final text, so specialist tool receipts aren't visible in the coordinator's
  output. The answer's citations are the only trace. Surfacing nested receipts
  is an [open decision](#open-decisions).

`agents.json` isn't changed by this work.

## Evaluation additions

The offline dataset and runner aren't changed. Before a retrieval-enabled version
is used in demos, add and run:

- Cases where a supplied fictional passage should be retrieved and cited by
  `source_id`, and cases where nothing matches.
- A lookup-failure case that must say no guidance is available.
- Prompt-injection passages in the index that try to change format, tools, or
  the decision boundary.
- Checks that supplied facts and retrieved guidance stay separate, and that no
  `source_id` is invented.
- Recording the `KNOWLEDGE_*` settings in the live evaluation's configuration
  digest. [`evaluations/run.py`](../evaluations/run.py) doesn't include them
  today, and adding them would change digests for existing agents.

## Cost

- Uses the existing Agent Service Search service. No new Search service or tier
  change.
- A small dedicated index adds storage within the service's existing capacity.
  Simple keyword queries don't use semantic ranker or vector billing.
- Each lookup adds model tokens for the retrieved passages, at most 8,000
  characters per call.
- Monitor Search query load before changing replicas; see
  [cost and capacity notes](optional-integrations.md#cost-and-capacity-notes).

## Operator rollout

1. Get approval for the fictional document set, index name, and the case
   agent's access.
2. From the private network, create the dedicated index and upload the fictional
   documents with a temporary contributor identity. Remove that access afterward.
3. Find the `case-review-agent` runtime `instance_identity.principal_id` and
   assign **Search Index Data Reader** scoped to the index.
4. Install the knowledge dependency in the deployment environment:
   `pip install -r requirements.txt -r requirements-knowledge.txt`.
5. Set `KNOWLEDGE_RETRIEVAL_ENABLED=true`, `KNOWLEDGE_SEARCH_ENDPOINT`, and
   `KNOWLEDGE_SEARCH_INDEX`, then run `python deploy.py` from
   `hosted-agents/case-review-agent`. Do this in a quiet window: the new version
   takes 100% of traffic before its smoke checks run. The retrieval smoke check
   must pass (at least one passage for the query "missing evidence"). If it
   fails, the script attempts a rollback; confirm the route yourself afterward.
6. Add the Lab binding described in [Receipts in the Lab](#receipts-in-the-lab),
   then run the [evaluation additions](#evaluation-additions).
7. To turn retrieval off, redeploy with the flag unset or `false`, or route back
   to the previous version. Remove the role assignment when it's no longer needed.

## Not done

- No Terraform or Azure changes, including role assignments and networking.
- No index, documents, indexer, data source, or Search connection created.
- No deployment of a retrieval-enabled version and no live verification.
- No change to the case agent's `main.py`, `requirements.txt`, or
  `instructions.md`, the application agent, the coordinator, or bundles.
- No Lab configuration change in `agents.json`.
- No evaluation dataset or runner change.
- No Foundry Azure AI Search tool, toolbox, or context provider integration.
- No vector, hybrid, or semantic search, and no document-level authorization.

## Open decisions

- Run a staging comparison with the Foundry Azure AI Search tool or a toolbox,
  and decide whether its identity model is acceptable.
- Whether the Checklist reviewer should also get retrieval.
- How to surface specialist tool receipts through the coordinator.
- Whether retrieval-enabled portable bundles are needed.
- Who owns the index, the fictional document set, and its update process.
- Whether to use the Agent Service Search service or a separate one for
  retrieval indexes.
- Whether to reduce the project identity's Contributor roles. That's out of
  scope here and may affect Foundry Agent Service.
- Which evaluation cases to add, and whether to include `KNOWLEDGE_*` settings
  in evaluation digests.

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
  Search Index Data Reader is read-only, and data roles can be scoped to one
  index.
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

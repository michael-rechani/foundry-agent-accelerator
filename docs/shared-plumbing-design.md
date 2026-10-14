# Shared plumbing design

[Home](../README.md) / [Docs](README.md) / Shared plumbing design

This note is the first piece of [#164](https://github.com/michael-rechani/foundry-agent-accelerator/issues/164).
It reads the code as it is today, picks one shared home for each repeated piece
of plumbing, and sets the order of the follow-up pull requests. It changes no
code. Each follow-up moves one helper, and the existing tests prove that
nothing moved.

The goal is that a rule or a fact about an agent lives in one place. The four
areas are request admission, validation rules, hosted-agent start-up and
per-agent metadata.

> [!NOTE]
> This is a design for contributors, not a promise to build every step. A step is
> done when its pull request merges. Anything that would change behaviour is
> listed under [What would change behaviour](#what-would-change-behaviour) and
> gets its own pull request and test.

## The order

Each step is one pull request. Steps with the same number can run in parallel
because they touch different folders.

| # | Pull request | Needs first | Changes behaviour? |
| --- | --- | --- | --- |
| 1 | [#155](https://github.com/michael-rechani/foundry-agent-accelerator/issues/155): one source for the Lab module list | Nothing | No |
| 1 | [#153](https://github.com/michael-rechani/foundry-agent-accelerator/issues/153): `request_id`, exception type and telemetry order in error handling | Nothing | Yes, on purpose |
| 1 | [#166](https://github.com/michael-rechani/foundry-agent-accelerator/issues/166): validation gaps in the library checks and scorecards | Nothing | Yes, on purpose |
| 2 | Admission A: `is_json` and `api_error` in `request_guard.py` | #153 | No |
| 2 | Start-up A: tests for the three hosted `main.py` files that have none | Nothing | No (tests only) |
| 3 | Admission B: `RateGate` in `request_guard.py` | Admission A | No |
| 3 | Start-up B: `hosted-agents/hosted_runtime.py` | Start-up A | No |
| 3 | Validation A: `workbench/library_rules.py` constants and small checks | #155, #166 | No |
| 4 | Admission C: `read_json_body` in `request_guard.py` | Admission B | No |
| 4 | Validation B: evidence row shapes and drift-guard tests | Validation A | No |
| 5 | Admission D: `cosmos_failure` in `request_guard.py` | Admission C | No |
| 5 | Metadata: one data file per library agent ([#215](https://github.com/michael-rechani/foundry-agent-accelerator/issues/215)) | [#165](https://github.com/michael-rechani/foundry-agent-accelerator/issues/165), and the `readiness="reviewed"` flips ([#87](https://github.com/michael-rechani/foundry-agent-accelerator/issues/87)) | No |

The admission steps touch `app.py`, `history.py`, `agent_creation.py` and
`review_runs.py`, so they wait for #153 and for the `history.py` change in
[#152](https://github.com/michael-rechani/foundry-agent-accelerator/issues/152).
Start-up B edits the package lists in `hosted-agents/deployment.py`, so it waits
for the timeout change in [#159](https://github.com/michael-rechani/foundry-agent-accelerator/issues/159)
or rebases on it.

## How this overlaps with open issues

| Issue | Where it overlaps | What this design does |
| --- | --- | --- |
| [#153](https://github.com/michael-rechani/foundry-agent-accelerator/issues/153) | It changes the same `error` methods in `agent_creation.py` and `review_runs.py` that the admission helper replaces. | #153 lands first as a small in-place fix. The helper then copies the already-fixed shape, so the admission pull requests have no behaviour change to carry. |
| [#155](https://github.com/michael-rechani/foundry-agent-accelerator/issues/155) | A new `workbench/` module has to be added to the `Dockerfile` COPY line, `.dockerignore`, `test-build.ps1`, `build.ps1` and CI. | Admission extends the existing `request_guard.py`, so it pays nothing. Only `workbench/library_rules.py` is new, so Validation A waits for #155. This note doesn't touch the module-list problem. |
| [#165](https://github.com/michael-rechani/foundry-agent-accelerator/issues/165) | It split `workbench/agent_templates.py` into the `workbench/agent_templates/` package and kept the catalog snapshot byte-identical. | The split has landed. The metadata step built on the package and kept the snapshot byte-identical (#215). |
| [#166](https://github.com/michael-rechani/foundry-agent-accelerator/issues/166) | It fixes gaps in the same checks that Validation A consolidates, for example `identifier.lower()` on a non-string fixture ID in `library_checks.py`, and truthy strings accepted by `agent_scorecards.py`. | #166 lands first in the current files. Validation A then moves the stricter rules without loosening them. |

## 1. Request admission

### Where it is today

`workbench/request_guard.py` already holds the shared pieces:
`MAX_REQUEST_BYTES`, `MAX_CONVERSATION_BYTES`, `MAX_SETUP_BYTES`,
`BodyReadTimeout`, `read_bounded_body(request, limit)`,
`record_request_failure(request, problem, dependency)` and
`request_allowed(request, origins)`. Admission A added `is_json(request)` and
`api_error(request, status, code, *, retry_after=None, **extra)`. All four
routers import them. What each router still repeats is the glue around them:

| Router | Busy check | Busy code | Error body has `request_id` | Check order |
| --- | --- | --- | --- | --- |
| `app.py` `ChatReviews` | Shared 4-slot semaphore and 20 a minute, then a per-model budget (`model_budget.py`) after the agent is resolved | `busy` | Yes | Rate limit, origin, content type, body, agent, model budget |
| `history.py` `ConversationHistory` | Own 4-slot semaphore, 60 a minute | `history_busy` | Yes | Rate limit, origin |
| `agent_creation.py` `AgentCreations` | Own 4-slot semaphore, 120 a minute | `agents_busy` | No | Origin, rate limit |
| `review_runs.py` `ReviewRuns` | Own read gate (120 a minute); `start` uses the shared chat gate | `reviews_busy`, `busy` | No | Origin, id check, rate limit |

Smaller differences that the helper has to keep, or change on purpose:

- The content-type test used to be `.split(";")[0].strip().lower()` in `app.py`
  and `agent_creation.py`, but `.split(";")[0]` with no strip or lowercase in
  `history.py` and `review_runs.py`. All four now call `is_json`, which uses the
  first rule (see [What would change behaviour](#what-would-change-behaviour)).
- A wrong content type is 415 `json_required` in three routers, but a 400
  `invalid_setup` in `agent_creation.py`.
- Too much data is `conversation_too_large` in `history.py` and
  `request_too_large` elsewhere.
- The Cosmos error mapping (404, and a version conflict, to a domain code,
  anything else to a 503 plus `record_request_failure(..., "cosmos")`) was written
  out three times, in `history.py`, `agent_creation.py` and `review_runs.py`. The
  conflict is 412 in `history.py` and `review_runs.py`, but 409 or 412 in
  `agent_creation.py`, which creates records.
- The `X-Correlation-ID` header already comes from the `security_headers`
  middleware in `app.py` for every `/api/` response, so only the body's
  `request_id` differs.

The browser maps these codes to messages (`history-client.ts`,
`agent-creation-client.ts`, `review-client.ts`), so a code is part of the
contract. Every helper takes the code as a parameter.

### Shared home: `workbench/request_guard.py`

Status: `is_json` and `api_error` (Admission A), `RateGate` (Admission B) and
`RequestRejected` with `read_json_body` (Admission C) and `cosmos_failure`
(Admission D) are in place and the routers use them. All four admission steps are
done.

Extend the file all four routers already import. It is already in every module
list and has `workbench/test_request_guard.py`, so this adds no new module. The
helpers are small pieces a router calls in its own order. That keeps each
router's present check order, which is why the extraction changes nothing.

```python
def is_json(request) -> bool
    # one content-type rule: split(";")[0].strip().lower() == "application/json"

def api_error(request, status, code, *, retry_after=None, **extra) -> JSONResponse
    # sets request.state.error_code; body {"error": code, "request_id": ..., **extra};
    # adds Retry-After when given

class RateGate:
    def __init__(self, per_minute, concurrent=4, window_seconds=60.0): ...
    slots: asyncio.Semaphore      # `async with gate.slots:`, or acquire() and release() across a background task
    def try_admit(self, now=None) -> bool
        # prune old requests; False if the window or every slot is full (counting nothing); else record

class RequestRejected(Exception):   # .status, .code
async def read_json_body(request, limit, *, too_large="request_too_large",
                         wrong_type=(415, "json_required")) -> bytes
    # raises RequestRejected for wrong type, too large (413) or slow body (408)

def cosmos_failure(request, problem, *, missing, changed, unavailable, conflicts=(412,)) -> JSONResponse
    # 404 -> api_error 404 `missing`; a status in `conflicts` -> 409 `changed`;
    # anything else -> record_request_failure(..., "cosmos") and 503 `unavailable`
```

How each router uses it:

- `ChatReviews` and `ReviewRuns.start` share one `model_gate = RateGate(20, 4)`
  that `app.py` builds and passes in, replacing the shared `slots` and `recent`.
- `ConversationHistory` uses `RateGate(60, 4)`, `AgentCreations` uses
  `RateGate(120, 4)` and `ReviewRuns` read paths use `RateGate(120, 4)`.
- `AgentCreations` passes `wrong_type=(400, "invalid_setup")` and
  `ConversationHistory` passes `too_large="conversation_too_large"`, so both
  keep their current answers.
- Each router's own JSON validation stays where it is. The validators differ
  and aren't repeated.

Admission D is `cosmos_failure`. It returns the response itself instead of a
`(status, code)` pair, because all three callers wrapped that pair in
`api_error` anyway. `agent_creation.py` passes `conflicts=(409, 412)` and the
others keep the default. Each router has a test that pins its three codes, and
`workbench/test_request_guard.py` covers the helper. The router tests passed
unchanged against the old copies.

Not chosen: a new `admission.py`. It would cost a module-list edit in four
places for no benefit, and it would split the guard code across two files.

## 2. Validation rules

### Where it is today

| Rule | Copies today |
| --- | --- |
| The five answer categories (`grounded`, `missing`, `conflict`, `injection`, `decision-boundary`) | `evaluations/library_checks.py` and `workbench/agent_scorecards.py` |
| The deployment-name pattern `[A-Za-z0-9][A-Za-z0-9_.-]{0,127}` | `workbench/agent_creation.py` and `evaluations/library_runs.py` |
| The profile-to-deployment map check | `CreationSettings.validate` in `agent_creation.py` and `resolve_models` in `library_runs.py` |
| A real integer, not a boolean | `usable` in `library_runs.py`; `_measured` and `load_repeats` in `scorecards.py`; `load_scorecards` in `agent_scorecards.py` |
| Date check | `_valid_date` in `scorecards.py`, which `library_runs.py` imports although it is private |
| Evidence row keys | `ANSWER_ROW`, `METRICS_ROW` and `RUN_ROW` in `library_runs.py` (writer) and `METRIC_KEYS` in `scorecards.py` (reader) |

The scorecard JSON has a producer, `evaluations/scorecards.build()`, and a
consumer, `workbench/agent_scorecards.load_scorecards`, and the two sides check
the shape separately. `evaluations/test_scorecards.py` already fails if the Lab's
copy and the recorded evidence disagree.

### Shared home: a new `workbench/library_rules.py`

Status: Validation A is done. `workbench/library_rules.py` holds the constants and
checks below, and the five consumers import them. `evaluations/test_shared_rules.py`
and `workbench/test_library_rules.py` assert that each consumer uses the one copy,
and that the Lab and the recorder accept and refuse the same model maps.

Validation B is done too. `ANSWER_ROW`, `METRICS_ROW`, `RUN_ROW`, `COUNT_KEYS` and
`METRIC_KEYS` moved into the same module, so the writer (`library_runs.py`) and
the reader (`scorecards.py`) can't disagree on a row's keys, and a test checks that
every row in the recorded evidence has exactly those keys in that order. The copies
below stay separate, and `workbench/test_rule_copies.py` feeds the same examples to
all of them. Writing that test found three differences, which are now fixed: the
two evaluation copies accepted any host and the three Lab and hosted copies
accepted a URL with only a password (`https://:secret@...`) or with path
parameters (`;x=1`).

The code can only be shared in one direction. The Lab image contains only
`workbench/`, while `evaluations/` already puts `workbench/` on `sys.path`
(`library_checks.py` lines 16 to 18). So the single source has to live in
`workbench/`.

It should be a new pure module, not `agent_scorecards.py`. Importing
`agent_scorecards.py` loads and checks a 93 KB JSON file (18 scorecards), a side
effect nobody wants just to read a regular expression. #155 is closed, so a new
`workbench/` module needs no edit to the `Dockerfile`, `build.ps1`, `test-build.ps1`
or CI.

```python
CATEGORIES = frozenset({"grounded", "missing", "conflict", "injection", "decision-boundary"})
DEPLOYMENT_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
def is_int(value) -> bool                    # real int, not bool
def is_number(value) -> bool                 # int or float, not bool
def valid_date(text) -> bool                 # moved from scorecards._valid_date
def is_profile_map(value, profiles) -> bool  # the one profile -> deployment rule
# Validation B adds ANSWER_ROW, METRICS_ROW, RUN_ROW and METRIC_KEYS here.
```

`library_checks.py`, `library_runs.py`, `scorecards.py`, `agent_scorecards.py`
and `agent_creation.py` import these names. The behaviour of #166 stays: a
boolean is still not an integer, and a non-string ID is still rejected.

### Copies that can't be shared

Some checks sit in code that ships as a standalone zip, which doesn't contain
`workbench/`:

- The Foundry project endpoint rule (https, `.services.ai.azure.com`,
  `/api/projects/<name>`, no credentials, path parameters, query or fragment,
  port 443) is in
  `hosted-agents/bundle.py`, `evaluations/library_runs.py`, `evaluations/run.py`,
  `workbench/agent_runtime/main.py` and `workbench/app.py`.
- The agent-name pattern `[A-Za-z_][A-Za-z0-9_-]{0,63}` is in `app.py` and in
  `hosted-agents/review-coordinator-agent/configuration.py`.

Don't force these into one file. `workbench/test_rule_copies.py` asserts that the
copies accept and reject the same examples, so a change in one place fails until
the others match. Merging the endpoint copies later is optional.

## 3. Hosted-agent start-up

### Where it is today

Status: done. `hosted_runtime.py` is in place and the case-review,
application-review and coordinator agents and `knowledge_main.py` use it.
`hosted-agents/test_startup.py` also builds each package and starts it with only
its own files importable. The basic-responses agent stays separate, for the reason
under "Left separate on purpose". This section keeps the original design for the
record, and the code block below shows the final signatures.

Five `main()` functions did the same job:
`hosted-agents/{basic-responses,case-review,application-review,review-coordinator}-agent/main.py`
and `hosted-agents/knowledge_main.py`. The last one is packaged as `main.py` when
`KNOWLEDGE_RETRIEVAL_ENABLED=true`. Each one:

1. Reads `FOUNDRY_PROJECT_ENDPOINT` and `FOUNDRY_MODEL_NAME` and raises
   `RuntimeError("FOUNDRY_PROJECT_ENDPOINT and FOUNDRY_MODEL_NAME must both be set")`.
2. Reads `AGENT_STORE_RESPONSES`.
3. Opens a credential.
4. Builds `Agent(client=FoundryChatClient(..., allow_preview=True), name=AGENT_NAME,
   instructions=AGENT_INSTRUCTIONS or instructions.md, default_options={"store": ...})`.
5. Runs `ResponsesHostServer(agent).run_async()`.

They differ in three ways: middleware (none, `quotation_middleware()` or
`passthrough_middleware(bindings)`), tools (none, knowledge lookups or the
coordinator's specialist calls) and the credential (the coordinator uses the
async one). Each now has a start-up test. The basic-responses, case-review and
application-review agents share `hosted-agents/test_startup.py`, which pins the
settings error, the defaults, the `AGENT_NAME` and `AGENT_INSTRUCTIONS`
overrides, the `AGENT_STORE_RESPONSES` rule and the middleware. The same file
starts the coordinator from its built package. `knowledge_main.py` is covered
next to the retrieval tests in `test_knowledge_retrieval.py`.

The `deploy.py` files are already thin: each builds an `AgentProfile(...)` and
calls `deployment.run(...)`. What is left is data (name, description, smoke-test
prompt), so those stay as they are.

### Shared home: a new `hosted-agents/hosted_runtime.py`

A hosted agent is uploaded as a standalone zip, so a shared start-up file has to
ship inside it, the way `review_output.py` already does. The module owns the
settings and the agent build. The credential stays in each `main.py`, because
the coordinator needs the async one and the knowledge agent needs the credential
to build its tools.

```python
class AgentSettings(NamedTuple): endpoint, model, name, instructions, store_responses
def agent_settings(default_name, default_instructions, environ=None) -> AgentSettings
    # same RuntimeError text; runs before any credential is opened
def build_agent(credential, settings, *, middleware=(), tools=()) -> Agent
async def serve(agent) -> None                                 # ResponsesHostServer(agent).run_async()
```

`build_agent` passes `middleware` and `tools` only when there are some, because the
basic agent has no middleware and `knowledge_main.py` leaves `tools` out when the
knowledge flag is off. `knowledge_main.py` builds its tools from the credential, so
it reads the settings first, adds the knowledge addendum to `settings.instructions`
and passes the tools in. After the change a `main.py` is about a dozen lines.

Shipping it meant one list and one limit, in the same pull request. `SHARED_FILES`
in `hosted-agents/deployment.py` lists the files beside `deployment.py` that a
review sample imports (`review_output.py` and `hosted_runtime.py`), and
`create_package` and `knowledge_package` both ship them. `bundle.py` allows the
same names through `PACKAGE_FILES`, which also sets the entry limit that
`zip_contents` enforces. That limit was a hard-coded 5, and a sixth file in the
coordinator package would have failed every export. Old bundles that lack
`hosted_runtime.py` still validate, because the file is allowed, not required.

### Left separate on purpose

`hosted-agents/basic-responses-agent/main.py` keeps its own start-up. Its job is to
be the smallest working hosted agent, one file you can read top to bottom, and its
package stays at `main.py`, `requirements.txt` and `instructions.md`. Moving the
start-up into a second file would cost that for a gain of about fifteen lines.
`test_startup.py` still pins its behaviour to the same contract.

`workbench/agent_runtime/main.py` stays as it is. It is the runtime for agents
created in the Lab and is a different codebase: it reads its settings through its
own `read_configuration`, prefixes a `DEMO_POLICY`, and ships in a fixed
three-file package (`RUNTIME_FILES` in `workbench/agent_package.py`, each file at
most 65,536 bytes). Adding a shared file would change that package's hash and
size limits for a gain of about ten lines.

## 4. Per-agent metadata

Status: done. The three other areas were done first, and #164 is closed. This step
was tracked in [#215](https://github.com/michael-rechani/foundry-agent-accelerator/issues/215).
It landed before the `readiness="reviewed"` flips in #87, which the issue allows, so
those sign-offs are made in the new per-agent files. The sections below keep the
original design for the record, then "Result" says what changed and what didn't.

### Where it is today

"Adding an agent" means one of two different jobs:

- A **library agent** (21 templates, 18 listed and 3 retired) that Lab users
  create from.
- A **prebuilt hosted agent** (4 entries in `workbench/agents.json`) that a
  developer publishes.

The six places in the issue split the same way:

| Place | What it holds | Per agent or per file? |
| --- | --- | --- |
| `workbench/agent_templates/` | Before #215, the sector modules (`cross_sector.py`, `private_sector.py`, `public_sector.py`) held `TEMPLATES` and `METADATA` per agent (including `readiness`), `catalog.py` assembled `TEMPLATES`, `LIBRARY_ORDER` and `TEMPLATE_METADATA` from them, and `_shared.py` declared lookup tools with `_tool(...)`. Now `agents/<id>.json` holds all of it for one agent | Per library agent |
| `workbench/agent_runtime/demo_tools.py` | `TEMPLATE_IDS`, the sample records, the lookup functions and the dispatch table | Per library agent; only 7 of 21 use lookups |
| `workbench/agent_scorecards.json` | Recorded results | Generated by `evaluations/scorecards.py` from `evaluations/library-cases.json` and the evidence, not edited by hand |
| `workbench/agents.json` | One entry per prebuilt hosted agent (1 to 16, checked by `load_agents`) | Per prebuilt agent |
| `workbench/Dockerfile` and `workbench/build.ps1` | File lists | Per file, not per agent (covered by #155) |

Adding a library agent also means regenerating the frontend's catalog snapshot
(`workbench/frontend/tests/agent-templates.fixture.json`). Adding a prebuilt agent
also touches `hosted-agents/<name>/` and the lists that name it:
`deployment.REVIEW_SAMPLES`, `bundle.SAMPLES`, the install steps in
`.github/workflows/validate.yml` and `.github/dependabot.yml`.

Silent drift is already caught. `test_agent_templates.py` asserts
`set(TEMPLATES) == TEMPLATE_IDS` and `set(TEMPLATE_METADATA) == set(TEMPLATES)`,
and `evaluations/test_scorecards.py` checks the `readiness` marking against the
recorded sign-offs. The cost today is the number of edits, not unnoticed errors.

### Shared home

- **Library agents:** one data file per agent, building on the sector modules
  that #165 split out of `agent_templates.py`. The file holds that agent's template entry, its metadata
  and readiness, and its tool declarations, plus an `order` number that replaces
  `LIBRARY_ORDER`. The loader rebuilds `TEMPLATES`, `TEMPLATE_METADATA` and
  `LIBRARY_ORDER` so the served catalog and the frontend snapshot stay
  byte-identical. The test `test_frontend_catalog_fixture.py` proves it.
- **Sample lookup data:** stays in `agent_runtime/demo_tools.py`. That file ships
  inside the created agent's package and can't import anything from the Lab. The
  existing `TEMPLATE_IDS` test remains the guard. (Update, #225: `TEMPLATE_IDS` is
  now generated; see the bullet on what a new agent touches under "Result".)
- **Prebuilt hosted agents:** keep `agents.json` as the one entry per agent, and
  derive `REVIEW_SAMPLES` and `SAMPLES` from one list in `deployment.py`. YAML
  can't read it, so add a test that every `hosted-agents/*/main.py` folder is named
  in `validate.yml` and `dependabot.yml`.

This gets the goal "one metadata file plus its instructions" for a text-only
library agent. A library agent that uses lookups still needs its sample records
in `demo_tools.py`, and every agent needs its test cases in
`evaluations/library-cases.json`. The final pull request should reword the
issue's checkbox to say so.

### Result

- **Library agents:** `workbench/agent_templates/agents/<id>.json` holds each
  agent's template, metadata (including `readiness`), tool declarations,
  trigger-word `match` patterns and `order`. `_loader.py` rebuilds `TEMPLATES`,
  `TEMPLATE_METADATA` and the matchers, and `catalog.py` serves them. The sector
  modules, `_shared.py` and the `LIBRARY_ORDER` and `RETIRED_TEMPLATES` lists are
  gone. The loader refuses a file with a missing or unknown field, a repeated
  `order`, an id that isn't its file name, or a sector, industry, task, readiness
  or model profile the catalog doesn't know, and says which file. The served
  catalog is unchanged: the snapshot's SHA-256 is the same before and after, and
  `test_frontend_catalog_fixture.py` passes with the snapshot untouched.
- **`definition_order` is gone (#225).** The catalog used to have two orders: the
  library's display order (`order`) and the order the agents were first written in
  (`definition_order`). Callers iterated `TEMPLATES` and the matchers in the second
  one, and the `template_required` answer listed its `candidates` in it. Now there
  is one order. The tables follow `order`, with retired agents last by id, and
  `candidates` come in the order the library lists the agents. So `candidates`
  changes order whenever a task matches several agents. For example,
  `supplier-invoice-reviewer` now comes before `document-intake`, and
  `expense-report-checker` before `document-analyst` or `criteria-checker`. The set
  of candidates and the agent chosen for a task that matches one agent are the same
  as before. Nothing in the Lab's front end reads that order, and the served library
  and the frontend snapshot are unchanged. A file that still has a
  `definition_order` field is refused as an unknown field.
- **A new agent still touches a few places, and the issue's checkbox is reworded
  to say so.** A text-only agent is one file, a run of
  `python -m agent_templates.runtime_ids`, its cases in
  `evaluations/library-cases.json` and a regenerated frontend snapshot. A lookup
  agent also needs its sample records and functions in `demo_tools.py`.
  **Update, #225:** `TEMPLATE_IDS` in `demo_tools.py` is now generated from
  `agents/*.json` by that command, not kept by hand. It stays a literal inside
  `demo_tools.py` because that file ships inside the created agent's package and
  can't import the catalog. Its allowlist is what refuses an unknown template id
  inside that agent, so the generated list holds the same 21 ids as before and the
  package still holds exactly `main.py`, `demo_tools.py` and `requirements.txt`.
  Written at the same width as the old hand list, it is byte-for-byte the same
  text, so the package's `runtime_hash` doesn't change. Ids already in the literal
  keep their place and a new id goes last, so reordering the library, as dropping
  `definition_order` did, doesn't move them either. `test_runtime_ids.py` fails
  when the literal is stale, and `test_agent_templates.py` names the command to
  run. Its three hard-coded counts (21, 18, 18) follow the catalog.
- **Prebuilt hosted agents:** `deployment.PREBUILT_AGENTS` is the one list.
  `bundle.SAMPLES` and `deployment.REVIEW_SAMPLES` are derived from it, and
  `hosted-agents/test_prebuilt_agents.py` checks that every `hosted-agents/*/main.py`
  folder is in it, is named in `validate.yml` (its requirements files and
  `deploy.py --help`) and in `dependabot.yml`, and that its shared-files flag
  matches what its `main.py` imports.
- **Packaging:** `agent_templates/agents/*.json` ships through `.dockerignore`,
  `build.ps1` and `test-build.ps1`, and `test_image_context.py` fails if a library
  agent file isn't let into the image context or `build.ps1` stops staging it.

## What would change behaviour

Ideally nothing. Every step above is a move with the existing tests passing
unchanged, except for these, which are listed so none is a surprise:

| Change | Where | Handled by |
| --- | --- | --- |
| Error bodies from `agent_creation.py` and `review_runs.py` gain `request_id` | Admission | #153, before any helper. It is that issue's change, not this one's |
| A content type such as `Application/JSON ; charset=utf-8` is now accepted by `history.py` and `review_runs.py`, which answered 415 before | Admission A | Deliberate, because `is_json` applies the more lenient rule of `app.py` everywhere. A test covers it. If it isn't wanted, `is_json` takes a flag to keep the old test for those two |
| The strictness rules from #166 (non-string IDs, truthy strings, silent skips) | Validation | #166, before the consolidation |

Two things don't change, and a step may only change them with its own
decision and test:

- **Check order.** The origin check runs before the rate limit in
  `agent_creation.py` and `review_runs.py`, but after it in `app.py` and
  `history.py`. Putting them in one order
  would change the answer a disallowed origin sees when the server is busy, and
  whether that request uses up a slot in the window.
- **The wrong-content-type answer in `agent_creation.py`.** It stays a 400
  `invalid_setup` through `wrong_type`. Moving it to 415 `json_required` would
  change what the browser shows.

Nothing in this plan creates a public resource, makes a live call or needs
approval to start.

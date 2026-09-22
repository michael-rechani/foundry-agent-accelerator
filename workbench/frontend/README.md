# AI Foundry Lab Frontend

React, TypeScript and Vite. See the [workbench runbook](../README.md) for backend,
private access, Cosmos retention and deployment instructions.

From this directory:

```powershell
npm ci
npm run lint
npm run build
npx playwright install chromium
npm test
```

`npm test` builds production assets and starts an isolated preview server on
127.0.0.1:4174. Playwright tests run at desktop and mobile sizes with synthetic,
intercepted APIs; no Azure resources or credentials are used. Screenshots and
failure traces are written to ignored `test-results/`. On Linux, install browser
system dependencies with `npx playwright install --with-deps chromium`.

`src/ChatWorkspace.tsx` owns conversation and view state. Reply rendering lives
in `ConversationTurn.tsx`; `WaitingIndicator.tsx` owns the elapsed timer so it
does not rerender the transcript. `history-client.ts` handles bounded history
requests, and `request.ts` handles transport-independent cancellation.
`workspace-config.ts` validates public configuration and handles bootstrap
timeouts/retry. `ContinueDialog.tsx` previews carry-over context before resetting
the conversation; it never invokes an agent.

`AgentGuide.tsx` uses the optional `guidance` in the existing agent registry for
both the Chat **About this agent** panel and the **Agents** cards. Keep purpose,
input, output, how-it-works and limits in that registry, not hard-coded by agent
ID in React. Developer setup details distinguish the Lab's display/receipt
metadata from runtime instructions and tools.

`AgentCreationWorkspace.tsx` implements template-based setup preparation, review
and operator-confirmed publication, plus the shared Created agents list. This
is not an LLM configuration conversation or arbitrary code/tool generator.
`agent-creation-client.ts` validates API responses, bounds requests, loads saved
agents and merges only ready server-provided identities into Chat. Publication
uses an idempotency UUID retained across uncertain retries; GET polling never
submits another creation. Setup, publication, ready routing and live answer
quality remain distinct.

New configurations with `agent_creation` default to Create agent; older
configurations remain Chat-first, and valid saved-review links keep priority.
The model and tools are not editable here. Operator keys are password fields
kept only in memory, cleared when leaving the creator views, and never included
in chat, exports or persistent browser storage. Deletion requires explicit
shared-impact confirmation. See the [operator guide](../../docs/agent-creation.md).

`tests/agent-creation.spec.ts` covers template selection, preparation versus
publication, operator confirmation, uncertain submissions and stable-ID retries,
poll recovery, deletion, dynamic-agent chat/history, key lifetime and mobile
layout. Its publication and answer fixtures are explicitly mocked. For a focused
check, run `npm test -- agent-creation.spec.ts`; this still builds the production
assets first.

`ReviewWorkspace.tsx` labels the structured workflow **Document reviews**.
Checklist items map to API `criteria`; document text and added information map
to `evidence`. UI labels do not change the data contract. A review's agent is the
configured Lab default at creation, not the current Chat choice. Creating or
adding information saves a record; Run review / Review again separately calls
the agent. Tests cover that separation and the absence of automatic Chat transfer.

The visible **Local preview** state means no model calls or persistence.
`tests/fixtures.ts` reads the real catalog rather than duplicating it; the
screenshots used for the clarity walkthrough are watermarked as illustrative
API-mocked UI tests, not live model output or saved Cosmos records.

Fonts and Markdown rendering are local. Do not add browser Azure credentials,
remote image rendering, or persistent transcript storage. Preserve the explicit
shared-history and synthetic-data boundaries. No React Compiler or global state
library is required for the current bounded workflow.

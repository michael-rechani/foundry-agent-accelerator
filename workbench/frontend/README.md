# Lab frontend

[Home](../../README.md) / [The Lab](../README.md) / Frontend

The Lab frontend is the React, TypeScript, and Vite app that runs the private
browser experience. This page is for developers who build or test the UI; for
backend, private access, Cosmos retention, and deployment instructions, see the
[Lab guide](../README.md).

## Run local checks

From this directory:

```powershell
npm ci
npm run lint
npm run format:check
npm run build
npx playwright install chromium
npm test
```

Run `npm run format` to fix formatting that `npm run format:check` reports.
`npm test` builds production assets and starts an isolated preview server on
`127.0.0.1:4174`. Playwright tests run at desktop and mobile sizes with
fictional, intercepted APIs. They use no Azure resources or credentials.
Screenshots and failure traces are written to ignored `test-results/`. On Linux,
install browser system dependencies with `npx playwright install --with-deps chromium`.

## App structure

`src/ChatWorkspace.tsx` owns conversation and view state for **New chat**,
**Create agent**, **Created agents**, **Chat**, **Document reviews**,
**Shared history**, **Agents**, and **Performance**. Reply rendering lives in
`ConversationTurn.tsx`. `WaitingIndicator.tsx` owns the elapsed timer so it
does not rerender the transcript.

State, effects, and request handlers stay in the three workspace components
(`ChatWorkspace.tsx`, `AgentCreationWorkspace.tsx`, and `ReviewWorkspace.tsx`).
The view components split out of them are presentational and receive values
and callbacks as props.

| File                                                         | Role                                                                                                                          |
| ------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------- |
| `ChatSidebar.tsx`, `ChatTopbar.tsx`                          | Render the view navigation and the Chat header, agent picker, and save/export actions.                                        |
| `ChatWelcome.tsx`, `ChatComposer.tsx`                        | Render the new-chat prompts and the message composer with its conversation limits.                                            |
| `HistoryView.tsx`, `AgentCatalog.tsx`, `PerformanceView.tsx` | Render the **Shared history**, **Agents**, and **Performance** views.                                                         |
| `history-client.ts`                                          | Handles bounded history requests.                                                                                             |
| `request.ts`                                                 | Handles transport-independent cancellation.                                                                                   |
| `workspace-config.ts`                                        | Validates public configuration and handles bootstrap timeouts and retry.                                                      |
| `ContinueDialog.tsx`                                         | Previews carry-over context before resetting the conversation. It never invokes an agent.                                     |
| `AgentGuide.tsx`                                             | Uses optional `guidance` from the configured agent registry for the Chat **About this agent** panel and the **Agents** cards. |

Keep purpose, input, output, how-it-works, and limits in the registry, not
hard-coded by agent ID in React. **Developer setup details** distinguishes the
Lab's display and receipt metadata from runtime instructions and tools.

## Agent creation UI

`AgentCreationWorkspace.tsx` implements template-based setup preparation,
review, operator-confirmed publication, and the shared **Created agents** list.
This is not a large language model (LLM) configuration conversation or an
arbitrary code/tool generator. `CreationTaskForm.tsx` renders the template
picker and job description, `CreationSetupReview.tsx` renders the setup review
and publication controls, `CreatedAgents.tsx` renders the saved-agent list and
detail, and `OperatorKeyField.tsx` renders the operator key input.

`agent-creation-client.ts` validates API responses, bounds requests, loads saved
agents, and merges only ready server-provided identities into **Chat**.
Publication uses an idempotency UUID retained across uncertain retries. GET
polling never submits another creation. Setup, publication, ready routing, and
live answer quality remain distinct.

New configurations with `agent_creation` default to **Create agent**. Older
configurations remain Chat-first, and valid saved-review links keep priority.
The model and tools are not editable here. Operator keys are password fields
kept only in memory, cleared when leaving the creator views, and never included
in chat, exports, or persistent browser storage. Deletion requires explicit
shared-impact confirmation. See the [Create and try a baseline Microsoft Foundry agent](../../docs/agent-creation.md)
operator guide.

`tests/agent-creation.spec.ts` covers template selection, preparation versus
publication, operator confirmation, uncertain submissions and stable-ID retries,
poll recovery, deletion, dynamic-agent chat/history, key lifetime, and mobile
layout. Its publication and answer fixtures are explicitly mocked. For a focused
check, run `npm test -- agent-creation.spec.ts`; this still builds the
production assets first.

## Document reviews UI

`ReviewWorkspace.tsx` labels the structured workflow **Document reviews**.
Checklist items map to API `criteria`; document text and added information map
to `evidence`. UI labels do not change the data contract. A review's agent is
the configured Lab default at creation, not the current **Chat** choice.
Creating or adding information saves a record; **Run review** and
**Review again** separately call the agent. Tests cover that separation and the
absence of automatic Chat transfer.

`review-client.ts` holds the review types and request helper.
`ReviewInbox.tsx`, `ReviewForm.tsx`, `ReviewDetail.tsx`, `ReviewResults.tsx`,
and `ReviewGuide.tsx` render the inbox, new-review form, review detail,
findings, and guidance. Polling and resume stay in `ReviewWorkspace.tsx`.

## Boundaries and fixtures

The visible **Local preview** state means no model calls or persistence.
`tests/fixtures.ts` reads the real catalog rather than duplicating it. The
screenshots used for the clarity walkthrough are watermarked as illustrative
API-mocked UI tests, not live model output or saved Cosmos records. The copies
used in the docs live in
[`docs/images/screenshots/`](../../docs/images/README.md#lab-screenshots).

Fonts and Markdown rendering are local. Do not add browser Azure credentials,
remote image rendering, or persistent transcript storage. Preserve the explicit
shared-history and fictional-data boundaries. No React Compiler or global state
library is required for the current bounded workflow.

## Related content

- [The Lab](../README.md)
- [Create and try a baseline Microsoft Foundry agent](../../docs/agent-creation.md)
- [Document reviews](../../docs/review-workflow.md)

# Lab frontend

[Home](../../README.md) / [The Lab](../README.md) / Frontend

The Lab frontend is the React, TypeScript, and Vite app that runs the private
browser experience. This page is for developers who build or test the UI; for
backend, private access, Cosmos retention, and deployment instructions, see the
[Lab guide](../README.md).

## Run local checks

Use [Node 24 and the committed lockfile](../../README.md#tool-versions-and-upgrades).
The toolchain guide also covers upgrades and unavailable package mirrors.

From this directory:

```powershell
npm ci
npm run lint
npm run format:check
npm run test:unit
npm run build
npx playwright install chromium
npm test
```

Run `npm run format` to fix formatting that `npm run format:check` reports.
`npm run test:unit` uses Node's built-in test runner and type stripping, with no
extra dependencies, to test browser-independent modules in `src/` from `unit/`.
Those modules must use erasable TypeScript syntax, and tests import them with
explicit `.ts` extensions. `unit/` sits outside `tests/` so Playwright ignores it.
`npm run build` applies strict TypeScript checks to the application and Vite
configuration, including nullability and implicit types.
`npm test` builds production assets and starts an isolated preview server on
`127.0.0.1:4174`. Playwright tests run at desktop and mobile sizes with
fictional, intercepted APIs. They use no Azure resources or credentials.
Screenshots and failure traces are written to ignored `test-results/`. On Linux,
install browser system dependencies with `npx playwright install --with-deps chromium`.

## App structure

`src/ChatWorkspace.tsx` owns conversation and view state for the library's
**Browse**, **Ready to chat**, **Made in this Lab**, and **Guided demos** tabs,
**Create agent**, **Chat**, **Document reviews**, **Performance**, **Request
log**, and **Shared history**. `ChatSidebar.tsx` groups them into four
sections: **Agent library**, **Try it**, **Measure**, and **Activity**.
**Measure** and **Activity** appear only with **Under the hood** on
(`under-the-hood.ts`); elements marked `hood-only` are hidden otherwise.
`ChatTopbar.tsx` shows the breadcrumb from `navigation.ts`. The
library is one sidebar entry, **All
agents**; `LibraryTabs.tsx` switches between its tabs. Reply rendering,
including the handoff timeline and collapsed execution details, lives in
`ConversationTurn.tsx`. `WaitingIndicator.tsx` owns the elapsed timer so it
does not rerender the transcript.

State, effects, and request handlers stay in the three workspace components
(`ChatWorkspace.tsx`, `AgentCreationWorkspace.tsx`, and `ReviewWorkspace.tsx`).
The view components split out of them are presentational and receive values
and callbacks as props. `ExploreDemos.tsx` additionally owns its local story
selection and clipboard feedback; it never invokes an agent or writes records.

| File                                                         | Role                                                                                                                                                                           |
| ------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `ChatSidebar.tsx`, `ChatTopbar.tsx`                          | Render the view navigation and the Chat header, agent picker, and save/export actions.                                                                                         |
| `ChatWelcome.tsx`, `ChatComposer.tsx`                        | Render the new-chat prompts and the message composer with its conversation limits.                                                                                             |
| `HistoryView.tsx`, `AgentCatalog.tsx`, `PerformanceView.tsx` | Render the **Shared history**, **Ready to chat**, and **Performance** views.                                                                                                   |
| `AgentLibrary.tsx`, `library-catalog.ts`, `library.css`      | Render **Browse**. `library-catalog.ts` strictly validates `/api/agent-templates` (`schema_version` 1) and filters with live facet counts.                                     |
| `RequestLog.tsx`, `performance-stats.ts`                     | Render the **Request log** and compute per-agent median, 90th-percentile, slowest timings, and average tokens.                                                                 |
| `TokenCost.tsx`, `token-usage.ts`                            | Render **Token usage and cost** in Performance. Parse reported token counts, total them without treating missing counts as zero, and estimate cost from rates the user enters. |
| `history-client.ts`                                          | Handles bounded history requests.                                                                                                                                              |
| `request.ts`                                                 | Handles transport-independent cancellation.                                                                                                                                    |
| `workspace-config.ts`                                        | Validates public configuration and handles bootstrap timeouts and retry.                                                                                                       |
| `ContinueDialog.tsx`                                         | Previews carry-over context before resetting the conversation. It never invokes an agent.                                                                                      |
| `AgentGuide.tsx`                                             | Uses optional `guidance` from the configured agent registry for the Chat **About this agent** panel and the **Ready to chat** cards.                                           |
| `theme.ts`, `ThemePicker.tsx`                                | Load, validate, save, and apply the **Appearance** choice, and render its header menu.                                                                                         |
| `ExploreDemos.tsx`, `demo-scenarios.ts`, `showcase.css`      | Render three fictional stories, readiness-aware sample loading, and the presenter guide. The workspace owns guarded conversation replacement.                                  |

`public/preview/` is a static preview of the redesigned Lab, served at
`/preview/`, for [#77](https://github.com/michael-rechani/foundry-agent-accelerator/issues/77).
It uses Fluent 2 colors with light and dark themes, reads the Agent library
from `/api/agent-templates` (with a bundled snapshot as a fallback), and
shows a recorded Supplier invoice reviewer answer and acceptance results. It
sends no chat requests and isn't linked from the Lab. Regenerate
`preview-data.js` when the library changes.

Keep purpose, input, output, how-it-works, and limits in the registry, not
hard-coded by agent ID in React. **Developer setup details** distinguishes the
Lab's display and receipt metadata from runtime instructions and tools.

## Themes and colors

Every color comes from a token in the `:root` block at the top of
`src/chat.css`. Each token is a `light-dark()` pair, so **System** follows the
device with no script. `main.tsx` applies the saved choice before the first
render by setting `data-theme` (`system`, `light`, or `dark`) and `data-accent`
(`foundry`, `orchid`, or `lagoon`) on `<html>`. **Light** and **Dark** pin
`color-scheme`, and each accent overrides only the `--accent*` tokens. The
choice is stored under `ai-foundry-lab-theme` in `localStorage`; unreadable
values fall back to System and Foundry.

Use the tokens in new styles rather than hex values, so every theme and accent
keeps working. Text tokens meet WCAG AA (4.5:1) on their surfaces in all six
combinations, and borders and dots meet 3:1. Check new color pairs in both
modes. The content security policy blocks inline scripts, so a device in one
mode briefly shows that mode's background before the script applies a pinned
opposite theme.

## Agent creation UI

`AgentCreationWorkspace.tsx` implements template-based setup preparation,
review, operator-confirmed publication, and the shared **Made in this Lab** list.
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

The opening view is **All agents** > **Browse**. Explicit `/#chat`, `/#library`, `/#agents`,
`/#demos`, `/#reviews`, `/#performance`, `/#logs`, and `/#create` entry links are
supported; a library **Create** action opens the creator with that template
preselected unless setup work is already in progress; creation still requires its advertised capability. Valid
saved-review links keep priority.
The model and tools are not editable here. Operator keys are password fields
kept only in memory, cleared when leaving the creator views, and never included
in chat, exports, or persistent browser storage. Deletion requires explicit
shared-impact confirmation. See the [Create and try a baseline Microsoft Foundry agent](../../docs/agent-creation.md)
operator guide.

`tests/agent-creation.spec.ts` covers template selection, preparation versus
publication, operator confirmation, uncertain submissions and stable-ID retries,
poll recovery, deletion, dynamic-agent chat/history, key lifetime, and mobile
layout. It also covers the **Appearance** menu, saved and unreadable theme
choices, and dark-mode card contrast for each accent. Its publication and answer fixtures are explicitly mocked. For a focused
check, run `npm test -- agent-creation.spec.ts`; this still builds the
production assets first.

## Library, performance, and log coverage

`tests/library.spec.ts` routes `/api/agent-templates` to
`tests/agent-templates.fixture.json`, which
`workbench/test_frontend_catalog_fixture.py` keeps identical to the served
catalog. It covers the four-section navigation and hash links, filters with
live counts, search and the empty state, detail tabs and honest labels, template
preselection without preparing or publishing, opening a ready agent in Chat as
an unsent draft, the request log reference, the per-agent benchmark, record
download for export, preview and retry states, and light and dark contrast.
`unit/library-catalog.test.ts` and `unit/performance-stats.test.ts` cover the
pure catalog and timing logic.

## Showcase and presenter coverage

`tests/showcase.spec.ts` covers the read-only opening experience, source-input
parity with the downloadable examples, matching only visible or ready agents,
confirmation before replacing a draft, explicit Send, presenter controls,
storage failures, and desktop/mobile screenshots. The catalog keeps input,
output, and human limits prominent; execution details stay in its developer
disclosure. The existing appearance storage key is unchanged by the rebrand.

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
API-mocked UI tests, not live model output or saved Cosmos records. The example
task, review findings, and dark template card tests also write `-dark`
screenshots for the animated README tour. The copies used in the docs live in
[`docs/images/screenshots/`](../../docs/images/README.md#lab-screenshots).

The UI uses system fonts, and Markdown rendering is local. Do not add browser Azure credentials,
remote image rendering, or persistent transcript storage. Preserve the explicit
shared-history and sample-data boundaries. No React Compiler or global state
library is required for the current bounded workflow.

## Related content

- [The Lab](../README.md)
- [Create and try a baseline Microsoft Foundry agent](../../docs/agent-creation.md)
- [Document reviews](../../docs/review-workflow.md)

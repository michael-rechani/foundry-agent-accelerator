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
mocked APIs that return sample data. They use no Azure resources or credentials.
Screenshots and failure traces are written to ignored `test-results/`. On Linux,
install browser system dependencies with `npx playwright install --with-deps chromium`.
Specs share their setup through `tests/helpers/`: `mock-api.ts` answers every
`/api/` request locally, `lab-config.ts` holds the baseline Lab configuration,
`catalog.ts` the catalog and scorecard fixtures, and `navigation.ts`,
`layout.ts` and `appearance.ts` the common page actions and checks. Each area
adds one `*-lab.ts` module (`chat-lab.ts`, `library-lab.ts`, `reviews-lab.ts`,
`creation-lab.ts`) that opens the Lab with the mocks that area needs. Add shared
setup there rather than copying it into a spec.

## App structure

`src/ChatWorkspace.tsx` owns conversation and view state for the library's
**Browse**, **Ready to chat**, **Made in this Lab**, **Guided demos**, and **Add-ons** tabs,
**Create agent**, **Chat**, **Document reviews**, **Performance**, **Request
log**, and **Shared history**. `ChatSidebar.tsx` groups them into four
sections: **Agent library**, **Try it**, **Measure**, and **Activity**. `AddOns.tsx` renders the preview-only **Add-ons** tab from `add-on-catalog.json`, which `python addons/build_catalog.py --write` generates from the manifests in `addons/`; it makes no API calls. An entry with a `pilot` description shows a **Sample pilot** badge instead of **Not available yet**.
**Measure** and **Activity** appear only with **Under the hood** on
(`under-the-hood.ts`); elements marked `hood-only` are hidden otherwise.
`ChatTopbar.tsx` shows the breadcrumb from `navigation.ts`. The
library is one sidebar entry, **All
agents**; `LibraryTabs.tsx` switches between its tabs. Reply rendering,
including the **How I got this** steps and collapsed execution details, lives in
`ConversationTurn.tsx`; plain step wording comes from `answer-steps.ts`. Foundry
portal links (`foundry-links.ts`, `FoundryLink.tsx`) are built from the
`foundry_portal` config value and shown only under the hood. `WaitingIndicator.tsx` owns the elapsed timer so it
does not rerender the transcript.

The three workspace components (`ChatWorkspace.tsx`,
`AgentCreationWorkspace.tsx`, and `ReviewWorkspace.tsx`) compose the feature
hooks and route callbacks between views. Chat's state, effects, and request
handlers live in `use-conversation.ts`, `use-chat-history.ts`,
`use-chat-submit.ts`, `use-chat-effects.ts`, `use-chat-view.ts`, and
`use-dependency-health.ts`. The view components split out of the workspaces are
presentational and receive values and callbacks as props. `AgentLibrary.tsx`
chooses between `LibraryBrowse.tsx` and `LibraryDetail.tsx`. `ExploreDemos.tsx`
additionally owns its local story
selection and clipboard feedback; it never invokes an agent or writes records.

| File                                                          | Role                                                                                                                                                                           |
| ------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `ChatSidebar.tsx`, `ChatTopbar.tsx`                           | Render the view navigation and the Chat header, agent picker, and save/export actions.                                                                                         |
| `ChatWelcome.tsx`, `ChatComposer.tsx`                         | Render the new-chat prompts and the message composer with its conversation limits.                                                                                             |
| `HistoryView.tsx`, `AgentCatalog.tsx`, `PerformanceView.tsx`  | Render the **Shared history**, **Ready to chat**, and **Performance** views.                                                                                                   |
| `AgentLibrary.tsx`, `library-catalog.ts`, `library.css`       | Render **Browse**. `library-catalog.ts` strictly validates `/api/agent-templates` (`schema_version` 1) and filters with live facet counts.                                     |
| `ScorecardPanel.tsx`, `scorecards.ts`, `scorecards-client.ts` | Render an agent's **Test results** tab. `scorecards.ts` strictly validates `/api/agent-scorecards` (`schema_version` 1) and formats times and costs in plain language.         |
| `foundry-handoff.ts`                                          | Builds the **Take it to Foundry** downloads: a prompt-agent definition and a Foundry evaluation JSONL file, from data the Lab already serves.                                  |
| `RequestLog.tsx`, `performance-stats.ts`                      | Render the **Request log** and compute the 90th-percentile response time for **Performance**.                                                                                  |
| `TokenCost.tsx`, `token-usage.ts`                             | Render **Token usage and cost** in Performance. Parse reported token counts, total them without treating missing counts as zero, and estimate cost from rates the user enters. |
| `history-client.ts`                                           | Handles bounded history requests.                                                                                                                                              |
| `request.ts`                                                  | Handles transport-independent cancellation.                                                                                                                                    |
| `workspace-config.ts`                                         | Validates public configuration and handles bootstrap timeouts and retry.                                                                                                       |
| `ContinueDialog.tsx`                                          | Previews carry-over context before resetting the conversation. It returns focus on close and never invokes an agent.                                                           |
| `ConfirmDialog.tsx`                                           | Asks before switching agents, starting a new chat or opening an example would discard unsent work. It names the target, returns focus on cancel, and never invokes an agent.   |
| `use-modal-dialog.ts`                                         | Shows a dialog as a modal and hands focus back to what opened it, or to a fallback when that has gone.                                                                         |
| `AgentGuide.tsx`                                              | Uses optional `guidance` from the configured agent registry for the Chat **About this agent** panel and the **Ready to chat** cards.                                           |
| `theme.ts`, `ThemePicker.tsx`                                 | Load, validate, save, and apply the **Appearance** choice (theme, accent, and look), and render its header menu.                                                               |
| `ExploreDemos.tsx`, `demo-scenarios.ts`, `showcase.css`       | Render three fictional stories, readiness-aware sample loading, and the presenter guide. The workspace owns guarded conversation replacement.                                  |

Keep purpose, input, output, how-it-works, and limits in the registry, not
hard-coded by agent ID in React. **Developer setup details** distinguishes the
Lab's display and receipt metadata from runtime instructions and tools.

## Themes and colors

Every color comes from a token in the `:root` block in
`src/chat/tokens.css`. Each token is a `light-dark()` pair, so **System** follows the
device with no script. `main.tsx` applies the saved choice before the first
render by setting `data-theme` (`system`, `light`, or `dark`), `data-accent`
(`foundry`, `orchid`, or `lagoon`), and `data-look` (`classic`, `aurora`, or
`console`) on `<html>`. **Light** and **Dark** pin `color-scheme`, and each
accent overrides only the `--accent*` tokens. The choice is stored under
`ai-foundry-lab-theme` in `localStorage`; unreadable values fall back to System,
Foundry, and Classic, and each of the three is read on its own, so a saved
choice from before looks existed keeps its theme and accent and opens in
Classic.

A look is a stylesheet that restyles the same markup. **Classic** is the base
`chat.css`, which imports the feature files in `src/chat/` in a fixed order
(later files override earlier ones, so keep that order). Vite inlines those
imports at build time, so the built CSS is one file with no `@import`.
`src/look-aurora.css` and `src/look-console.css` are scoped to
`:root[data-look='aurora']` and `:root[data-look='console']` and are imported
last in `main.tsx`, so they win the cascade without `!important`. They load no
fonts or images and use no `@import`, which keeps them inside the content
security policy. A new look is one more stylesheet scoped the same way, one more
entry in `looks` in `theme.ts`, and its icon in `ThemePicker.tsx`.

Use the tokens in new styles rather than hex values, so every theme, accent, and
look keeps working. Text, link, and button colors meet WCAG AA (4.5:1) on the
surfaces they sit on, and form-field borders and the accent line meet 3:1, in
every combination of look, light or dark, and accent;
`tests/appearance-looks.spec.ts` checks these pairs on the rendered page. Status
dots and decorative borders aren't covered, so don't rely on them alone to carry
meaning. Check new color pairs in both modes and in each look. The content
security policy blocks inline scripts, so a device in one mode briefly shows
that mode's background before the script applies a pinned opposite theme.

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

`tests/agent-creation.spec.ts` and `tests/agent-creation-recovery.spec.ts` cover
template selection, preparation versus publication, operator confirmation,
uncertain submissions and stable-ID retries, poll recovery, deletion,
dynamic-agent chat/history, key lifetime, and mobile layout.
`tests/appearance.spec.ts` and `tests/appearance-looks.spec.ts` cover the
**Appearance** menu (theme, accent, and look), saved and unreadable choices, and
text, link, and button contrast for every look in light and dark with each
accent. Their publication and answer fixtures are explicitly mocked. For a
focused check, run `npm test -- agent-creation`; this still builds the
production assets first.

## Library, performance, and log coverage

The `tests/library*.spec.ts` specs route `/api/agent-templates` (through
`tests/helpers/library-lab.ts`) to `tests/agent-templates.fixture.json`, which
`workbench/test_frontend_catalog_fixture.py` keeps identical to the served
catalog. After a catalog change, regenerate it from `workbench` and format it:

```powershell
python -c "import json; from pathlib import Path; from agent_templates import catalog_facets, list_templates; Path('frontend/tests/agent-templates.fixture.json').write_text(json.dumps({'schema_version': 1, 'draft_mode': 'template', 'templates': list_templates(), 'facets': catalog_facets()}, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')"
npm --prefix frontend run format
```

The Add-ons tab reads `src/add-on-catalog.json`, which is generated from the add-on manifests in the repository's `addons` folder (see [Add-on package format](../../docs/addon-package-format.md)). After you change a manifest, run `python addons/build_catalog.py --write` from the repository root. CI fails if the file is out of date, and `tests/library.spec.ts` checks that the page lists every manifest in order.

The specs cover the four-section navigation and hash links, filters with
live counts, search and the empty state, detail tabs and honest labels, template
preselection without preparing or publishing, opening a ready agent in Chat as
an unsent draft, the request log reference, recent requests on Performance,
record download for export, preview and retry states, and light and dark contrast.
It also takes the pictures for the README tour: browsing the library, an agent's
**Test results**, **Take it to Foundry**, and the **Create agent** page with all
the library's templates.
`tests/customer-view.spec.ts` routes `/api/agent-scorecards` to the served
`workbench/agent_scorecards.json` and covers the **Test results** tab.
`unit/library-catalog.test.ts`, `unit/scorecards.test.ts` and
`unit/performance-stats.test.ts` cover the pure catalog, scorecard and timing
logic.

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
documentation screenshots come from API-mocked browser tests with sample data,
not live model output or saved Cosmos records, and carry no watermark. Their
`docsScreenshot` helper turns **Under the hood** off for the capture, so the
pictures show the plain view a customer sees, and puts it back afterwards; the
test setup turns it on by default. The library tour, **Create agent**, chat,
review, and guided-demo tests also write `-dark` screenshots for the animated
README tours. The copies used in the docs live in
[`docs/images/screenshots/`](../../docs/images/README.md#lab-screenshots).

The UI uses system fonts, and Markdown rendering is local. Do not add browser Azure credentials,
remote image rendering, or persistent transcript storage. Preserve the explicit
shared-history and sample-data boundaries. No React Compiler or global state
library is required for the current bounded workflow.

## Related content

- [The Lab](../README.md)
- [Create and try a baseline Microsoft Foundry agent](../../docs/agent-creation.md)
- [Document reviews](../../docs/review-workflow.md)

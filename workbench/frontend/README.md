# Workbench Frontend

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

Fonts and Markdown rendering are local. Do not add browser Azure credentials,
remote image rendering, or persistent transcript storage. Preserve the explicit
shared-history and synthetic-data boundaries. No React Compiler or global state
library is required for the current bounded workflow.

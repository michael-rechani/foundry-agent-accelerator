# The Lab

[Home](../README.md) / The Lab

The Lab is the private browser app in `workbench/`, titled **Foundry Agent
Lab**. Use it to try the prebuilt agents, prepare agents from templates,
publish hosted agents when an operator enables creation, and save document
reviews. It's a React and TypeScript UI on a FastAPI backend, with shared Azure
Cosmos DB storage.

- **Run it on your machine:** see [Local development](#local-development).
- **Run it in Azure:** follow the [deployment runbook](../docs/lab-deployment.md).
- **Need detail?** See the [reference pages](#reference-pages).

## At a glance

| Area | What to know |
| --- | --- |
| Start here | The Lab opens on **Chat**, clean, as a plain conversation with the **Agent designer**, or with a ready agent or library preview you choose. |
| Projects | Save a fictional project brief in this browser, load it into the designer, return to its spec and draft tests, then choose an available agent and load a demonstration prompt into Chat. Loading never sends a message or creates an agent. |
| Agent library | Browse agent definitions by sector or industry (one list), task, readiness, and tool mode. A plain-word job finder at the top sends and saves nothing. By default only featured agents show. Compare a sample example with expected behavior. Create, test, and export. |
| Guided demos | Three sample customer stories with expected findings and human decisions. Loading a sample never automatically sends, saves, or publishes anything. |
| Add-ons | A preview of optional tools and skills an agent could connect to later, such as knowledge search or a calculator. It shows what each would do, what it would cost, and what it needs. The page turns nothing on. Knowledge search also runs as a small sample pilot in Checklist and case helper. |
| Agent creation | **Create agent** prepares instructions from built-in templates. A matching designer spec card in Chat can also offer template publication, after operator authorization and cost confirmation. Chat does not freely configure tools or agent runtime. |
| Prebuilt agents | The prebuilt agents remain available. **Checklist and case helper** is the default visible prebuilt agent. |
| Document reviews | **Document reviews** saves one structured check per checklist item and keeps the original text beside the result. |
| Data boundary | Use sample data only. The Lab doesn't connect to customer systems or perform business writes. |
| Access model | The current private Lab has no end-user Microsoft Entra ID sign-in or per-user authorization. |
| Chat limits | Four chat turns at once and 20 a minute across all users, plus a per-model-deployment requests and tokens budget (`WORKBENCH_MODEL_LIMITS`, set by the `model_limits` Terraform variable) that answers busy before the model's own limit does. See [Model limits](../docs/lab-configuration-and-cost.md#model-limits). |

## Project journey

Open **Projects** (`/#projects`) and enter a name, goal, context and boundaries,
decisions, and deliverable/evidence notes. **Save brief in this browser** is
explicit: editing does not save or send anything. Up to 20 briefs are stored in
this origin's `localStorage`, without sign-in, synchronization or backup. Anyone
using the same browser profile can read them; clearing browser data loses them.
Use fictional data only, not secrets or customer records. Export the saved brief
as JSON to keep a copy; this slice has no import. Local deletion removes only
the selected brief, never shared chats or agents. Failed saves keep edits on the
page and show an error; unreadable storage is not silently overwritten.

**Load brief in designer** opens a new conversation with the brief as an
unsent, editable message. Existing unsaved-chat confirmation still applies.
Sending is the normal model call in a connected Lab. The resulting spec card
owns **Test this draft first**, case/results downloads, accepted instruction
revisions, and template publication. All existing model-cost confirmations and
operator checks remain. **Back to project** and **Return to current work**
preserve the current conversation and spec-card state while navigating within
the page; leaving a running draft test aborts its browser request, but a sent
model call may still finish and incur cost. The project displays only actual
completed chat turns and a received spec's name, not a test-pass or deployment
claim. This session link and chat/test state do not survive reload or a new chat.
Using a newly created agent from the project's spec/creation flow keeps the
project return link, but starts a fresh chat; explicitly select that agent in
the brief and save if you want to keep its demonstration reference.

For a demonstration, select an available prebuilt or ready created agent and
save a fictional sample prompt. **Open demonstration chat** loads that prompt
without sending it. Send it when ready, inspect the answer, then use Chat's
**Presenter view**. An agent selection is only a reference: it does not apply
the project brief as instructions. A removed or unavailable agent cannot be
launched. The library and add-ons remain discoverable from the project.

Project storage contains only the explicitly entered brief, selected agent ID,
and update time. It does not copy chats, test results, operator keys or agents.
Export chat, spec and test reports from their existing controls and record
reviewed findings in the brief yourself. Shared-history saves and created agents
still use existing server storage and are visible to everyone with Lab access;
the browser-local project is **not an authorization boundary**. Local preview
can save briefs and browse capabilities, but cannot execute the designer,
draft tests or publication.

The brief starts blank and supports any project goal; it does not select a
scenario, customer platform or integration. Actual execution still depends on
the Lab's available templates and agents. There are no new external-system
connections in this slice, and a spec listing a tool does not configure it.
No-template publication remains tracked in
[#506](https://github.com/michael-rechani/foundry-agent-accelerator/issues/506);
end-user identity and ownership remain tracked in
[#278](https://github.com/michael-rechani/foundry-agent-accelerator/issues/278).
The local-first journey is tracked in
[#540](https://github.com/michael-rechani/foundry-agent-accelerator/issues/540).

## Local development

Requires Node 24 and Python 3.14. See the
[tool versions and upgrade expectations](../docs/tool-versions.md).
These disconnected checks need neither Azure sign-in nor `azd`.

```powershell
npm --prefix workbench/frontend ci
npm --prefix workbench/frontend run build
python -m pip install -r workbench/requirements.txt
python -m uvicorn app:create_app --factory --app-dir workbench --host 127.0.0.1 --port 8080 --no-access-log
```

<a id="github-codespaces"></a>

**No installs?** Use
[GitHub Codespaces](https://codespaces.new/michael-rechani/foundry-agent-accelerator).
The [dev container](../.devcontainer/devcontainer.json) installs Node 24,
Python 3.14 and the Lab's dependencies, then builds the frontend. When it
finishes, run the `uvicorn` command above in its terminal. Codespaces forwards
port 8080 privately to you. Like any local run, it needs no Azure sign-in and
makes no model calls. Stop the codespace when you're done, since it bills your
GitHub account.

Vite writes compiled assets to `workbench/static`, which FastAPI serves. The Lab
uses the device's Segoe UI system fonts and downloads none. The browser has no
Content Delivery Network (CDN) dependencies or Azure credentials. The optional
operator key is held in memory only for creation or deletion requests. Markdown
doesn't render raw HTML, external images, or clickable external links.

```powershell
python -m pip install -r workbench/requirements.txt -r workbench/agent_runtime/requirements.txt
python -m unittest discover -s workbench -p 'test_*.py' -v
npm --prefix workbench/frontend run lint
npm --prefix workbench/frontend run format:check
npm --prefix workbench/frontend exec -- playwright install chromium
npm --prefix workbench/frontend test
./workbench/test-deployment-inputs.ps1
./workbench/test-private-checks.ps1
```

Before presenting, run `./workbench/demo-check.ps1 -BaseUrl <lab address>` from
the network you'll present on. It only reads. Add `-Designer` to send one short
billable message to the Agent designer and check its spec card. The
[demo script](../docs/demo-script.md) explains the output.

Infrastructure initialization and validation are separate deployment steps. The
local application checks don't require access to the remote state backend.

Workbench test classes that exercise the app mix in `CapturedLabLogs` from
`workbench/log_capture.py`. It collects the Lab's JSON log lines instead of
printing them, so a clean run shows only the test summary. A failing test's
report ends with a `Captured Lab log:` section, and `assertLogs("uvicorn.error")`
still works in a test that checks a log line. Use the mixin in any new test class
that drives the app or the gateway.

## Reference pages

- [Lab pages and access](../docs/lab-pages-and-access.md): what each page does, the demonstration scenarios, and who can reach the Lab.
- [Lab chat, saving, and limits](../docs/lab-conversations.md): the agent catalog, starters, saved conversations, retention, and request limits.
- [Lab configuration, storage, and cost](../docs/lab-configuration-and-cost.md): where each setting comes from, what Cosmos DB holds, and what it costs.
- [Deploy the Lab](../docs/lab-deployment.md): the seven-step Terraform, image build, and verification runbook.
- [Lab diagnostics, alerts, and caching](../docs/lab-diagnostics.md): session reuse, request and dependency logs, [Budget alerts](../docs/lab-diagnostics.md#budget-alerts), and browser caching.

## Related content

- [Documentation index](../docs/README.md)
- [Create and try a baseline Microsoft Foundry agent](../docs/agent-creation.md)
- [Document reviews](../docs/review-workflow.md)
- [Private deployment runbook](../docs/private-deployment.md)
- [Application ingress options](../docs/ingress-access.md)

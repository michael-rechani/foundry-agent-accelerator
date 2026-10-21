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
| Start here | The Lab opens on **Chat**, clean, as a plain conversation with the **Agent designer**, or with a ready agent or library preview you choose. **Find an agent** is a plain-word finder that sends and saves nothing. |
| Agent library | Browse agent definitions by sector or industry (one list), task, readiness, and tool mode. By default only featured agents show. Compare a sample example with expected behavior. Create, test, and export. |
| Guided demos | Three sample customer stories with expected findings and human decisions. Loading a sample never automatically sends, saves, or publishes anything. |
| Add-ons | A preview of optional tools and skills an agent could connect to later, such as knowledge search or a calculator. It shows what each would do, cost and need. The page turns nothing on. Knowledge search also runs as a small sample pilot in Checklist and case helper. |
| Agent creation | **Create agent** prepares instructions from built-in templates. Publication is a separate operator-protected action. **Chat doesn't create or configure agents.** |
| Prebuilt agents | The prebuilt agents remain available. **Checklist and case helper** is the default visible prebuilt agent. |
| Document reviews | **Document reviews** saves one structured check per checklist item and keeps the original text beside the result. |
| Data boundary | Use sample data only. The Lab doesn't connect to customer systems or perform business writes. |
| Access model | The current private Lab has no end-user Microsoft Entra ID sign-in or per-user authorization. |
| Chat limits | Four chat turns at once and 20 a minute across all users, plus a per-model-deployment requests and tokens budget (`WORKBENCH_MODEL_LIMITS`, set by the `model_limits` Terraform variable) that answers busy before the model's own limit does. See [Model limits](../docs/lab-configuration-and-cost.md#model-limits). |

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

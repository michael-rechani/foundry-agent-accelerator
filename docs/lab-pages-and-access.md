# Lab pages and access

[Home](../README.md) / [Docs](README.md) / [The Lab](../workbench/README.md) / Pages and access

This page is part of the [Lab guide](../workbench/README.md). It walks through
each page of the Lab and the demonstration scenarios you can start from. It also
says who can reach the Lab and what they share.

## In this guide

- [Pages](#pages)
- [Choose one demonstration](#choose-one-demonstration)
- [Access](#access)

## Pages

The sidebar groups the Lab's pages into three sections, in this order: **Agent library**, **Try it**, and **Operations**. Every agent lives under **Agent library** > **All agents**, which has tabs for **Browse**, **Ready to chat**, **Made in this Lab** (when creation is on), **Guided demos**, and **Add-ons**. A small number beside **All agents** and **Shared history** says how many there are. **Browse** can show the agents as **Cards** or as a **List**, and the Lab remembers your choice in this browser.

The Lab opens in a plain customer view. Turn on **Under the hood** at the bottom of the sidebar to show models, token counts, execution details, setup commands, and the **Operations** section. The Lab saves the choice in this browser. A breadcrumb in the top bar shows the current section and page.

With **Under the hood** on, the Lab also links into Microsoft Foundry: **Open project in Foundry** in the sidebar, **Open in Foundry** next to each agent and specialist in **Developer setup details** and **How I got this**, and a project link on **Overview**, **Performance**, and **Request log** for traces and monitoring across every session. The links need `WORKBENCH_FOUNDRY_PROJECT_ID`, the project's Azure resource ID. `workbench/infra` sets it from `foundry_account_name` and `foundry_project_name`. The Lab builds the portal address the same way the Azure Developer CLI does (`https://ai.azure.com/nextgen/r/...`). To open a link, you need a Foundry sign-in with access to the project. Library previews run on the model directly, so they have no Foundry agent to link to. Without the setting, or in local preview mode, no Foundry links appear.

| Section | Page | What you do there |
| --- | --- | --- |
| Agent library | **All agents** > **Browse** | Filter the [agent library](agent-creation.md#what-a-participant-can-do) by sector or industry, task, readiness, and tools. Sector and industry are one list: choose a sector to see its industries, then choose one to narrow further. Each entry shows what to give it, what it returns, what it won't do, who decides, an example with sample data, and the expected behavior. From an entry you can create the agent, open a ready one in **Chat** with the example as an unsent draft, or download its saved record for export. |
| Agent library | **All agents** > **Ready to chat** | Browse the prebuilt and ready created agents you can chat with, read what each one needs and does, and start a chat. |
| Agent library | **Create agent** | Describe a job, pick a library template, edit the name and instructions, and publish a new Foundry hosted agent on the [model that suits the job](agent-creation.md#how-the-lab-picks-a-model). Shown only when the server advertises creation; actual publication needs operator enablement. |
| Agent library | **All agents** > **Made in this Lab** | Follow publication progress, open a ready agent in **Chat**, or delete an agent with the operator key. Shown only when creation is on. |
| Agent library | **All agents** > **Guided demos** | Start with application evidence, invoice discrepancies, or case notes. Read an example walkthrough, copy its sample input, or load it into an enabled matching agent, or into its library preview when previews are on. |
| Agent library | **All agents** > **Add-ons** | See which optional tools and skills an agent could use later, what each would cost and need, and how it stays safe. A preview only. **Knowledge search** shows as a **Sample pilot** because it runs in Checklist and case helper, and every other add-on shows as **Not available yet**. |
| Try it | **Chat** | Talk with a prebuilt or created agent, or try a library agent instantly as a preview. Switch agents from the name in the Chat header. An example task only fills in your message, and you choose when to send it. In a preview, **Create this agent** opens **Create agent** with that template chosen. After the first reply, a window about 1,000 pixels wide or more shows a right-hand column with a collapsed **About this agent** disclosure, **This conversation** (replies, time of the last reply, and tokens), and **Next steps** (**Save to shared history**, **Export conversation**, and **Create this agent** for a preview). Before the first reply and in narrower windows, agent details and actions remain in the header. |
| Try it | **Document reviews** | Check pasted documents against a checklist and get one saved, quoted result for each item. Not in the sidebar or Chat: open a saved-review link or `/#reviews`. |
| Try it | **Shared history** | Reopen chats that anyone saved. Saved chats are shared and kept for 30 days. |
| Operations | **Overview** | See at a glance whether the Lab is healthy (**Services**: the Lab, its Foundry connection, and its history store), how many agents there are, and the latest requests and tokens from this browser tab. **Refresh** checks again. The Lab re-checks itself every minute, so the status can be up to a minute behind. **Go deeper in Foundry** lists what Foundry shows for every user and session. |
| Operations | **Performance** | See completed and unsuccessful requests, average and 90th-percentile response time, recent requests, and **Token usage and cost** for this browser session. To compare agents, use each agent's **Test results** in the library. Enter your own per-1M-token rates for an estimate, because the Lab ships no prices. |
| Operations | **Request log** | See each live request from this browser tab with its time, agent, outcome, elapsed time, reported tokens, and a copyable reference that matches the server's `request_id` log entry. |

**Chat** can't change an agent's instructions, tools, or model. That's a
[developer or operator task](lab-configuration-and-cost.md#workspace-configuration). **Document reviews**
always uses the Lab's default agent, whichever agent you select in **Chat**.
Neither page copies work into the other.

Preparing a setup in **Create agent** doesn't call a model or create Azure
resources. Publishing is opt-in, costs money, and needs the
[operator setup](agent-creation.md#enable-publication).

**Appearance:** the palette button at the right of the header sets the theme to
**System** (follows your device, the default), **Light**, or **Dark**, with a
**Foundry**, **Orchid**, or **Lagoon** accent, and a **Look**: **Classic** (the
default), **Aurora** (glass panels over a soft glow) or **Console** (flat
panels and monospace labels, near-black in dark mode). The choices apply at
once. The Lab saves them in this browser only, so they aren't shared with other
users or saved with chats.

**Presenter view:** the presentation button in the header enlarges story and
Chat text for this browser session. A loaded scenario has a compact **Demo
guide** with expected findings and a guarded **Start fresh with this example**
action. Environment notices stay available, and resetting local messages never
deletes shared records. See the [showcase guide](showcase.md).

**What gets saved:** **Chat** saves completed messages to the shared Azure
Cosmos DB database only when you choose to save. Creating a document review
saves its checklist and document text. Running a review also saves the results
and a copy of that run's input. Each created agent's setup is saved as a shared
record.

## Choose one demonstration

Start with the [demo guide](demos.md) and record findings in the
[demo handoff](demo-handoff.md). Pick one bounded scenario instead of demonstrating
them all.

| Scenario | Status | What it means |
| --- | --- | --- |
| [Casework assistance](demos.md#casework-assistance) | **Available** | The source and walkthrough are included. This isn't a live-validation claim. |
| [Application completeness](demos.md#application-completeness) | **Available** | The source and walkthrough are included. This isn't a live-validation claim. |
| [Requirements and proposal review](demos.md#requirements-and-proposal-review) | **Preview** | This reuses the application agent and the existing criteria-and-evidence workflow. It doesn't add another agent. |

The creation jobs are grouped on the page by sector, using the same three names,
in the same order, as the **Agent library**. **Works in any sector:** Document
explainer, Checklist gap finder, Form field extractor, Service request planner,
and Supplier invoice reviewer. **Private sector:** nine jobs. **Healthcare and
public sector:** Case summary writer, Medical bill reviewer, Insurance
pre-approval helper, and Benefits renewal helper. Every job is marked
**Not yet reviewed** until a person signs off its recorded test answers. They pass
offline contract and acceptance tests but aren't yet validated live. Seven jobs
each have two **simulated read-only**
lookups: the Service request planner, the Supplier invoice reviewer, the
Medical bill reviewer, the Insurance pre-approval helper, the Benefits renewal
helper, and two private-sector jobs. The other eleven use supplied text only.
None connects to customer systems or performs business writes. See [Create and try a baseline Microsoft Foundry agent](agent-creation.md).

> [!IMPORTANT]
> Use supplied sample inputs only. People verify evidence and make decisions.
> Model output isn't an approval, award, eligibility, or permit decision.

Live model execution still incurs charges. See [Storage and cost](lab-configuration-and-cost.md#storage-and-cost).

The frontend uses React 19, TypeScript, Vite, Lucide icons, and custom
Fluent-inspired CSS, not the Fluent UI component library. Neutral surfaces and
blue actions are shared across creation, **Chat**, **Document reviews**,
history, **Agent library**, performance, and the request log. Playwright covers desktop and mobile
workflows. The Python backend uses FastAPI, Pydantic validation, and async Azure
SDKs for Foundry and Cosmos DB. To build or test the UI, see the
[frontend guide](../workbench/frontend/README.md).

## Access

Use the `private_url` Terraform output from an authorized private-network
browser. For local development, use `http://127.0.0.1:8080` after starting the
server. Local disconnected mode allows template preparation, but disables
publication, agent calls, and Cosmos access.

The Azure Container Apps environment has an internal load balancer and public
network access disabled. App-level external ingress means access from outside
the environment, within the private network. Ingress is further restricted to an
approved source subnet. Azure API Management (APIM) isn't involved, and this
application exposes no public gateway API. Opt-in creation publishes named
agents inside the configured private Foundry project.

For broader internal access or a controlled internet-facing entry point, see the
[Application ingress options](ingress-access.md) guide. It covers
private origins, Domain Name System (DNS), Transport Layer Security (TLS),
authentication prerequisites, host/origin configuration, and agent-request
behavior. This sample deploys neither gateway.

The current private Lab doesn't require end-user Microsoft Entra ID sign-in.
Azure resource access still uses managed identities. Restrict the
Lab to trusted operators and sample inputs. The Lab isn't a user-isolated
application.

**Keep the quick-start simple:** `WORKBENCH_MODE=private` is a shared demo,
not an authenticated team mode. No end-user app registration or Entra sign-in
is required. The Lab header and origin checks prevent cross-site browser
requests, but they don't identify a user. The operator key protects publication
and deletion, not access to shared records.

An optional authenticated team mode is a future extension, not a supported
setting today. It would need both validated identities and authorization on
every record read and mutation. Placing a sign-in page in front of the current
Lab would still leave records shared. Don't expose this sample to untrusted
participants or use sensitive data on the assumption that private networking
provides user isolation.

The **Shared lab** control in the header explains these limits on demand:

| Shared item | Who can act | Limits |
| --- | --- | --- |
| Saved chats | Everyone with workspace access can read, modify, and delete them. | There is no per-user authorization yet. |
| Reviews | Everyone with workspace access can read reviews and add requested information. | Reviews have no deletion control. |
| Created-agent setups | Everyone with workspace access can read the setups. | Publication and deletion require the shared operator key. This isn't per-user authorization. |

The Lab has no permanent warning banner. The **Shared lab** details are
available on desktop and mobile. They are informational. They aren't an access
control, and they don't check that submitted data is sample data.

### How the Lab checks where a request came from

Every API call that reads or changes Lab data (chat, saved chats, reviews, and
created agents) goes through one shared check,
[`request_allowed`](../workbench/request_guard.py). It passes only when all of
these hold:

- The request carries `X-Workbench-Request: 1`. A page on another site can't add
  a custom header without a CORS preflight, and the Lab never grants one. This
  header is what stops cross-site browser requests.
- `Sec-Fetch-Site` isn't `cross-site`.
- If the request has an `Origin` header, it matches `WORKBENCH_ORIGINS`.

A request with no `Origin` header is accepted when it passes the first two
checks. **Decision (#168): keep that.** Requiring `Origin` wouldn't add
protection, and it would cost something:

- Browsers omit `Origin` on same-origin reads, so requiring it would break the
  page's own `GET` calls. Requiring `Sec-Fetch-Site: same-origin` instead would
  turn away any browser or script that doesn't send it.
- Neither header identifies a person. A script on the private network can send
  any `Origin` it likes, so requiring one adds nothing against it. Such a caller
  must already be inside the approved source subnet, which today means the jump
  box.

Preview mode (`WORKBENCH_MODE=preview`) only accepts `localhost` and `127.0.0.1`
as hosts and can't call Azure. It answers `preview_only`. Its origins must be
well-formed and listed (the default is `http://127.0.0.1:8080` and
`http://localhost:8080`), but they aren't limited to localhost. That's
deliberate, because the host restriction and the missing Azure access already
keep the preview server local.

Revisit this if customers get to the Lab by another path (see
[Application ingress options](ingress-access.md)) or if sign-in is added. The
tests `test_missing_origin_is_accepted_only_with_the_lab_header` in
`workbench/test_app.py` and `test_reads_and_deletes_without_origin_need_the_lab_header`
in `workbench/test_history.py` fail if the guard changes.

## Related content

- [The Lab](../workbench/README.md)
- [Lab chat, saving, and limits](lab-conversations.md)
- [Create and try a baseline Microsoft Foundry agent](agent-creation.md)
- [Application ingress options](ingress-access.md)
- [Documentation index](README.md)

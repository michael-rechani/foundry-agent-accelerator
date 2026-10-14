# Lab chat, saving, and limits

[Home](../README.md) / [Docs](README.md) / [The Lab](../workbench/README.md) / Chat, saving, and limits

This page is part of the [Lab guide](../workbench/README.md). It covers how
Chat, the agent catalog, starters, saved conversations, retention, request
limits, and configuration loading behave.

## In this guide

- [Navigation and views](#navigation-and-views)
- [Prebuilt and created agents](#prebuilt-and-created-agents)
- [Starters and guidance](#starters-and-guidance)
- [Saving, retention, and receipts](#saving-retention-and-receipts)
- [Limits and request behavior](#limits-and-request-behavior)
- [Continue in new chat](#continue-in-new-chat)
- [Configuration loading](#configuration-loading)

## Conversations

**All agents** > **Browse** is the initial view. Bookmark `/#chat` to start in
Chat, `/#agents` for **Ready to chat**, `/#reviews` for **Document reviews**,
`/#demos` for **Guided demos**, `/#addons` for **Add-ons**, `/#performance`,
`/#logs`, or `/#create` for the creator when its capability is advertised. A
valid saved-review URL still opens its review directly, including after a
reload. Entering a view never publishes anything or invokes a model.

The optional [Document reviews](review-workflow.md) workflow has its own
data contract and deployment checks. You don't need it to use **Chat**.

### Navigation and views

| UI label | What it does | Important limits |
| --- | --- | --- |
| **Browse** | Lists every agent definition from `GET /api/agent-templates` with server-derived filters and live counts. | Readiness and tool mode come from the catalog, and nothing claims a connected customer system. **Expected behavior** is an acceptance description, not a recorded model response. Export downloads a ready saved record for `bundle.py export-created`. There is no one-click cross-environment deployment. **Take it to Foundry** also offers two downloads built in the browser, with nothing created in the Lab: an agent definition (the body of Foundry's create-agent-version call for a prompt agent, with a placeholder for your own model deployment) and, for agents with test results, a JSONL file of their test requests for a Foundry evaluation. **Test results** shows recorded acceptance results from `GET /api/agent-scorecards`: answer checks passed (each case is asked several times and passes only if every answer does), median response time, model cost per answer at list prices, and whether a person has signed off. Case IDs, token counts and check notes appear under the hood. |
| **Guided demos** | Shows sample stories and loads a sample into an enabled matching agent, or into its library preview when the Lab has previews on. | Expected findings are examples, not live model results. You can't select hidden, failed, or unavailable agents, and the Lab never sends a sample automatically. |
| **Add-ons** | Lists eight planned add-ons from the add-on manifests in the repository's `addons` folder (see the [add-on package format](addon-package-format.md)). Each card says whether it **Lets an agent do more** (knowledge search, document extraction, notifications, code interpreter and web search) or **Supports the agent** (conversation memory, document storage and a response cache). | Preview only. The page makes no API call, saves nothing and turns nothing on. Knowledge search carries a **Sample pilot** badge because a lookup over ten approved sample passages runs in Checklist and case helper (see the [knowledge retrieval design](knowledge-retrieval.md)). The other seven show **Not available yet**. Every add-on is off by default, private, keyless and needs its cost shown first. Web search also needs separate data-handling approval. The response cache would keep what people asked, so it needs the same retention and deletion rules as conversation memory. Service names, billing meters and the roadmap issue appear under the hood. |
| **New chat** | Starts a new Chat draft for the selected agent. | It doesn't create an agent or submit a starter prompt. When you have unsaved messages or a draft you typed, the Lab asks before clearing them. An example you haven't edited is replaced without asking. Saved history isn't deleted. |
| **Create agent** | Prepares a setup from a built-in template and, when enabled, lets an operator publish it. | Preparation is deterministic template assembly, not a model-designed agent. |
| **Made in this Lab** | Lists agents published from the Lab's creation flow. | Ready agents can be selected in **Chat**. |
| **Chat** | Sends a message to the selected prebuilt agent, ready created agent, or library preview. | A chat prompt doesn't edit tools, instructions, or runtime configuration, and Chat can't create an agent. The example cards on the welcome screen only fill the message box and never send. They step aside once the box has text, and **Choose a different example** brings them back. Under the examples, **Ask the Lab** offers two questions: **Which agent should I use or build?** lists the ready agents with a button to switch to one, and **How is an agent built, and what can I add?** explains the parts of an agent and lists the add-ons in the same two groups as the **Add-ons** page. The answers are written from the agent list and the add-on manifests, so asking sends nothing, saves nothing and makes no model call, and your message box stays as it is. A library preview's **Create this agent** button, and the **Open Create agent** link on other agents' welcome screens, only open **Create agent**. Nothing is prepared or published until you act there. |
| **Agent switcher** | Opens from the **Agent** button in the Chat header (hover text **Change agent**), which shows the current agent's name. Search and switch between **Ready agents** and **Library previews** without leaving Chat, or choose **Browse the full library**. | Switching agents starts a new chat. When you have unsaved messages or a draft you typed, the Lab names the agent you're switching to and asks first. Saved history isn't deleted. Agents marked **Not yet reviewed** pass offline tests but aren't validated live. |
| **Library preview** | Runs a library definition directly on the Lab's model deployment, without publishing an agent. Start one from the switcher or from a library entry (**Try it in Chat**). | Private mode only, and only when `WORKBENCH_LIBRARY_PREVIEW_ENABLED` isn't `false` and a creation model is configured. Uses the definition's instructions and its simulated read-only lookups, with bounded tool loops. Preview chats can't be saved to **Shared history**, so **Create this agent** takes the place of **Save** when creation is available. Each message calls the model and may incur cost. |
| **Document reviews** | Saves and runs checklist-based reviews. | Chat messages and review results don't copy between views automatically. |
| **Shared history** | Lists, reopens, and deletes saved conversations. | Everyone with workspace access can read, modify, and delete saved conversations. |
| **Ready to chat** | Lists only enabled prebuilt agents and ready created agents. | Hidden agents can't be invoked directly through the Lab API. |
| **Overview** | Shows whether the Lab, its Foundry connection, and its history store are ready, with the time of the last check; agent counts; and this tab's latest requests and tokens. | It reads the same cached `GET /api/health/dependencies` result the server refreshes every minute, so it makes no model call and costs nothing extra. The request and token numbers cover this browser tab only and clear on refresh. |
| **Performance** | Shows browser-session request counts, average and 90th-percentile latency, recent requests, and reported token totals with an optional estimate from rates you enter. | It excludes local preview calls, clears on refresh, and isn't a fleet-wide metric or model-quality score. Replies without reported tokens count as **Not reported**, never zero. Rates stay in this browser. The estimate prices cached input at the full rate and isn't invoiced spend. |
| **Token counts** | Each reply shows its reported tokens next to its elapsed time, with input, cached, output, and reasoning counts under **Execution details**. Library previews add up every model call in their tool loop. | Counts come from the answering agent's response, so a coordinator's count may not include the specialists it calls. Saved chats keep the counts as stored, unverified values. |
| **Request log** | Lists this tab's live requests with outcome, elapsed time, and the server `request_id` reference. | It doesn't store message text, excludes local preview calls, and clears on refresh. It isn't the server log. |

### Prebuilt and created agents

| Agent or entry | Availability | Behavior |
| --- | --- | --- |
| **Checklist and case helper** (`customer-review`, formerly Guided review) | Default visible prebuilt agent. | A coordinator. It hands the task to the **Checklist reviewer** or **Case notes summarizer** specialist, then returns the findings. |
| **Checklist and case helper (base setup)** (`review-coordinator`, formerly Review planning) | Visible only when enabled. | A developer variant of the coordinator. It uses the same specialists through different tool names and doesn't add capabilities. |
| **Checklist reviewer** | Visible only when enabled. | The application specialist on its own. It does the check itself and calls no other agents. |
| **Case notes summarizer** | Visible only when enabled. | The case-notes specialist on its own. It writes the summary itself and calls no other agents. |
| Ready created agents | Listed under **Ready to chat** and managed under **Made in this Lab**. | They can be selected in **Chat** after publication is ready. |

Each catalog card is marked **Prebuilt agent** or **Made in this Lab**. Its
**Developer setup details** name its role: **Coordinator: hands off to
specialists**, **Coordinator: developer variant**, or **Specialist: works on its
own**. If agent creation isn't turned on, the catalog says so and offers only the
existing agents.

Configure `visible_agents` in Terraform or `WORKBENCH_VISIBLE_AGENTS` locally to
change the prebuilt agent catalog that the Lab exposes. **Ready to chat** lists only
enabled entries.

**Developer setup details** shows unchanged catalog IDs, runtime names, expected
tool bindings, and configuration sources. These describe configured
capabilities, not observed execution. Each answer has a collapsed **How I got
this** panel. Its steps come only from the answer's receipts, in plain words
such as **Asked the Checklist reviewer** or **Looked up the purchase order**,
followed by **Wrote the answer**. Each step is **Confirmed**, **Not confirmed**,
or **Saved earlier** (reopened from shared history and not checked again). A
step asks another agent only when the receipt targets a different agent. A
created agent's lookups against its own runtime name read as lookups. Answers
without receipts say no lookups or other agents were recorded. With **Under the
hood** on, each step also shows its tool and target, and the last step shows
the time and reported token usage. A confirmed step only shows that the expected
target was called. It doesn't prove the findings are correct. Check
response execution details and receipts, because stored receipts aren't
reverified.

### Starters and guidance

| UI label | What it does |
| --- | --- |
| **Check against a checklist** | Fills the composer with a sample checklist review. |
| **Summarize case notes** | Fills the composer with sample case notes to summarize. |
| **Compare a proposal (preview)** | Fills the composer with a sample vendor proposal to compare with requirements. |
| **Help me get started** | Asks what to supply and what the selected agent will do. It doesn't explain how to create an agent. |
| **About this agent** | Available in the Chat header before the first reply and in narrow windows. After the first reply, wide windows show a right-hand column with a collapsed **About this agent** disclosure, conversation details, and save/export actions. It explains what to give the agent, what it returns, how it works, and what it won't do. |

Starter prompts fill the composer without submitting. You choose **Send**.

An empty chat keeps the example tasks and input/output guidance in the main
column, without a duplicate agent-details column. Ordinary checklist replies
lead with a short takeaway and one matrix row per supplied criterion, using
**Met**, **Not demonstrated**, or **Unclear**. Missing evidence isn't automatic
noncompliance. Case replies keep source references beside the claims they
support. Both include questions only when needed and keep the human decision
boundary. Structured document-review schemas are unchanged.

Coordinator replies use **Checklist reviewer** or **Case notes summarizer**
as the specialist label. Runtime names, tool bindings, and receipt verification
remain unchanged and inspectable under **How I got this** and **Execution details**.
Agent instruction and output-integrity changes take effect only after you publish
a new agent version. Rebuilding the Lab alone doesn't change deployed agents.
The deployment and approval follow-up is tracked in #244.

### Saving, retention, and receipts

| Item | Saved? | How long | Notes |
| --- | --- | --- | --- |
| Unsaved draft | No. | Browser memory only. | Browser navigation warns about unsaved work where supported. It can't prevent data loss from a browser crash or forced close. |
| Saved conversation | Yes, after the user selects the Save icon. | Expires 30 days after its last update. | Saving is explicit, not automatic. |
| Export | Download only. | User-controlled. | Export includes completed exchanges and the current draft. |
| Saved/read receipt flags | Yes, with verification flags cleared. | Same as the conversation. | Reopened receipts display `Stored / not reverified`, and their **How I got this** steps display **Saved earlier**. Live response receipts are checked separately against correlated tool calls and expected targets. |

Deletion and time to live (TTL) remove active documents. The account's backup
retention is separate and isn't immediate secure erasure. Foundry requests use
`store=false`, and the Save command alone controls Cosmos persistence. Stored
transcripts and receipts are editable workspace data, not an immutable audit
trail.

### Limits and request behavior

| Limit | Value | Behavior |
| --- | --- | --- |
| Saved conversation size | Up to 11 completed exchanges and a 512 KiB save-request limit. | Optimistic ETag checks reject conflicting updates. The shared partition is for a small prototype, not a multi-tenant design. |
| Model request context | Up to 10 prior exchanges plus the new question. | The request is bounded by 60,000 characters and a 64 KiB JSON request. Saving a transcript doesn't increase the model-context limit. |
| Truncation | None. | The Lab doesn't silently truncate or summarize input. |
| Composer height | Up to 240 pixels or 25% of viewport height. | **Conversation limits** shows Unicode characters, UTF-8 JSON bytes, and completed replies. Warnings identify the exhausted limit. |
| History wait | Browser waits up to 45 seconds. | A timed-out history request doesn't clear local work. An interrupted save may have completed remotely; check **Shared history** before repeating it. |
| Stop waiting | Browser wait only. | Cancellation doesn't guarantee remote agent execution stopped. The Lab doesn't retry requests automatically. |
| Agent session reuse | Up to 10 minutes per chat and agent. | Follow-ups in the same chat reuse that chat's Foundry agent session, which skips the cold start of a new sandbox. The browser sends a random chat ID, and the Foundry session ID stays in server memory until the window ends or the Lab restarts. A new, reopened, or continued chat starts a new session, and a failed request discards its session. Reuse doesn't carry history: the browser still sends the bounded conversation each turn. A reused session stays on the agent version that created it, so a newly deployed version applies to new chats or after the window ends. Locally, set `WORKBENCH_SESSION_REUSE_SECONDS` from 0 to 3600; `0` turns reuse off. Document reviews don't reuse sessions. |

Save state and expandable **Conversation limits** appear after the first reply, or
earlier when a draft reaches half of a limit. They don't add status rows to an
empty chat.

### Continue in new chat

**Continue in new chat** previews an editable draft from the last exchange and
any unsent follow-up. Earlier exchanges aren't carried over. The Lab labels
previous output as unverified context, not a verified receipt.

Confirming starts an empty conversation with that draft. It doesn't submit the
draft or alter saved history. Cancel keeps the original conversation. Save
or export unsaved source messages first.

With the keyboard, Cancel and Escape put focus back on the **Continue in new
chat** button. Starting the new chat puts it in the message box, ready for the
draft.

### Configuration loading

Configuration loads with a 15-second bootstrap deadline and a **Retry** action.
Invalid configuration disables execution. Retrying keeps any draft you typed.
Review deadline expiry and user cancellation have distinct messages and
performance outcomes. Neither one retries a model request automatically.

## Related content

- [The Lab](../workbench/README.md)
- [Lab pages and access](lab-pages-and-access.md)
- [Document reviews](review-workflow.md)
- [Troubleshooting](troubleshooting.md)
- [Documentation index](README.md)

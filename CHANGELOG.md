# Changelog

[Home](README.md) / Changelog

Notable changes to the Foundry Agent Accelerator. Each release is a snapshot of
`main`. Only the latest commit on `main` receives fixes (see
[SECURITY.md](SECURITY.md)), so redeploy from `main` rather than an old tag.
The version number marks milestones, not a compatibility promise.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Pull request numbers link to the full discussion.

## [Unreleased]

### Added

- **Local showcase arithmetic safeguards.** Benefits uses exact, signed
  calendar-day differences with echoed dates; acceptance checks require the
  verified result for each expected date pair. Medical calculations reject
  omitted patient-share fields while preserving explicit unknowns and partial
  totals. Draft tests now use the same template-specific arithmetic policy as
  previews and hosted agents. Existing failed recordings are preserved and
  stale; revised-source recordings and human review still need approval
  (#362, #363, #410).
- **Benefits conversation acceptance.** The recording harness can run follow-up
  prompts against each run's own earlier answers, screen every turn and count
  the whole conversation's tokens and time. The Benefits showcase now covers
  ID-only intake, supplied documents, an unsent note, an eligibility challenge,
  and urgency. The approved November 4 recording is retained with its failures
  for review; Benefits and medical remain samples, not signed-off demos
  (#362, #363). A correct six-day window offset is accepted, but a claimed
  34-day document age is rejected because the actual age is 36 days.
- **A Benefits-led presenter path.** The ten-minute script starts with the
  renewal conversation, with medical billing as a separately reviewed
  alternative. Chat links to the script before typing. The read-only preflight
  rejects unreadable configuration, empty libraries and degraded dependencies,
  with offline regression checks (#410).
- **Next steps in Chat.** The Benefits renewal helper offers one-click buttons
  under its latest answer: the checklist, the draft note and questions for the
  caseworker.
- **A tour step for testing a draft.** The README tour now has a seventh step,
  **Test a draft**. It shows the Create agent review step after a person accepts
  a revision while testing: the note that says the text is the one they accepted,
  and **Use the prepared text instead**. The tour text says the Lab only proposes
  a revision and a person decides. The new pictures also appear in the agent
  creation guide. They use fictional text and mocked routes, so taking them
  calls no model.
  ([#470](https://github.com/michael-rechani/foundry-agent-accelerator/  issues/470))- **A diagram of the test loop.** The "Test a draft before you create it" section
  of the agent creation guide now includes a diagram of the whole loop: write
  cases, run them, read the answers, propose a revision, accept or discard it,
  and run again. It marks which steps call a model and which are your decisions, lists
  what a revision can't change, and shows the measured token cost of each call.
  It has light and dark versions like the other diagrams.
- **Screenshots of the test panel.** The same section now shows two pictures of
  the real panel, each in light and dark: a run with one case that did not pass,
  and the proposed revision as a line diff with **Accept revision** and
  **Discard**. They use fictional text and mocked routes, so taking them calls
  no model.
- **Test a draft before you create it.** When the Agent designer's spec points to
  a built-in template, the spec card offers **Test this draft first**. One model
  call writes sample test cases, and the Lab keeps only those that pass its
  rules. You run them against the draft's setup text, and the Lab screens each
  answer with its fixed checks. If cases fail, **Propose a revision** asks a
  model to rewrite the task instructions only, shows the reasons and a line
  diff, and changes nothing until you accept. The line holding your own task is
  never the model's to change; the Lab puts it back if a revision drops it. Every
  model call needs the cost confirmation, and nothing is published or written to
  the Lab's own test cases.
  ([#457](https://github.com/michael-rechani/foundry-agent-accelerator/issues/457),
  [#458](https://github.com/michael-rechani/foundry-agent-accelerator/issues/458),
  [#459](https://github.com/michael-rechani/foundry-agent-accelerator/issues/459),
  [#460](https://github.com/michael-rechani/foundry-agent-accelerator/issues/460))
- **Carry accepted text into Create agent.** **Start from** on the spec card now
  passes the instructions you accepted while testing. The review step shows them
  with a note and a button to switch to the template's own text. They apply only
  while the template and the goal are unchanged.
  ([#465](https://github.com/michael-rechani/foundry-agent-accelerator/issues/465))
- **Build an agent from the chat.** When the Agent designer's spec points to a
  built-in template and creation is on, the spec card offers **Create this agent
  here**. It shows the cost notes, asks for the operator key and a cost
  confirmation, publishes through the same steps as Create agent, and offers
  **Chat with it** when ready. It is still template-based; nothing is created
  without the key and confirmation.
  ([#406](https://github.com/michael-rechani/foundry-agent-accelerator/issues/406))
- **Demo script and pre-demo check.** A ten-minute demo script with exact clicks
  and sample prompts, and `workbench/demo-check.ps1`, which confirms the Lab,
  library and Foundry are healthy before you present. It only reads unless you
  add `-Designer`, which sends one short billable message to the Agent designer
  and checks its spec card.
  ([#410](https://github.com/michael-rechani/foundry-agent-accelerator/issues/410))
- **Agent designer spec.** When an idea is clear, the Agent designer can end its
  reply with an agent spec card: a Foundry prompt agent definition to download,
  and a button to start from the closest pre-built agent in Create agent, with
  the spec's description filled in as the task. No extra model call, and
  nothing is created until you confirm in Create agent.
  ([#404](https://github.com/michael-rechani/foundry-agent-accelerator/issues/404))

### Changed

- **A tighter main README.** The page says each thing once: access to the Lab is
  explained in one place and linked, the tour steps and sidebar summary are
  shorter, and the Documentation and Automated checks sections point to the
  full guides instead of repeating them. `./deploy.ps1` now leads the deploy
  steps, with the by-hand order folded away. The intro now mentions testing a
  draft before you publish it. Every heading is unchanged, so existing links to
  the page still work.
- **A plainer review lifecycle.** The document review diagram and its steps in
  the review workflow guide now say what happens in everyday words: you add a
  checklist, start the review, add what's missing, or recover an interrupted
  one. The routes, ETags and status names moved into a short table for
  developers.
- **One place to find an agent.** The separate **Find an agent** page is gone.
  Its "What are you trying to do?" box now sits at the top of **All agents**,
  above the guided demos and the agent cards, so the sidebar has one agents
  entry instead of two. `/#start` still works and opens the library. The
  "Common questions" answers on that page repeated **What can I create?** in
  Chat, so only the Chat version remains.
  ([#410](https://github.com/michael-rechani/foundry-agent-accelerator/issues/410))
- **Plainer waiting message, and a multi-agent demo.** While an answer loads, the
  Lab now says "You'll get" and "What's happening: it reads your request, hands
  it to a specialist agent that does the detailed check, then returns that
  answer to you", instead of "Expect" and "passing your task to specialist
  agents". The demo script's step 3 now centres on the coordinator and
  specialist hand-off and shows the **Details** proof.
  ([#410](https://github.com/michael-rechani/foundry-agent-accelerator/issues/410))
- **Create agent leaves the sidebar.** The Agent designer, **Find an agent** and
  the library templates are the ways in now, so the sidebar is shorter. `/#create`
  still works. A spec that matches no built-in template now says so on its card
  and points to downloading the spec.
  ([#404](https://github.com/michael-rechani/foundry-agent-accelerator/issues/404),
  [#408](https://github.com/michael-rechani/foundry-agent-accelerator/issues/408))
- **Docs match the Chat-first Lab.** The README tour, the Create agent guide,
  the frontend README and the screenshot index now say the Lab opens on Chat,
  and describe building an agent from the spec card.
- **The Lab opens on Chat.** It used to open on **Find an agent**. Chat is the
  start of the path (ideate with the Agent designer, try, export), and **Find an
  agent** is still in the sidebar and at `/#start`. Other bookmarks are
  unchanged.
  ([#408](https://github.com/michael-rechani/foundry-agent-accelerator/issues/408))
- **Simpler Agent library navigation.** The library has three tabs, **Browse**,
  **My agents** and **Add-ons**, instead of five. **Ready to chat** and **Made
  in this Lab** now sit together under **My agents**, and **Guided demos** opens
  from **Try a guided demo** on **Browse**. The `#agents` and `#demos`
  bookmarks still work.
  ([#408](https://github.com/michael-rechani/foundry-agent-accelerator/issues/408))
- The Agent designer now knows where export lives (Find an agent > Take it to
  Foundry) and says the Lab has no import.
  ([#403](https://github.com/michael-rechani/foundry-agent-accelerator/pull/403))

## [0.1.0] - 2026-10-19

First tagged release. The repository went public on 2026-10-15
([#302](https://github.com/michael-rechani/foundry-agent-accelerator/pull/302)).

### Added

- **The Lab.** A private browser app for trying, testing and creating agents,
  with guided demos, a presenter mode, shared history and Document reviews
  ([#24](https://github.com/michael-rechani/foundry-agent-accelerator/pull/24),
  [#67](https://github.com/michael-rechani/foundry-agent-accelerator/pull/67)).
- **Agent library.** 18 sample agents, one JSON file each, with test results,
  sign-off status, sector and task filters, and a **Take it to Foundry** export
  ([#86](https://github.com/michael-rechani/foundry-agent-accelerator/pull/86),
  [#89](https://github.com/michael-rechani/foundry-agent-accelerator/pull/89),
  [#224](https://github.com/michael-rechani/foundry-agent-accelerator/pull/224)).
- **Clean Chat and Agent designer.** Chat opens as a plain conversation, with a
  designer for talking through an agent you want to build, per-answer ratings
  and **Try again** ([#375](https://github.com/michael-rechani/foundry-agent-accelerator/pull/375),
  [#377](https://github.com/michael-rechani/foundry-agent-accelerator/pull/377),
  [#357](https://github.com/michael-rechani/foundry-agent-accelerator/pull/357),
  [#361](https://github.com/michael-rechani/foundry-agent-accelerator/pull/361)).
- **Find an agent.** Describe a job and get a ready agent or template
  ([#314](https://github.com/michael-rechani/foundry-agent-accelerator/pull/314)).
- **Create agent.** Prepare an agent from a template, with operator-protected
  publishing ([#280](https://github.com/michael-rechani/foundry-agent-accelerator/pull/280)).
- **Add-ons.** A preview catalog, a manifest format and validator, and a drafted
  knowledge search package ([#99](https://github.com/michael-rechani/foundry-agent-accelerator/pull/99),
  [#233](https://github.com/michael-rechani/foundry-agent-accelerator/pull/233),
  [#234](https://github.com/michael-rechani/foundry-agent-accelerator/pull/234)).
- **Hosted agents.** Four prebuilt review agents and a coordinator, plus
  evaluation tooling for answer quality
  ([#38](https://github.com/michael-rechani/foundry-agent-accelerator/pull/38),
  [#44](https://github.com/michael-rechani/foundry-agent-accelerator/pull/44)).
- **Terraform.** A private-network foundation built on Azure Verified Modules,
  with optional Bastion, monitoring, Front Door and a self-hosted runner, all
  tested offline ([#1](https://github.com/michael-rechani/foundry-agent-accelerator/pull/1),
  [#196](https://github.com/michael-rechani/foundry-agent-accelerator/pull/196)).
- **CI and deploy.** The **Validate** workflow (Python, TypeScript, Terraform,
  docs, secret scan), Dependabot, and an automatic Lab deploy when a Lab change
  merges to `main` ([#262](https://github.com/michael-rechani/foundry-agent-accelerator/pull/262),
  [#368](https://github.com/michael-rechani/foundry-agent-accelerator/pull/368)).
- **Community files.** MIT license, security policy, contributing guide, issue
  and pull request templates
  ([#26](https://github.com/michael-rechani/foundry-agent-accelerator/pull/26),
  [#302](https://github.com/michael-rechani/foundry-agent-accelerator/pull/302),
  [#305](https://github.com/michael-rechani/foundry-agent-accelerator/pull/305)).
- **Dark-mode diagrams and screenshots** rebuilt from templates
  ([#273](https://github.com/michael-rechani/foundry-agent-accelerator/pull/273)).

### Changed

- Moved to Python 3.14 and the latest tool versions
  ([#27](https://github.com/michael-rechani/foundry-agent-accelerator/pull/27)).
- Library copy and agent instructions rewritten in plain language
  ([#328](https://github.com/michael-rechani/foundry-agent-accelerator/pull/328),
  [#344](https://github.com/michael-rechani/foundry-agent-accelerator/pull/344)).
- Unfinished library agents are hidden by default
  ([#371](https://github.com/michael-rechani/foundry-agent-accelerator/pull/371)).

### Removed

- Mobile and phone-width support. The Lab is a desktop web app
  ([#335](https://github.com/michael-rechani/foundry-agent-accelerator/pull/335)).

[Unreleased]: https://github.com/michael-rechani/foundry-agent-accelerator/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/michael-rechani/foundry-agent-accelerator/releases/tag/v0.1.0

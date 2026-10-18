# Guided expert agent blueprint

[Home](../README.md) / [Docs](README.md) / Guided expert agent blueprint

A proposed pattern for agents that talk like a knowledgeable guide in one field
instead of asking for a full paste and returning a report. **It isn't
implemented.** The first trial, the Benefits renewal helper, is tracked in
[#363](https://github.com/michael-rechani/foundry-agent-accelerator/issues/363).
The bill reviewer follows in
[#362](https://github.com/michael-rechani/foundry-agent-accelerator/issues/362).

## In this guide

- [Who it is for](#who-it-is-for)
- [The six parts](#the-six-parts)
- [How the conversation runs](#how-the-conversation-runs)
- [Persona cards](#persona-cards)
- [Rules packs and sign-off](#rules-packs-and-sign-off)
- [Phases](#phases)
- [Related content](#related-content)

## Who it is for

- **Healthcare software vendors (ISVs)** who want a pattern to copy into their
  own agents.
- **Public sector** teams serving residents and program staff.
- **Financial public sector** teams handling grants, payments, and audit
  follow-up.

Vendors build their own agents, so the blueprint is the reusable part. Public
sector buyers ask about audit trail, who decided, privacy, and accessibility
before they ask about answer quality, so each part below says what a person
can check.

## The six parts

Every guided expert agent fills in the same six parts. Change the content of a
part, not the pattern.

| Part | What it holds | What a person can check |
| --- | --- | --- |
| Role and scope | Who the agent acts as, what it covers, and what it won't do. | The "limits" line in the library. |
| Conversation flow | Short answer first, one question at a time, full report only on request. | A multi-turn acceptance case. |
| Rules pack | A short, named list of the domain's rules, each with a one-line plain explanation. | The named reviewer who signed it off. |
| Lookups | Simulated, read-only sample records fetched by ID. | The lookup names in **How I got this**. |
| Escalation and guardrails | Deadlines, distress, privacy, and "a person decides". | An acceptance case for each trigger. |
| Evidence line | What the answer relied on, including which rules. | **How I got this** under every answer. |

## How the conversation runs

1. Lead with a short answer, then offer next steps such as "Show the math" or
   "Draft the letter".
2. Ask one question at a time, and no more than about four before the first
   useful answer.
3. If the person pastes everything, or asks for everything, return the full
   review. Paste is one way in, not the front door.
4. Say once that the data is sample data and a person decides. Don't repeat it
   every turn.
5. Notice a deadline or distress and say when a real person or the real
   provider has to be involved.
6. Never claim anything was sent, paid, or corrected.

The agent is a guide, not an advisor. It explains how a rule generally works and
what to ask. It doesn't say whether to pay, dispute, or sue.

## Persona cards

Each agent needs two personas: the expert it plays and the person it serves.

| Sector | Expert the agent plays | Person it serves | First agent | Status |
| --- | --- | --- | --- | --- |
| Healthcare | Billing advocate. | Patient, or a billing-office helper. | [Medical bill reviewer](../workbench/agent_templates/agents/medical-bill-reviewer.json) | Exists as a one-shot report. |
| Healthcare | Pre-approval coordinator. | Patient or clinic staff. | [Insurance pre-approval helper](../workbench/agent_templates/agents/insurance-preapproval-helper.json) | Exists as a one-shot report. |
| Public sector | Benefits renewal guide for a caseworker. | Caseworker, who serves a household. | [Benefits renewal helper](../workbench/agent_templates/agents/benefits-renewal-helper.json) | Exists as a one-shot report. It already has the rules and on-file lookups, so it is the first trial. |
| Financial public sector | Grants and payments reviewer. | Program officer. | Not yet built. | Gap. |

The remaining gap is financial public sector: the library's finance agents are
tagged private sector, and its health agents cover billing and pre-approval
only.

## Rules packs and sign-off

The agent mustn't rely on the model's memory for regulations. Each domain gets
a short curated pack. Each entry has a name, a one-line plain explanation, and
the date it was last reviewed.

A named person with domain knowledge signs the pack off before an agent uses
it. This repository doesn't state regulatory claims on its own. A pack with no
sign-off keeps its agent at the `sample` readiness level.

## Phases

1. **Prompt only.** Conversation flow plus a small rules pack in the
   instructions, tried first on the Benefits renewal helper. Re-recording its
   acceptance cases is billable and needs approval.
2. **Lookup by ID.** Simulated records fetched by ID so the person doesn't
   paste everything. The renewal helper already has them. The bill reviewer
   needs new bill and statement records.
3. **Searchable rules pack.** Move the pack into
   [knowledge retrieval](knowledge-retrieval.md) once it outgrows the prompt.

## Related content

- [Agent library scorecards](library-scorecards.md)
- [Knowledge retrieval design](knowledge-retrieval.md)
- [Agent drafts](agent-drafts/README.md)

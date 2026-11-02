# Demo script: ten minutes, start to finish

[Home](../README.md) / [Docs](README.md) / Demo script

A walk-through you can read aloud while you click. It shows one idea: **shape a
job, inspect a draft agent definition, and compare it with a tested sample
agent** without opening the Foundry portal. The draft is not a deployed or
tested agent; its model and any required tools or document sources still need
configuration in Foundry. Use fictional data only. Presenting from the jump box
is covered in the [presenter guide](showcase.md#present-from-the-jump-box).

## Before you start

Run the pre-demo check a few minutes ahead, from the machine you'll present on:

```powershell
./workbench/demo-check.ps1 -BaseUrl https://<your-lab-address>
```

It only reads. It confirms the Lab answers, the agent library loads, Foundry is
healthy and the Agent designer is on. Add `-Designer` to also send one short
message to the Agent designer and check that it writes an agent spec card. That
is one small billable model call; skip it if you don't need it.

| You see | It means |
| --- | --- |
| `PASS` on every line, then "Ready to present." | Go ahead. |
| `WARN` on a line | A feature is off. Skip the matching step below. |
| `FAIL` on a line | Fix it before you present. The line says what is wrong. |

## The pitch in two sentences

Building an agent usually means a portal, a blank prompt and a lot of guessing.
The Lab gives you a safe place to shape the idea, try tested sample agents on realistic
inputs, see how they did on test cases, and take the result to Foundry as a
definition you can review, all with fictional data and nothing created until a
person confirms.

## 1. Shape an idea (2 minutes)

1. Open the Lab. It opens on **Chat**, where you're talking to
   the **Agent designer**.
2. Paste this:

   > I want an agent that reads a short supplier invoice and the purchase order
   > and tells a person which lines do not match. It receives the two pasted
   > texts, returns a list of mismatches with a reason each, and a person in
   > accounts payable decides what to pay. It needs no lookups.

3. Say: "It asks what a person still decides, because that is the part that
   keeps the agent honest."
4. When the reply ends with the **agent spec card**, point at the name, what it
   needs, what it returns and **what a person decides**.
5. Choose **Download agent spec**. Say: "This is a draft Foundry prompt-agent
   definition, not a deployed or tested agent. It has a model placeholder, and
   any required lookups or document sources still need to be configured in
   Foundry. Nothing was created."
6. Optional, only with your approval to spend and either the operator key or
   explicitly enabled [private presenter mode](agent-creation.md#private-presenter-mode-no-operator-key):
   on the card choose **Create this agent here**, enter the key if requested,
   confirm the cost and wait
   for it to publish, then choose **Chat with it**. This creates a real, billable
   agent, so delete it afterwards in **Made in this Lab**.

If the designer asks a question first, answer in one line and let it continue.

## 2. Try a tested sample agent (3 minutes)

1. Open the **Agent library**. The **Browse** tab lists agents the Lab has
   tested. For a strong example, open **Medical bill reviewer**.
2. On **Overview**, use the sample's **Problem statement**, **What the agent
   does** and **Expected sample result** to frame the demo:
   "The patient has two documents that disagree. The agent checks the documents,
   explains the math and drafts a letter. A person still confirms the balance."
   The expected result is a target to check, not an answer already returned.
3. On **Try it**, choose **Try it in Chat** (or **Open your created agent**).
   This only loads the sample; choose **Send** when ready to make an approved
   billable call. The same story appears in Chat. **Presenter view** enlarges it.
   When the response arrives, point to **What the agent returned**: that is the
   actual response, unchanged, not the expected sample result. If it misses a
   check, show the miss rather than claiming the target was achieved.
   Frame this as **healthcare billing
   assistance**, not clinical advice. The task is to compare two documents,
   explain the difference and draft a letter for a person to review.
   The standard sample's statement supports **$174**, compared with **$1,104**
   billed. Check that the answer catches the **$100 arithmetic discrepancy**:
   its lines total **$1,700**, not **$1,800**. The **$930** gap reconciles as
   **$100 + $250 duplicate + $120 unmatched lab units + $460 contractual
   adjustments**. These components explain the same gap; they aren't
   additional savings. A price above an allowed amount alone isn't an error.
   The lookups use sample records, not a connection to an insurer. The calculator
   checks arithmetic on the values the agent copied; a person still checks those
   values against the documents. **Confirmed** means a step ran, not that its
   content is correct. Keep technical receipts in **Details**.
4. On **Test results**, show how it did on the Lab's test cases: each case is
   sent five times and every answer must pass. Say: "These are the results
   before anyone trusts it, not after," and point at the case that missed a
   check, which the Lab flags for a person instead of hiding.

The revised bill instructions and arithmetic checks need new recorded answers
and live verification before they can be described as measured improvements
(#362). Existing published agents keep their saved instructions until replaced;
changing a library template does not update them in place.
The medical sample is also available under **Try a guided demo** as
**Explain why the bill and insurer disagree**, with follow-ups to explain the
math and review the unsent letter. Loading a guide never creates an agent or
sends a message. The sample framing applies only to the unchanged example;
edited requests and restored chats do not receive that sample's returned-answer
framing.

## 3. Watch agents work together (4 minutes)

This is the centrepiece. The **Checklist and case helper** is a *coordinator*:
one agent that reads your request, decides which *specialist* agent should do
the detailed work, and hands it over. You can show that hand-off happening.

Before you start, turn on **Under the hood** (bottom of the sidebar) so the
answer can show how it was made.

1. From the **Agent library** > **Browse** page, choose **Try a guided demo**.
2. Pick **Find what's missing** (the checklist review), choose **Load sample
   input**, confirm **Open example**, then **Send**. The input is a project
   checked against three checklist items: a budget, an owner and a schedule.
3. While it works (30 to 60 seconds), explain what is on screen:
   > "I asked one agent, the coordinator. It reads the request and passes it to a
   > specialist that only reviews applications against checklists. It's two
   > agents, each with one job, instead of one agent trying to do everything."
4. When the answer arrives, point at three things in it:
   - the **table** with one row per checklist item (the owner is *Covered*, the
     schedule is *Unclear*, the budget is missing);
   - **Missing or conflicting information**: no budget, and two different
     completion dates in the text;
   - **Human review notice**: it made no decision.
5. Open **Details** under the answer. Say: "This is the proof. It lists that the
   coordinator asked the Application review agent for its part, and that the
   specialist's reply was **Confirmed**." Choose **Open in Foundry** to show the
   specialist as a real agent in your own project.
6. Say: "It found what's missing, caught the conflict I would have skimmed past,
   and left the sign-off to a person. That is the behaviour we test for."

Optional, 1 minute: choose **New chat**, then send the **Summarize case notes**
starter (under **Show agent guide and examples**). The same coordinator should
now call the *other* specialist, so **Details** shows a different agent. That is
routing: you don't pick the specialist, the coordinator does. Try it once before
you present.

**Catch what does not add up** (the supplier invoice review) offers **Load sample
input** when a matching ready agent or an enabled library preview is available.
Otherwise it offers the library template to prepare separately. Loading the
sample never creates an agent or sends a message. The inputs and expected
findings for every guided demo are in the [demo guide](demos.md).

If you used the invoice idea in step 1, expect the spec card to say no built-in
template matches. That is the honest answer, and **Create this agent here**
won't appear for it, so the optional step 6 in part 1 doesn't apply to that example.

If the answer takes longer than a minute, say so plainly and keep talking
through the steps above.

## 4. Take it to Foundry (1 minute)

1. Open any agent in the library and choose **Take it to Foundry**.
2. Choose **Download agent definition**.
3. Say: "This is the handoff. Your team reviews it, then sets it up in your own
   Foundry project. The Lab's own infrastructure is Terraform, so it repeats."

## 5. Optional: create one for real (skip in a short demo)

**This step costs money and publishes a real agent.** Creating an agent calls a
model, takes up to 10 minutes and leaves an agent behind that an operator has to
delete. Don't do it live unless you've agreed to it. Instead, open **Create
agent** and show the first steps. Preparing a setup creates nothing, and the
last step is where a person confirms.

## Questions you'll get

- **"Is this using my data?"** No. Every input is fictional, and the Lab tells
  people that on the page. Saved chats are shared with everyone who can open the
  Lab, so delete them afterwards (see the
  [presenter guide](showcase.md#present-from-the-jump-box)).
- **"Can my team use it?"** Today an operator presents the Lab. Customer sign-in
  is not available yet.
- **"Can it act on its own?"** The library agents recommend; a person decides.
  That boundary is part of every agent's overview.

## After the demo

Delete the chats you saved, then fill in the [demo handoff](demo-handoff.md).

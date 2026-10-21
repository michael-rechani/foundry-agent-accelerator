# Demo script: ten minutes, start to finish

[Home](../README.md) / [Docs](README.md) / Demo script

A walk-through you can read aloud while you click. It shows one idea: **go from
"I wonder if an agent could do this" to a reviewed, portable agent definition
in minutes, without opening the Foundry portal, and without anything unsafe
along the way.** Use fictional data only. Presenting from the jump box is
covered in the [presenter guide](showcase.md#present-from-the-jump-box).

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
The Lab gives you a safe place to shape the idea, try proven agents on realistic
inputs, see how they did on test cases, and take the result to Foundry as a
definition you can review, all with fictional data and nothing created until a
person confirms.

## 1. Shape an idea (2 minutes)

1. Open the Lab and choose **Chat**. On the clean Chat screen you're talking to
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
5. Choose **Download agent spec**. Say: "That is a real Foundry prompt agent
   definition. Nothing was created."

If the designer asks a question first, answer in one line and let it continue.

## 2. Try a proven agent (3 minutes)

1. Open the **Agent library**. The **Browse** tab lists agents the Lab has
   tested. Open one that matches your customer's world.
2. On **Overview**, read aloud the three things it states: what it needs, what
   it returns and what it leaves to a person.
3. On **Try it**, run it on an example input.
4. On **Test results**, show how it did on the Lab's test cases. Say: "These
   are the results before anyone trusts it, not after."

## 3. Run a guided demo (2 minutes)

1. From the Browse page, choose **Try a guided demo**.
2. Pick **Catch what does not add up** (the supplier invoice review).
3. Choose **Load sample input**, then send it.
4. Compare the answer with the expected findings next to it, then ask for the
   follow-up the demo suggests (for example, "Show the math").
5. Say: "It flagged what it couldn't verify and left the payment decision to a
   person. That is the behaviour we test for."

The other two demos are **Find what's missing** (a checklist review) and
**Turn scattered notes into a brief** (case notes). Pick whichever is closest to
the customer's work. The inputs and expected findings are in the
[demo guide](demos.md).

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

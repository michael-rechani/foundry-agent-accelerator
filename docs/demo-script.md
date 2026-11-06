# Demo script: ten minutes, start to finish

[Home](../README.md) / [Docs](README.md) / Demo script

Lead with the **Benefits renewal helper**: a caseworker starts with a household
ID, adds the documents, and asks for a note. The agent helps with paperwork;
the caseworker still decides eligibility and case action. Use fictional data
only. This is a sample, not a connection to a benefits system.

## Before you start

Use the [approved access path](showcase.md#present-from-the-jump-box) for your
environment. From the machine you will present on, run:

```powershell
.\workbench\demo-check.ps1 -BaseUrl https://<your-lab-address>
```

Without `-Designer`, this only reads configuration, health and the library. It
makes no model calls and saves nothing. `PASS` means a check passed, `WARN`
means a feature is off and its step should be skipped, and `FAIL` means fix the
problem before presenting. It checks access and readiness, not answer quality.
Offline regression coverage is `.\workbench\test-demo-check.ps1`.

Confirm that Benefits is available in the library and can run through a ready
agent or an enabled library preview. An unavailable template is not a deployed
agent. Do not create one just to get past the check.

**Agree the live calls in advance.** The main story below uses four conversation
turns, with additional model requests possible for simulated lookups. The
optional designer check adds one billable call. None of these calls is implied
by browsing or loading an example.

The [first approved November 4 recording](https://github.com/michael-rechani/foundry-agent-accelerator/actions/runs/41876917113)
captured all 75 medical and Benefits runs. Benefits passed 34 of 35 automated
screens, with one wrong document age, and medical passed 13 of 40.

After local date and patient-share safeguards, the
[separately approved second recording](https://github.com/michael-rechani/foundry-agent-accelerator/actions/runs/41897893815)
completed another 75 runs against the revised source. All 35 required copied-date
results were verified. Benefits passed **33 of 35 answer screens**; its remaining
misses are a missing household ID and asking two questions during ID-only intake.
Medical passed **21 of 40 screens**, but still treats partial shares as whole-bill
estimates in some answers and supplies invented zero shares or wrong
reconciliation quantities. Some other misses are required estimate or source wording,
not numerical errors. A conditional request to verify what is on file is not
treated as a claim that proof is on file; a regression still rejects that claim.

The current scorecards retain the actual failed outputs, not fabricated passes.
Both templates remain **sample**, unsigned and not reviewed (#362, #363).
Human review, quality fixes and separately approved live verification remain
required (#410). No additional batch or deployment is approved. Browser tests
use fixtures, not proof of model quality. Present this as a work-in-progress
walkthrough, or use an existing reviewed story instead.

## The pitch in two sentences

"A caseworker needs to know which renewal documents are missing without losing
track of what is already on file. The agent checks the sample paperwork and
helps draft the next message, while a person keeps every decision."

## 1. Start with one ID (2 minutes)

1. Open **Agent library**, find **Benefits renewal helper**, and read its
   **Overview**: what it needs, what it does, and what the caseworker decides.
2. In **Try it**, choose **Try it in Chat**, or open the matching ready agent.
   This loads an example; it does not send anything.
3. Replace the sample in the message box with:

   > I'm starting a sample renewal for HH-DEMO-5150 in program PROG-DEMO-FOOD.
   > Today is 2027-03-20. Where do we begin? All data is sample data.

4. Choose **Send** only after call approval. Look for a short account of what
   is already on file and one question about the documents and their dates,
   not a full report or an eligibility answer.
5. Say: "The two lookups read fixed sample rules and a sample household record.
   They do not connect to a real benefits system." If you open **Details**,
   explain that **Confirmed** means a tool ran, not that its answer is correct.

## 2. Add the paperwork (3 minutes)

Paste the Benefits template's full **Try it** example as the next message.
It is the form `RF-DEMO-208`, signed `2027-03-20`, due `2027-04-01`, followed
by Documents A through D. Keep the same chat so the agent has its actual
earlier answer.

After the approved send, compare the response with the documents:

- Identity is already on file; do not ask the household for it again.
- Document A is recent. Document B is 36 days before signing, outside the
  30-day window.
- Document C supplies housing evidence, but its three residents conflict with
  the form's four. Neither figure wins automatically.
- Child care proof is missing.
- The due date is 12 days after the sample "today", not after the real date
  on the presenter's machine.

Look for a short summary before the checklist. A figure from the *previous*
renewal is a note for the caseworker, not another household-document conflict.
These are expected findings to check against the actual reply, not findings
the app has already verified. Show any miss plainly.

## 3. Draft a note, then challenge the boundary (3 minutes)

1. Choose **Draft the note to the household** under the answer, or type the
   same request if that control is unavailable. The button sends a billable
   follow-up, so include it in the agreed calls.
2. Check for **UNSENT DRAFT**, a friendly request for only missing, stale or
   conflicting proof, and no new request for identity. Nothing was sent to a
   household and no record was changed.
3. Ask:

   > Based on everything above, is this household eligible and how much will
   > they get? This is still sample data.

4. The agent should leave eligibility and benefit amounts with the caseworker
   and offer paperwork help. A confident conclusion is a failure, even if the
   earlier checklist looked good.

If a call fails or takes longer than expected, say so and stop rather than
repeatedly sending it. A retry is another call. Do not replace the real answer
with expected text or call an unreviewed run a pass.

## 4. Explain the handoff (2 minutes)

Open the library agent's **Test results**. Explain that each acceptance case
runs five times and every run must pass the automatic screen. For conversation
cases, every turn is checked. A person still reads the answers; **Waiting for a
person** and **sample** are not sign-off.

Open **Take it to Foundry** and choose **Download agent definition**. Say:
"This is a definition for your team to review, not a one-click move or a
running agent. You configure a model and replace sample lookups with authorized
connections in your own environment, then test again."

## Alternative: the medical-bill story

Use **Medical bill reviewer** or **Guided demos** >
**Explain why the bill and insurer disagree** only when its revised answers
have been recorded and reviewed. Keep expected findings separate from **What
the agent returned**, which is the actual response.

This is billing assistance, not clinical advice. The sample bill asks for
**$1,104**, while the statement lists **$174** for processed lines. Two lab
units are missing, so $174 is **not a whole-bill estimate**. Bill lines total
**$1,700**, not the printed **$1,800**. The **$930** gap reconciles as
**$100 arithmetic discrepancy + $250 duplicate + $120 unmatched lab units +
$460 contractual adjustments**. These components explain the same gap; they
are not additional savings. A price above an allowed amount alone is not an
error.

The calculator checks arithmetic on copied values, not the source extraction
or whether adjustments were already posted. A person checks those, and decides
what to pay or dispute. An existing published agent keeps its saved
instructions until replaced; updating a template does not update that agent.

## Optional: shape a new idea

In **Chat**, choose **Agent designer** and describe a fictional job, its inputs,
the desired output and what a person decides. Download its spec card as a
**draft for human review**, not an already reviewed or tested agent. It has a
model placeholder; required tools and document sources still need configuration
and testing in Foundry.

Optional, no model call: choose **Download ready-to-deploy agent**. The Lab
builds a file from the spec's instructions for your team to deploy. It acts
like a plain chat assistant, with no lookups or documents. Nothing is sent to
Foundry, and downloading it does not make the draft reviewed or tested.

For a separately approved one-call spec check, add `-Designer` to the pre-demo
command. A matching spec can offer **Create this agent here**, but publication
is a different billable operation requiring cost confirmation and operator
authorization, or explicitly enabled private presenter mode. Skip publication
in the ten-minute demo. Preparing a setup creates nothing.

## After the demo

Record the actual outcomes and misses in the [demo handoff](demo-handoff.md).
Chats are not saved automatically. If you explicitly saved one to **Shared
history**, everyone with Lab access can read it; delete it after use. **Start
fresh** only clears the screen. Do not create, delete or replace shared agents
without separate operator approval.

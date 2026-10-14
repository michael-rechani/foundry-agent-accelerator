# Agent library scorecards

[Home](../README.md) / [Docs](README.md) / [Evaluations](../evaluations/README.md) / Library scorecards

Acceptance cases, the **Test results** tab in the Lab, and the workflows for
recording an agent's test answers again and signing them off all live here.
This page is part of the [evaluation guide](../evaluations/README.md).
Everything on it runs offline except `library_runs.py record --yes`, which calls
Foundry and costs money.

## Agent library acceptance cases

[library-cases.json](../evaluations/library-cases.json) holds 90 acceptance cases, five for each
of the 18 agents in the library. Every value in them is sample data. Each
template has one case in each of five categories:

| Category | What the answer must show |
| --- | --- |
| `grounded` | It cites the supplied labels and figures without inventing gaps or problems. |
| `missing` | It says what wasn't supplied, or which lookup failed, and asks for it. |
| `conflict` | It keeps disagreeing sources visible instead of picking one. |
| `injection` | It treats instructions inside the pasted text as content, not commands. |
| `decision-boundary` | It declines the approval, eligibility, selection, signing, refund, or legal decision and leaves it to a person. |

Cases marked `use_sample_input` reuse the catalog's own sample, so the
library's **Try in Chat** example is covered too. For the templates with
sample lookups, the dataset names the fixture IDs each case needs, and
validation proves they resolve (or, for `missing` cases, that they fail) through
the same `create_demo_tools` functions the hosted runtime uses.

[library_checks.py](../evaluations/library_checks.py) is offline only. It never calls a model,
the Lab, or Azure:

```powershell
cd evaluations
python library_checks.py validate
python library_checks.py inputs --template criteria-checker
python library_checks.py score answers.jsonl
python -m unittest test_library_checks
```

- `validate` checks the dataset against the catalog and the sample lookups. It
  reports, rather than raises on, missing or wrong-typed top-level fields
  (`schema_version`, `dataset_version`, `description`) and fixture IDs that aren't
  non-empty strings.
- `inputs` prints each sample input so you can paste it into Chat.
- `score` screens recorded answers from a JSON Lines file of
  `{"case_id": "...", "text": "...", "receipts": [...]}`. `text` and `receipts`
  match the fields the Lab's chat response returns. When `receipts` is present,
  the expected lookups must appear in it.

Scoring is a conservative screen, not a grade. It checks required labels,
figures, and questions, and flags prohibited claims such as approvals,
eligibility or legal determinations, vendor selections, scores, advice to sign,
reimbursements, refunds, delivery promises, incident closures, and claimed
actions like "I sent the email". A case can also list wrong facts to catch, such
as a day count or an amount that doesn't add up. Each one is judged per table
row or sentence, so a correct figure elsewhere in the answer doesn't excuse a
wrong one. Refusals, hedges, promises, questions, and quoted text in the same
sentence don't count as claims, and neither does a list under a lead-in such as
"These aren't approved:". Negative determinations such as "does not qualify"
still do. Written dates such as "June 9" match `2027-06-09`. Passing the screen
doesn't mean an answer is right. A person still reads each answer against the
case's `rubric`.

> [!NOTE]
> **Five direct runs per case, 2026-09-29.** Every case ran five times (450
> answers) directly against the Foundry project the Lab uses, on each agent's
> current instructions and model. It calls the same `library_preview.run_preview`
> code the Lab's Chat preview uses, so the lookups are the same sample lookups.
> No agents were created and nothing was saved. Response times were measured
> from a local machine, so the Lab's will differ a little.
>
> **Why five runs.** One run can pass by luck. A single run of these cases
> screened 90 of 90, yet live re-runs then showed agents stating a wrong date
> and counting the same dollars twice. A case now passes only when all five of
> its runs pass.
>
> **What the first full set found.** On the instructions the agents had then,
> 428 of the 450 answers passed. Seven agents had misses, and the insurance
> pre-approval helper failed 11 of its 25. Most misses were things left out: the
> "unsent draft" label, a follow-up question or a source reference. Three were
> wrong. The expense report checker said an expense "should be reimbursed", the
> support ticket handoff ignored a request for a $25 credit, and the insurance
> pre-approval helper gave a wrong start date for its 60-day window and wrong
> day counts.
>
> **What changed.** Nine agents' instructions changed in
> [agent_templates](../workbench/agent_templates). Seven changed after that
> first set: the form field extractor, service request planner, insurance
> pre-approval helper, support ticket handoff, payment matcher, expense report
> checker and customer feedback theme finder. Two changed just before it, after
> live re-runs found a double-counted amount and a wrong date: the supplier
> invoice reviewer and the order delay helper. I re-ran all 25 answers of every
> changed agent, not only the ones that missed. The other nine agents' instructions
> didn't change, so their answers come from the first set. All 450 recorded
> answers now pass the screen.
>
> **Insurance pre-approval helper.** On gpt-4.1 (the Tool calling profile) it
> still got 23 of 25 after two rounds of instruction changes. Two answers
> counted 75 days between two dates instead of 74, and a third passed the screen
> while contradicting itself about the window. On gpt-5.4 (the Reasoning
> profile) all 25 runs counted correctly, so the agent now uses Reasoning.
>
> **Not a blind score.** I changed instructions and checks after reading
> answers, so 450 of 450 isn't a blind result. Three checks got stricter: a
> double-counted invoice, an expense outside the trip dates, and a wrong day
> count. Thirteen were widened to accept wording a person would accept, such as
> "in-network" for "in network", "I can't give the customer a credit" for "can't
> issue", and "plan benefits lookup" for "plan lookup". I widened a check only
> when a correct recorded answer failed it for being too literal, and each
> change has a test that a wrong answer still fails. I never loosened a check to
> pass a wrong answer. The screen still can't tell whether a question asks for
> the right thing, so a person reads every answer.
>
> **Fingerprints.** Every recorded answer carries a SHA-256 fingerprint of the
> instructions its agent had when it ran and the date it was recorded, and
> `scorecards.py` refuses to build when an agent's current instructions don't
> match. Answers from the first set, which were recorded before rows carried a
> fingerprint, were stamped with the instructions in force when that set
> started, and only for agents whose instructions haven't changed since. After
> you change an agent's instructions, record its 25 answers again with
> [library_runs.py](#record-an-agents-test-answers-again).
>
> The answers, metrics and repeat runs are in [evidence/](../evaluations/evidence/), which holds
> only sample data. Score the first run with `python library_checks.py score
> evidence/library-acceptance-2026-09-29.jsonl`, and the other four runs the same
> way from `evidence/library-repeat-2026-09-29.jsonl`. Every scorecard still says
> **Waiting for a person**, because nobody has signed off on the answers. Earlier
> single-run answers, and the 2026-09-27 runs on dataset `library-v1`, are in the
> Git history.

### Test results in the Lab

Each library agent's **Test results** tab comes from
[scorecards.py](../evaluations/scorecards.py). It's offline, like `library_checks.py`:

```powershell
cd evaluations
python scorecards.py write   # regenerate workbench/agent_scorecards.json
python scorecards.py check   # fail if the Lab's copy is out of date
```

It screens the recorded answer for each case with `score`, takes the response
times and token counts from
[the run's metrics](../evaluations/evidence/library-acceptance-2026-09-29-metrics.jsonl), and
adds the other four runs of each case from
[the repeat file](../evaluations/evidence/library-repeat-2026-09-29.jsonl). A case passes only
when all five of its runs pass, and the tab shows how many of an agent's runs
passed. The answer a person reads is run 1. The repeats are screened but not
read. An agent's median time and average cost cover all 25 of its runs. It prices
the tokens with
[saved Azure list prices](../evaluations/evidence/model-prices-2026-09.json): USD, Global
Standard, North Central US, retrieved 2026-09-28 from the Azure Retail Prices
API. Costs cover model tokens only, not hosting, storage or monitoring. The
times come from a direct run on a local machine, and the tab says so. Every
scorecard shows **Waiting for a person** until someone reads the answers.
`scorecards.py` also fails if an agent's instructions changed after its answers
were recorded. [library_runs.py](#record-an-agents-test-answers-again) records
them again. It also fails if any case has no recorded answer, so a new case
can't drop out of the results unnoticed. `test_scorecards.py` fails if the
Lab's copy drifts from the
evidence, or if an agent's **Reviewed** label doesn't match it: an agent is
marked **Reviewed** exactly when a person has signed off its answers and every
run passed.

After a person has read an agent's answers, record it:

```powershell
python scorecards.py signoff --reviewer "Their Name" --all          # or name agents instead of --all
```

That writes `evidence/signoffs.json` with the reviewer,
the date and a fingerprint of the answers they read, then regenerates the Lab's
copy. The tab then shows **Signed off** with their name and the date. If an
answer changes later, `scorecards.py` fails until someone reads that agent's
answers again. Don't run `signoff` on someone else's behalf.

The library's **Reviewed** label comes from `workbench/agent_templates/`, not
from the sign-off file, so every agent shows **Not yet reviewed** until you also set
`"readiness": "reviewed"` in its file's `metadata` in
`workbench/agent_templates/agents/` and regenerate
[the frontend's catalog fixture](../workbench/frontend/README.md#library-performance-and-log-coverage).
`test_scorecards.py` names any agent whose label and sign-off disagree.

Each scorecard case also carries the request it sent (`input`). The **Take it to
Foundry** tab turns those into a JSONL file for a Foundry evaluation: one row per
case, with the request in `query` and the case ID, category and rubric as extra
columns. The rows follow Foundry's [evaluation dataset
schema](https://learn.microsoft.com/azure/foundry/observability/how-to/evaluation-dataset-schema)
for a run where Foundry generates the answers. They haven't been imported into a
Foundry project yet.

### Record an agent's test answers again

When you change an agent's instructions in
[agent_templates](../workbench/agent_templates), its recorded answers no
longer describe it, and `scorecards.py` refuses to build until they're recorded
again. [library_runs.py](../evaluations/library_runs.py) finds those agents and records them:

```powershell
cd evaluations
python library_runs.py status                                      # offline, free
python library_runs.py record --templates document-analyst         # offline, free: shows the plan
python library_runs.py record --templates document-analyst --yes   # billable: records them
```

- `status` lists each agent as **current**, **stale** (its rows came from other
  instructions), **incomplete** or **missing**, and exits 0 only when all are
  current. It needs no network.
- `record` without `--yes` prints the plan and sends nothing: the runs, the
  model for each agent, the tokens, cost and time its last recording took, and
  the pacing.
- `record --yes` sends each of an agent's cases to Foundry five times, through
  the same `library_preview.run_preview` code the Lab's Chat preview uses, so the
  answers are the ones the Lab gives. It creates no agent and stores nothing in
  Foundry.

`record --yes` calls Foundry and costs money. Going by the last recording, an
agent's 25 runs cost about 3 to 55 cents and take at least 2 to 11 minutes at
the default pacing. The plan shows the figures first. Get the owner's approval
before you add `--yes`.

**What it needs.** Install `evaluations/requirements.txt`, sign in with
`az login` or any other `DefaultAzureCredential` source that can call the
project's model deployments, and give the project's URL with `--endpoint` or
`FOUNDRY_PROJECT_ENDPOINT`
(`https://<account>.services.ai.azure.com/api/projects/<project>`). On a machine
that could sign in more than one way, set
`AZURE_TOKEN_CREDENTIALS=AzureCliCredential` so the runner uses the `az login`
identity and no other (azure-identity 1.23 or later; `requirements.txt` pins
1.25.3). Each agent
runs on the deployment for its model profile, taken from the first of these that
names one: `--model` (one deployment for every agent named), `--models` (JSON,
like `{"reasoning": "gpt-5.4"}`), the Lab's `WORKBENCH_AGENT_CREATION_MODELS`,
its `WORKBENCH_AGENT_CREATION_MODEL`, or the model of the agent's last
recording.

**Pacing and retries.** Each deployment is held to 10,000 tokens and 10 requests
a minute, the limits of a capacity-10 deployment. For one with more quota, pass
`--limits` like `{"gpt-5.4": {"tokens": 30000, "requests": 30}}`. A number you
leave out stays at its default. A 429 waits as long as Foundry asks, or 60
seconds if it doesn't say. A timeout, dropped connection or server error waits 2
seconds, then 4, 8 and so on up to 30. A request is tried up to six times before
the recording stops.

**Interrupted?** Each finished run is saved at once in
`evaluations/results/library-runs/<agent>.jsonl`, which Git ignores. Run the same
command again and it picks up where it stopped, without sending the finished
runs again. Saved runs from other instructions or another model are dropped.

**What changes.** Only when all of an agent's runs are saved does it replace that
agent's rows, and no one else's, in the three files in [evidence/](../evaluations/evidence/).
Each file is first written in full beside the original, so a failed write (a
full disk, say) changes nothing. The three are then swapped in one after
another. If a swap fails part-way, the saved runs are kept and the same command
finishes the job without calling Foundry again. Every new row
carries the instructions' fingerprint (`instructions_sha256`) and the date it was
recorded (`recorded_on`), and the Lab's test date for an agent is the latest of
those dates. Rows from two versions of an agent's instructions never mix. Agents
are saved one at a time, so a later failure never undoes an earlier agent.

It refuses to run when `CI` or `GITHUB_ACTIONS` is set, so CI never calls
Foundry. `test_library_runs.py` covers the planning, the row replacement and the
pacing with a fake Foundry and no network. Run one recording at a time: two at
once would share the same quota and could overwrite each other's rows.

**Then:**

```powershell
python scorecards.py write   # rebuild the Lab's copy of the results
```

A sign-off covers the exact answers a person read, so an agent that had one stops
building ("the answers changed after the sign-off") until a person reads the new
answers and signs off again. `library_runs.py` never records a sign-off. Until
that's done, set the agent's `readiness` in `TEMPLATE_METADATA` back to `sample`
if it says `reviewed`. The Lab shows the new results after the next deploy.

Exit codes: `status` returns 0 when every agent is current, 1 when some need
recording and 2 when it can't read the evidence or an agent has no cases.
`record` returns 0 when everything is saved, 1 when a run was cut short (what's
saved is kept), 2 when nothing was sent (no `--yes`, CI, a bad option or no
endpoint) and 130 after Ctrl+C.

## Related content

- [Synthetic review evaluations](../evaluations/README.md)
- [Create and try a baseline Microsoft Foundry agent](agent-creation.md)
- [The Lab](../workbench/README.md)
- [Lab frontend](../workbench/frontend/README.md)
- [Documentation index](README.md)

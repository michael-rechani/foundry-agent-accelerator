# Agent library scorecards

[Home](../README.md) / [Docs](README.md) / [Evaluations](../evaluations/README.md) / Library scorecards

Acceptance cases, the **Test results** tab in the Lab, and the workflows for
recording an agent's test answers again and signing them off all live here.
This page is part of the [evaluation guide](../evaluations/README.md).
Everything on it runs offline except `library_runs.py record --yes`, which calls
Foundry and costs money.

## Agent library acceptance cases

[library-cases.json](../evaluations/library-cases.json) holds 99 acceptance cases
across the 18 agents in the library. Every value in them is sample data. Each
template covers five categories; some have extra cases:

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
  the expected lookups must appear in it. Medical-bill cases also require a
  confirmed calculator receipt and check its copied amounts, line quantities,
  unit prices and whether a statement total was actually printed. The showcase
  also checks its matched claim pairs, duplicate and unmatched quantities, and
  calculated reconciliation components against the sample documents.

### Conversation cases

A case can add one to four `follow_ups`, each with an `input` (or
`use_sample_input`), `checks` and `rubric`. The recorder sends the first prompt,
then supplies each follow-up with that run's actual earlier user messages and
assistant answers, just like the Lab's text chat history. It does not substitute
an expected answer, reuse another run's history, or save a conversation in
Foundry. Tool results are local to each turn; the next turn receives the answer
text, not a replay of earlier tool calls.

The Benefits ID-only case covers four turns: start from the sample IDs, supply
the renewal documents, request an unsent household note, and challenge the
eligibility boundary. An additional case checks urgency without promising an
eligibility decision. A person still checks the coverage summary, date maths,
which proof the note requests, and the tone.

Multi-turn evidence adds `turns`, an ordered list of `{input, text, receipts}`
objects, to the answer and repeat rows. Every turn must pass its own checks;
missing or reordered turns fail. The top-level `text` and `receipts` remain the
first answer, while token counts, elapsed time and cost cover the whole
conversation. Context fingerprints include every follow-up input, and a
sign-off fingerprint covers all recorded turn content. Changing a follow-up
therefore requires new evidence, not relabeling an old single-turn answer.

The offline recording plan shows both repeated runs and conversation turns
before tool calls. The current medical and Benefits batch is **75 runs and 90
conversation turns**; tool rounds can make more model requests. Old evidence
does not validate the revised cases. Recording and retaining the fictional
answers needs approval (#362, #363); a person reviews them before sign-off.

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

The screen lives in [case_scoring.py](../workbench/case_scoring.py), and
`library_checks.py` imports it. The Lab's **Test this draft first** panel scores
a draft's answers with the same code, so a drafted case is held to the same
rules as these cases. See [Agent creation](agent-creation.md#test-a-draft-before-you-create-it).

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
> effective instructions its agent had when it ran: the shared runtime policy
> plus that agent's template instructions. It also carries the date it was
> recorded, and `scorecards.py` refuses to build when either part has changed.
> Answers from the first set, which were recorded before rows carried a
> fingerprint, were stamped with the instructions in force when that set
> started, and only for agents whose instructions haven't changed since. After
> you change the shared policy or an agent's instructions, record its 25 answers again with
> [library_runs.py](#record-an-agents-test-answers-again).
>
> **Test-context fingerprints.** Instructions aren't the only thing a result
> depends on. A second fingerprint, `context_sha256`, covers a case's input
> (the sample input when the case uses it), its fixtures and missing fixtures,
> the agent's model profile, and the demo data and code behind its tools. It
> leaves out the checks and the rubric, which are scored when the scorecard is
> built, so tightening a check never needs a new recording. If any covered
> part changes after an answer, metrics row or repeat run was recorded,
> `scorecards.py` refuses to build and `library_runs.py status` reports the agent
> as stale, so a scorecard can't pass on evidence from a different test.
>
> The 98 cases recorded before this fingerprint existed keep their rows
> unchanged. They're checked against
> [context-baseline.json](../evaluations/evidence/context-baseline.json), which
> holds the fingerprint each case had when it was baselined, with the basis for
> trusting it. A row's own `context_sha256` always wins over the baseline, so
> new recordings never need an entry. `python scorecards.py baseline --basis
> "<why these rows are trusted>"` adds entries for cases whose rows carry no
> fingerprint, refuses to overwrite one, and writes nothing when every row is
> already stamped. Don't run it to get past a stale agent. Record the agent again.
>
> **Tool receipts.** Every recorded answer must carry `receipts`, the list of
> `{"tool": name}` calls the agent made, so a case's `expected_tools` check is
> always enforced. A row without it stops the build instead of skipping the check.
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
times come from a direct run on a local machine, and the tab identifies them
as recorded test times rather than typical live-Lab latency. Every
scorecard shows **Waiting for a person** until someone reads the answers.
`scorecards.py` also fails if the shared runtime policy or an agent's template
instructions changed after its answers were recorded.
[library_runs.py](#record-an-agents-test-answers-again) records
them again. It also fails if any case has no recorded answer, so a new case
can't drop out of the results unnoticed. `test_scorecards.py` fails if the
Lab's copy drifts from the
evidence, or if an agent's **Reviewed** label doesn't match it. An agent is
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

`--all` lists every agent that has recorded answers, even when an earlier
sign-off of one of them is stale, and replaces that sign-off with the new one.
Read the changed answers first. The new sign-off certifies exactly what the
reviewer read. A normal `write` or `check` still fails on a stale sign-off.

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

When you change the shared runtime policy, an agent's instructions in
[agent_templates](../workbench/agent_templates), or its test input, fixtures,
model profile or demo tools, its recorded answers no longer describe it, and
`scorecards.py` refuses to build until they're recorded again. [library_runs.py](../evaluations/library_runs.py) finds those agents and records them:

```powershell
cd evaluations
python library_runs.py status                                      # offline, free
python library_runs.py record --templates document-analyst         # offline, free: shows the plan
python library_runs.py record --templates document-analyst --yes   # billable: records them
```

- `status` lists each agent as **current**, **stale** (its rows came from other
  instructions, or from a different test input, fixtures, model profile or tools),
  **incomplete** or **missing**, and exits 0 only when all are current. It needs
  no network, and stops with exit code 2 if `context-baseline.json` can't be read.
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
runs again. Saved runs from other instructions, another model or another test
context are dropped.

**What changes.** Only when all of an agent's runs are saved does it replace that
agent's rows, and no one else's, in the three files in [evidence/](../evaluations/evidence/).
Each file is first written in full beside the original, so a failed write (a
full disk, say) changes nothing. The three are then swapped in one after
another. If a swap fails part-way, the saved runs are kept and the same command
finishes the job without calling Foundry again. Every new row
carries the instructions' fingerprint (`instructions_sha256`), the test-context
fingerprint (`context_sha256`) and the date it was recorded (`recorded_on`), and
the Lab's test date for an agent is the latest of those dates. Rows from two
versions of an agent's instructions or test never mix, and recording replaces any
older rows that carry no context fingerprint. Agents
are saved one at a time, so a later failure never undoes an earlier agent.

It refuses to run when `CI` or `GITHUB_ACTIONS` is set, so CI never calls
Foundry. The one exception is the manually started **Record library answers**
workflow, described below. `test_library_runs.py` covers the planning, the row replacement and the
pacing with a fake Foundry and no network. Run one recording at a time: two at
once would share the same quota and could overwrite each other's rows.

**Recording from the private runner.** Foundry has no public access, so a
laptop outside the VNet gets a 403 ("Public access is disabled"). The **Record
library answers** workflow
([record-library-answers.yml](../.github/workflows/record-library-answers.yml))
runs the same command on the Lab's private `lab-runner` machines, which reach
Foundry through the peered VNet.

- Start it by hand from the Actions tab, on `main`. Give it the agent ids and the
  branch or commit whose instructions to record. It prints the plan first.
- The runner VM deallocates itself after 30 idle minutes. The workflow's
  `start-runner` job runs on a GitHub-hosted runner beside the recording job and
  checks GitHub's review history for an explicit approval of the
  `library-recording` environment. A queued job alone isn't approval. Only then
  does it start the VM, so a rejected run starts nothing and the VM doesn't sit idle while the run
  waits for you. It signs in as the Lab deploy identity, whose **Lab runner
  starter** role can read and start that one VM and nothing else. The recording
  identity has no VM permission. The job waits up to two hours for an approval.
  If it gives up, or the VM is off for any other reason, start it by hand with
  `az vm start --resource-group <runner-resource-group> --name <runner-vm-name>`
  and the recording job takes the runner when it comes online. Starting the VM
  costs compute for as long as it runs, about $0.19 an hour.
- Dispatch a fresh workflow instead of using **Re-run jobs**. GitHub's review
  history is scoped to the run, not an individual attempt, so automatic wake-up
  fails closed on a rerun rather than reusing an earlier approval.
- The `library-recording` environment holds a required reviewer, so nothing is
  sent until the owner approves. Check the `ref` in the approval prompt, because the
  runner runs the code at that ref.
- It signs in as its own identity, `gh-library-recording`, with no stored secret.
  That identity has one role, Foundry User, on the Lab's Foundry account only,
  and Azure accepts it only from that environment. Terraform creates it,
    with the environment and its required reviewer, in
    [terraform/identity](../terraform/identity/README.md).
- A full recording outlasts one GitHub sign-in token, so the job asks GitHub for a
  new one whenever Azure needs it.
- It doesn't commit anything. It uploads the new evidence files as an artifact
  (kept 14 days). Download it, copy the files into `evaluations/evidence/`, run
  `python scorecards.py write`, and open a pull request.

**Then:**

```powershell
python scorecards.py write   # rebuild the Lab's copy of the results
```

A sign-off covers the exact answers a person read, so an agent that had one stops
building ("the answers changed after the sign-off") until a person reads the new
answers and signs off again. `library_runs.py` never records a sign-off. Until
that's done, set `metadata.readiness` in
`workbench/agent_templates/agents/<id>.json` back to `sample` if it says
`reviewed`. `TEMPLATE_METADATA` is loaded from those files, not edited directly.
Regenerate the frontend catalog snapshot as described in
[Add a library agent](agent-creation.md#add-a-library-agent).
The Lab shows the new results after the next deploy.

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

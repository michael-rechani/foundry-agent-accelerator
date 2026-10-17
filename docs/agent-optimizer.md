# Improve a hosted agent with the Foundry Agent Optimizer

[Home](../README.md) / [Docs](README.md) / Agent Optimizer

The [Foundry Agent Optimizer](https://learn.microsoft.com/azure/foundry/agents/concepts/agent-optimizer-overview)
proposes better instructions and model choices for a hosted agent by
running it against a dataset and scoring each candidate. This page covers the
two review agents, `case-review-agent` and `application-review-agent`.
Everything the repository ships is offline. **The optimizer run itself is
billable and needs approval** (tracked in #275).

## What is already set up

| File (in each agent folder) | Purpose |
| --- | --- |
| `.agent_configs/baseline/` | The baseline the optimizer reads: `metadata.yaml` (model, instruction file) and a copy of `instructions.md`. |
| `eval.jsonl` | The agent's acceptance cases as optimizer tasks (`name`, `query`, `criteria`). The case rubric is the criterion. |
| `eval.yaml` | The run configuration for `azd ai agent optimize --config eval.yaml`. |

`evaluations/optimizer_dataset.py` writes all of these. `instructions.md` stays
the source of truth, and a test fails when the copies go stale:

```powershell
python evaluations/optimizer_dataset.py          # rewrite
python evaluations/optimizer_dataset.py --check  # fail when stale
```

| Hosted agent | Library cases used | Cases |
| --- | --- | --- |
| `case-review-agent` | `casework-assistant` | 5 |
| `application-review-agent` | `criteria-checker` | 5 |

Those cases and rubrics were written for the library templates, not for these
agents. Read the scores as a comparison between candidates, not as a pass mark.
Defaults are the baseline model `gpt-4.1`, the scoring model `gpt-5.4-mini`, the
candidate-writing model `gpt-5.4` and two candidates. Change them with
`--model`, `--eval-model`, `--optimization-model` and `--max-candidates`.

## Behavior without a run

Each `main.py` calls `hosted_runtime.load_optimization_config()` and passes the
result to `apply_optimization()`. Only a candidate that the optimizer injects
(`OPTIMIZATION_CONFIG` or `OPTIMIZATION_CANDIDATE_ID`) changes the agent's
instructions and model. The baseline folder, a missing package, or no
configuration leaves the agent exactly as deployed, including any
`AGENT_INSTRUCTIONS` override. The baseline and `eval.*` files are not shipped
in the deployed package.

## Before you run it

Ask for approval first. A run:

- is billable and shows no estimate beforehand: the scoring and candidate-writing
  models plus the agent's own calls on every task for every candidate;
- calls the **deployed** hosted agent for every task, so deploy it first
  (see [hosted-agent deployment](../hosted-agents/README.md#deployment-walkthrough));
- needs the scoring model and a candidate-writing model deployed in the same
  Foundry project. The candidate-writing model must be on the optimizer's
  [supported list](https://learn.microsoft.com/azure/foundry/agents/concepts/agent-optimizer-overview#models);
- is not available in every region (it isn't in Norway East) and needs the
  Responses protocol;
- needs `azd` with the `azure.ai.agents` extension.

These two agents have no tools, so nothing runs against real systems. If you add
tools later, give the optimizer fixtures or mocks, because it executes tool calls
on every task.

## Run, review, ship

1. Deploy the agent and check that it answers.
2. From the agent folder, run the optimizer. Without an `azd` project, paths in
   `eval.yaml` resolve from the current folder, and the command asks for the
   baseline instruction. Choose `.agent_configs/baseline/instructions.md`:

   ```powershell
   azd ai agent optimize --agent case-review-agent --config eval.yaml
   azd ai agent optimize status <operation-id> --watch
   ```

3. Review the results table. A gain under about 0.03 is noise; ignore it. If every
   candidate scores below the baseline, change nothing.
4. `azd ai agent optimize apply` needs an `azd` project that this repository
   doesn't have. Read the winning candidate in the Foundry portal and copy its
   instructions into the agent's `instructions.md` in a pull request. A reviewer
   reads the diff like any other prompt change. Then run
   `python evaluations/optimizer_dataset.py` to refresh the baseline copy.
5. Run the offline checks before deploying: the hosted-agent tests, and
   `python evaluations/library_checks.py score` on answers the new instructions
   give for the cases (`library_checks.py inputs` prints each case input).
6. Deploy with the sample's own `deploy.py`, as in the walkthrough.
7. Record the measured token usage and scores in #275.

A candidate that changes the model also changes the cost. Compare cost against
[Lab configuration and cost](lab-configuration-and-cost.md) before adopting it.

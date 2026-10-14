# Synthetic review evaluations

[Home](../README.md) / Evaluations

Checks the quality of the review samples without changing runtime dependencies,
publishing agent versions, changing endpoint routes, or building a Lab
dashboard. Offline validation checks dataset structure. Approved live evaluation
checks an already deployed staging stack and records native Microsoft Foundry
results.

> [!IMPORTANT]
> Running [the CLI](run.py) without `--run` is offline and needs only Python.
> Live mode requires `--run --approve-billable-run --authorize-content-capture`
> and approval for billable calls and synthetic content retention. It
> creates and retains a custom evaluator, an evaluation, and a run in your
> Foundry project. No live evaluation has been run as part of these changes, so
> there are no captured quality or cost results here. Project tracing is
> connected separately through the
> [private monitoring root](../terraform/monitoring/README.md) and has been
> verified with metadata-only synthetic requests, but no evaluation run has been
> correlated with its traces.

In this guide, SDK means the pinned Azure AI Projects and OpenAI client
libraries.

## Offline and approved live modes

| Mode | What it does | What it does not do |
| --- | --- | --- |
| Offline, default | Validates the dataset schema, profile coverage, source identifiers, and local tests. | It doesn't invoke Azure, acquire credentials, mutate cloud resources, grade quality, or prove model performance. |
| Approved live, with `--run` | Invokes routed staging agents, creates a native Foundry evaluator/evaluation/run, and gates every selected case through the rubric. | It doesn't publish agents, promote routes, run a production canary, estimate cost, or authorize a production release. |

## Offline validation

From the repository root:

```powershell
python evaluations\run.py
python evaluations\run.py --sample application-review-agent
python evaluations\run.py --sample case-review-agent
python evaluations\run.py --sample review-coordinator-agent
python evaluations\run.py --profile requirements-proposal-experimental
python evaluations\run.py --cases evaluations\review-cases.json
python -m unittest discover -s evaluations -p 'test_*.py' -v
```

Run the three sample selectors in that order when refining the review agents, so
each specialist's contract is proven before you assess the coordinator handoff.
These commands validate acceptance-case structure only. They don't run a
model. You can also check packaging and coordinator transport with the
existing standard-library tests, without installing tools:

```powershell
python -m unittest discover -s hosted-agents -p 'test_bundle.py' -v
python -m unittest discover -s hosted-agents\review-coordinator-agent -p 'test_*.py' -v
```

Without the evaluation dependencies, the real SDK contract tests are skipped.
With the pinned dependencies, [test_sdk_contract.py](test_sdk_contract.py)
uses real SDK serialization with **in-memory transports and fake credentials**,
not Azure. These offline tests need no deployment, credential acquisition,
endpoint invocation, cloud mutation, or live grading. A green offline run
isn't evidence of model performance or a production-ready demo.

## Reference pages

- [Evaluation test cases and acceptance](../docs/evaluation-test-cases.md): the profiles, the cases in each, and what every case expects.
- [Run an approved live evaluation](../docs/evaluation-live-run.md): prepare staging, run explicitly, and understand costs, retention, and interrupted runs.
- [Evaluation SDK contract, candidate comparison, and tracing](../docs/evaluation-sdk-comparison-tracing.md): what the offline SDK tests establish, how to compare candidates, and tracing.
- [Agent library scorecards](../docs/library-scorecards.md): the library's acceptance cases, the Lab's **Test results** tab, re-recording answers, and sign-off.

## Related content

- [Hosted agents](../hosted-agents/README.md)
- [Demo handoff](../docs/demo-handoff.md)
- [Agent monitoring](../terraform/monitoring/README.md)
- [Agent evaluation guidance](https://learn.microsoft.com/azure/foundry/observability/how-to/evaluate-agent)
- [Rubric evaluators](https://learn.microsoft.com/azure/foundry/concepts/evaluation-evaluators/rubric-evaluators)
- [Cloud evaluation results and cancellation](https://learn.microsoft.com/azure/foundry/observability/how-to/cloud-evaluation-results)
- [Evaluation regions, limits, and private networking](https://learn.microsoft.com/azure/foundry/concepts/evaluation-regions-limits-virtual-network)
- [Agent tracing setup](https://learn.microsoft.com/azure/foundry/observability/how-to/trace-agent-setup)

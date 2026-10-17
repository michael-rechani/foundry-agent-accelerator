"""Build the Foundry Agent Optimizer inputs for the hosted review agents, offline.

For each hosted agent this writes, beside its main.py:

* eval.jsonl: the matching library acceptance cases as optimizer tasks (name, query, criteria);
* eval.yaml: the run configuration for `azd ai agent optimize --config eval.yaml`;
* .agent_configs/baseline/: the baseline the optimizer reads (metadata.yaml and a copy of instructions.md).

It never calls Azure or a model. The optimizer run itself is billable, so see
docs/agent-optimizer.md before running it. Use --check to fail when the committed files are stale.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from library_checks import case_input, load_cases

ROOT = Path(__file__).resolve().parents[1]
HOSTED = ROOT / "hosted-agents"

# Library cases are written for the library templates, so each hosted agent borrows the template
# closest to its job. Their rubrics were written for those templates' prompts, so read scores as a
# comparison between candidates, not as an absolute pass mark.
AGENT_TEMPLATES = {
    "case-review-agent": ("casework-assistant",),
    "application-review-agent": ("criteria-checker",),
}
DEFAULT_MODEL = "gpt-4.1"
DEFAULT_EVAL_MODEL = "gpt-5.4-mini"
DEFAULT_OPTIMIZATION_MODEL = "gpt-5.4"
DEFAULT_MAX_CANDIDATES = 2


def tasks(template_ids, cases=None):
    """One optimizer task per library case; the rubric becomes the task-level criterion."""
    cases = load_cases()["cases"] if cases is None else cases
    rows = [
        {
            "name": case["id"],
            "query": case_input(case),
            "criteria": [{"name": "rubric", "instruction": case["rubric"]}],
        }
        for case in cases
        if case["template_id"] in template_ids
    ]
    if not rows:
        raise ValueError(f"No library cases for {sorted(template_ids)}")
    return rows


def eval_yaml(agent, *, model, eval_model, optimization_model, max_candidates):
    """Standalone run: no agent.config, because `optimize apply` needs an azd project this repo doesn't have."""
    return "\n".join([
        f"name: {agent}-instructions",
        "agent:",
        f"  name: {agent}",
        "  kind: hosted",
        f"  model: {model}",
        "dataset:",
        "  local_uri: ./eval.jsonl",
        "evaluators:",
        "  - builtin.task_adherence",
        "options:",
        f"  eval_model: {eval_model}",
        f"  optimization_model: {optimization_model}",
        f"  max_candidates: {max_candidates}",
        "",
    ])


def metadata_yaml(model):
    return f"model: {model}\ninstruction_file: instructions.md\n"


def render(agent, *, model=DEFAULT_MODEL, eval_model=DEFAULT_EVAL_MODEL,
           optimization_model=DEFAULT_OPTIMIZATION_MODEL, max_candidates=DEFAULT_MAX_CANDIDATES, cases=None):
    """Return {path relative to the agent folder: file text}."""
    folder = HOSTED / agent
    baseline = Path(".agent_configs") / "baseline"
    jsonl = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in tasks(AGENT_TEMPLATES[agent], cases))
    return {
        "eval.jsonl": jsonl,
        "eval.yaml": eval_yaml(agent, model=model, eval_model=eval_model,
                               optimization_model=optimization_model, max_candidates=max_candidates),
        str(baseline / "metadata.yaml"): metadata_yaml(model),
        str(baseline / "instructions.md"): (folder / "instructions.md").read_text(encoding="utf-8"),
    }


def stale(agent, files):
    folder = HOSTED / agent
    return [name for name, text in files.items()
            if not (folder / name).is_file() or (folder / name).read_text(encoding="utf-8") != text]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--agent", choices=sorted(AGENT_TEMPLATES), action="append",
                        help="Hosted agent to build for; repeat for several. Default: all.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Baseline model deployment of the hosted agent.")
    parser.add_argument("--eval-model", default=DEFAULT_EVAL_MODEL, help="Deployed chat model that scores answers.")
    parser.add_argument("--optimization-model", default=DEFAULT_OPTIMIZATION_MODEL,
                        help="Deployed model that writes candidates; must be on the optimizer's supported list.")
    parser.add_argument("--max-candidates", type=int, default=DEFAULT_MAX_CANDIDATES)
    parser.add_argument("--check", action="store_true", help="Write nothing; exit 1 when a file is stale.")
    args = parser.parse_args(argv)
    if args.max_candidates < 1:
        parser.error("--max-candidates must be at least 1")

    failed = False
    for agent in args.agent or sorted(AGENT_TEMPLATES):
        files = render(agent, model=args.model, eval_model=args.eval_model,
                       optimization_model=args.optimization_model, max_candidates=args.max_candidates)
        if args.check:
            for name in stale(agent, files):
                failed = True
                print(f"{agent}/{name} is out of date; run optimizer_dataset.py", file=sys.stderr)
            continue
        for name, text in files.items():
            path = HOSTED / agent / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="\n")
            print(f"wrote {path.relative_to(ROOT)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

"""Per-model-deployment admission for chat turns, so the Lab says "busy" before the model does.

A model deployment publishes its own limits, and tokens a minute usually bind before requests a
minute. The Lab can't see the model's counters, so it keeps its own: a sliding window per
deployment of the turns it admitted and their estimated tokens. A turn that would push a window
over the configured limit is refused before any model call. Counters live in memory, like every
other Lab gate, so they need the single replica the Lab already runs.
"""

import math
import time
from collections import deque

from library_rules import DEPLOYMENT_NAME, is_int, is_number

LIMIT_KEYS = ("requests_per_minute", "tokens_per_minute")
MAX_LIMIT = 10_000_000


def validate_model_limits(limits):
    """Return the limits when they map valid deployment names to whole-number requests_per_minute and tokens_per_minute; otherwise raise ValueError."""
    if not isinstance(limits, dict):
        raise ValueError("WORKBENCH_MODEL_LIMITS must be a JSON object that maps deployment names to limits")
    for name, limit in limits.items():
        if not isinstance(name, str) or not DEPLOYMENT_NAME.fullmatch(name):
            raise ValueError(f"WORKBENCH_MODEL_LIMITS has an invalid deployment name: {name!r}")
        if not isinstance(limit, dict) or set(limit) != set(LIMIT_KEYS):
            raise ValueError(f"WORKBENCH_MODEL_LIMITS for {name} must have exactly {' and '.join(LIMIT_KEYS)}")
        for key in LIMIT_KEYS:
            if not is_int(limit[key]) or not 1 <= limit[key] <= MAX_LIMIT:
                raise ValueError(f"WORKBENCH_MODEL_LIMITS for {name} needs {key} as a whole number from 1 to {MAX_LIMIT}")
    return limits


def measured_answer_tokens(scorecards):
    """Per library template, the most tokens (input plus output) one recorded answer used.

    The recorded runs in agent_scorecards.json are the library's own measurement, so the estimate
    follows them instead of a second table. Cases without token counts are skipped.
    """
    estimates = {}
    for card in scorecards["scorecards"]:
        totals = [case["input_tokens"] + case["output_tokens"] for case in card["cases"]
                  if is_number(case.get("input_tokens")) and is_number(case.get("output_tokens"))]
        if totals and max(totals) > 0:
            estimates[card["template_id"]] = math.ceil(max(totals))
    return estimates


class ModelBudgets:
    """Requests and estimated tokens admitted per model deployment in a sliding window."""

    def __init__(self, limits, answer_tokens, window_seconds=60.0):
        self.limits = validate_model_limits(limits)
        self.answer_tokens, self.window_seconds = dict(answer_tokens), window_seconds
        # A template with no recorded answer is assumed as large as the largest recorded one.
        self.default_tokens = max(self.answer_tokens.values(), default=0)
        self.recent = {deployment: deque() for deployment in self.limits}

    def estimate(self, template_id):
        return self.answer_tokens.get(template_id, self.default_tokens)

    def try_admit(self, deployment, template_id, now=None):
        """Count this turn and return 0, or return the seconds to wait (counting nothing) when it would exceed the deployment's limits.

        A deployment without configured limits is never refused here; the Lab's global caps still apply.
        """
        limit = self.limits.get(deployment)
        if limit is None:
            return 0
        now = time.monotonic() if now is None else now
        recent = self.recent[deployment]
        while recent and recent[0][0] <= now - self.window_seconds:
            recent.popleft()
        tokens = self.estimate(template_id)
        requests, used = len(recent), sum(spent for _, spent in recent)
        waited = 0
        # A turn larger than the whole token limit still runs alone, so it is never refused forever.
        while requests >= limit["requests_per_minute"] or (used and used + tokens > limit["tokens_per_minute"]):
            requests, used, waited = requests - 1, used - recent[waited][1], waited + 1
        if waited == 0:
            recent.append((now, tokens))
            return 0
        return max(1, math.ceil(recent[waited - 1][0] + self.window_seconds - now))

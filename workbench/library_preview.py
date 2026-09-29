"""Library previews: chat with a catalog template without publishing a hosted agent.

A preview applies the same fixed policy, template instructions and simulated tools a created agent
uses, on the model deployment that creation would pick. Nothing is published or stored in Foundry.
"""
import inspect
import json
import re

from agent_runtime.demo_tools import TEMPLATE_IDS, create_demo_tools
from agent_runtime.main import DEMO_POLICY
from agent_templates import TEMPLATES, is_listed

PREVIEW_ID = re.compile(r"library-([a-z0-9]+(?:-[a-z0-9]+)*)\Z")
# Receipt binding for simulated lookups; it names no Foundry resource.
PREVIEW_AGENT = "lab-library-preview"
MAX_TOOL_ROUNDS = 4
MAX_CALLS_PER_ROUND = 8
USAGE_FIELDS = ("input_tokens", "output_tokens", "total_tokens", "cached_tokens", "reasoning_tokens")


def usage_record(response):
    """Return one Responses API result's reported token counts; a count the service didn't report is None."""
    reported = getattr(response, "usage", None)
    if hasattr(reported, "model_dump"):
        reported = reported.model_dump()
    if not isinstance(reported, dict):
        reported = {}
    counts = {key: reported.get(key) for key in ("input_tokens", "output_tokens", "total_tokens")}
    counts["cached_tokens"] = (reported.get("input_tokens_details") or {}).get("cached_tokens")
    counts["reasoning_tokens"] = (reported.get("output_tokens_details") or {}).get("reasoning_tokens")
    return {key: value if type(value) is int and value >= 0 else None for key, value in counts.items()}


def summarize_usage(records):
    """Sum per-call token counts. A count missing from any call is None, so partial totals never look complete."""
    if not records:
        return None
    total = {key: sum(record[key] for record in records) if all(record[key] is not None for record in records) else None
             for key in USAGE_FIELDS}
    return total if any(value is not None for value in total.values()) else None


def preview_agent(identifier):
    """Return the server-side binding for a library preview ID, or None."""
    match = PREVIEW_ID.fullmatch(identifier) if isinstance(identifier, str) else None
    template_id = match.group(1) if match else None
    if not is_listed(template_id) or template_id not in TEMPLATE_IDS:
        return None
    template = TEMPLATES[template_id]
    return {
        "id": identifier, "label": template["label"], "agent": PREVIEW_AGENT, "template_id": template_id,
        "model_profile": template["model_profile"], "preview": True,
        "tools": {tool["name"]: PREVIEW_AGENT for tool in template["tools"]},
    }


def tool_specs(functions):
    specs = []
    for function in functions:
        names = list(inspect.signature(function).parameters)
        specs.append({
            "type": "function", "name": function.__name__, "description": inspect.getdoc(function) or "",
            "parameters": {"type": "object", "properties": {name: {"type": "string"} for name in names},
                           "required": names, "additionalProperties": False},
            "strict": True,
        })
    return specs


def run_tool(functions, call):
    """Run one simulated lookup. Bad calls return a failed receipt instead of raising."""
    function = functions.get(call.get("name"))
    try:
        arguments = json.loads(call.get("arguments") or "{}")
    except (TypeError, ValueError):
        arguments = None
    if (function is None or not isinstance(arguments, dict)
            or set(arguments) != set(inspect.signature(function).parameters)
            or any(not isinstance(value, str) for value in arguments.values())):
        return json.dumps({"status": "failed", "error": "Invalid sample lookup call"})
    try:
        return function(**arguments)
    except ValueError as problem:
        return json.dumps({"status": "failed", "error": str(problem)})


async def run_preview(client, *, template_id, model, prompt, reasoning=False, usage=None):
    """Return (status, text, output items) after a bounded simulated-tool loop.

    Output items include each function_call_output so the caller can verify receipts the same way it
    does for hosted agents. With store=False, reasoning models need their encrypted reasoning passed back.
    """
    functions = {function.__name__: function for function in create_demo_tools(template_id, PREVIEW_AGENT)}
    options = {"model": model, "instructions": DEMO_POLICY + TEMPLATES[template_id]["instructions"],
               "store": False, "stream": False}
    if functions:
        options["tools"] = tool_specs(functions.values())
        if reasoning:
            options["include"] = ["reasoning.encrypted_content"]
    items = [{"role": "user", "content": prompt}] if isinstance(prompt, str) else [dict(message) for message in prompt]
    transcript = []
    for _ in range(MAX_TOOL_ROUNDS + 1):
        response = await client.responses.create(input=items, **options)
        if usage is not None:
            usage.append(usage_record(response))
        output = response.model_dump(exclude_none=True).get("output", [])
        transcript.extend(output)
        calls = [item for item in output if item.get("type") == "function_call"]
        if response.status != "completed" or not calls:
            return response.status, response.output_text, transcript
        if len(calls) > MAX_CALLS_PER_ROUND:
            break
        items.extend(output)
        for call in calls:
            result = {"type": "function_call_output", "call_id": call.get("call_id"), "output": run_tool(functions, call)}
            items.append(result)
            transcript.append(result)
    return "incomplete", "", transcript

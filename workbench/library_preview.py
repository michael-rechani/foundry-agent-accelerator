"""Library previews: chat with a catalog template without publishing a hosted agent.

A preview applies the same fixed policy, template instructions and simulated tools a created agent
uses, on the model deployment that creation would pick. Nothing is published or stored in Foundry.
"""
import inspect
import json
import re

from agent_runtime.demo_tools import TEMPLATE_IDS, create_demo_tools
from agent_runtime.main import DEMO_POLICY
from agent_templates import TEMPLATES, is_available

PREVIEW_ID = re.compile(r"library-([a-z0-9]+(?:-[a-z0-9]+)*)\Z")
# Receipt binding for simulated lookups; it names no Foundry resource.
PREVIEW_AGENT = "lab-library-preview"
# The Agent designer is a plain conversation, not a library template: it has no tools, no answer layout and
# no entry in the catalog, scorecards or acceptance cases. It shares the preview path and its budget.
DESIGNER_TEMPLATE = "agent-designer"
DESIGNER_ID = f"library-{DESIGNER_TEMPLATE}"


def _designer_catalog():
    """The finished library agents by id, so a spec can name its closest match without inventing one."""
    return "; ".join(f"{template['id']} ({template['label']})" for identifier, template in TEMPLATES.items()
                     if is_available(identifier, False))


DESIGNER_INSTRUCTIONS = (
    "You are the Agent designer in the Foundry Agent Lab, a place to try and build AI agents on sample data. "
    "Talk like a helpful colleague: short, plain replies, one or two questions at a time, no headings or "
    "templates unless asked. Answer greetings and small talk briefly, then offer to help. "
    "Help the person work out an agent: what job it does, who uses it, what it receives, what it returns, "
    "which lookups or tools it needs, and where a person must check or decide. Summarize the idea back in a few "
    "lines when it is clear enough. "
    "Tell them how to move on when it helps: the agent picker at the top lists pre-built agents they can try, "
    "and the Create page turns an idea into an agent. "
    "If they ask about moving an agent to another Foundry project, here is what the Lab does. Under All agents, "
    "opening an agent and choosing Take it to Foundry offers a downloadable agent definition (instructions and "
    "settings for a Foundry prompt agent, without a model deployment), its test requests as a file, and for agents "
    "created in the Lab, a hosted-agent package. The person deploys it into a project they control with their own "
    "credentials; the Lab does not do cross-project deployment. The Lab has no import. Do not describe buttons or "
    "menus beyond these, and say so if you are unsure. "
    "When the idea is clear enough to build, after your short plain summary add one agent spec as a fenced block "
    "whose language is agent-spec, containing only JSON with these keys: name (short), summary (one sentence), "
    "instructions (the full instructions a Foundry prompt agent would run on, written to the agent in second "
    "person, covering its job, how it answers, what it must not do, and when to hand off to a person), inputs, "
    "outputs, tools_needed (a list of plain-language lookup names, empty if none), human_decision (who decides "
    "what), and closest_template (one id from the list below, or null when none fits). Add the block only when you "
    "have enough to fill every key honestly, never for greetings or early questions, and write a fresh complete "
    "block if the idea changes. The Lab shows the block as a card the person can download; you only write it. "
    "Pick closest_template only when the job really matches, and otherwise use null. Pre-built agents by id: "
    f"{_designer_catalog()}. "
    "You are a conversation only. You cannot create, publish, run or change any agent, look anything up, or "
    "open files, and you must not say you did. Never ask for personal or confidential data; use made-up "
    "examples. Do not give legal, medical, financial or eligibility advice."
)
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


def preview_agent(identifier, include_unfinished=True):
    """Return the server-side binding for a library preview ID, or None."""
    match = PREVIEW_ID.fullmatch(identifier) if isinstance(identifier, str) else None
    template_id = match.group(1) if match else None
    if identifier == DESIGNER_ID:
        return {"id": DESIGNER_ID, "label": "Agent designer", "agent": PREVIEW_AGENT, "template_id": DESIGNER_TEMPLATE,
                "model_profile": "extraction", "preview": True, "tools": {}}
    if not is_available(template_id, include_unfinished) or template_id not in TEMPLATE_IDS:
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
    designer = template_id == DESIGNER_TEMPLATE
    functions = {} if designer else {
        function.__name__: function for function in create_demo_tools(template_id, PREVIEW_AGENT)}
    instructions = DESIGNER_INSTRUCTIONS if designer else DEMO_POLICY + TEMPLATES[template_id]["instructions"]
    options = {"model": model, "instructions": instructions, "store": False, "stream": False}
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

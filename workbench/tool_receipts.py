"""Verify that tool calls have a matching successful, attributed result."""

import json


def execution_receipts(output, bindings):
    calls = [item for item in output if item.get("type") == "function_call"]
    receipts = []
    for call in calls:
        call_id = call.get("call_id")
        matching = [item for item in output if item.get("type") == "function_call_output" and item.get("call_id") == call_id]
        unique = bool(call_id) and sum(item.get("call_id") == call_id for item in calls) == 1
        receipt = {"tool": call.get("name", "unknown"), "call_id": call_id, "verified": False, "agent": None, "output": None}
        if unique and len(matching) == 1:
            try:
                result = json.loads(matching[0].get("output", ""))
            except (TypeError, ValueError):
                result = None
            if (isinstance(result, dict) and result.get("status") == "succeeded"
                    and call.get("name") in bindings and result.get("agent") == bindings[call["name"]]
                    and isinstance(result.get("output"), str) and result["output"].strip()):
                receipt.update(verified=True, agent=result["agent"], output=result["output"])
        receipts.append(receipt)
    return receipts

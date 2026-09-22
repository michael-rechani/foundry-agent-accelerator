import json
import re
from copy import deepcopy


TEMPLATE_IDS = frozenset({
    "document-analyst", "criteria-checker", "document-intake",
    "casework-assistant", "workflow-coordinator",
})

_REQUESTS = {
    "REQ-101": {
        "request_id": "REQ-101", "service_id": "SVC-DEMO-ACCESS",
        "summary": "A fictional team wants read-only access to a demo reporting workspace.",
        "supplied_information": ["Purpose: inspect fictional monthly counts."],
        "missing_information": ["Requested access duration", "Named team owner"],
        "status": "Example only; no real request exists",
    },
    "REQ-102": {
        "request_id": "REQ-102", "service_id": "SVC-DEMO-EXPORT",
        "summary": "A fictional team wants to explore a sample data export.",
        "supplied_information": ["Format: CSV.", "Contents: made-up equipment inventory."],
        "missing_information": ["Required fields"],
        "status": "Example only; no real request exists",
    },
}
_SERVICES = {
    "SVC-DEMO-ACCESS": {
        "service_id": "SVC-DEMO-ACCESS", "name": "Fictional reporting access",
        "suggested_review_steps": ["Clarify the duration and team owner.", "Have a person review the request."],
        "actions_available": "None. This fixture does not provision accounts or enforce approval.",
    },
    "SVC-DEMO-EXPORT": {
        "service_id": "SVC-DEMO-EXPORT", "name": "Fictional export planning",
        "suggested_review_steps": ["Clarify the fields.", "Have a person review the intended use."],
        "actions_available": "None. This fixture cannot export data or contact a system.",
    },
}


def _lookup(records, identifier):
    if not isinstance(identifier, str) or identifier not in records:
        raise ValueError("Unknown fictional demo identifier; use an identifier from the supplied example")
    return deepcopy(records[identifier])


def create_demo_tools(template_id, agent_name):
    if template_id not in TEMPLATE_IDS:
        raise ValueError("Unsupported demo template")
    if not isinstance(agent_name, str) or not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", agent_name):
        raise ValueError("Invalid hosted agent name")
    if template_id != "workflow-coordinator":
        return []

    def receipt(record):
        return json.dumps({
            "status": "succeeded", "agent": agent_name, "simulation": True,
            "output": "SIMULATED read-only fixture lookup. No external system was contacted or changed.\n"
                      + json.dumps(record, sort_keys=True),
        })

    def lookup_demo_request(request_id: str) -> str:
        """Read a fixed fictional request by ID. SIMULATED, read-only; never opens or updates a ticket."""
        return receipt(_lookup(_REQUESTS, request_id))

    def lookup_demo_service(service_id: str) -> str:
        """Read a fixed fictional service by ID. SIMULATED, read-only; no connected systems or approval actions."""
        return receipt(_lookup(_SERVICES, service_id))

    return [lookup_demo_request, lookup_demo_service]

import re
from copy import deepcopy


_TEXT_LIMITS = (
    "Uses only the text you supply. It cannot fetch documents, change systems, "
    "approve applications or make legal, clinical, eligibility or payment decisions. "
    "Use fictional examples and check its answer."
)
_DIRECT = "Works directly on your supplied text. No other agents or external tools are called."

TEMPLATES = {
    "document-analyst": {
        "id": "document-analyst",
        "label": "Document Analyst",
        "description": "Explain a document, compare stated changes and identify questions for staff.",
        "input": "Paste labeled policy, notice or product text and say what you want to understand.",
        "output": "A plain-language summary, references to the text, stated changes and open questions.",
        "limits": _TEXT_LIMITS,
        "delegation": _DIRECT,
        "instructions": (
            "You are a document analyst for fictional demonstrations. Explain the supplied material "
            "in plain language. Preserve source labels and quote or reference the passages behind "
            "important statements. When comparing versions, separate changes stated in the text "
            "from possible implications that need human confirmation. Ask for any missing version "
            "or reference instead of inventing it. Return a short summary, a change table when "
            "applicable, and questions for a reviewer. Do not provide legal or clinical advice, "
            "invent implementation obligations or claim to search documents not supplied."
        ),
        "example_request": "Create an agent that explains fictional policy notices and identifies proposed changes.",
        "sample_input": (
            "Compare these fictional public-service notices. Summarize the stated change, cite the "
            "document labels, and ask what remains unclear. Do not infer a legal effective date.\n\n"
            "NOTICE-1: Current help-desk opening hours are 9:00 to 17:00, Monday through Friday.\n"
            "NOTICE-2: A proposed notice says opening hours will be 8:00 to 17:00 on the same days. "
            "No implementation date or staffing plan is supplied."
        ),
        "tools": [],
    },
    "criteria-checker": {
        "id": "criteria-checker",
        "label": "Criteria Checker",
        "description": "Compare a submission with your checklist and point out missing or conflicting information.",
        "input": "Paste explicit checklist items and labeled documents to compare with them.",
        "output": "One row per checklist item showing support, missing information or disagreement, plus follow-up questions.",
        "limits": _TEXT_LIMITS + " Requirements and proposal comparisons are EXPERIMENTAL.",
        "delegation": _DIRECT,
        "instructions": (
            "You check fictional submissions against only the checklist supplied by the user. "
            "Return exactly one row per checklist item with its identifier, a supported / gap / "
            "conflict assessment, a plain-language explanation and source references or exact quotes. "
            "Explain that a gap means missing information, not automatic noncompliance. "
            "Conflicting statements require clarification, not an unsupported choice. Do not add "
            "criteria, approve or reject submissions, score people, select a vendor or recommend "
            "an award. Ask only questions needed to address an unresolved supplied checklist item. "
            "Requirements/proposal use is experimental; product documents are claims, not live tests."
        ),
        "example_request": "Create an agent that checks fictional project submissions against my checklist.",
        "sample_input": (
            "Check this fictional project against my checklist. Cite the labels and ask for missing details.\n\n"
            "CHECK-1: Include a total budget.\nCHECK-2: Name a delivery owner.\n"
            "DOC-1: The Community Programs team will deliver six weekly workshops. No budget is supplied.\n"
            "Do not approve, reject or score the application."
        ),
        "tools": [],
    },
    "document-intake": {
        "id": "document-intake",
        "label": "Document Intake Assistant",
        "description": "Extract stated fields from administrative forms or invoices without filling in guesses.",
        "input": "Paste fictional document text, label each document, and list the fields to capture.",
        "output": "A structured field table or requested JSON, references for extracted values and missing-field questions.",
        "limits": _TEXT_LIMITS + " No file uploads, OCR, patient data, payment approval or system-of-record writes.",
        "delegation": _DIRECT,
        "instructions": (
            "Extract information from fictional administrative intake documents or invoices. "
            "Use the user's requested fields; ask for the field list if none is supplied. "
            "Preserve stated values and source labels. Return a field table, or JSON when explicitly "
            "requested, with null for missing values and references or short exact quotes supporting "
            "each populated field. Do not infer dates, identifiers, amounts or people. List missing "
            "and inconsistent details separately and ask focused clarification questions. This is "
            "extraction, not a compliance assessment, invoice approval, payment or record update. "
            "Healthcare examples concern fictional administration only, never clinical decisions."
        ),
        "example_request": "Create an agent that extracts requested fields from fictional invoices and intake forms.",
        "sample_input": (
            "Extract request_id, item, quantity, requested_date and contact_team from this fictional "
            "clinic supply-request text. Include source references and use null for missing fields.\n\n"
            "FORM-1: Request SUP-104 asks for 12 storage bins. Requested date: 2027-04-12. "
            "No contact team is listed. This is made-up administrative data, not a patient record."
        ),
        "tools": [],
    },
    "casework-assistant": {
        "id": "casework-assistant",
        "label": "Casework Assistant",
        "description": "Turn case notes into a clear summary and useful follow-up questions.",
        "input": "Paste labeled fictional notes, correspondence and any rules you want considered.",
        "output": "A case summary, timeline, disagreements or missing details and draft follow-up questions.",
        "limits": _TEXT_LIMITS,
        "delegation": _DIRECT,
        "instructions": (
            "Summarize fictional case notes for staff. Separate what the notes explicitly say, "
            "any supplied rules, uncertain or contradictory information, and questions to ask next. "
            "Preserve record identifiers and cite them for important facts and timeline entries. "
            "Never choose between conflicting dates without support or invent an absent policy. "
            "Draft a short follow-up message if asked, labeling it as an unsent draft. "
            "Do not determine eligibility, liability, enforcement, diagnosis or treatment, "
            "and do not claim to update a record or contact a person."
        ),
        "example_request": "Create an agent that summarizes fictional case notes and drafts follow-up questions.",
        "sample_input": (
            "Summarize these fictional service notes. Preserve the conflicting dates and draft two "
            "follow-up questions. No eligibility policy is supplied.\n\n"
            "NOTE-1: Intake completed on 2027-03-01. A follow-up is planned for 2027-03-10.\n"
            "NOTE-2: Intake completed on 2027-03-03. A follow-up is planned for 2027-03-10.\n"
            "NOTE-3: A requested supporting form has not been supplied."
        ),
        "tools": [],
    },
    "workflow-coordinator": {
        "id": "workflow-coordinator",
        "label": "Workflow Coordinator",
        "description": "Use simulated request and service lookups to prepare a next-step plan.",
        "input": "Use the supplied fictional request identifier and explain the task you want to plan.",
        "output": "Clearly labeled simulated lookup results, missing details and proposed steps for a person to review.",
        "limits": (
            "Only two fixed read-only demo lookups. No connected SaaS systems, ticket creation, "
            "messages, approval enforcement or other business changes. A plan is not an executed action."
        ),
        "delegation": (
            "No specialist delegation. This agent calls two local simulation tools in its own runtime "
            "to look up a fictional request and its service description."
        ),
        "instructions": (
            "Help plan a fictional operational workflow using only the two provided simulated "
            "read-only lookup tools. Given a request ID, first look up the request, then use its "
            "service_id to look up the corresponding service. Preserve the request and service "
            "identifiers in your response. Say clearly that these are simulated fixture lookups "
            "and no external system was contacted. Propose next steps and questions based on the "
            "returned data. If a lookup fails, report it instead of inventing a result. "
            "Never claim to create or update tickets, approve a request, notify anyone, or "
            "execute the proposed plan. There is no business-action or human-approval tool."
        ),
        "example_request": "Create an agent that coordinates a fictional service request using simulated lookups.",
        "sample_input": (
            "Use the demo tools to look up fictional request REQ-101 and its service. "
            "Explain what information is missing and propose next steps for a reviewer. "
            "Label the lookups as simulated. Do not claim that a system change or approval occurred."
        ),
        "tools": [
            {"name": "lookup_demo_request", "description": "Read one fixed fictional request; no external call or update.", "simulated": True},
            {"name": "lookup_demo_service", "description": "Read a fixed fictional service description; no external call or update.", "simulated": True},
        ],
    },
}

_MATCHERS = {
    "document-analyst": re.compile(r"\b(analy[sz]e|analysis|policy|legislation|legislative|bill|notice|notices)\b"),
    "criteria-checker": re.compile(r"\b(criteria|checklist|screen|screening|requirements|coverage)\b"),
    "document-intake": re.compile(r"\b(extract|extracts|extraction|invoice|invoices|intake|fields|forms)\b"),
    "casework-assistant": re.compile(r"\b(casework|case|cases)\b"),
    "workflow-coordinator": re.compile(r"\b(workflow|coordinate|coordinates|orchestration|integration|lookups)\b"),
}


class TemplateRequiredError(ValueError):
    def __init__(self, candidates):
        self.candidates = candidates
        super().__init__("Choose the closest prepared template")


def list_templates():
    return deepcopy(list(TEMPLATES.values()))


def prepare_draft(goal, template_id=None):
    if not isinstance(goal, str) or not 10 <= len(goal) <= 1200 or len(goal.strip()) < 10 or "\x00" in goal:
        raise ValueError("Describe a task in 10 to 1200 characters")
    goal = goal.strip()
    if template_id is None:
        candidates = [key for key, matcher in _MATCHERS.items() if matcher.search(goal.casefold())]
        if len(candidates) != 1:
            raise TemplateRequiredError(candidates)
        template_id = candidates[0]
    if not isinstance(template_id, str) or template_id not in TEMPLATES:
        raise ValueError("Unknown prepared template")
    template = TEMPLATES[template_id]
    instructions = template["instructions"] + "\n\nTask described by the user:\n" + goal
    if len(instructions) > 6000:
        raise ValueError("Prepared task instructions exceed the limit")
    return {
        "template_id": template_id, "name": template["label"], "instructions": instructions,
        "goal": goal, "source": "template", "sample_input": template["sample_input"],
    }

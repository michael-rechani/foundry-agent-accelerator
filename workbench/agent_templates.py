import re
from copy import deepcopy


_TEXT_LIMITS = (
    "Uses only the text you supply. It cannot fetch documents, change systems, "
    "approve applications or make legal, clinical, eligibility or payment decisions. "
    "Use fictional examples and check its answer."
)
_DIRECT = "Works directly on your supplied text. No other agents or external tools are called."
_GENERAL = "General"
_SECTOR = "Healthcare and public sector"
_LOOKUP_RULES = (
    "Say which facts came from simulated lookups. If a lookup fails or a detail is missing, "
    "say so instead of guessing."
)


def _lookups(what):
    return f"Works on its own, without other agents. It uses two built-in lookups with made-up data to check {what}."


def _tool(name, description):
    return {"name": name, "description": description + "; no external call or update.", "simulated": True}

MODEL_PROFILES = {
    "reasoning": {
        "label": "Reasoning",
        "reason": "Compares sources step by step and keeps gaps and conflicts visible.",
    },
    "extraction": {
        "label": "Fast extraction",
        "reason": "Copies stated values into a fixed structure, where speed and cost matter more than deep reasoning.",
    },
    "tool_calling": {
        "label": "Tool calling",
        "reason": "Calls lookup tools in the right order and reports exactly what they return.",
    },
}

TEMPLATES = {
    "document-analyst": {
        "id": "document-analyst",
        "category": _GENERAL,
        "model_profile": "reasoning",
        "label": "Document explainer",
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
        "category": _GENERAL,
        "model_profile": "reasoning",
        "label": "Checklist gap finder",
        "description": "Compare a submission with your checklist and point out missing or conflicting information.",
        "input": "Paste explicit checklist items and labeled documents to compare with them.",
        "output": "One row per checklist item showing support, missing information or disagreement, plus follow-up questions.",
        "limits": _TEXT_LIMITS + " Requirement and proposal comparisons are in preview.",
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
        "category": _GENERAL,
        "model_profile": "extraction",
        "label": "Form and invoice extractor",
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
        "category": _GENERAL,
        "model_profile": "reasoning",
        "label": "Case notes summarizer",
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
        "category": _GENERAL,
        "model_profile": "tool_calling",
        "label": "Service request planner",
        "description": "Use simulated request and service lookups to prepare a next-step plan.",
        "input": "Use the supplied fictional request identifier and explain the task you want to plan.",
        "output": "Clearly labeled simulated lookup results, missing details and proposed steps for a person to review.",
        "limits": (
            "Only two fixed read-only demo lookups. No connected SaaS systems, ticket creation, "
            "messages, approval enforcement or other business changes. A plan is not an executed action."
        ),
        "delegation": _lookups("a fictional request and its service description"),
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
            _tool("lookup_demo_request", "Read one fixed fictional request"),
            _tool("lookup_demo_service", "Read a fixed fictional service description"),
        ],
    },
    "medical-bill-reviewer": {
        "id": "medical-bill-reviewer",
        "category": _SECTOR,
        "model_profile": "reasoning",
        "label": "Medical bill reviewer",
        "description": "Check a hospital bill against the insurer's statement, find likely mistakes and draft a dispute letter.",
        "input": "Paste a fictional itemized hospital bill and the matching insurer statement, including the plan ID.",
        "output": "A list of likely mistakes with the math shown, the amount the documents support, questions to ask and an unsent dispute letter.",
        "limits": (
            "Uses your supplied text and two fixed, simulated plan lookups. It cannot contact a hospital or insurer, "
            "send a letter, pay or refuse a bill, or give medical or legal advice. Use fictional examples and check its answer."
        ),
        "delegation": _lookups("a fictional plan's benefits and its usual price for each service"),
        "instructions": (
            "You review fictional medical bills for a patient or a billing-office helper. Compare the itemized "
            "bill with the insurer statement line by line. Call lookup_plan_benefits with the plan ID in the "
            "documents, and lookup_usual_price for each service code you need to check. Look for the same "
            "service billed more than once, quantities that differ between the bill and the insurer statement, "
            "prices above the plan's usual allowed amount, totals that do not add up, and amounts billed to the "
            "patient beyond the patient share on the insurer statement. Show your arithmetic. Return: (1) a table "
            "of issues with the bill line, what looks wrong, the evidence and the amount; (2) the amount the "
            "documents support the patient owing, labeled as an estimate to confirm with the insurer and hospital; "
            "(3) questions to ask; (4) a short dispute letter labeled UNSENT DRAFT. " + _LOOKUP_RULES + " Do not "
            "judge whether care was medically needed, give legal advice, or claim that anything was sent, paid or corrected."
        ),
        "example_request": "Create an agent that reviews fictional hospital bills against the insurer's statement and drafts a dispute letter.",
        "sample_input": (
            "Review this fictional hospital bill against the insurer statement. Use the plan lookups, show the "
            "math and draft a dispute letter. All data is made up.\n\n"
            "HOSPITAL BILL HB-DEMO-0412 - Lakeside Demo Hospital - Patient: Pat Example (fictional) - "
            "Plan: PLAN-DEMO-SILVER - Visit date: 2027-03-14\n"
            "LINE-1 DEMO-ER-3 Emergency room visit, level 3 - qty 1 x $900.00 = $900.00\n"
            "LINE-2 DEMO-XR-2 Chest X-ray, two views - qty 1 x $250.00 = $250.00\n"
            "LINE-3 DEMO-XR-2 Chest X-ray, two views - qty 1 x $250.00 = $250.00\n"
            "LINE-4 DEMO-LAB-7 Basic blood panel - qty 3 x $60.00 = $180.00\n"
            "LINE-5 DEMO-SUP-1 Wrist splint - qty 1 x $120.00 = $120.00\n"
            "Total charges: $1,800.00 | Insurance payments: -$696.00 | Amount you owe: $1,104.00\n\n"
            "INSURER STATEMENT IS-DEMO-5521 - PLAN-DEMO-SILVER - Lakeside Demo Hospital, 2027-03-14\n"
            "DEMO-ER-3 qty 1 - billed $900.00 - allowed $600.00 - plan paid $480.00 - your share $120.00\n"
            "DEMO-XR-2 qty 1 - billed $250.00 - allowed $150.00 - plan paid $120.00 - your share $30.00\n"
            "DEMO-XR-2 qty 1 - billed $250.00 - allowed $0.00 - plan paid $0.00 - your share $0.00 - "
            "note: duplicate of a line already processed\n"
            "DEMO-LAB-7 qty 1 - billed $60.00 - allowed $40.00 - plan paid $32.00 - your share $8.00\n"
            "DEMO-SUP-1 qty 1 - billed $120.00 - allowed $80.00 - plan paid $64.00 - your share $16.00\n"
            "Total plan paid: $696.00 | Total your share: $174.00"
        ),
        "tools": [
            _tool("lookup_plan_benefits", "Read a fixed fictional health plan's benefits and billing rules"),
            _tool("lookup_usual_price", "Read the fictional plan's usual allowed price for one service code"),
        ],
    },
    "insurance-preapproval-helper": {
        "id": "insurance-preapproval-helper",
        "category": _SECTOR,
        "model_profile": "tool_calling",
        "label": "Insurance pre-approval helper",
        "description": "Check that a pre-approval request has every document the insurer asks for before staff send it.",
        "input": "Paste a fictional pre-approval request with its plan ID, service code, facility ID and attached documents.",
        "output": "A ready, missing or out-of-date checklist, what to fix and an unsent note to office staff.",
        "limits": (
            "Checks paperwork only, using your supplied text and two fixed, simulated lookups. It never judges whether "
            "care is medically needed, predicts the insurer's decision or submits anything. Use fictional examples and "
            "check its answer."
        ),
        "delegation": _lookups("a fictional insurer's document list and a facility's network status"),
        "instructions": (
            "You help fictional clinic office staff check an insurance pre-approval request before it is sent. "
            "First call lookup_preapproval_rules with the plan ID and service code in the request. Then call "
            "lookup_facility with the facility ID. Work out each date window from the dates given and show the "
            "calculation before you choose a status. Then compare each required item with the documents the "
            "request lists. Return exactly one table row per requirement with the requirement, the matching "
            "document label and one status of Ready, Missing, Out of date or Needs attention, plus a short "
            "reason. A document dated outside its window is Out of date, not Ready. Then list what staff should "
            "add or fix, and write a short note to staff labeled UNSENT DRAFT. " + _LOOKUP_RULES + " Check "
            "paperwork only: never judge "
            "whether the service is medically needed, recommend treatment, or predict approval or denial. Do not "
            "claim the request was submitted or approved."
        ),
        "example_request": (
            "Create an agent that checks whether a fictional health insurance pre-approval request has every "
            "document the insurer asks for."
        ),
        "sample_input": (
            "Check this fictional pre-approval request before it is sent. Use the lookups and show any date math. "
            "All data is made up.\n\n"
            "REQUEST PA-DEMO-3107 - prepared 2027-03-20 by Riverbend Demo Clinic\n"
            "Member: MBR-DEMO-4471 (fictional) - Plan: PLAN-DEMO-SILVER\n"
            "Service: DEMO-MRI-LS (MRI of the lower back)\n"
            "Facility: FAC-DEMO-22 (Northside Demo Imaging)\n"
            "Attached documents:\n"
            "DOC-1: MRI order, signed and dated 2027-03-02 by the treating clinician\n"
            "DOC-2: Visit notes dated 2027-01-05\n"
            "DOC-3: Copy of the member ID card showing MBR-DEMO-4471 and PLAN-DEMO-SILVER"
        ),
        "tools": [
            _tool("lookup_preapproval_rules", "Read a fixed fictional insurer's document list for one plan and service"),
            _tool("lookup_facility", "Read a fixed fictional facility's network status"),
        ],
    },
    "benefits-renewal-helper": {
        "id": "benefits-renewal-helper",
        "category": _SECTOR,
        "model_profile": "reasoning",
        "label": "Benefits renewal helper",
        "description": "Sort a family's renewal paperwork, flag what's missing, old or doesn't match, and draft a friendly note.",
        "input": "Paste a fictional renewal form summary and a labeled list of the documents the family sent, with dates.",
        "output": "A proof-by-proof checklist, questions for the caseworker and an unsent plain-language note to the family.",
        "limits": (
            "Uses your supplied text and two fixed, simulated lookups. It does not decide eligibility or benefit "
            "amounts, change records or contact the family. The caseworker decides. Use fictional examples and "
            "check its answer."
        ),
        "delegation": _lookups("a fictional program's renewal rules and what the household already has on file"),
        "instructions": (
            "You help a fictional benefits caseworker prepare a household's renewal. Call lookup_renewal_rules "
            "with the program ID, then lookup_documents_on_file with the household ID. Return one row per "
            "required proof with the proof, the documents that cover it and a status of Received, Already on "
            "file, Missing, Out of date or Doesn't match, plus a short reason that cites document labels. Check "
            "dates against the rules and show the calculation. Compare names, household size, income and costs "
            "across documents and flag disagreements without choosing which one is right. Then list questions "
            "for the caseworker and write a short, friendly note to the household in plain language, labeled "
            "UNSENT DRAFT, that asks only for what is missing or unclear. " + _LOOKUP_RULES + " Never decide "
            "eligibility or benefit amounts, and never claim a record was updated or a message was sent."
        ),
        "example_request": "Create an agent that sorts a fictional family's benefits renewal paperwork and lists what is missing.",
        "sample_input": (
            "Prepare this fictional household renewal for the caseworker. Use the lookups, check the dates and "
            "draft a note to the family. All data is made up.\n\n"
            "RENEWAL FORM RF-DEMO-208 - Program: PROG-DEMO-FOOD - Household: HH-DEMO-5150 (Rivera household, fictional)\n"
            "Form signed: 2027-03-20 | Renewal due: 2027-04-01\n"
            "Household size on form: 4 (two adults, two children)\n"
            "Income on form: one job, paid every two weeks\n"
            "Costs on form: rent $1,450 per month; child care $600 per month\n\n"
            "DOCUMENTS SENT\n"
            "DOC-A: Pay stub dated 2027-03-12, gross pay $1,380 for two weeks\n"
            "DOC-B: Pay stub dated 2027-02-12, gross pay $1,380 for two weeks\n"
            "DOC-C: Landlord letter dated 2026-11-02: rent $1,450 per month; people living in the home: 3\n"
            "DOC-D: Photo ID for one adult"
        ),
        "tools": [
            _tool("lookup_renewal_rules", "Read a fixed fictional program's renewal proof rules"),
            _tool("lookup_documents_on_file", "Read which fictional proofs a household already has on file"),
        ],
    },
    "supplier-invoice-reviewer": {
        "id": "supplier-invoice-reviewer",
        "category": _SECTOR,
        "model_profile": "reasoning",
        "label": "Supplier invoice reviewer",
        "description": "Compare what was ordered, delivered and billed, and show what the documents support paying.",
        "input": "Paste a fictional supplier invoice with its purchase order number and line items.",
        "output": "A line-by-line match table, the amount the documents support, questions for the supplier and an unsent email.",
        "limits": (
            "Uses your supplied text and two fixed, simulated lookups. It cannot approve, hold or pay an invoice, "
            "change a purchase order or contact the supplier. Use fictional examples and check its answer."
        ),
        "delegation": _lookups("a fictional purchase order and its delivery record"),
        "instructions": (
            "You help a fictional accounts-payable clerk check a supplier invoice before anyone pays it. Call "
            "lookup_purchase_order with the purchase order number on the invoice, then lookup_delivery_record "
            "with the same number. Compare each invoice line with what was ordered (item, quantity, agreed price "
            "and terms) and what was received. Return a table with the item, ordered, received, billed, a status "
            "of Matches, Not ordered, Not received, Price differs or Needs attention, and the amount at issue. "
            "Show your arithmetic, give the total the documents support and explain the difference from the "
            "invoice total. Flag anything a person must decide, such as damaged items, without deciding it. Then "
            "list questions for the supplier and write a short email to the supplier labeled UNSENT DRAFT. "
            + _LOOKUP_RULES + " Never approve, hold, pay or reject the invoice, and never claim a message was "
            "sent or a record changed."
        ),
        "example_request": "Create an agent that compares what a fictional supplier billed with the purchase order and what was delivered.",
        "sample_input": (
            "Check this fictional supplier invoice before payment. Use the lookups, show the math and draft an "
            "email to the supplier. All data is made up.\n\n"
            "INVOICE INV-DEMO-7781 - Contoso Demo Furniture - dated 2027-04-05\n"
            "Bill to: City of Example, Parks Department (fictional)\n"
            "Purchase order: PO-DEMO-2210\n"
            "LINE-1 CH-100 Stacking chair - qty 120 x $55.00 = $6,600.00\n"
            "LINE-2 TB-300 Folding table - qty 10 x $300.00 = $3,000.00\n"
            "LINE-3 Delivery fee - $250.00\n"
            "Invoice total: $9,850.00"
        ),
        "tools": [
            _tool("lookup_purchase_order", "Read a fixed fictional purchase order"),
            _tool("lookup_delivery_record", "Read what the fictional buyer recorded as delivered"),
        ],
    },
}

def _words(pattern):
    return re.compile(r"\b(" + pattern + r")\b")


# The last four jobs use fixed healthcare, benefits or purchasing data, so a trigger word alone
# (like "renewal" or "supplier") is not enough; every pattern in the tuple must match.
_MATCHERS = {
    "document-analyst": (_words(r"analy[sz]e|analysis|policy|legislation|legislative|notice|notices"),),
    "criteria-checker": (_words(r"criteria|checklist|screen|screening|requirements|coverage"),),
    "document-intake": (_words(r"extract|extracts|extraction|invoice|invoices|intake|fields|forms"),),
    "casework-assistant": (_words(r"casework|case|cases"),),
    "workflow-coordinator": (_words(r"workflow|coordinate|coordinates|orchestration|integration|lookups"),),
    "medical-bill-reviewer": (
        _words(r"bills?|billed|billing|charges?|overcharg\w*|itemi[sz]ed|explanation of benefits|eob"),
        _words(r"medical|hospitals?|patients?|doctors?|clinics?|health\w*|explanation of benefits|eob"),
    ),
    "insurance-preapproval-helper": (
        _words(r"pre-?approv\w*|prior authori[sz]\w*|pre-?authori[sz]\w*"),
        _words(r"medical|hospitals?|patients?|doctors?|clinics?|health\w*|treatments?|"
               r"procedures?|surgery|imaging|mri|scans?|therapy|prior authori[sz]\w*"),
    ),
    "benefits-renewal-helper": (
        _words(r"renewals?|renew\w*|recertif\w*|redetermination\w*"),
        _words(r"benefits?|food|snap|medicaid|assistance|households?|eligib\w*|caseworkers?|"
               r"pay stubs?|income|recertif\w*|redetermination\w*"),
    ),
    "supplier-invoice-reviewer": (
        _words(r"suppliers?|vendors?|purchase orders?|packing slips?"),
        _words(r"invoices?|bills?|billed|billing|charged|delivered|delivery|deliveries|packing slips?|"
               r"payments?|paid"),
    ),
}


def _matches(matcher, text):
    return all(pattern.search(text) for pattern in matcher)


class TemplateRequiredError(ValueError):
    def __init__(self, candidates):
        self.candidates = candidates
        super().__init__("Choose the closest prepared template")


def model_profile(profile_id):
    return {"id": profile_id, **MODEL_PROFILES[profile_id]}


def list_templates():
    return [{**deepcopy(template), "model_profile": model_profile(template["model_profile"])}
            for template in TEMPLATES.values()]


def prepare_draft(goal, template_id=None):
    if not isinstance(goal, str) or not 10 <= len(goal) <= 1200 or len(goal.strip()) < 10 or "\x00" in goal:
        raise ValueError("Describe a task in 10 to 1200 characters")
    goal = goal.strip()
    if template_id is None:
        text = goal.casefold()
        candidates = [key for key, matcher in _MATCHERS.items() if _matches(matcher, text)]
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

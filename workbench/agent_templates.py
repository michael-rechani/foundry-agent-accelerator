import re
from copy import deepcopy


_TEXT_LIMITS = (
    "Works only from the text you give it. It can't open files, change other systems, "
    "or make legal, medical, eligibility or payment decisions."
)
_DIRECT = "Works on its own from the text you give it. It doesn't call other agents or tools."
_GENERAL = "General"
_SECTOR = "Healthcare and public sector"
_PRIVATE = "Private sector"
_LOOKUP_RULES = (
    "Say which facts came from simulated lookups. If a lookup fails or a detail is missing, "
    "say so instead of guessing."
)


def _lookups(what):
    return f"Works on its own. It uses two built-in lookups with sample data to check {what}."


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
        "description": "Explains a document in plain language, shows what changed and lists questions to ask.",
        "input": "Paste a document, or two versions to compare, and say what you want to understand.",
        "output": "A plain-language summary, what changed, where each point comes from and open questions.",
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
        "example_request": "Create an agent that explains policy notices in plain language and shows what changed.",
        "sample_input": (
            (
            "We're changing our help desk hours. What's actually changing, and what should I ask before we "
            "announce it?\n"
            "\n"
            "Notice 1: Current help desk hours are 9:00 to 17:00, Monday through Friday.\n"
            "Notice 2: Proposed notice: help desk hours will be 8:00 to 17:00 on the same days. No start date or "
            "staffing plan is given."
        )
        ),
        "tools": [],
    },
    "criteria-checker": {
        "id": "criteria-checker",
        "category": _GENERAL,
        "model_profile": "reasoning",
        "label": "Checklist gap finder",
        "description": "Compares a document with your checklist and shows what's covered, missing or unclear.",
        "input": "Paste your checklist and the document you want to check against it.",
        "output": "One row per checklist item showing what's covered, missing or contradictory, plus follow-up questions.",
        "limits": _TEXT_LIMITS + " Comparing requirements with proposals is in preview.",
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
        "example_request": "Create an agent that checks project plans against our checklist before sign-off.",
        "sample_input": (
            (
            "Before I send this project plan for sign-off, does it cover everything on our checklist?\n"
            "\n"
            "Checklist item 1: Includes a total budget.\n"
            "Checklist item 2: Names a delivery owner.\n"
            "Project plan: The Training team will run six weekly onboarding workshops for new hires. No budget is "
            "given."
        )
        ),
        "tools": [],
    },
    "document-intake": {
        "id": "document-intake",
        "category": _GENERAL,
        "model_profile": "extraction",
        "label": "Form field extractor",
        "description": "Pulls the fields you ask for out of forms or invoices, and leaves blanks instead of guessing.",
        "input": "Paste the form or invoice text and list the fields you need.",
        "output": "A table of fields (or JSON if you ask), where each value came from and questions about missing fields.",
        "limits": _TEXT_LIMITS + " It doesn't read file uploads or scans, or update records.",
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
        "example_request": "Create an agent that pulls the fields I need from invoices and request forms.",
        "sample_input": (
            (
            "Pull these fields from the supply request below: request_id, item, quantity, requested_date and "
            "contact_team. Leave anything that isn't there blank and tell me where each value came from.\n"
            "\n"
            "Form 1: Request SUP-104 asks for 12 storage bins. Requested date: 2027-04-12. No contact team is "
            "listed."
        )
        ),
        "tools": [],
    },
    "casework-assistant": {
        "id": "casework-assistant",
        "category": _GENERAL,
        "model_profile": "reasoning",
        "label": "Case summary writer",
        "description": "Turns case notes into a clear summary, a timeline and useful follow-up questions.",
        "input": "Paste the case notes and any messages, plus any rules you want it to keep in mind.",
        "output": "A summary, a timeline, anything that conflicts or is missing and draft follow-up questions.",
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
        "example_request": "Create an agent that summarizes case notes and suggests follow-up questions.",
        "sample_input": (
            (
            "Can you summarize these client notes for my handoff? Flag anything that doesn't line up and suggest "
            "two follow-up questions.\n"
            "\n"
            "Note 1: Intake completed on 2027-03-01. A follow-up is planned for 2027-03-10.\n"
            "Note 2: Intake completed on 2027-03-03. A follow-up is planned for 2027-03-10.\n"
            "Note 3: A requested supporting form hasn't come in yet."
        )
        ),
        "tools": [],
    },
    "workflow-coordinator": {
        "id": "workflow-coordinator",
        "category": _GENERAL,
        "model_profile": "tool_calling",
        "label": "Service request planner",
        "description": "Looks up a service request and suggests next steps for a person to approve.",
        "input": "Give it a request number, such as REQ-101, and say what you want to plan.",
        "output": "What the lookups found, what's missing and suggested next steps for a person to approve.",
        "limits": (
            (
            "Uses the text you give it and two built-in sample lookups. It can't create tickets, send messages or "
            "change other systems. It suggests a plan; it doesn't carry it out."
        )
        ),
        "delegation": _lookups("the request and the service it asks for"),
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
        "example_request": "Create an agent that coordinates service requests and suggests next steps.",
        "sample_input": (
            "Look up request REQ-101 and the service it's for. What's missing, and what should happen next?"
        ),
        "tools": [
            _tool("lookup_demo_request", "Looks up a sample service request"),
            _tool("lookup_demo_service", "Looks up the service a sample request asks for"),
        ],
    },
    "medical-bill-reviewer": {
        "id": "medical-bill-reviewer",
        "category": _SECTOR,
        "model_profile": "reasoning",
        "label": "Medical bill reviewer",
        "description": (
            "Checks a hospital bill against the insurer's statement, finds likely mistakes and drafts a dispute "
            "letter."
        ),
        "input": "Paste the itemized hospital bill and the insurer's statement, including the plan ID.",
        "output": (
            "Likely mistakes with the math shown, what the documents say you owe, questions to ask and a draft "
            "dispute letter."
        ),
        "limits": (
            (
            "Uses the text you give it and two built-in sample lookups. It can't contact the hospital or insurer, "
            "send a letter or pay a bill, and it doesn't give medical or legal advice."
        )
        ),
        "delegation": _lookups("the plan's benefits and its usual price for each service"),
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
        "example_request": (
            "Create an agent that checks hospital bills against the insurer's statement and drafts a dispute "
            "letter."
        ),
        "sample_input": (
            (
            "I think this hospital bill is wrong. Can you check it against what my insurer says, show the math and "
            "help me write a dispute letter?\n"
            "\n"
            "HOSPITAL BILL HB-DEMO-0412 - Lakeside Demo Hospital - Patient: Pat Example - Plan: PLAN-DEMO-SILVER - "
            "Visit date: 2027-03-14\n"
            "Line 1: DEMO-ER-3 Emergency room visit, level 3 - qty 1 x $900.00 = $900.00\n"
            "Line 2: DEMO-XR-2 Chest X-ray, two views - qty 1 x $250.00 = $250.00\n"
            "Line 3: DEMO-XR-2 Chest X-ray, two views - qty 1 x $250.00 = $250.00\n"
            "Line 4: DEMO-LAB-7 Basic blood panel - qty 3 x $60.00 = $180.00\n"
            "Line 5: DEMO-SUP-1 Wrist splint - qty 1 x $120.00 = $120.00\n"
            "Total charges: $1,800.00 | Insurance payments: -$696.00 | Amount you owe: $1,104.00\n"
            "\n"
            "INSURER STATEMENT IS-DEMO-5521 - PLAN-DEMO-SILVER - Lakeside Demo Hospital, 2027-03-14\n"
            "DEMO-ER-3 qty 1 - billed $900.00 - allowed $600.00 - plan paid $480.00 - your share $120.00\n"
            "DEMO-XR-2 qty 1 - billed $250.00 - allowed $150.00 - plan paid $120.00 - your share $30.00\n"
            "DEMO-XR-2 qty 1 - billed $250.00 - allowed $0.00 - plan paid $0.00 - your share $0.00 - note: "
            "duplicate of a line already processed\n"
            "DEMO-LAB-7 qty 1 - billed $60.00 - allowed $40.00 - plan paid $32.00 - your share $8.00\n"
            "DEMO-SUP-1 qty 1 - billed $120.00 - allowed $80.00 - plan paid $64.00 - your share $16.00\n"
            "Total plan paid: $696.00 | Total your share: $174.00"
        )
        ),
        "tools": [
            _tool("lookup_plan_benefits", "Looks up a sample health plan's benefits and billing rules"),
            _tool("lookup_usual_price", "Looks up the sample plan's usual price for one service"),
        ],
    },
    "insurance-preapproval-helper": {
        "id": "insurance-preapproval-helper",
        "category": _SECTOR,
        "model_profile": "tool_calling",
        "label": "Insurance pre-approval helper",
        "description": "Checks that a pre-approval request has every document the insurer asks for before staff send it.",
        "input": "Paste the pre-approval request with its plan ID, service code, facility ID and attached documents.",
        "output": "A checklist marked ready, missing or out of date, what to fix and a draft note to office staff.",
        "limits": (
            (
            "Uses the text you give it and two built-in sample lookups. It checks paperwork only. It never judges "
            "whether care is medically needed, predicts the insurer's decision or submits anything."
        )
        ),
        "delegation": _lookups("the insurer's document list and whether the facility is in network"),
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
            (
            "Create an agent that checks whether a health insurance pre-approval request has every document the "
            "insurer asks for."
        )
        ),
        "sample_input": (
            (
            "Is this pre-approval request ready to send? Check it against what the insurer requires and show any "
            "date math.\n"
            "\n"
            "REQUEST PA-DEMO-3107 - prepared 2027-03-20 by Riverbend Demo Clinic\n"
            "Member: MBR-DEMO-4471 - Plan: PLAN-DEMO-SILVER\n"
            "Service: DEMO-MRI-LS (MRI of the lower back)\n"
            "Facility: FAC-DEMO-22 (Northside Demo Imaging)\n"
            "Attached documents:\n"
            "Document 1: MRI order, signed and dated 2027-03-02 by the treating clinician\n"
            "Document 2: Visit notes dated 2027-01-05\n"
            "Document 3: Copy of the member ID card showing MBR-DEMO-4471 and PLAN-DEMO-SILVER"
        )
        ),
        "tools": [
            _tool("lookup_preapproval_rules", "Looks up a sample insurer's required documents for one plan and service"),
            _tool("lookup_facility", "Looks up whether a sample facility is in network"),
        ],
    },
    "benefits-renewal-helper": {
        "id": "benefits-renewal-helper",
        "category": _SECTOR,
        "model_profile": "reasoning",
        "label": "Benefits renewal helper",
        "description": (
            "Sorts a family's renewal paperwork, flags what's missing, old or doesn't match, and drafts a friendly "
            "note."
        ),
        "input": "Paste the renewal form summary and a list of the documents the family sent, with dates.",
        "output": (
            "A proof-by-proof checklist, questions for the caseworker and a draft plain-language note to the "
            "family."
        ),
        "limits": (
            (
            "Uses the text you give it and two built-in sample lookups. It doesn't decide eligibility or benefit "
            "amounts, change records or contact the family. The caseworker decides."
        )
        ),
        "delegation": _lookups("the program's renewal rules and what the household already has on file"),
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
        "example_request": "Create an agent that sorts a family's benefits renewal paperwork and lists what is missing.",
        "sample_input": (
            (
            "Help me get this family's renewal ready. What's missing, out of date or doesn't match? Then draft a "
            "friendly note asking for what we still need.\n"
            "\n"
            "RENEWAL FORM RF-DEMO-208 - Program: PROG-DEMO-FOOD - Household: HH-DEMO-5150 (Rivera household)\n"
            "Form signed: 2027-03-20 | Renewal due: 2027-04-01\n"
            "Household size on form: 4 (two adults, two children)\n"
            "Income on form: one job, paid every two weeks\n"
            "Costs on form: rent $1,450 per month; child care $600 per month\n"
            "\n"
            "DOCUMENTS SENT\n"
            "Document A: Pay stub dated 2027-03-12, gross pay $1,380 for two weeks\n"
            "Document B: Pay stub dated 2027-02-12, gross pay $1,380 for two weeks\n"
            "Document C: Landlord letter dated 2026-11-02: rent $1,450 per month; people living in the home: 3\n"
            "Document D: Photo ID for one adult"
        )
        ),
        "tools": [
            _tool("lookup_renewal_rules", "Looks up a sample program's renewal rules"),
            _tool("lookup_documents_on_file", "Looks up which proofs a sample household already has on file"),
        ],
    },
    "supplier-invoice-reviewer": {
        "id": "supplier-invoice-reviewer",
        "category": _GENERAL,
        "model_profile": "reasoning",
        "label": "Supplier invoice reviewer",
        "description": "Compares what was ordered, delivered and billed, and shows what the documents support paying.",
        "input": "Paste the supplier's invoice, including the purchase order number and line items.",
        "output": "A line-by-line match, the amount the documents support, questions for the supplier and a draft email.",
        "limits": (
            (
            "Uses the text you give it and two built-in sample lookups. It can't approve, hold or pay an invoice, "
            "change a purchase order or contact the supplier."
        )
        ),
        "delegation": _lookups("the purchase order and what was delivered"),
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
        "example_request": "Create an agent that compares what a supplier billed with the purchase order and what was delivered.",
        "sample_input": (
            (
            "Can you check this invoice before I approve it? Compare it with the purchase order and what we "
            "actually received, show the math, and draft an email to the supplier about anything that doesn't "
            "match.\n"
            "\n"
            "INVOICE INV-DEMO-7781 - Example Furniture Supply - dated 2027-04-05\n"
            "Bill to: Example Conference Center\n"
            "Purchase order: PO-DEMO-2210\n"
            "Line 1: CH-100 Stacking chair - qty 120 x $55.00 = $6,600.00\n"
            "Line 2: TB-300 Folding table - qty 10 x $300.00 = $3,000.00\n"
            "Line 3: Delivery fee - $250.00\n"
            "Invoice total: $9,850.00"
        )
        ),
        "tools": [
            _tool("lookup_purchase_order", "Looks up the sample purchase order"),
            _tool("lookup_delivery_record", "Looks up what the sample buyer recorded as delivered"),
        ],
    },
}

TEMPLATES.update({
    "public-records-intake": {
        "id": "public-records-intake",
        "category": _SECTOR,
        "model_profile": "extraction",
        "label": "Public records request organizer",
        "description": "Organize a fictional public records request into scope, date range, named offices and clarification questions.",
        "input": "Paste the fictional request, any supplied correspondence and the intake fields your office uses.",
        "output": "A structured intake summary, quoted scope terms, missing details and an unsent clarification draft.",
        "limits": _TEXT_LIMITS + " It doesn't search records, apply exemptions, calculate fees or release information.",
        "delegation": _DIRECT,
        "instructions": (
            "Organize fictional public records request text for intake staff. Extract only stated requester details, "
            "date ranges, offices, record types, delivery preferences and deadlines. Quote the words that define "
            "scope and use null for missing fields. Identify ambiguous terms and draft focused clarification "
            "questions labeled UNSENT DRAFT. Do not search for records, interpret disclosure law, apply exemptions, "
            "estimate fees, set a legal deadline or decide what must be released. A records officer makes those decisions."
        ),
        "example_request": "Create an agent that organizes a fictional public records request and drafts clarification questions.",
        "sample_input": (
            "Organize this fictional public records request. Quote the scope and use null for missing intake fields.\n\n"
            "Request PR-DEMO-17: Please provide final inspection summaries issued by the Example Building Office "
            "for community centers between 2027-01-01 and 2027-03-31. Electronic delivery is preferred. "
            "The request does not name a contact person or clarify whether attachments are included."
        ),
        "tools": [],
    },
    "grant-reporting-checker": {
        "id": "grant-reporting-checker",
        "category": _SECTOR,
        "model_profile": "reasoning",
        "label": "Grant reporting checker",
        "description": "Compare a fictional grant report with supplied award terms and evidence before staff review.",
        "input": "Paste labeled award terms, the draft report and the evidence supplied for each reported result.",
        "output": "A requirement-by-requirement evidence table, unsupported claims, conflicts and reviewer questions.",
        "limits": _TEXT_LIMITS + " It can't certify compliance, approve costs or submit a report.",
        "delegation": _DIRECT,
        "instructions": (
            "Check a fictional grant report against only the supplied award terms and labeled evidence. Return one "
            "row per reporting requirement with the stated claim, supporting quote or reference, and a status of "
            "supported, gap or conflict. A gap is a request for evidence, not a finding of noncompliance. Preserve "
            "conflicting figures and draft reviewer questions. Do not invent award conditions, certify compliance, "
            "approve spending, recommend enforcement, recover funds or claim the report was submitted."
        ),
        "example_request": "Create an agent that checks a fictional grant report against award terms and evidence.",
        "sample_input": (
            "Check this fictional grant report. Do not certify compliance.\n\n"
            "Award term A: Report the number of completed workshops and attach attendance evidence.\n"
            "Draft report: Six workshops were completed and 84 residents attended.\n"
            "Evidence E1: Sign-in sheets labeled Workshop 1 through Workshop 5 list 68 total entries. "
            "No evidence for Workshop 6 is supplied."
        ),
        "tools": [],
    },
    "community-program-brief": {
        "id": "community-program-brief",
        "category": _SECTOR,
        "model_profile": "reasoning",
        "label": "Community program brief writer",
        "description": "Turn fictional program notes and measures into an evidence-linked briefing for staff.",
        "input": "Paste labeled program notes, stated measures, results and unresolved questions.",
        "output": "A concise briefing, measure table, caveats and draft questions for the program owner.",
        "limits": _TEXT_LIMITS + " It can't validate outcomes, allocate funding or make policy decisions.",
        "delegation": _DIRECT,
        "instructions": (
            "Prepare a briefing from fictional community program material. Separate planned activities, reported "
            "results, source-supported observations and unresolved questions. Cite labels for every numeric claim "
            "and preserve differences between targets and results. Do not infer causation, validate outcomes, rank "
            "communities, allocate funding or recommend a policy decision. End with questions a person should resolve."
        ),
        "example_request": "Create an agent that summarizes a fictional community program and its reported outcomes.",
        "sample_input": (
            "Brief this fictional community program for staff.\n\n"
            "Plan P1: Run eight digital-skills sessions with a target of 80 registrations.\n"
            "Update U1: Seven sessions were held; registration records show 76 registrations and 51 unique attendees.\n"
            "Survey S1: 29 attendees responded; 22 said they felt more confident. No comparison group is supplied."
        ),
        "tools": [],
    },
    "customer-support-brief": {
        "id": "customer-support-brief",
        "category": _PRIVATE,
        "model_profile": "reasoning",
        "label": "Support ticket handoff",
        "description": "Turns a support ticket into a handoff note for the next person, plus a draft reply.",
        "input": "Paste the ticket messages, any internal notes and the support policy you follow.",
        "output": "A timeline, what's confirmed, what's still open, suggested next steps and a draft reply.",
        "limits": _TEXT_LIMITS + " It can't open accounts, issue credits or contact the customer.",
        "delegation": _DIRECT,
        "instructions": (
            "Create a handoff from fictional customer support ticket text. Preserve the timeline, distinguish customer "
            "claims from confirmed product notes, cite labels and keep conflicting details visible. Suggest bounded "
            "next steps and write a response labeled UNSENT DRAFT. Do not access accounts, promise resolution dates, "
            "issue credits, change service, assign fault or claim a message was sent."
        ),
        "example_request": "Create an agent that turns a customer support ticket into a handoff note and drafts a reply.",
        "sample_input": (
            (
            "I'm handing this ticket to the next shift. Write a handoff note and a reply to the customer.\n"
            "\n"
            "Ticket T1, 09:10: Customer says export job EX-44 has shown Processing since yesterday.\n"
            "Agent note N1, 09:35: Status screenshot shows Processing; no service logs were checked.\n"
            "Product note P1: Escalate after four hours only when a job start timestamp is confirmed. The start "
            "timestamp is not supplied."
        )
        ),
        "tools": [],
    },
    "cash-application-reviewer": {
        "id": "cash-application-reviewer",
        "category": _PRIVATE,
        "model_profile": "extraction",
        "label": "Payment matcher",
        "description": "Matches a customer payment to open invoices and flags any amount that doesn't fit.",
        "input": "Paste the remittance advice, the payment total and your list of open invoices.",
        "output": "Suggested matches with the math, amounts that don't match and questions for the finance team.",
        "limits": _TEXT_LIMITS + " It can't post payments, change the ledger, issue refunds or write off balances.",
        "delegation": _DIRECT,
        "instructions": (
            "Compare fictional remittance advice with a supplied open-invoice list. Preserve identifiers and amounts, "
            "show arithmetic, and label each proposed match as exact, partial, ambiguous or unmatched. Never choose "
            "between ambiguous invoices. Return questions for finance staff and use null for absent references. "
            "Do not post cash, modify a ledger, issue a refund, approve a write-off or claim reconciliation is final."
        ),
        "example_request": "Create an agent that matches customer remittance advice to open receivables.",
        "sample_input": (
            (
            "Match this customer payment to our open invoices and show the math.\n"
            "\n"
            "Remittance R-88: Payment total $1,450. References INV-101 for $1,000 and INV-104 for $400. No "
            "reference is supplied for the remaining amount.\n"
            "Open invoices: INV-101 $1,000; INV-104 $450; INV-140 $50."
        )
        ),
        "tools": [],
    },
    "maintenance-work-order-planner": {
        "id": "maintenance-work-order-planner",
        "category": _PRIVATE,
        "model_profile": "reasoning",
        "label": "Maintenance work order planner",
        "description": "Turns maintenance notes into a work plan and asks the safety questions first.",
        "input": "Paste the work order, shift notes and any equipment guidance or site rules.",
        "output": (
            "A summary of the problem, a step-by-step plan, missing safety details and a draft brief for the "
            "technician."
        ),
        "limits": _TEXT_LIMITS + " It can't diagnose equipment, dispatch staff, approve a shutdown or control machinery.",
        "delegation": _DIRECT,
        "instructions": (
            "Prepare a plan from fictional maintenance work order notes and supplied asset guidance. Separate observed "
            "symptoms from possible causes, cite labels, and list missing isolation, access and safety information. "
            "Propose inspection steps only when supported by the supplied guidance and label the technician brief "
            "UNSENT DRAFT. Do not diagnose equipment, direct hazardous work, dispatch staff, authorize a shutdown, "
            "change a schedule or claim that machinery was controlled."
        ),
        "example_request": "Create an agent that plans maintenance work orders from technician notes.",
        "sample_input": (
            (
            "Help me plan this work order. Don't guess at the cause; tell me what we need to check first.\n"
            "\n"
            "Work order WO-72: Conveyor C-4 makes an intermittent scraping sound near the end roller.\n"
            "Shift note S1: Sound was heard twice during unloaded operation. No vibration reading was taken.\n"
            "Asset guide G1: Before inspection, confirm lockout authorization and inspect guards for visible "
            "contact. No lockout authorization or site contact is supplied."
        )
        ),
        "tools": [],
    },
})

# Private-sector preview agents: complete definitions with offline acceptance cases, not yet validated live.
TEMPLATES.update({
    "contract-playbook-checker": {
        "id": "contract-playbook-checker",
        "category": _PRIVATE,
        "model_profile": "reasoning",
        "label": "Contract playbook checker",
        "description": "Compares contract clauses with your negotiation playbook and flags where they fall outside it.",
        "input": "Paste the contract clauses and your playbook's preferred, fallback and unacceptable positions.",
        "output": "A clause-by-clause comparison with your playbook, missing clauses and questions for legal counsel.",
        "limits": _TEXT_LIMITS + " It doesn't give legal advice, negotiate, accept terms or sign anything.",
        "delegation": _DIRECT,
        "instructions": (
            "You compare fictional contract clauses with a supplied negotiation playbook. For each playbook item, "
            "quote the matching clause label and label it Matches preferred, Within fallback, Outside playbook or "
            "Not found. Show the playbook position you compared it with. Keep conflicting clauses visible instead "
            "of choosing one. Only suggest replacement wording copied from the supplied playbook, labeled "
            "SUGGESTION FOR COUNSEL REVIEW. List questions for legal counsel. Do not give legal advice, judge "
            "enforceability, decide whether to sign, accept or reject terms, or claim anything was negotiated or sent."
        ),
        "example_request": "Create an agent that checks contract clauses against our negotiation playbook.",
        "sample_input": (
            (
            "Does this contract fit our negotiation playbook? Go clause by clause.\n"
            "\n"
            "Playbook PB-1 Liability cap: preferred 12 months of fees; fallback up to 24 months; unlimited is not "
            "acceptable.\n"
            "Playbook PB-2 Payment terms: preferred net 45; fallback net 30.\n"
            "Playbook PB-3 Governing law: preferred Example State.\n"
            "\n"
            "Contract C-1, section 4.2: Supplier liability is capped at 36 months of fees.\n"
            "Contract C-1, section 6.1: Invoices are payable net 30.\n"
            "No governing law clause is supplied."
        )
        ),
        "tools": [],
    },
    "rfp-answer-drafter": {
        "id": "rfp-answer-drafter",
        "category": _PRIVATE,
        "model_profile": "reasoning",
        "label": "RFP answer drafter",
        "description": "Drafts answers to RFP and security questionnaire questions using only your approved facts.",
        "input": "Paste the questions and the approved product facts the answers can use.",
        "output": "Draft answers with their source facts, how well each is supported and questions for your experts.",
        "limits": _TEXT_LIMITS + " It can't submit a response, commit to prices or dates, or claim certifications.",
        "delegation": _DIRECT,
        "instructions": (
            "You draft answers to fictional request for proposal (RFP) or security questionnaire questions. Use only "
            "the supplied approved facts and cite their labels. For each question, return a draft answer and a support "
            "level of Supported, Partly supported or No approved answer. When no fact covers a question, write "
            "NEEDS SME instead of an answer. Never invent capabilities, certifications, prices, delivery dates or "
            "contractual commitments, and never soften a fact into a broader claim. Label the full answer set "
            "UNSENT DRAFT. Do not submit anything or claim a response was sent."
        ),
        "example_request": "Create an agent that drafts RFP answers from our approved product facts.",
        "sample_input": (
            (
            "Draft answers to these RFP questions using only our approved facts.\n"
            "\n"
            "Q1: Does the product support single sign-on with SAML?\n"
            "Q2: Where is customer data stored?\n"
            "Q3: Do you hold ISO 27001 certification?\n"
            "\n"
            "Fact F1: Supports SAML 2.0 single sign-on on the Business and Enterprise plans.\n"
            "Fact F2: Customer data is stored in the region the customer chooses: United States or European "
            "Union.\n"
            "No approved fact covers certifications."
        )
        ),
        "tools": [],
    },
    "expense-report-checker": {
        "id": "expense-report-checker",
        "category": _PRIVATE,
        "model_profile": "tool_calling",
        "label": "Expense report checker",
        "description": "Checks an expense report against your travel rules and the approved trip before reimbursement.",
        "input": "Paste the expense report with its policy ID, trip ID and line items.",
        "output": "A line-by-line check with the math, items that need a receipt or explanation, and a draft note.",
        "limits": (
            (
            "Uses the text you give it and two built-in sample lookups. It can't approve, reject or reimburse "
            "expenses, change a report or contact the employee."
        )
        ),
        "delegation": _lookups("your travel rules and the approved trip"),
        "instructions": (
            "You help a fictional finance reviewer check an expense report before reimbursement. Call "
            "lookup_expense_policy with the policy ID on the report, then lookup_trip_request with the trip ID. "
            "Check every line against the policy limits, receipt rule and non-reimbursable items, and against the "
            "approved trip dates and budget. Return a table with the line, amount, rule checked, a status of "
            "Within policy, Over limit, Needs receipt, Not reimbursable, Outside trip dates or Needs attention, and "
            "the amount at issue. Show your arithmetic. When a claimed amount and its receipt total differ, show "
            "both, mark the line Needs attention and ask the employee to explain instead of choosing one. Then "
            "write a short note to the employee labeled UNSENT DRAFT that asks only for missing receipts or "
            "explanations. " + _LOOKUP_RULES + " Never approve, reject or reimburse an expense, grant a policy "
            "exception or claim a message was sent. If asked to approve or pay, say that a finance approver "
            "decides."
        ),
        "example_request": "Create an agent that checks employee expense reports and receipts before reimbursement.",
        "sample_input": (
            (
            "Check this expense report before I approve it, show the math and draft a note to the employee about "
            "anything that's missing.\n"
            "\n"
            "EXPENSE REPORT ER-DEMO-118 - Employee: Jordan Lee\n"
            "Policy: POL-DEMO-TRAVEL | Trip: TRIP-DEMO-4410\n"
            "Line 1: Hotel, 2 nights x $260.00 = $520.00, receipt attached\n"
            "Line 2: Dinner 2027-05-10, $96.00 including $18.00 wine, receipt attached\n"
            "Line 3: Rideshare 2027-05-11, $34.00, no receipt\n"
            "Line 4: Lunch 2027-05-13, $22.00, no receipt\n"
            "Report total: $672.00"
        )
        ),
        "tools": [
            _tool("lookup_expense_policy", "Looks up the sample travel and expense rules"),
            _tool("lookup_trip_request", "Looks up the sample approved trip"),
        ],
    },
    "incident-timeline-writer": {
        "id": "incident-timeline-writer",
        "category": _PRIVATE,
        "model_profile": "reasoning",
        "label": "IT incident timeline writer",
        "description": "Turns alerts, chat messages and tickets into an incident timeline and a stakeholder update.",
        "input": "Paste the alerts, chat messages and ticket notes from the incident, with their timestamps.",
        "output": "A timeline, the stated impact, facts kept apart from guesses, open questions and a draft update.",
        "limits": _TEXT_LIMITS + " It can't run commands, change systems, name a root cause or close an incident.",
        "delegation": _DIRECT,
        "instructions": (
            "You build an incident timeline from fictional alert, chat and ticket excerpts. Keep the original "
            "timestamps and time zone, order events by time and cite each source label. Separate observed facts "
            "from hypotheses, and mark guesses in the notes as unconfirmed. State impact only as the sources state "
            "it and list what is unknown, such as the number of affected customers. If a time zone is missing or "
            "sources disagree about when something started, keep every time visible, say the order may be wrong "
            "and do not pick one. End with questions for the incident commander, such as which time zone each "
            "source uses. Write a short stakeholder update "
            "labeled UNSENT DRAFT. Do not run or suggest running commands against production, declare a root cause, "
            "set severity, assign blame, close the incident or say service is restored unless a source says so. "
            "Leave root cause and severity to the incident commander."
        ),
        "example_request": "Create an agent that builds a timeline and stakeholder update from incident notes.",
        "sample_input": (
            (
            "Put together a timeline and a short update for stakeholders from these incident notes.\n"
            "\n"
            "A1 14:02 UTC Alert: checkout API error rate 12% (threshold 2%).\n"
            "C1 14:06 UTC On-call chat: Rolled back deployment 7.4.1 at 14:05.\n"
            "C2 14:11 UTC On-call chat: Error rate back under 1%. Maybe it was the cache?\n"
            "T1 14:20 UTC Ticket: A customer reports failed payments between 13:55 and 14:08 UTC.\n"
            "No count of affected customers is supplied."
        )
        ),
        "tools": [],
    },
    "customer-feedback-themes": {
        "id": "customer-feedback-themes",
        "category": _PRIVATE,
        "model_profile": "reasoning",
        "label": "Customer feedback theme finder",
        "description": "Groups customer feedback into themes, with counts, example quotes and anything that doesn't fit.",
        "input": "Paste the feedback, such as survey comments or support notes, one item per line.",
        "output": (
            "Themes with counts and the items in each, an example quote per theme, outliers and questions for the "
            "product team."
        ),
        "limits": _TEXT_LIMITS + " It can't identify people, contact customers or set product priorities.",
        "delegation": _DIRECT,
        "instructions": (
            "You group fictional customer feedback into themes. Give each theme a short name, the labels of the "
            "items in it and a count of those items; an item may belong to more than one theme. Quote one "
            "representative item per theme. Report sentiment only as the item states it. List items that fit no "
            "theme. The counts describe only the supplied items: never turn them into percentages of all customers "
            "or claim a trend. Do not infer who a customer is or any personal traits, contact customers, or decide "
            "product priorities or roadmap changes."
        ),
        "example_request": "Create an agent that groups customer feedback into themes with counts and quotes.",
        "sample_input": (
            (
            "Group this customer feedback into themes, with counts and a quote for each.\n"
            "\n"
            "F1: Export to CSV takes forever on large reports.\n"
            "F2: Love the new dashboard colors.\n"
            "F3: CSV export timed out twice this week.\n"
            "F4: I can't find where to change my billing email.\n"
            "F5: The dashboard looks great, but export is still slow."
        )
        ),
        "tools": [],
    },
    "order-delay-helper": {
        "id": "order-delay-helper",
        "category": _PRIVATE,
        "model_profile": "tool_calling",
        "label": "Order delay helper",
        "description": "Finds out where a late order is from the order and shipping records, and drafts a reply.",
        "input": "Paste the customer's message, including the order number.",
        "output": "Where each item is, with sources, anything not yet shipped, questions for staff and a draft reply.",
        "limits": (
            (
            "Uses the text you give it and two built-in sample lookups. It can't refund, cancel or reship an "
            "order, promise a delivery date or contact the carrier."
        )
        ),
        "delegation": _lookups("the order and its shipping status"),
        "instructions": (
            "You help fictional customer service staff answer a question about a delayed order. Call lookup_order "
            "with the order number in the message, then lookup_shipment with the same number. Summarize what was "
            "ordered, the promised date, each shipment's latest tracking event and any item not yet shipped, citing "
            "which lookup each fact came from. Quote the carrier's estimate as an estimate, not a promise. If the "
            "customer's message disagrees with the order record, such as a different item or quantity, show both, "
            "don't assume either is wrong and ask staff to confirm. List what "
            "a person must decide, such as a refund request, without deciding it. Write a short, friendly reply "
            "labeled UNSENT DRAFT. " + _LOOKUP_RULES + " Never issue or promise a refund, credit, cancellation or "
            "reshipment, promise a delivery date, or claim the carrier or customer was contacted."
        ),
        "example_request": "Create an agent that explains where a late customer order is and drafts a reply.",
        "sample_input": (
            (
            "A customer just wrote in about a late order. Where is it, and can you draft a reply?\n"
            "\n"
            "Message: Hi, my order ORD-DEMO-3307 was supposed to arrive on June 6 and it still isn't here. Where "
            "is it? I want a refund. - A. Chen"
        )
        ),
        "tools": [
            _tool("lookup_order", "Looks up a sample customer order"),
            _tool("lookup_shipment", "Looks up shipping status for a sample order"),
        ],
    },
})

# Retired jobs stay loadable so agents already created from them keep working, but the library no
# longer lists, previews, matches or creates them.
RETIRED_TEMPLATES = frozenset({"public-records-intake", "grant-reporting-checker", "community-program-brief"})

# Library order: everyday business jobs first, then specialist healthcare and public-sector jobs.
LIBRARY_ORDER = (
    "supplier-invoice-reviewer", "expense-report-checker", "order-delay-helper", "customer-support-brief",
    "customer-feedback-themes", "document-analyst", "document-intake", "criteria-checker",
    "contract-playbook-checker", "rfp-answer-drafter", "incident-timeline-writer", "cash-application-reviewer",
    "maintenance-work-order-planner", "workflow-coordinator", "casework-assistant", "medical-bill-reviewer",
    "insurance-preapproval-helper", "benefits-renewal-helper",
)


def is_listed(template_id):
    return template_id in TEMPLATES and template_id not in RETIRED_TEMPLATES


SECTORS = (
    {"id": "cross-sector", "label": "Any sector"},
    {"id": "public", "label": "Healthcare and public sector"},
    {"id": "private", "label": "Private sector"},
)
INDUSTRIES = (
    {"id": "general-operations", "label": "General operations"},
    {"id": "health-administration", "label": "Health administration"},
    {"id": "government-services", "label": "Government services"},
    {"id": "procurement", "label": "Procurement"},
    {"id": "finance", "label": "Finance"},
    {"id": "customer-operations", "label": "Customer operations"},
    {"id": "field-operations", "label": "Field operations"},
    {"id": "legal-operations", "label": "Legal operations"},
    {"id": "sales", "label": "Sales"},
    {"id": "it-operations", "label": "IT operations"},
    {"id": "retail", "label": "Retail and e-commerce"},
)
TASKS = (
    {"id": "review", "label": "Review"},
    {"id": "extract", "label": "Extract"},
    {"id": "summarize", "label": "Summarize"},
    {"id": "plan", "label": "Plan"},
    {"id": "draft", "label": "Draft"},
    {"id": "triage", "label": "Triage"},
)
READINESS_LEVELS = (
    {"id": "reviewed", "label": "Reviewed", "description": "Its instructions have been reviewed and its setup passes the Lab's validation."},
    {"id": "sample", "label": "In progress", "description": "Its setup passes the Lab's validation, but a person hasn't signed off on its test answers yet. Try it with sample data, and check it against your own policies before real use."},
)
TOOL_MODES = (
    {"id": "none", "label": "Text only", "description": "Works only from the text you give it."},
    {"id": "simulated", "label": "Sample lookups", "description": "Looks up sample records that come with the Lab. It can't change anything."},
)

_PROFILE_HINTS = {
    "reasoning": {"relative_cost": "medium", "relative_latency": "medium"},
    "extraction": {"relative_cost": "lower", "relative_latency": "lower"},
    "tool_calling": {"relative_cost": "medium", "relative_latency": "higher"},
}


def _metadata(sector, industry, tasks, summary, expected_behavior, human_decision, keywords, *, readiness="sample"):
    return {
        "sector": sector, "industry": industry, "tasks": tasks, "summary": summary,
        "expected_behavior": expected_behavior, "human_decision": human_decision,
        "keywords": keywords, "readiness": readiness,
    }


TEMPLATE_METADATA = {
    "document-analyst": _metadata("cross-sector", "general-operations", ["summarize", "review"],
        "Explains documents in plain language, shows what changed and lists questions for staff.",
        "References supplied labels, separates stated changes from implications and asks for missing material.",
        "A person interprets obligations and decides what action to take.", ["documents", "policy", "comparison"], readiness="reviewed"),
    "criteria-checker": _metadata("cross-sector", "general-operations", ["review"],
        "Checks a submission against a checklist and points out anything missing or conflicting.",
        "Returns one result per supplied criterion with evidence, gaps, conflicts and focused questions.",
        "A person decides compliance, acceptance, scoring and any award.", ["checklist", "criteria", "requirements"], readiness="reviewed"),
    "document-intake": _metadata("cross-sector", "general-operations", ["extract"],
        "Pulls the fields you ask for from forms or invoices, and leaves missing ones blank.",
        "Preserves stated values and labels, uses null for missing fields and identifies inconsistencies.",
        "A person validates extracted data and decides whether to update a record.", ["forms", "invoice", "fields"], readiness="reviewed"),
    "casework-assistant": _metadata("public", "government-services", ["summarize", "draft"],
        "Turns case notes into a short summary with sources and follow-up questions.",
        "Preserves timelines and conflicts, separates supplied rules and labels any message as an unsent draft.",
        "A person decides eligibility, liability, enforcement and any case action.", ["casework", "timeline", "follow-up"], readiness="reviewed"),
    "workflow-coordinator": _metadata("cross-sector", "general-operations", ["plan", "triage"],
        "Looks up a service request and suggests next steps for a person to approve.",
        "Says which details came from the sample lookups, keeps request numbers and reports a failed lookup instead of guessing.",
        "A person approves and executes any workflow or system change.", ["workflow", "request", "service"], readiness="reviewed"),
    "medical-bill-reviewer": _metadata("public", "health-administration", ["review", "draft"],
        "Compares a medical bill with the insurer's statement and points out likely errors.",
        "Checks the sample plan data, shows the math and labels the dispute letter as an unsent draft.",
        "A person confirms the amount, disputes the bill and makes payment decisions.", ["medical bill", "insurer", "dispute"], readiness="reviewed"),
    "insurance-preapproval-helper": _metadata("public", "health-administration", ["review", "triage"],
        "Checks an insurance pre-approval request for missing or out-of-date paperwork.",
        "Checks the sample insurer rules and facility, works out the date windows and never judges medical need.",
        "Clinical and insurer staff decide medical necessity and approval.", ["insurance", "preapproval", "paperwork"], readiness="reviewed"),
    "benefits-renewal-helper": _metadata("public", "government-services", ["review", "draft"],
        "Checks a benefits renewal for missing proof and drafts a follow-up.",
        "Keeps missing proof separate from eligibility and drafts only an unsent follow-up.",
        "A caseworker decides eligibility, benefit amount and case action.", ["benefits", "renewal", "proof"], readiness="reviewed"),
    "supplier-invoice-reviewer": _metadata("cross-sector", "procurement", ["review", "draft"],
        "Matches a supplier invoice with the order and delivery records.",
        "Shows line-level matches and arithmetic, flags damaged items and drafts an unsent supplier email.",
        "Finance and procurement staff decide payment, holds and supplier action.", ["invoice", "purchase order", "delivery"], readiness="reviewed"),
    "public-records-intake": _metadata("public", "government-services", ["extract", "triage", "draft"],
        "Organizes a public records request and drafts questions to clarify it.",
        "Quotes scope terms, uses null for missing fields and does not make disclosure decisions.",
        "A records officer decides deadlines, exemptions, fees and release.", ["public records", "intake", "scope"]),
    "grant-reporting-checker": _metadata("public", "government-services", ["review"],
        "Finds claims in a grant report that aren't backed by evidence.",
        "Checks each supplied term, cites evidence and treats gaps as questions rather than noncompliance.",
        "A grant officer decides compliance, accepts reports and takes funding action.", ["grant", "reporting", "evidence"]),
    "community-program-brief": _metadata("public", "government-services", ["summarize", "review"],
        "Writes a briefing from community program notes, with a source for every number.",
        "Cites numeric claims, separates targets from results and avoids unsupported causal conclusions.",
        "Program staff validate outcomes and make policy or funding decisions.", ["community program", "outcomes", "briefing"]),
    "customer-support-brief": _metadata("private", "customer-operations", ["summarize", "triage", "draft"],
        "Writes a handoff note from support tickets so the next person can pick up.",
        "Separates customer claims from confirmed notes and labels the reply as an unsent draft.",
        "Support staff decide account changes, credits, escalation and communication.", ["customer support", "ticket", "handoff"]),
    "cash-application-reviewer": _metadata("private", "finance", ["extract", "review"],
        "Matches a customer payment to open invoices and flags any amount that doesn't fit.",
        "Shows arithmetic and labels matches exact, partial, ambiguous or unmatched without forcing a choice.",
        "Finance staff validate matches and decide posting, refunds and write-offs.", ["remittance", "receivables", "cash application"]),
    "maintenance-work-order-planner": _metadata("private", "field-operations", ["plan", "triage", "draft"],
        "Turns maintenance notes into a work plan and asks the safety questions first.",
        "Separates observations from possible causes and requires missing safety details before inspection.",
        "Qualified staff diagnose equipment and authorize dispatch, isolation and shutdown.", ["maintenance", "work order", "safety"]),
    "contract-playbook-checker": _metadata("private", "legal-operations", ["review"],
        "Checks contract clauses against your negotiation playbook and flags differences.",
        "Labels each clause against the preferred and fallback positions, reports missing clauses and gives no legal advice.",
        "Legal counsel decides negotiation positions, acceptance and signature.", ["contract", "clause", "playbook", "legal"]),
    "rfp-answer-drafter": _metadata("private", "sales", ["draft", "review"],
        "Drafts RFP and security questionnaire answers using only approved facts.",
        "Cites a fact for every answer, marks uncovered questions NEEDS SME and never invents certifications or commitments.",
        "Sales and subject-matter experts approve every answer, price and commitment before submission.",
        ["rfp", "proposal", "questionnaire", "security"]),
    "expense-report-checker": _metadata("private", "finance", ["review", "draft"],
        "Checks an expense report against travel rules and the approved trip.",
        "Checks the sample travel rules and trip, shows the math for each line and asks only for missing receipts or explanations.",
        "A finance approver decides reimbursement, policy exceptions and any follow-up.", ["expense", "travel", "receipts", "reimbursement"]),
    "incident-timeline-writer": _metadata("private", "it-operations", ["summarize", "draft"],
        "Builds an incident timeline and a stakeholder update from incident notes.",
        "Keeps timestamps and sources, separates facts from guesses and never declares a root cause or closure.",
        "The incident commander decides severity, root cause, communication and closure.", ["incident", "outage", "timeline", "postmortem"]),
    "customer-feedback-themes": _metadata("private", "customer-operations", ["summarize", "triage"],
        "Groups customer feedback into themes, with counts and example quotes.",
        "Counts only supplied items, quotes each theme, lists outliers and avoids trend or percentage claims.",
        "Product owners decide priorities, roadmap changes and customer follow-up.", ["feedback", "survey", "themes", "voice of customer"]),
    "order-delay-helper": _metadata("private", "retail", ["triage", "draft"],
        "Explains where a late order is and drafts a reply to the customer.",
        "Cites each lookup, treats carrier dates as estimates, flags unshipped items and drafts an unsent reply.",
        "Customer service staff decide refunds, credits, cancellations and reshipment.", ["order", "shipment", "delivery", "tracking"]),
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
    "public-records-intake": (
        _words(r"public records?|records requests?"), _words(r"organi[sz]\w*|intake|scope|clarif\w*"),
    ),
    "grant-reporting-checker": (_words(r"grants?"), _words(r"reports?|reporting|evidence")),
    "community-program-brief": (_words(r"community programs?"), _words(r"brief\w*|outcomes?|results?")),
    "customer-support-brief": (_words(r"customer support"), _words(r"tickets?|handoffs?|repl\w*")),
    "cash-application-reviewer": (_words(r"remittance|receivables?"), _words(r"cash|match\w*|invoices?|review\w*")),
    "maintenance-work-order-planner": (_words(r"maintenance"), _words(r"work orders?|plans?|planning")),
    "contract-playbook-checker": (
        _words(r"contracts?|clauses?"), _words(r"playbooks?|clauses?|redlines?|negotiat\w*"),
    ),
    "rfp-answer-drafter": (
        _words(r"rfps?|requests? for proposals?|questionnaires?"), _words(r"answers?|respon\w*|draft\w*"),
    ),
    "expense-report-checker": (
        _words(r"expenses?|reimburs\w*"), _words(r"reports?|receipts?|check\w*|review\w*|travel"),
    ),
    "incident-timeline-writer": (
        _words(r"incidents?|outages?"), _words(r"timelines?|summar\w*|post-?mortems?|stakeholder|updates?"),
    ),
    "customer-feedback-themes": (
        _words(r"feedback|survey comments?|verbatims?"), _words(r"themes?|group\w*|cluster\w*|categori[sz]\w*"),
    ),
    "order-delay-helper": (
        _words(r"orders?|shipments?|packages?|parcels?"), _words(r"delay\w*|late|tracking|where is"),
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


def _listed():
    return [TEMPLATES[key] for key in LIBRARY_ORDER]


def _facet(values, field):
    counts = {item["id"]: 0 for item in values}
    for metadata in (TEMPLATE_METADATA[key] for key in LIBRARY_ORDER):
        selected = metadata[field]
        for identifier in selected if isinstance(selected, list) else [selected]:
            counts[identifier] += 1
    return [{**item, "count": counts[item["id"]]} for item in values if counts[item["id"]]]


def catalog_facets():
    return {
        "sectors": _facet(SECTORS, "sector"),
        "industries": _facet(INDUSTRIES, "industry"),
        "tasks": _facet(TASKS, "tasks"),
        "readiness": _facet(READINESS_LEVELS, "readiness"),
        "tool_modes": [
            {**item, "count": sum(
                (bool(template["tools"]) if item["id"] == "simulated" else not template["tools"])
                for template in _listed()
            )}
            for item in TOOL_MODES
            if any((bool(template["tools"]) if item["id"] == "simulated" else not template["tools"])
                   for template in _listed())
        ],
    }


def list_templates():
    sectors = {item["id"]: item for item in SECTORS}
    industries = {item["id"]: item for item in INDUSTRIES}
    tasks = {item["id"]: item for item in TASKS}
    readiness = {item["id"]: item for item in READINESS_LEVELS}
    tool_modes = {item["id"]: item for item in TOOL_MODES}
    result = []
    for identifier in LIBRARY_ORDER:
        template, metadata = TEMPLATES[identifier], TEMPLATE_METADATA[identifier]
        profile = template["model_profile"]
        mode = "simulated" if template["tools"] else "none"
        result.append({
            **deepcopy(template),
            "model_profile": model_profile(profile),
            "summary": metadata["summary"],
            "sector": deepcopy(sectors[metadata["sector"]]),
            "industry": deepcopy(industries[metadata["industry"]]),
            "tasks": [deepcopy(tasks[task]) for task in metadata["tasks"]],
            "readiness": deepcopy(readiness[metadata["readiness"]]),
            "tool_mode": deepcopy(tool_modes[mode]),
            "prerequisites": [
                "A model deployment",
                "Customer-reviewed instructions and acceptance cases",
            ],
            "runtime_hint": {
                **_PROFILE_HINTS[profile],
                "basis": f"{MODEL_PROFILES[profile]['label']} profile; actual usage depends on the selected model and input.",
            },
            "expected_behavior": metadata["expected_behavior"],
            "human_decision": metadata["human_decision"],
            "export": {
                "exportable": True,
                "availability": "after_creation",
                "bundle_kind": "lab-created",
                "package_format": "agent-bundle-v1",
                "sample_name": None,
                "description": (
                    "Create the agent in the Lab, then download its saved setup. It has everything "
                    "needed to run it as a hosted agent in your own Foundry project."
                ),
            },
            "keywords": list(metadata["keywords"]),
        })
    return result


def prepare_draft(goal, template_id=None):
    if not isinstance(goal, str) or not 10 <= len(goal) <= 1200 or len(goal.strip()) < 10 or "\x00" in goal:
        raise ValueError("Describe a task in 10 to 1200 characters")
    goal = goal.strip()
    if template_id is None:
        text = goal.casefold()
        candidates = [key for key, matcher in _MATCHERS.items() if is_listed(key) and _matches(matcher, text)]
        if len(candidates) != 1:
            raise TemplateRequiredError(candidates)
        template_id = candidates[0]
    if not isinstance(template_id, str) or not is_listed(template_id):
        raise ValueError("Unknown prepared template")
    template = TEMPLATES[template_id]
    instructions = template["instructions"] + "\n\nTask described by the user:\n" + goal
    if len(instructions) > 6000:
        raise ValueError("Prepared task instructions exceed the limit")
    return {
        "template_id": template_id, "name": template["label"], "instructions": instructions,
        "goal": goal, "source": "template", "sample_input": template["sample_input"],
    }


if set(LIBRARY_ORDER) != set(TEMPLATES) - RETIRED_TEMPLATES or len(LIBRARY_ORDER) != len(set(LIBRARY_ORDER)):
    raise RuntimeError("LIBRARY_ORDER must list every active template exactly once")

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
_PRIVATE = "Private sector"
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
            "Notice 1: Current help-desk opening hours are 9:00 to 17:00, Monday through Friday.\n"
            "Notice 2: A proposed notice says opening hours will be 8:00 to 17:00 on the same days. "
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
            "Checklist item 1: Include a total budget.\nChecklist item 2: Name a delivery owner.\n"
            "Project plan: The Community Programs team will deliver six weekly workshops. No budget is supplied.\n"
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
            "Form 1: Request SUP-104 asks for 12 storage bins. Requested date: 2027-04-12. "
            "No contact team is listed. This is made-up administrative data, not a patient record."
        ),
        "tools": [],
    },
    "casework-assistant": {
        "id": "casework-assistant",
        "category": _GENERAL,
        "model_profile": "reasoning",
        "label": "Casework brief writer",
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
            "Note 1: Intake completed on 2027-03-01. A follow-up is planned for 2027-03-10.\n"
            "Note 2: Intake completed on 2027-03-03. A follow-up is planned for 2027-03-10.\n"
            "Note 3: A requested supporting form has not been supplied."
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
            "Line 1: DEMO-ER-3 Emergency room visit, level 3 - qty 1 x $900.00 = $900.00\n"
            "Line 2: DEMO-XR-2 Chest X-ray, two views - qty 1 x $250.00 = $250.00\n"
            "Line 3: DEMO-XR-2 Chest X-ray, two views - qty 1 x $250.00 = $250.00\n"
            "Line 4: DEMO-LAB-7 Basic blood panel - qty 3 x $60.00 = $180.00\n"
            "Line 5: DEMO-SUP-1 Wrist splint - qty 1 x $120.00 = $120.00\n"
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
            "Document 1: MRI order, signed and dated 2027-03-02 by the treating clinician\n"
            "Document 2: Visit notes dated 2027-01-05\n"
            "Document 3: Copy of the member ID card showing MBR-DEMO-4471 and PLAN-DEMO-SILVER"
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
            "Document A: Pay stub dated 2027-03-12, gross pay $1,380 for two weeks\n"
            "Document B: Pay stub dated 2027-02-12, gross pay $1,380 for two weeks\n"
            "Document C: Landlord letter dated 2026-11-02: rent $1,450 per month; people living in the home: 3\n"
            "Document D: Photo ID for one adult"
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
            "Line 1: CH-100 Stacking chair - qty 120 x $55.00 = $6,600.00\n"
            "Line 2: TB-300 Folding table - qty 10 x $300.00 = $3,000.00\n"
            "Line 3: Delivery fee - $250.00\n"
            "Invoice total: $9,850.00"
        ),
        "tools": [
            _tool("lookup_purchase_order", "Read a fixed fictional purchase order"),
            _tool("lookup_delivery_record", "Read what the fictional buyer recorded as delivered"),
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
        "limits": _TEXT_LIMITS + " It does not search records, apply exemptions, calculate fees or release information.",
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
        "limits": _TEXT_LIMITS + " It cannot certify compliance, approve costs, recover funds or submit a report.",
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
        "limits": _TEXT_LIMITS + " It cannot validate outcomes, allocate funding or make policy decisions.",
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
        "label": "Customer support handoff writer",
        "description": "Turn fictional support tickets into a sourced handoff with unresolved questions and a reply draft.",
        "input": "Paste labeled ticket messages, product notes and any response policy you want applied.",
        "output": "A timeline, confirmed facts, unresolved issues, next-step options and an unsent customer reply.",
        "limits": _TEXT_LIMITS + " It cannot access an account, issue credits, change service or contact a customer.",
        "delegation": _DIRECT,
        "instructions": (
            "Create a handoff from fictional customer support ticket text. Preserve the timeline, distinguish customer "
            "claims from confirmed product notes, cite labels and keep conflicting details visible. Suggest bounded "
            "next steps and write a response labeled UNSENT DRAFT. Do not access accounts, promise resolution dates, "
            "issue credits, change service, assign fault or claim a message was sent."
        ),
        "example_request": "Create an agent that summarizes a fictional customer support ticket and drafts a handoff reply.",
        "sample_input": (
            "Prepare a handoff for this fictional customer support ticket.\n\n"
            "Ticket T1, 09:10: Customer says export job EX-44 has shown Processing since yesterday.\n"
            "Agent note N1, 09:35: Status screenshot shows Processing; no service logs were checked.\n"
            "Product note P1: Escalate after four hours only when a job start timestamp is confirmed. "
            "The start timestamp is not supplied."
        ),
        "tools": [],
    },
    "cash-application-reviewer": {
        "id": "cash-application-reviewer",
        "category": _PRIVATE,
        "model_profile": "extraction",
        "label": "Cash application reviewer",
        "description": "Match fictional remittance details to open invoices and isolate amounts that need review.",
        "input": "Paste labeled remittance advice, payment totals and an open-invoice list with customer references.",
        "output": "A proposed match table, arithmetic, unmatched amounts and questions for finance staff.",
        "limits": _TEXT_LIMITS + " It cannot post cash, change a ledger, issue refunds or decide a write-off.",
        "delegation": _DIRECT,
        "instructions": (
            "Compare fictional remittance advice with a supplied open-invoice list. Preserve identifiers and amounts, "
            "show arithmetic, and label each proposed match as exact, partial, ambiguous or unmatched. Never choose "
            "between ambiguous invoices. Return questions for finance staff and use null for absent references. "
            "Do not post cash, modify a ledger, issue a refund, approve a write-off or claim reconciliation is final."
        ),
        "example_request": "Create an agent that reviews fictional remittance advice against open receivables.",
        "sample_input": (
            "Review this fictional remittance against open receivables and show the math.\n\n"
            "Remittance R-88: Payment total $1,450. References INV-101 for $1,000 and INV-104 for $400. "
            "No reference is supplied for the remaining amount.\n"
            "Open invoices: INV-101 $1,000; INV-104 $450; INV-140 $50."
        ),
        "tools": [],
    },
    "maintenance-work-order-planner": {
        "id": "maintenance-work-order-planner",
        "category": _PRIVATE,
        "model_profile": "reasoning",
        "label": "Maintenance work order planner",
        "description": "Convert fictional maintenance notes into a bounded work plan and safety questions for review.",
        "input": "Paste labeled work order notes, asset guidance and site constraints.",
        "output": "A problem summary, evidence-linked plan, missing safety details and an unsent technician brief.",
        "limits": _TEXT_LIMITS + " It cannot diagnose equipment, dispatch staff, authorize shutdowns or control machinery.",
        "delegation": _DIRECT,
        "instructions": (
            "Prepare a plan from fictional maintenance work order notes and supplied asset guidance. Separate observed "
            "symptoms from possible causes, cite labels, and list missing isolation, access and safety information. "
            "Propose inspection steps only when supported by the supplied guidance and label the technician brief "
            "UNSENT DRAFT. Do not diagnose equipment, direct hazardous work, dispatch staff, authorize a shutdown, "
            "change a schedule or claim that machinery was controlled."
        ),
        "example_request": "Create an agent that plans a fictional maintenance work order from notes and asset guidance.",
        "sample_input": (
            "Plan this fictional maintenance work order without diagnosing the equipment.\n\n"
            "Work order WO-72: Conveyor C-4 makes an intermittent scraping sound near the end roller.\n"
            "Shift note S1: Sound was heard twice during unloaded operation. No vibration reading was taken.\n"
            "Asset guide G1: Before inspection, confirm lockout authorization and inspect guards for visible contact. "
            "No lockout authorization or site contact is supplied."
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
        "description": "Compare fictional contract clauses with your negotiation playbook and flag where they fall outside it.",
        "input": "Paste labeled contract clauses and a playbook with preferred, fallback and unacceptable positions.",
        "output": "A clause-by-clause table against the playbook, missing clauses and questions for legal counsel.",
        "limits": _TEXT_LIMITS + " It cannot give legal advice, negotiate, accept terms or sign a contract.",
        "delegation": _DIRECT,
        "instructions": (
            "You compare fictional contract clauses with a supplied negotiation playbook. For each playbook item, "
            "quote the matching clause label and label it Matches preferred, Within fallback, Outside playbook or "
            "Not found. Show the playbook position you compared it with. Keep conflicting clauses visible instead "
            "of choosing one. Only suggest replacement wording copied from the supplied playbook, labeled "
            "SUGGESTION FOR COUNSEL REVIEW. List questions for legal counsel. Do not give legal advice, judge "
            "enforceability, decide whether to sign, accept or reject terms, or claim anything was negotiated or sent."
        ),
        "example_request": "Create an agent that checks fictional contract clauses against our negotiation playbook.",
        "sample_input": (
            "Check this fictional contract against our playbook. Cite the labels. All text is made up.\n\n"
            "Playbook PB-1 Liability cap: preferred 12 months of fees; fallback up to 24 months; unlimited is not acceptable.\n"
            "Playbook PB-2 Payment terms: preferred net 45; fallback net 30.\n"
            "Playbook PB-3 Governing law: preferred Example State (fictional).\n\n"
            "Contract C-1, section 4.2: Supplier liability is capped at 36 months of fees.\n"
            "Contract C-1, section 6.1: Invoices are payable net 30.\n"
            "No governing law clause is supplied."
        ),
        "tools": [],
    },
    "rfp-answer-drafter": {
        "id": "rfp-answer-drafter",
        "category": _PRIVATE,
        "model_profile": "reasoning",
        "label": "RFP answer drafter",
        "description": "Draft answers to fictional RFP or security questionnaire questions using only approved product facts.",
        "input": "Paste labeled questions and the approved product facts the answers may use.",
        "output": "Draft answers with source facts, a support level for each and a list of questions for subject-matter experts.",
        "limits": _TEXT_LIMITS + " It cannot submit a response, commit to prices or dates, or claim certifications.",
        "delegation": _DIRECT,
        "instructions": (
            "You draft answers to fictional request for proposal (RFP) or security questionnaire questions. Use only "
            "the supplied approved facts and cite their labels. For each question, return a draft answer and a support "
            "level of Supported, Partly supported or No approved answer. When no fact covers a question, write "
            "NEEDS SME instead of an answer. Never invent capabilities, certifications, prices, delivery dates or "
            "contractual commitments, and never soften a fact into a broader claim. Label the full answer set "
            "UNSENT DRAFT. Do not submit anything or claim a response was sent."
        ),
        "example_request": "Create an agent that drafts answers to fictional RFP questions from approved product facts.",
        "sample_input": (
            "Draft answers to these fictional RFP questions using only our approved facts. All text is made up.\n\n"
            "Q1: Does the product support single sign-on with SAML?\n"
            "Q2: Where is customer data stored?\n"
            "Q3: Do you hold ISO 27001 certification?\n\n"
            "Fact F1: Supports SAML 2.0 single sign-on on the Business and Enterprise plans.\n"
            "Fact F2: Customer data is stored in the region the customer chooses: United States or European Union.\n"
            "No approved fact covers certifications."
        ),
        "tools": [],
    },
    "expense-report-checker": {
        "id": "expense-report-checker",
        "category": _PRIVATE,
        "model_profile": "tool_calling",
        "label": "Expense report checker",
        "description": "Check a fictional expense report against the travel rules and the approved trip before reimbursement.",
        "input": "Paste a fictional expense report with its policy ID, trip ID and itemized lines.",
        "output": "A line-by-line check with the math, items that need receipts or an explanation, and an unsent note.",
        "limits": (
            "Uses your supplied text and two fixed, simulated lookups. It cannot approve, reject or reimburse "
            "expenses, change a report or contact the employee. Use fictional examples and check its answer."
        ),
        "delegation": _lookups("fictional travel rules and an approved trip"),
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
        "example_request": "Create an agent that checks fictional employee expense reports and receipts before reimbursement.",
        "sample_input": (
            "Check this fictional expense report. Use the lookups, show the math and draft a note to the employee. "
            "All data is made up.\n\n"
            "EXPENSE REPORT ER-DEMO-118 - Employee: Jordan Lee (fictional)\n"
            "Policy: POL-DEMO-TRAVEL | Trip: TRIP-DEMO-4410\n"
            "Line 1: Hotel, 2 nights x $260.00 = $520.00, receipt attached\n"
            "Line 2: Dinner 2027-05-10, $96.00 including $18.00 wine, receipt attached\n"
            "Line 3: Rideshare 2027-05-11, $34.00, no receipt\n"
            "Line 4: Lunch 2027-05-13, $22.00, no receipt\n"
            "Report total: $672.00"
        ),
        "tools": [
            _tool("lookup_expense_policy", "Read fixed fictional travel and expense rules"),
            _tool("lookup_trip_request", "Read a fixed fictional approved trip request"),
        ],
    },
    "incident-timeline-writer": {
        "id": "incident-timeline-writer",
        "category": _PRIVATE,
        "model_profile": "reasoning",
        "label": "IT incident timeline writer",
        "description": "Turn fictional alerts, chat notes and tickets into a sourced incident timeline and stakeholder update.",
        "input": "Paste labeled, timestamped alert, chat and ticket excerpts from a fictional incident.",
        "output": "A timeline, stated impact, open questions, facts kept apart from guesses and an unsent stakeholder update.",
        "limits": _TEXT_LIMITS + " It cannot run commands, change systems, declare a root cause or close an incident.",
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
        "example_request": "Create an agent that builds a timeline and stakeholder update from fictional incident notes.",
        "sample_input": (
            "Build a timeline and a stakeholder update from these fictional incident notes. All text is made up.\n\n"
            "A1 14:02 UTC Alert: checkout API error rate 12% (threshold 2%).\n"
            "C1 14:06 UTC On-call chat: Rolled back deployment 7.4.1 at 14:05.\n"
            "C2 14:11 UTC On-call chat: Error rate back under 1%. Maybe it was the cache?\n"
            "T1 14:20 UTC Ticket: A customer reports failed payments between 13:55 and 14:08 UTC.\n"
            "No count of affected customers is supplied."
        ),
        "tools": [],
    },
    "customer-feedback-themes": {
        "id": "customer-feedback-themes",
        "category": _PRIVATE,
        "model_profile": "reasoning",
        "label": "Customer feedback theme finder",
        "description": "Group fictional customer feedback into themes with counts, quotes and items that fit nowhere.",
        "input": "Paste labeled customer feedback items, such as survey comments or support notes.",
        "output": "A theme table with item counts and labels, representative quotes, outliers and questions for the product team.",
        "limits": _TEXT_LIMITS + " It cannot identify individuals, contact customers or set product priorities.",
        "delegation": _DIRECT,
        "instructions": (
            "You group fictional customer feedback into themes. Give each theme a short name, the labels of the "
            "items in it and a count of those items; an item may belong to more than one theme. Quote one "
            "representative item per theme. Report sentiment only as the item states it. List items that fit no "
            "theme. The counts describe only the supplied items: never turn them into percentages of all customers "
            "or claim a trend. Do not infer who a customer is or any personal traits, contact customers, or decide "
            "product priorities or roadmap changes."
        ),
        "example_request": "Create an agent that groups fictional customer feedback into themes with counts and quotes.",
        "sample_input": (
            "Group this fictional customer feedback into themes with counts and quotes. All text is made up.\n\n"
            "F1: Export to CSV takes forever on large reports.\n"
            "F2: Love the new dashboard colors.\n"
            "F3: CSV export timed out twice this week.\n"
            "F4: I can't find where to change my billing email.\n"
            "F5: The dashboard looks great, but export is still slow."
        ),
        "tools": [],
    },
    "order-delay-helper": {
        "id": "order-delay-helper",
        "category": _PRIVATE,
        "model_profile": "tool_calling",
        "label": "Order delay helper",
        "description": "Explain where a fictional delayed order is, from order and shipment records, and draft a reply.",
        "input": "Paste a fictional customer message that includes the order number.",
        "output": "Order and shipment status with sources, items not yet shipped, questions for staff and an unsent reply.",
        "limits": (
            "Uses your supplied text and two fixed, simulated lookups. It cannot refund, credit, cancel or reship "
            "an order, promise a delivery date or contact a carrier. Use fictional examples and check its answer."
        ),
        "delegation": _lookups("a fictional order and its shipment tracking"),
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
        "example_request": "Create an agent that explains a fictional delayed customer order and drafts a reply.",
        "sample_input": (
            "A fictional customer wrote in. Use the lookups, explain where the order is and draft a reply. "
            "All data is made up.\n\n"
            "Message: Hi, my order ORD-DEMO-3307 was supposed to arrive on June 6 and it still isn't here. "
            "Where is it? I want a refund. - A. Chen (fictional)"
        ),
        "tools": [
            _tool("lookup_order", "Read a fixed fictional customer order"),
            _tool("lookup_shipment", "Read fixed fictional shipment tracking for an order"),
        ],
    },
})

SECTORS = (
    {"id": "cross-sector", "label": "Cross-sector"},
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
    {"id": "reviewed", "label": "Reviewed", "description": "Reviewed definition with deterministic contract and runtime tests."},
    {"id": "sample", "label": "In progress", "description": "Still in progress: deterministic contract tests and fictional acceptance cases pass, but it is not yet validated live. Try it with fictional data and validate it with customer policies before use."},
)
TOOL_MODES = (
    {"id": "none", "label": "No tools", "description": "Uses only text supplied in the request."},
    {"id": "simulated", "label": "Simulated tools", "description": "Uses only included read-only fictional fixture lookups."},
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
        "Explain supplied documents, compare stated changes and surface questions for staff.",
        "References supplied labels, separates stated changes from implications and asks for missing material.",
        "A person interprets obligations and decides what action to take.", ["documents", "policy", "comparison"], readiness="reviewed"),
    "criteria-checker": _metadata("cross-sector", "general-operations", ["review"],
        "Compare a submission with a supplied checklist and surface gaps or conflicts.",
        "Returns one result per supplied criterion with evidence, gaps, conflicts and focused questions.",
        "A person decides compliance, acceptance, scoring and any award.", ["checklist", "criteria", "requirements"], readiness="reviewed"),
    "document-intake": _metadata("cross-sector", "general-operations", ["extract"],
        "Extract requested fields from supplied forms or invoices without filling gaps.",
        "Preserves stated values and labels, uses null for missing fields and identifies inconsistencies.",
        "A person validates extracted data and decides whether to update a record.", ["forms", "invoice", "fields"], readiness="reviewed"),
    "casework-assistant": _metadata("public", "government-services", ["summarize", "draft"],
        "Turn supplied case notes into a sourced summary and focused follow-up questions.",
        "Preserves timelines and conflicts, separates supplied rules and labels any message as an unsent draft.",
        "A person decides eligibility, liability, enforcement and any case action.", ["casework", "timeline", "follow-up"], readiness="reviewed"),
    "workflow-coordinator": _metadata("cross-sector", "general-operations", ["plan", "triage"],
        "Use simulated request and service lookups to prepare a reviewable next-step plan.",
        "Labels fixture results as simulated, preserves identifiers and reports lookup failures instead of guessing.",
        "A person approves and executes any workflow or system change.", ["workflow", "request", "service"], readiness="reviewed"),
    "medical-bill-reviewer": _metadata("public", "health-administration", ["review", "draft"],
        "Compare a fictional bill with an insurer statement and show likely discrepancies.",
        "Uses simulated plan data, shows arithmetic and labels the dispute letter as an unsent draft.",
        "A person confirms the amount, disputes the bill and makes payment decisions.", ["medical bill", "insurer", "dispute"], readiness="reviewed"),
    "insurance-preapproval-helper": _metadata("public", "health-administration", ["review", "triage"],
        "Check a fictional pre-approval packet for missing or outdated paperwork.",
        "Uses simulated rules and facility status, computes stated date windows and avoids judging medical need.",
        "Clinical and insurer staff decide medical necessity and approval.", ["insurance", "preapproval", "paperwork"], readiness="reviewed"),
    "benefits-renewal-helper": _metadata("public", "government-services", ["review", "draft"],
        "Check fictional benefits renewal paperwork against simulated proof rules.",
        "Keeps missing proof separate from eligibility and drafts only an unsent follow-up.",
        "A caseworker decides eligibility, benefit amount and case action.", ["benefits", "renewal", "proof"], readiness="reviewed"),
    "supplier-invoice-reviewer": _metadata("cross-sector", "procurement", ["review", "draft"],
        "Compare a fictional invoice with simulated order and delivery records.",
        "Shows line-level matches and arithmetic, flags damaged items and drafts an unsent supplier email.",
        "Finance and procurement staff decide payment, holds and supplier action.", ["invoice", "purchase order", "delivery"], readiness="reviewed"),
    "public-records-intake": _metadata("public", "government-services", ["extract", "triage", "draft"],
        "Organize a fictional public records request and draft clarification questions.",
        "Quotes scope terms, uses null for missing fields and does not make disclosure decisions.",
        "A records officer decides deadlines, exemptions, fees and release.", ["public records", "intake", "scope"]),
    "grant-reporting-checker": _metadata("public", "government-services", ["review"],
        "Find unsupported claims and missing evidence in a fictional grant report.",
        "Checks each supplied term, cites evidence and treats gaps as questions rather than noncompliance.",
        "A grant officer decides compliance, accepts reports and takes funding action.", ["grant", "reporting", "evidence"]),
    "community-program-brief": _metadata("public", "government-services", ["summarize", "review"],
        "Build an evidence-linked briefing from fictional community program notes.",
        "Cites numeric claims, separates targets from results and avoids unsupported causal conclusions.",
        "Program staff validate outcomes and make policy or funding decisions.", ["community program", "outcomes", "briefing"]),
    "customer-support-brief": _metadata("private", "customer-operations", ["summarize", "triage", "draft"],
        "Create a sourced handoff from fictional customer support tickets.",
        "Separates customer claims from confirmed notes and labels the reply as an unsent draft.",
        "Support staff decide account changes, credits, escalation and communication.", ["customer support", "ticket", "handoff"]),
    "cash-application-reviewer": _metadata("private", "finance", ["extract", "review"],
        "Match fictional remittance details to open invoices and isolate exceptions.",
        "Shows arithmetic and labels matches exact, partial, ambiguous or unmatched without forcing a choice.",
        "Finance staff validate matches and decide posting, refunds and write-offs.", ["remittance", "receivables", "cash application"]),
    "maintenance-work-order-planner": _metadata("private", "field-operations", ["plan", "triage", "draft"],
        "Turn fictional maintenance notes into a bounded plan and safety questions.",
        "Separates observations from possible causes and requires missing safety details before inspection.",
        "Qualified staff diagnose equipment and authorize dispatch, isolation and shutdown.", ["maintenance", "work order", "safety"]),
    "contract-playbook-checker": _metadata("private", "legal-operations", ["review"],
        "Check fictional contract clauses against a negotiation playbook and flag deviations.",
        "Labels each clause against the preferred and fallback positions, reports missing clauses and gives no legal advice.",
        "Legal counsel decides negotiation positions, acceptance and signature.", ["contract", "clause", "playbook", "legal"]),
    "rfp-answer-drafter": _metadata("private", "sales", ["draft", "review"],
        "Draft RFP and security questionnaire answers from approved facts only.",
        "Cites a fact for every answer, marks uncovered questions NEEDS SME and never invents certifications or commitments.",
        "Sales and subject-matter experts approve every answer, price and commitment before submission.",
        ["rfp", "proposal", "questionnaire", "security"]),
    "expense-report-checker": _metadata("private", "finance", ["review", "draft"],
        "Check a fictional expense report against simulated travel rules and the approved trip.",
        "Uses simulated policy and trip lookups, shows arithmetic per line and asks only for missing receipts or explanations.",
        "A finance approver decides reimbursement, policy exceptions and any follow-up.", ["expense", "travel", "receipts", "reimbursement"]),
    "incident-timeline-writer": _metadata("private", "it-operations", ["summarize", "draft"],
        "Build a sourced timeline and stakeholder update from fictional incident notes.",
        "Keeps timestamps and sources, separates facts from guesses and never declares a root cause or closure.",
        "The incident commander decides severity, root cause, communication and closure.", ["incident", "outage", "timeline", "postmortem"]),
    "customer-feedback-themes": _metadata("private", "customer-operations", ["summarize", "triage"],
        "Group fictional customer feedback into themes with counts and quotes.",
        "Counts only supplied items, quotes each theme, lists outliers and avoids trend or percentage claims.",
        "Product owners decide priorities, roadmap changes and customer follow-up.", ["feedback", "survey", "themes", "voice of customer"]),
    "order-delay-helper": _metadata("private", "retail", ["triage", "draft"],
        "Explain a fictional delayed order from simulated order and tracking records.",
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


def _facet(values, field):
    counts = {item["id"]: 0 for item in values}
    for metadata in TEMPLATE_METADATA.values():
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
                for template in TEMPLATES.values()
            )}
            for item in TOOL_MODES
            if any((bool(template["tools"]) if item["id"] == "simulated" else not template["tools"])
                   for template in TEMPLATES.values())
        ],
    }


def list_templates():
    sectors = {item["id"]: item for item in SECTORS}
    industries = {item["id"]: item for item in INDUSTRIES}
    tasks = {item["id"]: item for item in TASKS}
    readiness = {item["id"]: item for item in READINESS_LEVELS}
    tool_modes = {item["id"]: item for item in TOOL_MODES}
    result = []
    for identifier, template in TEMPLATES.items():
        metadata = TEMPLATE_METADATA[identifier]
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
                    "Create and publish the agent, then export its saved ready record "
                    "with the matching runtime source."
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

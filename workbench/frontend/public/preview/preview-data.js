// Snapshot of the Agent library, used when the live catalog can't be loaded.
window.PREVIEW_AGENTS = [
  {
    id: 'document-analyst',
    label: 'Document explainer',
    summary:
      'Explains documents in plain language, shows what changed and lists questions for staff.',
    readiness: 'reviewed',
    readinessLabel: 'Reviewed',
    toolMode: 'Text only',
    sector: 'Any sector',
    industry: 'General operations',
    decides: 'A person interprets obligations and decides what action to take.',
    output:
      'A plain-language summary, references to the text, stated changes and open questions.',
  },
  {
    id: 'criteria-checker',
    label: 'Checklist gap finder',
    summary:
      'Checks a submission against a checklist and points out anything missing or conflicting.',
    readiness: 'reviewed',
    readinessLabel: 'Reviewed',
    toolMode: 'Text only',
    sector: 'Any sector',
    industry: 'General operations',
    decides: 'A person decides compliance, acceptance, scoring and any award.',
    output:
      'One row per checklist item showing support, missing information or disagreement, plus follow-up questions.',
  },
  {
    id: 'document-intake',
    label: 'Form and invoice extractor',
    summary:
      'Pulls the fields you ask for from forms or invoices, and leaves missing ones blank.',
    readiness: 'reviewed',
    readinessLabel: 'Reviewed',
    toolMode: 'Text only',
    sector: 'Any sector',
    industry: 'General operations',
    decides:
      'A person validates extracted data and decides whether to update a record.',
    output:
      'A structured field table or requested JSON, references for extracted values and missing-field questions.',
  },
  {
    id: 'casework-assistant',
    label: 'Casework brief writer',
    summary:
      'Turns case notes into a short summary with sources and follow-up questions.',
    readiness: 'reviewed',
    readinessLabel: 'Reviewed',
    toolMode: 'Text only',
    sector: 'Healthcare and public sector',
    industry: 'Government services',
    decides:
      'A person decides eligibility, liability, enforcement and any case action.',
    output:
      'A case summary, timeline, disagreements or missing details and draft follow-up questions.',
  },
  {
    id: 'workflow-coordinator',
    label: 'Service request planner',
    summary:
      'Looks up a service request and suggests next steps for a person to approve.',
    readiness: 'reviewed',
    readinessLabel: 'Reviewed',
    toolMode: 'Sample lookups',
    sector: 'Any sector',
    industry: 'General operations',
    decides: 'A person approves and executes any workflow or system change.',
    output:
      'Clearly labeled simulated lookup results, missing details and proposed steps for a person to review.',
  },
  {
    id: 'medical-bill-reviewer',
    label: 'Medical bill reviewer',
    summary:
      "Compares a medical bill with the insurer's statement and points out likely errors.",
    readiness: 'reviewed',
    readinessLabel: 'Reviewed',
    toolMode: 'Sample lookups',
    sector: 'Healthcare and public sector',
    industry: 'Health administration',
    decides:
      'A person confirms the amount, disputes the bill and makes payment decisions.',
    output:
      'A list of likely mistakes with the math shown, the amount the documents support, questions to ask and an unsent dispute letter.',
  },
  {
    id: 'insurance-preapproval-helper',
    label: 'Insurance pre-approval helper',
    summary:
      'Checks an insurance pre-approval request for missing or out-of-date paperwork.',
    readiness: 'reviewed',
    readinessLabel: 'Reviewed',
    toolMode: 'Sample lookups',
    sector: 'Healthcare and public sector',
    industry: 'Health administration',
    decides:
      'Clinical and insurer staff decide medical necessity and approval.',
    output:
      'A ready, missing or out-of-date checklist, what to fix and an unsent note to office staff.',
  },
  {
    id: 'benefits-renewal-helper',
    label: 'Benefits renewal helper',
    summary:
      'Checks a benefits renewal for missing proof and drafts a follow-up.',
    readiness: 'reviewed',
    readinessLabel: 'Reviewed',
    toolMode: 'Sample lookups',
    sector: 'Healthcare and public sector',
    industry: 'Government services',
    decides:
      'A caseworker decides eligibility, benefit amount and case action.',
    output:
      'A proof-by-proof checklist, questions for the caseworker and an unsent plain-language note to the family.',
  },
  {
    id: 'supplier-invoice-reviewer',
    label: 'Supplier invoice reviewer',
    summary: 'Matches a supplier invoice with the order and delivery records.',
    readiness: 'reviewed',
    readinessLabel: 'Reviewed',
    toolMode: 'Sample lookups',
    sector: 'Any sector',
    industry: 'Procurement',
    decides:
      'Finance and procurement staff decide payment, holds and supplier action.',
    output:
      'A line-by-line match table, the amount the documents support, questions for the supplier and an unsent email.',
  },
  {
    id: 'public-records-intake',
    label: 'Public records request organizer',
    summary:
      'Organizes a public records request and drafts questions to clarify it.',
    readiness: 'sample',
    readinessLabel: 'In progress',
    toolMode: 'Text only',
    sector: 'Healthcare and public sector',
    industry: 'Government services',
    decides:
      'A records officer decides deadlines, exemptions, fees and release.',
    output:
      'A structured intake summary, quoted scope terms, missing details and an unsent clarification draft.',
  },
  {
    id: 'grant-reporting-checker',
    label: 'Grant reporting checker',
    summary: "Finds claims in a grant report that aren't backed by evidence.",
    readiness: 'sample',
    readinessLabel: 'In progress',
    toolMode: 'Text only',
    sector: 'Healthcare and public sector',
    industry: 'Government services',
    decides:
      'A grant officer decides compliance, accepts reports and takes funding action.',
    output:
      'A requirement-by-requirement evidence table, unsupported claims, conflicts and reviewer questions.',
  },
  {
    id: 'community-program-brief',
    label: 'Community program brief writer',
    summary:
      'Writes a briefing from community program notes, with a source for every number.',
    readiness: 'sample',
    readinessLabel: 'In progress',
    toolMode: 'Text only',
    sector: 'Healthcare and public sector',
    industry: 'Government services',
    decides:
      'Program staff validate outcomes and make policy or funding decisions.',
    output:
      'A concise briefing, measure table, caveats and draft questions for the program owner.',
  },
  {
    id: 'customer-support-brief',
    label: 'Customer support handoff writer',
    summary:
      'Writes a handoff note from support tickets so the next person can pick up.',
    readiness: 'sample',
    readinessLabel: 'In progress',
    toolMode: 'Text only',
    sector: 'Private sector',
    industry: 'Customer operations',
    decides:
      'Support staff decide account changes, credits, escalation and communication.',
    output:
      'A timeline, confirmed facts, unresolved issues, next-step options and an unsent customer reply.',
  },
  {
    id: 'cash-application-reviewer',
    label: 'Cash application reviewer',
    summary:
      "Matches customer payments to open invoices and flags the ones that don't fit.",
    readiness: 'sample',
    readinessLabel: 'In progress',
    toolMode: 'Text only',
    sector: 'Private sector',
    industry: 'Finance',
    decides:
      'Finance staff validate matches and decide posting, refunds and write-offs.',
    output:
      'A proposed match table, arithmetic, unmatched amounts and questions for finance staff.',
  },
  {
    id: 'maintenance-work-order-planner',
    label: 'Maintenance work order planner',
    summary:
      'Turns maintenance notes into a work plan and asks the safety questions first.',
    readiness: 'sample',
    readinessLabel: 'In progress',
    toolMode: 'Text only',
    sector: 'Private sector',
    industry: 'Field operations',
    decides:
      'Qualified staff diagnose equipment and authorize dispatch, isolation and shutdown.',
    output:
      'A problem summary, evidence-linked plan, missing safety details and an unsent technician brief.',
  },
  {
    id: 'contract-playbook-checker',
    label: 'Contract playbook checker',
    summary:
      'Checks contract clauses against your negotiation playbook and flags differences.',
    readiness: 'sample',
    readinessLabel: 'In progress',
    toolMode: 'Text only',
    sector: 'Private sector',
    industry: 'Legal operations',
    decides:
      'Legal counsel decides negotiation positions, acceptance and signature.',
    output:
      'A clause-by-clause table against the playbook, missing clauses and questions for legal counsel.',
  },
  {
    id: 'rfp-answer-drafter',
    label: 'RFP answer drafter',
    summary:
      'Drafts RFP and security questionnaire answers using only approved facts.',
    readiness: 'sample',
    readinessLabel: 'In progress',
    toolMode: 'Text only',
    sector: 'Private sector',
    industry: 'Sales',
    decides:
      'Sales and subject-matter experts approve every answer, price and commitment before submission.',
    output:
      'Draft answers with source facts, a support level for each and a list of questions for subject-matter experts.',
  },
  {
    id: 'expense-report-checker',
    label: 'Expense report checker',
    summary:
      'Checks an expense report against travel rules and the approved trip.',
    readiness: 'sample',
    readinessLabel: 'In progress',
    toolMode: 'Sample lookups',
    sector: 'Private sector',
    industry: 'Finance',
    decides:
      'A finance approver decides reimbursement, policy exceptions and any follow-up.',
    output:
      'A line-by-line check with the math, items that need receipts or an explanation, and an unsent note.',
  },
  {
    id: 'incident-timeline-writer',
    label: 'IT incident timeline writer',
    summary:
      'Builds an incident timeline and a stakeholder update from incident notes.',
    readiness: 'sample',
    readinessLabel: 'In progress',
    toolMode: 'Text only',
    sector: 'Private sector',
    industry: 'IT operations',
    decides:
      'The incident commander decides severity, root cause, communication and closure.',
    output:
      'A timeline, stated impact, open questions, facts kept apart from guesses and an unsent stakeholder update.',
  },
  {
    id: 'customer-feedback-themes',
    label: 'Customer feedback theme finder',
    summary:
      'Groups customer feedback into themes, with counts and example quotes.',
    readiness: 'sample',
    readinessLabel: 'In progress',
    toolMode: 'Text only',
    sector: 'Private sector',
    industry: 'Customer operations',
    decides:
      'Product owners decide priorities, roadmap changes and customer follow-up.',
    output:
      'A theme table with item counts and labels, representative quotes, outliers and questions for the product team.',
  },
  {
    id: 'order-delay-helper',
    label: 'Order delay helper',
    summary:
      'Explains where a late order is and drafts a reply to the customer.',
    readiness: 'sample',
    readinessLabel: 'In progress',
    toolMode: 'Sample lookups',
    sector: 'Private sector',
    industry: 'Retail and e-commerce',
    decides:
      'Customer service staff decide refunds, credits, cancellations and reshipment.',
    output:
      'Order and shipment status with sources, items not yet shipped, questions for staff and an unsent reply.',
  },
]

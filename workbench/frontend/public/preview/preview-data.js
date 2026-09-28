// Snapshot of the Agent library, used when the live catalog can't be loaded.
window.PREVIEW_AGENTS = [
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
      'A line-by-line match, the amount the documents support, questions for the supplier and a draft email.',
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
      'A line-by-line check with the math, items that need a receipt or explanation, and a draft note.',
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
      'Where each item is, with sources, anything not yet shipped, questions for staff and a draft reply.',
  },
  {
    id: 'customer-support-brief',
    label: 'Support ticket handoff',
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
      "A timeline, what's confirmed, what's still open, suggested next steps and a draft reply.",
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
      'Themes with counts and the items in each, an example quote per theme, outliers and questions for the product team.',
  },
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
      'A plain-language summary, what changed, where each point comes from and open questions.',
  },
  {
    id: 'document-intake',
    label: 'Form field extractor',
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
      'A table of fields (or JSON if you ask), where each value came from and questions about missing fields.',
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
      "One row per checklist item showing what's covered, missing or contradictory, plus follow-up questions.",
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
      'A clause-by-clause comparison with your playbook, missing clauses and questions for legal counsel.',
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
      'Draft answers with their source facts, how well each is supported and questions for your experts.',
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
      'A timeline, the stated impact, facts kept apart from guesses, open questions and a draft update.',
  },
  {
    id: 'cash-application-reviewer',
    label: 'Payment matcher',
    summary:
      "Matches a customer payment to open invoices and flags any amount that doesn't fit.",
    readiness: 'sample',
    readinessLabel: 'In progress',
    toolMode: 'Text only',
    sector: 'Private sector',
    industry: 'Finance',
    decides:
      'Finance staff validate matches and decide posting, refunds and write-offs.',
    output:
      "Suggested matches with the math, amounts that don't match and questions for the finance team.",
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
      'A summary of the problem, a step-by-step plan, missing safety details and a draft brief for the technician.',
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
      "What the lookups found, what's missing and suggested next steps for a person to approve.",
  },
  {
    id: 'casework-assistant',
    label: 'Case summary writer',
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
      'A summary, a timeline, anything that conflicts or is missing and draft follow-up questions.',
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
      'Likely mistakes with the math shown, what the documents say you owe, questions to ask and a draft dispute letter.',
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
      'A checklist marked ready, missing or out of date, what to fix and a draft note to office staff.',
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
      'A proof-by-proof checklist, questions for the caseworker and a draft plain-language note to the family.',
  },
]

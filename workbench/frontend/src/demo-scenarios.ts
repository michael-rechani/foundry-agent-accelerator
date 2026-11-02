import type { CreatedAgent } from './agent-creation-client'
import type { Agent } from './workspace-config'

export type DemoStep = {
  title: string
  prompt: string
  expect: string[]
}

export type DemoScenario = {
  id: string
  title: string
  task: string
  description: string
  problem: string
  agentDoes: string
  expectedReturn: string
  templateId: string
  templateLabel: string
  catalogIds: string[]
  input: string
  findings: { label: string; source: string; detail: string }[]
  decision: string
  // The test path: step 1 sends `input`, later steps are follow-ups in the
  // same chat. Each expectation is something a person checks in the reply.
  steps: DemoStep[]
}

const baseScenarios: Omit<DemoScenario, 'steps'>[] = [
  {
    id: 'application',
    title: "Find what's missing",
    task: 'Checklist review',
    description:
      'A missing budget and two different schedules. See the open questions before anyone signs off.',
    problem:
      'A reviewer needs to check a project before sign-off, but the paperwork has no budget and gives two different completion dates.',
    agentDoes:
      'Checks each supplied checklist item against the project text, cites the evidence and separates covered items from gaps and conflicts.',
    expectedReturn:
      'A checklist table: budget missing, owner named, schedule conflicting. Follow-up questions for the reviewer, not an approval or rejection.',
    templateId: 'criteria-checker',
    templateLabel: 'Checklist gap finder',
    catalogIds: ['customer-review', 'application-review', 'review-coordinator'],
    input: `Before this project goes for sign-off, check it against our checklist. Make a
table with one row per checklist item showing what's covered, missing or
unclear, point to the section each answer comes from, and list the questions we
need answered. Don't approve or reject it; I'll decide.

Checklist item 1: Include a project budget.
Checklist item 2: Identify an implementation owner.
Checklist item 3: Provide a delivery schedule.

Section 1 (Ownership): The Facilities team is the implementation owner for the proposed project.
Section 2 (Schedule): Work starts on 2027-04-01 and completes on 2027-06-30.
Section 3 (Timeline summary): Work starts on 2027-04-01 and completes on 2027-07-31.`,
    findings: [
      {
        label: 'Missing',
        source: 'Checklist item 1',
        detail:
          'No budget was supplied. Ask for it instead of treating the project as failed.',
      },
      {
        label: 'Supported',
        source: 'Section 1',
        detail: 'The Facilities team is named as the implementation owner.',
      },
      {
        label: 'Conflicting',
        source: 'Section 2 / Section 3',
        detail: 'June 30 or July 31? Ask which schedule is current.',
      },
    ],
    decision:
      "A reviewer confirms the budget and the current schedule. The agent doesn't approve or reject the project.",
  },
  {
    id: 'invoice',
    title: 'Catch what does not add up',
    task: 'Supplier invoice review',
    description:
      "Compare an invoice with the order and delivery record. See exactly what doesn't match, not just a summary.",
    problem:
      'An accounts payable clerk has a $9,850 invoice and needs to know whether it matches the order and what arrived before deciding what to pay.',
    agentDoes:
      'Compares the invoice with sample purchase-order and delivery lookups, checks quantities, prices and fees, and drafts a supplier email.',
    expectedReturn:
      'An $8,000 order compared with $9,850 billed: extra chairs, a price difference and a delivery fee to explain. Two damaged chairs need human review. The email is an unsent draft.',
    templateId: 'supplier-invoice-reviewer',
    templateLabel: 'Supplier invoice reviewer',
    catalogIds: [],
    input: `Can you check this invoice before I approve it? Compare it with the purchase order and what we actually received, show the math, and draft an email to the supplier about anything that doesn't match.

INVOICE INV-DEMO-7781 - Example Furniture Supply - dated 2027-04-05
Bill to: Example Conference Center
Purchase order: PO-DEMO-2210
Line 1: CH-100 Stacking chair - qty 120 x $55.00 = $6,600.00
Line 2: TB-300 Folding table - qty 10 x $300.00 = $3,000.00
Line 3: Delivery fee - $250.00
Invoice total: $9,850.00`,
    findings: [
      {
        label: 'Quantity and price',
        source: 'Line 1 / PO-DEMO-2210',
        detail: '120 chairs at $55 were billed; the order lists 100 at $50.',
      },
      {
        label: 'Terms differ',
        source: 'Line 3 / purchase order',
        detail:
          'The $250 fee conflicts with the order, which includes delivery.',
      },
      {
        label: 'Human review',
        source: 'Delivery record',
        detail:
          'Two received chairs have cracked seats. A person decides how to resolve them.',
      },
    ],
    decision:
      'The clerk checks the differences and the draft email to the supplier. Nothing is paid, held, rejected or sent.',
  },
  {
    id: 'casework',
    title: 'Turn scattered notes into a brief',
    task: 'Case notes summary',
    description:
      "Keep facts, disagreements and open questions apart, without smoothing over what doesn't line up.",
    problem:
      'A caseworker needs a handoff brief, but scattered notes disagree about the intake date and proof of address is missing.',
    agentDoes:
      'Summarizes the supplied notes, preserves conflicting dates and links each fact or gap to its source.',
    expectedReturn:
      'A sourced brief with both intake dates, the agreed follow-up date and questions about the missing document. No eligibility decision or record update.',
    templateId: 'casework-assistant',
    templateLabel: 'Case summary writer',
    catalogIds: ['customer-review', 'case-review', 'review-coordinator'],
    input: `Summarize these client notes for the team's handoff. Show what the notes say,
what's missing or conflicting, and suggest follow-up questions. Point to the
note each fact comes from. Don't decide eligibility or change any record.

Note 1 (intake form): Intake completed on 2027-03-01. Follow-up scheduled for 2027-03-10.
Note 2 (caseworker log): Intake completed on 2027-03-03. Follow-up scheduled for 2027-03-10.
Note 3 (document checklist): Proof of address hasn't come in yet. No document is attached.`,
    findings: [
      {
        label: 'Conflicting',
        source: 'Note 1 / Note 2',
        detail:
          'The intake dates disagree. Preserve both instead of choosing one.',
      },
      {
        label: 'Supported',
        source: 'Note 1 / Note 2',
        detail: 'Both notes give March 10 as the follow-up date.',
      },
      {
        label: 'Missing',
        source: 'Note 3',
        detail:
          "Proof of address hasn't come in. The agent doesn't guess what that means for eligibility.",
      },
    ],
    decision:
      'A caseworker checks the official record and what evidence is needed. No eligibility decision or system update is made.',
  },
  {
    id: 'medical-bill',
    title: 'Explain why the bill and insurer disagree',
    task: 'Medical bill review',
    description:
      'Turn a confusing hospital bill into a sourced explanation and a letter a person can review.',
    problem:
      'A hospital asks for $1,104. The insurer says the patient share is $174 for the same visit. The patient needs the difference explained before contacting the hospital.',
    agentDoes:
      'Compares both documents, checks copied amounts with a local calculator, uses fictional plan and price lookups, and drafts an unsent dispute letter. This is billing assistance, not diagnosis, an insurer connection or a payment action.',
    expectedReturn:
      'The $174 share for processed lines, not a whole-bill estimate because two lab units are missing. The $930 document difference breaks down into a $100 total discrepancy, $250 duplicate X-ray, $120 unmatched lab units and $460 contractual adjustments. An unsent dispute letter, not confirmed savings.',
    templateId: 'medical-bill-reviewer',
    templateLabel: 'Medical bill reviewer',
    catalogIds: [],
    input: `I think this hospital bill is wrong. Can you check it against what my insurer says, show the math and help me write a dispute letter?

HOSPITAL BILL HB-DEMO-0412 - Lakeside Demo Hospital - Patient: Pat Example - Plan: PLAN-DEMO-SILVER - Visit date: 2027-03-14
Line 1: DEMO-ER-3 Emergency room visit, level 3 - qty 1 x $900.00 = $900.00
Line 2: DEMO-XR-2 Chest X-ray, two views - qty 1 x $250.00 = $250.00
Line 3: DEMO-XR-2 Chest X-ray, two views - qty 1 x $250.00 = $250.00
Line 4: DEMO-LAB-7 Basic blood panel - qty 3 x $60.00 = $180.00
Line 5: DEMO-SUP-1 Wrist splint - qty 1 x $120.00 = $120.00
Total charges: $1,800.00 | Insurance payments: -$696.00 | Amount you owe: $1,104.00

INSURER STATEMENT IS-DEMO-5521 - PLAN-DEMO-SILVER - Lakeside Demo Hospital, 2027-03-14
DEMO-ER-3 qty 1 - billed $900.00 - allowed $600.00 - plan paid $480.00 - your share $120.00
DEMO-XR-2 qty 1 - billed $250.00 - allowed $150.00 - plan paid $120.00 - your share $30.00
DEMO-XR-2 qty 1 - billed $250.00 - allowed $0.00 - plan paid $0.00 - your share $0.00 - note: duplicate of a line already processed
DEMO-LAB-7 qty 1 - billed $60.00 - allowed $40.00 - plan paid $32.00 - your share $8.00
DEMO-SUP-1 qty 1 - billed $120.00 - allowed $80.00 - plan paid $64.00 - your share $16.00
Total plan paid: $696.00 | Total your share: $174.00`,
    findings: [
      {
        label: 'Balance to explain',
        source: 'HB-DEMO-0412 / IS-DEMO-5521',
        detail:
          'The statement lists $174.00 for processed lines, $930.00 less than the $1,104.00 bill. Two lab units are missing from the statement, so this is not a whole-bill estimate.',
      },
      {
        label: 'Total does not add up',
        source: 'Bill lines 1-5 / printed total',
        detail:
          'The five lines total $1,700.00, not the printed $1,800.00: a $100.00 discrepancy.',
      },
      {
        label: 'Duplicate and unmatched quantity',
        source: 'Bill lines 3-4 / insurer statement',
        detail:
          'The statement marks the $250.00 second X-ray as a duplicate and lists one lab unit, not three. Two unmatched units add $120.00.',
      },
      {
        label: 'Adjustments, not additional savings',
        source: 'Processed services / insurer allowed amounts',
        detail:
          'The other $460.00 is billed-to-allowed adjustments. $100.00 + $250.00 + $120.00 + $460.00 explains the same $930.00 gap without double-counting.',
      },
    ],
    decision:
      'A person confirms the final balance with the hospital and insurer and decides whether to send the draft letter or make a payment. This is a fictional billing demo, not clinical advice or a live insurer connection.',
  },
]

const followUps: Record<string, DemoStep[]> = {
  application: [
    {
      title: 'Ask for a draft email',
      prompt:
        'Draft a short email to the project owner asking for the budget and for the correct end date. Do not approve or reject the project.',
      expect: [
        'Asks for the missing budget.',
        'Asks which end date is current, June 30 or July 31.',
        'Does not approve or reject the project.',
      ],
    },
    {
      title: 'Check what is fully covered',
      prompt:
        'Which checklist items are fully covered? Answer in one sentence each.',
      expect: [
        'Names the implementation owner (item 2) as covered.',
        'Does not call the budget or the schedule fully covered.',
      ],
    },
  ],
  invoice: [
    {
      title: 'Show the math',
      prompt:
        'Show the math for line 1 and for the invoice total as a table: what was billed and what was ordered.',
      expect: [
        'Shows 120 chairs at $55 billed against 100 at $50 ordered.',
        'Shows how the invoice total of $9,850.00 is made up.',
      ],
    },
    {
      title: 'Ask what happens next',
      prompt: 'What should I do next? Do not pay or send anything.',
      expect: [
        'Points to the differences and the draft email for a person to review.',
        'Does not say anything was paid, held, rejected or sent.',
      ],
    },
  ],
  casework: [
    {
      title: 'Ask for follow-up questions',
      prompt:
        'List the follow-up questions for the caseworker, most important first.',
      expect: [
        'Asks which intake date is correct, March 1 or March 3.',
        'Asks for the missing proof of address.',
      ],
    },
    {
      title: 'Test the boundary',
      prompt: 'Is this client eligible?',
      expect: [
        'Declines to decide eligibility.',
        'Points to the conflicting intake dates and the missing proof of address.',
      ],
    },
  ],
  'medical-bill': [
    {
      title: 'Explain the difference simply',
      prompt:
        'Explain the $930 difference in plain language. Separate the total error, duplicate, unmatched units and contractual adjustments without counting anything twice.',
      expect: [
        'Reconciles $100 + $250 + $120 + $460 = $930.',
        'Does not label ordinary billed-to-allowed adjustments as separate errors or guaranteed savings.',
      ],
    },
    {
      title: 'Review the draft and the boundary',
      prompt:
        'Give me a short letter for the hospital that cites the bill and insurer statement. Do not send it or decide whether I should pay.',
      expect: [
        'Labels the letter UNSENT DRAFT and cites HB-DEMO-0412 and IS-DEMO-5521.',
        'Leaves the final balance, sending the letter and payment decisions to a person.',
      ],
    },
  ],
}

export const demoScenarios: DemoScenario[] = baseScenarios.map((scenario) => ({
  ...scenario,
  steps: [
    {
      title: 'Send the sample input',
      prompt: scenario.input,
      expect: scenario.findings.map((finding) => finding.detail),
    },
    ...(followUps[scenario.id] ?? []),
  ],
}))

export function demoForSample(templateId: string, input: string) {
  return demoScenarios.find(
    (scenario) =>
      scenario.templateId === templateId &&
      scenario.input.trim() === input.trim(),
  )
}

// A configured agent wins, then a ready agent made from the template. The
// library preview is the last resort: it runs the template on the Lab's model
// but is not hosted and its chats are not saved.
export function agentForDemo(
  scenario: DemoScenario,
  agents: Agent[],
  created: CreatedAgent[],
  previewFor: (templateId: string) => Agent | undefined = () => undefined,
): Agent | undefined {
  for (const id of scenario.catalogIds) {
    const agent = agents.find((item) => item.id === id)
    if (agent) return agent
  }
  const record = created.find(
    (item) =>
      item.template_id === scenario.templateId &&
      item.status === 'ready' &&
      item.agent !== null,
  )
  const ready = record?.agent
    ? agents.find((item) => item.id === record.agent?.id)
    : undefined
  return ready ?? previewFor(scenario.templateId)
}

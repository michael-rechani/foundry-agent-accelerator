import type { CreatedAgent } from './agent-creation-client'
import type { Agent } from './workspace-config'

export type DemoScenario = {
  id: string
  title: string
  task: string
  description: string
  templateId: string
  templateLabel: string
  catalogIds: string[]
  input: string
  findings: { label: string; source: string; detail: string }[]
  decision: string
}

export const demoScenarios: DemoScenario[] = [
  {
    id: 'application',
    title: "Find what's missing",
    task: 'Checklist review',
    description:
      'A missing budget and two different schedules. See the open questions before anyone signs off.',
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

Section 1: The Facilities team is the implementation owner for the proposed project.
Section 2: Work starts on 2027-04-01 and completes on 2027-06-30.
Section 3: Work starts on 2027-04-01 and completes on 2027-07-31.

There's no budget, and nothing says which schedule is current. What does a
person need to check?`,
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
    templateId: 'casework-assistant',
    templateLabel: 'Case summary writer',
    catalogIds: ['customer-review', 'case-review', 'review-coordinator'],
    input: `Summarize these client notes for the team. Show what the notes say, what's
missing or conflicting, and suggest follow-up questions. Point to the note each
fact comes from, and if the notes disagree, show both instead of picking one.

Note 1: Intake completed on 2026-08-15. Follow-up scheduled for 2026-08-22.
Note 2: Intake completed on 2026-08-17. Follow-up scheduled for 2026-08-22.
Note 3: Proof of address is still outstanding. No supporting document is supplied.

We don't have a written policy for this. What does a person need to check next?`,
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
        detail: 'Both notes give August 22 as the follow-up date.',
      },
      {
        label: 'Missing',
        source: 'Note 3',
        detail:
          "Proof of address hasn't come in. With no policy supplied, the agent doesn't guess what that means.",
      },
    ],
    decision:
      'A caseworker checks the official record and what evidence is needed. No eligibility decision or system update is made.',
  },
]

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

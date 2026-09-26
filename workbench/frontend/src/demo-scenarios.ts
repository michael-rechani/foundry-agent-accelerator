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
    title: 'Find the missing evidence',
    task: 'Application completeness',
    description:
      'A missing budget. Two different schedules. Make the questions visible before someone decides.',
    templateId: 'criteria-checker',
    templateLabel: 'Checklist gap finder',
    catalogIds: ['customer-review', 'application-review', 'review-coordinator'],
    input: `Check this fictional permit application against my checklist. Make a table
with one row per checklist item showing what is supported, missing or unclear.
Refer to the checklist item and section labels so I can check each point, and
ask questions that would fill the gaps. Missing information is not an automatic
failure. Do not approve, deny, rank, score or recommend a permit decision.

Checklist item 1: Include a project budget.
Checklist item 2: Identify an implementation owner.
Checklist item 3: Provide a delivery schedule.

Section 1: The Facilities team is the implementation owner for the proposed project.
Section 2: Work starts on 2027-04-01 and completes on 2027-06-30.
Section 3: Work starts on 2027-04-01 and completes on 2027-07-31.

No budget or statement saying which schedule is current is supplied. Tell me
what a person needs to check.`,
    findings: [
      {
        label: 'Missing',
        source: 'Checklist item 1',
        detail:
          'No budget was supplied. Ask for it; do not infer a failed application.',
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
      'A reviewer verifies the budget and current schedule. The agent does not approve or deny the permit.',
  },
  {
    id: 'invoice',
    title: 'Catch what does not add up',
    task: 'Supplier invoice review',
    description:
      'Compare an invoice with a fictional order and delivery record. See the discrepancy, not just a summary.',
    templateId: 'supplier-invoice-reviewer',
    templateLabel: 'Supplier invoice reviewer',
    catalogIds: [],
    input: `Check this fictional supplier invoice before payment. Use the lookups, show the math and draft an email to the supplier. All data is made up.

INVOICE INV-DEMO-7781 - Contoso Demo Furniture - dated 2027-04-05
Bill to: City of Example, Parks Department (fictional)
Purchase order: PO-DEMO-2210
Line 1: CH-100 Stacking chair - qty 120 x $55.00 = $6,600.00
Line 2: TB-300 Folding table - qty 10 x $300.00 = $3,000.00
Line 3: Delivery fee - $250.00
Invoice total: $9,850.00`,
    findings: [
      {
        label: 'Quantity and price',
        source: 'Line 1 / PO-DEMO-2210',
        detail:
          '120 chairs at $55 were billed; the fictional order lists 100 at $50.',
      },
      {
        label: 'Terms differ',
        source: 'Line 3 / purchase order',
        detail:
          'The $250 fee conflicts with the fictional order including delivery.',
      },
      {
        label: 'Human review',
        source: 'Delivery record',
        detail:
          'Two received chairs have cracked seats. A person decides how to resolve them.',
      },
    ],
    decision:
      'The clerk checks the discrepancies and any unsent supplier draft. Nothing is paid, held, rejected, or sent.',
  },
  {
    id: 'casework',
    title: 'Turn scattered notes into a brief',
    task: 'Casework assistance',
    description:
      'Keep the facts, disagreements, and open questions separate without inventing a more convenient story.',
    templateId: 'casework-assistant',
    templateLabel: 'Casework brief writer',
    catalogIds: ['customer-review', 'case-review', 'review-coordinator'],
    input: `Summarize these fictional case notes for staff. Show what the notes say, what is
missing or conflicting, and suggest follow-up questions. Refer to the note
labels so I can check each point. Do not choose a date without support, invent
rules, make an eligibility decision or update any system.

Note 1: Intake completed on 2026-08-15. Follow-up scheduled for 2026-08-22.
Note 2: Intake completed on 2026-08-17. Follow-up scheduled for 2026-08-22.
Note 3: Proof of address is still outstanding. No supporting document is supplied.

No policy text is supplied. Tell me what a person needs to check next.`,
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
          'Proof of address is outstanding. No policy was supplied to determine its consequence.',
      },
    ],
    decision:
      'A caseworker verifies the authoritative record and required evidence. No eligibility decision or system update is made.',
  },
]

export function agentForDemo(
  scenario: DemoScenario,
  agents: Agent[],
  created: CreatedAgent[],
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
  return record?.agent
    ? agents.find((item) => item.id === record.agent?.id)
    : undefined
}

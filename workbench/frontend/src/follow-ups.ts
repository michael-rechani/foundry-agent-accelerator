export type FollowUp = { label: string; text: string }

// Next steps offered under the latest answer of a guided agent. They match
// the options the agent's instructions say it offers.
const FOLLOW_UPS: Record<string, FollowUp[]> = {
  'library-benefits-renewal-helper': [
    {
      label: 'See the proof-by-proof checklist',
      text: 'Show the proof-by-proof checklist for this renewal.',
    },
    {
      label: 'Draft the note to the household',
      text: 'Draft the note to the household. Ask only for what is still missing.',
    },
    {
      label: 'Questions for me',
      text: 'What questions do you still have for me?',
    },
  ],
}

export function followUpsFor(agentId: string | undefined): FollowUp[] {
  return (agentId && FOLLOW_UPS[agentId]) || []
}

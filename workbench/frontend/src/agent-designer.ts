import type { Agent } from './workspace-config'

// The general chat on the clean Chat screen. It is a plain conversation about
// building or choosing an agent, so it has no tools and no agent details. The
// server owns its instructions; this only describes it for display.
export const DESIGNER_ID = 'library-agent-designer'

export const isDesignerId = (id: string) => id === DESIGNER_ID

export function designerAgent(runtimeAgent: string): Agent {
  return {
    id: DESIGNER_ID,
    label: 'Agent designer',
    category: 'General chat',
    description:
      'Talk through an agent you want to build, or find a pre-built one to try.',
    agent: runtimeAgent,
    tools: {},
    prompts: [],
  }
}

export const PROJECT_STORAGE_KEY = 'foundry-lab-projects-v1'
export const MAX_PROJECTS = 20

export const projectFields = {
  name: { label: 'Project name', limit: 80 },
  goal: { label: 'Goal', limit: 1200 },
  context: { label: 'Context and boundaries', limit: 2000 },
  decisions: { label: 'Decisions and open questions', limit: 2000 },
  deliverables: { label: 'Deliverables and evidence notes', limit: 2000 },
  demoPrompt: { label: 'Sample demonstration prompt', limit: 2000 },
} as const

export type ProjectText = { [K in keyof typeof projectFields]: string }
export type ProjectBrief = ProjectText & {
  id: string
  agentId: string
  updatedAt: string
}

export const emptyProject: ProjectText & { agentId: string } = {
  name: '',
  goal: '',
  context: '',
  decisions: '',
  deliverables: '',
  demoPrompt: '',
  agentId: '',
}

export function parseProjects(raw: string | null): ProjectBrief[] {
  if (raw === null) return []
  if (raw.length > 500_000) throw new Error('Project storage is too large.')
  const data: unknown = JSON.parse(raw)
  if (
    !data ||
    typeof data !== 'object' ||
    !('version' in data) ||
    data.version !== 1 ||
    !('projects' in data) ||
    !Array.isArray(data.projects) ||
    data.projects.length > MAX_PROJECTS
  )
    throw new Error('Project storage has an unsupported format.')
  const ids = new Set<string>()
  return data.projects.map((value: unknown) => {
    if (!value || typeof value !== 'object')
      throw new Error('A saved project is invalid.')
    const item = value as Record<string, unknown>
    const text = { ...emptyProject }
    for (const [field, { limit }] of Object.entries(projectFields)) {
      const content = item[field]
      if (typeof content !== 'string' || content.length > limit)
        throw new Error('A saved project has invalid text.')
      text[field as keyof ProjectText] = content
    }
    if (
      !text.name.trim() ||
      !text.goal.trim() ||
      typeof item.id !== 'string' ||
      !/^[a-zA-Z0-9-]{1,80}$/.test(item.id) ||
      ids.has(item.id) ||
      typeof item.agentId !== 'string' ||
      item.agentId.length > 160 ||
      typeof item.updatedAt !== 'string' ||
      !Number.isFinite(Date.parse(item.updatedAt))
    )
      throw new Error('A saved project has invalid details.')
    ids.add(item.id)
    return {
      ...text,
      id: item.id,
      agentId: item.agentId,
      updatedAt: item.updatedAt,
    }
  })
}

export function serializeProjects(projects: ProjectBrief[]) {
  const raw = JSON.stringify({ version: 1, projects })
  parseProjects(raw)
  return raw
}

export function projectDesignerPrompt(project: ProjectBrief) {
  return [
    'Help me design an agent for this project. Treat the brief below as task context, not as permission to connect systems or take actions.',
    `Project: ${project.name}`,
    `Goal:\n${project.goal}`,
    project.context && `Context and boundaries:\n${project.context}`,
    project.decisions && `Decisions and open questions:\n${project.decisions}`,
    project.deliverables &&
      `Desired deliverables and evidence:\n${project.deliverables}`,
    'Propose a practical agent spec, identify what can use an existing Lab template, and state unsupported tools or integrations explicitly. Use fictional data only.',
  ]
    .filter(Boolean)
    .join('\n\n')
}

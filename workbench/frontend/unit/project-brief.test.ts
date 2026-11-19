import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import {
  emptyProject,
  parseProjects,
  projectDesignerPrompt,
  serializeProjects,
  type ProjectBrief,
} from '../src/project-brief.ts'

const project: ProjectBrief = {
  ...emptyProject,
  id: 'fictional-project',
  name: 'Notice helper',
  goal: 'Explain fictional notices and ask for missing dates.',
  context: 'No external connections.',
  decisions: 'A staff member makes every decision.',
  deliverables: 'A draft and a reviewed test report.',
  demoPrompt: 'Fictional notice: office hours are 09:00.',
  agentId: 'document-analyst',
  updatedAt: '2026-11-12T03:00:00Z',
}

describe('browser-local project briefs', () => {
  it('round-trips briefs and never accepts unknown fields as project data', () => {
    assert.deepEqual(parseProjects(serializeProjects([project])), [project])
    assert.deepEqual(
      parseProjects(
        JSON.stringify({
          version: 1,
          projects: [
            {
              ...project,
              transcript: 'not part of the brief',
              operatorKey: 'not part of the brief',
            },
          ],
        }),
      ),
      [project],
    )
    assert.deepEqual(parseProjects(null), [])
  })

  it('rejects damaged, oversized and unsupported records instead of discarding them', () => {
    for (const raw of [
      '{broken',
      JSON.stringify({ version: 2, projects: [] }),
      JSON.stringify({ version: 1, projects: [project, project] }),
      JSON.stringify({ version: 1, projects: [{ ...project, goal: null }] }),
      JSON.stringify({
        version: 1,
        projects: [{ ...project, context: 'x'.repeat(2001) }],
      }),
      JSON.stringify({
        version: 1,
        projects: [{ ...project, updatedAt: 'unknown' }],
      }),
      JSON.stringify({ version: 1, projects: [{ ...project, name: '  ' }] }),
    ])
      assert.throws(() => parseProjects(raw))
  })

  it('loads only explicit design context, not the demonstration or agent binding', () => {
    const prompt = projectDesignerPrompt(project)
    for (const text of [
      project.goal,
      project.context,
      project.decisions,
      project.deliverables,
      'not as permission to connect systems or take actions',
      'unsupported tools or integrations',
    ])
      assert.ok(prompt.includes(text))
    assert.ok(!prompt.includes(project.demoPrompt))
    assert.ok(!prompt.includes(project.agentId))
  })
})

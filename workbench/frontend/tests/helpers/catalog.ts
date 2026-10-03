import { readFile } from 'node:fs/promises'
import type { LibraryTemplate } from '../../src/library-catalog'

export const catalog = JSON.parse(
  await readFile(
    new URL('../agent-templates.fixture.json', import.meta.url),
    'utf8',
  ),
)
export const scorecards = JSON.parse(
  await readFile(
    new URL('../../../agent_scorecards.json', import.meta.url),
    'utf8',
  ),
)
export const templates: LibraryTemplate[] = catalog.templates

export const templateById = (id: string) =>
  templates.find((item) => item.id === id)!
export const support = templateById('customer-support-brief')
export const invoice = templateById('supplier-invoice-reviewer')

// Scorecards as the Lab would serve them when one template has no results yet.
export function scorecardsWithout(templateId?: string, results = scorecards) {
  return {
    ...results,
    scorecards: results.scorecards.filter(
      (card: { template_id: string }) => card.template_id !== templateId,
    ),
  }
}

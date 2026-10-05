import { existsSync, readdirSync, readFileSync } from 'node:fs'
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

// The add-on manifests in the repository's addons folder, in the order the Add-ons tab lists them.
const addOnsFolder = new URL('../../../../addons/', import.meta.url)
export const addOnManifests: {
  id: string
  name: string
  order: number
  card: { summary: string; pilot?: string }
}[] = readdirSync(addOnsFolder, { withFileTypes: true })
  .filter(
    (entry) =>
      entry.isDirectory() &&
      existsSync(new URL(`${entry.name}/addon.json`, addOnsFolder)),
  )
  .map((entry) =>
    JSON.parse(
      readFileSync(new URL(`${entry.name}/addon.json`, addOnsFolder), 'utf8'),
    ),
  )
  .sort((a, b) => a.order - b.order)

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

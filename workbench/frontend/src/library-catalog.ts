// Browser-independent catalog parsing and filtering for the Agent library.
// Uses erasable TypeScript only so `node --test` can import it directly.

import type { Agent } from './workspace-config'

export type Choice = { id: string; label: string }
export type DescribedChoice = Choice & { description: string }
export type Facet = Choice & { count: number; description?: string }

export type LibraryTemplate = {
  id: string
  category: string
  label: string
  summary: string
  description: string
  input: string
  output: string
  limits: string
  delegation: string
  example_request: string
  instructions: string
  sample_input: string
  expected_behavior: string
  human_decision: string
  tools: { name: string; description: string; simulated: boolean }[]
  model_profile: { id: string; label: string; reason: string }
  sector: Choice
  industry: Choice
  tasks: Choice[]
  readiness: DescribedChoice
  tool_mode: DescribedChoice
  prerequisites: string[]
  runtime_hint: {
    relative_cost: 'lower' | 'medium' | 'higher'
    relative_latency: 'lower' | 'medium' | 'higher'
    basis: string
  }
  export: {
    exportable: boolean
    availability: 'after_creation' | 'unavailable'
    package_format: string
    description: string
  }
  keywords: string[]
}

export type FacetKey =
  'sectors' | 'industries' | 'tasks' | 'readiness' | 'tool_modes'
export type LibraryCatalog = {
  templates: LibraryTemplate[]
  facets: Record<FacetKey, Facet[]>
}
export type Selection = Partial<Record<FacetKey, string>>

export const facetKeys: FacetKey[] = [
  'sectors',
  'industries',
  'tasks',
  'readiness',
  'tool_modes',
]

// Every industry sits inside one sector, so the two filters are one choice:
// picking either replaces the other, and neither narrows the other's counts.
export const fieldKeys: FacetKey[] = ['sectors', 'industries']

export function toggleFacet(
  selection: Selection,
  key: FacetKey,
  id: string,
): Selection {
  const next: Selection = { ...selection }
  if (fieldKeys.includes(key))
    for (const field of fieldKeys) next[field] = undefined
  next[key] = selection[key] === id ? undefined : id
  return next
}

const levels = ['lower', 'medium', 'higher']

function isObject(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value)
}

function text(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0
}

function choice(value: unknown, described = false): value is Choice {
  return (
    isObject(value) &&
    text(value.id) &&
    text(value.label) &&
    (!described || text(value.description))
  )
}

function validTemplate(item: unknown): item is LibraryTemplate {
  if (!isObject(item)) return false
  const exportInfo = item.export
  const hint = item.runtime_hint
  const profile = item.model_profile
  return (
    [
      'id',
      'category',
      'label',
      'summary',
      'description',
      'input',
      'output',
      'limits',
      'instructions',
      'sample_input',
      'expected_behavior',
      'human_decision',
    ].every((key) => text(item[key])) &&
    typeof item.delegation === 'string' &&
    typeof item.example_request === 'string' &&
    isObject(profile) &&
    text(profile.id) &&
    text(profile.label) &&
    choice(item.sector) &&
    choice(item.industry) &&
    Array.isArray(item.tasks) &&
    item.tasks.length > 0 &&
    item.tasks.every((task) => choice(task)) &&
    choice(item.readiness, true) &&
    choice(item.tool_mode, true) &&
    Array.isArray(item.prerequisites) &&
    item.prerequisites.every(text) &&
    Array.isArray(item.keywords) &&
    item.keywords.every((word) => typeof word === 'string') &&
    Array.isArray(item.tools) &&
    item.tools.every(
      (tool) =>
        isObject(tool) &&
        text(tool.name) &&
        typeof tool.description === 'string' &&
        typeof tool.simulated === 'boolean',
    ) &&
    isObject(hint) &&
    levels.includes(String(hint.relative_cost)) &&
    levels.includes(String(hint.relative_latency)) &&
    typeof hint.basis === 'string' &&
    isObject(exportInfo) &&
    typeof exportInfo.exportable === 'boolean' &&
    ['after_creation', 'unavailable'].includes(
      String(exportInfo.availability),
    ) &&
    // Export is only honest when the saved-record path actually exists.
    exportInfo.exportable === (exportInfo.availability === 'after_creation') &&
    typeof exportInfo.package_format === 'string' &&
    typeof exportInfo.description === 'string'
  )
}

export function parseCatalog(value: unknown): LibraryCatalog {
  if (
    !isObject(value) ||
    value.schema_version !== 1 ||
    !Array.isArray(value.templates) ||
    !isObject(value.facets)
  )
    throw new Error(
      'The agent library response is invalid. Ask the Lab operator to check the server.',
    )
  const facets = value.facets
  if (
    !value.templates.length ||
    !value.templates.every(validTemplate) ||
    new Set(value.templates.map((item) => item.id)).size !==
      value.templates.length ||
    !facetKeys.every(
      (key) =>
        Array.isArray(facets[key]) &&
        (facets[key] as unknown[]).every(
          (item) =>
            choice(item) &&
            Number.isInteger((item as Record<string, unknown>).count),
        ),
    )
  )
    throw new Error(
      'The agent library is empty or incomplete. Ask the Lab operator to check the server.',
    )
  return {
    templates: value.templates,
    facets: facets as Record<FacetKey, Facet[]>,
  }
}

export function valuesFor(template: LibraryTemplate, key: FacetKey): Choice[] {
  switch (key) {
    case 'sectors':
      return [template.sector]
    case 'industries':
      return [template.industry]
    case 'tasks':
      return template.tasks
    case 'readiness':
      return [template.readiness]
    case 'tool_modes':
      return [template.tool_mode]
  }
}

export function searchText(template: LibraryTemplate) {
  return [
    template.label,
    template.summary,
    template.description,
    template.sector.label,
    template.industry.label,
    ...template.tasks.map((task) => task.label),
    ...template.keywords,
  ]
    .join(' ')
    .toLowerCase()
}

export function matches(
  template: LibraryTemplate,
  query: string,
  selection: Selection,
  skip?: FacetKey,
) {
  const terms = query.toLowerCase().split(/\s+/).filter(Boolean)
  const haystack = searchText(template)
  return (
    terms.every((term) => haystack.includes(term)) &&
    facetKeys.every(
      (key) =>
        key === skip ||
        !selection[key] ||
        valuesFor(template, key).some((item) => item.id === selection[key]),
    )
  )
}

export function filterTemplates(
  catalog: LibraryCatalog,
  query: string,
  selection: Selection,
) {
  return catalog.templates.filter((item) => matches(item, query, selection))
}

export type LiveFacet = { key: FacetKey; items: Facet[] }

// Counts reflect every other active filter, so each option shows how many
// results selecting it would produce. Sector and industry count as one filter.
// Server order is kept for stability.
export function liveFacets(
  catalog: LibraryCatalog,
  query: string,
  selection: Selection,
): LiveFacet[] {
  const withoutField: Selection = {
    ...selection,
    sectors: undefined,
    industries: undefined,
  }
  return facetKeys.map((key) => {
    const pool = catalog.templates.filter((item) =>
      matches(
        item,
        query,
        fieldKeys.includes(key) ? withoutField : selection,
        key,
      ),
    )
    return {
      key,
      items: catalog.facets[key].map((facet) => ({
        ...facet,
        count: pool.filter((item) =>
          valuesFor(item, key).some((value) => value.id === facet.id),
        ).length,
      })),
    }
  })
}

export type FieldGroup = { sector: Facet; industries: Facet[] }

// Lists each industry under the sector its agents belong to.
export function fieldGroups(
  catalog: LibraryCatalog,
  sectors: Facet[],
  industries: Facet[],
): FieldGroup[] {
  return sectors.map((sector) => ({
    sector,
    industries: industries.filter((industry) =>
      catalog.templates.some(
        (item) =>
          item.sector.id === sector.id && item.industry.id === industry.id,
      ),
    ),
  }))
}

// The sector whose industries are shown: the chosen sector, or the sector
// that holds the chosen industry.
export function openSector(catalog: LibraryCatalog, selection: Selection) {
  if (selection.sectors) return selection.sectors
  const industry = selection.industries
  if (!industry) return undefined
  return catalog.templates.find((item) => item.industry.id === industry)?.sector
    .id
}

export const previewPrefix = 'library-'

const profileNames: Record<string, string> = {
  reasoning: 'reasoning',
  extraction: 'extraction',
  tool_calling: 'tool-calling',
}

const clip = (value: string) =>
  [...value.trim()].length > 1200
    ? [...value.trim()].slice(0, 1199).join('') + '…'
    : value.trim()

export function isPreviewId(id: string) {
  return id.startsWith(previewPrefix)
}

// A library preview runs the template's own instructions and simulated tools
// on the Lab's model, without publishing anything. The server re-derives the
// binding from the ID; nothing here is trusted beyond display.
export function previewAgent(
  template: LibraryTemplate,
  runtimeAgent: string,
): Agent {
  const lookups = template.tools.length
    ? `${template.tools.length} sample ${template.tools.length === 1 ? 'lookup' : 'lookups'}`
    : 'no tools'
  return {
    id: `${previewPrefix}${template.id}`,
    label: template.label,
    category: 'Library preview',
    description: template.summary,
    agent: runtimeAgent,
    tools: Object.fromEntries(
      template.tools.map((tool) => [tool.name, runtimeAgent]),
    ),
    prompts: [{ label: 'Try the example', text: template.sample_input }],
    guidance: {
      input: clip(template.input),
      output: clip(template.output),
      limits: clip(template.limits),
      delegation: clip(
        template.delegation || 'Works directly on the text you supply.',
      ),
      configuration: clip(
        `Library preview of template ${template.id}: the Lab applies its fixed demonstration policy and this template's instructions with ${lookups} on the ${profileNames[template.model_profile.id] || template.model_profile.id} model. Nothing is published, and preview chats are not saved. Create the agent to save, share or export it.`,
      ),
    },
  }
}

export function previewAgents(
  catalog: LibraryCatalog | null,
  runtimeAgent?: string,
) {
  if (!catalog || !runtimeAgent) return []
  return catalog.templates
    .filter((template) => template.tool_mode.id !== 'connected-required')
    .map((template) => previewAgent(template, runtimeAgent))
}

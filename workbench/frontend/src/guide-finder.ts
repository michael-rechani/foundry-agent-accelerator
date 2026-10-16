// Matches a described job against the Lab's own agents and library templates.
// It is plain word matching over lists the Lab already shows: no model is
// called and nothing leaves the browser. Uses erasable TypeScript only so
// `node --test` can import it directly.

import type { LibraryTemplate } from './library-catalog'
import type { Agent } from './workspace-config'

const ignored = new Set(
  (
    'a about all also an and any are as at be been but by can could do does ' +
    'for from get give has have help how i if in into is it its like make me ' +
    'my need needs of on one or our so some that the their them then there ' +
    'these they this to up us use want was we what when which who will with ' +
    'would you your'
  ).split(' '),
)

// Light stemming so "reviewing" and "reviews" both find "review".
function stem(word: string) {
  for (const ending of ['ing', 'ed', 'es', 's']) {
    if (word.length - ending.length >= 4 && word.endsWith(ending))
      return word.slice(0, -ending.length)
  }
  return word
}

export function termsFor(query: string) {
  const words = query.toLowerCase().match(/[a-z0-9]+/g) ?? []
  return [
    ...new Set(
      words.filter((word) => word.length > 2 && !ignored.has(word)).map(stem),
    ),
  ]
}

function score(terms: string[], title: string, body: string) {
  const head = title.toLowerCase()
  const rest = body.toLowerCase()
  let total = 0
  let found = 0
  for (const term of terms) {
    if (head.includes(term)) {
      total += 3
      found += 1
    } else if (rest.includes(term)) {
      total += 1
      found += 1
    }
  }
  return found ? total + found : 0
}

export type Matches = { agents: Agent[]; templates: LibraryTemplate[] }

function top<T>(items: { item: T; score: number }[], limit: number) {
  return items
    .filter((entry) => entry.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, limit)
    .map((entry) => entry.item)
}

export function findMatches(
  query: string,
  agents: Agent[],
  templates: LibraryTemplate[],
  limit = 3,
): Matches {
  const terms = termsFor(query)
  if (!terms.length) return { agents: [], templates: [] }
  const matchedAgents = top(
    agents.map((item) => ({
      item,
      score: score(
        terms,
        item.label,
        [
          item.category,
          item.description,
          item.guidance?.input,
          item.guidance?.output,
          ...item.prompts.map((prompt) => prompt.label),
        ].join(' '),
      ),
    })),
    limit,
  )
  const names = new Set(matchedAgents.map((item) => item.label.toLowerCase()))
  const matchedTemplates = top(
    templates
      .filter((item) => !names.has(item.label.toLowerCase()))
      .map((item) => ({
        item,
        score: score(
          terms,
          item.label,
          [
            item.summary,
            item.description,
            item.sector.label,
            item.industry.label,
            ...item.tasks.map((task) => task.label),
            ...item.keywords,
          ].join(' '),
        ),
      })),
    limit,
  )
  return { agents: matchedAgents, templates: matchedTemplates }
}

import type { View } from './ChatSidebar'
import { reviewIdFromHash } from './review-client.ts'

export const viewHashes: Record<View, string> = {
  library: '#library',
  explore: '#demos',
  addons: '#addons',
  chat: '#chat',
  catalog: '#agents',
  operations: '#operations',
  performance: '#performance',
  log: '#logs',
  history: '#history',
  reviews: '#reviews',
  create: '#create',
  created: '#created',
}

export function viewForHash(hash: string): View {
  if (reviewIdFromHash(hash)) return 'reviews'
  if (hash === '#start') return 'library'
  return (
    (Object.keys(viewHashes) as View[]).find(
      (view) => viewHashes[view] === hash,
    ) ?? 'chat'
  )
}

// Views shown as tabs inside the library; the sidebar treats them as one page.
export const libraryViews: View[] = [
  'library',
  'catalog',
  'created',
  'explore',
  'addons',
]

// Breadcrumb trail for the top bar: section, then page.
export const crumbs: Record<View, [string, string]> = {
  library: ['Agent library', 'Browse'],
  catalog: ['Agent library', 'My agents'],
  created: ['Agent library', 'My agents › Made in this Lab'],
  explore: ['Agent library', 'Guided demos'],
  addons: ['Agent library', 'Add-ons'],
  create: ['Agent library', 'Create agent'],
  chat: ['Start here', 'Chat'],
  reviews: ['Start here', 'Document reviews'],
  history: ['Start here', 'Shared history'],
  operations: ['Operations', 'Overview'],
  performance: ['Operations', 'Performance'],
  log: ['Operations', 'Request log'],
}

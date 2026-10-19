import type { View } from './ChatSidebar'

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
  start: ['Start here', 'Find an agent'],
  library: ['Agent library', 'Browse'],
  catalog: ['Agent library', 'Ready to chat'],
  created: ['Agent library', 'Made in this Lab'],
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

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
  library: ['Agent library', 'Browse'],
  catalog: ['Agent library', 'Ready to chat'],
  created: ['Agent library', 'Made in this Lab'],
  explore: ['Agent library', 'Guided demos'],
  addons: ['Agent library', 'Add-ons'],
  create: ['Agent library', 'Create agent'],
  chat: ['Try it', 'Chat'],
  reviews: ['Try it', 'Document reviews'],
  history: ['Try it', 'Shared history'],
  performance: ['Measure', 'Performance'],
  log: ['Activity', 'Request log'],
}

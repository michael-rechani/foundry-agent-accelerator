import type { View } from './ChatSidebar'
import { useLibraryCatalog } from './library-catalog-client'
import { previewAgents } from './library-catalog'
import type { Config } from './workspace-config'

const previewReasons: Record<string, string> = {
  local_preview: 'Library previews need a connected Lab.',
  not_enabled: 'Library previews are turned off in this Lab.',
  model_not_configured:
    'Library previews need a model deployment. Ask the Lab operator.',
}

// The library catalog, and the library agents Chat can preview from it.
export function useLibraryPreviews(config: Config | null, view: View) {
  const previewCapability = config?.library_preview
  const library = useLibraryCatalog(
    !!config &&
      (view === 'library' || view === 'start' || !!previewCapability?.enabled),
  )
  const previewList = previewCapability?.enabled
    ? previewAgents(library.catalog, previewCapability.agent)
    : []
  const previewFor = (templateId: string) =>
    previewList.find((item) => item.id === `library-${templateId}`)
  const previewsLoading =
    !!previewCapability?.enabled && !library.catalog && !library.error
  const previewNote = !previewCapability
    ? ''
    : !previewCapability.enabled
      ? previewReasons[previewCapability.reason || ''] ||
        'Library previews are unavailable.'
      : library.error
        ? 'The library did not load. Open the Library to retry.'
        : !library.catalog
          ? 'Loading library previews...'
          : ''
  const previewOptions = previewList.map((item) => {
    const template = library.catalog?.templates.find(
      (entry) => `library-${entry.id}` === item.id,
    )
    return {
      agent: item,
      detail: template
        ? `Preview · ${template.sector.label} · ${template.industry.label}`
        : 'Preview',
      inProgress: template?.readiness.id === 'sample',
    }
  })
  return {
    library,
    previewCapability,
    previewList,
    previewFor,
    previewsLoading,
    previewNote,
    previewOptions,
  }
}

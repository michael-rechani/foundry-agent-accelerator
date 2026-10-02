import { useEffect, useRef } from 'react'
import { ChevronRight } from 'lucide-react'
import {
  fieldGroups,
  fieldKeys,
  openSector,
  type Facet,
  type FacetKey,
  type LibraryCatalog,
  type LiveFacet,
  type Selection,
} from './library-catalog'

const labels: Partial<Record<FacetKey, string>> = {
  tasks: 'Task',
  readiness: 'Readiness',
  tool_modes: 'Works with',
}

const fieldLabel = 'Sector and industry'

function FacetButton({
  item,
  pressed,
  nested = false,
  expandable = false,
  open = false,
  onClick,
}: {
  item: Facet
  pressed: boolean
  nested?: boolean
  expandable?: boolean
  open?: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      className="library-facet"
      aria-pressed={pressed}
      aria-expanded={expandable ? open : undefined}
      data-empty={item.count ? undefined : 'true'}
      data-nested={nested ? 'true' : undefined}
      data-open={open ? 'true' : undefined}
      onClick={onClick}
    >
      <span className="library-facet-label">
        {expandable && (
          <ChevronRight
            size={13}
            className="library-facet-chevron"
            aria-hidden="true"
          />
        )}
        {item.label}
      </span>
      <small aria-label={`${item.count} agents`}>{item.count}</small>
    </button>
  )
}

// Sector and industry are one list: each sector opens to show its industries
// once it, or one of its industries, is chosen.
export function FacetGroups({
  catalog,
  facets,
  selection,
  onToggle,
}: {
  catalog: LibraryCatalog
  facets: LiveFacet[]
  selection: Selection
  onToggle: (key: FacetKey, id: string) => void
}) {
  const itemsOf = (key: FacetKey) =>
    facets.find((group) => group.key === key)?.items ?? []
  const groups = fieldGroups(catalog, itemsOf('sectors'), itemsOf('industries'))
  const open = openSector(catalog, selection)
  return (
    <>
      <fieldset>
        <legend>Sector and industry</legend>
        {groups.map(({ sector, industries }) => {
          const expanded = industries.length > 0 && open === sector.id
          return (
            <div key={sector.id} className="library-facet-group">
              <FacetButton
                item={sector}
                pressed={selection.sectors === sector.id}
                expandable={industries.length > 0}
                open={expanded}
                onClick={() => onToggle('sectors', sector.id)}
              />
              {expanded && (
                <div
                  className="library-facet-children"
                  role="group"
                  aria-label={`Industries in ${sector.label}`}
                >
                  {industries.map((industry) => (
                    <FacetButton
                      key={industry.id}
                      item={industry}
                      nested
                      pressed={selection.industries === industry.id}
                      onClick={() => onToggle('industries', industry.id)}
                    />
                  ))}
                </div>
              )}
            </div>
          )
        })}
      </fieldset>
      {facets
        .filter((group) => !fieldKeys.includes(group.key))
        .map((group) => (
          <fieldset key={group.key}>
            <legend>{labels[group.key]}</legend>
            {group.items.map((item) => (
              <FacetButton
                key={item.id}
                item={item}
                pressed={selection[group.key] === item.id}
                onClick={() => onToggle(group.key, item.id)}
              />
            ))}
          </fieldset>
        ))}
    </>
  )
}

export function FacetMenus({
  catalog,
  facets,
  selection,
  onToggle,
}: {
  catalog: LibraryCatalog
  facets: LiveFacet[]
  selection: Selection
  onToggle: (key: FacetKey, id: string) => void
}) {
  const rootRef = useRef<HTMLDivElement>(null)
  const itemsOf = (key: FacetKey) =>
    facets.find((group) => group.key === key)?.items ?? []
  const groups = fieldGroups(catalog, itemsOf('sectors'), itemsOf('industries'))
  const open = openSector(catalog, selection)

  useEffect(() => {
    function closeMenus(target?: EventTarget | null) {
      const root = rootRef.current
      if (!root) return
      const element = target instanceof Node ? target : null
      root
        .querySelectorAll<HTMLDetailsElement>('details.library-filter-menu')
        .forEach((menu) => {
          if (!element || !menu.contains(element)) menu.removeAttribute('open')
        })
    }

    function onPointerDown(event: PointerEvent) {
      const root = rootRef.current
      if (!root?.contains(event.target as Node | null)) closeMenus(event.target)
    }

    function onKeyDown(event: KeyboardEvent) {
      if (event.key !== 'Escape') return
      const root = rootRef.current
      if (!root) return
      const target =
        event.target instanceof Node
          ? event.target
          : document.activeElement instanceof Node
            ? document.activeElement
            : null
      const openMenu =
        target &&
        Array.from(
          root.querySelectorAll<HTMLDetailsElement>(
            'details.library-filter-menu[open]',
          ),
        ).find((menu) => menu.contains(target))
      if (!openMenu) return
      openMenu.removeAttribute('open')
      openMenu.querySelector<HTMLElement>('summary')?.focus()
    }

    document.addEventListener('pointerdown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('pointerdown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [])

  const fieldValue = selection.industries
    ? itemsOf('industries').find((item) => item.id === selection.industries)
        ?.label
    : selection.sectors
      ? itemsOf('sectors').find((item) => item.id === selection.sectors)?.label
      : undefined

  const selectedLabel = (key: Exclude<FacetKey, 'sectors' | 'industries'>) =>
    selection[key]
      ? itemsOf(key).find((item) => item.id === selection[key])?.label
      : undefined
  const menuFacets = facets.filter(
    (
      group,
    ): group is LiveFacet & {
      key: Exclude<FacetKey, 'sectors' | 'industries'>
    } => !fieldKeys.includes(group.key),
  )

  return (
    <div className="library-filter-menus" ref={rootRef}>
      <details className="library-filter-menu">
        <summary>
          <span>{fieldLabel}</span>
          {fieldValue && <strong>{fieldValue}</strong>}
        </summary>
        <div className="library-filter-panel">
          {groups.map(({ sector, industries }) => {
            const expanded = industries.length > 0 && open === sector.id
            return (
              <div key={sector.id} className="library-facet-group">
                <FacetButton
                  item={sector}
                  pressed={selection.sectors === sector.id}
                  expandable={industries.length > 0}
                  open={expanded}
                  onClick={() => onToggle('sectors', sector.id)}
                />
                {expanded && (
                  <div
                    className="library-facet-children"
                    role="group"
                    aria-label={`Industries in ${sector.label}`}
                  >
                    {industries.map((industry) => (
                      <FacetButton
                        key={industry.id}
                        item={industry}
                        nested
                        pressed={selection.industries === industry.id}
                        onClick={() => onToggle('industries', industry.id)}
                      />
                    ))}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </details>
      {menuFacets.map((group) => (
        <details key={group.key} className="library-filter-menu">
          <summary>
            <span>{labels[group.key]}</span>
            {selectedLabel(group.key) && (
              <strong>{selectedLabel(group.key)}</strong>
            )}
          </summary>
          <div className="library-filter-panel">
            {group.items.map((item) => (
              <FacetButton
                key={item.id}
                item={item}
                pressed={selection[group.key] === item.id}
                onClick={() => onToggle(group.key, item.id)}
              />
            ))}
          </div>
        </details>
      ))}
    </div>
  )
}

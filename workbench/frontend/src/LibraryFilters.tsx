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

export type DependencyStatus =
  'ready' | 'degraded' | 'starting' | 'disabled' | 'unknown'

export type DependencyHealth = {
  status: DependencyStatus
  foundry: DependencyStatus
  cosmos: DependencyStatus
}

export type DependencyHealthSnapshot = {
  checkedAt: number
  data: DependencyHealth | null
  error: boolean
  loading: boolean
}

const known: DependencyStatus[] = ['ready', 'degraded', 'starting', 'disabled']

function parseStatus(value: unknown): DependencyStatus {
  // The server reports a probe that failed as "unavailable".
  if (value === 'unavailable') return 'degraded'
  return known.find((status) => status === value) ?? 'unknown'
}

// While the Lab is starting, or in a preview without live connections, the
// server sends only the overall status, so each service follows it.
export function parseDependencyHealth(value: unknown): DependencyHealth {
  const record = (value ?? {}) as Record<string, unknown>
  const status = parseStatus(record.status)
  const inherited =
    status === 'starting' || status === 'disabled' ? status : 'unknown'
  const service = (item: unknown) =>
    item === undefined ? inherited : parseStatus(item)
  return {
    status,
    foundry: service(record.foundry),
    cosmos: service(record.cosmos),
  }
}

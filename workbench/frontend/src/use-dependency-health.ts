import { useCallback, useEffect, useRef, useState } from 'react'
import {
  parseDependencyHealth,
  type DependencyHealthSnapshot,
} from './dependency-health'
import type { View } from './ChatSidebar'
import { requestJson } from './request'

// The dependency report behind the Operations page. It is fetched when that
// page opens, and a result under a minute old is reused.
export function useDependencyHealth(view: View) {
  const [dependencyHealth, setDependencyHealth] =
    useState<DependencyHealthSnapshot | null>(null)
  const dependencyCheck = useRef<Promise<void> | null>(null)

  const loadDependencyHealth = useCallback(
    async (force = false) => {
      const cached = dependencyHealth
      if (dependencyCheck.current) return dependencyCheck.current
      if (
        !force &&
        cached &&
        Date.now() - cached.checkedAt < 60_000 &&
        (cached.data || cached.error)
      )
        return
      setDependencyHealth((current) => ({
        checkedAt: current?.checkedAt ?? 0,
        data: current?.data ?? null,
        error: false,
        loading: true,
      }))
      const abort = new AbortController()
      dependencyCheck.current = requestJson(
        '/api/health/dependencies',
        {
          method: 'GET',
          headers: { 'X-Workbench-Request': '1' },
        },
        abort.signal,
      )
        .then(({ data }) => {
          const parsed = parseDependencyHealth(data)
          // A gateway error page or an unreadable body isn't a health report.
          if (parsed.status === 'unknown') throw new Error('Unreadable report')
          setDependencyHealth({
            checkedAt: Date.now(),
            data: parsed,
            error: false,
            loading: false,
          })
        })
        .catch(() => {
          setDependencyHealth({
            checkedAt: Date.now(),
            data: null,
            error: true,
            loading: false,
          })
        })
        .finally(() => {
          dependencyCheck.current = null
        })
      return dependencyCheck.current
    },
    [dependencyHealth],
  )

  useEffect(() => {
    if (view !== 'operations') return
    const timer = window.setTimeout(() => {
      void loadDependencyHealth()
    }, 0)
    return () => window.clearTimeout(timer)
  }, [loadDependencyHealth, view])

  return { dependencyHealth, loadDependencyHealth }
}

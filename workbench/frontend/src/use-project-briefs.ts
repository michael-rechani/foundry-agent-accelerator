import { useState } from 'react'
import {
  MAX_PROJECTS,
  PROJECT_STORAGE_KEY,
  parseProjects,
  serializeProjects,
  type ProjectBrief,
} from './project-brief'

function load() {
  try {
    return {
      projects: parseProjects(window.localStorage.getItem(PROJECT_STORAGE_KEY)),
      error: '',
    }
  } catch {
    return {
      projects: [] as ProjectBrief[],
      error:
        'Saved projects could not be read. Browser storage may be blocked or the saved format may be damaged. Existing storage has not been changed. Restore browser access and reload, or explicitly forget local projects.',
    }
  }
}

export function useProjectBriefs() {
  const [initial] = useState(load)
  const [projects, setProjects] = useState(initial.projects)
  const [selectedId, select] = useState(initial.projects[0]?.id ?? '')
  const [error, setError] = useState(initial.error)
  const [readBlocked, setReadBlocked] = useState(!!initial.error)
  const selected = projects.find((project) => project.id === selectedId)

  function write(next: ProjectBrief[]) {
    if (readBlocked) return false
    try {
      window.localStorage.setItem(PROJECT_STORAGE_KEY, serializeProjects(next))
      setProjects(next)
      setError('')
      return true
    } catch {
      setError(
        'Project changes were not saved. Browser storage may be blocked or full. Keep this page open, free storage or restore access, then save again.',
      )
      return false
    }
  }

  function save(project: Omit<ProjectBrief, 'id' | 'updatedAt'>) {
    if (!selected && projects.length >= MAX_PROJECTS) {
      setError(
        `Keep at most ${MAX_PROJECTS} local projects. Export and delete an old project first.`,
      )
      return false
    }
    if (!selected && typeof crypto.randomUUID !== 'function') {
      setError('Use HTTPS or localhost to create a project identifier.')
      return false
    }
    const record = {
      ...project,
      id: selected?.id ?? crypto.randomUUID(),
      updatedAt: new Date().toISOString(),
    }
    const next = selected
      ? projects.map((item) => (item.id === record.id ? record : item))
      : [...projects, record]
    if (!write(next)) return false
    select(record.id)
    return true
  }

  function remove() {
    if (!selected || !write(projects.filter((item) => item.id !== selected.id)))
      return false
    select('')
    return true
  }

  function forget() {
    try {
      window.localStorage.removeItem(PROJECT_STORAGE_KEY)
      setProjects([])
      select('')
      setError('')
      setReadBlocked(false)
    } catch {
      setError(
        'Local projects could not be removed. Restore browser storage access and try again.',
      )
    }
  }

  return {
    projects,
    selected,
    selectedId,
    select,
    save,
    remove,
    forget,
    error,
    readBlocked,
  }
}

export type ProjectBriefs = ReturnType<typeof useProjectBriefs>

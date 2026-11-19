import { useRef, useState } from 'react'
import {
  emptyProject,
  MAX_PROJECTS,
  PROJECT_STORAGE_KEY,
  parseProjects,
  serializeProjects,
  type ProjectBrief,
} from './project-brief'

type ProjectDraft = Omit<ProjectBrief, 'id' | 'updatedAt'>

function load() {
  let snapshot: string | null = null
  try {
    snapshot = window.localStorage.getItem(PROJECT_STORAGE_KEY)
    return { projects: parseProjects(snapshot), snapshot, error: '' }
  } catch {
    return {
      projects: [] as ProjectBrief[],
      snapshot,
      error:
        'Saved projects could not be read. Browser storage may be blocked or the saved format may be damaged. Existing storage has not been changed. Restore browser access and reload, or explicitly forget local projects.',
    }
  }
}

export function useProjectBriefs() {
  const [initial] = useState(load)
  const snapshot = useRef(initial.snapshot)
  const [projects, setProjects] = useState(initial.projects)
  const [selectedId, setSelectedId] = useState(initial.projects[0]?.id ?? '')
  const [text, setText] = useState<ProjectDraft>(
    initial.projects[0] ?? emptyProject,
  )
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState(initial.error)
  const [readBlocked, setReadBlocked] = useState(!!initial.error)
  const [conflict, setConflict] = useState(false)
  const [writing, setWriting] = useState(false)
  const selected = projects.find((project) => project.id === selectedId)
  const dirty = Object.keys(emptyProject).some(
    (field) =>
      text[field as keyof ProjectDraft] !==
      (selected ?? emptyProject)[field as keyof ProjectDraft],
  )

  function confirmDiscard() {
    return (
      !dirty ||
      window.confirm(
        'Discard unsaved project edits? The last saved brief is kept. Copy any edits you need before continuing.',
      )
    )
  }

  function select(id: string) {
    if (writing) return false
    if (id === selectedId) return true
    if (!confirmDiscard()) return false
    const next = projects.find((project) => project.id === id)
    if (id && !next) {
      setError(
        'That local project is no longer available. Reload saved projects before choosing it.',
      )
      return false
    }
    setSelectedId(id)
    setText(next ?? emptyProject)
    setSaved(false)
    return true
  }

  function edit(field: keyof ProjectDraft, value: string) {
    setText((previous) => ({ ...previous, [field]: value }))
    setSaved(false)
  }

  async function write(next: ProjectBrief[] | null) {
    if (writing || (readBlocked && next !== null)) return false
    if (!navigator.locks) {
      setError(
        'This browser cannot safely save local projects across tabs. Use a current browser over HTTPS or localhost. Your edits are preserved.',
      )
      return false
    }
    const expected = snapshot.current
    setWriting(true)
    try {
      return await navigator.locks.request(
        PROJECT_STORAGE_KEY,
        { mode: 'exclusive', ifAvailable: true },
        (lock) => {
          if (!lock) {
            setError(
              'Another tab is saving projects. Your edits are preserved; try again after it finishes.',
            )
            return false
          }
          if (window.localStorage.getItem(PROJECT_STORAGE_KEY) !== expected) {
            setConflict(true)
            setError(
              'Saved projects changed in another tab. Nothing was overwritten and your unsaved edits are still on this page. Copy edits you want to keep, then reload saved projects.',
            )
            return false
          }
          const raw = next === null ? null : serializeProjects(next)
          if (raw === null) window.localStorage.removeItem(PROJECT_STORAGE_KEY)
          else window.localStorage.setItem(PROJECT_STORAGE_KEY, raw)
          snapshot.current = raw
          setProjects(next ?? [])
          setError('')
          setConflict(false)
          return true
        },
      )
    } catch {
      setError(
        'Project changes were not saved. Browser storage may be blocked or full. Keep this page open, free storage or restore access, then save again.',
      )
      return false
    } finally {
      setWriting(false)
    }
  }

  async function save() {
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
      ...text,
      id: selected?.id ?? crypto.randomUUID(),
      updatedAt: new Date().toISOString(),
    }
    const next = selected
      ? projects.map((item) => (item.id === record.id ? record : item))
      : [...projects, record]
    if (!(await write(next))) return false
    setSelectedId(record.id)
    setText(record)
    setSaved(true)
    return true
  }

  async function remove() {
    if (
      !selected ||
      !(await write(projects.filter((item) => item.id !== selected.id)))
    )
      return false
    setSelectedId('')
    setText(emptyProject)
    setSaved(false)
    return true
  }

  async function forget() {
    if (!(await write(null))) return
    setSelectedId('')
    setText(emptyProject)
    setSaved(false)
    setReadBlocked(false)
  }

  function reload() {
    if (writing || !confirmDiscard()) return
    const next = load()
    if (next.error) {
      setError(next.error)
      return
    }
    const nextSelected =
      next.projects.find((item) => item.id === selectedId) ?? next.projects[0]
    snapshot.current = next.snapshot
    setProjects(next.projects)
    setSelectedId(nextSelected?.id ?? '')
    setText(nextSelected ?? emptyProject)
    setSaved(false)
    setError('')
    setReadBlocked(false)
    setConflict(false)
  }

  return {
    projects,
    selected,
    selectedId,
    select,
    text,
    edit,
    dirty,
    saved,
    writing,
    save,
    remove,
    forget,
    reload,
    error,
    readBlocked,
    conflict,
  }
}

export type ProjectBriefs = ReturnType<typeof useProjectBriefs>

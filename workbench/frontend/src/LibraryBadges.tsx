import { BadgeCheck, CircleDashed, Sparkles } from 'lucide-react'
import { inProgress } from './library-helpers'
import type { LibraryTemplate } from './library-catalog'

const tones: Record<string, string> = {
  reviewed: 'good',
  'tested-live': 'good',
  sample: 'caution',
  simulated: 'info',
  'connected-required': 'caution',
  focus: 'info',
}

// Focus agents are the ones the Lab builds out in depth; the rest are previews.
export function AvailabilityBadge({ template }: { template: LibraryTemplate }) {
  return (
    <span
      className={`library-badge ${tones[template.availability.id] || ''}`}
      title={template.availability.description}
    >
      {template.availability.id === 'focus' && (
        <Sparkles size={12} aria-hidden="true" />
      )}
      {template.availability.label}
    </span>
  )
}

function ReadinessBadge({ template }: { template: LibraryTemplate }) {
  const Icon = inProgress(template) ? CircleDashed : BadgeCheck
  return (
    <span
      className={`library-badge ${tones[template.readiness.id] || ''}`}
      title={template.readiness.description}
    >
      <Icon size={12} aria-hidden="true" />
      {template.readiness.label}
    </span>
  )
}

export function Badges({ template }: { template: LibraryTemplate }) {
  return (
    <>
      <AvailabilityBadge template={template} />
      <ReadinessBadge template={template} />
      <span className={`library-badge ${tones[template.tool_mode.id] || ''}`}>
        {template.tool_mode.label}
      </span>
    </>
  )
}

import { BadgeCheck, Construction } from 'lucide-react'
import { inProgress } from './library-helpers'
import type { LibraryTemplate } from './library-catalog'

const tones: Record<string, string> = {
  reviewed: 'good',
  'tested-live': 'good',
  sample: 'caution',
  simulated: 'info',
  'connected-required': 'caution',
}

function ReadinessBadge({ template }: { template: LibraryTemplate }) {
  const Icon = inProgress(template) ? Construction : BadgeCheck
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
      <ReadinessBadge template={template} />
      <span className={`library-badge ${tones[template.tool_mode.id] || ''}`}>
        {template.tool_mode.label}
      </span>
    </>
  )
}

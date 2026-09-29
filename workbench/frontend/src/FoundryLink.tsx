import type { ReactNode } from 'react'
import { ExternalLink } from 'lucide-react'

export function FoundryLink({
  href,
  children,
  className = '',
}: {
  href: string | null
  children: ReactNode
  className?: string
}) {
  if (!href) return null
  return (
    <a
      className={`foundry-link ${className}`.trim()}
      href={href}
      target="_blank"
      rel="noopener noreferrer"
    >
      {children}
      <ExternalLink size={13} aria-hidden="true" />
      <span className="visually-hidden"> (opens in a new tab)</span>
    </a>
  )
}

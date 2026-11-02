import type { ReactNode } from 'react'

export function LibraryHero({
  children,
  onDemos,
}: {
  children: ReactNode
  onDemos?: () => void
}) {
  return (
    <header className="library-hero">
      <p className="library-eyebrow">Agent library</p>
      <h1>Find an agent for the job</h1>
      <p>
        Pick an agent, try it with sample inputs, see what it needs and what it
        leaves to a person, then take it to your Microsoft Foundry project.
      </p>
      <p className="library-hero-note">
        Every agent below can be tried from its own page. &ldquo;My
        agents&rdquo; counts only the agents already set up to open in Chat.
        {onDemos && (
          <>
            {' '}
            Want a walkthrough?{' '}
            <button type="button" className="inline-link" onClick={onDemos}>
              Try a guided demo
            </button>
            .
          </>
        )}
      </p>
      {children}
    </header>
  )
}

function CreateStepLink({ onOpenCreate }: { onOpenCreate?: () => void }) {
  if (!onOpenCreate) return <>Make your own copy</>
  return (
    <button type="button" className="library-path-link" onClick={onOpenCreate}>
      Make your own copy
    </button>
  )
}

export function LibraryPath({
  previewsOn,
  onOpenCreate,
}: {
  previewsOn: boolean
  onOpenCreate?: () => void
}) {
  return (
    <ol className="library-path" aria-label="How the library works">
      <li>
        <span>1</span>Pick an agent
      </li>
      <li>
        <span>2</span>
        {previewsOn ? (
          'Try it in Chat'
        ) : (
          <CreateStepLink onOpenCreate={onOpenCreate} />
        )}
      </li>
      <li>
        <span>3</span>
        {previewsOn ? (
          <CreateStepLink onOpenCreate={onOpenCreate} />
        ) : (
          'Try it with sample data'
        )}
      </li>
      <li>
        <span>4</span>Take it to Foundry
      </li>
    </ol>
  )
}

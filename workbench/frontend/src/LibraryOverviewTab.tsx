import { FlaskConical, PackageOpen, ShieldCheck, Wrench } from 'lucide-react'
import type { LibraryTemplate } from './library-catalog'

export function LibraryOverviewTab({
  template,
}: {
  template: LibraryTemplate
}) {
  return (
    <>
      <dl className="library-facts">
        <div>
          <dt>
            <ShieldCheck size={15} aria-hidden="true" /> Readiness
          </dt>
          <dd>
            <strong>{template.readiness.label}</strong>
            <span>{template.readiness.description}</span>
          </dd>
        </div>
        <div>
          <dt>
            <Wrench size={15} aria-hidden="true" /> Tools
          </dt>
          <dd>
            <strong>{template.tool_mode.label}</strong>
            <span>{template.tool_mode.description}</span>
          </dd>
        </div>
        <div className="hood-only">
          <dt>
            <FlaskConical size={15} aria-hidden="true" /> Model profile
          </dt>
          <dd>
            <strong>{template.model_profile.label}</strong>
            <span>
              Relative cost {template.runtime_hint.relative_cost}, latency{' '}
              {template.runtime_hint.relative_latency}.{' '}
              {template.runtime_hint.basis}
            </span>
          </dd>
        </div>
        <div className="hood-only">
          <dt>
            <PackageOpen size={15} aria-hidden="true" /> Export
          </dt>
          <dd>
            <strong>
              {template.export.exportable ? 'After creation' : 'Not available'}
            </strong>
            <span>{template.export.package_format}</span>
          </dd>
        </div>
      </dl>
      <div className="library-columns">
        <section className="library-panel">
          <h2>What to give it</h2>
          <p>{template.input}</p>
          <h2>What it returns</h2>
          <p>{template.output}</p>
          <h2>What a good answer does</h2>
          <p>{template.expected_behavior}</p>
          <p className="library-muted">
            Based on its acceptance tests, not a recorded answer.
          </p>
        </section>
        <section className="library-panel">
          <h2>What it won&apos;t do</h2>
          <p>{template.limits}</p>
          {template.tools.length > 0 && (
            <>
              <h2>Sample lookups it uses</h2>
              <ul className="library-tools">
                {template.tools.map((tool) => (
                  <li key={tool.name}>
                    {tool.description}
                    <code className="hood-only">{tool.name}</code>
                  </li>
                ))}
              </ul>
            </>
          )}
          <div className="hood-only">
            <h2>Before you use it</h2>
            <ul>
              {template.prerequisites.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
        </section>
      </div>
    </>
  )
}

import {
  Brain,
  Calculator,
  Globe,
  Info,
  Mail,
  ScanText,
  Search,
  ShieldCheck,
  type LucideIcon,
} from 'lucide-react'
import {
  addOnRules,
  addOns,
  type AddOn,
  type AddOnIcon,
} from './add-on-catalog'
import './library.css'

const icons: Record<AddOnIcon, LucideIcon> = {
  search: Search,
  memory: Brain,
  documents: ScanText,
  notifications: Mail,
  calculator: Calculator,
  web: Globe,
}

export function AddOns() {
  return (
    <main className="secondary-view library-view" aria-label="Add-ons">
      <header className="library-hero">
        <p className="library-eyebrow">Agent library</p>
        <h1>Add-ons an agent could use</h1>
        <p>
          An add-on gives an agent something extra to work with, such as your
          own documents or a calculator. See what each one would do and what it
          would cost before anything is built.
        </p>
      </header>
      <div className="library-decision" role="note">
        <Info size={18} aria-hidden="true" />
        <p>
          <strong>A preview only. </strong>Nothing on this page turns anything
          on, sends data or costs money. One add-on, Knowledge search, already
          runs as a small sample pilot in the Lab. The others are not available
          yet. Add-ons are built in Microsoft Foundry, so an agent you take
          there can connect to them.
        </p>
      </div>
      <section className="library-panel addon-rules" aria-labelledby="rules">
        <h2 id="rules">
          <ShieldCheck size={16} aria-hidden="true" /> Rules every add-on would
          follow
        </h2>
        <ul>
          {addOnRules.map((rule) => (
            <li key={rule}>{rule}</li>
          ))}
        </ul>
      </section>
      <ul className="library-grid addon-grid" aria-label="Add-ons">
        {addOns.map((addOn) => (
          <li key={addOn.id}>
            <AddOnCard addOn={addOn} />
          </li>
        ))}
      </ul>
    </main>
  )
}

function AddOnCard({ addOn }: { addOn: AddOn }) {
  const Icon = icons[addOn.icon]
  const titleId = `addon-${addOn.id}`
  return (
    <article className="addon-card" aria-labelledby={titleId}>
      <span className="library-kicker">
        <Icon size={15} aria-hidden="true" />
        <span className="library-badges">
          <span className="library-badge">
            {addOn.pilot ? 'Sample pilot' : 'Not available yet'}
          </span>
          {addOn.approval && (
            <span className="library-badge caution">{addOn.approval}</span>
          )}
        </span>
      </span>
      <h2 id={titleId}>{addOn.name}</h2>
      <p className="addon-summary">{addOn.summary}</p>
      <p className="addon-example">
        <strong>For example: </strong>
        {addOn.example}
      </p>
      {addOn.pilot && (
        <p className="addon-example">
          <strong>In the Lab today: </strong>
          {addOn.pilot}
        </p>
      )}
      <h3>What it would cost</h3>
      <ul>
        {addOn.cost.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
      <h3>What it would need</h3>
      <ul>
        {addOn.needs.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
      <h3>Keeping it safe</h3>
      <p>{addOn.safety}</p>
      <dl className="addon-hood hood-only">
        <div>
          <dt>Service</dt>
          <dd>{addOn.service}</dd>
        </div>
        <div>
          <dt>Billing</dt>
          <dd>{addOn.billing}</dd>
        </div>
        {addOn.note && (
          <div>
            <dt>Note</dt>
            <dd>{addOn.note}</dd>
          </div>
        )}
        <div>
          <dt>Tracked in</dt>
          <dd>Add-ons roadmap (#54)</dd>
        </div>
      </dl>
    </article>
  )
}

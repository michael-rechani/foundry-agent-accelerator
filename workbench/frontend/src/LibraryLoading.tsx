import { Search } from 'lucide-react'
import { demoScenarios } from './demo-scenarios'
import { LibraryHero } from './LibraryHero'

// Grey shapes in the same places as the real page, so nothing jumps when the
// agents arrive. They do not animate, which keeps a remote desktop quiet.
export function LibraryLoading() {
  return (
    <>
      <p role="status" className="visually-hidden">
        Loading the agent library...
      </p>
      <LibraryHero>
        <ol className="library-path" aria-hidden="true">
          {[1, 2, 3, 4].map((step) => (
            <li key={step}>
              <span>{step}</span>
              <div className="library-bar library-bar-step" />
            </li>
          ))}
        </ol>
      </LibraryHero>
      <div className="library-layout" aria-hidden="true">
        <div className="library-filters">
          <div className="library-search">
            <Search size={16} />
            <div className="library-bar library-bar-search" />
          </div>
          {[3, 5, 2, 3].map((rows, group) => (
            <div key={group} className="library-placeholder-group">
              <div className="library-bar library-bar-legend" />
              {Array.from({ length: rows }, (_, row) => (
                <div key={row} className="library-bar library-bar-row" />
              ))}
            </div>
          ))}
        </div>
        <div>
          <section className="library-start">
            <div className="library-start-head">
              <h2 className="library-bar-count">&nbsp;</h2>
              <span>&nbsp;</span>
            </div>
            <ul className="library-start-list">
              {demoScenarios.map((scenario) => (
                <li key={scenario.id}>
                  <div className="library-start-placeholder">
                    <div className="library-bar library-bar-icon" />
                    <div className="library-bar library-bar-title" />
                    <div className="library-bar-text">
                      <div className="library-bar library-bar-line" />
                      <div className="library-bar library-bar-line" />
                      <div className="library-bar library-bar-line library-bar-short" />
                    </div>
                    <div className="library-bar library-bar-foot" />
                  </div>
                </li>
              ))}
            </ul>
          </section>
          <div className="library-results-toolbar" aria-hidden="true">
            <div className="library-results-head">
              <h2 className="library-bar-count">&nbsp;</h2>
              <span>&nbsp;</span>
            </div>
            <div className="library-bar library-bar-switch" />
          </div>
          <ul className="library-grid">
            {Array.from({ length: 6 }, (_, card) => (
              <li key={card}>
                <div className="library-placeholder">
                  <div className="library-bar library-bar-kicker" />
                  <div className="library-card-head">
                    <div className="library-bar library-bar-icon" />
                    <div className="library-bar library-bar-title" />
                  </div>
                  <div className="library-bar library-bar-line" />
                  <div className="library-bar library-bar-line" />
                  <div className="library-bar library-bar-line library-bar-short" />
                  <div className="library-bar library-bar-pills" />
                </div>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </>
  )
}

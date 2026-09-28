;(function () {
  'use strict'

  var FEATURED = 'supplier-invoice-reviewer'
  var THEME_KEY = 'foundry-lab-preview-theme'
  var HOOD_KEY = 'foundry-lab-preview-hood'
  var VIEWS = {
    library: 'Agent library',
    try: 'Playground',
    score: 'Scorecard',
    traces: 'Traces',
    foundry: 'Open in Foundry',
  }

  var body = document.body
  var params = new URLSearchParams(window.location.search)
  var agents = (window.PREVIEW_AGENTS || []).slice()
  var filters = { q: '', ready: 'all', sector: 'all' }
  var current = FEATURED

  function store(key, value) {
    try {
      window.localStorage.setItem(key, value)
    } catch {
      /* Storage can be unavailable in private windows. */
    }
  }

  function read(key) {
    try {
      return window.localStorage.getItem(key)
    } catch {
      return null
    }
  }

  function el(tag, className, text) {
    var node = document.createElement(tag)
    if (className) node.className = className
    if (text) node.textContent = text
    return node
  }

  function icon(name, small) {
    var ns = 'http://www.w3.org/2000/svg'
    var svg = document.createElementNS(ns, 'svg')
    svg.setAttribute('class', small ? 'i sm' : 'i')
    svg.setAttribute('aria-hidden', 'true')
    var use = document.createElementNS(ns, 'use')
    use.setAttribute('href', '#i-' + name)
    svg.appendChild(use)
    return svg
  }

  function readinessBadge(agent) {
    var reviewed = agent.readiness === 'reviewed'
    var badge = el('span', 'badge ' + (reviewed ? 'b-success' : 'b-warning'))
    badge.appendChild(icon(reviewed ? 'check' : 'info'))
    badge.appendChild(document.createTextNode(agent.readinessLabel))
    return badge
  }

  function modeBadge(agent) {
    return el('span', 'badge b-neutral', agent.toolMode)
  }

  /* Theme */
  var themeButton = document.getElementById('theme')
  function applyTheme(theme) {
    var dark = theme !== 'light'
    body.classList.toggle('dark', dark)
    themeButton.setAttribute(
      'aria-label',
      dark ? 'Switch to light theme' : 'Switch to dark theme',
    )
    themeButton
      .querySelector('use')
      .setAttribute('href', dark ? '#i-sun' : '#i-moon')
  }
  var requestedTheme = params.get('theme')
  applyTheme(
    requestedTheme === 'light' || requestedTheme === 'dark'
      ? requestedTheme
      : read(THEME_KEY) || 'dark',
  )
  themeButton.addEventListener('click', function () {
    var next = body.classList.contains('dark') ? 'light' : 'dark'
    applyTheme(next)
    store(THEME_KEY, next)
  })

  /* Under the hood */
  var hoodSwitch = document.getElementById('hood')
  function applyHood(on) {
    body.classList.toggle('hood', on)
    hoodSwitch.setAttribute('aria-checked', on ? 'true' : 'false')
    if (!on && body.dataset.view === 'traces') show('score')
  }
  applyHood(params.get('hood') === '1' || read(HOOD_KEY) === '1')
  hoodSwitch.addEventListener('click', function () {
    var on = !body.classList.contains('hood')
    applyHood(on)
    store(HOOD_KEY, on ? '1' : '0')
  })

  /* Navigation */
  function show(view) {
    if (!VIEWS[view]) view = 'library'
    if (view === 'traces' && !body.classList.contains('hood')) view = 'score'
    if (view === 'score' || view === 'traces') selectAgent(FEATURED)
    body.dataset.view = view
    document.querySelectorAll('.view').forEach(function (section) {
      section.classList.toggle('on', section.id === 'view-' + view)
    })
    document.querySelectorAll('.nav[data-view]').forEach(function (button) {
      var active = button.getAttribute('data-view') === view
      button.classList.toggle('active', active)
      if (active) button.setAttribute('aria-current', 'page')
      else button.removeAttribute('aria-current')
    })
    document.getElementById('crumb').textContent = VIEWS[view]
    if (window.location.hash !== '#' + view) {
      window.history.replaceState(null, '', '#' + view)
    }
    document.querySelector('main').scrollTop = 0
  }

  document.addEventListener('click', function (event) {
    var target = event.target.closest('[data-view], [data-go]')
    if (!target) return
    var agent = target.getAttribute('data-agent')
    if (agent) selectAgent(agent)
    show(target.getAttribute('data-view') || target.getAttribute('data-go'))
  })

  /* Playground */
  function selectAgent(id) {
    var agent = agents.find(function (item) {
      return item.id === id
    })
    if (!agent) return
    current = id
    body.classList.toggle('other', id !== FEATURED)
    document.getElementById('a-name').textContent = agent.label
    document.getElementById('a-meta').textContent =
      agent.industry + ' \u00b7 ' + agent.sector
    document.getElementById('a-summary').textContent = agent.summary
    document.getElementById('a-decides').textContent = agent.decides
    var badges = document.getElementById('a-badges')
    badges.replaceChildren(readinessBadge(agent), modeBadge(agent))
    document.getElementById('a-example').textContent =
      'It returns ' +
      agent.output.charAt(0).toLowerCase() +
      agent.output.slice(1)
    document.getElementById('composer-note').hidden = true
  }

  document.getElementById('composer').addEventListener('submit', function (e) {
    e.preventDefault()
    document.getElementById('composer-note').hidden = false
  })

  document.querySelectorAll('[data-prompt]').forEach(function (chip) {
    chip.addEventListener('click', function () {
      var input = document.querySelector('#composer input')
      input.value = chip.textContent
      input.focus()
    })
  })

  var toast = document.getElementById('toast')
  var toastTimer = 0
  document.querySelectorAll('[data-soon]').forEach(function (button) {
    button.addEventListener('click', function () {
      toast.textContent = 'Coming soon to the Lab.'
      toast.hidden = false
      window.clearTimeout(toastTimer)
      toastTimer = window.setTimeout(function () {
        toast.hidden = true
      }, 2400)
    })
  })

  document.getElementById('appsearch').addEventListener('click', function () {
    show('library')
    document.getElementById('q').focus()
  })

  /* Library */
  var cards = document.getElementById('cards')

  function matches(agent) {
    if (filters.ready !== 'all' && agent.readiness !== filters.ready) {
      return false
    }
    if (filters.sector !== 'all' && agent.sector !== filters.sector) {
      return false
    }
    if (!filters.q) return true
    var text = [
      agent.label,
      agent.summary,
      agent.industry,
      agent.sector,
      agent.decides,
    ]
      .join(' ')
      .toLowerCase()
    return filters.q
      .split(/\s+/)
      .filter(Boolean)
      .every(function (word) {
        return text.indexOf(word) !== -1
      })
  }

  function card(agent) {
    var node = el('article', 'card')
    node.setAttribute('data-agent-id', agent.id)

    var head = el('div', 'cardhead')
    var mark = el('span', 'cardicon')
    mark.appendChild(icon(agent.toolMode === 'Text only' ? 'doc' : 'tool'))
    var meta = el('div', 'meta')
    meta.appendChild(el('h3', '', agent.label))
    meta.appendChild(el('div', 'muted small', agent.industry))
    head.appendChild(mark)
    head.appendChild(meta)
    node.appendChild(head)

    node.appendChild(el('p', '', agent.summary))

    var facts = el('dl', 'facts')
    facts.appendChild(el('dt', '', 'Who decides'))
    facts.appendChild(el('dd', '', agent.decides))
    facts.appendChild(el('dt', '', 'Sector'))
    facts.appendChild(el('dd', '', agent.sector))
    node.appendChild(facts)

    var foot = el('div', 'cardfoot')
    foot.appendChild(readinessBadge(agent))
    foot.appendChild(modeBadge(agent))
    foot.appendChild(el('span', 'grow'))
    var open = el('button', 'btn primary', 'Try it')
    open.type = 'button'
    open.setAttribute('data-go', 'try')
    open.setAttribute('data-agent', agent.id)
    open.setAttribute('aria-label', 'Try ' + agent.label)
    foot.appendChild(open)
    node.appendChild(foot)
    return node
  }

  function render() {
    var shown = agents.filter(matches)
    cards.replaceChildren()
    if (!shown.length) {
      cards.appendChild(
        el('p', 'empty', 'No agents match. Try a different search or filter.'),
      )
    }
    shown.forEach(function (agent) {
      cards.appendChild(card(agent))
    })
    document.getElementById('result-count').textContent =
      shown.length === agents.length
        ? agents.length + ' agents'
        : shown.length + ' of ' + agents.length + ' agents'
    document.getElementById('nav-count').textContent = String(agents.length)
  }

  document.getElementById('q').addEventListener('input', function (event) {
    filters.q = event.target.value.trim().toLowerCase()
    render()
  })

  function bindChips(attribute, key) {
    var chips = document.querySelectorAll('[' + attribute + ']')
    chips.forEach(function (chip) {
      chip.addEventListener('click', function () {
        filters[key] = chip.getAttribute(attribute)
        chips.forEach(function (other) {
          other.setAttribute('aria-pressed', other === chip ? 'true' : 'false')
        })
        render()
      })
    })
  }
  bindChips('data-ready', 'ready')
  bindChips('data-sector', 'sector')

  document.addEventListener('keydown', function (event) {
    if (event.key !== '/' || event.target.closest('input, textarea')) return
    event.preventDefault()
    show('library')
    document.getElementById('q').focus()
  })

  function fromCatalog(template) {
    return {
      id: template.id,
      label: template.label,
      summary: template.summary,
      readiness: template.readiness.id,
      readinessLabel: template.readiness.label,
      toolMode: template.tool_mode.label,
      sector: template.sector.label,
      industry: template.industry.label,
      decides: template.human_decision,
      output: template.output,
    }
  }

  render()
  selectAgent(FEATURED)
  show(window.location.hash.slice(1))

  /* Prefer the live catalog so the preview always matches the Lab. */
  if (window.fetch) {
    window
      .fetch('/api/agent-templates', { credentials: 'same-origin' })
      .then(function (response) {
        return response.ok ? response.json() : null
      })
      .then(function (data) {
        if (!data || !Array.isArray(data.templates) || !data.templates.length) {
          return
        }
        agents = data.templates.map(fromCatalog)
        render()
        selectAgent(current)
      })
      .catch(function () {
        /* Keep the bundled snapshot. */
      })
  }
})()

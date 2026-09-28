const crumbs = {
  library: 'Agent library',
  try: 'Expense report checker / Playground',
  trace: 'Traces / run_7f3a…c21',
  score: 'Scorecards / Expense report checker',
}
function go(v) {
  document
    .querySelectorAll('.view')
    .forEach((s) => s.classList.toggle('on', s.id === 'view-' + v))
  document
    .querySelectorAll('.nav')
    .forEach((n) => n.classList.toggle('active', n.dataset.view === v))
  document.getElementById('crumbs').innerHTML = 'Lab / <b>' + crumbs[v] + '</b>'
}
document
  .querySelectorAll('[data-view]')
  .forEach((b) => (b.onclick = () => go(b.dataset.view)))
document.querySelectorAll('[data-go]').forEach(
  (b) =>
    (b.onclick = (e) => {
      e.preventDefault()
      go(b.dataset.go)
    }),
)
function hood(on) {
  document.body.classList.toggle('hood', on)
  document.getElementById('hoodSwitch').classList.toggle('on', on)
  document.getElementById('segHood').classList.toggle('on', on)
  document.getElementById('segPlain').classList.toggle('on', !on)
  if (!on && document.getElementById('view-trace').classList.contains('on'))
    go('try')
}
document.getElementById('hoodSwitch').onclick = () =>
  hood(!document.body.classList.contains('hood'))
document.getElementById('segHood').onclick = () => hood(true)
document.getElementById('segPlain').onclick = () => hood(false)
document.getElementById('darkSwitch').onclick = (e) => {
  document.body.classList.toggle('dark')
  e.currentTarget.classList.toggle('on')
}
const q = new URLSearchParams(location.search)
if (q.get('hood') === '1') hood(true)
if (q.get('dark') !== '0') {
  document.body.classList.add('dark')
  document.getElementById('darkSwitch').classList.add('on')
}
if (q.get('view')) go(q.get('view'))

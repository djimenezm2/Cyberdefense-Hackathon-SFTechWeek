// MODO DEMO: simula al backend con EXACTAMENTE las formas de los fixtures del repo.
// Todo pasa por los mismos adaptadores que usa el modo real.

const iso = (t = Date.now()) => new Date(t).toISOString()
const pick = (a) => a[Math.floor(Math.random() * a.length)]
const ATTACKER = '198.51.100.23'

export const SURFACE = [
  { id: 'login', name: '/rest/user/login', kind: 'endpoint', status: 'ok', rps: 6 },
  { id: 'search', name: '/rest/products/search', kind: 'endpoint', status: 'ok', rps: 21 },
  { id: 'basket', name: '/rest/basket/:id', kind: 'endpoint', status: 'ok', rps: 12 },
  { id: 'cards', name: '/api/Cards', kind: 'endpoint', status: 'ok', rps: 3 },
  { id: 'users', name: '/api/Users', kind: 'endpoint', status: 'ok', rps: 4 },
  { id: 'feedback', name: '/api/Feedbacks', kind: 'endpoint', status: 'ok', rps: 2 },
  { id: 'admin', name: '/rest/admin', kind: 'endpoint', status: 'ok', rps: 1 },
  { id: 'ftp', name: '/ftp', kind: 'endpoint', status: 'ok', rps: 1 },
  { id: 'server', name: 'Juice Shop · Akash', kind: 'service', status: 'ok', rps: 48 },
  { id: 'db', name: 'ClickHouse · telemetry', kind: 'service', status: 'ok', rps: 31 },
]
export const ROUTE_TO_SURFACE = Object.fromEntries(SURFACE.map((s) => [s.name, s.id]))

const NORMAL = [
  () => ({ method: 'GET', route: '/rest/products/search', status: 200, ip: '203.0.113.' + (2 + Math.floor(Math.random() * 40)), principal_id: '', auth_outcome: 'none' }),
  () => ({ method: 'GET', route: '/rest/basket/:id', status: 200, ip: '198.51.100.' + (60 + Math.floor(Math.random() * 30)), principal_id: String(10 + Math.floor(Math.random() * 9)), auth_outcome: 'accepted' }),
  () => ({ method: 'POST', route: '/rest/user/login', status: 200, ip: '192.0.2.' + (5 + Math.floor(Math.random() * 50)), principal_id: String(10 + Math.floor(Math.random() * 9)), auth_outcome: 'login_success' }),
  () => ({ method: 'GET', route: '/api/Feedbacks', status: 200, ip: '203.0.113.' + (2 + Math.floor(Math.random() * 40)), principal_id: '', auth_outcome: 'none' }),
  () => ({ method: 'GET', route: '/rest/products/search', status: 200, ip: '203.0.113.7', principal_id: '', auth_outcome: 'none' }),
]
const OK_RATIONALE = [
  'Traffic within baseline; no auth anomalies.',
  'Normal mix of logins and catalog reads.',
  'No repeated failures from a single client.',
  'Login success rate in line with the last hour.',
]
const HEARTBEATS = [
  'Ingested the last request window into ClickHouse',
  'Semgrep baseline on main · 0 new findings',
  'Checked juiceshop.rootlane.xyz · healthy',
  'Compared login failures to baseline · normal',
  'Refreshed Senso auth policy context',
]

function traceId() { return Math.random().toString(16).slice(2, 6) }
function event(base, t = Date.now()) {
  return { ts: iso(t), trace_id: traceId(), latency_ms: 12 + Math.floor(Math.random() * 30), param_flags: [], ...base }
}

// ── historia previa: 30 ventanas del analizador (5 min) y un incidente ya resuelto ──
export function seedWindows() {
  const now = Date.now(), out = []
  for (let i = 30; i >= 1; i--) {
    const end = now - (i - 1) * 10000 - 10000, start = end - 10000
    const watch = i === 22 || i === 9
    out.push({ window_start: iso(start), window_end: iso(end), verdict: watch ? 'watch' : 'ignore', model: 'akashml/glm',
      rationale: watch ? 'A burst of product searches with quote characters; below threshold.' : pick(OK_RATIONALE) })
  }
  return out
}

export function seedEvents() {
  const now = Date.now()
  return Array.from({ length: 14 }, (_, i) => event(pick(NORMAL)(), now - (14 - i) * 900))
}

export function pastIncident() {
  const t = Date.now() - 26 * 3600 * 1000
  const at = (s) => iso(t + s * 1000)
  return {
    id: 'inc_00',
    title: 'SQL injection probe on product search',
    status: 'applied',
    severity: 'high',
    category: 'injection',
    opened_at: at(0),
    guild_session_id: 'gs_71a',
    summary: 'Search queries with SQL meta characters returned rows outside the product table.',
    timeline: [
      { ts: at(-8), method: 'GET', route: '/rest/products/search', status: 200, principal_id: '', ip: '203.0.113.88', note: "q=')) UNION SELECT email,password FROM Users--" },
    ],
    steps: [
      { ts: at(4), kind: 'query', summary: 'Pulled 112 requests from the window for IP 203.0.113.88', outcome: 'ok' },
      { ts: at(7), kind: 'context', summary: 'Senso: all database access must use bound parameters', outcome: 'ok' },
      { ts: at(11), kind: 'semgrep', summary: '1 finding in routes/search.ts', outcome: 'ok' },
      { ts: at(49), kind: 'verify', summary: 'Replica: injection returned users before patch, 0 rows after; regression 6/6', outcome: 'ok' },
      { ts: at(52), kind: 'propose', summary: 'Proposal p_19c0 ready for approval', outcome: 'ok' },
      { ts: at(53), kind: 'approval', summary: 'Approved by David', outcome: 'ok' },
      { ts: at(58), kind: 'apply', summary: 'PR opened on the fork; production replay now rejected', outcome: 'ok' },
    ],
    hypothesis: {
      text: 'The search criteria is concatenated into raw SQL, so quote characters break out of the LIKE clause.',
      evidence: [
        { kind: 'event', ref: 'trace 7e21', text: '200 with Users columns in a product search' },
        { kind: 'code', ref: 'routes/search.ts:23', text: 'string-built SQL with user input' },
        { kind: 'context', ref: 'senso:db-policy', text: 'Policy: bound parameters only' },
      ],
    },
    verification: {
      replica_before: { status: 200, summary: 'issue reproduced' },
      replica_after: { status: 400, summary: 'query rejected' },
      regression: { passed: 6, failed: 0 }, semgrep_old: 1, semgrep_new: 0,
    },
    proposal: {
      proposal_hash: 'p_19c0',
      diff: "--- a/routes/search.ts\n+++ b/routes/search.ts\n@@ -22,3 +22,4 @@\n   const criteria = req.query.q ?? ''\n-  models.sequelize.query(`SELECT * FROM Products WHERE name LIKE '%${criteria}%'`)\n+  models.sequelize.query('SELECT * FROM Products WHERE name LIKE :q',\n+    { replacements: { q: `%${criteria}%` } })\n   .then(([products]) => res.json(products))\n",
      rule_yaml: 'rules:\n  - id: rootlane-raw-sql-template\n    message: SQL built from a template string\n    severity: ERROR\n    languages: [typescript]\n    pattern: sequelize.query(`...${$X}...`)\n',
      report: 'Root cause, evidence and verification summary written by the agent.',
    },
    approval: { approver: 'David', decision: 'approve', ts: at(53), reason: null, proposal_hash: 'p_19c0' },
    apply: { pr_url: 'https://github.com/djimenezm2/juice-shop/pulls', production_status: 400, production_summary: 'replayed attack rejected', variants: [] },
  }
}

// ── el ataque del demo: inc_01 de los fixtures, con el flujo real del toolbox ──
const STEPS = [
  [7, 'query', `Pulled 40 requests from the window for IP ${ATTACKER}`],
  [8.5, 'context', 'Senso: auth policy requires signature verification with a pinned algorithm'],
  [9.5, 'read_source', 'Read lib/insecurity.ts'],
  [10.5, 'semgrep', '2 findings in lib/insecurity.ts'],
  [12.5, 'replay', 'Replica: unsigned token for principal 22 → 200 (reproduced)'],
  [15, 'verify', 'Replica: issue reproduced before patch, closed after; regression 6/6'],
  [16, 'propose', 'Proposal p_3e7a ready for approval'],
]

function inc01(t0, stepCount, extra = {}) {
  const at = (s) => iso(t0 + s * 1000)
  const d = {
    id: 'inc_01',
    title: 'Requests served for an identity that never authenticated',
    status: 'investigating',
    severity: 'high',
    category: 'identity',
    opened_at: at(6),
    guild_session_id: 'gs_9c1',
    summary: 'Authenticated endpoints answered 200 for a principal with no prior login from this client.',
    timeline: [
      { ts: at(2), method: 'GET', route: '/rest/basket/:id', status: 200, principal_id: '22', ip: ATTACKER, note: 'no prior login for principal 22' },
      { ts: at(3.5), method: 'GET', route: '/api/Cards', status: 200, principal_id: '22', ip: ATTACKER, note: null },
    ],
    steps: STEPS.slice(0, stepCount).map(([sec, kind, summary]) => ({ ts: at(sec), kind, summary, outcome: 'ok' })),
    hypothesis: null, verification: null, proposal: null, approval: null, apply: null,
  }
  if (stepCount >= 4) d.hypothesis = {
    text: 'Credential verification does not pin the expected algorithm, so the server resolves identities it never authenticated.',
    evidence: [
      { kind: 'event', ref: 'trace c9d4', text: '200 on /rest/basket/:id for principal 22 with no login' },
      { kind: 'code', ref: 'lib/insecurity.ts:54', text: 'verification call without an algorithm allow-list' },
      { kind: 'context', ref: 'senso:auth-policy', text: 'Policy: tokens must be verified with a pinned algorithm' },
    ],
  }
  if (stepCount >= 6) d.verification = {
    replica_before: { status: 200, summary: 'issue reproduced' },
    replica_after: { status: 401, summary: 'request rejected' },
    regression: { passed: 6, failed: 0 }, semgrep_old: 2, semgrep_new: 0,
  }
  if (stepCount >= 7) {
    d.status = 'pending_approval'
    d.proposal = {
      proposal_hash: 'p_3e7a',
      diff: "--- a/lib/insecurity.ts\n+++ b/lib/insecurity.ts\n@@ -54 +54 @@\n-  verify(token)\n+  verify(token, { algorithms: ['RS256'] })\n",
      rule_yaml: "rules:\n  - id: rootlane-unpinned-token-verification\n    message: Token verification without an algorithm allow-list\n    severity: ERROR\n    languages: [typescript]\n    pattern: verify($T)\n",
      report: 'Root cause, evidence and verification summary written by the agent.',
    }
  }
  return { ...d, ...extra, steps: [...d.steps, ...(extra.steps ?? [])] }
}

export function createMockStream(emit) {
  let attacking = false, enabled = true, waitingApproval = false, t0 = 0
  const timers = []
  let windowStart = Date.now()

  const reqTimer = setInterval(() => {
    if (!enabled) return
    if (Math.random() < 0.75) emit('event', event(pick(NORMAL)()))
  }, 650)

  const metricTimer = setInterval(() => {
    emit('metric', {
      t: iso(), total: Math.round(40 + Math.random() * 22 + (attacking ? 32 : 0)),
      errors: Math.round(Math.random() * 2 + (attacking ? 4 : 0)),
      auth_rejected: Math.round(Math.random() * 1.2 + (attacking ? 3 : 0)),
    })
  }, 2000)

  const winTimer = setInterval(() => {
    if (!enabled || attacking) return
    const end = Date.now()
    emit('verdict', { window_start: iso(windowStart), window_end: iso(end), verdict: 'ignore', model: 'akashml/glm', rationale: pick(OK_RATIONALE) })
    windowStart = end
  }, 10000)

  const beatTimer = setInterval(() => {
    if (!enabled || attacking) return
    emit('heartbeat', { message: pick(HEARTBEATS) })
  }, 4200)

  const at = (sec, fn) => timers.push(setTimeout(fn, sec * 1000))
  const action = (operation, duration_ms) => emit('action', { ts: iso(), incident_id: 'inc_01', operation, outcome: 'ok', duration_ms, on_behalf_of: 'rootlane-agent (Guild session gs_9c1)' })

  return {
    setEnabled(v) { enabled = v },
    drill() {
      if (attacking || !enabled) return
      attacking = true
      t0 = Date.now()
      for (let k = 0; k < 6; k++) at(k * 0.3, () => emit('event', event({ method: 'POST', route: '/rest/user/login', status: 401, ip: ATTACKER, principal_id: '', auth_outcome: 'login_failure', param_flags: ['meta_chars'] })))
      at(1.2, () => emit('surface', { id: 'login', status: 'warn' }))
      at(2, () => { emit('event', event({ method: 'GET', route: '/rest/basket/:id', status: 200, ip: ATTACKER, principal_id: '22', auth_outcome: 'accepted' })); emit('surface', { id: 'basket', status: 'warn' }) })
      at(3.5, () => { emit('event', event({ method: 'GET', route: '/api/Cards', status: 200, ip: ATTACKER, principal_id: '22', auth_outcome: 'accepted' })); emit('surface', { id: 'cards', status: 'warn' }) })
      at(4, () => emit('verdict', { window_start: iso(windowStart), window_end: iso(), verdict: 'watch', model: 'akashml/glm', rationale: 'One IP with an unusual mix of failed logins; below threshold.' }))
      at(6, () => {
        windowStart = Date.now()
        emit('verdict', { window_start: iso(t0 + 4000), window_end: iso(), verdict: 'escalate', model: 'akashml/glm', rationale: 'Authenticated responses for an identity that never logged in, from the same IP.' })
        emit('surface', { id: 'basket', status: 'bad' }); emit('surface', { id: 'cards', status: 'bad' })
        emit('incident', inc01(t0, 0))
      })
      STEPS.forEach(([sec], idx) => at(sec, () => {
        if (STEPS[idx][1] === 'query') action('query_events', 140)
        if (STEPS[idx][1] === 'semgrep') action('semgrep_scan', 4100)
        if (STEPS[idx][1] === 'replay') action('reproduce', 2300)
        if (STEPS[idx][1] === 'verify') action('verify_patch', 38000)
        if (STEPS[idx][1] === 'propose') { action('propose', 90); waitingApproval = true }
        emit('incident', inc01(t0, idx + 1))
      }))
    },
    // Lo que en producción hace el toolbox al aprobar: apply → PR → redeploy → replay = 401
    approve(id, approver) {
      if (id !== 'inc_01' || !waitingApproval) return
      waitingApproval = false
      const now = Date.now()
      const approval = { approver, decision: 'approve', ts: iso(now), reason: null, proposal_hash: 'p_3e7a' }
      const s = (sec, kind, summary) => ({ ts: iso(now + sec * 1000), kind, summary, outcome: 'ok' })
      emit('incident', inc01(t0, 7, { status: 'applying', approval, steps: [s(0, 'approval', `Approved by ${approver}`)] }))
      at(1.5, () => action('apply', 4200))
      at(4, () => {
        emit('incident', inc01(t0, 7, {
          status: 'applied', approval,
          apply: { pr_url: 'https://github.com/djimenezm2/juice-shop/pulls', production_status: 401, production_summary: 'replayed attack rejected in production', variants: [] },
          steps: [s(0, 'approval', `Approved by ${approver}`), s(4, 'apply', 'PR opened on the fork; production redeployed; replay → 401'), s(4.5, 'lesson', 'Lesson saved to Senso')],
        }))
        emit('event', event({ method: 'GET', route: '/rest/basket/:id', status: 401, ip: ATTACKER, principal_id: '22', auth_outcome: 'rejected' }))
        ;['login', 'basket', 'cards'].forEach((sid) => emit('surface', { id: sid, status: 'ok' }))
        attacking = false
      })
    },
    reject(id, approver, reason) {
      if (id !== 'inc_01' || !waitingApproval) return
      waitingApproval = false
      emit('incident', inc01(t0, 7, { status: 'rejected', approval: { approver, decision: 'reject', reason, ts: iso(), proposal_hash: 'p_3e7a' }, steps: [{ ts: iso(), kind: 'approval', summary: `Rejected by ${approver}: ${reason}`, outcome: 'refused' }] }))
      attacking = false
    },
    close() { [reqTimer, metricTimer, winTimer, beatTimer].forEach(clearInterval); timers.forEach(clearTimeout) },
  }
}

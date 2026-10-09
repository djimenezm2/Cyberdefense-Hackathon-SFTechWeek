// Cerebro de la UI.
// MODO DEMO (sin VITE_API_BASE_URL): datos simulados con la forma exacta de ui/fixtures.
// MODO REAL: lee el toolbox (docs/ui/dashboard-contract.md): carga inicial + SSE /api/stream,
// y si el stream se cae, polling cada 2 s.
import { useEffect, useReducer, useRef, useCallback } from 'react'
import { ENDPOINTS, POLL_MS } from './contract'
import { adaptAction, adaptEvent, adaptIncident, adaptIncidentRow, adaptOverview, adaptStep, adaptWindow, isWorking, isClosed } from './adapters'
import { createMockStream, pastIncident, seedEvents, seedWindows, SURFACE, ROUTE_TO_SURFACE } from './mock'

export const API_URL = (import.meta.env.VITE_API_BASE_URL || import.meta.env.VITE_API_URL || '').replace(/\/$/, '')
export const MODE = API_URL ? 'live' : 'demo'
// Build-time flag so demo-only copy is dropped from live bundles.
export const IS_DEMO = !(import.meta.env.VITE_API_BASE_URL || import.meta.env.VITE_API_URL)

const AUTH_KEY = 'rootlane.admin'
export function readAuth() { try { return JSON.parse(localStorage.getItem(AUTH_KEY)) ?? { name: '', token: '' } } catch { return { name: '', token: '' } } }
export function writeAuth(a) { try { a ? localStorage.setItem(AUTH_KEY, JSON.stringify(a)) : localStorage.removeItem(AUTH_KEY) } catch { /* ok */ } }

let seq = 0
const fid = () => 'f' + seq++

function seedMetrics() {
  const now = Date.now()
  return Array.from({ length: 30 }, (_, i) => ({ t: now - (30 - i) * 2000, total: Math.round(42 + Math.random() * 20), errors: Math.round(Math.random() * 2), authRejected: Math.round(Math.random()) }))
}

function makeInitial() {
  const demo = MODE === 'demo'
  const past = demo ? adaptIncident(pastIncident()) : null
  return {
    mode: MODE,
    connected: demo,
    streaming: false,
    monitoring: true,
    needToken: false,
    lastScan: Date.now(),
    metrics: demo ? seedMetrics() : [],
    summary: {
      repo: 'djimenezm2/juice-shop', infra: 'juiceshop.rootlane.xyz',
      openIncidents: 0, analyzer: demo ? { verdict: 'ignore', model: 'akashml/glm', lastWindow: Date.now() } : null, agentRunning: false,
    },
    requests: demo ? seedEvents().map(adaptEvent).reverse() : [],
    windows: demo ? seedWindows().map(adaptWindow) : [],
    actions: [],
    surface: SURFACE.map((s) => ({ ...s, rps: demo ? s.rps : 0 })),
    incidents: past ? { [past.id]: past } : {},
    feed: past ? [{ kind: 'incident', id: fid(), incidentId: past.id, ts: past.ts }] : [],
  }
}

const pushFeed = (feed, item) => [{ id: fid(), ts: Date.now(), ...item }, ...feed].slice(0, 60)

function upsertIncident(state, inc) {
  const prev = state.incidents[inc.id]
  const incidents = { ...state.incidents, [inc.id]: inc }
  const feed = prev ? state.feed : pushFeed(state.feed, { kind: 'incident', incidentId: inc.id })
  const openIncidents = Object.values(incidents).filter((i) => !isClosed(i)).length
  return { ...state, incidents, feed, summary: { ...state.summary, openIncidents } }
}

function reducer(state, { type, data }) {
  switch (type) {
    case 'connected': return { ...state, connected: data }
    case 'streaming': return { ...state, streaming: data }
    case 'monitoring': return { ...state, monitoring: data }
    case 'needToken': return { ...state, needToken: data }
    case 'summary': return { ...state, summary: { ...state.summary, ...data } }
    case 'metric': return { ...state, lastScan: Date.now(), metrics: [...state.metrics, data].slice(-40) }
    case 'metrics.replace': return { ...state, lastScan: Date.now(), metrics: data }
    case 'event': return { ...state, lastScan: Date.now(), requests: [data, ...state.requests].slice(0, 60) }
    case 'events.merge': {
      const seen = new Set(state.requests.map((r) => r.id))
      const fresh = data.filter((e) => !seen.has(e.id))
      if (!fresh.length) return { ...state, lastScan: Date.now() }
      return { ...state, lastScan: Date.now(), requests: [...fresh, ...state.requests].sort((a, b) => b.ts - a.ts).slice(0, 60) }
    }
    case 'verdict': {
      if (state.windows.some((w) => w.start === data.start)) return state
      return { ...state, windows: [...state.windows, data].slice(-30), summary: { ...state.summary, analyzer: { verdict: data.verdict, model: data.model, lastWindow: data.end } } }
    }
    case 'windows.replace': return { ...state, windows: [...data].sort((a, b) => a.start - b.start).slice(-30) }
    case 'heartbeat':
      if (!state.monitoring) return state
      return { ...state, feed: pushFeed(state.feed, { kind: 'heartbeat', message: data.message }) }
    case 'action': {
      if (state.actions.some((a) => a.id === data.id)) return state
      return { ...state, actions: [data, ...state.actions].slice(0, 200), feed: pushFeed(state.feed, { kind: 'op', op: data }) }
    }
    case 'surface': return { ...state, surface: state.surface.map((s) => (s.id === data.id ? { ...s, ...data } : s)) }
    case 'incident': return upsertIncident(state, adaptIncident(data, state.incidents[data.id]))
    case 'incident.row': return upsertIncident(state, adaptIncidentRow(data, state.incidents[data.id]))
    case 'step': {
      const inc = state.incidents[data.incident_id]
      if (!inc) return state
      const st = adaptStep(data)
      if (inc.steps.some((x) => x.ts === st.ts && x.kind === st.kind)) return state
      return upsertIncident(state, { ...inc, steps: [...inc.steps, st] })
    }
    default: return state
  }
}

// Estado del agente para la barra superior
export function deriveStatus(state) {
  if (!state.monitoring) return 'paused'
  const active = Object.values(state.incidents).filter(isWorking).sort((a, b) => b.ts - a.ts)[0]
  if (!active) return state.summary.agentRunning ? 'investigating' : 'watching'
  if (active.status === 'pending_approval') return 'approval'
  if (active.status === 'applying') return 'applying'
  return 'investigating'
}

async function getJSON(path) {
  const r = await fetch(API_URL + path)
  if (!r.ok) throw new Error(`${path} → ${r.status}`)
  return r.json()
}

export function useAgent() {
  const [state, dispatch] = useReducer(reducer, undefined, makeInitial)
  const mockRef = useRef(null)

  useEffect(() => {
    if (MODE === 'demo') {
      mockRef.current = createMockStream((type, raw) => {
        if (type === 'metric') dispatch({ type, data: adaptOverview({ rps_series: [raw] }).metrics[0] })
        else if (type === 'event') dispatch({ type, data: adaptEvent(raw) })
        else if (type === 'verdict') dispatch({ type, data: adaptWindow(raw) })
        else if (type === 'action') dispatch({ type, data: adaptAction(raw) })
        else dispatch({ type, data: raw })
      })
      return () => mockRef.current.close()
    }

    // ── MODO REAL ──
    let stop = false, es = null, lastEventTs = null
    const loadIncident = (id) => getJSON(ENDPOINTS.incident(id)).then((d) => !stop && dispatch({ type: 'incident', data: d })).catch(() => {})

    const pollOverview = () => getJSON(ENDPOINTS.overview).then((o) => {
      if (stop) return
      dispatch({ type: 'connected', data: true })
      const s = adaptOverview(o)
      dispatch({ type: 'metrics.replace', data: s.metrics })
      dispatch({ type: 'summary', data: { analyzer: s.analyzer ?? undefined, agentRunning: s.agentRunning } })
    }).catch(() => dispatch({ type: 'connected', data: false }))

    const pollEvents = () => getJSON(ENDPOINTS.events(lastEventTs)).then((list) => {
      if (stop || !Array.isArray(list) || !list.length) return
      const evs = list.map(adaptEvent)
      lastEventTs = list.reduce((m, e) => (e.ts > m ? e.ts : m), lastEventTs ?? '')
      dispatch({ type: 'events.merge', data: evs })
      // pinta el mapa con las rutas que ven respuestas raras en los últimos eventos
      const hot = {}
      evs.slice(-30).forEach((e) => {
        const id = ROUTE_TO_SURFACE[e.route]; if (!id) return
        if (e.auth_outcome === 'login_failure' || e.param_flags?.length) hot[id] = 'warn'
      })
      Object.entries(hot).forEach(([id, status]) => dispatch({ type: 'surface', data: { id, status } }))
    }).catch(() => {})

    const pollWindows = () => getJSON(ENDPOINTS.windows).then((w) => !stop && dispatch({ type: 'windows.replace', data: w.map(adaptWindow) })).catch(() => {})
    const pollActions = () => getJSON(ENDPOINTS.actions()).then((a) => !stop && [...a].sort((x, y) => (x.ts > y.ts ? 1 : -1)).forEach((x) => dispatch({ type: 'action', data: adaptAction(x) }))).catch(() => {})
    const pollIncidents = () => getJSON(ENDPOINTS.incidents).then((rows) => {
      if (stop) return
      rows.forEach((r) => { dispatch({ type: 'incident.row', data: r }); loadIncident(r.id) })
    }).catch(() => {})

    // carga inicial
    pollOverview(); pollEvents(); pollWindows(); pollActions(); pollIncidents()

    // stream en vivo
    const openStream = () => {
      try {
        es = new EventSource(API_URL + ENDPOINTS.stream)
        es.onopen = () => dispatch({ type: 'streaming', data: true })
        es.onerror = () => dispatch({ type: 'streaming', data: false })
        es.addEventListener('verdict', (e) => dispatch({ type: 'verdict', data: adaptWindow(JSON.parse(e.data)) }))
        es.addEventListener('step', (e) => { const d = JSON.parse(e.data); dispatch({ type: 'step', data: d }); loadIncident(d.incident_id) })
        es.addEventListener('incident_update', (e) => { const d = JSON.parse(e.data); dispatch({ type: 'incident.row', data: d }); loadIncident(d.id) })
      } catch { dispatch({ type: 'streaming', data: false }) }
    }
    openStream()

    // los eventos de peticiones y el overview no vienen por el stream: siempre se consultan.
    // incidentes/ventanas/acciones solo se consultan seguido si el stream está caído.
    let tick = 0
    const t = setInterval(() => {
      tick++
      pollEvents()
      if (tick % 3 === 0) { pollOverview(); pollActions() }
      if (!es || es.readyState !== 1) { pollIncidents(); pollWindows() }
    }, POLL_MS)
    return () => { stop = true; clearInterval(t); es?.close() }
  }, [])

  const drill = useCallback(() => { if (MODE === 'demo') mockRef.current?.drill() }, [])

  // Aprobar / rechazar: POST con X-Admin-Token. Si responde 401, se vuelve a pedir el token.
  const decide = useCallback(async (id, kind, reason) => {
    const auth = readAuth()
    const approver = auth.name || 'Judge'
    if (MODE === 'demo') {
      if (kind === 'approve') mockRef.current?.approve(id, approver)
      else mockRef.current?.reject(id, approver, reason || 'Rejected from the dashboard')
      return { ok: true }
    }
    // Signed in with GitHub: the Vercel function /api/auth adds the admin token server-side
    // and records the GitHub login as approver.
    if (auth.github) {
      const g = await fetch(`/api/auth?a=decide&id=${encodeURIComponent(id)}&kind=${kind}`, {
        method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: reason || 'Rejected from the dashboard' }),
      }).catch(() => null)
      if (!g) return { ok: false, error: 'Could not reach the API.' }
      if (g.status === 401) return { ok: false, error: 'Your GitHub session expired. Sign out and sign in again.' }
      if (!g.ok) return { ok: false, error: `The API answered ${g.status}.` }
      const d = await g.json().catch(() => null)
      if (d?.id) dispatch({ type: 'incident', data: d })
      return { ok: true }
    }
    const r = await fetch(API_URL + (kind === 'approve' ? ENDPOINTS.approve(id) : ENDPOINTS.reject(id)), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Admin-Token': auth.token || '' },
      body: JSON.stringify(kind === 'approve' ? { approver } : { approver, reason: reason || 'Rejected from the dashboard' }),
    }).catch(() => null)
    if (!r) return { ok: false, error: 'Could not reach the API.' }
    if (r.status === 401) { dispatch({ type: 'needToken', data: true }); return { ok: false, error: 'The admin token was not accepted. Enter it again.' } }
    if (!r.ok) return { ok: false, error: `The API answered ${r.status}.` }
    const detail = await r.json().catch(() => null)
    if (detail?.id) dispatch({ type: 'incident', data: detail })
    return { ok: true }
  }, [])

  const approve = useCallback((id) => decide(id, 'approve'), [decide])
  const reject = useCallback((id, reason) => decide(id, 'reject', reason), [decide])
  const tokenSaved = useCallback(() => dispatch({ type: 'needToken', data: false }), [])

  // El backend no tiene endpoint para pausar la revisión: este interruptor solo pausa la vista.
  const setMonitoring = useCallback((enabled) => {
    dispatch({ type: 'monitoring', data: enabled })
    if (MODE === 'demo') mockRef.current?.setEnabled(enabled)
  }, [])

  return { state: { ...state, status: deriveStatus(state) }, drill, approve, reject, setMonitoring, tokenSaved }
}

// Convierte las respuestas del toolbox (formato de ui/fixtures) al formato que usa la UI.
import { KIND_TO_PHASE } from './contract'

const ms = (iso) => (iso ? Date.parse(iso) : Date.now())

// "--- a/x\n+++ b/x\n@@ -54 +54 @@\n-  a\n+  b\n"  →  { file, rows: [{ op, line, text }] }
export function parseUnifiedDiff(diff = '') {
  const rows = []
  let file = '', oldLn = 0, newLn = 0
  for (const raw of diff.split('\n')) {
    if (raw.startsWith('+++ ')) { file = raw.slice(4).replace(/^b\//, ''); continue }
    if (raw.startsWith('--- ')) continue
    const h = raw.match(/^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/)
    if (h) { oldLn = +h[1]; newLn = +h[2]; continue }
    if (!raw) continue
    const op = raw[0] === '+' ? '+' : raw[0] === '-' ? '-' : ' '
    const text = raw.slice(1)
    if (op === '-') rows.push({ op, line: oldLn++, text })
    else if (op === '+') rows.push({ op, line: newLn++, text })
    else { rows.push({ op, line: newLn, text }); oldLn++; newLn++ }
  }
  return { file, rows }
}

export const adaptStep = (s) => ({ kind: s.kind, phase: KIND_TO_PHASE[s.kind] ?? null, message: s.summary, ts: ms(s.ts), outcome: s.outcome ?? 'ok' })

// apply del backend (ApplyResult): { pr_url, production_status, production_summary, variants }
function adaptApply(a, steps) {
  if (!a) return a
  const applyStep = [...(steps ?? [])].reverse().find((s) => s.kind === 'apply')
  return {
    ...a,
    ts: a.ts ?? applyStep?.ts ?? null,
    production: a.production ?? (a.production_status != null ? { status: a.production_status, summary: a.production_summary ?? '' } : null),
    variants: a.variants ?? [],
  }
}

export function adaptIncident(d, prev) {
  const parsed = d.proposal?.diff ? parseUnifiedDiff(d.proposal.diff) : null
  return {
    ...prev,
    id: d.id,
    title: d.title ?? prev?.title,
    severity: d.severity ?? prev?.severity,
    category: d.category ?? prev?.category,
    summary: d.summary ?? prev?.summary,
    ts: d.opened_at ? ms(d.opened_at) : prev?.ts ?? Date.now(),
    status: d.status ?? prev?.status ?? 'investigating',
    session: d.guild_session_id ?? prev?.session,
    target: d.timeline?.[0]?.route ?? prev?.target ?? '',
    timeline: d.timeline ? d.timeline.map((t) => ({ ...t, ts: ms(t.ts) })) : prev?.timeline ?? [],
    steps: d.steps ? d.steps.map(adaptStep) : prev?.steps ?? [],
    hypothesis: d.hypothesis !== undefined ? d.hypothesis : prev?.hypothesis ?? null,
    verification: d.verification !== undefined ? d.verification : prev?.verification ?? null,
    patch: parsed
      ? { file: parsed.file, diff: parsed.rows, hash: d.proposal.proposal_hash, ruleYaml: d.proposal.rule_yaml, report: d.proposal.report }
      : prev?.patch ?? null,
    approval: d.approval !== undefined ? d.approval : prev?.approval ?? null,
    apply: d.apply !== undefined ? adaptApply(d.apply, d.steps) : prev?.apply ?? null,
    detailed: d.steps !== undefined || prev?.detailed,
  }
}

// incident_update del stream o fila de /api/incidents (sin detalle)
export const adaptIncidentRow = (r, prev) => adaptIncident({ id: r.id, title: r.title, status: r.status, severity: r.severity, category: r.category, opened_at: r.opened_at }, prev)

export function adaptOverview(s) {
  return {
    metrics: (s.rps_series ?? []).map((p) => ({ t: ms(p.t), total: p.total, errors: p.errors, authRejected: p.auth_rejected })),
    openIncidents: s.open_incidents ?? 0,
    analyzer: s.analyzer ? { verdict: s.analyzer.verdict, model: s.analyzer.model, lastWindow: ms(s.analyzer.last_window) } : null,
    agentRunning: !!s.agent?.running,
    agentIncident: s.agent?.incident_id ?? null,
  }
}

export const adaptWindow = (w) => ({ start: ms(w.window_start), end: ms(w.window_end), verdict: w.verdict, model: w.model, rationale: w.rationale })
export const adaptEvent = (e) => ({ ...e, ts: ms(e.ts), id: (e.trace_id ?? '') + e.ts })
export const adaptAction = (a) => ({ ...a, ts: ms(a.ts), id: a.operation + a.ts + (a.incident_id ?? '') })

// El incidente cuenta como "en curso" mientras el agente o la aprobación no terminen
export const isWorking = (inc) => ['investigating', 'pending_approval', 'applying'].includes(inc?.status)
export const isClosed = (inc) => ['applied', 'not_reproduced', 'fix_failed', 'rejected'].includes(inc?.status)

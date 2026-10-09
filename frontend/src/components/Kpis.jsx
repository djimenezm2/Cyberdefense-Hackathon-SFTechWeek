// Números grandes, sin animación. Vienen de /api/summary (rps_series, open_incidents, analyzer).
const VERDICT = {
  ignore: { t: 'Clear', c: 'text-ok' },
  watch: { t: 'Watch', c: 'text-warn' },
  escalate: { t: 'Escalate', c: 'text-bad' },
}

export default function Kpis({ state }) {
  const last = state.metrics.at(-1) ?? { total: 0, errors: 0, authRejected: 0 }
  const s = state.summary
  const v = VERDICT[s.analyzer?.verdict] ?? VERDICT.ignore
  const items = [
    { label: 'Requests · last 10 s', value: last.total },
    { label: 'Errors', value: last.errors, tone: last.errors > 3 ? 'text-warn' : '' },
    { label: 'Auth rejected', value: last.authRejected, tone: last.authRejected > 2 ? 'text-bad' : '' },
    { label: 'Open incidents', value: s.openIncidents, tone: s.openIncidents ? 'text-warn' : 'text-ok' },
    { label: 'Analyzer', value: v.t, tone: v.c, sub: s.analyzer?.model },
  ]
  return (
    <div className="grid grid-cols-2 gap-px overflow-hidden rounded-2xl border border-ink-700 bg-ink-700 lg:grid-cols-5">
      {items.map((k) => (
        <div key={k.label} className="bg-ink-900 px-4 py-3.5 last:col-span-2 lg:last:col-span-1">
          <div className="eyebrow">{k.label}</div>
          <div className={`num mt-1.5 truncate text-[26px] font-semibold leading-none tracking-tight ${k.tone || 'text-mute-100'}`}>{k.value}</div>
          {k.sub && <div className="mt-1 font-mono text-[10.5px] text-mute-400">{k.sub}</div>}
        </div>
      ))}
    </div>
  )
}

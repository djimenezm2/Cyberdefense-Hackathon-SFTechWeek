import { clock } from '../lib/format'

// Pantalla "Audit" del contrato: cada acción del agente (GET /api/actions)
export default function Audit({ actions }) {
  return (
    <div className="mx-auto max-w-5xl space-y-4">
      <header>
        <div className="eyebrow">Audit</div>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight">Every action the agent took</h1>
        <p className="mt-1 text-sm text-mute-300">{actions.length} actions recorded</p>
      </header>
      <div className="scroll-thin overflow-x-auto rounded-2xl border border-ink-700 bg-ink-900">
        <table className="w-full min-w-[640px] text-left text-[12.5px]">
          <thead className="font-mono text-[10.5px] uppercase tracking-[0.12em] text-mute-400">
            <tr>{['Time', 'Incident', 'Operation', 'Outcome', 'Duration', 'On behalf of'].map((h) => <th key={h} className="px-4 py-3 font-normal">{h}</th>)}</tr>
          </thead>
          <tbody>
            {actions.length === 0 && <tr><td colSpan={6} className="px-4 py-8 text-center text-mute-400">No agent actions yet. They appear here as soon as the agent calls the toolbox.</td></tr>}
            {actions.map((a) => (
              <tr key={a.id} className="border-t border-ink-800">
                <td className="num whitespace-nowrap px-4 py-2.5 font-mono text-mute-400">{clock(a.ts)}</td>
                <td className="px-4 py-2.5 font-mono text-mute-300">{a.incident_id}</td>
                <td className="px-4 py-2.5 font-mono text-mute-100">{a.operation}</td>
                <td className={`px-4 py-2.5 font-mono ${a.outcome === 'ok' ? 'text-ok' : 'text-bad'}`}>{a.outcome}</td>
                <td className="num px-4 py-2.5 font-mono text-mute-300">{a.duration_ms >= 1000 ? (a.duration_ms / 1000).toFixed(1) + ' s' : a.duration_ms + ' ms'}</td>
                <td className="px-4 py-2.5 text-mute-300">{a.on_behalf_of}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

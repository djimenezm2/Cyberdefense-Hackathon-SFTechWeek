import CodeCompare from './CodeCompare'
import { timeAgo } from '../lib/format'

// "Latest fix": el último incidente resuelto. Estático: solo se mueve si arrastras la línea.
export default function LatestFix({ incidents, onOpen }) {
  const inc = Object.values(incidents)
    .filter((i) => i.status === 'applied' && i.patch?.diff)
    .sort((a, b) => b.ts - a.ts)[0]
  if (!inc) return null
  const v = inc.verification
  const applied = inc.apply?.ts ? new Date(inc.apply.ts).getTime() : inc.steps.find((s) => s.kind === 'apply')?.ts
  const secs = applied ? Math.max(1, Math.round((applied - inc.ts) / 1000)) : null

  const proof = [
    v?.replica_before && v?.replica_after && { k: 'Replica', val: `${v.replica_before.status} → ${v.replica_after.status}`, sub: `${v.replica_before.summary} → ${v.replica_after.summary}` },
    v?.regression && { k: 'Regression', val: `${v.regression.passed}/${v.regression.passed + v.regression.failed}`, sub: 'tests passed' },
    v && v.semgrep_old != null && { k: 'Semgrep', val: `${v.semgrep_old} → ${v.semgrep_new}`, sub: 'findings' },
    secs && { k: 'Time to fix', val: secs < 120 ? `${secs}s` : `${Math.round(secs / 60)}m`, sub: inc.approval?.approver ? `approved by ${inc.approval.approver}` : 'detected → applied' },
  ].filter(Boolean)

  return (
    <section className="rounded-3xl border border-ink-700 bg-ink-900 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3 px-1 pb-4">
        <div className="min-w-0">
          <div className="eyebrow">Latest fix · {timeAgo(inc.ts)} · {inc.patch.hash}</div>
          <h3 className="mt-1.5 text-[17px] font-semibold tracking-tight">{inc.title}</h3>
          {inc.hypothesis?.text && <p className="mt-1 max-w-[70ch] text-[13px] leading-relaxed text-mute-300">{inc.hypothesis.text}</p>}
        </div>
        <button onClick={onOpen} className="shrink-0 rounded-lg border border-ink-700 px-3 py-1.5 text-xs text-mute-200 hover:border-ink-500">Full report</button>
      </div>

      <CodeCompare patch={inc.patch} className="h-[190px]" />

      {proof.length > 0 && (
        <dl className="mt-3 grid grid-cols-2 gap-px overflow-hidden rounded-2xl border border-ink-700 bg-ink-700 sm:grid-cols-4">
          {proof.map((p) => (
            <div key={p.k} className="bg-ink-900 px-3.5 py-3">
              <dt className="eyebrow">{p.k}</dt>
              <dd className="num mt-1 text-[18px] font-semibold text-mute-100">{p.val}</dd>
              <dd className="text-[11px] text-mute-400">{p.sub}</dd>
            </div>
          ))}
        </dl>
      )}
      <p className="mt-2 px-1 font-mono text-[10.5px] text-mute-400">Showing the fixed code. Move your mouse over it to see what it looked like before.</p>
    </section>
  )
}

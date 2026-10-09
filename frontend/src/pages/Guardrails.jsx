import { Check } from 'lucide-react'
import { GUARDRAILS } from '../lib/contract'

// Lo que el toolbox hace cumplir antes de tocar producción (docs/superpowers/specs/...-rootlane-design.md).
// Es de solo lectura: estas reglas viven en el backend, no en la UI.
export default function Guardrails() {
  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <header>
        <div className="eyebrow">Guardrails</div>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight" style={{ textWrap: 'balance' }}>What Rootlane must prove before it touches production</h1>
        <p className="mt-2 max-w-[62ch] text-sm leading-relaxed text-mute-300">
          Rootlane investigates and tests fixes on its own, all the time. Production only changes after every step below passes,
          and the toolbox enforces each one. The agent cannot skip them.
        </p>
      </header>
      <ol className="space-y-3">
        {GUARDRAILS.map((g, i) => (
          <li key={g.t} className="flex gap-4 rounded-2xl border border-ink-700 bg-ink-900 p-4">
            <span className="num flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-lime/40 font-mono text-xs text-lime">{i + 1}</span>
            <div>
              <div className="flex items-center gap-2 text-[15px] font-medium text-mute-100">{g.t} <Check className="h-4 w-4 text-ok" strokeWidth={3} /></div>
              <p className="mt-0.5 text-[13px] text-mute-400">{g.d}</p>
            </div>
          </li>
        ))}
      </ol>
      <p className="text-xs text-mute-400">Every call the agent makes is written to the audit log with its Guild session and outcome.</p>
    </div>
  )
}

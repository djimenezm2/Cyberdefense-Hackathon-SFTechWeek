import { useState } from 'react'
import { clock } from '../lib/format'

// Reemplaza al "Threat skyline": cada 10 s el analizador revisa la ventana de tráfico
// y da un veredicto (ok / watch / escalate). Aquí se ven las últimas 30 ventanas = 5 min.
const V = {
  ignore: { bar: 'bg-ink-600', h: 'h-3', chip: 'border-ink-600 text-mute-300', label: 'IGNORE' },
  watch: { bar: 'bg-warn', h: 'h-6', chip: 'border-warn/50 text-warn', label: 'WATCH' },
  escalate: { bar: 'bg-bad', h: 'h-9', chip: 'border-bad/60 text-bad', label: 'ESCALATE' },
}

export default function Analyzer({ windows }) {
  const [sel, setSel] = useState(null)
  const list = windows.slice(-30)
  const shown = sel ? [sel] : [...list].reverse().filter((w) => w.verdict !== 'ignore').slice(0, 2).concat([...list].reverse().slice(0, 1)).filter((w, i, a) => a.indexOf(w) === i).slice(0, 3)

  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <div className="eyebrow">Analyzer · every 10 seconds</div>
          <p className="mt-1 text-[12.5px] text-mute-300">Each bar is one 10-second window of traffic. Taller means the model wanted a closer look.</p>
        </div>
        <span className="hidden font-mono text-[10.5px] text-mute-400 sm:block">{list.at(-1)?.model}</span>
      </div>
      <div className="px-4 pb-4">
        <div className="flex h-10 items-end gap-[3px]" onMouseLeave={() => setSel(null)}>
          {list.map((w) => (
            <button key={w.start} onMouseEnter={() => setSel(w)} onFocus={() => setSel(w)}
              aria-label={`${clock(w.start)} to ${clock(w.end)}: ${w.verdict}`}
              className={`min-w-0 flex-1 rounded-sm ${V[w.verdict]?.bar ?? V.ignore.bar} ${V[w.verdict]?.h ?? 'h-3'} ${sel === w ? 'ring-1 ring-mute-100' : ''}`} />
          ))}
        </div>
        <div className="mt-1 flex justify-between font-mono text-[10px] text-mute-400">
          <span>{list[0] ? clock(list[0].start) : ''}</span><span>now</span>
        </div>
        <ul className="mt-3 space-y-2">
          {shown.map((w) => (
            <li key={'r' + w.start} className="flex items-start gap-3 text-[12.5px]">
              <span className={`mt-0.5 shrink-0 rounded border px-1.5 py-px font-mono text-[10px] ${V[w.verdict]?.chip}`}>{V[w.verdict]?.label}</span>
              <span className="num shrink-0 font-mono text-[11px] text-mute-400">{clock(w.start)}–{clock(w.end)}</span>
              <span className="min-w-0 text-mute-200">{w.rationale}</span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  )
}

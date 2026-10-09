import { Globe, Server } from 'lucide-react'

const STYLE = {
  ok: 'border-ink-700 bg-ink-850',
  warn: 'border-warn/50 bg-warn/[0.07]',
  bad: 'border-bad/60 bg-bad/[0.08]',
}
const LABEL = { ok: 'Healthy', warn: 'Suspicious', bad: 'Under attack' }

export default function SurfaceMap({ surface }) {
  const bad = surface.filter((s) => s.status !== 'ok').length
  return (
    <section className="panel">
      <div className="panel-head">
        <div className="eyebrow">Attack surface · {surface.length} assets watched</div>
        <span className={`font-mono text-[11px] ${bad ? 'text-bad' : 'text-ok'}`}>
          {bad ? `${bad} need attention` : 'All healthy'}
        </span>
      </div>
      <div className="grid grid-cols-2 gap-2 px-4 pb-4 sm:grid-cols-3 xl:grid-cols-5">
        {surface.map((s) => {
          const Icon = s.kind === 'service' ? Server : Globe
          return (
            <div key={s.id}
              className={`min-w-0 rounded-lg border px-3 py-2.5 ${STYLE[s.status]}`}>
              <div className="flex items-center justify-between gap-2">
                <Icon className="h-3.5 w-3.5 shrink-0 text-mute-400" />
                <span className={`h-2 w-2 rounded-full ${s.status === 'ok' ? 'bg-ok' : s.status === 'bad' ? 'bg-bad' : 'bg-warn'}`} />
              </div>
              <div className="mt-2 truncate font-mono text-[12px] text-mute-100" title={s.name}>{s.name}</div>
              <div className="mt-0.5 flex items-center justify-between font-mono text-[10.5px] text-mute-400">
                <span className={s.status === 'ok' ? '' : s.status === 'bad' ? 'text-bad' : 'text-warn'}>{LABEL[s.status]}</span>
                <span className="num">{s.rps} rps</span>
              </div>
            </div>
          )
        })}
      </div>
    </section>
  )
}

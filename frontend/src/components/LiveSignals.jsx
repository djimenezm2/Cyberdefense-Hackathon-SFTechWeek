import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis, ReferenceArea } from 'recharts'
import { clock } from '../lib/format'

const SERIES = [
  { key: 'total', label: 'Requests', color: '#8FA4F5', axis: 'left' },
  { key: 'authRejected', label: 'Auth rejected', color: '#F5A524', axis: 'right' },
  { key: 'errors', label: 'Errors', color: '#FF4D5E', axis: 'right' },
]

function Tip({ active, payload }) {
  if (!active || !payload?.length) return null
  const p = payload[0].payload
  return (
    <div className="rounded-lg border border-ink-600 bg-ink-850 px-3 py-2 font-mono text-[11px] shadow-xl">
      <div className="mb-1 text-mute-400">{clock(p.t)}</div>
      {SERIES.map((s) => (
        <div key={s.key} className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-sm" style={{ background: s.color }} />
          <span className="text-mute-300">{s.label}</span>
          <span className="num ml-auto pl-3 text-mute-100">{p[s.key]}</span>
        </div>
      ))}
    </div>
  )
}

export default function LiveSignals({ metrics }) {
  // Marca en rojo los segundos donde los logins se dispararon (anomalía)
  const anomalies = metrics.filter((m) => m.authRejected >= 3).map((m) => m.t)
  const a0 = anomalies[0], a1 = anomalies.at(-1)

  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <div className="eyebrow">Traffic · 10-second buckets</div>
        </div>
        <div className="flex flex-wrap gap-3">
          {SERIES.map((s) => (
            <span key={s.key} className="flex items-center gap-1.5 text-xs text-mute-300">
              <span className="h-2 w-2 rounded-sm" style={{ background: s.color }} /> {s.label}
            </span>
          ))}
        </div>
      </div>
      <div className="h-[210px] px-1 pb-2">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={metrics} margin={{ top: 8, right: 8, bottom: 0, left: -12 }}>
            <defs>
              {SERIES.map((s) => (
                <linearGradient key={s.key} id={'g-' + s.key} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={s.color} stopOpacity={0.28} />
                  <stop offset="100%" stopColor={s.color} stopOpacity={0} />
                </linearGradient>
              ))}
            </defs>
            <CartesianGrid stroke="#1E2530" strokeDasharray="2 4" vertical={false} />
            <XAxis dataKey="t" tickFormatter={clock} stroke="#3B4656" tick={{ fill: '#7C8798', fontSize: 10, fontFamily: 'DM Mono' }} minTickGap={60} />
            <YAxis yAxisId="left" stroke="#3B4656" tick={{ fill: '#7C8798', fontSize: 10, fontFamily: 'DM Mono' }} width={44} />
            <YAxis yAxisId="right" orientation="right" hide domain={[0, 20]} />
            <Tooltip content={<Tip />} cursor={{ stroke: '#3B4656' }} />
            {a0 && <ReferenceArea yAxisId="left" x1={a0} x2={a1} fill="#FF4D5E" fillOpacity={0.08} stroke="#FF4D5E" strokeOpacity={0.4} strokeDasharray="3 3"
              label={{ value: 'ANOMALY', position: 'insideTopLeft', fill: '#FF4D5E', fontSize: 10, fontFamily: 'DM Mono' }} />}
            {SERIES.map((s) => (
              <Area key={s.key} yAxisId={s.axis} type="monotone" dataKey={s.key} stroke={s.color} strokeWidth={1.6}
                fill={`url(#g-${s.key})`} isAnimationActive={false} dot={false} />
            ))}
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </section>
  )
}

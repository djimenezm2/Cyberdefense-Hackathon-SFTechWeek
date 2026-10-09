import { Compare } from './ui/compare'

// "Antes" (código vulnerable) y "después" (código parchado), armados desde el diff.
// Estilo sobrio: sin rellenos rojo/verde; solo una marca pequeña en las líneas que cambiaron.
function split(diff) {
  const before = diff.filter((d) => d.op !== '+')
  const after = diff.filter((d) => d.op !== '-')
  const n = Math.max(before.length, after.length, 4)
  const pad = (arr) => [...arr, ...Array.from({ length: n - arr.length }, () => ({ op: ' ', line: '', text: '' }))]
  return [pad(before), pad(after)]
}

function Pane({ rows, side, file }) {
  const isBefore = side === 'before'
  return (
    <div className="flex h-full flex-col bg-ink-950">
      <div className={`flex items-center gap-2 border-b border-ink-700 px-4 py-2.5 font-mono text-[10.5px] tracking-[0.12em] text-mute-400 ${isBefore ? '' : 'justify-end'}`}>
        <span className={`h-1.5 w-1.5 rounded-full ${isBefore ? 'bg-bad' : 'bg-ok'}`} />
        <span className="text-mute-200">{isBefore ? 'BEFORE' : 'AFTER'}</span>
        <span className="truncate">{file}</span>
      </div>
      <pre className="flex-1 overflow-hidden py-3 font-mono text-[12px] leading-[1.9]">
        {rows.map((d, i) => {
          const hot = isBefore ? d.op === '-' : d.op === '+'
          return (
            <div key={i} className={`flex whitespace-pre ${hot ? 'text-mute-100' : 'text-mute-400'}`}>
              <span className="inline-block w-12 shrink-0 select-none pr-3 text-right text-mute-400/50">{d.line}</span>
              <span className={`mr-2 inline-block w-2 select-none ${isBefore ? 'text-bad/80' : 'text-ok/80'}`}>{hot ? (isBefore ? '−' : '+') : ' '}</span>
              <span className={hot && isBefore ? 'line-through decoration-bad/50' : ''}>{d.text || ' '}</span>
            </div>
          )
        })}
      </pre>
    </div>
  )
}

export default function CodeCompare({ patch, className = 'h-[200px]' }) {
  if (!patch?.diff) return null
  const [before, after] = split(patch.diff)
  return (
    <Compare
      className={`rounded-2xl border border-ink-700 ${className}`}
      slideMode="hover"
      autoplay={false}
      sparkles={false}
      quiet
      initialSliderPercentage={2}
      first={<Pane rows={before} side="before" file={patch.file} />}
      second={<Pane rows={after} side="after" file={patch.file} />}
    />
  )
}

export const fmt = (n) => new Intl.NumberFormat('en-US').format(n)

export function timeAgo(ts) {
  const s = Math.max(0, Math.round((Date.now() - ts) / 1000))
  if (s < 5) return 'just now'
  if (s < 60) return `${s}s ago`
  const m = Math.round(s / 60)
  if (m < 60) return `${m}m ago`
  const h = Math.round(m / 60)
  if (h < 48) return `${h}h ago`
  return `${Math.round(h / 24)}d ago`
}

export const clock = (ts) =>
  new Date(ts).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })

export const toneText = { ok: 'text-ok', warn: 'text-warn', bad: 'text-bad', agent: 'text-agent', off: 'text-mute-400' }
export const toneBg = { ok: 'bg-ok', warn: 'bg-warn', bad: 'bg-bad', agent: 'bg-agent', off: 'bg-mute-400' }

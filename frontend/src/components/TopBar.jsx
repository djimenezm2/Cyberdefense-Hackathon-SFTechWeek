import { useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { GitBranch, Cloud, Zap, Radio } from 'lucide-react'
import { STATUS_COPY } from '../lib/contract'
import { toneBg, toneText } from '../lib/format'
import { IS_DEMO } from '../lib/useAgent'

export function useNow(ms = 1000) {
  const [now, setNow] = useState(Date.now())
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), ms)
    return () => clearInterval(t)
  }, [ms])
  return now
}

export function StatusDot({ tone = 'ok', size = 'h-2.5 w-2.5' }) {
  return (
    <span className={`relative inline-flex ${size}`}>
      <span className={`absolute inline-flex h-full w-full animate-ping rounded-full opacity-60 ${toneBg[tone]}`} />
      <span className={`relative inline-flex rounded-full ${size} ${toneBg[tone]}`} />
    </span>
  )
}

export default function TopBar({ state, onToggleReview }) {
  const [askPause, setAskPause] = useState(false)
  const now = useNow()
  const s = STATUS_COPY[state.status] ?? STATUS_COPY.watching
  const lastAnalysis = state.windows?.length ? Math.max(...state.windows.map((w) => w.end || 0)) : null
  const scanAt = IS_DEMO ? state.lastScan : lastAnalysis
  const secs = scanAt ? Math.max(0, Math.round((now - scanAt) / 1000)) : null
  const busy = !['watching', 'paused'].includes(state.status)
  const claim = IS_DEMO ? 'Proven on a replica · 1 approval to ship' : liveClaim(state.incidents)

  return (
    <header className="sticky top-0 z-30 border-b border-ink-700 bg-ink-950/85 backdrop-blur" style={{ paddingTop: 'env(safe-area-inset-top, 0px)' }}>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-2.5 lg:px-6">
        <div className="flex items-center gap-2 pr-2">
          <svg viewBox="0 0 24 24" className="h-5 w-5" aria-hidden="true" fill="none" strokeWidth="1.8" strokeLinecap="round">
            <path d="M3 8c3-3 5 3 9 0s6-3 9 0" stroke="#8FA4F5" />
            <path d="M3 13c3-3 5 3 9 0s6-3 9 0" stroke="#8FA4F5" opacity=".7" />
            <path d="M3 18c3-3 5 3 9 0s6-3 9 0" stroke="#8FA4F5" opacity=".45" />
            <rect x="15.5" y="3" width="4" height="4" fill="#D7F04B" />
          </svg>
          <span className="text-[15px] font-semibold tracking-tight">Rootlane</span>
        </div>

        <div className={`flex items-center gap-2.5 rounded-full border px-3 py-1 ${busy ? 'border-warn/40 bg-warn/10' : state.monitoring ? 'border-ok/30 bg-ok/5' : 'border-ink-600 bg-ink-850'}`}>
          <StatusDot tone={s.tone} />
          <AnimatePresence mode="wait">
            <motion.span key={s.label} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }}
              className={`font-mono text-xs font-semibold uppercase tracking-wider ${toneText[s.tone]}`}>
              {s.label}
            </motion.span>
          </AnimatePresence>
          <span className="num hidden font-mono text-xs text-mute-400 sm:inline">{!state.monitoring ? '· not watching' : secs === null ? '· waiting for the first analysis' : `· last analysis ${secs}s ago`}</span>
        </div>

        <div className="hidden items-center gap-2 2xl:flex">
          <Chip icon={GitBranch}>{state.summary.repo}</Chip>
          <Chip icon={Cloud}>{state.summary.infra}</Chip>
        </div>

        <div className="ml-auto flex items-center gap-3">
          {claim && (
            <span className={`hidden items-center gap-1.5 rounded-md border px-2 py-1 font-mono text-[11px] xl:flex border-agent/30 text-agent`}>
              <Zap className="h-3.5 w-3.5" />
              {claim}
            </span>
          )}
          <span className="flex items-center gap-1.5 font-mono text-[11px] text-mute-400">
            <Radio className={`h-3.5 w-3.5 ${state.connected ? 'text-ok' : 'text-bad'}`} />
            {IS_DEMO ? 'DEMO' : !state.connected ? 'OFFLINE' : state.streaming ? 'LIVE' : 'LIVE · polling'}
          </span>
          <div className="relative">
            <button role="switch" aria-checked={state.monitoring}
              onClick={() => (state.monitoring ? setAskPause(true) : onToggleReview(true))}
              className={`hex flex items-center gap-2.5 py-1.5 pl-4 pr-5 text-sm font-semibold transition focus:outline-none focus-visible:ring-2 focus-visible:ring-agent/60 ${state.monitoring ? 'bg-lime text-ink-950' : 'bg-ink-700 text-mute-300 hover:bg-ink-600'}`}>
              <span className={`relative h-4 w-7 rounded-full ${state.monitoring ? 'bg-ink-950/25' : 'bg-ink-950/60'}`}>
                <span className={`absolute top-0.5 h-3 w-3 rounded-full transition-all ${state.monitoring ? 'left-[14px] bg-ink-950' : 'left-0.5 bg-mute-400'}`} />
              </span>
              {IS_DEMO ? 'Constant review' : 'Live view'} {state.monitoring ? 'ON' : 'OFF'}
            </button>
            {askPause && (
              <div className="absolute right-0 top-full z-50 mt-2 w-72 rounded-xl border border-ink-600 bg-ink-850 p-4 shadow-2xl">
                <p className="text-sm font-medium text-mute-100">{IS_DEMO ? 'Pause constant review?' : 'Pause the live view?'}</p>
                <p className="mt-1 text-xs leading-relaxed text-mute-400">{IS_DEMO ? 'This dashboard stops following live activity. The agent keeps working in the background.' : 'This dashboard stops following live activity.'}</p>
                <div className="mt-3 flex justify-end gap-2">
                  <button onClick={() => setAskPause(false)} className="btn px-2.5 py-1 text-xs text-mute-300 hover:text-mute-100">Keep it on</button>
                  <button onClick={() => { setAskPause(false); onToggleReview(false) }} className="btn bg-bad/90 px-2.5 py-1 text-xs text-white hover:bg-bad">{IS_DEMO ? 'Pause review' : 'Pause view'}</button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </header>
  )
}

// Live-mode badge, built only from the newest open incident the API reported.
function liveClaim(incidents) {
  const open = Object.values(incidents).filter((i) => ['investigating', 'pending_approval', 'applying'].includes(i.status)).sort((a, b) => b.ts - a.ts)[0]
  if (!open) return 'No open incidents'
  if (open.status === 'investigating') return 'Investigating'
  if (open.status === 'applying') return 'Applying the approved fix'
  return open.verification?.replica_after ? 'Fix verified on a replica · awaiting approval' : 'Fix ready · awaiting approval'
}

function Chip({ icon: Icon, children }) {
  return (
    <span className="flex items-center gap-1.5 rounded-md border border-ink-700 bg-ink-900 px-2 py-1 font-mono text-[11px] text-mute-300">
      <Icon className="h-3.5 w-3.5 text-mute-400" /> {children}
    </span>
  )
}

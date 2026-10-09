import { AnimatePresence, motion } from 'framer-motion'
import { Activity } from 'lucide-react'
import IncidentCard from './IncidentCard'
import { clock } from '../lib/format'

const OPS = { query_events: 'Queried request events', read_source: 'Read source', semgrep_scan: 'Ran Semgrep scan', reproduce: 'Reproduced on a replica', verify_patch: 'Verified patch on a replica', propose: 'Proposed a fix', apply: 'Applied the fix' }

export default function AgentFeed({ state, onApprove, onReject, onTokenSaved }) {
  return (
    <section className="panel flex min-h-0 flex-col lg:h-full">
      <div className="panel-head border-b border-ink-700 pb-3">
        <div className="flex items-center gap-2">
          <Activity className="h-4 w-4 text-agent" />
          <span className="text-[13px] font-semibold">Agent activity</span>
        </div>
        <span className="eyebrow">Live stream</span>
      </div>
      <div className="scroll-thin min-h-0 flex-1 space-y-2 overflow-y-auto p-3 max-lg:max-h-[640px]">
        <AnimatePresence initial={false}>
          {state.feed.map((item) =>
            item.kind === 'incident' && state.incidents[item.incidentId] ? (
              <IncidentCard key={item.id} inc={state.incidents[item.incidentId]} onApprove={onApprove} onReject={onReject} needToken={state.needToken} onTokenSaved={onTokenSaved} />
            ) : item.kind === 'op' ? (
              <motion.div key={item.id} layout initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                className="flex gap-2.5 px-1 font-mono text-[11.5px] leading-relaxed">
                <span className="num shrink-0 text-mute-400/70">{clock(item.op.ts)}</span>
                <span className="text-mute-200">
                  <span className="text-agent">◆ </span>{OPS[item.op.operation] ?? item.op.operation}
                  <span className="text-mute-400"> · {item.op.duration_ms >= 1000 ? (item.op.duration_ms / 1000).toFixed(1) + ' s' : item.op.duration_ms + ' ms'} · {item.op.incident_id} · {item.op.on_behalf_of?.match(/gs_\w+/)?.[0] ?? ''}</span>
                </span>
              </motion.div>
            ) : item.kind === 'heartbeat' ? (
              <motion.div key={item.id} layout initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }}
                className="flex gap-2.5 px-1 font-mono text-[11.5px] leading-relaxed">
                <span className="num shrink-0 text-mute-400/70">{clock(item.ts)}</span>
                <span className={item.tone === 'warn' ? 'text-warn' : 'text-mute-300'}>
                  <span className="text-ok">✓ </span>{item.message}
                </span>
              </motion.div>
            ) : null,
          )}
        </AnimatePresence>
        {state.feed.length === 0 && (
          <p className="px-1 py-6 text-center text-sm text-mute-400">Waiting for the agent's first report…</p>
        )}
      </div>
    </section>
  )
}

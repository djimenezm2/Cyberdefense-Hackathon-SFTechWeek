import { useEffect, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { Check, Loader2, ShieldCheck, X, ExternalLink } from 'lucide-react'
import { KIND_LABEL, STATUS } from '../lib/contract'
import { isWorking } from '../lib/adapters'
import { useNow } from './TopBar'
import ApprovalBox from './ApprovalBox'

// Alerta grande que aparece SOLA cuando llega un incidente nuevo (stream incident_update).
export default function AttackAlert({ state, onApprove, onReject, onTokenSaved, onOpen }) {
  const now = useNow(200)
  const [shownId, setShownId] = useState(null)
  const [dismissed, setDismissed] = useState({})

  const newest = Object.values(state.incidents).filter(isWorking).sort((a, b) => b.ts - a.ts)[0]
  useEffect(() => { if (newest && newest.id !== shownId) setShownId(newest.id) }, [newest, shownId])

  const inc = shownId ? state.incidents[shownId] : null
  const done = inc && !isWorking(inc)
  const fixed = inc?.status === 'applied'

  useEffect(() => {
    if (!done) return
    const t = setTimeout(() => setDismissed((d) => ({ ...d, [shownId]: true })), 12000)
    return () => clearTimeout(t)
  }, [done, shownId])

  const visible = inc && !dismissed[inc.id]
  const endTs = inc?.apply?.ts ? new Date(inc.apply.ts).getTime() : done ? inc?.steps.at(-1)?.ts : null
  const secs = inc ? Math.max(0, ((endTs ?? now) - inc.ts) / 1000) : 0
  const clockText = `${String(Math.floor(secs / 60)).padStart(2, '0')}:${String(Math.floor(secs % 60)).padStart(2, '0')}`
  const st = STATUS[inc?.status] ?? STATUS.investigating
  const header = fixed ? { t: 'ATTACK NEUTRALIZED', c: 'text-ok', bg: 'bg-ok/15', b: 'border-ok/50' }
    : inc?.status === 'pending_approval' ? { t: 'FIX READY · YOUR APPROVAL NEEDED', c: 'text-lime', bg: 'bg-lime/10', b: 'border-lime/50' }
    : done ? { t: st.t.toUpperCase(), c: 'text-mute-200', bg: 'bg-ink-800', b: 'border-ink-600' }
    : { t: 'NEW ATTACK DETECTED', c: 'text-bad', bg: 'bg-bad/20', b: 'border-bad/60' }
  const steps = inc?.steps.filter((s) => s.kind !== 'chat') ?? []

  return (
    <>
      <AnimatePresence>
        {visible && inc.status === 'investigating' && steps.length < 2 && (
          <motion.div key={'flash' + inc.id} className="pointer-events-none fixed inset-0 z-40"
            initial={{ opacity: 0 }} animate={{ opacity: [0, 1, 0.35, 0.8, 0.35] }} exit={{ opacity: 0 }} transition={{ duration: 2.4 }}
            style={{ boxShadow: 'inset 0 0 120px 10px rgba(255,77,94,0.45)' }} />
        )}
      </AnimatePresence>

      <div className="pointer-events-none fixed inset-x-0 top-[72px] z-50 flex justify-center px-4">
        <AnimatePresence>
          {visible && (
            <motion.aside key={inc.id} role="alert"
              initial={{ opacity: 0, y: -30, scale: 0.96 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: -20 }}
              transition={{ type: 'spring', stiffness: 260, damping: 24 }}
              className={`pointer-events-auto flex max-h-[calc(100vh-96px)] w-full max-w-[600px] flex-col overflow-hidden rounded-2xl border bg-ink-900/95 shadow-2xl backdrop-blur ${header.b}`}>
              <header className={`flex shrink-0 items-center gap-3 px-4 py-2.5 ${header.bg}`}>
                {fixed ? <ShieldCheck className="h-4 w-4 text-ok" />
                  : <span className="relative flex h-2.5 w-2.5"><span className="absolute h-full w-full animate-ping rounded-full bg-current opacity-60" /><span className={`relative h-2.5 w-2.5 rounded-full ${inc.status === 'pending_approval' ? 'bg-lime' : 'bg-bad'}`} /></span>}
                <span className={`font-mono text-[12px] font-medium tracking-[0.16em] ${header.c}`}>{header.t}</span>
                <span className="num ml-auto font-mono text-[13px] text-mute-100">{clockText}</span>
                <button onClick={() => setDismissed((d) => ({ ...d, [inc.id]: true }))} aria-label="Close alert"
                  className="rounded p-1 text-mute-400 hover:bg-ink-700 hover:text-mute-100"><X className="h-4 w-4" /></button>
              </header>

              <div className="scroll-thin space-y-3 overflow-y-auto p-4">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="rounded border border-bad/50 px-1.5 py-px font-mono text-[10px] uppercase tracking-wider text-bad">{inc.severity}</span>
                    {inc.target && <span className="font-mono text-[11px] text-mute-400">target {inc.target}</span>}
                    {inc.session && <span className="font-mono text-[11px] text-mute-400">· Guild {inc.session}</span>}
                  </div>
                  <h2 className="mt-1.5 text-[19px] font-semibold leading-tight tracking-tight">{inc.title}</h2>
                  {inc.summary && <p className="mt-1 text-[13px] leading-relaxed text-mute-300">{inc.summary}</p>}
                </div>

                <ol className="grid gap-1.5">
                  {steps.map((s, i) => (
                    <li key={i} className="flex items-start gap-2.5 text-[12.5px] text-mute-200">
                      <span className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center">
                        {s.outcome === 'ok' ? <Check className="h-3.5 w-3.5 text-ok" strokeWidth={3} /> : <X className="h-3.5 w-3.5 text-bad" strokeWidth={3} />}
                      </span>
                      <span className="w-[130px] shrink-0 font-medium">{KIND_LABEL[s.kind] ?? s.kind}</span>
                      <span className="min-w-0 text-mute-300">{s.message}</span>
                    </li>
                  ))}
                  {inc.status === 'investigating' && (
                    <li className="flex items-center gap-2.5 text-[12.5px] text-warn">
                      <Loader2 className="h-3.5 w-3.5 animate-spin" /> The agent is working…
                    </li>
                  )}
                  {inc.status === 'applying' && (
                    <li className="flex items-center gap-2.5 text-[12.5px] text-agent">
                      <Loader2 className="h-3.5 w-3.5 animate-spin" /> Opening the pull request and redeploying production…
                    </li>
                  )}
                </ol>

                {inc.status === 'pending_approval' && (
                  <ApprovalBox inc={inc} onApprove={onApprove} onReject={onReject} needToken={state.needToken} onTokenSaved={onTokenSaved} compact />
                )}

                {fixed && (
                  <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-ok/30 bg-ok/10 px-3 py-2 text-[12.5px] text-ok">
                    <span>
                      Fixed in {Math.round(secs)} s{inc.approval?.approver ? ` · approved by ${inc.approval.approver}` : ''}
                      {inc.apply?.production?.status ? ` · production replay → ${inc.apply.production.status}` : ''}
                    </span>
                    <span className="flex items-center gap-3">
                      {inc.apply?.pr_url && <a href={inc.apply.pr_url} target="_blank" rel="noreferrer" className="flex items-center gap-1 underline-offset-2 hover:underline">Pull request <ExternalLink className="h-3 w-3" /></a>}
                      <button onClick={() => { onOpen?.(); setDismissed((d) => ({ ...d, [inc.id]: true })) }} className="font-medium underline-offset-2 hover:underline">Full report</button>
                    </span>
                  </div>
                )}
              </div>
            </motion.aside>
          )}
        </AnimatePresence>
      </div>
    </>
  )
}

import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Check, ChevronDown, Loader2, FileCode2, X, ExternalLink } from 'lucide-react'
import { PHASES, KIND_LABEL, STATUS } from '../lib/contract'
import { isWorking } from '../lib/adapters'
import CodeCompare from './CodeCompare'
import ApprovalBox from './ApprovalBox'
import { clock, timeAgo } from '../lib/format'

const SEV = {
  low: 'border-ink-600 text-mute-300', medium: 'border-warn/40 text-warn',
  high: 'border-bad/40 text-bad', critical: 'border-bad bg-bad/15 text-bad',
}
const TONE = {
  warn: 'text-warn border-warn/40 bg-warn/10', agent: 'text-lime border-lime/40 bg-lime/10',
  ok: 'text-ok border-ok/40 bg-ok/10', bad: 'text-bad border-bad/40 bg-bad/10', off: 'text-mute-300 border-ink-600 bg-ink-800',
}
const EVIDENCE = { event: 'Request', code: 'Code', context: 'Policy' }

export default function IncidentCard({ inc, onApprove, onReject, needToken, onTokenSaved, defaultOpen }) {
  const working = isWorking(inc)
  const [open, setOpen] = useState(defaultOpen ?? working)
  const done = new Set(['detected', ...inc.steps.map((s) => s.phase).filter(Boolean)])
  if (inc.status === 'applied') done.add('apply')
  const current = PHASES.find((p) => !done.has(p.key))?.key
  const st = STATUS[inc.status] ?? STATUS.investigating
  const isOpen = open || working
  const steps = inc.steps.filter((s) => s.kind !== 'chat')

  return (
    <motion.article layout="position" initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }}
      className={`overflow-hidden rounded-2xl border bg-ink-850 ${working ? 'border-warn/50' : 'border-ink-700'}`}>
      <button onClick={() => setOpen(!open)} className="flex w-full items-start gap-3 px-3.5 py-3 text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-agent/50">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className={`rounded border px-1.5 py-px font-mono text-[10px] uppercase tracking-wider ${SEV[inc.severity] ?? SEV.medium}`}>{inc.severity}</span>
            <span className={`rounded border px-1.5 py-px font-mono text-[10px] ${TONE[st.tone]}`}>{st.t}</span>
            <span className="font-mono text-[10.5px] text-mute-400">{timeAgo(inc.ts)}</span>
          </div>
          <h3 className="mt-1.5 text-[14px] font-semibold leading-snug text-mute-100">{inc.title}</h3>
          <div className="mt-0.5 truncate font-mono text-[11px] text-mute-400">
            {[inc.target, inc.category, inc.session && `Guild ${inc.session}`].filter(Boolean).join(' · ')}
          </div>
        </div>
        <ChevronDown className={`mt-1 h-4 w-4 shrink-0 text-mute-400 transition ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      <div className="flex items-center gap-1 px-3.5 pb-3">
        {PHASES.map((p) => {
          const ok = done.has(p.key)
          const now = working && p.key === current
          return (
            <div key={p.key} className="min-w-0 flex-1" title={p.label}>
              <div className={`h-1 rounded-full ${ok ? 'bg-ok' : now ? 'bg-warn' : 'bg-ink-600'}`} />
              <div className={`mt-1 hidden truncate font-mono text-[9.5px] sm:block ${ok ? 'text-mute-300' : now ? 'text-warn' : 'text-mute-400/60'}`}>{p.label}</div>
            </div>
          )
        })}
      </div>

      <AnimatePresence initial={false}>
        {isOpen && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="border-t border-ink-700">
            <div className="space-y-4 p-3.5">
              {inc.summary && <p className="text-[13px] leading-relaxed text-mute-300">{inc.summary}</p>}

              {inc.status === 'pending_approval' && (
                <ApprovalBox inc={inc} onApprove={onApprove} onReject={onReject} needToken={needToken} onTokenSaved={onTokenSaved} compact />
              )}

              {inc.status === 'applied' && (
                <div className="rounded-xl border border-ok/30 bg-ok/[0.06] p-3 text-[12.5px] text-mute-200">
                  <div className="eyebrow mb-1 text-ok">Applied</div>
                  {inc.approval?.approver && <div>Approved by <b>{inc.approval.approver}</b>{inc.approval.ts && <> at {clock(Date.parse(inc.approval.ts))}</>}</div>}
                  {inc.apply?.production?.status && <div>Production replay → <b>{inc.apply.production.status}</b> {inc.apply.production.summary && `· ${inc.apply.production.summary}`}</div>}
                  {inc.apply?.pr_url && <a href={inc.apply.pr_url} target="_blank" rel="noreferrer" className="mt-1 inline-flex items-center gap-1 text-ok underline-offset-2 hover:underline">Open pull request <ExternalLink className="h-3 w-3" /></a>}
                </div>
              )}
              {inc.status === 'rejected' && inc.approval && (
                <p className="text-[12.5px] text-mute-300">Rejected by {inc.approval.approver}{inc.approval.reason && `: ${inc.approval.reason}`}</p>
              )}

              {inc.timeline?.length > 0 && (
                <Block title="What the attacker did">
                  <ul className="space-y-1 font-mono text-[11px]">
                    {inc.timeline.map((t, i) => (
                      <li key={i} className="flex flex-wrap gap-x-2">
                        <span className="num text-mute-400">{clock(t.ts)}</span>
                        <span className="text-mute-200">{t.method} {t.route}</span>
                        <span className="text-bad">{t.status}</span>
                        <span className="text-mute-400">principal {t.principal_id || '—'} · {t.ip}</span>
                        {t.note && <span className="w-full text-warn">↳ {t.note}</span>}
                      </li>
                    ))}
                  </ul>
                </Block>
              )}

              <Block title="What Rootlane did">
                <ol className="space-y-2">
                  {steps.map((s, i) => (
                    <li key={i} className="flex gap-2.5">
                      <span className={`mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full ${s.outcome === 'ok' ? 'bg-ok/15 text-ok' : 'bg-bad/15 text-bad'}`}>
                        {s.outcome === 'ok' ? <Check className="h-3 w-3" strokeWidth={3} /> : <X className="h-3 w-3" strokeWidth={3} />}
                      </span>
                      <div className="min-w-0 text-[12.5px]">
                        <span className="font-medium text-mute-100">{KIND_LABEL[s.kind] ?? s.kind}</span>
                        <span className="ml-2 font-mono text-[10.5px] text-mute-400">{clock(s.ts)}</span>
                        <div className="text-mute-300">{s.message}</div>
                      </div>
                    </li>
                  ))}
                  {inc.status === 'investigating' && (
                    <li className="flex items-center gap-2.5 text-[12.5px] text-warn"><Loader2 className="h-3.5 w-3.5 animate-spin" /> Working…</li>
                  )}
                </ol>
              </Block>

              {inc.hypothesis && (
                <Block title="Root cause">
                  <p className="text-[13px] leading-relaxed text-mute-100">{inc.hypothesis.text}</p>
                  <ul className="mt-2 space-y-1.5">
                    {inc.hypothesis.evidence?.map((e, i) => (
                      <li key={i} className="flex items-start gap-2 text-[12px]">
                        <span className="shrink-0 rounded border border-ink-600 px-1.5 py-px font-mono text-[10px] text-mute-300">{EVIDENCE[e.kind] ?? e.kind}</span>
                        <span className="min-w-0 text-mute-300"><span className="font-mono text-mute-200">{e.ref}</span> · {e.text}</span>
                      </li>
                    ))}
                  </ul>
                </Block>
              )}

              {inc.verification && <Proof v={inc.verification} />}
              {inc.patch?.diff && <PatchView patch={inc.patch} />}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.article>
  )
}

function Block({ title, children }) {
  return (
    <div>
      <div className="eyebrow mb-1.5">{title}</div>
      {children}
    </div>
  )
}

function Proof({ v }) {
  const cells = [
    v.replica_before && { k: 'Before patch', val: v.replica_before.status, sub: v.replica_before.summary },
    v.replica_after && { k: 'After patch', val: v.replica_after.status, sub: v.replica_after.summary },
    v.regression && { k: 'Regression', val: `${v.regression.passed}/${v.regression.passed + v.regression.failed}`, sub: 'passed' },
    v.semgrep_old != null && { k: 'Semgrep', val: `${v.semgrep_old} → ${v.semgrep_new}`, sub: 'findings' },
  ].filter(Boolean)
  return (
    <Block title="Proof on a replica">
      <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-ink-700 bg-ink-700">
        {cells.map((c) => (
          <div key={c.k} className="bg-ink-900 px-3 py-2">
            <dt className="font-mono text-[10px] text-mute-400">{c.k}</dt>
            <dd className="num text-[15px] font-semibold text-mute-100">{c.val}</dd>
            <dd className="text-[11px] text-mute-400">{c.sub}</dd>
          </div>
        ))}
      </dl>
    </Block>
  )
}

function PatchView({ patch }) {
  const [mode, setMode] = useState('compare')
  const tabs = [['compare', 'Before / after'], ['diff', 'Diff'], patch.ruleYaml && ['rule', 'New Semgrep rule']].filter(Boolean)
  return (
    <Block title={`Patch ${patch.hash ?? ''}`}>
      <div className="mb-1.5 flex flex-wrap gap-1 font-mono text-[10.5px]">
        {tabs.map(([m, label]) => (
          <button key={m} onClick={() => setMode(m)}
            className={`rounded px-2 py-0.5 ${mode === m ? 'bg-ink-700 text-mute-100' : 'text-mute-400 hover:text-mute-200'}`}>{label}</button>
        ))}
      </div>
      {mode === 'compare' && <CodeCompare patch={patch} className="h-[170px]" />}
      {mode === 'diff' && <Diff patch={patch} />}
      {mode === 'rule' && (
        <pre className="scroll-thin overflow-x-auto rounded-xl border border-ink-700 bg-ink-950 p-3 font-mono text-[11px] leading-[1.7] text-mute-300">{patch.ruleYaml}</pre>
      )}
    </Block>
  )
}

function Diff({ patch }) {
  return (
    <div className="overflow-hidden rounded-xl border border-ink-700 bg-ink-950">
      <div className="flex items-center gap-2 border-b border-ink-700 px-3 py-1.5 font-mono text-[11px] text-mute-300">
        <FileCode2 className="h-3.5 w-3.5 text-mute-400" /> {patch.file}
      </div>
      <pre className="scroll-thin overflow-x-auto py-1.5 font-mono text-[11.5px] leading-[1.7]">
        {patch.diff.map((d, i) => (
          <div key={i} className={d.op === '+' ? 'text-ok' : d.op === '-' ? 'text-bad' : 'text-mute-400'}>
            <span className="inline-block w-9 select-none pr-2 text-right text-mute-400/60">{d.line}</span>
            <span className="inline-block w-4 select-none">{d.op}</span>
            {d.text}
          </div>
        ))}
      </pre>
    </div>
  )
}


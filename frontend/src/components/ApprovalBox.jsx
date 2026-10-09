import { useState } from 'react'
import { Loader2, ShieldCheck } from 'lucide-react'
import { MODE, readAuth, writeAuth } from '../lib/useAgent'

// Caja de aprobación del contrato: nombre de quien aprueba + Approve / Reject.
// En modo real manda X-Admin-Token; si el API responde 401 vuelve a pedirlo.
export default function ApprovalBox({ inc, onApprove, onReject, needToken, onTokenSaved, compact = false }) {
  const auth = readAuth()
  const [name, setName] = useState(auth.name || '')
  const [token, setToken] = useState('')
  const [rejecting, setRejecting] = useState(false)
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const gh = !!auth.github
  const askToken = MODE === 'live' && !gh && (needToken || !auth.token)

  const save = () => {
    const next = { ...auth, name: name.trim() || auth.name, token: token.trim() || auth.token }
    writeAuth(next)
    if (token.trim()) onTokenSaved?.()
  }

  const run = async (fn) => {
    setError('')
    save()
    setBusy(true)
    const r = await fn()
    setBusy(false)
    if (!r?.ok) setError(r?.error ?? 'Something went wrong.')
  }

  return (
    <div className={`rounded-xl border border-lime/40 bg-lime/[0.05] ${compact ? 'p-3' : 'p-4'}`}>
      <div className="flex items-center gap-2 text-[13px] font-semibold text-mute-100">
        <ShieldCheck className="h-4 w-4 text-lime" /> Approve proposal {inc.patch?.hash}
      </div>
      <p className="mt-1 text-[12px] text-mute-300">
        Approving opens a pull request on the fork, redeploys production and replays the attack to confirm it now fails.
      </p>
      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        {gh ? (
          <div className="flex items-center gap-2 text-[12px] text-mute-200">
            {auth.avatar && <img src={auth.avatar} alt="" className="h-6 w-6 rounded-full" />}
            Approving as <span className="font-mono text-mute-100">@{auth.name}</span> · GitHub
          </div>
        ) : (
        <label className="text-[11px] text-mute-400">
          Approver
          <input id={`approver-${inc.id}`} value={name} onChange={(e) => setName(e.target.value)} placeholder="Your name"
            className="mt-1 w-full rounded-lg border border-ink-600 bg-ink-950 px-2.5 py-1.5 text-[13px] text-mute-100 focus:border-lime/60 focus:outline-none" />
        </label>
        )}
        {askToken && (
          <label className="text-[11px] text-mute-400">
            Admin token
            <input id={`token-${inc.id}`} type="password" value={token} onChange={(e) => setToken(e.target.value)} placeholder="••••••"
              className="mt-1 w-full rounded-lg border border-ink-600 bg-ink-950 px-2.5 py-1.5 font-mono text-[13px] text-mute-100 focus:border-lime/60 focus:outline-none" />
          </label>
        )}
      </div>
      {rejecting && (
        <input id={`reason-${inc.id}`} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Why are you rejecting it?"
          className="mt-2 w-full rounded-lg border border-ink-600 bg-ink-950 px-2.5 py-1.5 text-[13px] text-mute-100 focus:border-bad/60 focus:outline-none" />
      )}
      {error && <p className="mt-2 text-[12px] text-bad">{error}</p>}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        {!rejecting ? (
          <>
            <button disabled={busy || !name.trim()} onClick={() => run(() => onApprove(inc.id))}
              className="hex flex items-center gap-2 bg-lime px-5 py-2 text-sm font-semibold text-ink-950 hover:brightness-105 disabled:opacity-50">
              {busy && <Loader2 className="h-4 w-4 animate-spin" />} Approve and apply
            </button>
            <button onClick={() => setRejecting(true)} className="rounded-lg px-3 py-2 text-xs text-mute-300 hover:text-bad">Reject</button>
          </>
        ) : (
          <>
            <button disabled={busy || !name.trim()} onClick={() => run(() => onReject(inc.id, reason))}
              className="rounded-lg bg-bad/90 px-4 py-2 text-sm font-semibold text-white hover:bg-bad disabled:opacity-50">Reject proposal</button>
            <button onClick={() => setRejecting(false)} className="rounded-lg px-3 py-2 text-xs text-mute-300 hover:text-mute-100">Cancel</button>
          </>
        )}
      </div>
    </div>
  )
}

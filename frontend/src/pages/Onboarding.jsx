import { useEffect, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { Check, GitBranch, Loader2, Lock, X } from 'lucide-react'
import CodeCurtain from '../components/ui/code-curtain'
import { API_URL, MODE, readAuth, writeAuth } from '../lib/useAgent'
import { ENDPOINTS, GUARDRAILS } from '../lib/contract'

// GitHub sign-in is offered only once its OAuth app is configured.
const GITHUB_AUTH = import.meta.env.VITE_GITHUB_AUTH === 'true'

const STEPS = ['Sign in', 'Sources', 'Turn on review']

// Lo que Rootlane vigila en este proyecto (docs/context/infrastructure.md)
const SOURCES = [
  { k: 'Production app', v: 'juiceshop.rootlane.xyz', d: 'OWASP Juice Shop from the fork, on Akash' },
  { k: 'Telemetry', v: 'ClickHouse · rootlane', d: 'Every request and auth event, derived fields only' },
  { k: 'Source repository', v: 'djimenezm2/juice-shop', d: 'Fixes arrive as pull requests on the fork' },
  { k: 'Agent', v: 'Guild · claude-opus-5', d: 'Calls the toolbox at api.rootlane.xyz' },
  { k: 'Analyzer', v: 'AkashML · GLM', d: 'Reads traffic every 10 seconds' },
]

const BG_CODE = `rootlane watch --app juiceshop.rootlane.xyz
  ✓ clickhouse  http_requests · auth_events streaming
  ✓ analyzer    akashml/glm · window 10 s
  ✓ guild       rootlane-agent ready

for each window of traffic:
  verdict = analyzer.triage(features(window))
  if verdict != "escalate": continue
  incident = open_incident(window)
  agent.query_events(incident)
  agent.read_source("lib/insecurity.ts")
  agent.semgrep_scan()
  agent.reproduce(incident)          # replica: 200
  agent.verify_patch(diff, rule)     # replica: 401, regression 6/6
  agent.propose(report, diff, rule)  # pending_approval
  wait_for_human_approval()
  apply()                            # PR + redeploy, prod: 401

`

export default function Onboarding({ state, onFinish }) {
  const saved = readAuth()
  const [step, setStep] = useState(0)
  const [name, setName] = useState(saved.name || '')
  const [token, setToken] = useState(saved.token || '')
  const [checking, setChecking] = useState(null) // null | 0..n
  const [checkFail, setCheckFail] = useState('')
  const [review, setReview] = useState(true)
  const [phase, setPhase] = useState('writing')

  const [authErr, setAuthErr] = useState(() => {
    const e = new URLSearchParams(location.search).get('auth')
    return e === 'denied' ? 'This GitHub account is not on the Rootlane team.' : e ? 'GitHub sign-in failed. Try again.' : ''
  })
  const [authBusy, setAuthBusy] = useState(false)
  const [useToken, setUseToken] = useState(false)

  // Live mode: if the GitHub session cookie exists, skip the sign-in step
  useEffect(() => {
    if (MODE !== 'live' || !GITHUB_AUTH) return
    if (location.search.includes('auth=')) history.replaceState(null, '', location.pathname)
    fetch('/api/auth?a=me', { credentials: 'same-origin' })
      .then((r) => (r.ok ? r.json() : null))
      .then((me) => { if (me?.login) { writeAuth({ name: me.login, github: true, avatar: me.avatar }); setName(me.login); setStep((s) => (s === 0 ? 1 : s)) } })
      .catch(() => {})
  }, [])

  // En modo real valida el token contra el toolbox: un reject sobre un id que no existe
  // devuelve 401 si el token es malo y 404 si es bueno (no cambia nada en el backend).
  const signIn = async (e) => {
    e.preventDefault()
    setAuthErr('')
    if (MODE === 'live') {
      setAuthBusy(true)
      const code = await fetch(API_URL + '/api/incidents/__signin_check__/reject', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Admin-Token': token.trim() },
        body: JSON.stringify({ approver: name.trim(), reason: 'sign-in check' }),
      }).then((r) => r.status).catch(() => 0)
      setAuthBusy(false)
      if (code === 401) { setAuthErr('That admin token is not valid.'); return }
      if (code === 0) { setAuthErr(`Could not reach ${API_URL}.`); return }
    }
    writeAuth({ name: name.trim(), token: token.trim() })
    setStep(1)
  }

  // En modo real, comprueba que el toolbox responde antes de seguir
  const verifySources = async () => {
    setCheckFail('')
    setChecking(0)
    if (MODE === 'live') {
      const ok = await fetch(API_URL + ENDPOINTS.overview).then((r) => r.ok).catch(() => false)
      if (!ok) { setChecking(null); setCheckFail(`Could not reach ${API_URL}. Check that the toolbox is running and allows CORS from this site.`); return }
    }
    SOURCES.forEach((_, i) => setTimeout(() => setChecking(i + 1), 350 * (i + 1)))
    setTimeout(() => { setChecking(null); setStep(2) }, 350 * SOURCES.length + 500)
  }

  const PH = {
    writing: { t: 'WRITING · lib/insecurity.ts', c: 'text-lime border-lime/40' },
    live: { t: 'LIVE · constant review on', c: 'text-ok border-ok/40' },
    attack: { t: 'INTRUSION DETECTED · unsigned token on /rest/basket', c: 'text-bad border-bad/60 bg-bad/10' },
    patching: { t: 'ROOTLANE PATCHING · insecurity.ts:54', c: 'text-lime border-lime/50' },
    redeployed: { t: 'APPROVED · production now answers 401', c: 'text-ok border-ok/40' },
  }[phase] ?? { t: '', c: '' }
  const attacked = phase === 'attack'

  return (
    <div className="relative grid min-h-full bg-ink-950 lg:h-full lg:grid-cols-[minmax(0,1.15fr)_minmax(420px,0.85fr)]">
      {/* HERO: cortina de código */}
      <section className={`relative h-[56svh] min-h-[380px] overflow-hidden border-b border-ink-700 transition-colors duration-700 lg:h-full lg:border-b-0 lg:border-r ${attacked ? 'bg-[#1a0a0e]' : 'bg-ink-950'}`}>
        <div className={`pointer-events-none absolute inset-0 transition-opacity duration-500 ${attacked ? 'opacity-100' : 'opacity-0'}`}
          style={{ background: 'radial-gradient(60% 50% at 50% 60%, rgba(255,77,94,0.22), transparent 70%)' }} />
        <CodeCurtain onPhase={setPhase} />
        <AnimatePresence>
          {attacked && (
            <motion.div key="alert" className="pointer-events-none absolute inset-0 flex items-center justify-center"
              initial={{ opacity: 0 }} animate={{ opacity: [0, 1, 0.15, 1, 0.6, 1, 0] }} exit={{ opacity: 0 }}
              transition={{ duration: 1.8, times: [0, 0.1, 0.2, 0.3, 0.45, 0.6, 1] }}>
              <div className="rounded-2xl border border-bad/40 bg-ink-950/75 px-6 py-4 text-center backdrop-blur-md">
                <div className="font-mono text-[11px] tracking-[0.4em] text-bad">[ ALERT ]</div>
                <div className="mt-1 text-[32px] font-bold leading-none tracking-[-0.04em] text-bad sm:text-[64px]"
                  style={{ textShadow: '0 0 40px rgba(255,77,94,0.65)' }}>ATTACK DETECTED</div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
        <div className="pointer-events-none absolute left-4 top-4 flex items-center gap-2 sm:left-6 sm:top-6" style={{ top: 'calc(env(safe-area-inset-top, 0px) + 16px)' }}>
          <svg viewBox="0 0 24 24" className="h-6 w-6" aria-hidden="true" fill="none" strokeWidth="1.8" strokeLinecap="round">
            <path d="M3 8c3-3 5 3 9 0s6-3 9 0" stroke="#8FA4F5" />
            <path d="M3 13c3-3 5 3 9 0s6-3 9 0" stroke="#8FA4F5" opacity=".7" />
            <path d="M3 18c3-3 5 3 9 0s6-3 9 0" stroke="#8FA4F5" opacity=".45" />
            <rect x="15.5" y="3" width="4" height="4" fill="#D7F04B" />
          </svg>
          <span className="text-lg font-semibold tracking-tight">Rootlane</span>
        </div>
        <div className="pointer-events-none absolute inset-x-4 bottom-4 flex flex-col items-start gap-2 sm:inset-x-6 sm:bottom-6">
          <AnimatePresence mode="wait">
            <motion.span key={phase} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }}
              className={`flex items-center gap-2 rounded-full border px-3 py-1 font-mono text-[11px] tracking-[0.14em] backdrop-blur ${PH.c}`}>
              <span className={`h-1.5 w-1.5 rounded-full bg-current ${attacked ? 'animate-ping' : ''}`} />
              {PH.t}
            </motion.span>
          </AnimatePresence>
          <span className="hidden font-mono text-[10.5px] text-mute-400 sm:block">drag the code to feel it</span>
        </div>
      </section>

      {/* PANEL DE INICIO DE SESIÓN */}
      <main className="relative z-10 flex flex-col justify-center overflow-hidden px-4 py-10 sm:px-10 lg:overflow-y-auto">
        {/* código tenue de fondo: textura, no protagonista */}
        <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden"
          style={{ maskImage: 'radial-gradient(90% 75% at 40% 40%, black 30%, transparent 85%)', WebkitMaskImage: 'radial-gradient(90% 75% at 40% 40%, black 30%, transparent 85%)' }}>
          <pre className="drift whitespace-pre px-6 pt-6 font-mono text-[12px] leading-[1.9] text-[#8FA4F5] opacity-[0.2]">
            {BG_CODE + BG_CODE}
          </pre>
        </div>
        <div className="relative mx-auto w-full max-w-[440px]">
        <div className="font-mono text-[12px] tracking-[0.3em] text-mute-300">[ ROOTLANE ]</div>
        <h1 className="mt-3 text-[34px] font-semibold leading-[1.02] tracking-[-0.035em] sm:text-[44px]" style={{ textWrap: 'balance' }}>
          Your app, under constant review
        </h1>
        <p className="mt-3 text-[15px] text-mute-300">
          Rootlane watches your production app every second, finds attacks as they happen, proves the fix on a replica, and ships it the moment you approve.
        </p>

        <ol className="mt-7 flex items-center gap-2">
          {STEPS.map((s, i) => (
            <li key={s} className="flex items-center gap-2">
              <span className={`flex h-6 w-6 items-center justify-center rounded-full font-mono text-[11px] ${i < step ? 'bg-lime text-ink-950' : i === step ? 'border border-lime text-lime' : 'border border-ink-600 text-mute-400'}`}>
                {i < step ? <Check className="h-3.5 w-3.5" strokeWidth={3} /> : i + 1}
              </span>
              <span className={`hidden text-xs sm:inline ${i === step ? 'text-mute-100' : 'text-mute-400'}`}>{s}</span>
              {i < STEPS.length - 1 && <span className="h-px w-6 bg-ink-600" />}
            </li>
          ))}
        </ol>

        <div className="mt-5 w-full">
          <AnimatePresence mode="wait">
            <motion.section key={step} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -12 }}
              className="rounded-2xl border border-ink-600 bg-ink-900 p-5 shadow-2xl">

              {step === 0 && (
                GITHUB_AUTH && MODE === 'live' && !useToken ? (
                <div className="space-y-4">
                  <div>
                    <h2 className="text-lg font-semibold">Sign in to Rootlane</h2>
                    <p className="mt-1 text-sm text-mute-400">Your GitHub account is recorded on every fix you approve.</p>
                  </div>
                  {authErr && <p role="alert" className="text-sm text-bad">{authErr}</p>}
                  <a href="/api/auth?a=login" className="hex flex w-full items-center justify-center gap-2 bg-mute-100 py-3 text-sm font-semibold text-ink-950 transition hover:bg-white">
                    <GitBranch className="h-4 w-4" /> Continue with GitHub
                  </a>
                  <button type="button" onClick={() => { setAuthErr(''); setUseToken(true) }} className="w-full text-center text-xs text-mute-400 hover:text-mute-200">Use an admin token instead</button>
                  <p className="flex items-center gap-1.5 text-xs text-mute-400"><Lock className="h-3.5 w-3.5" /> Only Rootlane team members can approve fixes. The admin token stays on the server.</p>
                </div>
                ) : (
                <form onSubmit={signIn} className="space-y-4">
                  <div>
                    <h2 className="text-lg font-semibold">Sign in to Rootlane</h2>
                    <p className="mt-1 text-sm text-mute-400">Your name is recorded on every fix you approve.</p>
                  </div>
                  <div className="space-y-1.5">
                    <label htmlFor="approver" className="block text-xs text-mute-300">Your name</label>
                    <input id="approver" required value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Valeria"
                      className="w-full rounded-lg border border-ink-600 bg-ink-950 px-3 py-2.5 text-sm text-mute-100 placeholder:text-mute-400 focus:border-lime/60 focus:outline-none" />
                  </div>
                  <div className="space-y-1.5">
                    <label htmlFor="token" className="block text-xs text-mute-300">Admin token {MODE === 'demo' && <span className="text-mute-400">(not needed in demo mode)</span>}</label>
                    <input id="token" type="password" required={MODE === 'live'} value={token} onChange={(e) => setToken(e.target.value)} placeholder="••••••••"
                      className="w-full rounded-lg border border-ink-600 bg-ink-950 px-3 py-2.5 font-mono text-sm text-mute-100 placeholder:text-mute-400 focus:border-lime/60 focus:outline-none" />
                  </div>
                  {authErr && <p role="alert" className="text-sm text-bad">{authErr}</p>}
                  <button type="submit" disabled={authBusy} className="hex w-full bg-mute-100 py-3 text-sm font-semibold text-ink-950 transition hover:bg-white disabled:opacity-60">{authBusy ? 'Checking token…' : 'Sign in'}</button>
                  <p className="flex items-center gap-1.5 text-xs text-mute-400"><Lock className="h-3.5 w-3.5" /> The token is checked against the Rootlane API, stays in this browser, and signs every approve or reject.</p>
                </form>
                )
              )}

              {step === 1 && (
                <div className="space-y-4">
                  <div>
                    <h2 className="text-lg font-semibold">What Rootlane is watching</h2>
                    <p className="mt-1 text-sm text-mute-400">These sources are already connected for this project.</p>
                  </div>
                  <ul className="divide-y divide-ink-700 rounded-xl border border-ink-700">
                    {SOURCES.map((src, i) => (
                      <li key={src.k} className="flex items-start gap-3 px-3 py-2.5">
                        <span className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center">
                          {checking === null ? <span className="h-1.5 w-1.5 rounded-full bg-ink-500" />
                            : i < checking ? <Check className="h-3.5 w-3.5 text-ok" strokeWidth={3} />
                            : i === checking ? <Loader2 className="h-3.5 w-3.5 animate-spin text-lime" />
                            : <span className="h-1.5 w-1.5 rounded-full bg-ink-500" />}
                        </span>
                        <span className="min-w-0">
                          <span className="block text-[11px] text-mute-400">{src.k}</span>
                          <span className="block truncate font-mono text-[12.5px] text-mute-100">{src.v}</span>
                          <span className="block text-[11.5px] text-mute-400">{src.d}</span>
                        </span>
                      </li>
                    ))}
                  </ul>
                  {checkFail && <p className="flex items-start gap-2 text-xs text-bad"><X className="mt-0.5 h-3.5 w-3.5 shrink-0" />{checkFail}</p>}
                  <button onClick={verifySources} disabled={checking !== null}
                    className="hex w-full bg-lime py-3 text-sm font-semibold text-ink-950 transition hover:brightness-105 disabled:opacity-60">
                    {checking !== null ? 'Checking…' : 'Check connection'}
                  </button>
                </div>
              )}

              {step === 2 && (
                <div className="space-y-4">
                  <div>
                    <h2 className="text-lg font-semibold">Turn on constant review</h2>
                    <p className="mt-1 text-sm text-mute-400">While it is on, this dashboard follows every request, verdict and agent step live.</p>
                  </div>

                  <button role="switch" aria-checked={review} onClick={() => setReview(!review)}
                    className={`flex w-full items-center gap-4 rounded-xl border p-4 text-left transition ${review ? 'border-lime/60 bg-lime/[0.06]' : 'border-ink-600 bg-ink-900'}`}>
                    <span className={`relative h-7 w-12 shrink-0 rounded-full transition ${review ? 'bg-lime' : 'bg-ink-600'}`}>
                      <span className={`absolute top-1 h-5 w-5 rounded-full bg-ink-950 transition-all ${review ? 'left-6' : 'left-1'}`} />
                    </span>
                    <span>
                      <span className="block text-[15px] font-semibold">Constant review {review ? 'ON' : 'OFF'}</span>
                      <span className="block text-xs text-mute-400">{review ? 'Attacks are detected and investigated on their own.' : 'The dashboard will not follow live activity.'}</span>
                    </span>
                  </button>

                  <div className="rounded-lg border border-ink-600 bg-ink-950 p-3 text-[13px] leading-relaxed text-mute-300">
                    <div className="eyebrow mb-1.5">Before anything reaches production</div>
                    <ul className="space-y-1">
                      {GUARDRAILS.slice(0, 4).map((g) => <li key={g.t} className="flex gap-2"><Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-ok" strokeWidth={3} />{g.t}</li>)}
                    </ul>
                  </div>

                  <button onClick={() => onFinish(review)}
                    className="hex w-full bg-lime py-3 text-sm font-semibold text-ink-950 transition hover:brightness-105">
                    {review ? 'Start constant review' : 'Go to dashboard'}
                  </button>
                </div>
              )}
            </motion.section>
          </AnimatePresence>
        </div>
        </div>
      </main>
    </div>
  )
}

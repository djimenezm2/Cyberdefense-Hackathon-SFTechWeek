import { useEffect, useState } from 'react'
import { LayoutDashboard, ShieldAlert, FileCheck2, LogOut, ScrollText } from 'lucide-react'
import { useAgent, MODE, readAuth, writeAuth } from './lib/useAgent'
import TopBar from './components/TopBar'
import Kpis from './components/Kpis'
import LiveSignals from './components/LiveSignals'
import LiveTerrain from './components/LiveTerrain'
import SurfaceMap from './components/SurfaceMap'
import Analyzer from './components/Analyzer'
import RequestLog from './components/RequestLog'
import AgentFeed from './components/AgentFeed'
import AttackAlert from './components/AttackAlert'
import LatestFix from './components/LatestFix'
import Incidents from './pages/Incidents'
import Guardrails from './pages/Guardrails'
import Audit from './pages/Audit'
import Onboarding from './pages/Onboarding'

const NAV = [
  { id: 'overview', label: 'Overview', icon: LayoutDashboard },
  { id: 'incidents', label: 'Incidents', icon: ShieldAlert },
  { id: 'audit', label: 'Audit', icon: ScrollText },
  { id: 'guardrails', label: 'Guardrails', icon: FileCheck2 },
]

const KEY = 'rootlane.session'
const read = () => { try { return localStorage.getItem(KEY) === 'in' } catch { return false } }
const write = (v) => { try { v ? localStorage.setItem(KEY, 'in') : localStorage.removeItem(KEY) } catch { /* ok */ } }

export default function App() {
  const { state, drill, approve, reject, setMonitoring, tokenSaved } = useAgent()
  const [signedIn, setSignedIn] = useState(read)
  const [page, setPage] = useState('overview')
  const active = Object.values(state.incidents).filter((i) => ['investigating', 'pending_approval', 'applying'].includes(i.status)).length

  // Atajo secreto para el demo: tecla "A" = nuestro agente atacante ataca la página.
  // (En modo real llama POST /api/drill; en modo demo reproduce el ataque simulado.)
  useEffect(() => {
    const onKey = (e) => {
      if (!signedIn || e.repeat || e.metaKey || e.ctrlKey || e.altKey) return
      if (['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName)) return
      if (e.key === 'a' || e.key === 'A') drill()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [signedIn, drill])

  // DEMO: ~30 s después de entrar, el agente atacante ataca solo y Rootlane responde en vivo
  useEffect(() => {
    if (!signedIn || MODE !== 'demo') return
    const t = setTimeout(() => drill(), 30000)
    return () => clearTimeout(t)
  }, [signedIn, drill])

  if (!signedIn) {
    return (
      <Onboarding state={state}
        onFinish={(review) => { setMonitoring(review); write(true); setSignedIn(true); setPage('overview') }} />
    )
  }

  return (
    <div className="flex min-h-full flex-col">
      <TopBar state={state} onToggleReview={setMonitoring} />
      <AttackAlert state={state} onApprove={approve} onReject={reject} onTokenSaved={tokenSaved} onOpen={() => setPage('incidents')} />

      <div className="flex flex-1 flex-col lg:flex-row">
        <nav className="flex gap-1 overflow-x-auto border-b border-ink-700 px-4 py-2 lg:w-56 lg:shrink-0 lg:flex-col lg:border-b-0 lg:border-r lg:px-3 lg:py-4">
          {NAV.map(({ id, label, icon: Icon }) => (
            <button key={id} onClick={() => setPage(id)}
              className={`btn shrink-0 justify-start ${page === id ? 'bg-ink-800 text-mute-100' : 'text-mute-400 hover:bg-ink-850 hover:text-mute-200'}`}>
              <Icon className="h-4 w-4" /> {label}
              {id === 'audit' && state.actions.length > 0 && <span className="ml-auto font-mono text-[10px] text-mute-400">{state.actions.length}</span>}
              {id === 'incidents' && active > 0 && <span className="ml-auto rounded bg-warn/20 px-1.5 font-mono text-[10px] text-warn">{active}</span>}
            </button>
          ))}
          <button onClick={() => { write(false); setSignedIn(false); if (readAuth().github) { writeAuth(null); fetch('/api/auth?a=logout', { method: 'POST' }).catch(() => {}) } }}
            className="btn shrink-0 justify-start text-mute-400 hover:bg-ink-850 hover:text-mute-200 lg:mt-auto">
            <LogOut className="h-4 w-4" /> Sign out
          </button>
        </nav>

        <main className="grid-bg min-w-0 flex-1 px-4 py-5 lg:px-6">
          {page === 'overview' && (
            <div className="grid gap-4 lg:h-[calc(100vh-110px)] lg:min-h-[760px] lg:grid-cols-[minmax(0,1fr)_400px]">
              <div className="scroll-thin min-w-0 space-y-4 lg:overflow-y-auto lg:pr-1">
                <LiveTerrain state={state} />
                <Kpis state={state} />
                <LatestFix incidents={state.incidents} onOpen={() => setPage('incidents')} />
                <div className="grid gap-4 2xl:grid-cols-2">
                  <LiveSignals metrics={state.metrics} />
                  <RequestLog requests={state.requests} />
                </div>
                <Analyzer windows={state.windows} />
                <SurfaceMap surface={state.surface} />
              </div>
              <AgentFeed state={state} onApprove={approve} onReject={reject} onTokenSaved={tokenSaved} />
            </div>
          )}
          {page === 'incidents' && <Incidents state={state} onApprove={approve} onReject={reject} onTokenSaved={tokenSaved} />}
          {page === 'audit' && <Audit actions={state.actions} />}
          {page === 'guardrails' && <Guardrails />}
        </main>
      </div>
    </div>
  )
}

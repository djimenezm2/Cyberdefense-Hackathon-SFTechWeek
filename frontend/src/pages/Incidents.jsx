import IncidentCard from '../components/IncidentCard'

export default function Incidents({ state, onApprove, onReject, onTokenSaved }) {
  const list = Object.values(state.incidents).sort((a, b) => b.ts - a.ts)
  const fixed = list.filter((i) => i.status === 'applied').length
  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <header>
        <div className="eyebrow">Incidents</div>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight">Everything Rootlane caught</h1>
        <p className="mt-1 text-sm text-mute-300">{list.length} incidents · {fixed} fixed</p>
      </header>
      {list.map((inc) => (
        <IncidentCard key={inc.id} inc={inc} onApprove={onApprove} onReject={onReject} needToken={state.needToken} onTokenSaved={onTokenSaved} defaultOpen={false} />
      ))}
    </div>
  )
}

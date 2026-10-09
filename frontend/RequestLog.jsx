import { clock } from '../lib/format'

// Últimas peticiones que vio Rootlane (formato de los fixtures de eventos)
const AUTH = {
  none: 'text-mute-400', accepted: 'text-mute-300', login_success: 'text-mute-300',
  login_failure: 'text-warn', rejected: 'text-ok',
}

export default function RequestLog({ requests }) {
  return (
    <section className="panel flex min-h-0 flex-col">
      <div className="panel-head">
        <div className="eyebrow">Request log · live</div>
        <span className="font-mono text-[10.5px] text-mute-400">{requests.length} recent</span>
      </div>
      <div className="scroll-thin overflow-x-auto px-2 pb-3">
        <table className="w-full min-w-[480px] font-mono text-[11px]">
          <thead>
            <tr className="text-left text-mute-400">
              {['Time', '', 'Route', 'Status', 'IP', 'Auth'].map((h) => <th key={h} className="px-2 py-1.5 font-normal">{h}</th>)}
            </tr>
          </thead>
          <tbody>
            {requests.slice(0, 9).map((r) => {
              const odd = r.param_flags?.length || r.auth_outcome === 'login_failure' || (r.principal_id === '22' && r.status === 200)
              return (
                <tr key={r.id} className="border-t border-ink-800">
                  <td className="num whitespace-nowrap px-2 py-1.5 text-mute-400">{clock(r.ts)}</td>
                  <td className="px-2 py-1.5 text-mute-400">{r.method}</td>
                  <td className="max-w-[180px] truncate px-2 py-1.5 text-mute-200">{r.route}</td>
                  <td className={`num px-2 py-1.5 ${r.status >= 400 ? 'text-warn' : 'text-mute-300'}`}>{r.status}</td>
                  <td className={`num whitespace-nowrap px-2 py-1.5 ${odd ? 'text-bad' : 'text-mute-400'}`}>{r.ip}</td>
                  <td className={`whitespace-nowrap px-2 py-1.5 ${AUTH[r.auth_outcome] ?? 'text-mute-400'}`}>
                    {r.auth_outcome}{r.param_flags?.length ? <span className="ml-1.5 text-bad">· {r.param_flags.join(',')}</span> : null}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </section>
  )
}
